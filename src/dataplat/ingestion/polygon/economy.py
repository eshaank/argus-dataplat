"""Polygon economy data backfill — treasury yields, inflation, labor market.

Each endpoint returns full history in one call. Total: 4 API calls.
"""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

POLYGON_BASE = "https://api.polygon.io"

# Endpoint → (table_name, field_mapping)
ECONOMY_ENDPOINTS = {
    "treasury-yields": {
        "table": "treasury_yields",
        "fields": {
            "date": pl.Date,
            "yield_1_month": pl.Float64,
            "yield_3_month": pl.Float64,
            "yield_1_year": pl.Float64,
            "yield_2_year": pl.Float64,
            "yield_5_year": pl.Float64,
            "yield_10_year": pl.Float64,
            "yield_30_year": pl.Float64,
        },
    },
    "inflation": {
        "table": "inflation",
        "fields": {
            "date": pl.Date,
            "cpi": pl.Float64,
            "cpi_core": pl.Float64,
            "pce": pl.Float64,
            "pce_core": pl.Float64,
            "pce_spending": pl.Float64,
        },
    },
    "inflation-expectations": {
        "table": "inflation_expectations",
        "fields": {
            "date": pl.Date,
            "market_5_year": pl.Float64,
            "market_10_year": pl.Float64,
            "forward_years_5_to_10": pl.Float64,
            "model_1_year": pl.Float64,
            "model_5_year": pl.Float64,
            "model_10_year": pl.Float64,
            "model_30_year": pl.Float64,
        },
    },
    "labor-market": {
        "table": "labor_market",
        "fields": {
            "date": pl.Date,
            "unemployment_rate": pl.Float64,
            "labor_force_participation_rate": pl.Float64,
            "avg_hourly_earnings": pl.Float64,
            "job_openings": pl.Float64,
        },
    },
}


def _fetch_economy_endpoint(client: httpx.Client, endpoint: str) -> list[dict]:
    """Fetch all records from a /fed/v1/ endpoint."""
    url = f"{POLYGON_BASE}/fed/v1/{endpoint}"
    params = {"apiKey": settings.polygon_api_key, "limit": "50000"}

    all_results: list[dict] = []
    while url:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))
        next_url = data.get("next_url")
        if next_url:
            url = f"{next_url}&apiKey={settings.polygon_api_key}"
            params = None
        else:
            url = None

    return all_results


def _transform_economy(results: list[dict], config: dict) -> pl.DataFrame:
    """Transform economy results into a typed Polars DataFrame."""
    if not results:
        return pl.DataFrame()

    fields = config["fields"]
    # Only keep fields that exist in the schema
    df = pl.DataFrame(results)

    # Select and cast columns that exist
    select_exprs = []
    for col_name, col_type in fields.items():
        if col_name in df.columns:
            select_exprs.append(pl.col(col_name).cast(col_type, strict=False))
        else:
            select_exprs.append(pl.lit(None).cast(col_type).alias(col_name))

    return df.select(select_exprs)


def run_economy_backfill() -> None:
    """Backfill all 4 economy endpoints into ClickHouse."""
    if not settings.polygon_api_key:
        raise RuntimeError("POLYGON_API_KEY must be set in .env")

    ensure_schema()
    ch = get_client()
    start_time = time.monotonic()

    logger.info("Economy backfill: %d endpoints", len(ECONOMY_ENDPOINTS))

    with httpx.Client(timeout=60.0) as client:
        for endpoint, config in ECONOMY_ENDPOINTS.items():
            try:
                results = _fetch_economy_endpoint(client, endpoint)
                if not results:
                    logger.warning("%s: no data returned", endpoint)
                    continue

                df = _transform_economy(results, config)
                if df.is_empty():
                    continue

                ch.insert_arrow(config["table"], df.to_arrow())
                logger.info("%s → %s: %s rows inserted", endpoint, config["table"], f"{len(df):,}")

            except Exception as exc:
                logger.error("%s: FAILED — %s", endpoint, exc)

    elapsed = time.monotonic() - start_time
    logger.info("Economy backfill complete in %.1f seconds", elapsed)
