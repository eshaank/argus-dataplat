"""Zweig Breadth Thrust (ZBT) compute pipeline.

Reads NYSE daily closes from ohlcv_daily, computes breadth ratio + 10-day EMA,
detects ZBT signals, and writes results to the zbt_breadth table.

ZBT signal fires when 10-day EMA of breadth ratio:
  1. Dips below 0.40 (oversold)
  2. Surges above 0.615 within 10 trading days

Run: just zbt
"""

from __future__ import annotations

import logging
import time

import polars as pl

from dataplat.db.client import get_client
from dataplat.db.migrate import ensure_schema

logger = logging.getLogger(__name__)

OVERSOLD_THRESHOLD = 0.40
THRUST_THRESHOLD = 0.615
WINDOW_DAYS = 10
EMA_SPAN = 10


def _fetch_nyse_daily() -> pl.DataFrame:
    """Fetch daily closes for NYSE tickers from ohlcv_daily."""
    ch = get_client()
    result = ch.query(
        """
        SELECT d.ticker, d.day, d.close
        FROM ohlcv_daily d
        INNER JOIN universe u ON d.ticker = u.ticker
        WHERE u.exchange IN ('NYSE', 'NYSE American')
          AND d.close > 0
        ORDER BY d.ticker, d.day
        """
    )
    if not result.result_rows:
        return pl.DataFrame()

    return pl.DataFrame(
        {
            "ticker": [r[0] for r in result.result_rows],
            "day": [r[1] for r in result.result_rows],
            "close": [r[2] for r in result.result_rows],
        }
    )


def _compute_breadth(daily: pl.DataFrame) -> pl.DataFrame:
    """Compute daily advance/decline breadth ratio from ticker closes."""
    daily = daily.sort(["ticker", "day"])
    daily = daily.with_columns(
        pl.col("close").shift(1).over("ticker").alias("prev_close")
    )
    daily = daily.filter(pl.col("prev_close").is_not_null())

    daily = daily.with_columns(
        (pl.col("close") > pl.col("prev_close")).alias("is_advancing"),
        (pl.col("close") < pl.col("prev_close")).alias("is_declining"),
    )

    breadth = daily.group_by("day").agg(
        pl.col("is_advancing").sum().alias("advancing"),
        pl.col("is_declining").sum().alias("declining"),
        ((~pl.col("is_advancing")) & (~pl.col("is_declining"))).sum().alias("unchanged"),
        pl.len().alias("total"),
    ).sort("day")

    breadth = breadth.with_columns(
        (pl.col("advancing") / (pl.col("advancing") + pl.col("declining"))).alias("breadth_ratio")
    )

    return breadth


def _compute_ema(values: list[float], span: int) -> list[float]:
    """Compute EMA. Returns list same length as input."""
    if not values:
        return []
    k = 2.0 / (span + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def run_zbt(dry_run: bool = False) -> int:
    """Compute ZBT breadth and write to zbt_breadth table.

    Returns number of rows written.
    """
    ensure_schema()
    t0 = time.monotonic()

    logger.info("Fetching NYSE daily closes from ohlcv_daily...")
    daily = _fetch_nyse_daily()
    if daily.is_empty():
        raise RuntimeError("No NYSE daily data in ohlcv_daily. Run: just backfill-daily --universe nyse --months 3")

    logger.info("Computing breadth for %d ticker-days...", len(daily))
    breadth = _compute_breadth(daily)

    # 10-day EMA
    ratios = breadth["breadth_ratio"].to_list()
    ema_values = _compute_ema(ratios, EMA_SPAN)
    breadth = breadth.with_columns(pl.Series("ema_10", ema_values))

    # Signal detection — scan chronologically
    days_list = breadth["day"].to_list()
    ema_list = breadth["ema_10"].to_list()

    oversold_flags: list[bool] = []
    thrust_flags: list[bool] = []
    signal_active_flags: list[bool] = []
    days_in_window: list[int | None] = []
    signal_fired_flags: list[bool] = []

    oversold_idx: int | None = None
    fired = False

    for i, ema in enumerate(ema_list):
        is_oversold = ema < OVERSOLD_THRESHOLD
        is_thrust = ema > THRUST_THRESHOLD

        if is_oversold:
            oversold_idx = i
            fired = False

        active = False
        diw: int | None = None
        if oversold_idx is not None and not fired:
            diw = i - oversold_idx
            if diw <= WINDOW_DAYS:
                active = True
                if is_thrust:
                    fired = True
                    logger.info(
                        "ZBT SIGNAL on %s (oversold %s, %d days)",
                        days_list[i], days_list[oversold_idx], diw,
                    )
            else:
                diw = None  # window expired

        oversold_flags.append(is_oversold)
        thrust_flags.append(is_thrust)
        signal_active_flags.append(active)
        days_in_window.append(diw)
        signal_fired_flags.append(fired and is_thrust and active)

    breadth = breadth.with_columns(
        pl.Series("oversold", oversold_flags),
        pl.Series("thrust", thrust_flags),
        pl.Series("signal_active", signal_active_flags),
        pl.Series("days_in_window", days_in_window, dtype=pl.UInt8),
        pl.Series("signal_fired", signal_fired_flags),
    )

    # Cast to match table schema
    breadth = breadth.with_columns(
        pl.col("advancing").cast(pl.UInt32),
        pl.col("declining").cast(pl.UInt32),
        pl.col("unchanged").cast(pl.UInt32),
        pl.col("total").cast(pl.UInt32),
    )

    if dry_run:
        logger.info("Dry run — %d rows computed, not writing", len(breadth))
        return len(breadth)

    ch = get_client()
    ch.insert_arrow("zbt_breadth", breadth.to_arrow())

    elapsed = time.monotonic() - t0
    logger.info("ZBT: %d rows written to zbt_breadth in %.1fs", len(breadth), elapsed)
    return len(breadth)
