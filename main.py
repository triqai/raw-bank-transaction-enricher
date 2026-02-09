#!/usr/bin/env python3
"""Bank Transaction Enricher - Transform raw transactions into structured data.

Usage:
    python main.py                          # Enrich sample dataset
    python main.py --input your_data.csv    # Enrich custom dataset
    python main.py --help                   # Show all options
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from src import TriqaiClient, TransactionEnricher

# Load environment variables
load_dotenv()

# Setup rich console
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging - quiet by default for clean output."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s")
    # Suppress httpx logs unless verbose
    logging.getLogger("httpx").setLevel(logging.WARNING if not verbose else logging.DEBUG)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Enrich bank transactions using the Triqai API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --input data/transactions.csv --output-dir results
  python main.py --format jsonl --verbose

Environment Variables:
  TRIQAI_API_KEY          Your Triqai API key (required)
  MAX_CONCURRENT_REQUESTS Maximum concurrent requests (default: 5)
  REQUEST_DELAY           Delay between requests in seconds (default: 0.1)
        """,
    )

    parser.add_argument(
        "--input", "-i",
        type=str,
        default="data/transactions.csv",
        help="Path to input CSV file (default: data/transactions.csv)",
    )

    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="output",
        help="Directory to save output files (default: output)",
    )

    parser.add_argument(
        "--format", "-f",
        choices=["json", "jsonl"],
        default="json",
        help="Output format (default: json)",
    )

    parser.add_argument(
        "--max-concurrent", "-c",
        type=int,
        default=None,
        help="Maximum concurrent requests (default: from env or 5)",
    )

    parser.add_argument(
        "--api-key", "-k",
        type=str,
        default=None,
        help="Triqai API key (default: from TRIQAI_API_KEY env var)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load transactions but don't make API calls",
    )

    return parser.parse_args()


def display_results_table(results: list) -> None:
    """Display a summary table of enrichment results."""
    table = Table(title="Enrichment Results", show_lines=True)

    table.add_column("Transaction", style="cyan", max_width=40)
    table.add_column("Status", style="green")
    table.add_column("Merchant", style="yellow")
    table.add_column("Category", style="magenta")
    table.add_column("Time (ms)", justify="right")

    for result in results[:15]:  # Show first 15
        status = "[green]Success" if result.success else "[red]Failed"
        if result.partial:
            status = "[yellow]Partial"

        merchant = "N/A"
        category = "N/A"

        if result.data:
            # Get merchant name safely
            enrichments = result.data.enrichments
            if enrichments and enrichments.merchant and enrichments.merchant.data:
                merchant = enrichments.merchant.data.name

            # Get category name using helper method
            category = result.data.transaction.get_primary_category_name()

        time_str = f"{result.processing_time_ms:.0f}" if result.processing_time_ms else "-"

        table.add_row(
            result.input.title[:40] + ("..." if len(result.input.title) > 40 else ""),
            status,
            merchant,
            category,
            time_str,
        )

    if len(results) > 15:
        table.add_row(f"... and {len(results) - 15} more", "", "", "", "")

    console.print(table)


async def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Get API key
    api_key = args.api_key or os.getenv("TRIQAI_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] TRIQAI_API_KEY environment variable not set")
        console.print("Set it with: export TRIQAI_API_KEY=your_api_key_here")
        console.print("Or use: python main.py --api-key your_api_key_here")
        return 1

    # Get configuration
    max_concurrent = args.max_concurrent or int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))
    request_delay = float(os.getenv("REQUEST_DELAY", "0.1"))

    # Check input file exists
    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]Error:[/red] Input file not found: {input_path}")
        return 1

    console.print()
    console.print("[bold]Bank Transaction Enricher[/bold]")
    console.print(f"[dim]Input: {input_path} → Output: {args.output_dir}/[/dim]")
    console.print()

    # Initialize client and enricher
    client = TriqaiClient(
        api_key=api_key,
        max_concurrent=max_concurrent,
        request_delay=request_delay,
    )

    enricher = TransactionEnricher(
        client=client,
        output_dir=args.output_dir,
    )

    # Load transactions
    console.print("[bold]Loading transactions...[/bold]")
    transactions = enricher.load_transactions_from_csv(input_path)
    console.print(f"Loaded [green]{len(transactions)}[/green] transactions\n")

    if args.dry_run:
        console.print("[yellow]Dry run mode - skipping API calls[/yellow]")
        for i, txn in enumerate(transactions[:5], 1):
            console.print(f"  {i}. {txn.country} | {txn.type.value} | {txn.title[:50]}...")
        if len(transactions) > 5:
            console.print(f"  ... and {len(transactions) - 5} more")
        return 0

    # Enrich with progress bar
    console.print("[bold]Enriching transactions...[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing", total=len(transactions))

        def update_progress(completed: int, total: int) -> None:
            progress.update(task, completed=completed)

        results = await enricher.enrich_transactions(transactions, update_progress)

    console.print()

    # Display results table
    display_results_table(results)

    # Save results
    console.print("\n[bold]Saving results...[/bold]")

    results_path = enricher.save_results(results, format=args.format)
    console.print(f"  Results saved to: [green]{results_path}[/green]")

    summary_path = enricher.save_summary(results)
    console.print(f"  Summary saved to: [green]{summary_path}[/green]")

    # Print summary statistics
    console.print("\n[bold]Summary:[/bold]")
    successful = sum(1 for r in results if r.success)
    partial = sum(1 for r in results if r.partial)
    failed = sum(1 for r in results if not r.success)

    console.print(f"  [green]Successful:[/green] {successful}/{len(results)}")
    if partial:
        console.print(f"  [yellow]Partial:[/yellow] {partial}")
    if failed:
        console.print(f"  [red]Failed:[/red] {failed}")

    # Show rate limit info
    if client.rate_limit_info:
        info = client.rate_limit_info
        console.print(f"\n[dim]Rate limit: {info.remaining}/{info.limit} remaining[/dim]")

    console.print()
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        sys.exit(1)
