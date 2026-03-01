"""Collector for Hansard debates and written statements via the Hansard API."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import httpx

from parliament_monitor.config import (
    MAX_RETRIES,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    ParliamentItem,
)

logger = logging.getLogger(__name__)

HANSARD_SEARCH_URL = "https://hansard-api.parliament.uk/search.json"
DEBATE_BASE_URL = "https://hansard.parliament.uk"


def _debate_url(ext_id: str, house: str, sitting_date: str) -> str:
    """Construct a URL to the Hansard debate section."""
    date_slug = sitting_date[:10].replace("-", "/")
    house_slug = house.lower() if house.lower() in ("commons", "lords") else "commons"
    return f"{DEBATE_BASE_URL}/{house_slug}/{date_slug}/debates/{ext_id}"


async def collect(
    target_date: date, client: httpx.AsyncClient
) -> list[ParliamentItem]:
    """Fetch Hansard debates and written statements for *target_date*."""
    date_str = target_date.isoformat()
    logger.info("Hansard: fetching for %s", date_str)

    items: list[ParliamentItem] = []

    # The search API returns Debates and WrittenStatements for a specific date
    params = {
        "startDate": date_str,
        "endDate": date_str,
        "take": 50,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(
                HANSARD_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Hansard attempt %d failed: %s", attempt, exc)
            if attempt == MAX_RETRIES:
                logger.error("Hansard: all retries exhausted")
                return []
            await asyncio.sleep(2**attempt)

    debates = data.get("Debates", [])
    written_statements = data.get("WrittenStatements", [])

    logger.info(
        "Hansard: %d debates, %d written statements", len(debates), len(written_statements)
    )

    for debate in debates:
        ext_id = debate.get("DebateSectionExtId", "")
        house = debate.get("House", "Commons")
        sitting = debate.get("SittingDate", "")[:10]
        title = debate.get("Title", "").strip()
        section = debate.get("DebateSection", "")

        if not title:
            continue

        url = _debate_url(ext_id, house, sitting or date_str)

        items.append(
            ParliamentItem(
                id=f"hansard-debate-{ext_id}",
                source="hansard",
                title=title,
                url=url,
                date=sitting or date_str,
                extra={
                    "type": "debate",
                    "house": house,
                    "section": section,
                    "ext_id": ext_id,
                },
            )
        )
        await asyncio.sleep(REQUEST_DELAY)

    for stmt in written_statements:
        # The Hansard search API returns WrittenStatements as debate contributions
        # Fields: MemberName, AttributedTo, ItemId, ContributionExtId, ContributionText
        ext_id = stmt.get("ContributionExtId", stmt.get("ItemId", ""))
        house = stmt.get("House", "Commons")
        minister = stmt.get("AttributedTo", stmt.get("MemberName", ""))
        text = stmt.get("ContributionTextFull", stmt.get("ContributionText", ""))
        stmt_date = stmt.get("SittingDate", date_str)[:10]

        # Construct title from minister name + first line of text
        snippet = text[:80].replace("\r\n", " ").replace("\n", " ").strip()
        if snippet:
            title = f"Written Statement – {minister}: {snippet}…"
        elif minister:
            title = f"Written Statement – {minister}"
        else:
            continue

        url = f"{DEBATE_BASE_URL}/{'lords' if 'lord' in house.lower() else 'commons'}/{stmt_date.replace('-', '/')}/statements/{ext_id}" if ext_id else DEBATE_BASE_URL

        items.append(
            ParliamentItem(
                id=f"hansard-stmt-{ext_id or hash(title)}",
                source="hansard",
                title=f"[Written Statement] {title[:150]}",
                url=url,
                date=stmt_date or date_str,
                body_text=text[:1000],
                extra={
                    "type": "written_statement",
                    "house": house,
                    "minister": minister,
                },
            )
        )

    logger.info("Hansard: collected %d items total", len(items))
    return items
