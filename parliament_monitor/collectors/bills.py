"""Collector for UK Parliament Bills via the Bills API."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import httpx

from parliament_monitor.config import (
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    ParliamentItem,
)

logger = logging.getLogger(__name__)

BILLS_API_URL = "https://bills-api.parliament.uk/api/v1/Bills"
BILLS_WEB_URL = "https://bills.parliament.uk/bills"


async def collect(
    target_date: date, client: httpx.AsyncClient
) -> list[ParliamentItem]:
    """Fetch bills updated on or around *target_date*."""
    date_str = target_date.isoformat()
    logger.info("Bills: fetching bills updated around %s", date_str)

    items: list[ParliamentItem] = []

    params = {
        "SortBy": "DateUpdatedDesc",
        "Take": 50,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(
                BILLS_API_URL, params=params, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("Bills attempt %d failed: %s", attempt, exc)
            if attempt == MAX_RETRIES:
                logger.error("Bills: all retries exhausted")
                return []
            await asyncio.sleep(2**attempt)

    raw_bills = data.get("items", [])
    logger.info("Bills: received %d bills from API", len(raw_bills))

    # Filter to bills updated on target_date
    for bill in raw_bills:
        last_update = bill.get("lastUpdate", "")[:10]
        if last_update != date_str:
            continue

        bill_id = bill.get("billId", "")
        title = bill.get("shortTitle", "").strip()
        if not title:
            continue

        current_stage = bill.get("currentStage", {}) or {}
        stage_desc = current_stage.get("description", "")
        house = current_stage.get("house", bill.get("currentHouse", ""))
        is_act = bill.get("isAct", False)
        is_defeated = bill.get("isDefeated", False)

        # Find next sitting date if available
        stage_sittings = current_stage.get("stageSittings", []) or []
        next_sitting = None
        for sitting in stage_sittings:
            sitting_date = (sitting.get("date") or "")[:10]
            if sitting_date >= date_str:
                next_sitting = sitting_date
                break

        status_parts = []
        if is_act:
            status_parts.append("Act of Parliament")
        elif is_defeated:
            status_parts.append("Defeated")
        if stage_desc:
            status_parts.append(stage_desc)
        if house:
            status_parts.append(f"({house})")
        status = " – ".join(status_parts)

        body = f"Current stage: {status}"
        if next_sitting:
            body += f"\nNext sitting: {next_sitting}"

        items.append(
            ParliamentItem(
                id=f"bill-{bill_id}",
                source="bills",
                title=title,
                url=f"{BILLS_WEB_URL}/{bill_id}",
                date=last_update,
                body_text=body,
                extra={
                    "bill_id": bill_id,
                    "stage": stage_desc,
                    "house": house,
                    "is_act": is_act,
                    "is_defeated": is_defeated,
                    "next_sitting": next_sitting,
                    "originating_house": bill.get("originatingHouse", ""),
                },
            )
        )

    logger.info("Bills: %d bills updated on %s", len(items), date_str)
    return items
