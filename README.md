# Bank Transaction Enricher

Transform cryptic bank transaction strings into structured, actionable data.

**Before:**
```
SQ *VERVE ROASTERS gosq.com CA
```

**After:**
```json
{
  "merchant": "Verve Coffee Roasters",
  "category": "Food & Beverages → Cafes",
  "location": "Santa Cruz, CA",
  "channel": "in_store",
  "payment_processor": "Square"
}
```

## Features

- **Merchant Identification** — Clean names, logos, and websites
- **Smart Categorization** — Hierarchical categories with MCC/SIC/NAICS codes
- **Location Extraction** — Addresses, coordinates, and timezones
- **Payment Detection** — Identify processors like Stripe, Square, PayPal
- **P2P Recognition** — Detect Venmo, Zelle, PIX, and other transfer platforms
- **Subscription Detection** — Flag recurring payments automatically

## Quick Start

```bash
# Clone the repository
git clone https://github.com/triqai/bank-transaction-enricher.git
cd bank-transaction-enricher

# Install dependencies
pip install -r requirements.txt

# Set your API key
export TRIQAI_API_KEY=your_api_key_here

# Run enrichment
python main.py
```

Get your free API key at [triqai.com](https://triqai.com)

## Sample Dataset

The included dataset covers real-world transaction patterns:

| Type | Examples |
|------|----------|
| Retail | Amazon, Walmart, Target |
| Food & Drink | Restaurants, coffee shops, delivery |
| Subscriptions | Adobe, Apple, Netflix |
| P2P Transfers | PIX, Venmo, Tikkie, VIPPS |
| Payroll | Salary deposits, freelance income |
| International | Transactions in JP, KR, BR, NL, and more |

## Usage

### Command Line

```bash
# Enrich the sample dataset
python main.py

# Use a custom CSV file
python main.py --input your_transactions.csv

# Output as JSON Lines
python main.py --format jsonl

# See all options
python main.py --help
```

### Python API

```python
import asyncio
from src import TriqaiClient, Transaction

async def main():
    client = TriqaiClient(api_key="your_api_key")
    
    result = await client.enrich(Transaction(
        title="AMAZON MKTPLACE PMTS AMZN.COM/BILL WA",
        country="US",
        type="expense",
    ))
    
    if result.success:
        print(f"Merchant: {result.data.enrichments.merchant.data.name}")
        print(f"Category: {result.data.transaction.get_primary_category_name()}")

asyncio.run(main())
```

## Input Format

Create a CSV with these columns:

```csv
country,type,title,comment
US,expense,"SQ *VERVE ROASTERS gosq.com CA",Coffee shop
GB,expense,"CARD PAYMENT - FALLOW LONDON",Restaurant
BR,expense,"PIX ENVIADO - JOAO SILVA",P2P transfer
```

| Column | Required | Description |
|--------|----------|-------------|
| country | Yes | ISO 3166-1 alpha-2 code (US, GB, BR) |
| type | Yes | `expense` or `income` |
| title | Yes | Raw transaction string |
| comment | No | Optional note |

## Output

Results are saved to `output/`:

- `enrichments_*.json` — Full enrichment data
- `summary_*.json` — Statistics and metrics

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `TRIQAI_API_KEY` | — | API key (required) |
| `MAX_CONCURRENT_REQUESTS` | 5 | Parallel requests |
| `REQUEST_DELAY` | 0.1 | Delay between requests (seconds) |

## Rate Limiting

The client automatically handles rate limits with exponential backoff. Monitor usage via response headers:

- `X-RateLimit-Limit` — Maximum requests allowed
- `X-RateLimit-Remaining` — Requests remaining
- `X-RateLimit-Reset` — Reset timestamp

## License

MIT License — see [LICENSE](LICENSE) for details.
