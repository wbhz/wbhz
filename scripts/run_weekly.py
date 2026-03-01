"""CLI script: run the weekly parliament synthesis briefing.

Usage:
    python scripts/run_weekly.py [--week-ending YYYY-MM-DD] [--no-email] [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import asyncio
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
        description="Run the Parliament Monitor weekly synthesis briefing."
    )
    parser.add_argument(
        "--week-ending",
        help="Friday date for week-ending in YYYY-MM-DD format (default: most recent Friday)",
        default=None,
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending the email even if SENDGRID_API_KEY is set",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save output files (default: outputs/weekly)",
        default=None,
    )
    parser.add_argument(
        "--daily-dir",
        help="Directory containing daily digest files (default: outputs/daily)",
        default=None,
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    _configure_logging(args.log_level)

    week_ending: date | None = None
    if args.week_ending:
        try:
            week_ending = date.fromisoformat(args.week_ending)
        except ValueError:
            print(
                f"Error: invalid date '{args.week_ending}'. Use YYYY-MM-DD format.",
                file=sys.stderr,
            )
            sys.exit(1)

    output_dir: Path | None = Path(args.output_dir) if args.output_dir else None
    daily_dir: Path | None = Path(args.daily_dir) if args.daily_dir else None

    from parliament_monitor.weekly import run_weekly

    result = asyncio.run(
        run_weekly(
            week_ending=week_ending,
            send_email_flag=not args.no_email,
            daily_dir=daily_dir,
            output_dir=output_dir,
        )
    )

    print("\n" + "=" * 60)
    print(f"Weekly Synthesis Summary – w/e {result['week_ending']}")
    print("=" * 60)
    print(f"  Markdown: {result['markdown_path']}")
    print(f"  HTML:     {result['html_path']}")
    print(f"  Email sent: {result['email_sent']}")
    print(f"  Elapsed: {result['elapsed_s']:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
