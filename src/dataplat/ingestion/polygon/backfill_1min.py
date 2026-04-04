"""ONE-OFF Polygon 1-minute OHLCV backfill.

Fetches ~4 years of 1-min bars from Polygon's /v2/aggs endpoint,
transforms via Polars, and bulk-inserts into ClickHouse.

This pipeline is designed to run once to seed the ohlcv table.
After that, Schwab is the sole ongoing data source.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.transforms.ohlcv import transform_polygon_aggs
from dataplat.transforms.validation import validate_ohlcv

logger = logging.getLogger(__name__)

# Silence httpx per-request logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

POLYGON_BASE = "https://api.polygon.io/v2/aggs/ticker"

# Retry config for transient failures (disconnects, 429s, 5xx)
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 1.0  # seconds, doubles each attempt
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _month_ranges(months: int) -> list[tuple[str, str]]:
    """Generate (from_date, to_date) pairs going back N months from today."""
    end = date.today()
    ranges: list[tuple[str, str]] = []
    for _ in range(months):
        start = (end.replace(day=1) - timedelta(days=1)).replace(day=1)
        ranges.append((start.isoformat(), end.isoformat()))
        end = start - timedelta(days=1)
    ranges.reverse()
    return ranges


async def _fetch_month(
    client: httpx.AsyncClient,
    ticker: str,
    from_date: str,
    to_date: str,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Fetch 1-min bars for one ticker-month with retry on transient errors."""
    url = f"{POLYGON_BASE}/{ticker}/range/1/minute/{from_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": "50000", "apiKey": settings.polygon_api_key}

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with semaphore:
                resp = await client.get(url, params=params)

            if resp.status_code == 403:
                logger.debug("%s %s→%s: NOT_AUTHORIZED (before plan lookback)", ticker, from_date, to_date)
                return []

            if resp.status_code in _RETRYABLE_STATUS:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "%s %s→%s: HTTP %d, retry %d/%d in %.1fs",
                    ticker, from_date, to_date, resp.status_code, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "NOT_AUTHORIZED":
                return []

            return data.get("results", [])

        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "%s %s→%s: %s, retry %d/%d in %.1fs",
                    ticker, from_date, to_date, type(exc).__name__, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise

    raise last_exc  # type: ignore[misc]  # should never reach here


async def _backfill_ticker(
    client: httpx.AsyncClient,
    ticker: str,
    ranges: list[tuple[str, str]],
    semaphore: asyncio.Semaphore,
) -> int:
    """Backfill all months for a single ticker. Returns total rows inserted."""
    ch = get_client()
    total = 0

    tasks = [_fetch_month(client, ticker, fr, to, semaphore) for fr, to in ranges]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("%s month %d failed: %s", ticker, i, result)
            continue
        if not result:
            continue

        df = transform_polygon_aggs(result, ticker)
        df = validate_ohlcv(df)

        if df.is_empty():
            continue

        try:
            ch.insert_arrow("ohlcv", df.to_arrow())
            total += len(df)
        except Exception as exc:
            logger.error("%s insert failed for month %d: %s", ticker, i, exc)

    return total


async def _run_async(tickers: list[str], months: int, concurrency: int) -> None:
    """Async entry point for the backfill."""
    if not settings.polygon_api_key:
        raise RuntimeError("POLYGON_API_KEY must be set in .env for the backfill")

    ensure_schema()

    ranges = _month_ranges(months)
    semaphore = asyncio.Semaphore(concurrency)
    start_time = time.monotonic()
    completed = 0
    total_rows = 0
    lock = asyncio.Lock()

    logger.info("Polygon 1-min backfill: %d tickers × %d months, concurrency=%d", len(tickers), len(ranges), concurrency)

    async def _process_ticker(client: httpx.AsyncClient, ticker: str) -> None:
        nonlocal completed, total_rows
        ticker_start = time.monotonic()
        rows = await _backfill_ticker(client, ticker, ranges, semaphore)
        elapsed = time.monotonic() - ticker_start
        async with lock:
            completed += 1
            total_rows += rows
            logger.info(
                "[%d/%d] %s: %s rows (%.1fs)",
                completed, len(tickers), ticker,
                f"{rows:,}" if rows else "0", elapsed,
            )

    # Process tickers in batches (concurrency controls total HTTP requests,
    # ticker_batch_size controls how many tickers run simultaneously)
    ticker_batch_size = max(concurrency // 4, 5)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(tickers), ticker_batch_size):
            batch = tickers[i : i + ticker_batch_size]
            await asyncio.gather(*[_process_ticker(client, t) for t in batch])

    total_elapsed = time.monotonic() - start_time
    logger.info(
        "Polygon backfill complete: %s rows in %.1f minutes (%.0f rows/sec)",
        f"{total_rows:,}", total_elapsed / 60, total_rows / max(total_elapsed, 1),
    )


def run_polygon_backfill(tickers: list[str], months: int = 48, concurrency: int = 10) -> None:
    """Synchronous wrapper for the async backfill."""
    asyncio.run(_run_async(tickers, months, concurrency))
