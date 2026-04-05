"""Shared FRED API client — rate-limited, with retry and pivot logic.

FRED rate limit: 120 requests/minute. We use 0.6s delay between calls.
All series return JSON with {date, value} observations where "." = missing.
"""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.config import settings

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Delay between requests to stay under 120 req/min
_RATE_LIMIT_DELAY = 0.6


def fetch_series(
    client: httpx.Client,
    series_id: str,
    start: str = "1900-01-01",
) -> list[tuple[str, float]]:
    """Fetch all observations for a single FRED series.

    Returns list of (date_str, value) tuples, skipping "." missing values.
    Retries once on transient errors.
    """
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
        "limit": "100000",
    }

    for attempt in range(3):
        try:
            resp = client.get(FRED_BASE, params=params)
            resp.raise_for_status()
            break
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            if attempt < 2:
                wait = 2 ** attempt
                logger.warning(
                    "FRED %s attempt %d failed (%s), retrying in %ds",
                    series_id, attempt + 1, exc, wait,
                )
                time.sleep(wait)
            else:
                raise

    rows: list[tuple[str, float]] = []
    for o in resp.json().get("observations", []):
        val_str = o.get("value", ".")
        if val_str == ".":
            continue
        try:
            rows.append((o["date"], float(val_str)))
        except (ValueError, KeyError):
            continue

    return rows


def fetch_and_pivot(
    client: httpx.Client,
    series_map: dict[str, str],
    start: str = "1900-01-01",
) -> pl.DataFrame:
    """Fetch multiple FRED series and full-outer-join into one wide DataFrame.

    Args:
        client: httpx client instance
        series_map: {FRED_series_id: clickhouse_column_name}
        start: observation start date (YYYY-MM-DD)

    Returns:
        Wide DataFrame with 'date' + one column per series, sorted by date.
    """
    frames: list[pl.DataFrame] = []

    for series_id, col_name in series_map.items():
        obs = fetch_series(client, series_id, start)

        if not obs:
            logger.warning("FRED %s: no observations", series_id)
        else:
            df = pl.DataFrame(
                {"date": [r[0] for r in obs], col_name: [r[1] for r in obs]},
            ).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
            frames.append(df)
            logger.info("FRED %s → %s: %d observations", series_id, col_name, len(obs))

        time.sleep(_RATE_LIMIT_DELAY)

    if not frames:
        return pl.DataFrame()

    # Full outer join all series on date
    result = frames[0]
    for f in frames[1:]:
        result = result.join(f, on="date", how="full", coalesce=True)

    # Ensure all expected columns exist
    for col in series_map.values():
        if col not in result.columns:
            result = result.with_columns(pl.lit(None).cast(pl.Float64).alias(col))

    # Select in consistent order
    cols = ["date"] + list(series_map.values())
    return result.select(cols).sort("date")
