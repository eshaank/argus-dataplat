"""CLI entry point for the feature engineering pipeline.

Usage:
    # Backfill features for a date range
    uv run python -m dataplat.cli.compute_features --start 2023-01-01 --end 2024-12-31

    # Compute today only
    uv run python -m dataplat.cli.compute_features --today

    # Dry run (compute but don't write)
    uv run python -m dataplat.cli.compute_features --start 2024-01-01 --dry-run

    # List available feature modules
    uv run python -m dataplat.cli.compute_features --list
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime

from dataplat.algo.features.pipeline import FeaturePipeline
from dataplat.algo.features.registry import get_all_modules
from dataplat.db.client import get_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute daily algo features → ClickHouse")
    parser.add_argument("--start", type=parse_date, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=parse_date, help="End date (YYYY-MM-DD), default=today")
    parser.add_argument("--today", action="store_true", help="Compute features for today only")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't write to ClickHouse")
    parser.add_argument("--list", action="store_true", help="List registered feature modules and exit")
    args = parser.parse_args()

    client = get_client()

    if args.list:
        modules = get_all_modules(client)
        print(f"\n{len(modules)} registered feature modules:\n")
        for m in modules:
            print(f"  {m.name}")
            for feat in m.feature_names:
                print(f"    • {feat}")
            print()
        sys.exit(0)

    pipeline = FeaturePipeline(client)

    if args.today:
        today = date.today()
        logger.info("Computing features for today: %s", today)
        row = pipeline.run_single(today, dry_run=args.dry_run)
        if args.dry_run:
            print(f"\nFeatures for {today}:")
            for k, v in sorted(row.items()):
                if k not in ("date", "stale_features", "feature_count"):
                    print(f"  {k:30s} = {v}")
            print(f"\n  feature_count = {row.get('feature_count', 'N/A')}")
            print(f"  stale_features = {row.get('stale_features', [])}")
        return

    if not args.start:
        parser.error("--start is required (or use --today)")

    end = args.end or date.today()
    count = pipeline.run(args.start, end, dry_run=args.dry_run)
    logger.info("Done — %d rows %s", count, "computed (dry run)" if args.dry_run else "written")


if __name__ == "__main__":
    main()
