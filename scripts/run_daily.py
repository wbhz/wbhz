"""CLI script: run the daily parliament digest.

Usage:
    python scripts/run_daily.py [--date YYYY-MM-DD] [--no-email] [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Parliament Monitor daily digest pipeline."
    )
    parser.add_argument(
        "--date",
        help="Target date in YYYY-MM-DD format (default: yesterday)",
        default=None,
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending the email even if SENDGRID_API_KEY is set",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save output files (default: outputs/daily)",
        default=None,
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=3,
        help="Minimum relevance score to include in digest (default: 3)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    _configure_logging(args.log_level)

    target_date: date | None = None
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"Error: invalid date '{args.date}'. Use YYYY-MM-DD format.", file=sys.stderr)
            sys.exit(1)

    output_dir: Path | None = None
    if args.output_dir:
        output_dir = Path(args.output_dir)

    from parliament_monitor.digest import run_daily

    result = asyncio.run(
        run_daily(
            target_date=target_date,
            send_email_flag=not args.no_email,
            output_dir=output_dir,
            min_score=args.min_score,
        )
    )

    # Print summary
    print("\n" + "=" * 60)
    print(f"Daily Digest Summary – {result['date']}")
    print("=" * 60)
    print(f"  Items scanned: {result['total_scanned']}")
    print(f"  Items flagged: {result['total_flagged']}")
    print(f"    Score 5 (High):    {result['score_5']}")
    print(f"    Score 4 (Notable): {result['score_4']}")
    print(f"    Score 3 (Worth noting): {result['score_3']}")
    print(f"  By source:")
    for source, count in result['by_source'].items():
        print(f"    {source}: {count}")
    print(f"  Markdown: {result['markdown_path']}")
    print(f"  HTML:     {result['html_path']}")
    print(f"  Email sent: {result['email_sent']}")
    print(f"  Elapsed: {result['elapsed_s']:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
