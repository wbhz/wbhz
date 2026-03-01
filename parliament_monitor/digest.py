"""Daily digest orchestrator – collects, scores, formats, and delivers."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

from parliament_monitor import collectors
from parliament_monitor.collectors import bills, govuk, hansard, legislation, questions
from parliament_monitor.config import (
    DAILY_DIR,
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    EMAIL_TO,
    OUTPUT_DIR,
    SENDGRID_API_KEY,
    ParliamentItem,
    ScoredItem,
)
from parliament_monitor.formatter import DigestStats, render_html_email, render_markdown
from parliament_monitor.processor import score_items

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------
def send_email(subject: str, html_body: str, text_body: str) -> bool:
    """Send the digest email via SendGrid. Returns True on success."""
    if not SENDGRID_API_KEY:
        logger.info("No SENDGRID_API_KEY – email not sent")
        return False
    if not EMAIL_TO:
        logger.warning("EMAIL_TO not configured – email not sent")
        return False

    try:
        import sendgrid
        from sendgrid.helpers.mail import Content, Email, Mail, To

        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        message = Mail(
            from_email=Email(EMAIL_FROM, EMAIL_FROM_NAME),
            to_emails=To(EMAIL_TO),
            subject=subject,
            plain_text_content=Content("text/plain", text_body),
            html_content=Content("text/html", html_body),
        )
        response = sg.client.mail.send.post(request_body=message.get())
        logger.info("Email sent – status %s", response.status_code)
        return response.status_code in (200, 202)
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------
def save_outputs(
    target_date: date,
    markdown: str,
    html: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Save markdown and HTML to disk. Returns (md_path, html_path)."""
    date_str = target_date.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"{date_str}-digest.md"
    html_path = output_dir / f"{date_str}-digest.html"

    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    logger.info("Saved digest: %s", md_path)
    logger.info("Saved HTML:   %s", html_path)
    return md_path, html_path


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
async def run_daily(
    target_date: date | None = None,
    send_email_flag: bool = True,
    output_dir: Path | None = None,
    min_score: int = 3,
) -> dict:
    """Run the daily digest pipeline.

    Returns a summary dict with counts and output paths.
    """
    if target_date is None:
        # Default to yesterday (last working day)
        target_date = date.today() - timedelta(days=1)

    if output_dir is None:
        output_dir = DAILY_DIR

    date_str = target_date.isoformat()
    logger.info("=== Daily digest for %s ===", date_str)
    pipeline_start = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Collect from all sources concurrently
    # ------------------------------------------------------------------
    async with httpx.AsyncClient(
        headers={"User-Agent": "ParliamentMonitor/1.0 (City of London Corporation)"},
        follow_redirects=True,
    ) as client:
        logger.info("Collecting from all sources…")
        collect_start = time.monotonic()

        results = await asyncio.gather(
            hansard.collect(target_date, client),
            bills.collect(target_date, client),
            questions.collect(target_date, client),
            legislation.collect(target_date, client),
            govuk.collect(target_date, client),
            return_exceptions=True,
        )

        collect_elapsed = time.monotonic() - collect_start

    source_names = ["hansard", "bills", "questions", "legislation", "govuk"]
    all_items: list[ParliamentItem] = []
    by_source_count: dict[str, int] = {}

    for name, result in zip(source_names, results):
        if isinstance(result, Exception):
            logger.error("Collector %s raised: %s", name, result)
            by_source_count[name] = 0
        else:
            by_source_count[name] = len(result)
            all_items.extend(result)
            logger.info("  %s: %d items", name, len(result))

    logger.info("Collection complete in %.1fs – %d total items", collect_elapsed, len(all_items))

    # ------------------------------------------------------------------
    # 2. Score with Claude
    # ------------------------------------------------------------------
    score_start = time.monotonic()
    scored_items: list[ScoredItem] = await score_items(all_items, min_score=min_score)
    score_elapsed = time.monotonic() - score_start

    # ------------------------------------------------------------------
    # 3. Build stats
    # ------------------------------------------------------------------
    stats = DigestStats(
        total_scanned=len(all_items),
        total_flagged=len(scored_items),
        score_5=sum(1 for s in scored_items if s.relevance_score == 5),
        score_4=sum(1 for s in scored_items if s.relevance_score == 4),
        score_3=sum(1 for s in scored_items if s.relevance_score == 3),
        by_source=by_source_count,
        sources_active=sum(1 for c in by_source_count.values() if c > 0),
        processing_time_s=time.monotonic() - pipeline_start,
    )

    logger.info(
        "Scoring complete in %.1fs – %d flagged (5=%d 4=%d 3=%d)",
        score_elapsed,
        stats.total_flagged,
        stats.score_5,
        stats.score_4,
        stats.score_3,
    )

    # ------------------------------------------------------------------
    # 4. Format
    # ------------------------------------------------------------------
    markdown = render_markdown(date_str, scored_items, stats)
    html = render_html_email(date_str, scored_items, stats)

    # ------------------------------------------------------------------
    # 5. Save to disk
    # ------------------------------------------------------------------
    md_path, html_path = save_outputs(target_date, markdown, html, output_dir)

    # ------------------------------------------------------------------
    # 6. Send email
    # ------------------------------------------------------------------
    email_sent = False
    if send_email_flag:
        from datetime import datetime
        try:
            date_obj = datetime.fromisoformat(date_str)
            date_display = date_obj.strftime("%A, %d %B %Y")
        except ValueError:
            date_display = date_str
        subject = f"Parliament Monitor – {date_display}"
        email_sent = send_email(subject, html, markdown)

    total_elapsed = time.monotonic() - pipeline_start
    logger.info("=== Daily digest complete in %.1fs ===", total_elapsed)

    return {
        "date": date_str,
        "total_scanned": stats.total_scanned,
        "total_flagged": stats.total_flagged,
        "score_5": stats.score_5,
        "score_4": stats.score_4,
        "score_3": stats.score_3,
        "by_source": by_source_count,
        "markdown_path": str(md_path),
        "html_path": str(html_path),
        "email_sent": email_sent,
        "elapsed_s": total_elapsed,
    }
