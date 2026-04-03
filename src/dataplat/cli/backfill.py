"""CLI entry point: python -m dataplat.cli.backfill

Supports both Polygon 1-min backfill and Schwab daily backfill.

Universe options:
    --universe spy     S&P 500 constituents (503 tickers)
    --universe qqq     Nasdaq-100 constituents (101 tickers)
    --universe all     All active US equities from Polygon (fetches dynamically)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

UNIVERSES_DIR = Path(__file__).resolve().parents[1] / "ingestion" / "polygon" / "universes"


def _load_universe(name: str) -> list[str]:
    """Load tickers from a universe file or fetch dynamically for 'all'."""
    if name == "all":
        all_file = UNIVERSES_DIR / "all.txt"
        if not all_file.exists():
            logging.info("all.txt not found — fetching all active US equities from Polygon...")
            from dataplat.ingestion.polygon.universes.fetch_all import fetch_all_tickers

            tickers = fetch_all_tickers()
            all_file.write_text("\n".join(tickers) + "\n")
            logging.info("Wrote %d tickers to all.txt", len(tickers))
            return tickers
        return [t.strip() for t in all_file.read_text().splitlines() if t.strip()]

    universe_file = UNIVERSES_DIR / f"{name}.txt"
    if not universe_file.exists():
        available = [f.stem for f in UNIVERSES_DIR.glob("*.txt")]
        logging.error("Unknown universe '%s'. Available: %s", name, ", ".join(available))
        sys.exit(1)
    return [t.strip() for t in universe_file.read_text().splitlines() if t.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill OHLCV data into ClickHouse")
    parser.add_argument(
        "--source",
        choices=["polygon", "schwab"],
        required=True,
        help="Data source: 'polygon' for 1-min backfill, 'schwab' for daily",
    )

    ticker_group = parser.add_mutually_exclusive_group(required=True)
    ticker_group.add_argument("--tickers", type=str, help="Comma-separated ticker symbols")
    ticker_group.add_argument("--file", type=str, help="Path to file with one ticker per line")
    ticker_group.add_argument(
        "--universe",
        type=str,
        metavar="NAME",
        help="Predefined universe: spy (S&P 500), qqq (Nasdaq-100), all (fetches from Polygon)",
    )

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
        tickers = [line.strip().upper() for line in Path(args.file).read_text().splitlines() if line.strip()]
    elif args.universe:
        tickers = _load_universe(args.universe.lower())

    if not tickers:
        logging.error("No tickers resolved. Check your --tickers, --file, or --universe argument.")
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
