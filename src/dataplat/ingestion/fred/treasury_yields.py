"""FRED treasury yields backfill.

Fetches daily US Treasury constant-maturity yields from FRED and merges
them into the treasury_yields ClickHouse table (same schema as the
Polygon economy pipeline). Fills gaps that Polygon leaves NULL
(1M, 3M, 2Y, 30Y).

FRED series mapping:
  DGS1MO  → yield_1_month
  DGS3MO  → yield_3_month
  DGS1    → yield_1_year
  DGS2    → yield_2_year
  DGS5    → yield_5_year
  DGS10   → yield_10_year
  DGS30   → yield_30_year
"""

from __future__ import annotations

import logging
import time
from datetime import date

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES_MAP: dict[str, str] = {
    "DGS1MO": "yield_1_month",
    "DGS3MO": "yield_3_month",
    "DGS1":   "yield_1_year",
    "DGS2":   "yield_2_year",
    "DGS5":   "yield_5_year",
    "DGS10":  "yield_10_year",
    "DGS30":  "yield_30_year",
}

YIELD_COLUMNS = list(SERIES_MAP.values())


def _fetch_series(
    client: httpx.Client,
    series_id: str,
    start: str = "1962-01-01",
) -> list[dict[str, str]]:
    """Fetch all observations for a single FRED series."""
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
        "limit": "100000",
    }
    resp = client.get(FRED_BASE, params=params)
    resp.raise_for_status()
    return resp.json().get("observations", [])


def _fetch_all_yields(start: str = "1962-01-01") -> pl.DataFrame:
    """Fetch all 7 yield series and pivot into one wide DataFrame."""
    frames: list[pl.DataFrame] = []

    with httpx.Client(timeout=60.0) as client:
        for series_id, col_name in SERIES_MAP.items():
            obs = _fetch_series(client, series_id, start)
            if not obs:
                logger.warning("FRED %s: no observations", series_id)
                continue

            # FRED returns {date, value} — value is string, "." means missing
            rows = []
            for o in obs:
                val_str = o.get("value", ".")
                if val_str == ".":
                    continue
                try:
                    rows.append({"date": o["date"], col_name: float(val_str)})
                except (ValueError, KeyError):
                    continue

            if rows:
                df = pl.DataFrame(rows).with_columns(
                    pl.col("date").str.to_date("%Y-%m-%d")
                )
                frames.append(df)
                logger.info("FRED %s → %s: %d observations", series_id, col_name, len(rows))

            # FRED rate limit: 120 req/min
            time.sleep(0.6)

    if not frames:
        return pl.DataFrame()

    # Join all series on date
    result = frames[0]
    for f in frames[1:]:
        result = result.join(f, on="date", how="full", coalesce=True)

    # Ensure all columns exist
    for col in YIELD_COLUMNS:
        if col not in result.columns:
            result = result.with_columns(pl.lit(None).cast(pl.Float64).alias(col))

    # Select in schema order, sort by date
    return (
        result
        .select(["date"] + YIELD_COLUMNS)
        .sort("date")
    )


def run_treasury_yields_backfill(start: str = "1962-01-01") -> None:
    """Backfill treasury yields from FRED into ClickHouse."""
    if not settings.fred_api_key:
        raise RuntimeError(
            "FRED_API_KEY must be set in .env — "
            "get one free at https://fred.stlouisfed.org/docs/api/api_key.html"
        )

    ensure_schema()

    logger.info("FRED treasury yields backfill starting (from %s)", start)
    t0 = time.monotonic()

    df = _fetch_all_yields(start)
    if df.is_empty():
        logger.warning("No yield data fetched from FRED")
        return

    # Add source column
    df = df.with_columns(pl.lit("fred").alias("source"))

    ch = get_client()
    ch.insert_arrow("treasury_yields", df.to_arrow())

    elapsed = time.monotonic() - t0
    logger.info(
        "FRED treasury yields complete: %s rows, %s–%s, %.1f seconds",
        f"{len(df):,}",
        df["date"].min(),
        df["date"].max(),
        elapsed,
    )
