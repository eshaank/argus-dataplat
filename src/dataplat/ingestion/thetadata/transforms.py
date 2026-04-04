"""ThetaData v3 NDJSON → Polars transforms for option_chains table.

Parses NDJSON responses from the v3 EOD greeks and open interest
endpoints, joins them, and produces a DataFrame matching the
option_chains ClickHouse schema.
"""

from __future__ import annotations

import io
import logging
from datetime import date

import polars as pl

logger = logging.getLogger(__name__)

# Fields we extract from the greeks NDJSON (everything option_chains needs)
_GREEKS_COLUMNS = {
    # Contract identity
    "symbol": pl.Utf8,
    "expiration": pl.Utf8,
    "strike": pl.Float64,
    "right": pl.Utf8,
    # OHLCV
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
    "count": pl.Int64,
    # Quote
    "bid": pl.Float64,
    "ask": pl.Float64,
    "bid_size": pl.Int64,
    "ask_size": pl.Int64,
    # Greeks — 1st order
    "delta": pl.Float64,
    "gamma": pl.Float64,
    "theta": pl.Float64,
    "vega": pl.Float64,
    "rho": pl.Float64,
    # Greeks — 2nd order
    "vanna": pl.Float64,
    "charm": pl.Float64,
    "vomma": pl.Float64,
    "veta": pl.Float64,
    "epsilon": pl.Float64,
    "lambda": pl.Float64,
    # Greeks — 3rd order
    "vera": pl.Float64,
    "speed": pl.Float64,
    "zomma": pl.Float64,
    "color": pl.Float64,
    "ultima": pl.Float64,
    # Volatility
    "implied_vol": pl.Float64,
    "iv_error": pl.Float64,
    # Context
    "underlying_price": pl.Float64,
}


def parse_greeks_ndjson(ndjson_text: str, snapshot_date: date) -> pl.DataFrame:
    """Parse NDJSON from /v3/option/history/greeks/eod into a Polars DataFrame.

    Each line is a flat JSON object with all fields. Returns a DataFrame
    with columns matching the option_chains ClickHouse schema.
    """
    if not ndjson_text.strip():
        return pl.DataFrame()

    try:
        df = pl.read_ndjson(io.StringIO(ndjson_text))
    except Exception as exc:
        logger.error("Failed to parse greeks NDJSON: %s", exc)
        return pl.DataFrame()

    if df.is_empty():
        return df

    # Select only columns we need (response may have extras)
    available = [c for c in _GREEKS_COLUMNS if c in df.columns]
    df = df.select(available)

    # Rename for ClickHouse schema
    df = df.rename({
        "symbol": "underlying",
        "right": "put_call",
        "count": "trade_count",
    })

    # Map put_call: CALL/call → call, PUT/put → put
    df = df.with_columns(
        pl.col("put_call").str.to_lowercase().alias("put_call"),
    )

    # Parse expiration string → Date
    df = df.with_columns(
        pl.col("expiration").str.to_date("%Y-%m-%d").alias("expiration"),
    )

    # Add metadata columns
    df = df.with_columns(
        pl.lit(snapshot_date).alias("snapshot_date"),
        pl.lit("thetadata").alias("source"),
    )

    # Cast integer columns
    int_cols = {"volume": pl.UInt32, "trade_count": pl.UInt32, "bid_size": pl.UInt32, "ask_size": pl.UInt32}
    for col, dtype in int_cols.items():
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(dtype, strict=False).fill_null(0))

    return df


def parse_oi_ndjson(ndjson_text: str) -> pl.DataFrame:
    """Parse NDJSON from /v3/option/history/open_interest.

    Returns a DataFrame with (underlying, expiration, strike, put_call, open_interest).
    """
    if not ndjson_text.strip():
        return pl.DataFrame()

    try:
        df = pl.read_ndjson(io.StringIO(ndjson_text))
    except Exception as exc:
        logger.error("Failed to parse OI NDJSON: %s", exc)
        return pl.DataFrame()

    if df.is_empty():
        return df

    # Select join key + OI
    cols = ["symbol", "expiration", "strike", "right", "open_interest"]
    available = [c for c in cols if c in df.columns]
    df = df.select(available)

    df = df.rename({"symbol": "underlying", "right": "put_call"})
    df = df.with_columns(
        pl.col("put_call").str.to_lowercase(),
        pl.col("expiration").str.to_date("%Y-%m-%d"),
        pl.col("open_interest").cast(pl.UInt32, strict=False).fill_null(0),
    )

    return df


def merge_greeks_and_oi(greeks_df: pl.DataFrame, oi_df: pl.DataFrame) -> pl.DataFrame:
    """Left join greeks onto OI by contract identity.

    Missing OI → 0. Returns the merged DataFrame ready for ClickHouse.
    """
    if greeks_df.is_empty():
        return greeks_df

    if oi_df.is_empty():
        # No OI data — add column with zeros
        return greeks_df.with_columns(pl.lit(0).cast(pl.UInt32).alias("open_interest"))

    join_keys = ["underlying", "expiration", "strike", "put_call"]
    merged = greeks_df.join(oi_df, on=join_keys, how="left")

    # Fill missing OI with 0
    if "open_interest" in merged.columns:
        merged = merged.with_columns(
            pl.col("open_interest").fill_null(0),
        )
    else:
        merged = merged.with_columns(pl.lit(0).cast(pl.UInt32).alias("open_interest"))

    return merged


def validate_options(df: pl.DataFrame) -> pl.DataFrame:
    """Validate option chain data before ClickHouse insertion.

    1. Drop rows with null required greeks (delta, gamma, theta, vega, implied_vol)
    2. Drop rows with null bid/ask
    3. Deduplicate on (underlying, expiration, strike, put_call)
    """
    if df.is_empty():
        return df

    initial = len(df)

    # 1. Required greeks must not be null
    required = ["delta", "gamma", "theta", "vega", "implied_vol", "bid", "ask"]
    present = [c for c in required if c in df.columns]
    df = df.drop_nulls(subset=present)
    after_nulls = len(df)
    if after_nulls < initial:
        logger.warning("Dropped %d rows with null required fields", initial - after_nulls)

    # 2. Deduplicate (shouldn't happen with EOD data, but safety net)
    dedup_keys = ["underlying", "expiration", "strike", "put_call"]
    present_keys = [c for c in dedup_keys if c in df.columns]
    df = df.unique(subset=present_keys, keep="last")
    after_dedup = len(df)
    if after_dedup < after_nulls:
        logger.warning("Dropped %d duplicate rows", after_nulls - after_dedup)

    return df
