# Bank Transaction Enricher

> Transform raw, cryptic bank transaction strings into clean, structured data -- merchant names, categories, locations, and more.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

**Before** a raw bank statement line:

```
SQ *VERVE ROASTERS gosq.com CA
```

**After** structured, enriched data:

```json
{
  "merchant": { "name": "Verve Coffee Roasters", "website": "vervecoffee.com" },
  "category": { "primary": "Food & Beverages", "secondary": "Cafes" },
  "location": { "city": "Santa Cruz", "state": "CA", "country": "US" },
  "channel": "in_store",
  "paymentProcessor": { "name": "Square" }
}
```

## Why?

Bank transaction descriptions are messy. They're truncated, filled with reference codes, and inconsistent across banks and countries. This tool takes those raw strings and returns structured data you can actually use for dashboards, expense tracking, financial analytics, or PFM apps.

Powered by the [Triqai API](https://triqai.com), which handles merchant identification, categorization, and enrichment.

## Features

- **Merchant Identification**: Resolve raw strings to clean merchant names, logos, and websites
- **Smart Categorization**: Hierarchical categories (primary/secondary/tertiary) with MCC, SIC, and NAICS codes
- **Location Extraction**: Structured addresses, coordinates, and timezones
- **Payment Processor Detection**: Identify Square, Stripe, Adyen, PayPal, and others
- **P2P Recognition**: Detect Venmo, Zelle, PIX, Tikkie, VIPPS, and other transfer platforms
- **Subscription Detection**: Flag recurring payments and classify subscription types
- **Async & Concurrent**: Process hundreds of transactions in parallel with built-in rate limiting
- **Rich CLI Output**: Progress bars, colored tables, and summary statistics

## Quick Start

### 1. Install dependencies

```bash
git clone https://github.com/triqai/bank-transaction-enricher.git
cd bank-transaction-enricher
pip install -r requirements.txt
```

### 2. Get your API key

Sign up for a free API key at **[triqai.com](https://triqai.com)** the free tier includes enough requests to test with the included sample dataset.

```bash
cp .env.example .env
# Edit .env and add your API key
```

### 3. Run

```bash
python main.py
```

That's it. The sample dataset of 40 real-world transactions will be enriched and results saved to `output/`.

## Usage

### Command Line

```bash
# Enrich the included sample dataset
python main.py

# Use your own CSV file
python main.py --input your_transactions.csv

# Save as JSON Lines (one object per line, better for streaming)
python main.py --format jsonl

# Increase concurrency for large datasets
python main.py --max-concurrent 10

# Preview without making API calls
python main.py --dry-run

# Verbose logging for debugging
python main.py --verbose

# See all options
python main.py --help
```

### Python API

```python
import asyncio
from src import TriqaiClient, Transaction

async def main():
    client = TriqaiClient(api_key="your_api_key")

    transaction = Transaction(
        title="AMAZON MKTPLACE PMTS AMZN.COM/BILL WA",
        country="US",
        type="expense",
    )

    result = await client.enrich(transaction)

    if result.success:
        data = result.data
        enrichments = data.enrichments

        # Merchant info
        if enrichments.merchant and enrichments.merchant.data:
            print(f"Merchant: {enrichments.merchant.data.name}")
            print(f"Website:  {enrichments.merchant.data.website}")

        # Category
        print(f"Category: {data.transaction.get_primary_category_name()}")

        # Location
        if enrichments.location and enrichments.location.data:
            loc = enrichments.location.data
            print(f"Location: {loc.structured.city}, {loc.structured.state}")

asyncio.run(main())
```

### Batch Processing

```python
import asyncio
from src import TriqaiClient, TransactionEnricher

async def main():
    client = TriqaiClient(api_key="your_api_key", max_concurrent=10)
    enricher = TransactionEnricher(client=client, output_dir="results")

    # Load from CSV
    transactions = enricher.load_transactions_from_csv("data/transactions.csv")

    # Enrich all (with automatic rate limiting and retries)
    results = await enricher.enrich_transactions(transactions)

    # Save results
    enricher.save_results(results, output_format="json")
    enricher.save_summary(results)

    # Print report
    print(enricher.generate_report(results))

asyncio.run(main())
```

## Input Format

Prepare a CSV with these columns:

```csv
country,type,title,comment
US,expense,"SQ *VERVE ROASTERS gosq.com CA",Coffee shop
GB,expense,"CARD PAYMENT - FALLOW LONDON",Restaurant
BR,expense,"PIX ENVIADO - JOAO SILVA",P2P transfer
NL,income,"SALARIS DECEMBER 25 #890",Monthly salary
```

| Column    | Required | Description                                |
| --------- | -------- | ------------------------------------------ |
| `country` | Yes      | ISO 3166-1 alpha-2 code (`US`, `GB`, `BR`) |
| `type`    | Yes      | `expense` or `income`                      |
| `title`   | Yes      | Raw transaction string from the bank       |
| `comment` | No       | Optional note (not sent to API)            |

### Sample Dataset

The included `data/transactions.csv` covers diverse real-world patterns across 18 countries:

| Pattern       | Examples                                                           |
| ------------- | ------------------------------------------------------------------ |
| Retail        | Amazon (DE long-form SEPA), Walmart, Target                        |
| Food & Drink  | Restaurants, coffee shops, delivery services                       |
| Subscriptions | Adobe Creative Cloud, Apple One                                    |
| P2P Transfers | PIX (BR), Venmo (US), Tikkie (NL), VIPPS (NO)                      |
| Payroll       | Salary deposits (US, NL, KR, JP)                                   |
| Freelance     | Upwork payouts, Adobe Stock, Twitch affiliates                     |
| International | Japanese (ファミリーマート), Korean (삼성전자), special characters |
| Complex       | Multi-processor chains, long SEPA references                       |

## Output

Results are saved to the `output/` directory:

- **`enrichments_<timestamp>.json`**: Full enrichment data for each transaction
- **`summary_<timestamp>.json`**: Aggregate statistics and category distribution

### Example Enrichment Response

```json
{
  "input": {
    "title": "SQ *VERVE ROASTERS gosq.com CA",
    "country": "US",
    "type": "expense"
  },
  "success": true,
  "data": {
    "transaction": {
      "category": {
        "primary": {
          "name": "Food & Beverages",
          "code": { "mcc": 5814, "sic": 5812, "naics": 722515 }
        },
        "secondary": {
          "name": "Cafes",
          "code": { "mcc": 5814, "sic": 5812, "naics": 722515 }
        },
        "confidence": 95
      },
      "channel": "in_store",
      "subscription": { "recurring": false },
      "confidence": 92
    },
    "enrichments": {
      "merchant": {
        "status": "found",
        "confidence": 95,
        "data": {
          "id": "...",
          "name": "Verve Coffee Roasters",
          "alias": [],
          "website": "vervecoffee.com",
          "icon": "https://..."
        }
      },
      "location": {
        "status": "found",
        "confidence": 85,
        "data": {
          "id": "...",
          "name": "Verve Coffee Roasters",
          "formatted": "1540 Pacific Ave, Santa Cruz, CA 95060, US",
          "structured": {
            "street": "1540 Pacific Ave",
            "city": "Santa Cruz",
            "state": "CA",
            "postalCode": "95060",
            "country": "US",
            "countryName": "United States",
            "coordinates": { "latitude": 36.9741, "longitude": -122.0308 },
            "timezone": "America/Los_Angeles"
          }
        }
      },
      "paymentProcessor": {
        "status": "found",
        "confidence": 99,
        "data": { "id": "...", "name": "Square", "website": "squareup.com" }
      },
      "peerToPeer": {
        "status": "not_applicable",
        "confidence": null,
        "data": null
      }
    }
  }
}
```

## Configuration

| Environment Variable      | Default | Description                              |
| ------------------------- | ------- | ---------------------------------------- |
| `TRIQAI_API_KEY`          | --      | Your Triqai API key (**required**)       |
| `MAX_CONCURRENT_REQUESTS` | `5`     | Maximum parallel API requests            |
| `REQUEST_DELAY`           | `0.1`   | Minimum delay between requests (seconds) |

All options can also be passed as CLI arguments. Run `python main.py --help` for details.

## Rate Limiting

The client automatically handles API rate limits with exponential backoff and retries. You don't need to manage this yourself. The API uses a **token bucket algorithm** you can burst up to `Remaining` requests instantly, then tokens refill at `Limit` per second. Current rate limit status is displayed after each run and can be inspected via:

```python
client.rate_limit_info  # RateLimitInfo(limit=10, remaining=87, reset='2026-01-19T10:30:00Z', burst=100)
```

Response headers tracked:

- `X-RateLimit-Limit`: Requests per second (sustained refill rate)
- `X-RateLimit-Remaining`: Current tokens available (can burst up to this many instantly)
- `X-RateLimit-Reset`: ISO timestamp when tokens start refilling
- `X-RateLimit-Burst`: Maximum burst capacity

## Project Structure

```
bank-transaction-enricher/
├── main.py              # CLI entry point
├── src/
│   ├── __init__.py      # Package exports
│   ├── client.py        # Async API client with rate limiting & retries
│   ├── enricher.py      # High-level enrichment orchestrator
│   └── models.py        # Pydantic models for API request/response
├── data/
│   └── transactions.csv # Sample dataset (40 transactions, 18 countries)
├── output/              # Generated results (git-ignored)
├── pyproject.toml       # Project metadata and tool config
├── requirements.txt     # Python dependencies
└── .env.example         # Environment variable template
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linter
ruff check .

# Run type checker
mypy src/

# Run tests
pytest
```

## License

MIT License, see [LICENSE](LICENSE) for details.
