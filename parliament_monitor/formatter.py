"""Formats scored items as Markdown and HTML email."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from parliament_monitor.config import TEMPLATES_DIR, ScoredItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------
_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader([str(TEMPLATES_DIR), str(TEMPLATES_DIR / "partials")]),
            autoescape=select_autoescape(["html"]),
        )
    return _jinja_env


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------
@dataclass
class DigestStats:
    total_scanned: int = 0
    total_flagged: int = 0
    score_5: int = 0
    score_4: int = 0
    score_3: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    sources_active: int = 0
    processing_time_s: float = 0.0


# ---------------------------------------------------------------------------
# Markdown formatter
# ---------------------------------------------------------------------------
SECTION_HEADERS = {
    5: "## 🔴 High Relevance (Score 5)",
    4: "## 🟠 Notable (Score 4)",
    3: "## 🟡 Worth Noting (Score 3)",
}

SOURCE_LABELS = {
    "hansard": "Hansard",
    "bills": "Bills",
    "questions": "Questions/Statements",
    "legislation": "Legislation.gov.uk",
    "govuk": "Gov.uk",
}


def _item_to_markdown(si: ScoredItem) -> str:
    """Format a single ScoredItem as Markdown."""
    lines: list[str] = []
    source_label = SOURCE_LABELS.get(si.item.source, si.item.source.capitalize())
    urgency_emoji = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(si.urgency, "")
    tags_str = " · ".join(si.topic_tags) if si.topic_tags else ""

    lines.append(f"### [{si.item.title}]({si.item.url})")
    lines.append(
        f"**Source:** {source_label} | **Date:** {si.item.date} | "
        f"**Score:** {si.relevance_score}/5 | **Urgency:** {urgency_emoji} {si.urgency.title()}"
    )
    if si.item.extra.get("house"):
        lines.append(f"**House:** {si.item.extra['house']}")
    if si.item.extra.get("answering_body"):
        lines.append(f"**Department:** {si.item.extra['answering_body']}")
    if si.item.extra.get("org_str"):
        lines.append(f"**Organisation:** {si.item.extra['org_str']}")
    lines.append("")
    lines.append(si.summary)
    if tags_str:
        lines.append(f"\n*Topics: {tags_str}*")
    if si.action_needed:
        lines.append(f"\n> **Action suggested:** {si.action_needed}")
    lines.append("")
    return "\n".join(lines)


def render_markdown(
    date_str: str,
    scored_items: list[ScoredItem],
    stats: DigestStats,
) -> str:
    """Render the full daily digest as Markdown."""
    lines: list[str] = []

    lines.append(f"# Parliament Monitor — Daily Digest")
    lines.append(f"**City of London Corporation** | {date_str}")
    lines.append(
        f"\n*{stats.total_scanned} items scanned · {stats.total_flagged} flagged · "
        f"generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*"
    )
    lines.append("")

    by_score: dict[int, list[ScoredItem]] = {5: [], 4: [], 3: []}
    for si in scored_items:
        if si.relevance_score in by_score:
            by_score[si.relevance_score].append(si)

    for score in (5, 4, 3):
        lines.append(SECTION_HEADERS[score])
        lines.append("")
        if by_score[score]:
            for si in by_score[score]:
                lines.append(_item_to_markdown(si))
        else:
            lines.append("*No items at this level today.*\n")

    # Coming up (bills with upcoming sittings)
    bill_items = [
        si for si in scored_items
        if si.item.source == "bills" and si.item.extra.get("next_sitting")
    ]
    if bill_items:
        lines.append("## 📅 Coming Up — Bills Approaching Stages\n")
        for si in bill_items:
            next_sit = si.item.extra["next_sitting"]
            stage = si.item.extra.get("stage", "")
            house = si.item.extra.get("house", "")
            lines.append(
                f"- **[{si.item.title}]({si.item.url})** — "
                f"{stage} ({house}) — Next sitting: {next_sit}"
            )
        lines.append("")

    # Stats
    lines.append("## 📊 Statistics\n")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Items scanned | {stats.total_scanned} |")
    lines.append(f"| Items flagged (≥3) | {stats.total_flagged} |")
    lines.append(f"| Score 5 (High) | {stats.score_5} |")
    lines.append(f"| Score 4 (Notable) | {stats.score_4} |")
    lines.append(f"| Score 3 (Worth Noting) | {stats.score_3} |")
    for source, count in sorted(stats.by_source.items()):
        label = SOURCE_LABELS.get(source, source.capitalize())
        lines.append(f"| {label} | {count} |")
    if stats.processing_time_s:
        lines.append(f"| Processing time | {stats.processing_time_s:.0f}s |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML email formatter
# ---------------------------------------------------------------------------
def render_html_email(
    date_str: str,
    scored_items: list[ScoredItem],
    stats: DigestStats,
) -> str:
    """Render the daily digest as an HTML email via Jinja2."""
    env = _get_jinja_env()
    template = env.get_template("email_daily.html")

    by_score: dict[int, list[ScoredItem]] = {5: [], 4: [], 3: []}
    for si in scored_items:
        if si.relevance_score in by_score:
            by_score[si.relevance_score].append(si)

    coming_up = [
        si for si in scored_items
        if si.item.source == "bills" and si.item.extra.get("next_sitting")
    ]

    try:
        date_obj = datetime.fromisoformat(date_str)
        date_display = date_obj.strftime("%A, %d %B %Y")
    except ValueError:
        date_display = date_str

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"Parliament Monitor – {date_display}"

    return template.render(
        subject=subject,
        date_display=date_display,
        generated_at=generated_at,
        high_items=by_score[5],
        notable_items=by_score[4],
        worth_noting_items=by_score[3],
        coming_up_bills=coming_up,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Weekly HTML formatter
# ---------------------------------------------------------------------------
def render_weekly_html(
    week_ending: str,
    synthesis_text: str,
) -> str:
    """Render the weekly synthesis as an HTML email."""
    env = _get_jinja_env()
    template = env.get_template("email_weekly.html")

    try:
        date_obj = datetime.fromisoformat(week_ending)
        week_ending_display = date_obj.strftime("%d %B %Y")
    except ValueError:
        week_ending_display = week_ending

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"Parliament Monitor – Weekly Briefing w/e {week_ending_display}"

    return template.render(
        subject=subject,
        week_ending=week_ending_display,
        synthesis_text=synthesis_text,
        generated_at=generated_at,
    )
