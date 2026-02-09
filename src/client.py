"""Triqai API client with rate limiting and retry logic."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .models import (
    EnrichmentResult,
    EnrichSuccessResponse,
    ErrorResponse,
    RateLimitInfo,
    Transaction,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class TriqaiAPIError(Exception):
    """Base exception for Triqai API errors."""

    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class RateLimitError(TriqaiAPIError):
    """Rate limit exceeded error."""

    def __init__(self, message: str, reset_time: int | None = None):
        super().__init__(message, status_code=429, error_code="rate_limited")
        self.reset_time = reset_time


class AuthenticationError(TriqaiAPIError):
    """Authentication failed error."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(message, status_code=401, error_code="authentication_error")


class InsufficientCreditsError(TriqaiAPIError):
    """Insufficient credits error."""

    def __init__(self, message: str = "Insufficient credits"):
        super().__init__(message, status_code=402, error_code="insufficient_credits")


class TriqaiClient:
    """Async client for the Triqai Transaction Enrichment API.

    Features:
    - Automatic rate limit handling with backoff
    - Retry logic with exponential backoff
    - Concurrent request management
    - Detailed logging and error handling
    """

    BASE_URL = "https://api.triqai.com"
    ENRICH_ENDPOINT = "/v1/transactions/enrich"

    def __init__(
        self,
        api_key: str,
        max_concurrent: int = 5,
        request_delay: float = 0.1,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """Initialize the Triqai client.

        Args:
            api_key: Triqai API key
            max_concurrent: Maximum concurrent requests
            request_delay: Delay between requests in seconds
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.api_key = api_key
        self.max_concurrent = max_concurrent
        self.request_delay = request_delay
        self.timeout = timeout
        self.max_retries = max_retries

        self._semaphore: asyncio.Semaphore | None = None
        self._rate_limit_info: RateLimitInfo | None = None
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication."""
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _wait_for_rate_limit(self) -> None:
        """Wait if rate limit is approaching or exceeded."""
        async with self._rate_limit_lock:
            if self._rate_limit_info and self._rate_limit_info.remaining == 0:
                reset_ts = self._rate_limit_info.get_reset_timestamp()
                if reset_ts:
                    wait_time = max(0, reset_ts - time.time())
                    if wait_time > 0:
                        logger.warning(f"Rate limit reached. Waiting {wait_time:.1f}s until reset...")
                        await asyncio.sleep(wait_time + 0.5)  # Add buffer

            # Enforce minimum delay between requests
            elapsed = time.time() - self._last_request_time
            if elapsed < self.request_delay:
                await asyncio.sleep(self.request_delay - elapsed)

    def _update_rate_limit_info(self, headers: httpx.Headers) -> None:
        """Update rate limit info from response headers."""
        self._rate_limit_info = RateLimitInfo.from_headers(dict(headers))
        self._last_request_time = time.time()

        if self._rate_limit_info.remaining is not None:
            logger.debug(
                f"Rate limit: {self._rate_limit_info.remaining}/{self._rate_limit_info.limit} remaining"
            )

    async def _make_request(
        self,
        client: httpx.AsyncClient,
        transaction: Transaction,
    ) -> EnrichmentResult:
        """Make a single API request with retry logic."""
        start_time = time.perf_counter()

        @retry(
            retry=retry_if_exception_type(RateLimitError),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=60),
            reraise=True,
        )
        async def _request_with_retry() -> httpx.Response:
            await self._wait_for_rate_limit()

            response = await client.post(
                f"{self.BASE_URL}{self.ENRICH_ENDPOINT}",
                json=transaction.to_api_request(),
                headers=self._get_headers(),
                timeout=self.timeout,
            )

            self._update_rate_limit_info(response.headers)

            if response.status_code == 429:
                reset_time = self._rate_limit_info.reset if self._rate_limit_info else None
                raise RateLimitError("Rate limit exceeded", reset_time=reset_time)

            return response

        try:
            response = await _request_with_retry()
            processing_time = (time.perf_counter() - start_time) * 1000

            if response.status_code == 200:
                success_response = EnrichSuccessResponse.model_validate(response.json())
                return EnrichmentResult(
                    input=transaction,
                    success=True,
                    partial=success_response.partial,
                    data=success_response.data,
                    request_id=success_response.meta.requestId,
                    processing_time_ms=processing_time,
                )

            # Handle error responses
            error_response = ErrorResponse.model_validate(response.json())

            if response.status_code == 401:
                raise AuthenticationError(error_response.error.message)
            elif response.status_code == 402:
                raise InsufficientCreditsError(error_response.error.message)
            else:
                return EnrichmentResult(
                    input=transaction,
                    success=False,
                    error=error_response.error,
                    request_id=error_response.meta.requestId,
                    processing_time_ms=processing_time,
                )

        except RetryError as e:
            processing_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"Max retries exceeded for transaction: {transaction.title[:50]}...")
            return EnrichmentResult(
                input=transaction,
                success=False,
                error={
                    "code": "max_retries_exceeded",
                    "message": f"Failed after {self.max_retries} attempts: {str(e.last_attempt.exception())}",
                },
                processing_time_ms=processing_time,
            )

        except httpx.TimeoutException:
            processing_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"Timeout for transaction: {transaction.title[:50]}...")
            return EnrichmentResult(
                input=transaction,
                success=False,
                error={"code": "timeout", "message": f"Request timed out after {self.timeout}s"},
                processing_time_ms=processing_time,
            )

        except httpx.RequestError as e:
            processing_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"Request error for transaction: {transaction.title[:50]}... - {e}")
            return EnrichmentResult(
                input=transaction,
                success=False,
                error={"code": "request_error", "message": str(e)},
                processing_time_ms=processing_time,
            )

    async def enrich(self, transaction: Transaction) -> EnrichmentResult:
        """Enrich a single transaction.

        Args:
            transaction: Transaction to enrich

        Returns:
            EnrichmentResult with enriched data or error information
        """
        async with httpx.AsyncClient() as client:
            return await self._make_request(client, transaction)

    async def enrich_batch(
        self,
        transactions: list[Transaction],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[EnrichmentResult]:
        """Enrich multiple transactions concurrently.

        Uses a shared HTTP client for connection pooling across all requests,
        with a semaphore to limit concurrency.

        Args:
            transactions: List of transactions to enrich
            progress_callback: Optional callback(completed, total) for progress updates

        Returns:
            List of EnrichmentResults in the same order as input transactions
        """
        if not transactions:
            return []

        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        completed = 0
        total = len(transactions)

        async def process_one(
            shared_client: httpx.AsyncClient, idx: int, txn: Transaction
        ) -> tuple[int, EnrichmentResult]:
            async with self._semaphore:
                result = await self._make_request(shared_client, txn)
                return idx, result

        async with httpx.AsyncClient() as client:
            tasks = [process_one(client, i, txn) for i, txn in enumerate(transactions)]

            results_dict: dict[int, EnrichmentResult] = {}

            for coro in asyncio.as_completed(tasks):
                idx, result = await coro
                results_dict[idx] = result
                completed += 1

                if progress_callback:
                    progress_callback(completed, total)

                logger.debug(
                    f"Completed {completed}/{total}: {result.input.title[:40]}... "
                    f"({'success' if result.success else 'failed'})"
                )

        return [results_dict[i] for i in range(len(transactions))]

    @property
    def rate_limit_info(self) -> RateLimitInfo | None:
        """Get the current rate limit information."""
        return self._rate_limit_info
