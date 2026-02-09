"""Pydantic models for Triqai API request and response structures."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TransactionType(str, Enum):
    """Transaction direction type."""

    EXPENSE = "expense"
    INCOME = "income"


class TransactionChannel(str, Enum):
    """How the transaction was conducted."""

    IN_STORE = "in_store"
    ONLINE = "online"
    MOBILE_APP = "mobile_app"
    ATM = "atm"
    BANK_TRANSFER = "bank_transfer"
    UNKNOWN = "unknown"


class EnrichmentStatus(str, Enum):
    """Enrichment module result status."""

    FOUND = "found"
    NO_MATCH = "no_match"
    NOT_APPLICABLE = "not_applicable"


class SubscriptionType(str, Enum):
    """Subscription category types."""

    STREAMING = "streaming"
    SOFTWARE = "software"
    NEWS = "news"
    FITNESS = "fitness"
    MOBILE = "mobile"
    GAMING = "gaming"
    UTILITIES = "utilities"
    OTHER = "other"


# Request Models


class Transaction(BaseModel):
    """Input transaction to enrich."""

    title: str = Field(..., min_length=1, max_length=256, description="Transaction title from bank statement")
    country: str = Field(..., pattern=r"^[A-Za-z]{2}$", description="ISO 3166-1 alpha-2 country code")
    type: TransactionType = Field(..., description="Transaction direction (expense/income)")
    comment: str | None = Field(None, description="Optional comment about the transaction")

    def to_api_request(self) -> dict[str, str]:
        """Convert to API request payload."""
        return {
            "title": self.title,
            "country": self.country.upper(),
            "type": self.type.value,
        }


# Response Models


class Coordinates(BaseModel):
    """Geographic coordinates."""

    latitude: float
    longitude: float


class CategoryCode(BaseModel):
    """Industry classification codes."""

    mcc: int | None = Field(None, description="Merchant Category Code")
    sic: int | None = Field(None, description="Standard Industrial Classification")
    naics: int | None = Field(None, description="NAICS code")


class Category(BaseModel):
    """Category information.

    Handles both nested format (code.mcc) and flat format (mcc directly on category).
    """

    name: str
    # Nested code object (from some API responses)
    code: CategoryCode | None = None
    # Flat fields (from CategoryInfo format)
    mcc: int | None = None
    sic: int | None = None
    naics: int | None = None
    # Additional fields from CategoryInfo
    type: str | None = None  # primary, secondary, tertiary
    level: int | None = None  # 1, 2, 3
    parent: str | None = None
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_category_codes(cls, data: Any) -> Any:
        """Normalize category codes from either flat or nested format."""
        if isinstance(data, dict):
            # If we have flat mcc/sic/naics but no code object, create one
            if "code" not in data and any(k in data for k in ("mcc", "sic", "naics")):
                data["code"] = {
                    "mcc": data.get("mcc"),
                    "sic": data.get("sic"),
                    "naics": data.get("naics"),
                }
            # If we have a code object, also set flat fields for convenience
            elif "code" in data and isinstance(data["code"], dict):
                data["mcc"] = data.get("mcc") or data["code"].get("mcc")
                data["sic"] = data.get("sic") or data["code"].get("sic")
                data["naics"] = data.get("naics") or data["code"].get("naics")
        return data

    def get_mcc(self) -> int | None:
        """Get MCC code from either format."""
        if self.code and self.code.mcc:
            return self.code.mcc
        return self.mcc

    def get_sic(self) -> int | None:
        """Get SIC code from either format."""
        if self.code and self.code.sic:
            return self.code.sic
        return self.sic

    def get_naics(self) -> int | None:
        """Get NAICS code from either format."""
        if self.code and self.code.naics:
            return self.code.naics
        return self.naics


class CategoryStructure(BaseModel):
    """Hierarchical category structure."""

    primary: Category
    secondary: Category | None = None
    tertiary: Category | None = None
    confidence: int = Field(default=0, ge=0, le=100)


class Subscription(BaseModel):
    """Subscription detection result."""

    recurring: bool
    type: SubscriptionType | None = None


class StructuredAddress(BaseModel):
    """Structured address information."""

    street: str | None = None
    city: str | None = None
    state: str | None = None
    postalCode: str | None = None
    country: str | None = None
    countryName: str | None = None
    coordinates: Coordinates | None = None
    timezone: str | None = None


class MerchantData(BaseModel):
    """Merchant information."""

    id: str | None = None
    name: str
    alias: list[str] = []
    keywords: list[str] | None = None
    icon: str | None = None
    description: str | None = None
    color: str | None = None
    website: str | None = None
    domain: str | None = None


class LocationData(BaseModel):
    """Location information."""

    id: str | None = None
    name: str | None = None
    formatted: str | None = None
    phoneNumber: str | None = None
    structured: StructuredAddress | None = None


class PaymentProcessorData(BaseModel):
    """Payment processor information."""

    id: str | None = None
    name: str
    icon: str | None = None
    color: str | None = None
    website: str | None = None


class P2PPlatformInfo(BaseModel):
    """P2P platform information."""

    id: str | None = None
    name: str | None = None
    icon: str | None = None
    color: str | None = None
    website: str | None = None


class P2PRecipient(BaseModel):
    """P2P recipient information."""

    displayName: str | None = None


class P2PData(BaseModel):
    """P2P transfer information."""

    platform: P2PPlatformInfo | None = None
    recipient: P2PRecipient | None = None
    memo: str | None = None


class MerchantEnrichment(BaseModel):
    """Merchant enrichment result."""

    status: EnrichmentStatus
    confidence: int | None = None
    data: MerchantData | None = None


class LocationEnrichment(BaseModel):
    """Location enrichment result."""

    status: EnrichmentStatus
    confidence: int | None = None
    data: LocationData | None = None


class PaymentProcessorEnrichment(BaseModel):
    """Payment processor enrichment result."""

    status: EnrichmentStatus
    confidence: int | None = None
    data: PaymentProcessorData | None = None


class P2PEnrichment(BaseModel):
    """P2P enrichment result."""

    status: EnrichmentStatus
    confidence: int | None = None
    data: P2PData | None = None


class Enrichments(BaseModel):
    """All enrichment results."""

    merchant: MerchantEnrichment | None = None
    location: LocationEnrichment | None = None
    paymentProcessor: PaymentProcessorEnrichment | None = None
    peerToPeer: P2PEnrichment | None = None


class TransactionData(BaseModel):
    """Enriched transaction data."""

    model_config = {"extra": "allow"}

    category: Any = None
    subscription: Subscription | None = None
    channel: TransactionChannel | str = TransactionChannel.UNKNOWN
    confidence: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def normalize_transaction_data(cls, data: Any) -> Any:
        """Normalize transaction data from API response."""
        if isinstance(data, dict):
            # Handle channel as string
            if "channel" in data and isinstance(data["channel"], str):
                try:
                    data["channel"] = TransactionChannel(data["channel"])
                except ValueError:
                    data["channel"] = TransactionChannel.UNKNOWN
        return data

    @property
    def category_structure(self) -> CategoryStructure | None:
        """Get category as a CategoryStructure if possible."""
        if self.category is None:
            return None
        if isinstance(self.category, CategoryStructure):
            return self.category
        if isinstance(self.category, dict):
            try:
                # Try to parse as CategoryStructure
                if "primary" in self.category:
                    return CategoryStructure.model_validate(self.category)
                # If it's a flat category, wrap it
                elif "name" in self.category:
                    return CategoryStructure(
                        primary=Category.model_validate(self.category),
                        confidence=self.category.get("confidence", 0),
                    )
            except Exception:
                pass
        return None

    def get_primary_category_name(self) -> str:
        """Safely get the primary category name."""
        if self.category is None:
            return "Unknown"

        # If it's already a CategoryStructure
        if isinstance(self.category, CategoryStructure):
            return self.category.primary.name

        # If it's a dict
        if isinstance(self.category, dict):
            # Check for nested primary
            if "primary" in self.category:
                primary = self.category["primary"]
                if isinstance(primary, dict):
                    return primary.get("name", "Unknown")
                if isinstance(primary, Category):
                    return primary.name
            # Flat format
            if "name" in self.category:
                return self.category["name"]

        return "Unknown"


class EnrichmentData(BaseModel):
    """Complete enrichment data."""

    transaction: TransactionData
    enrichments: Enrichments


class ResponseMeta(BaseModel):
    """Response metadata."""

    generatedAt: datetime
    requestId: str
    version: str
    categoryVersion: str | None = None
    errors: list[str] | None = None


class EnrichSuccessResponse(BaseModel):
    """Successful enrichment response."""

    success: bool
    partial: bool
    data: EnrichmentData
    meta: ResponseMeta


class ErrorDetail(BaseModel):
    """Error details."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool
    error: ErrorDetail
    meta: ResponseMeta


class RateLimitInfo(BaseModel):
    """Rate limit information from response headers."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> RateLimitInfo:
        """Parse rate limit info from response headers."""
        return cls(
            limit=int(headers.get("X-RateLimit-Limit", 0)) or None,
            remaining=int(headers.get("X-RateLimit-Remaining", 0)) or None,
            reset=int(headers.get("X-RateLimit-Reset", 0)) or None,
        )


class EnrichmentResult(BaseModel):
    """Combined result with input transaction and enrichment."""

    input: Transaction
    success: bool
    partial: bool = False
    data: EnrichmentData | None = None
    error: ErrorDetail | None = None
    request_id: str | None = None
    processing_time_ms: float | None = None
