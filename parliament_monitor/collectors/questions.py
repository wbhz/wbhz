"""Collector for Written Questions and Written Statements via Parliament Questions API."""

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

QUESTIONS_BASE = "https://questions-statements-api.parliament.uk/api"


async def _fetch_written_questions(
    date_str: str, client: httpx.AsyncClient
) -> list[dict]:
    """Fetch written questions tabled on *date_str*."""
    all_items: list[dict] = []
    skip = 0
    take = 50

    while True:
        params = {
            "tabledWhenFrom": date_str,
            "tabledWhenTo": date_str,
            "take": take,
            "skip": skip,
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(
                    f"{QUESTIONS_BASE}/writtenquestions/questions",
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("Questions attempt %d failed: %s", attempt, exc)
                if attempt == MAX_RETRIES:
                    return all_items
                await asyncio.sleep(2**attempt)

        results = data.get("results", [])
        all_items.extend(results)

        total = data.get("totalResults", 0)
        skip += take
        if skip >= total or not results:
            break
        await asyncio.sleep(REQUEST_DELAY)

    return all_items


async def _fetch_written_statements(
    date_str: str, client: httpx.AsyncClient
) -> list[dict]:
    """Fetch written statements made on *date_str*."""
    all_items: list[dict] = []
    skip = 0
    take = 50

    while True:
        params = {
            "madeWhenFrom": date_str,
            "madeWhenTo": date_str,
            "take": take,
            "skip": skip,
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(
                    f"{QUESTIONS_BASE}/writtenstatements/statements",
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("Statements attempt %d failed: %s", attempt, exc)
                if attempt == MAX_RETRIES:
                    return all_items
                await asyncio.sleep(2**attempt)

        results = data.get("results", [])
        all_items.extend(results)

        total = data.get("totalResults", 0)
        skip += take
        if skip >= total or not results:
            break
        await asyncio.sleep(REQUEST_DELAY)

    return all_items


async def collect(
    target_date: date, client: httpx.AsyncClient
) -> list[ParliamentItem]:
    """Fetch written questions and statements for *target_date*."""
    date_str = target_date.isoformat()
    logger.info("Questions: fetching for %s", date_str)

    raw_questions, raw_statements = await asyncio.gather(
        _fetch_written_questions(date_str, client),
        _fetch_written_statements(date_str, client),
    )

    logger.info(
        "Questions: %d questions, %d statements",
        len(raw_questions),
        len(raw_statements),
    )

    items: list[ParliamentItem] = []

    for result in raw_questions:
        q = result.get("value", result)
        q_id = q.get("id", "")
        uin = q.get("uin", "")
        question_text = q.get("questionText", "").strip()
        answer_text = (q.get("answerText") or "").strip()
        body_name = q.get("answeringBodyName", "")
        house = q.get("house", "Commons")
        date_tabled = (q.get("dateTabled") or date_str)[:10]

        if not question_text:
            continue

        # Compose a meaningful title
        title = question_text[:120]
        if len(question_text) > 120:
            title += "…"

        body_text = question_text
        if answer_text:
            body_text += f"\n\nAnswer: {answer_text[:400]}"

        items.append(
            ParliamentItem(
                id=f"question-{q_id or uin}",
                source="questions",
                title=f"[WQ] {title}",
                url=f"https://questions-statements.parliament.uk/written-questions/detail/{date_tabled}/{uin}",
                date=date_tabled,
                body_text=body_text[:800],
                extra={
                    "type": "written_question",
                    "uin": uin,
                    "house": house,
                    "answering_body": body_name,
                    "has_answer": bool(answer_text),
                },
            )
        )

    for result in raw_statements:
        s = result.get("value", result)
        s_id = s.get("id", "")
        uin = s.get("uin", "")
        title = (s.get("title") or "").strip()
        text = (s.get("text") or "").strip()
        body_name = s.get("answeringBodyName", "")
        house = s.get("house", "Commons")
        date_made = (s.get("dateMade") or date_str)[:10]

        if not title:
            continue

        items.append(
            ParliamentItem(
                id=f"statement-{s_id or uin}",
                source="questions",
                title=f"[WS] {title}",
                url=f"https://questions-statements.parliament.uk/written-statements/detail/{date_made}/{uin}",
                date=date_made,
                body_text=text[:800],
                extra={
                    "type": "written_statement",
                    "uin": uin,
                    "house": house,
                    "answering_body": body_name,
                },
            )
        )

    logger.info("Questions: collected %d items total", len(items))
    return items
