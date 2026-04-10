"""EIA backfill runner — reads the registry, fetches, inserts.

Supports both backfill (historical) and current-pull (recent) modes.
The only difference is the date range passed to the fetch.

Usage:
    run_eia_backfill()                                           # All tables, full history
    run_eia_backfill(tables=["eia_petroleum_weekly"])             # Single table
    run_eia_backfill(start="2024-01-01", end="2024-12-31")       # Date range
    run_eia_backfill(start="2025-04-01")                         # Pull recent data
"""

from __future__ import annotations

import logging
import time

import httpx
import polars as pl

from dataplat.config import settings
from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema
from dataplat.ingestion.eia.client import fetch_and_pivot
from dataplat.ingestion.eia.registry import ALL_TABLES, TABLE_BY_NAME, EIATableConfig

logger = logging.getLogger(__name__)


def _backfill_table(
    client: httpx.Client,
    config: EIATableConfig,
    ch,
    start: str | None = None,
    end: str | None = None,
) -> int:
    """Fetch all series for one table and insert into ClickHouse.

    Args:
        client: httpx client instance.
        config: EIA table configuration.
        ch: ClickHouse client.
        start: Override start date. None = use config default.
        end: Override end date. None = latest available.

    Returns:
        Number of rows inserted.
    """
    effective_start = start or config.start

    df = fetch_and_pivot(client, config.series, effective_start, end)
    if df.is_empty():
        logger.warning("%s: no data fetched", config.table)
        return 0

    df = df.with_columns(
        pl.lit("eia").alias("source"),
        pl.lit(config.update_frequency).alias("update_frequency"),
    )
    ch.insert_arrow(config.table, df.to_arrow())

    logger.info(
        "%s: %s rows (%s – %s)",
        config.table,
        f"{len(df):,}",
        df["date"].min(),
        df["date"].max(),
    )
    return len(df)


def run_eia_backfill(
    tables: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> None:
    """Fetch EIA data and insert into ClickHouse.

    Works for both historical backfill and pulling current data —
    just set start/end to control the date range.

    Args:
        tables: List of table names to backfill. None = all tables.
        start: Override start date (YYYY-MM-DD). None = table default.
        end: Override end date (YYYY-MM-DD). None = latest available.
    """
    if not settings.eia_api_key:
        raise RuntimeError(
            "EIA_API_KEY must be set in .env — "
            "get one free at https://www.eia.gov/opendata/register.php"
        )

    # Resolve which tables to fetch
    if tables:
        configs: list[EIATableConfig] = []
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
        "EIA: %d tables, %d series (start=%s, end=%s)",
        len(configs), total_series, start or "full history", end or "latest",
    )

    total_rows = 0
    failures: list[str] = []

    with httpx.Client(timeout=60.0) as client:
        for i, config in enumerate(configs, 1):
            logger.info(
                "[%d/%d] %s (%d series)",
                i, len(configs), config.table, len(config.series),
            )
            try:
                rows = _backfill_table(client, config, ch, start, end)
                total_rows += rows
            except Exception as exc:
                logger.error("%s: FAILED — %s", config.table, exc)
                failures.append(config.table)

    elapsed = time.monotonic() - t0
    logger.info(
        "EIA complete: %s rows across %d tables in %.1fs",
        f"{total_rows:,}", len(configs), elapsed,
    )
    if failures:
        logger.warning("Failed tables: %s", ", ".join(failures))
