"""Transform raw API responses into clean OHLCV Polars DataFrames.

Handles both Polygon (1-min backfill) and Schwab (daily) response shapes,
producing a unified schema that matches the ClickHouse ``ohlcv`` table.
"""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl


def transform_polygon_aggs(results: list[dict], ticker: str) -> pl.DataFrame:
    """Transform Polygon /v2/aggs response ``results`` list.

    Polygon fields: v, vw, o, c, h, l, t, n
    """
    if not results:
        return pl.DataFrame()

    df = pl.DataFrame(results)

    df = df.select(
        pl.lit(ticker).alias("ticker"),
        (pl.col("t") * 1_000).cast(pl.Datetime("us", "UTC")).cast(pl.Datetime("ms", "UTC")).alias("timestamp"),
        pl.col("o").cast(pl.Float64).alias("open"),
        pl.col("h").cast(pl.Float64).alias("high"),
        pl.col("l").cast(pl.Float64).alias("low"),
        pl.col("c").cast(pl.Float64).alias("close"),
        pl.col("v").cast(pl.Int64).cast(pl.UInt64).alias("volume"),
        pl.col("vw").cast(pl.Float64).alias("vwap"),
        pl.col("n").cast(pl.UInt32).alias("transactions"),
        pl.lit("polygon_backfill").alias("source"),
        pl.lit(datetime.now(timezone.utc)).cast(pl.Datetime("ms", "UTC")).alias("ingested_at"),
    )

    return df


def transform_schwab_candles(candles: list[dict], ticker: str) -> pl.DataFrame:
    """Transform Schwab /pricehistory ``candles`` list.

    Schwab fields: open, high, low, close, volume, datetime (epoch ms)
    """
    if not candles:
        return pl.DataFrame()

    df = pl.DataFrame(candles)

    df = df.select(
        pl.lit(ticker).alias("ticker"),
        (pl.col("datetime") * 1_000).cast(pl.Datetime("us", "UTC")).cast(pl.Datetime("ms", "UTC")).alias("timestamp"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Int64).cast(pl.UInt64),
        pl.lit(None).cast(pl.Float64).alias("vwap"),
        pl.lit(None).cast(pl.UInt32).alias("transactions"),
        pl.lit("schwab").alias("source"),
        pl.lit(datetime.now(timezone.utc)).cast(pl.Datetime("ms", "UTC")).alias("ingested_at"),
    )

    return df
