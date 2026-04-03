"""OHLCV data validation — schema enforcement, sanity checks, dedup.

All functions take and return Polars DataFrames.  Invalid rows are
dropped with a warning, never silently passed through.
"""

from __future__ import annotations

import logging

import polars as pl

logger = logging.getLogger(__name__)


def validate_ohlcv(df: pl.DataFrame) -> pl.DataFrame:
    """Run all validations on an OHLCV DataFrame.

    1. Drop rows with nulls in required columns (OHLC, volume)
    2. Enforce high >= low, high >= open, high >= close
    3. Enforce volume >= 0
    4. Deduplicate on (ticker, timestamp)
    """
    if df.is_empty():
        return df

    initial = len(df)

    # 1. Required columns must not be null
    required = ["ticker", "timestamp", "open", "high", "low", "close", "volume"]
    df = df.drop_nulls(subset=[c for c in required if c in df.columns])
    after_nulls = len(df)
    if after_nulls < initial:
        logger.warning("Dropped %d rows with null required fields", initial - after_nulls)

    # 2. OHLC sanity: high must be the highest
    df = df.filter(
        (pl.col("high") >= pl.col("low"))
        & (pl.col("high") >= pl.col("open"))
        & (pl.col("high") >= pl.col("close"))
        & (pl.col("low") <= pl.col("open"))
        & (pl.col("low") <= pl.col("close"))
    )
    after_ohlc = len(df)
    if after_ohlc < after_nulls:
        logger.warning("Dropped %d rows failing OHLC sanity checks", after_nulls - after_ohlc)

    # 3. Volume >= 0
    df = df.filter(pl.col("volume") >= 0)
    after_vol = len(df)
    if after_vol < after_ohlc:
        logger.warning("Dropped %d rows with negative volume", after_ohlc - after_vol)

    # 4. Deduplicate
    df = df.unique(subset=["ticker", "timestamp"], keep="last")
    after_dedup = len(df)
    if after_dedup < after_vol:
        logger.warning("Dropped %d duplicate (ticker, timestamp) rows", after_vol - after_dedup)

    return df
