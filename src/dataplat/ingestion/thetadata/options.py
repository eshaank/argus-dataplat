"""ThetaData v3 options backfill pipeline.

Fetches 8 years of EOD option chain snapshots (greeks, IV, OI, OHLCV)
from ThetaTerminal v3 using expiration=* wildcard (full chain per request).
Transforms via Polars and bulk-inserts into ClickHouse.

Requires ThetaTerminal v3 running: `just thetadata up`
Max concurrency: 4 (ThetaTerminal v3 limit).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta

import httpx
import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.thetadata.transforms import (
    merge_greeks_and_oi,
    parse_greeks_ndjson,
    parse_oi_ndjson,
    validate_options,
)

logger = logging.getLogger(__name__)

# Silence httpx per-request logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_BASE_URL = "http://127.0.0.1:25503/v3"
_DEFAULT_TIMEOUT = 120.0

# Retry config
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# 472 = ThetaData "no data" (weekends, holidays, non-trading dates)
_NO_DATA_STATUS = {472}


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
                # No data for this date (weekend, holiday, etc.)
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

        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.ReadTimeout) as exc:
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


async def _backfill_day(
    client: httpx.AsyncClient,
    symbol: str,
    day: str,
    semaphore: asyncio.Semaphore,
    ch_client: object,
) -> int:
    """Fetch greeks + OI for one underlying on one day, insert into ClickHouse.

    Returns row count inserted.
    """
    label = f"{symbol} {day}"

    # 1. Fetch EOD greeks (full chain)
    greeks_text = await _fetch_with_retry(
        client,
        f"{_BASE_URL}/option/history/greeks/eod",
        {
            "symbol": symbol,
            "expiration": "*",
            "start_date": day,
            "end_date": day,
            "format": "ndjson",
        },
        semaphore,
        f"{label} greeks",
    )

    # 2. Fetch open interest (full chain)
    oi_text = await _fetch_with_retry(
        client,
        f"{_BASE_URL}/option/history/open_interest",
        {
            "symbol": symbol,
            "expiration": "*",
            "date": day,
            "format": "ndjson",
        },
        semaphore,
        f"{label} OI",
    )

    # 3. Parse + merge + validate
    snapshot_date = date.fromisoformat(day) if "-" in day else datetime.strptime(day, "%Y%m%d").date()
    greeks_df = parse_greeks_ndjson(greeks_text, snapshot_date)
    oi_df = parse_oi_ndjson(oi_text)

    if greeks_df.is_empty():
        logger.debug("%s: no greeks data", label)
        return 0

    df = merge_greeks_and_oi(greeks_df, oi_df)
    df = validate_options(df)

    if df.is_empty():
        return 0

    # 4. Insert into ClickHouse
    try:
        ch_client.insert_arrow("option_chains", df.to_arrow())  # type: ignore[union-attr]
        return len(df)
    except Exception as exc:
        logger.error("%s: ClickHouse insert failed: %s", label, exc)
        return 0


def _get_ingested_dates(symbol: str) -> set[str]:
    """Query ClickHouse for dates already ingested for this underlying.

    Returns set of YYYY-MM-DD strings.
    """
    ch = get_client()
    try:
        result = ch.query(
            "SELECT DISTINCT toString(snapshot_date) AS d "
            "FROM option_chains "
            "WHERE underlying = %(symbol)s AND source = 'thetadata'",
            parameters={"symbol": symbol},
        )
        return {row[0] for row in result.result_rows}
    except Exception:
        return set()


def _get_trading_dates(symbol: str) -> list[str]:
    """Fetch available trading dates from ThetaData for this underlying."""
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
        # Normalize to YYYY-MM-DD for comparison
        normalized = dt.isoformat()
        if normalized not in ingested:
            result.append(d)
    return result


async def _run_async(
    tickers: list[str],
    concurrency: int = 4,
    resume: bool = False,
    dry_run: bool = False,
    years: int | None = None,
    days: int | None = None,
) -> None:
    """Async entry point for the options backfill."""
    ensure_schema()
    ch = get_client()

    # Calculate cutoff_start: days takes precedence over years
    if days is not None:
        cutoff_start = date.today() - timedelta(days=days)
    else:
        years = years if years is not None else 8
        cutoff_start = date(date.today().year - years, date.today().month, date.today().day)
    semaphore = asyncio.Semaphore(concurrency)

    start_time = time.monotonic()
    total_rows = 0
    total_requests = 0
    failures: list[tuple[str, str]] = []

    if days is not None:
        logger.info(
            "ThetaData options backfill: %d tickers, %d day window, concurrency=%d%s",
            len(tickers),
            days,
            concurrency,
            " (resume)" if resume else "",
        )
    else:
        logger.info(
            "ThetaData options backfill: %d tickers, %d year window, concurrency=%d%s",
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
            logger.error("[%d/%d] %s: failed to fetch trading dates: %s", ticker_idx, len(tickers), ticker, exc)
            failures.append((ticker, "ALL"))
            continue

        # Filter dates
        ingested = _get_ingested_dates(ticker) if resume else set()
        dates = _filter_dates(all_dates, ingested, cutoff_start)

        if not dates:
            logger.info("[%d/%d] %s: no dates to process (all ingested or out of window)", ticker_idx, len(tickers), ticker)
            continue

        if dry_run:
            requests_needed = len(dates) * 2  # greeks + OI per day
            logger.info(
                "[%d/%d] %s: %d dates, %d requests needed",
                ticker_idx, len(tickers), ticker, len(dates), requests_needed,
            )
            total_requests += requests_needed
            continue

        # Process dates in batches for this ticker
        ticker_rows = 0
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as http_client:
            # Process dates concurrently (semaphore limits to 4)
            # But batch to avoid building huge task lists
            batch_size = 50
            for i in range(0, len(dates), batch_size):
                batch = dates[i : i + batch_size]
                tasks = [
                    _backfill_day(http_client, ticker, day, semaphore, ch)
                    for day in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for j, result in enumerate(results):
                    if isinstance(result, Exception):
                        day = batch[j]
                        logger.error("%s %s: %s", ticker, day, result)
                        failures.append((ticker, day))
                    elif isinstance(result, int):
                        ticker_rows += result

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
        est_hours = total_requests / 3.6 / 3600  # ~3.6 req/s at concurrency=4
        logger.info(
            "DRY RUN: %d tickers, %s total requests, estimated %.1f hours at concurrency=%d",
            len(tickers), f"{total_requests:,}", est_hours, concurrency,
        )
        return

    logger.info(
        "Options backfill complete: %s total rows in %.1f minutes",
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


def run_options_backfill(
    tickers: list[str],
    concurrency: int = 4,
    resume: bool = False,
    dry_run: bool = False,
    years: int | None = None,
    days: int | None = None,
) -> None:
    """Synchronous wrapper for the async options backfill."""
    asyncio.run(_run_async(tickers, concurrency, resume, dry_run, years, days))
