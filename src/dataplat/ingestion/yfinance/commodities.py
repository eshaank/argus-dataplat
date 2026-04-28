"""Yahoo Finance commodity futures — full OHLCV.

Fetches daily and intraday OHLCV for all major commodity futures via yfinance.
Covers precious metals, energy, industrial metals, grains, softs, livestock.

Rate limits: ~2,000 req/hour, IP-based. We fetch all tickers in one batch
call via yfinance's multi-ticker support, so this is very lightweight.

Data is ~15 min delayed (not real-time).

Usage:
    run_yfinance_commodities()                                  # Daily, full history
    run_yfinance_commodities(interval='1d', start="2024-01-01") # Daily from date
    run_yfinance_commodities(interval='15m')                    # 15m bars, last 60 days
    run_yfinance_commodities(interval='1h')                     # 1h bars, last 730 days
    run_yfinance_commodities(interval='4h')                     # 4h bars, last 730 days
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)

# Suppress noisy yfinance/peewee logging
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("peewee").setLevel(logging.WARNING)

# Yahoo Finance futures ticker → human-readable name
FUTURES_MAP: dict[str, str] = {
    # Precious metals
    "GC=F":  "Gold",
    "SI=F":  "Silver",
    "PL=F":  "Platinum",
    "PA=F":  "Palladium",
    # Energy
    "CL=F":  "WTI Crude Oil",
    "BZ=F":  "Brent Crude Oil",
    "NG=F":  "Natural Gas",
    "HO=F":  "Heating Oil",
    "RB=F":  "Gasoline (RBOB)",
    # Industrial metals
    "HG=F":  "Copper",
    "ALI=F": "Aluminum",
    # Grains
    "ZW=F":  "Wheat",
    "ZC=F":  "Corn",
    "ZS=F":  "Soybeans",
    "ZL=F":  "Soybean Oil",
    "ZM=F":  "Soybean Meal",
    # Softs
    "KC=F":  "Coffee",
    "SB=F":  "Sugar",
    "CT=F":  "Cotton",
    "CC=F":  "Cocoa",
    "OJ=F":  "Orange Juice",
    "LBS=F": "Lumber",
    # Livestock
    "LE=F":  "Live Cattle",
    "HE=F":  "Lean Hogs",
    "GF=F":  "Feeder Cattle",
}


# Interval → table mapping
INTERVAL_TABLE_MAP: dict[str, str] = {
    "1d": "commodities_ohlcv",
    "15m": "commodities_ohlcv_15m",
    "1h": "commodities_ohlcv_1h",
    "4h": "commodities_ohlcv_4h",
}

# Interval → period for intraday (yfinance requires period, not start/end for intraday)
INTERVAL_PERIOD_MAP: dict[str, str] = {
    "15m": "60d",   # yfinance limit for 15m
    "1h": "730d",   # yfinance limit for 1h
    "4h": "730d",   # yfinance limit for 4h (uses 1h internally)
}


def _fetch_futures_ohlcv(
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
) -> pl.DataFrame:
    """Fetch OHLCV for all commodity futures.

    For daily: uses start/end date range.
    For intraday (15m, 1h, 4h): uses period param (yfinance limitation).

    Returns a tall DataFrame with columns:
    - Daily: ticker, name, date, open, high, low, close, volume
    - Intraday: ticker, name, timestamp, open, high, low, close, volume
    """
    import yfinance as yf

    tickers = list(FUTURES_MAP.keys())
    is_intraday = interval in INTERVAL_PERIOD_MAP

    if is_intraday:
        # yfinance requires period for intraday, not start/end
        period = INTERVAL_PERIOD_MAP[interval]
        yf_interval = "1h" if interval == "4h" else interval
        logger.info(
            "yfinance: fetching %d commodity futures (%s bars, period=%s)",
            len(tickers), interval, period,
        )
        data = yf.download(
            tickers,
            period=period,
            interval=yf_interval,
            auto_adjust=True,
            progress=False,
        )
    else:
        effective_start = start or "2000-01-01"
        # yfinance end is exclusive, add 1 day
        effective_end = end or (date.today() + timedelta(days=1)).isoformat()
        logger.info(
            "yfinance: fetching %d commodity futures (%s – %s)",
            len(tickers), effective_start, effective_end,
        )
        data = yf.download(
            tickers,
            start=effective_start,
            end=effective_end,
            interval="1d",
            auto_adjust=True,
            progress=False,
        )

    if data.empty:
        logger.warning("yfinance: no data returned")
        return pl.DataFrame()

    # yfinance returns MultiIndex columns (Price, Ticker) for multi-ticker
    # Reshape into tall format: one row per (ticker, date/timestamp)
    all_rows: list[dict] = []
    timestamps = data.index.tolist()
    time_col = "timestamp" if is_intraday else "date"

    for yf_ticker, clean_name in FUTURES_MAP.items():
        try:
            ticker_data = {
                "Open": data["Open"][yf_ticker] if yf_ticker in data["Open"].columns else None,
                "High": data["High"][yf_ticker] if yf_ticker in data["High"].columns else None,
                "Low": data["Low"][yf_ticker] if yf_ticker in data["Low"].columns else None,
                "Close": data["Close"][yf_ticker] if yf_ticker in data["Close"].columns else None,
                "Volume": data["Volume"][yf_ticker] if yf_ticker in data["Volume"].columns else None,
            }

            if ticker_data["Close"] is None:
                logger.warning("  %s (%s): not in response, skipping", clean_name, yf_ticker)
                continue

            row_count = 0
            for i, dt in enumerate(timestamps):
                close_val = ticker_data["Close"].iloc[i]
                # Skip NaN rows
                if close_val != close_val:
                    continue

                row = {
                    "ticker": yf_ticker,
                    "name": clean_name,
                    "open": float(ticker_data["Open"].iloc[i]) if ticker_data["Open"].iloc[i] == ticker_data["Open"].iloc[i] else 0.0,
                    "high": float(ticker_data["High"].iloc[i]) if ticker_data["High"].iloc[i] == ticker_data["High"].iloc[i] else 0.0,
                    "low": float(ticker_data["Low"].iloc[i]) if ticker_data["Low"].iloc[i] == ticker_data["Low"].iloc[i] else 0.0,
                    "close": float(close_val),
                    "volume": int(ticker_data["Volume"].iloc[i]) if ticker_data["Volume"] is not None and ticker_data["Volume"].iloc[i] == ticker_data["Volume"].iloc[i] else 0,
                }

                if is_intraday:
                    # For intraday: store as datetime string (will be parsed to DateTime)
                    row["timestamp"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # For daily: store as date string
                    row["date"] = dt.strftime("%Y-%m-%d")

                all_rows.append(row)
                row_count += 1

            logger.info("  %s (%s): %s rows", clean_name, yf_ticker, f"{row_count:,}")

        except Exception as exc:
            logger.error("  %s (%s): FAILED — %s", clean_name, yf_ticker, exc)

    if not all_rows:
        return pl.DataFrame()

    df = pl.DataFrame(all_rows)

    if is_intraday:
        # For 4h interval, aggregate 1h bars into 4h
        if interval == "4h":
            df = df.with_columns(
                pl.col("timestamp").str.to_datetime("%Y-%m-%d %H:%M:%S"),
            )
            df = (
                df.group_by(
                    "ticker",
                    "name",
                    pl.col("timestamp").dt.truncate("4h").alias("timestamp"),
                )
                .agg(
                    pl.col("open").first(),
                    pl.col("high").max(),
                    pl.col("low").min(),
                    pl.col("close").last(),
                    pl.col("volume").sum(),
                )
                .sort("ticker", "timestamp")
            )
        else:
            df = df.with_columns(
                pl.col("timestamp").str.to_datetime("%Y-%m-%d %H:%M:%S"),
            )
    else:
        df = df.with_columns(
            pl.col("date").str.to_date("%Y-%m-%d"),
        )

    logger.info("yfinance: %s total rows across %d commodities", f"{len(df):,}", df["ticker"].n_unique())
    return df


def run_yfinance_commodities(
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> None:
    """Fetch commodity futures OHLCV from Yahoo Finance and insert into ClickHouse.

    Works for both historical backfill and pulling current data.
    For daily: uses start/end to control date range.
    For intraday: uses yfinance period limits (15m=60d, 1h/4h=730d).

    Args:
        interval: Bar interval ('1d', '15m', '1h', '4h'). Default '1d'.
        start: Start date (YYYY-MM-DD). Only for daily. None = 2000-01-01.
        end: End date (YYYY-MM-DD). Only for daily. None = today.
    """
    if interval not in INTERVAL_TABLE_MAP:
        raise ValueError(f"Invalid interval '{interval}'. Valid: {list(INTERVAL_TABLE_MAP.keys())}")

    ensure_schema()
    ch = get_client()
    t0 = time.monotonic()

    df = _fetch_futures_ohlcv(start, end, interval)
    if df.is_empty():
        logger.warning("yfinance: no data to insert")
        return

    table = INTERVAL_TABLE_MAP[interval]
    is_intraday = interval in INTERVAL_PERIOD_MAP
    time_col = "timestamp" if is_intraday else "date"
    update_freq = interval if is_intraday else "daily"

    df = df.with_columns(
        pl.lit("yfinance").alias("source"),
        pl.lit(update_freq).alias("update_frequency"),
    )
    ch.insert_arrow(table, df.to_arrow())

    elapsed = time.monotonic() - t0
    logger.info(
        "yfinance: inserted %s rows into %s (%s – %s) in %.1fs",
        f"{len(df):,}",
        table,
        df[time_col].min(),
        df[time_col].max(),
        elapsed,
    )
