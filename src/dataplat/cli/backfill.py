"""CLI entry point: python -m dataplat.cli.backfill

Supports both Polygon 1-min backfill and Schwab daily backfill.
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill OHLCV data into ClickHouse")
    parser.add_argument(
        "--source",
        choices=["polygon", "schwab"],
        required=True,
        help="Data source: 'polygon' for 1-min backfill, 'schwab' for daily",
    )
    parser.add_argument("--tickers", type=str, help="Comma-separated ticker symbols")
    parser.add_argument("--file", type=str, help="Path to file with one ticker per line")
    parser.add_argument("--universe", action="store_true", help="Use all tickers from universe table")
    parser.add_argument("--months", type=int, default=48, help="Months of history (polygon, default 48)")
    parser.add_argument("--years", type=int, default=20, help="Years of history (schwab, default 20)")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent requests (polygon, default 10)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve ticker list
    tickers: list[str] = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.file:
        from pathlib import Path

        tickers = [line.strip().upper() for line in Path(args.file).read_text().splitlines() if line.strip()]
    elif args.universe:
        from dataplat.db.client import get_client

        client = get_client()
        rows = client.query("SELECT ticker FROM universe WHERE active = true ORDER BY ticker").result_rows
        tickers = [row[0] for row in rows]

    if not tickers:
        logging.error("No tickers specified. Use --tickers, --file, or --universe.")
        sys.exit(1)

    logging.info("Backfilling %d ticker(s) from %s", len(tickers), args.source)

    if args.source == "polygon":
        from dataplat.ingestion.polygon.backfill_1min import run_polygon_backfill

        run_polygon_backfill(tickers=tickers, months=args.months, concurrency=args.concurrency)
    elif args.source == "schwab":
        from dataplat.ingestion.schwab.historical import run_schwab_backfill

        run_schwab_backfill(tickers=tickers, years=args.years)


if __name__ == "__main__":
    main()
