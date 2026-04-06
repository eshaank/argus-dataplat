"""CLI entry point: python -m dataplat.cli.backfill_economy

Backfills economic indicators from FRED into ClickHouse.

Examples:
    uv run python -m dataplat.cli.backfill_economy                     # All 8 tables
    uv run python -m dataplat.cli.backfill_economy --table rates       # Single table
    uv run python -m dataplat.cli.backfill_economy --table rates --table macro_daily
    uv run python -m dataplat.cli.backfill_economy --list              # Show available tables
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill economic indicators from FRED",
    )
    parser.add_argument(
        "--table",
        action="append",
        metavar="NAME",
        help="Table to backfill (repeatable). Omit for all tables.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available tables and their series, then exit.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list:
        from dataplat.ingestion.fred.registry import ALL_TABLES

        for config in ALL_TABLES:
            print(f"\n{config.table} (from {config.start}):")
            for fred_id, col in config.series.items():
                print(f"  {fred_id:20s} → {col}")
        sys.exit(0)

    from dataplat.ingestion.fred.backfill import run_fred_backfill

    run_fred_backfill(tables=args.table)


if __name__ == "__main__":
    main()
