"""Weekly synthesis briefing – reads the week's daily digests and produces a summary."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path

import anthropic

from parliament_monitor.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL,
    DAILY_DIR,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    EMAIL_TO,
    SENDGRID_API_KEY,
    WEEKLY_DIR,
)
from parliament_monitor.digest import send_email
from parliament_monitor.formatter import render_weekly_html

logger = logging.getLogger(__name__)

WEEKLY_SYNTHESIS_PROMPT = """You are a senior parliamentary monitoring analyst for the City of London Corporation.

You have received the daily parliamentary monitoring digests for this week. Your task is to produce a concise, high-quality weekly briefing (maximum 2 pages / ~600 words) covering:

## 1. Top Developments This Week
Summarise the 3-5 most significant parliamentary developments affecting the City Corporation's interests. Be specific about bills, debates, or policy announcements.

## 2. Bill Tracker
List the key bills in progress that affect City interests. For each: current stage, expected next step, and significance to the City Corporation.

## 3. Coming Next Week
Based on parliamentary schedules mentioned in this week's digests, flag what to watch for in the coming week.

## 4. Recommended Actions
Up to 5 specific, actionable recommendations for City Corporation policy officers (e.g., "Submit evidence to X committee by Y date", "Brief Lord Mayor on Z ahead of Q debate").

Keep language professional, factual and concise. Do not include waffle or filler phrases.
"""


async def _synthesise(weekly_content: str) -> str:
    """Call Claude to synthesise the weekly content."""
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set – cannot synthesise")
        return "Error: ANTHROPIC_API_KEY not configured."

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    user_message = (
        "Here are this week's daily parliamentary monitoring digests for the "
        "City of London Corporation:\n\n"
        + weekly_content
        + "\n\nPlease produce the weekly synthesis briefing."
    )

    for attempt in range(1, 4):
        try:
            import asyncio
            response = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=WEEKLY_SYNTHESIS_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except anthropic.RateLimitError as exc:
            wait = 2**attempt * 5
            logger.warning("Rate limit hit (attempt %d), waiting %ds: %s", attempt, wait, exc)
            import asyncio
            await asyncio.sleep(wait)
        except anthropic.APIError as exc:
            logger.error("Claude API error (attempt %d): %s", attempt, exc)
            if attempt == 3:
                return f"Error generating synthesis: {exc}"
            import asyncio
            await asyncio.sleep(2**attempt)

    return "Error: Failed to generate synthesis after retries."


def _collect_week_digests(week_ending: date, daily_dir: Path) -> str:
    """Read the markdown digests for Mon–Fri of the week ending *week_ending*."""
    # week_ending is a Friday
    monday = week_ending - timedelta(days=4)
    parts: list[str] = []

    for offset in range(5):  # Monday to Friday
        day = monday + timedelta(days=offset)
        md_path = daily_dir / f"{day.isoformat()}-digest.md"
        if md_path.exists():
            content = md_path.read_text(encoding="utf-8")
            parts.append(f"=== {day.strftime('%A %d %B')} ===\n{content}")
            logger.info("Weekly: loaded digest for %s (%d chars)", day, len(content))
        else:
            logger.warning("Weekly: no digest found for %s (%s)", day, md_path)

    if not parts:
        return "No daily digests found for this week."

    return "\n\n".join(parts)


async def run_weekly(
    week_ending: date | None = None,
    send_email_flag: bool = True,
    daily_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict:
    """Run the weekly synthesis pipeline.

    *week_ending* should be a Friday (defaults to the most recent Friday).
    """
    if week_ending is None:
        today = date.today()
        # Find the most recent Friday
        days_since_friday = (today.weekday() - 4) % 7
        week_ending = today - timedelta(days=days_since_friday)

    if daily_dir is None:
        daily_dir = DAILY_DIR
    if output_dir is None:
        output_dir = WEEKLY_DIR

    week_ending_str = week_ending.isoformat()
    logger.info("=== Weekly synthesis for week ending %s ===", week_ending_str)
    start = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Collect daily digests
    # ------------------------------------------------------------------
    weekly_content = _collect_week_digests(week_ending, daily_dir)

    # Truncate to avoid token limits (~100k chars ≈ 25k tokens)
    if len(weekly_content) > 90_000:
        weekly_content = weekly_content[:90_000] + "\n\n[Content truncated for length]"

    # ------------------------------------------------------------------
    # 2. Synthesise with Claude
    # ------------------------------------------------------------------
    import asyncio
    synthesis = await _synthesise(weekly_content)

    # ------------------------------------------------------------------
    # 3. Format and save
    # ------------------------------------------------------------------
    html = render_weekly_html(week_ending_str, synthesis)

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{week_ending_str}-weekly.md"
    html_path = output_dir / f"{week_ending_str}-weekly.html"

    md_path.write_text(synthesis, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    logger.info("Saved weekly synthesis: %s", md_path)

    # ------------------------------------------------------------------
    # 4. Send email
    # ------------------------------------------------------------------
    email_sent = False
    if send_email_flag:
        from datetime import datetime
        try:
            date_obj = datetime.fromisoformat(week_ending_str)
            display = date_obj.strftime("%d %B %Y")
        except ValueError:
            display = week_ending_str
        subject = f"Parliament Monitor – Weekly Briefing w/e {display}"
        email_sent = send_email(subject, html, synthesis)

    elapsed = time.monotonic() - start
    logger.info("=== Weekly synthesis complete in %.1fs ===", elapsed)

    return {
        "week_ending": week_ending_str,
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "email_sent": email_sent,
        "elapsed_s": elapsed,
    }
