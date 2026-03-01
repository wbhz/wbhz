"""Configuration and taxonomy for Parliament Monitor."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "outputs"))
DAILY_DIR = OUTPUT_DIR / "daily"
WEEKLY_DIR = OUTPUT_DIR / "weekly"
TEMPLATES_DIR = Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
EMAIL_TO: str = os.getenv("EMAIL_TO", "")
EMAIL_FROM: str = os.getenv("EMAIL_FROM", "parliament-monitor@example.com")
EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "Parliament Monitor")

# ---------------------------------------------------------------------------
# Claude model
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
CLAUDE_MAX_TOKENS = 4096
BATCH_SIZE = 20  # items per Claude API call

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Request settings
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 30.0
REQUEST_DELAY = 0.5  # seconds between Parliament API requests
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Topic taxonomy
# ---------------------------------------------------------------------------

TAXONOMY = {
    "CORE": {
        "description": "Core City of London Corporation entities – auto-scored 5",
        "keywords": [
            "City of London Corporation",
            "Lord Mayor",
            "Court of Common Council",
            "Court of Aldermen",
            "Livery Companies",
            "City of London Police",
            "Guildhall",
            "Square Mile",
            "City Corporation",
        ],
        "score_hint": 5,
    },
    "FINANCIAL_SERVICES": {
        "description": "Financial services regulation and competitiveness",
        "keywords": [
            "FCA",
            "Financial Conduct Authority",
            "PRA",
            "Prudential Regulation Authority",
            "Bank of England",
            "Basel",
            "Solvency UK",
            "capital markets",
            "listings reform",
            "crypto",
            "digital assets",
            "insurance regulation",
            "financial services competitiveness",
            "wholesale markets",
            "clearing",
            "AML",
            "anti-money laundering",
            "economic crime",
            "sanctions",
            "fintech",
            "payment systems",
            "FSMA",
            "financial promotion",
        ],
        "score_hint": "4-5",
    },
    "TRADE_INVESTMENT": {
        "description": "Trade agreements and investment promotion",
        "keywords": [
            "free trade agreement",
            "FTA",
            "professional services",
            "UK-EU financial services",
            "mutual recognition",
            "investment promotion",
            "trade in services",
            "financial services trade",
            "CPTPP",
        ],
        "score_hint": "3-4",
    },
    "PLANNING_INFRASTRUCTURE": {
        "description": "City planning and infrastructure",
        "keywords": [
            "City planning",
            "tall buildings",
            "Thames",
            "Crossrail",
            "Elizabeth line",
            "City transport",
            "planning permission",
            "development",
            "regeneration",
        ],
        "score_hint": "3-4",
    },
    "LOCAL_GOVERNMENT": {
        "description": "Local government funding and reform",
        "keywords": [
            "business rates",
            "local authority funding",
            "devolution",
            "local government reform",
            "council tax",
            "non-domestic rates",
            "retained rates",
        ],
        "score_hint": "3-4",
    },
    "POLICING": {
        "description": "Policing, economic crime and cyber",
        "keywords": [
            "economic crime",
            "fraud",
            "City of London Police",
            "City Police",
            "cyber security",
            "cybercrime",
            "money laundering",
            "proceeds of crime",
        ],
        "score_hint": "3-4",
    },
    "EDUCATION_CULTURE": {
        "description": "Education, arts and culture",
        "keywords": [
            "City academies",
            "Guildhall School",
            "Barbican",
            "skills policy",
            "apprenticeships",
            "further education",
        ],
        "score_hint": "2-3",
    },
}

TAXONOMY_TEXT = """
## Relevance Taxonomy for City of London Corporation

**CORE (auto-score 5):** City of London Corporation, Lord Mayor, Court of Common Council,
Court of Aldermen, Livery Companies, City of London Police, Guildhall, Square Mile,
City Corporation.

**FINANCIAL SERVICES (4-5):** FCA, PRA, Bank of England regulation, Basel, Solvency UK,
capital markets, listings reform, crypto/digital assets, insurance regulation, financial
services competitiveness, wholesale markets, clearing, AML, economic crime, sanctions,
fintech, payment systems, FSMA.

**TRADE & INVESTMENT (3-4):** FTAs, professional services trade, investment promotion,
UK-EU financial services, mutual recognition, CPTPP.

**PLANNING & INFRASTRUCTURE (3-4):** City planning, tall buildings, Thames, Crossrail/
Elizabeth line, City transport.

**LOCAL GOVERNMENT (3-4):** Business rates, local authority funding, devolution, local
government reform, non-domestic rates.

**POLICING (3-4):** Economic crime, fraud, City Police funding, cyber security,
cybercrime, money laundering.

**EDUCATION & CULTURE (2-3):** City academies, Guildhall School, Barbican, skills policy.

Items scoring below 3 are not relevant to the City Corporation and should be scored 1 or 2.
"""

SCORING_SYSTEM_PROMPT = f"""You are a parliamentary monitoring assistant for the City of London Corporation,
one of the UK's oldest local authorities responsible for the Square Mile financial district.
Your role is to assess the relevance of UK Parliament and government activity to the
Corporation's interests and responsibilities.

{TAXONOMY_TEXT}

For each item you receive, output a JSON array where each element corresponds to one input
item (same order). Each element must be a JSON object with exactly these fields:

{{
  "index": <integer, 0-based position in input array>,
  "relevance_score": <integer 1-5>,
  "summary": "<2-3 sentence plain-English summary of why this item matters to the City Corporation>",
  "topic_tags": ["<tag1>", "<tag2>"],
  "urgency": "<'high' | 'medium' | 'low'>",
  "action_needed": "<brief description of any action the City Corporation should consider, or null>"
}}

Relevance score guidance:
- 5: Directly mentions or affects the City Corporation, Square Mile, or core interests
- 4: Strongly related to City priorities (financial services regulation, major economic policy)
- 3: Moderately relevant (local government, general business policy, policing)
- 2: Tangentially relevant
- 1: Not relevant

Urgency guidance:
- high: Decision/vote imminent (<2 weeks), emergency legislation, or direct impact
- medium: Bill in progress, consultation open, or policy under review
- low: Early stage, informational, or long-term development

Output ONLY the JSON array, no other text.
"""

# ---------------------------------------------------------------------------
# Gov.uk departments of interest
# ---------------------------------------------------------------------------
GOVUK_ORGANISATIONS = [
    "hm-treasury",
    "department-for-business-and-trade",
    "ministry-of-housing-communities-and-local-government",
    "home-office",
    "financial-conduct-authority",
    "prudential-regulation-authority",
]

# ---------------------------------------------------------------------------
# Pydantic models for collected items
# ---------------------------------------------------------------------------


class ParliamentItem(BaseModel):
    """A single item collected from any parliamentary source."""

    id: str
    source: str  # 'hansard' | 'bills' | 'questions' | 'legislation' | 'govuk'
    title: str
    url: str
    date: str  # ISO date string YYYY-MM-DD
    body_text: str = ""  # truncated text for scoring
    extra: dict = Field(default_factory=dict)  # source-specific metadata

    def to_scoring_text(self) -> str:
        """Compact representation sent to Claude."""
        parts = [f"Title: {self.title}", f"Source: {self.source}"]
        if self.extra.get("house"):
            parts.append(f"House: {self.extra['house']}")
        if self.extra.get("minister") or self.extra.get("answering_body"):
            parts.append(
                f"Minister/Body: {self.extra.get('minister') or self.extra.get('answering_body')}"
            )
        if self.body_text:
            # Limit to ~500 chars to keep prompt manageable
            snippet = self.body_text[:500].replace("\n", " ").strip()
            if len(self.body_text) > 500:
                snippet += "…"
            parts.append(f"Text: {snippet}")
        return "\n".join(parts)


class ScoredItem(BaseModel):
    """A ParliamentItem enriched with Claude's relevance assessment."""

    item: ParliamentItem
    relevance_score: int
    summary: str
    topic_tags: list[str]
    urgency: str
    action_needed: str | None
