"""Generic FRED backfill runner — reads the registry, fetches, inserts.

Usage:
    run_fred_backfill()                          # All 8 tables
    run_fred_backfill(tables=["rates"])           # Single table
    run_fred_backfill(tables=["rates", "macro_daily"])  # Multiple tables
"""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.fred.client import fetch_and_pivot
from dataplat.ingestion.fred.registry import ALL_TABLES, TABLE_BY_NAME, TableConfig

logger = logging.getLogger(__name__)


def _backfill_table(client: httpx.Client, config: TableConfig, ch) -> int:
    """Fetch all series for one table and insert into ClickHouse.

    Returns number of rows inserted.
    """
    df = fetch_and_pivot(client, config.series, config.start)
    if df.is_empty():
        logger.warning("%s: no data fetched", config.table)
        return 0

    df = df.with_columns(pl.lit("fred").alias("source"))
    ch.insert_arrow(config.table, df.to_arrow())

    logger.info(
        "%s: %s rows (%s – %s)",
        config.table,
        f"{len(df):,}",
        df["date"].min(),
        df["date"].max(),
    )
    return len(df)


def run_fred_backfill(tables: list[str] | None = None) -> None:
    """Backfill FRED economic data into ClickHouse.

    Args:
        tables: List of table names to backfill. None = all tables.
    """
    if not settings.fred_api_key:
        raise RuntimeError(
            "FRED_API_KEY must be set in .env — "
            "get one free at https://fred.stlouisfed.org/docs/api/api_key.html"
        )

    # Resolve which tables to backfill
    if tables:
        configs: list[TableConfig] = []
        for name in tables:
            if name not in TABLE_BY_NAME:
                available = ", ".join(TABLE_BY_NAME.keys())
                raise ValueError(f"Unknown table '{name}'. Available: {available}")
            configs.append(TABLE_BY_NAME[name])
    else:
        configs = list(ALL_TABLES)

    ensure_schema()
    ch = get_client()
    t0 = time.monotonic()

    total_series = sum(len(c.series) for c in configs)
    logger.info(
        "FRED backfill: %d tables, %d series",
        len(configs), total_series,
    )

    total_rows = 0
    failures: list[str] = []

    with httpx.Client(timeout=60.0) as client:
        for config in configs:
            try:
                rows = _backfill_table(client, config, ch)
                total_rows += rows
            except Exception as exc:
                logger.error("%s: FAILED — %s", config.table, exc)
                failures.append(config.table)

    elapsed = time.monotonic() - t0
    logger.info(
        "FRED backfill complete: %s rows across %d tables in %.1f seconds",
        f"{total_rows:,}", len(configs), elapsed,
    )
    if failures:
        logger.warning("Failed tables: %s", ", ".join(failures))
