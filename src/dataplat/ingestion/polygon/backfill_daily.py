"""Polygon daily OHLCV backfill via Grouped Daily endpoint.

Uses /v2/aggs/grouped/locale/us/market/stocks/{date} which returns
OHLCV for every US stock in a single API call per day.

Inserts into the `ohlcv_daily` table (first-class, not an MV).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

POLYGON_BASE = "https://api.polygon.io"

_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _trading_days(months: int) -> list[date]:
    """Generate weekday dates going back N months from today."""
    end = date.today()
    start = end - timedelta(days=months * 31)
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            days.append(current)
        current += timedelta(days=1)
    return days


def _transform_grouped(results: list[dict], day: date) -> pl.DataFrame:
    """Transform Polygon grouped daily response into ohlcv_daily schema."""
    if not results:
        return pl.DataFrame()

    df = pl.DataFrame(results)

    # Polygon grouped fields: T (ticker), o, h, l, c, v, vw, n
    df = df.select(
        pl.col("T").alias("ticker"),
        pl.lit(day).alias("day"),
        pl.col("o").cast(pl.Float64).alias("open"),
        pl.col("h").cast(pl.Float64).alias("high"),
        pl.col("l").cast(pl.Float64).alias("low"),
        pl.col("c").cast(pl.Float64).alias("close"),
        pl.col("v").cast(pl.Int64).cast(pl.UInt64).alias("volume"),
        pl.col("vw").cast(pl.Float64).alias("vwap"),
        pl.col("n").cast(pl.UInt32).alias("transactions"),
        pl.lit("polygon").alias("source"),
        pl.lit(datetime.now(timezone.utc)).alias("ingested_at"),
    )

    # Basic validation
    df = df.filter(
        (pl.col("high") >= pl.col("low"))
        & (pl.col("volume") > 0)
        & (pl.col("close") > 0)
    )

    return df


async def _fetch_day(
    client: httpx.AsyncClient,
    day: date,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Fetch grouped daily bars for one date with retry."""
    url = f"{POLYGON_BASE}/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}"
    params = {"adjusted": "true", "apiKey": settings.polygon_api_key}

    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with semaphore:
                resp = await client.get(url, params=params)

            if resp.status_code in _RETRYABLE_STATUS:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "%s: HTTP %d, retry %d/%d in %.1fs",
                    day, resp.status_code, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            data = resp.json()

            if data.get("resultsCount", 0) == 0:
                return []

            return data.get("results", [])

        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning("%s: %s, retry %d/%d", day, type(exc).__name__, attempt + 1, _MAX_RETRIES)
                await asyncio.sleep(delay)
            else:
                logger.error("%s: failed after %d retries — %s", day, _MAX_RETRIES, exc)
                return []

    return []


async def _run_async(
    months: int = 3,
    ticker_filter: set[str] | None = None,
    concurrency: int = 5,
) -> None:
    """Async entry point for daily backfill."""
    if not settings.polygon_api_key:
        raise RuntimeError("POLYGON_API_KEY must be set in .env")

    ensure_schema()
    ch = get_client()

    days = _trading_days(months)
    semaphore = asyncio.Semaphore(concurrency)
    start_time = time.monotonic()
    total_rows = 0

    logger.info(
        "Polygon daily backfill: %d trading days, concurrency=%d%s",
        len(days),
        concurrency,
        f", filtering to {len(ticker_filter)} tickers" if ticker_filter else "",
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Process in batches to avoid memory blow-up
        batch_size = concurrency
        for i in range(0, len(days), batch_size):
            batch = days[i : i + batch_size]
            tasks = [_fetch_day(client, d, semaphore) for d in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(results):
                day = batch[j]
                if isinstance(result, Exception):
                    logger.error("%s: %s", day, result)
                    continue
                if not result:
                    continue

                df = _transform_grouped(result, day)

                if ticker_filter and not df.is_empty():
                    df = df.filter(pl.col("ticker").is_in(ticker_filter))

                if df.is_empty():
                    continue

                try:
                    ch.insert_arrow("ohlcv_daily", df.to_arrow())
                    total_rows += len(df)
                    logger.info("[%s] %d tickers inserted", day, len(df))
                except Exception as exc:
                    logger.error("[%s] insert failed: %s", day, exc)

    elapsed = time.monotonic() - start_time
    logger.info(
        "Polygon daily backfill complete: %s rows across %d days in %.1f seconds",
        f"{total_rows:,}",
        len(days),
        elapsed,
    )


def run_polygon_daily_backfill(
    months: int = 3,
    ticker_filter: set[str] | None = None,
    concurrency: int = 5,
) -> None:
    """Synchronous wrapper for the async daily backfill."""
    asyncio.run(_run_async(months, ticker_filter, concurrency))
