"""CLI entry point: python -m dataplat.cli.backfill_edgar

Backfills SEC EDGAR data: financials, filings, insider trades, institutional holders.
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


def _load_gap_tickers() -> list[str]:
    """Find tickers in universe but missing from financials table."""
    from dataplat.db.client import get_client
    from dataplat.db.migrate import ensure_schema

    ensure_schema()
    ch = get_client()
    rows = ch.query(
        "SELECT ticker FROM universe WHERE ticker NOT IN "
        "(SELECT DISTINCT ticker FROM financials WHERE source = 'sec_edgar') "
        "ORDER BY ticker"
    ).result_rows
    return [r[0] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill SEC EDGAR data (financials, filings, insider trades, institutional holders)"
    )

    # What to backfill
    parser.add_argument("--all", action="store_true", help="Backfill everything")
    parser.add_argument("--financials", action="store_true", help="Backfill financials (income, balance, cashflow, dilution)")
    parser.add_argument("--filings", action="store_true", help="Backfill filing index + material events")
    parser.add_argument("--insider", action="store_true", help="Backfill insider trades (Form 4)")
    parser.add_argument("--institutional", action="store_true", help="Backfill institutional holders (SC 13G/13D)")

    # Ticker selection
    ticker_group = parser.add_mutually_exclusive_group()
    ticker_group.add_argument("--tickers", type=str, help="Comma-separated ticker symbols")
    ticker_group.add_argument("--file", type=str, help="Path to file with one ticker per line")
    ticker_group.add_argument("--universe", type=str, metavar="NAME", help="Predefined universe: spy, qqq, all")
    ticker_group.add_argument("--gaps-only", action="store_true", help="Only tickers missing from financials")

    # Options
    parser.add_argument("--insider-years", type=int, default=3, help="Years of Form 4 history (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve tickers
    tickers: list[str] = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.file:
        tickers = [line.strip().upper() for line in Path(args.file).read_text().splitlines() if line.strip()]
    elif args.universe:
        tickers = _load_universe(args.universe.lower())
    elif args.gaps_only:
        tickers = _load_gap_tickers()
        logging.info("Found %d tickers missing from financials", len(tickers))

    if not tickers:
        logging.error("No tickers resolved. Use --tickers, --universe, --file, or --gaps-only")
        sys.exit(1)

    # Resolve what to backfill
    do_financials = args.all or args.financials
    do_filings = args.all or args.filings
    do_insider = args.all or args.insider
    do_institutional = args.all or args.institutional

    if not any([do_financials, do_filings, do_insider, do_institutional]):
        logging.error("Specify what to backfill: --all, --financials, --filings, --insider, --institutional")
        sys.exit(1)

    if args.dry_run:
        logging.info("DRY RUN — would backfill %d tickers:", len(tickers))
        if do_financials:
            logging.info("  ✓ financials (companyfacts API)")
        if do_filings:
            logging.info("  ✓ sec_filings + material_events (submissions API)")
        if do_insider:
            logging.info("  ✓ insider_trades (Form 4 XML, %d years)", args.insider_years)
        if do_institutional:
            logging.info("  ✓ institutional_holders (SC 13G/13D)")
        logging.info("  Tickers: %s", ", ".join(tickers[:20]) + ("..." if len(tickers) > 20 else ""))
        return

    # Load shared resources
    from dataplat.ingestion.edgar.cik_map import CIKMap
    from dataplat.ingestion.edgar.client import make_client

    cik_map = CIKMap()
    cik_map.load()
    client = make_client()

    try:
        if do_financials:
            from dataplat.ingestion.edgar.financials import run_financials_backfill

            run_financials_backfill(tickers, cik_map=cik_map, client=client)

        if do_filings:
            from dataplat.ingestion.edgar.filings import run_filings_backfill

            run_filings_backfill(tickers, cik_map=cik_map, client=client)

        if do_insider:
            from dataplat.ingestion.edgar.insider import run_insider_backfill

            run_insider_backfill(tickers, years=args.insider_years, cik_map=cik_map, client=client)

        if do_institutional:
            from dataplat.ingestion.edgar.institutional import run_institutional_backfill

            run_institutional_backfill(tickers, cik_map=cik_map, client=client)

    finally:
        client.close()


if __name__ == "__main__":
    main()
