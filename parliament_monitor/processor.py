"""Claude API relevance scoring for parliamentary items."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import anthropic

from parliament_monitor.config import (
    ANTHROPIC_API_KEY,
    BATCH_SIZE,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL,
    SCORING_SYSTEM_PROMPT,
    ParliamentItem,
    ScoredItem,
)

logger = logging.getLogger(__name__)


def _parse_scoring_response(raw: str, items: list[ParliamentItem]) -> list[ScoredItem]:
    """Parse the JSON array returned by Claude and match to input items."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        scored_list: list[dict[str, Any]] = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse scoring response as JSON: %s\nRaw: %s", exc, raw[:500])
        return []

    results: list[ScoredItem] = []
    for entry in scored_list:
        idx = entry.get("index")
        if idx is None or not isinstance(idx, int) or idx >= len(items):
            logger.warning("Invalid index in scoring response: %r", idx)
            continue

        score = int(entry.get("relevance_score", 1))
        summary = str(entry.get("summary", ""))
        tags = [str(t) for t in (entry.get("topic_tags") or [])]
        urgency = str(entry.get("urgency", "low"))
        action = entry.get("action_needed")
        action_str = str(action) if action else None

        results.append(
            ScoredItem(
                item=items[idx],
                relevance_score=score,
                summary=summary,
                topic_tags=tags,
                urgency=urgency,
                action_needed=action_str,
            )
        )

    return results


async def _score_batch(
    batch: list[ParliamentItem],
    client: anthropic.AsyncAnthropic,
) -> list[ScoredItem]:
    """Send a batch of items to Claude for relevance scoring."""
    # Build the user message
    lines: list[str] = ["Score the following parliamentary items for relevance to the City of London Corporation:\n"]
    for i, item in enumerate(batch):
        lines.append(f"--- Item {i} ---")
        lines.append(item.to_scoring_text())
        lines.append("")

    user_message = "\n".join(lines)

    for attempt in range(1, 4):
        try:
            response = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=SCORING_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text
            return _parse_scoring_response(raw, batch)
        except anthropic.RateLimitError as exc:
            wait = 2**attempt * 5
            logger.warning("Claude rate limit hit (attempt %d), waiting %ds: %s", attempt, wait, exc)
            await asyncio.sleep(wait)
        except anthropic.APIError as exc:
            logger.error("Claude API error on attempt %d: %s", attempt, exc)
            if attempt == 3:
                return []
            await asyncio.sleep(2**attempt)

    return []


async def score_items(
    items: list[ParliamentItem],
    min_score: int = 3,
) -> list[ScoredItem]:
    """Score all items using Claude, returning those that meet *min_score*.

    Items are batched in groups of BATCH_SIZE and processed concurrently.
    """
    if not items:
        logger.info("Processor: no items to score")
        return []

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set – cannot score items")
        return []

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    batches: list[list[ParliamentItem]] = [
        items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)
    ]
    logger.info(
        "Processor: scoring %d items in %d batches (model=%s)",
        len(items),
        len(batches),
        CLAUDE_MODEL,
    )

    start = time.monotonic()

    # Process batches concurrently (max 3 at a time to respect rate limits)
    semaphore = asyncio.Semaphore(3)

    async def bounded_score(batch: list[ParliamentItem]) -> list[ScoredItem]:
        async with semaphore:
            return await _score_batch(batch, client)

    batch_results = await asyncio.gather(*[bounded_score(b) for b in batches])

    all_scored: list[ScoredItem] = []
    for batch_result in batch_results:
        all_scored.extend(batch_result)

    elapsed = time.monotonic() - start
    logger.info(
        "Processor: scored %d/%d items in %.1fs",
        len(all_scored),
        len(items),
        elapsed,
    )

    # Filter by minimum score
    filtered = [s for s in all_scored if s.relevance_score >= min_score]
    logger.info(
        "Processor: %d items meet minimum score %d",
        len(filtered),
        min_score,
    )

    # Sort by relevance descending, then urgency
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    filtered.sort(
        key=lambda s: (-s.relevance_score, urgency_order.get(s.urgency, 3))
    )

    return filtered
