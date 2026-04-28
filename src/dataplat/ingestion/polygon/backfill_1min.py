"""ONE-OFF Polygon 1-minute OHLCV backfill.

Fetches ~4 years of 1-min bars from Polygon's /v2/aggs endpoint,
transforms via Polars, and bulk-inserts into ClickHouse.

This pipeline is designed to run once to seed the ohlcv table.
After that, Schwab is the sole ongoing data source.

Resume mode (--resume):
    Uses a local JSON progress file (``.backfill-progress/polygon_1min_{N}m.json``)
    to skip already-completed months. A month is "done" if it was previously:

    - ``ok``: data fetched and inserted into ClickHouse
    - ``empty``: Polygon returned no results (403/NOT_AUTHORIZED or empty results)
    - ``failed``: exhausted all retries — skipped permanently

    This avoids re-fetching ~157K pre-lookback months that return 403 on every
    resume run, and prevents permanently-failing months (e.g. delisted MIR) from
    being retried endlessly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

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
PROGRESS_DIR = Path(__file__).resolve().parents[4] / ".backfill-progress"

# Retry config for transient failures (disconnects, 429s, 5xx)
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 1.0  # seconds, doubles each attempt
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Progress file helpers
# ---------------------------------------------------------------------------

def _progress_file(months: int) -> Path:
    """Return the path to the progress file for a given month count."""
    PROGRESS_DIR.mkdir(exist_ok=True)
    return PROGRESS_DIR / f"polygon_1min_{months}m.json"


def _load_progress(months: int) -> dict[str, str]:
    """Load the progress file mapping ``'TICKER|YYYY-MM-DD'`` → status.

    Status is one of: ``'ok'``, ``'empty'``, ``'failed'``.
    """
    path = _progress_file(months)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.warning("Could not read progress file (%s) — starting fresh", exc)
        return {}


def _save_progress(months: int, progress: dict[str, str]) -> None:
    """Persist progress dict to disk."""
    path = _progress_file(months)
    path.write_text(json.dumps(progress, separators=(",", ":")))


def _get_done_months(months: int) -> set[tuple[str, str]]:
    """Return (ticker, from_date) pairs that are already done.

    A pair is done if it was previously recorded as 'ok' (data inserted),
    'empty' (no data available, e.g. 403/NOT_AUTHORIZED), or 'failed'
    (exhausted retries — skipped permanently).
    """
    progress = _load_progress(months)
    done: set[tuple[str, str]] = set()
    for key, status in progress.items():
        if status in ("ok", "empty", "failed"):
            parts = key.split("|", 1)
            if len(parts) == 2:
                done.add((parts[0], parts[1]))
    return done


# ---------------------------------------------------------------------------
# Date range generation
# ---------------------------------------------------------------------------

def _month_ranges(months: int) -> list[tuple[str, str]]:
    """Generate (from_date, to_date) pairs going back N months from today.

    Each range covers approximately 2 months (one Polygon API call).
    The ``from_date`` is always the first day of a month.
    """
    end = date.today()
    ranges: list[tuple[str, str]] = []
    for _ in range(months):
        start = (end.replace(day=1) - timedelta(days=1)).replace(day=1)
        ranges.append((start.isoformat(), end.isoformat()))
        end = start - timedelta(days=1)
    ranges.reverse()
    return ranges


# ---------------------------------------------------------------------------
# Fetch with retry
# ---------------------------------------------------------------------------

async def _fetch_month(
    client: httpx.AsyncClient,
    ticker: str,
    from_date: str,
    to_date: str,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Fetch 1-min bars for one ticker-month with retry on transient errors.

    Returns a list of result dicts on success, an empty list for 403/empty/failed.
    Never raises — always returns a list so callers can handle failures gracefully.
    """
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

            if resp.status_code >= 400:
                # Non-retryable HTTP error (e.g. 404, 422) — log and skip
                logger.warning(
                    "%s %s→%s: HTTP %d — skipping",
                    ticker, from_date, to_date, resp.status_code,
                )
                return []

            data = resp.json()

            if data.get("status") == "NOT_AUTHORIZED":
                return []

            return data.get("results", [])

        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "%s %s→%s: %s, retry %d/%d in %.1fs",
                    ticker, from_date, to_date, type(exc).__name__, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
            else:
                # Exhausted retries — return empty so caller can mark as 'failed'.
                # Never raise here: we want graceful degradation, not crash.
                logger.error(
                    "%s %s→%s: %s — giving up after %d retries",
                    ticker, from_date, to_date, exc, _MAX_RETRIES,
                )
                return []

    # Should be unreachable, but just in case
    logger.error("%s %s→%s: unexpected exit from retry loop", ticker, from_date, to_date)
    return []


# ---------------------------------------------------------------------------
# Per-ticker backfill (with progress tracking)
# ---------------------------------------------------------------------------

async def _backfill_ticker(
    client: httpx.AsyncClient,
    ticker: str,
    ranges: list[tuple[str, str]],
    semaphore: asyncio.Semaphore,
    done_months: set[tuple[str, str]] | None = None,
    progress: dict[str, str] | None = None,
    progress_months: int = 0,
) -> int:
    """Backfill all months for a single ticker. Returns total rows inserted.

    Args:
        done_months: Set of (ticker, from_date) pairs already completed.
        progress: Live progress dict to record status after each month.
        progress_months: Month count key for progress file saves.
    """
    ch = get_client()
    total = 0

    # Filter out already-done ranges, but ALWAYS re-fetch the most recent range
    # (it covers the current month which is incomplete — new bars arrive each day)
    last_from = ranges[-1][0]  # from_date of the most recent range
    if done_months is not None:
        active_ranges = [(fr, to) for fr, to in ranges if (ticker, fr) not in done_months]
        # Even if the last range was marked 'ok', re-fetch it — it's the current month
        if active_ranges or (ticker, last_from) in done_months:
            # Check if the last range was skipped but shouldn't be
            last_range = ranges[-1]
            if (ticker, last_from) in done_months and last_range not in active_ranges:
                active_ranges.append(last_range)
        skipped = len(ranges) - len(active_ranges)
        if skipped:
            logger.debug("%s: resume — skipping %d/%d already-done months (re-fetching current month)", ticker, skipped, len(ranges))
        if not active_ranges:
            return 0  # fully done
        ranges = active_ranges

    tasks = [_fetch_month(client, ticker, fr, to, semaphore) for fr, to in ranges]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    progress_dirty = False

    for i, result in enumerate(results):
        fr, to = ranges[i]
        key = f"{ticker}|{fr}"

        if isinstance(result, Exception):
            # Exhausted retries — record as 'failed' so resume skips it permanently
            logger.error("%s %s→%s: failed after all retries — marking as done (failed)", ticker, fr, to)
            if progress is not None:
                progress[key] = "failed"
                progress_dirty = True
            continue

        if not result:
            # Empty/403/NOT_AUTHORIZED — no data available, record as 'empty'
            if progress is not None and key not in progress:
                progress[key] = "empty"
                progress_dirty = True
            continue

        df = transform_polygon_aggs(result, ticker)
        df = validate_ohlcv(df)

        if df.is_empty():
            # Data came back but was all invalid — still counts as fetched
            if progress is not None:
                progress[key] = "empty"
                progress_dirty = True
            continue

        try:
            ch.insert_arrow("ohlcv", df.to_arrow())
            total += len(df)
            if progress is not None:
                progress[key] = "ok"
                progress_dirty = True
        except Exception as exc:
            logger.error("%s insert failed for %s→%s: %s", ticker, fr, to, exc)
            # Insert failure — don't mark as done; we want to retry on resume

    # Persist progress after each ticker
    if progress_dirty and progress_months > 0:
        _save_progress(progress_months, progress)

    return total


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------

async def _run_async(tickers: list[str], months: int, concurrency: int, resume: bool = False) -> None:
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

    # Resume: load progress file and skip fully-done tickers
    done_months: set[tuple[str, str]] | None = None
    progress: dict[str, str] | None = None

    if resume:
        progress = _load_progress(months)
        done_months = _get_done_months(months)

        # A ticker needs work if ANY of its ranges is not in done_months.
        # (The current-month range was stripped from progress, so all tickers
        # that have data will need at least that one range re-fetched.)
        needs_work = [t for t in tickers if not all((t, fr) in done_months for fr, _ in ranges)]
        fully_done = len(tickers) - len(needs_work)

        skipped_pairs = sum(
            1 for t in tickers for fr, _ in ranges if (t, fr) in done_months
        )
        total_pairs = len(tickers) * len(ranges)

        logger.info(
            "Resume: %d/%d pairs done — skipping %d fully-done tickers, processing %d",
            skipped_pairs, total_pairs, fully_done, len(needs_work),
        )
        tickers = needs_work

    logger.info(
        "Polygon 1-min backfill: %d tickers × %d months, concurrency=%d",
        len(tickers), len(ranges), concurrency,
    )

    async def _process_ticker(client: httpx.AsyncClient, ticker: str) -> None:
        nonlocal completed, total_rows
        ticker_start = time.monotonic()
        rows = await _backfill_ticker(
            client, ticker, ranges, semaphore,
            done_months=done_months,
            progress=progress,
            progress_months=months if resume else 0,
        )
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


def run_polygon_backfill(
    tickers: list[str],
    months: int = 48,
    concurrency: int = 10,
    resume: bool = False,
) -> None:
    """Synchronous wrapper for the async backfill.

    Args:
        tickers: Ticker symbols to backfill.
        months: How many months of history to fetch.
        concurrency: Max simultaneous HTTP requests.
        resume: If True, skip (ticker, month) pairs already present in
                the progress file.
    """
    asyncio.run(_run_async(tickers, months, concurrency, resume))
