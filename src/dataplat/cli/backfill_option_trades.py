"""CLI entry point: python -m dataplat.cli.backfill_option_trades

Backfills tick-level option trade data with NBBO from ThetaData v3
into the option_trades ClickHouse table.

Requires ThetaTerminal v3 running: `just thetadata up`

Examples:
    just backfill-option-trades --tickers ARM
    just backfill-option-trades --tickers ARM,SPY,QQQ --years 2
    just backfill-option-trades --tickers SPY --days 5 --resume
    just backfill-option-trades --tickers SPY,QQQ --dry-run
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
        description="Backfill tick-level option trades from ThetaData v3 into ClickHouse"
    )

    ticker_group = parser.add_mutually_exclusive_group(required=True)
    ticker_group.add_argument("--tickers", type=str, help="Comma-separated ticker symbols")
    ticker_group.add_argument("--file", type=str, help="Path to file with one ticker per line")
    ticker_group.add_argument(
        "--universe",
        type=str,
        metavar="NAME",
        help="Predefined universe: sp100, spy, qqq",
    )

    parser.add_argument("--years", type=int, default=None, help="Years of history (default 2 if no --days)")
    parser.add_argument("--days", type=int, default=None, help="Days of history (overrides --years if set)")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent requests (default 4, max 4)")
    parser.add_argument("--resume", action="store_true", help="Skip already-ingested (underlying, date) pairs")
    parser.add_argument("--dry-run", action="store_true", help="Count dates without fetching data")
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

    # Determine time range
    if args.days is not None:
        logging.info(
            "Option trades backfill: %d ticker(s), %d days, concurrency=%d",
            len(tickers), args.days, concurrency,
        )
    else:
        years = args.years if args.years is not None else 2
        logging.info(
            "Option trades backfill: %d ticker(s), %d years, concurrency=%d",
            len(tickers), years, concurrency,
        )

    from dataplat.ingestion.thetadata.trades import run_option_trades_backfill

    run_option_trades_backfill(
        tickers=tickers,
        concurrency=concurrency,
        resume=args.resume,
        dry_run=args.dry_run,
        years=args.years,
        days=args.days,
    )


if __name__ == "__main__":
    main()
