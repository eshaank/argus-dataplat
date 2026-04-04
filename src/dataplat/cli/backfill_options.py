"""CLI entry point: python -m dataplat.cli.backfill_options

Backfills historical EOD option chain snapshots (greeks, IV, OI, OHLCV)
from ThetaData v3 into the option_chains ClickHouse table.

Requires ThetaTerminal v3 running: `just thetadata up`

Examples:
    just backfill-options --tickers AAPL,MSFT
    just backfill-options --universe sp100
    just backfill-options --universe sp100 --resume
    just backfill-options --universe sp100 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

UNIVERSES_DIR = Path(__file__).resolve().parents[1] / "ingestion" / "polygon" / "universes"


def _load_universe(name: str) -> list[str]:
    """Load tickers from a universe file."""
    universe_file = UNIVERSES_DIR / f"{name}.txt"
    if not universe_file.exists():
        available = [f.stem for f in UNIVERSES_DIR.glob("*.txt")]
        logging.error("Unknown universe '%s'. Available: %s", name, ", ".join(available))
        sys.exit(1)
    return [t.strip() for t in universe_file.read_text().splitlines() if t.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill historical options data from ThetaData v3 into ClickHouse"
    )

    ticker_group = parser.add_mutually_exclusive_group(required=True)
    ticker_group.add_argument("--tickers", type=str, help="Comma-separated ticker symbols")
    ticker_group.add_argument("--file", type=str, help="Path to file with one ticker per line")
    ticker_group.add_argument(
        "--universe",
        type=str,
        metavar="NAME",
        help="Predefined universe: sp100, spy (S&P 500), qqq (Nasdaq-100)",
    )

    parser.add_argument("--years", type=int, default=8, help="Years of history (default 8)")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent requests (default 4, max 4)")
    parser.add_argument("--resume", action="store_true", help="Skip already-ingested (underlying, date) pairs")
    parser.add_argument("--dry-run", action="store_true", help="Count requests and estimate time without fetching data")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Clamp concurrency to ThetaTerminal v3 limit
    concurrency = min(args.concurrency, 4)
    if args.concurrency > 4:
        logging.warning("ThetaTerminal v3 max concurrency is 4, clamping from %d", args.concurrency)

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

    logging.info("Options backfill: %d ticker(s), %d years, concurrency=%d", len(tickers), args.years, concurrency)

    from dataplat.ingestion.thetadata.options import run_options_backfill

    run_options_backfill(
        tickers=tickers,
        concurrency=concurrency,
        resume=args.resume,
        dry_run=args.dry_run,
        years=args.years,
    )


if __name__ == "__main__":
    main()
