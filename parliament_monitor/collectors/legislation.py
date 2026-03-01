"""Collector for new UK legislation via legislation.gov.uk Atom feed."""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from parliament_monitor.config import (
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    ParliamentItem,
)

logger = logging.getLogger(__name__)

LEGISLATION_FEED_URL = "https://www.legislation.gov.uk/new/data.feed"

# XML namespaces used by legislation.gov.uk Atom feed
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "leg": "http://www.legislation.gov.uk/namespaces/legislation",
    "ukm": "http://www.legislation.gov.uk/namespaces/metadata",
    "theme": "http://www.legislation.gov.uk/namespaces/theme",
}

# Legislation type labels
TYPE_LABELS = {
    "ukpga": "UK Public General Act",
    "uksi": "UK Statutory Instrument",
    "ukla": "UK Local Act",
    "ukppa": "UK Private & Personal Act",
    "asp": "Act of the Scottish Parliament",
    "anaw": "Act of the National Assembly for Wales",
    "asc": "Act of Senedd Cymru",
    "wsi": "Wales Statutory Instrument",
    "ssi": "Scottish Statutory Instrument",
    "nia": "Northern Ireland Act",
    "nisr": "Northern Ireland Statutory Rule",
}


def _extract_leg_type(url: str) -> str:
    """Infer legislation type from the URL path segment."""
    for key in TYPE_LABELS:
        if f"/{key}/" in url:
            return TYPE_LABELS[key]
    return "Legislation"


async def collect(
    target_date: date, client: httpx.AsyncClient
) -> list[ParliamentItem]:
    """Fetch new legislation published on or around *target_date*."""
    date_str = target_date.isoformat()
    logger.info("Legislation: fetching feed for %s", date_str)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(
                LEGISLATION_FEED_URL, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            content = resp.text
            break
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Legislation attempt %d failed: %s", attempt, exc)
            if attempt == MAX_RETRIES:
                logger.error("Legislation: all retries exhausted")
                return []
            await asyncio.sleep(2**attempt)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        logger.error("Legislation: XML parse error: %s", exc)
        return []

    entries = root.findall("atom:entry", NS)
    logger.info("Legislation: %d entries in feed", len(entries))

    items: list[ParliamentItem] = []

    for entry in entries:
        title_el = entry.find("atom:title", NS)
        title = (title_el.text or "").strip() if title_el is not None else ""

        link_el = entry.find("atom:link", NS)
        href = link_el.get("href", "") if link_el is not None else ""
        # Normalise to https
        href = href.replace("http://www.legislation.gov.uk", "https://www.legislation.gov.uk")

        updated_el = entry.find("atom:updated", NS)
        updated = (updated_el.text or "")[:10] if updated_el is not None else ""

        summary_el = entry.find("atom:summary", NS)
        summary = (summary_el.text or "").strip() if summary_el is not None else ""

        # Only include items updated on target_date
        if updated != date_str:
            continue

        if not title:
            # Use the URL slug as fallback
            title = href.split("/")[-1] if href else "Unknown legislation"

        leg_type = _extract_leg_type(href)

        items.append(
            ParliamentItem(
                id=f"legislation-{href.split('/')[-1] if href else hash(title)}",
                source="legislation",
                title=f"[{leg_type}] {title}",
                url=href,
                date=updated or date_str,
                body_text=summary[:500],
                extra={
                    "leg_type": leg_type,
                    "url": href,
                },
            )
        )

    logger.info("Legislation: %d items on %s", len(items), date_str)
    return items
