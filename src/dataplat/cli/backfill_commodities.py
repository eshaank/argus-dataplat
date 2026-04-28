"""CLI: Backfill/fetch commodity and EIA petroleum data.

Usage:
    uv run python -m dataplat.cli.backfill_commodities                  # All sources, full history
    uv run python -m dataplat.cli.backfill_commodities --source eia     # EIA only
    uv run python -m dataplat.cli.backfill_commodities --source yfinance
    uv run python -m dataplat.cli.backfill_commodities --source fred    # FRED gold/silver only
    uv run python -m dataplat.cli.backfill_commodities --start 2025-04-01  # Pull recent
    uv run python -m dataplat.cli.backfill_commodities --table eia_petroleum_weekly
    uv run python -m dataplat.cli.backfill_commodities --list
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill/fetch commodity prices and EIA petroleum data",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch all sources (equivalent to omitting --source)",
    )
    parser.add_argument(
        "--source",
        choices=["eia", "yfinance"],
        help="Data source to fetch from. Omit or use --all for all sources.",
    )
    parser.add_argument(
        "--table",
        action="append",
        metavar="NAME",
        help="EIA table to backfill (repeatable). Omit for all EIA tables.",
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="Start date. Omit for full history.",
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        help="End date. Omit for latest available.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available EIA tables and their series, then exit.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list:
        from dataplat.ingestion.eia.registry import ALL_TABLES as EIA_TABLES
        from dataplat.ingestion.yfinance.commodities import FUTURES_MAP

        print("\n── EIA Tables ──")
        for config in EIA_TABLES:
            print(f"\n  {config.table} (from {config.start}):")
            for col, spec in config.series.items():
                if len(spec) == 4:
                    route, _, freq, facets = spec
                    print(f"    {col:25s} ← {route} / {facets} ({freq})")
                else:
                    route, series_id, freq = spec
                    print(f"    {col:25s} ← {route} / {series_id} ({freq})")

        print("\n── Yahoo Finance → commodity_prices ──")
        for yf_ticker, col in FUTURES_MAP.items():
            print(f"    {yf_ticker:10s} → {col}")

        sys.exit(0)

    sources_to_run = (
        [args.source] if args.source else ["eia", "yfinance"]
    )

    if "eia" in sources_to_run:
        from dataplat.ingestion.eia.backfill import run_eia_backfill

        logging.getLogger(__name__).info("── EIA: energy prices + petroleum data ──")
        run_eia_backfill(tables=args.table, start=args.start, end=args.end)

    if "yfinance" in sources_to_run:
        from dataplat.ingestion.yfinance.commodities import run_yfinance_commodities

        logging.getLogger(__name__).info("── Yahoo Finance: metals + agriculture futures ──")
        run_yfinance_commodities(start=args.start, end=args.end)


if __name__ == "__main__":
    main()
