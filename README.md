# Parliament Monitor

Automated UK Parliament monitoring for the City of London Corporation.

Every weekday at 07:00 UTC, this pipeline:
1. Pulls the previous day's activity from five parliamentary data sources
2. Sends all items to Claude (Sonnet) for relevance scoring against a City Corporation topic taxonomy
3. Filters to items scoring ≥3/5 relevance
4. Generates a formatted digest as both Markdown and HTML email
5. Sends via SendGrid (or saves locally if no key is set)

On Fridays at 16:00 UTC, it also produces a weekly synthesis briefing.

---

## Architecture

```
parliament_monitor/
├── collectors/
│   ├── hansard.py      # Hansard debates + written statements
│   ├── bills.py        # UK Parliament Bills
│   ├── questions.py    # Written questions + ministerial statements
│   ├── legislation.py  # New legislation (legislation.gov.uk Atom feed)
│   └── govuk.py        # Gov.uk publications (HMT, DBT, MHCLG, Home Office, FCA, PRA)
├── processor.py        # Claude API relevance scoring (batched, concurrent)
├── formatter.py        # Markdown + Jinja2 HTML email rendering
├── digest.py           # Daily orchestrator
├── weekly.py           # Weekly synthesis
├── config.py           # All settings + taxonomy + Pydantic models
└── templates/
    ├── email_daily.html
    ├── email_weekly.html
    └── partials/
        └── item_card.html

scripts/
├── run_daily.py        # CLI entrypoint
└── run_weekly.py       # CLI entrypoint

.github/workflows/
├── daily_digest.yml    # Cron: 07:00 UTC Mon–Fri
└── weekly_synthesis.yml # Cron: 16:00 UTC Fridays

outputs/
├── daily/              # YYYY-MM-DD-digest.{md,html} (committed to repo)
└── weekly/             # YYYY-MM-DD-weekly.{md,html} (committed to repo)
```

---

## Data Sources

| Source | Endpoint | Rate limit notes |
|--------|----------|-----------------|
| **Hansard** | `hansard-api.parliament.uk/search.json` | 0.5s delay between requests |
| **Bills** | `bills-api.parliament.uk/api/v1/Bills` | No auth required |
| **Questions** | `questions-statements-api.parliament.uk/api/...` | Paginated, 0.5s delay |
| **Legislation** | `legislation.gov.uk/new/data.feed` (Atom XML) | No auth required |
| **Gov.uk** | `gov.uk/api/search.json` | Filtered by org slug |

All sources are free and require no authentication.

---

## Topic Taxonomy

The City of London Corporation relevance taxonomy has seven categories:

| Category | Score Hint | Key Terms |
|----------|-----------|-----------|
| **CORE** | 5 (auto) | City of London Corporation, Lord Mayor, Court of Common Council, Guildhall, Square Mile |
| **FINANCIAL_SERVICES** | 4–5 | FCA, PRA, Bank of England, capital markets, listings reform, crypto, Solvency UK, AML |
| **TRADE_INVESTMENT** | 3–4 | FTAs, professional services, UK-EU financial services, mutual recognition, CPTPP |
| **PLANNING_INFRASTRUCTURE** | 3–4 | City planning, tall buildings, Thames, Crossrail, Elizabeth line |
| **LOCAL_GOVERNMENT** | 3–4 | Business rates, devolution, local government reform |
| **POLICING** | 3–4 | Economic crime, fraud, City Police, cyber security |
| **EDUCATION_CULTURE** | 2–3 | City academies, Guildhall School, Barbican, skills policy |

Claude is asked to output for each item:
```json
{
  "index": 0,
  "relevance_score": 4,
  "summary": "2-3 sentence plain-English summary",
  "topic_tags": ["FINANCIAL_SERVICES", "CAPITAL_MARKETS"],
  "urgency": "high|medium|low",
  "action_needed": "Brief description or null"
}
```

Items are batched in groups of 20 and scored concurrently (max 3 concurrent API calls).

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Anthropic API key (required for scoring)
- SendGrid API key (optional, for email delivery)

### Installation

```bash
git clone https://github.com/your-org/parliament-monitor
cd parliament-monitor

# With uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional: email delivery via SendGrid
SENDGRID_API_KEY=SG....
EMAIL_TO=
EMAIL_FROM=
EMAIL_FROM_NAME=Parliament Monitor

# Optional
OUTPUT_DIR=outputs
LOG_LEVEL=INFO
```

---

## Usage

### Run the daily digest

```bash
# Yesterday's digest (default)
python scripts/run_daily.py

# Specific date
python scripts/run_daily.py --date 2025-01-27

# Skip email (save locally only)
python scripts/run_daily.py --no-email

# Custom output directory
python scripts/run_daily.py --output-dir /path/to/outputs

# Adjust minimum score threshold (default: 3)
python scripts/run_daily.py --min-score 4

# Debug logging
python scripts/run_daily.py --log-level DEBUG
```

### Run the weekly synthesis

```bash
# Most recent Friday (default)
python scripts/run_weekly.py

# Specific week ending (must be a Friday)
python scripts/run_weekly.py --week-ending 2025-02-07

# Skip email
python scripts/run_weekly.py --no-email
```

### Output files

All outputs are saved under `outputs/`:

```
outputs/
├── daily/
│   ├── 2025-01-27-digest.md    # Markdown digest
│   └── 2025-01-27-digest.html  # HTML email (can open in browser)
└── weekly/
    ├── 2025-01-31-weekly.md    # Weekly synthesis text
    └── 2025-01-31-weekly.html  # Weekly HTML email
```

---

## GitHub Actions

### Secrets required

Set these in your repository's **Settings → Secrets and variables → Actions**:

| Secret | Required | Description |
|--------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for relevance scoring |
| `SENDGRID_API_KEY` | Optional | SendGrid API key for email delivery |
| `EMAIL_TO` | Optional | Recipient email address |
| `EMAIL_FROM` | Optional | Sender email address |
| `EMAIL_FROM_NAME` | Optional | Sender display name |

### Workflows

**`daily_digest.yml`** – Runs Monday–Friday at 07:00 UTC:
- Collects yesterday's parliamentary activity
- Scores items with Claude
- Generates and optionally sends the digest
- Commits output files to the repository

**`weekly_synthesis.yml`** – Runs Fridays at 16:00 UTC:
- Reads this week's daily digest files
- Generates a synthesised weekly briefing via Claude
- Commits output files to the repository

### Manual trigger

Both workflows support `workflow_dispatch` for manual testing:

```
GitHub → Actions → Parliament Monitor – Daily Digest → Run workflow
```

You can specify a custom date, skip email, and optionally trigger the weekly synthesis.

---

## Calibration

### Adjusting the relevance threshold

By default, items scoring ≥3 are included. To reduce noise:

```bash
python scripts/run_daily.py --min-score 4
```

For the GitHub Actions workflow, edit `daily_digest.yml`:
```yaml
run: python scripts/run_daily.py --min-score 4
```

### Adding keywords to the taxonomy

Edit `parliament_monitor/config.py` — the `TAXONOMY` dict and `TAXONOMY_TEXT` string control what Claude looks for. Add keywords to the relevant category's `keywords` list and update the `TAXONOMY_TEXT` string.

### Adding new Gov.uk departments

Edit `GOVUK_ORGANISATIONS` in `config.py`. Organisation slugs are found at `gov.uk/government/organisations`:

```python
GOVUK_ORGANISATIONS = [
    "hm-treasury",
    "department-for-business-and-trade",
    # Add slug here
]
```

### Tweaking the scoring prompt

`SCORING_SYSTEM_PROMPT` in `config.py` is the system prompt sent to Claude. Adjust urgency definitions, score descriptions, or request additional output fields here.

---

## Output Format

### Daily digest structure

```
Stats bar (items scanned, flagged, sources, processing time)

🔴 High Relevance (Score 5) – items directly affecting City Corporation
🟠 Notable (Score 4) – strongly related to City priorities
🟡 Worth Noting (Score 3) – moderately relevant

📅 Coming Up – bills with upcoming stage sittings
📊 Statistics table
```

Each item card includes:
- Relevance score badge (colour-coded)
- Title linked to source URL
- Source, date, house, department, urgency
- 2–3 sentence Claude summary
- Topic tags
- Suggested action (if any)

### HTML email

The HTML email is designed to work in Gmail, Outlook, and Apple Mail:
- Brand colours: `#C8102E` (City red) and `#002F5F` (City navy)
- Responsive up to 680px width
- Inline styles for maximum email client compatibility
- Score badges colour-coded (red/orange/amber)

---

## Technical Details

### Retry logic

All HTTP collectors use exponential backoff (2s, 4s, 8s) with up to 3 retries. A 0.5s delay is added between sequential Parliament API requests.

### Concurrency model

- All five collectors run concurrently via `asyncio.gather()`
- Claude API calls are batched (20 items per batch) with a semaphore limiting to 3 concurrent batches
- Rate limit errors trigger automatic backoff and retry

### Pydantic models

- `ParliamentItem` — a collected item from any source
- `ScoredItem` — a `ParliamentItem` enriched with Claude's assessment

### Output committed to repo

The GitHub Actions workflow commits `outputs/` after each run. This creates a versioned archive of all digests — the git history becomes a complete record of parliamentary activity as seen through the City Corporation lens.

---

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

Set the key in `.env` or as an environment variable.

### "No items flagged" even though Parliament was busy

Run with `--log-level DEBUG`. Check:
1. The date being used (items collected for *yesterday* by default)
2. Whether Parliament was in recess on that day
3. The `--min-score` threshold (default 3)

### Hansard returns 0 debates

Parliament recess dates return 0 debates. The search API only returns items for sitting days.

### Gov.uk returns 0 items

The specified organisations may have had no publications that day. This is normal. Expand `GOVUK_ORGANISATIONS` in `config.py` to monitor more departments.

### Weekly synthesis: "No daily digests found"

The synthesis reads Markdown files from `outputs/daily/`. Run the daily digest for each weekday of that week first, or specify `--daily-dir`.

### Email not sending

1. Verify `SENDGRID_API_KEY`, `EMAIL_TO`, `EMAIL_FROM` are all set
2. Ensure the FROM address is verified in your SendGrid account
3. Run with `--log-level DEBUG` for full SendGrid response

---

## Licence

MIT
