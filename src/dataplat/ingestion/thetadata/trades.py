"""ThetaData v3 option trades backfill pipeline.

Fetches tick-level trade data with NBBO from ThetaTerminal v3 using
/option/history/trade_quote?expiration=* (full chain per request per day).
Classifies aggressor side and bulk-inserts into ClickHouse option_trades table.

Requires ThetaTerminal v3 running: `just thetadata up`
Max concurrency: 4 (ThetaTerminal v3 limit).
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from datetime import date, datetime, timedelta

import httpx
import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)

# Silence httpx per-request logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_BASE_URL = "http://127.0.0.1:25503/v3"
# Large responses for SPY/QQQ — generous timeout
_DEFAULT_TIMEOUT = 300.0

# Retry config
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_NO_DATA_STATUS = {472}

# ── Column schema for trade_quote NDJSON ──────────────────

_TRADE_QUOTE_COLUMNS = {
    "symbol": pl.Utf8,
    "expiration": pl.Utf8,
    "strike": pl.Float64,
    "right": pl.Utf8,
    "trade_timestamp": pl.Utf8,
    "sequence": pl.Int64,
    "price": pl.Float64,
    "size": pl.Int64,
    "exchange": pl.Int64,
    "condition": pl.Int64,
    "bid": pl.Float64,
    "ask": pl.Float64,
    "bid_size": pl.Int64,
    "ask_size": pl.Int64,
}


def _parse_trade_quote_ndjson(ndjson_text: str) -> pl.DataFrame:
    """Parse NDJSON from /v3/option/history/trade_quote into Polars DataFrame.

    Classifies aggressor side from trade price vs NBBO:
      price >= ask → buy (lifted the ask)
      price <= bid → sell (hit the bid)
      else → mid
    """
    if not ndjson_text.strip():
        return pl.DataFrame()

    try:
        df = pl.read_ndjson(io.StringIO(ndjson_text))
    except Exception as exc:
        logger.error("Failed to parse trade_quote NDJSON: %s", exc)
        return pl.DataFrame()

    if df.is_empty():
        return df

    # Select only columns we need
    available = [c for c in _TRADE_QUOTE_COLUMNS if c in df.columns]
    df = df.select(available)

    # Rename to match ClickHouse schema
    df = df.rename({
        "symbol": "underlying",
        "right": "put_call",
    })

    # Normalize put_call
    df = df.with_columns(
        pl.col("put_call").str.to_lowercase().alias("put_call"),
    )

    # Parse expiration → Date
    df = df.with_columns(
        pl.col("expiration").str.to_date("%Y-%m-%d").alias("expiration"),
    )

    # Parse trade_timestamp → DateTime64(3)
    # ThetaData format: 2026-03-25T09:30:00.471
    df = df.with_columns(
        pl.col("trade_timestamp").str.to_datetime(
            "%Y-%m-%dT%H:%M:%S%.3f", time_zone=None, strict=False
        ).alias("trade_timestamp"),
    )

    # Drop rows where timestamp parsing failed
    df = df.drop_nulls(subset=["trade_timestamp"])

    # Cast integer columns
    df = df.with_columns(
        pl.col("sequence").cast(pl.Int64, strict=False).fill_null(0),
        pl.col("size").cast(pl.UInt32, strict=False).fill_null(0),
        pl.col("exchange").cast(pl.UInt8, strict=False).fill_null(0),
        pl.col("condition").cast(pl.UInt8, strict=False).fill_null(0),
        pl.col("bid_size").cast(pl.UInt32, strict=False).fill_null(0),
        pl.col("ask_size").cast(pl.UInt32, strict=False).fill_null(0),
    )

    # Classify aggressor side
    df = df.with_columns(
        pl.when(pl.col("price") >= pl.col("ask"))
        .then(pl.lit("buy"))
        .when(pl.col("price") <= pl.col("bid"))
        .then(pl.lit("sell"))
        .otherwise(pl.lit("mid"))
        .alias("aggressor_side"),
    )

    # Add source
    df = df.with_columns(
        pl.lit("thetadata").alias("source"),
    )

    # Final column order matching ClickHouse schema
    return df.select([
        "underlying",
        "expiration",
        "strike",
        "put_call",
        "trade_timestamp",
        "sequence",
        "price",
        "size",
        "exchange",
        "condition",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
        "aggressor_side",
        "source",
    ])


# ── Async fetch with retry ────────────────────────────────


async def _fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str],
    semaphore: asyncio.Semaphore,
    label: str,
) -> str:
    """Fetch URL with retry on transient errors. Returns response text."""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with semaphore:
                resp = await client.get(url, params=params)

            if resp.status_code in _NO_DATA_STATUS:
                return ""

            if resp.status_code in _RETRYABLE_STATUS:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "%s: HTTP %d, retry %d/%d in %.1fs",
                    label, resp.status_code, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            return resp.text

        except (
            httpx.RemoteProtocolError,
            httpx.ReadError,
            httpx.ConnectError,
            httpx.ReadTimeout,
        ) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "%s: %s, retry %d/%d in %.1fs",
                    label, type(exc).__name__, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise

    raise last_exc  # type: ignore[misc]


# ── Day-level backfill ────────────────────────────────────


async def _backfill_day(
    client: httpx.AsyncClient,
    symbol: str,
    day: str,
    semaphore: asyncio.Semaphore,
    ch_client: object,
) -> int:
    """Fetch trade_quote for one underlying on one day, insert into ClickHouse.

    Returns row count inserted.
    """
    label = f"{symbol} {day}"

    text = await _fetch_with_retry(
        client,
        f"{_BASE_URL}/option/history/trade_quote",
        {
            "symbol": symbol,
            "expiration": "*",
            "date": day,
            "format": "ndjson",
        },
        semaphore,
        label,
    )

    if not text.strip():
        return 0

    df = _parse_trade_quote_ndjson(text)

    if df.is_empty():
        return 0

    # Insert into ClickHouse
    try:
        ch_client.insert_arrow("option_trades", df.to_arrow())  # type: ignore[union-attr]
        return len(df)
    except Exception as exc:
        logger.error("%s: ClickHouse insert failed: %s", label, exc)
        return 0


# ── Resume support ────────────────────────────────────────


def _get_ingested_dates(symbol: str) -> set[str]:
    """Query ClickHouse for dates already ingested for this underlying."""
    ch = get_client()
    try:
        result = ch.query(
            "SELECT DISTINCT toString(toDate(trade_timestamp)) AS d "
            "FROM option_trades "
            "WHERE underlying = %(symbol)s AND source = 'thetadata'",
            parameters={"symbol": symbol},
        )
        return {row[0] for row in result.result_rows}
    except Exception:
        return set()


def _get_trading_dates(symbol: str) -> list[str]:
    """Fetch available trading dates from ThetaData."""
    from dataplat.ingestion.thetadata.client import get_thetadata_client

    client = get_thetadata_client()
    return client.get_trading_dates(symbol)


def _filter_dates(
    all_dates: list[str],
    ingested: set[str],
    cutoff_start: date | None = None,
) -> list[str]:
    """Filter to dates within window that haven't been ingested yet."""
    result = []
    for d in all_dates:
        dt = date.fromisoformat(d) if "-" in d else datetime.strptime(d, "%Y%m%d").date()
        if cutoff_start and dt < cutoff_start:
            continue
        normalized = dt.isoformat()
        if normalized not in ingested:
            result.append(d)
    return result


# ── Main async runner ─────────────────────────────────────


async def _run_async(
    tickers: list[str],
    concurrency: int = 4,
    resume: bool = False,
    dry_run: bool = False,
    years: int | None = None,
    days: int | None = None,
) -> None:
    """Async entry point for the option trades backfill."""
    ensure_schema()
    ch = get_client()

    # Calculate cutoff_start: days takes precedence over years
    if days is not None:
        cutoff_start = date.today() - timedelta(days=days)
    else:
        years = years if years is not None else 2
        cutoff_start = date(date.today().year - years, date.today().month, date.today().day)
    semaphore = asyncio.Semaphore(concurrency)

    start_time = time.monotonic()
    total_rows = 0
    total_requests = 0
    failures: list[tuple[str, str]] = []

    if days is not None:
        logger.info(
            "ThetaData option trades backfill: %d tickers, %d day window, concurrency=%d%s",
            len(tickers),
            days,
            concurrency,
            " (resume)" if resume else "",
        )
    else:
        logger.info(
            "ThetaData option trades backfill: %d tickers, %d year window, concurrency=%d%s",
            len(tickers),
            years,
            concurrency,
            " (resume)" if resume else "",
        )

    for ticker_idx, ticker in enumerate(tickers, 1):
        ticker_start = time.monotonic()

        # Discover trading dates
        try:
            all_dates = _get_trading_dates(ticker)
        except Exception as exc:
            logger.error(
                "[%d/%d] %s: failed to fetch trading dates: %s",
                ticker_idx, len(tickers), ticker, exc,
            )
            failures.append((ticker, "ALL"))
            continue

        # Filter dates
        ingested = _get_ingested_dates(ticker) if resume else set()
        dates = _filter_dates(all_dates, ingested, cutoff_start)

        if not dates:
            logger.info(
                "[%d/%d] %s: no dates to process",
                ticker_idx, len(tickers), ticker,
            )
            continue

        if dry_run:
            logger.info(
                "[%d/%d] %s: %d dates to backfill",
                ticker_idx, len(tickers), ticker, len(dates),
            )
            total_requests += len(dates)
            continue

        # Process dates in batches — smaller batches for SPY/QQQ (huge responses)
        ticker_rows = 0
        batch_size = 20
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http_client:
            for i in range(0, len(dates), batch_size):
                batch = dates[i : i + batch_size]
                tasks = [
                    _backfill_day(http_client, ticker, day, semaphore, ch)
                    for day in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                batch_rows = 0
                for j, result in enumerate(results):
                    if isinstance(result, Exception):
                        day = batch[j]
                        logger.error("%s %s: %s", ticker, day, result)
                        failures.append((ticker, day))
                    elif isinstance(result, int):
                        batch_rows += result

                ticker_rows += batch_rows

                # Progress log every batch
                days_done = min(i + batch_size, len(dates))
                elapsed_so_far = time.monotonic() - ticker_start
                rate = days_done / elapsed_so_far if elapsed_so_far > 0 else 0
                eta = (len(dates) - days_done) / rate if rate > 0 else 0
                logger.info(
                    "  %s: %d/%d days (%s rows) — %.1f days/min, ETA %.0fm",
                    ticker, days_done, len(dates),
                    f"{ticker_rows:,}", rate * 60, eta / 60,
                )

        ticker_elapsed = time.monotonic() - ticker_start
        total_rows += ticker_rows
        logger.info(
            "[%d/%d] %s: %s rows across %d dates (%.1fs)",
            ticker_idx, len(tickers), ticker,
            f"{ticker_rows:,}" if ticker_rows else "0",
            len(dates), ticker_elapsed,
        )

    elapsed = time.monotonic() - start_time

    if dry_run:
        logger.info(
            "DRY RUN: %d tickers, %d total days to backfill",
            len(tickers), total_requests,
        )
        return

    logger.info(
        "Option trades backfill complete: %s total rows in %.1f minutes",
        f"{total_rows:,}", elapsed / 60,
    )
    if failures:
        logger.warning(
            "Failed (%d): %s",
            len(failures),
            ", ".join(f"{t}:{d}" for t, d in failures[:20]),
        )
        if len(failures) > 20:
            logger.warning("... and %d more failures", len(failures) - 20)


def run_option_trades_backfill(
    tickers: list[str],
    concurrency: int = 4,
    resume: bool = False,
    dry_run: bool = False,
    years: int | None = None,
    days: int | None = None,
) -> None:
    """Synchronous wrapper for the async option trades backfill."""
    asyncio.run(_run_async(tickers, concurrency, resume, dry_run, years, days))
