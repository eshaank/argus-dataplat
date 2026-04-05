"""CLI entry point: python -m dataplat.cli.backfill_fundamentals

Backfills dividends, splits, and universe details from Polygon.
Economy data is handled by backfill_economy (FRED).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

UNIVERSES_DIR = Path(__file__).resolve().parents[1] / "ingestion" / "polygon" / "universes"


def _load_universe(name: str) -> list[str]:
    """Load tickers from a universe file."""
    if name == "all":
        all_file = UNIVERSES_DIR / "all.txt"
        if not all_file.exists():
            logging.info("all.txt not found — fetching from Polygon...")
            from dataplat.ingestion.polygon.universes.fetch_all import fetch_all_tickers
            tickers = fetch_all_tickers()
            all_file.write_text("\n".join(tickers) + "\n")
            return tickers
        return [t.strip() for t in all_file.read_text().splitlines() if t.strip()]

    universe_file = UNIVERSES_DIR / f"{name}.txt"
    if not universe_file.exists():
        available = [f.stem for f in UNIVERSES_DIR.glob("*.txt")]
        logging.error("Unknown universe '%s'. Available: %s", name, ", ".join(available))
        sys.exit(1)
    return [t.strip() for t in universe_file.read_text().splitlines() if t.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill dividends, splits, universe details from Polygon")

    ticker_group = parser.add_mutually_exclusive_group()
    ticker_group.add_argument("--tickers", type=str, help="Comma-separated ticker symbols")
    ticker_group.add_argument("--file", type=str, help="Path to file with one ticker per line")
    ticker_group.add_argument("--universe", type=str, metavar="NAME", help="Predefined universe: spy, qqq, all")

    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Dividends, splits, universe enrichment
    tickers: list[str] = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.file:
        tickers = [line.strip().upper() for line in Path(args.file).read_text().splitlines() if line.strip()]
    elif args.universe:
        tickers = _load_universe(args.universe.lower())

    if tickers:
        from dataplat.ingestion.polygon.fundamentals import run_fundamentals_backfill
        run_fundamentals_backfill(tickers=tickers)
    else:
        logging.error("Specify --tickers, --universe, or --file")
        sys.exit(1)


if __name__ == "__main__":
    main()
