"""Schwab daily OHLCV backfill pipeline.

Uses schwabdev to fetch up to 20 years of daily candles per ticker,
transforms via Polars, and bulk-inserts into ClickHouse.
"""

from __future__ import annotations

import logging
import time

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.schwab.client import get_schwab_client
from dataplat.transforms.ohlcv import transform_schwab_candles
from dataplat.transforms.validation import validate_ohlcv

logger = logging.getLogger(__name__)

# Schwab rate limit: 120 requests/min → 500ms between requests
REQUEST_DELAY_S = 0.5


def _backfill_ticker(ticker: str, years: int) -> int:
    """Fetch and insert daily candles for one ticker. Returns row count."""
    client = get_schwab_client()
    ch = get_client()

    resp = client.price_history(
        symbol=ticker,
        periodType="year",
        period=years,
        frequencyType="daily",
        frequency=1,
        needExtendedHoursData=False,
        needPreviousClose=False,
    )

    if not resp.ok:
        logger.error("%s: Schwab API returned HTTP %d", ticker, resp.status_code)
        return 0

    data = resp.json()
    if data.get("empty", True):
        logger.warning("%s: No candle data returned", ticker)
        return 0

    candles = data.get("candles", [])
    if not candles:
        return 0

    df = transform_schwab_candles(candles, ticker)
    df = validate_ohlcv(df)

    if df.is_empty():
        return 0

    try:
        ch.insert_arrow("ohlcv", df.to_arrow())
        return len(df)
    except Exception as exc:
        logger.error("%s: ClickHouse insert failed: %s", ticker, exc)
        return 0


def run_schwab_backfill(tickers: list[str], years: int = 20) -> None:
    """Backfill daily candles for a list of tickers."""
    logger.info("Schwab daily backfill: %d tickers, %d years", len(tickers), years)
    ensure_schema()
    start_time = time.monotonic()
    total_rows = 0
    failures: list[str] = []

    for idx, ticker in enumerate(tickers, 1):
        try:
            rows = _backfill_ticker(ticker, years)
            total_rows += rows
            logger.info("[%d/%d] %s: %s rows", idx, len(tickers), ticker, f"{rows:,}" if rows else "0")
        except Exception as exc:
            logger.error("[%d/%d] %s: FAILED — %s", idx, len(tickers), ticker, exc)
            failures.append(ticker)

        # Rate limit
        if idx < len(tickers):
            time.sleep(REQUEST_DELAY_S)

    elapsed = time.monotonic() - start_time
    logger.info(
        "Schwab backfill complete: %s total rows in %.1f minutes",
        f"{total_rows:,}",
        elapsed / 60,
    )
    if failures:
        logger.warning("Failed tickers (%d): %s", len(failures), ", ".join(failures))
