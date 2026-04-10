"""Yahoo Finance commodity futures — full OHLCV.

Fetches daily OHLCV for all major commodity futures via yfinance.
Covers precious metals, energy, industrial metals, grains, softs, livestock.

Rate limits: ~2,000 req/hour, IP-based. We fetch all tickers in one batch
call via yfinance's multi-ticker support, so this is very lightweight.

Data is ~15 min delayed (not real-time).

Usage:
    run_yfinance_commodities()                                  # Full history
    run_yfinance_commodities(start="2024-01-01")                # From date
    run_yfinance_commodities(start="2025-04-01", end="2025-04-07")  # Range
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


def _fetch_futures_ohlcv(
    start: str | None = None,
    end: str | None = None,
) -> pl.DataFrame:
    """Fetch daily OHLCV for all commodity futures.

    Returns a tall DataFrame with columns: ticker, date, open, high, low, close, volume.
    """
    import yfinance as yf

    tickers = list(FUTURES_MAP.keys())
    effective_start = start or "2000-01-01"
    # yfinance end is exclusive, add 1 day
    effective_end = end or (date.today() + timedelta(days=1)).isoformat()

    logger.info(
        "yfinance: fetching %d commodity futures (%s – %s)",
        len(tickers), effective_start, effective_end,
    )

    # Download all at once — single HTTP batch
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
    # Reshape into tall format: one row per (ticker, date)
    all_rows: list[dict] = []
    dates = data.index.tolist()

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
            for i, dt in enumerate(dates):
                close_val = ticker_data["Close"].iloc[i]
                # Skip NaN rows
                if close_val != close_val:
                    continue

                all_rows.append({
                    "ticker": yf_ticker,
                    "name": clean_name,
                    "date": dt.strftime("%Y-%m-%d"),
                    "open": float(ticker_data["Open"].iloc[i]) if ticker_data["Open"].iloc[i] == ticker_data["Open"].iloc[i] else 0.0,
                    "high": float(ticker_data["High"].iloc[i]) if ticker_data["High"].iloc[i] == ticker_data["High"].iloc[i] else 0.0,
                    "low": float(ticker_data["Low"].iloc[i]) if ticker_data["Low"].iloc[i] == ticker_data["Low"].iloc[i] else 0.0,
                    "close": float(close_val),
                    "volume": int(ticker_data["Volume"].iloc[i]) if ticker_data["Volume"] is not None and ticker_data["Volume"].iloc[i] == ticker_data["Volume"].iloc[i] else 0,
                })
                row_count += 1

            logger.info("  %s (%s): %s rows", clean_name, yf_ticker, f"{row_count:,}")

        except Exception as exc:
            logger.error("  %s (%s): FAILED — %s", clean_name, yf_ticker, exc)

    if not all_rows:
        return pl.DataFrame()

    df = pl.DataFrame(all_rows).with_columns(
        pl.col("date").str.to_date("%Y-%m-%d"),
    )

    logger.info("yfinance: %s total rows across %d commodities", f"{len(df):,}", df["ticker"].n_unique())
    return df


def run_yfinance_commodities(
    start: str | None = None,
    end: str | None = None,
) -> None:
    """Fetch commodity futures OHLCV from Yahoo Finance and insert into ClickHouse.

    Works for both historical backfill and pulling current data —
    just set start/end to control the date range.

    Args:
        start: Start date (YYYY-MM-DD). None = 2000-01-01.
        end: End date (YYYY-MM-DD). None = today.
    """
    ensure_schema()
    ch = get_client()
    t0 = time.monotonic()

    df = _fetch_futures_ohlcv(start, end)
    if df.is_empty():
        logger.warning("yfinance: no data to insert")
        return

    df = df.with_columns(
        pl.lit("yfinance").alias("source"),
        pl.lit("daily").alias("update_frequency"),
    )
    ch.insert_arrow("commodities_ohlcv", df.to_arrow())

    elapsed = time.monotonic() - t0
    logger.info(
        "yfinance: inserted %s rows (%s – %s) in %.1fs",
        f"{len(df):,}",
        df["date"].min(),
        df["date"].max(),
        elapsed,
    )
