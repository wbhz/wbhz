"""Collector for Gov.uk publications from key departments."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from datetime import date

import httpx

from parliament_monitor.config import (
    GOVUK_ORGANISATIONS,
    MAX_RETRIES,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    ParliamentItem,
)

logger = logging.getLogger(__name__)

GOVUK_SEARCH_URL = "https://www.gov.uk/api/search.json"
GOVUK_BASE_URL = "https://www.gov.uk"

# Content types to exclude (noisy, low-value)
REJECT_FORMATS = {
    "travel_advice",
    "smart-answer",
    "transaction",
    "gone",
    "redirect",
    "placeholder",
    "employment_tribunal_decision",
}


def _build_query_string(orgs: list[str]) -> str:
    """Build a query string for filtering by organisations.

    The gov.uk search API requires array parameters with [] brackets,
    which httpx doesn't encode correctly when passed as a dict, so we
    construct the query string manually.  The fields[] parameter causes
    422 errors so we omit it and filter fields in Python instead.
    """
    parts = []
    for org in orgs:
        parts.append("filter_organisations%5B%5D=" + urllib.parse.quote(org))
    parts.append("count=50")
    parts.append("order=-public_timestamp")
    return "&".join(parts)


async def collect(
    target_date: date, client: httpx.AsyncClient
) -> list[ParliamentItem]:
    """Fetch Gov.uk publications from tracked departments for *target_date*."""
    date_str = target_date.isoformat()
    logger.info("Govuk: fetching publications for %s", date_str)

    qs = _build_query_string(GOVUK_ORGANISATIONS)
    url = f"{GOVUK_SEARCH_URL}?{qs}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            break
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Govuk attempt %d failed: %s", attempt, exc)
            if attempt == MAX_RETRIES:
                logger.error("Govuk: all retries exhausted")
                return []
            await asyncio.sleep(2**attempt)

    raw_results = data.get("results", [])
    logger.info("Govuk: %d total results from API", len(raw_results))

    items: list[ParliamentItem] = []

    for result in raw_results:
        doc_format = result.get("document_type") or result.get("format", "")
        if doc_format in REJECT_FORMATS:
            continue

        pub_ts = (result.get("public_timestamp") or "")[:10]
        if pub_ts != date_str:
            continue

        title = (result.get("title") or "").strip()
        link = result.get("link", "")
        description = (result.get("description") or "").strip()

        if not title or not link:
            continue

        full_url = GOVUK_BASE_URL + link if link.startswith("/") else link

        org_names = [
            o.get("title", "")
            for o in (result.get("organisations") or [])
            if o.get("title")
        ]
        org_str = ", ".join(org_names)

        items.append(
            ParliamentItem(
                id=f"govuk-{link.strip('/').replace('/', '-')}",
                source="govuk",
                title=f"[Gov.uk] {title}",
                url=full_url,
                date=pub_ts,
                body_text=description[:600],
                extra={
                    "document_type": doc_format,
                    "organisations": org_names,
                    "org_str": org_str,
                },
            )
        )
        await asyncio.sleep(REQUEST_DELAY)

    logger.info("Govuk: %d items on %s", len(items), date_str)
    return items
