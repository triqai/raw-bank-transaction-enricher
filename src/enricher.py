"""Transaction enricher with data loading and saving capabilities."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .client import TriqaiClient
from .models import EnrichmentResult, Transaction, TransactionType

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class TransactionEnricher:
    """High-level interface for enriching transactions from files."""

    def __init__(
        self,
        client: TriqaiClient,
        output_dir: str | Path = "output",
    ):
        """Initialize the enricher.

        Args:
            client: Configured TriqaiClient instance
            output_dir: Directory to save enrichment results
        """
        self.client = client
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_transactions_from_csv(self, csv_path: str | Path) -> list[Transaction]:
        """Load transactions from a CSV file.

        Expected CSV columns: country, type, title, comment (optional)

        Args:
            csv_path: Path to the CSV file

        Returns:
            List of Transaction objects
        """
        transactions = []
        csv_path = Path(csv_path)

        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                try:
                    txn_type = row.get("type", "expense").strip().lower()
                    if txn_type not in ("expense", "income"):
                        logger.warning(f"Row {row_num}: Invalid type '{txn_type}', defaulting to 'expense'")
                        txn_type = "expense"

                    transaction = Transaction(
                        title=row["title"].strip(),
                        country=row["country"].strip().upper(),
                        type=TransactionType(txn_type),
                        comment=row.get("comment", "").strip() or None,
                    )
                    transactions.append(transaction)

                except KeyError as e:
                    logger.error(f"Row {row_num}: Missing required column {e}")
                except ValueError as e:
                    logger.error(f"Row {row_num}: Validation error - {e}")

        logger.debug(f"Loaded {len(transactions)} transactions from {csv_path}")
        return transactions

    async def enrich_transactions(
        self,
        transactions: list[Transaction],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[EnrichmentResult]:
        """Enrich a list of transactions.

        Args:
            transactions: List of transactions to enrich
            progress_callback: Optional callback(completed, total) for progress updates

        Returns:
            List of EnrichmentResults
        """
        logger.debug(f"Starting enrichment of {len(transactions)} transactions...")
        results = await self.client.enrich_batch(transactions, progress_callback)

        # Log summary
        successful = sum(1 for r in results if r.success)
        partial = sum(1 for r in results if r.partial)
        failed = sum(1 for r in results if not r.success)

        logger.debug(
            f"Enrichment complete: {successful} successful, {partial} partial, {failed} failed"
        )

        return results

    def save_results(
        self,
        results: list[EnrichmentResult],
        filename: str | None = None,
        output_format: str = "json",
    ) -> Path:
        """Save enrichment results to a file.

        Args:
            results: List of EnrichmentResults to save
            filename: Output filename (without extension). Defaults to timestamp.
            output_format: Output format ('json' or 'jsonl')

        Returns:
            Path to the saved file
        """
        if filename is None:
            filename = f"enrichments_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        extension = ".jsonl" if output_format == "jsonl" else ".json"
        output_path = self.output_dir / f"{filename}{extension}"

        # Convert results to serializable format
        serializable_results = []
        for result in results:
            result_dict = result.model_dump(mode="json", exclude_none=True)
            serializable_results.append(result_dict)

        if output_format == "jsonl":
            with output_path.open("w", encoding="utf-8") as f:
                for result in serializable_results:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")
        else:
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(serializable_results, f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved {len(results)} results to {output_path}")
        return output_path

    def save_summary(self, results: list[EnrichmentResult], filename: str | None = None) -> Path:
        """Save a summary report of the enrichment results.

        Args:
            results: List of EnrichmentResults
            filename: Output filename (without extension)

        Returns:
            Path to the saved summary file
        """
        if filename is None:
            filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        output_path = self.output_dir / f"{filename}.json"

        # Calculate statistics
        total = len(results)
        successful = sum(1 for r in results if r.success)
        partial = sum(1 for r in results if r.partial)
        failed = sum(1 for r in results if not r.success)

        # Aggregate timing
        processing_times = [r.processing_time_ms for r in results if r.processing_time_ms]
        avg_time = sum(processing_times) / len(processing_times) if processing_times else 0
        total_time = sum(processing_times)

        # Count categories
        categories: dict[str, int] = {}
        merchants_found = 0
        locations_found = 0
        intermediaries_found = 0
        persons_found = 0

        for result in results:
            if result.data:
                # Category stats - use helper method
                primary_cat = result.data.transaction.get_primary_category_name()
                categories[primary_cat] = categories.get(primary_cat, 0) + 1

                # Entity stats - iterate entities array
                if result.data.merchant:
                    merchants_found += 1
                if result.data.location:
                    locations_found += 1
                if result.data.intermediary:
                    intermediaries_found += 1
                if result.data.person:
                    persons_found += 1

        summary = {
            "generated_at": datetime.now().isoformat(),
            "statistics": {
                "total_transactions": total,
                "successful": successful,
                "partial": partial,
                "failed": failed,
                "success_rate": f"{(successful / total * 100):.1f}%" if total > 0 else "0%",
            },
            "timing": {
                "total_processing_ms": round(total_time, 2),
                "average_processing_ms": round(avg_time, 2),
                "transactions_per_second": round(total / (total_time / 1000), 2) if total_time > 0 else 0,
            },
            "entities": {
                "merchants_found": merchants_found,
                "locations_found": locations_found,
                "intermediaries_found": intermediaries_found,
                "persons_found": persons_found,
            },
            "categories": dict(sorted(categories.items(), key=lambda x: -x[1])),
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved summary to {output_path}")
        return output_path

    def generate_report(self, results: list[EnrichmentResult]) -> str:
        """Generate a human-readable report of the enrichment results.

        Args:
            results: List of EnrichmentResults

        Returns:
            Formatted report string
        """
        total = len(results)
        successful = sum(1 for r in results if r.success)
        partial = sum(1 for r in results if r.partial)
        failed = sum(1 for r in results if not r.success)

        processing_times = [r.processing_time_ms for r in results if r.processing_time_ms]
        avg_time = sum(processing_times) / len(processing_times) if processing_times else 0
        total_time = sum(processing_times)

        report = [
            "=" * 60,
            "TRANSACTION ENRICHMENT REPORT",
            "=" * 60,
            "",
            "SUMMARY",
            "-" * 40,
            f"  Total transactions:     {total}",
            f"  Successful:             {successful} ({successful/total*100:.1f}%)" if total > 0 else "  Successful:             0",
            f"  Partial results:        {partial}",
            f"  Failed:                 {failed}",
            "",
            "TIMING",
            "-" * 40,
            f"  Total processing time:  {total_time/1000:.2f}s",
            f"  Average per transaction: {avg_time:.0f}ms",
            "",
        ]

        # Show sample results
        report.extend([
            "SAMPLE RESULTS",
            "-" * 40,
        ])

        for result in results[:5]:
            if result.success and result.data:
                # Get merchant name from entities array
                merchant_name = result.data.get_merchant_name() or "N/A"

                # Get category name using helper method
                category = result.data.transaction.get_primary_category_name()

                report.append(f"  '{result.input.title[:40]}...'")
                report.append(f"    -> Merchant: {merchant_name}")
                report.append(f"    -> Category: {category}")
                report.append("")

        report.append("=" * 60)

        return "\n".join(report)
