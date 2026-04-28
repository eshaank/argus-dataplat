"""Equity / price-action features from ohlcv_daily_mv.

Overnight gaps, intraday momentum, realized volatility.
All SPY-centric for the primary trading signal.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from dataplat.algo.features.base import FeatureModule, FeatureRow
from dataplat.algo.features.registry import register

NAN = float("nan")


@register
class EquityFeatures(FeatureModule):
    name = "equity"
    staleness_threshold_days = 1

    @property
    def feature_names(self) -> list[str]:
        return [
            "overnight_gap",
            "premarket_range",
            "intraday_momentum",
            "realized_vol_5d",
            "realized_vol_20d",
        ]

    def compute(self, target_date: date) -> FeatureRow:
        stale: list[str] = []

        # Pull last 30 trading days of SPY daily bars for all computations
        bars = self._query(
            """
            SELECT day, open, high, low, close, total_volume
            FROM ohlcv_daily_mv
            WHERE ticker = 'SPY'
              AND day BETWEEN {start:Date} AND {end:Date}
            ORDER BY day
            """,
            {"start": target_date - timedelta(days=45), "end": target_date},
        )

        if len(bars) < 2:
            return FeatureRow(features={k: NAN for k in self.feature_names}, stale=self.feature_names)

        # Check if we actually have data for target_date
        latest_date = bars[-1]["day"]
        if hasattr(latest_date, "date"):
            latest_date = latest_date.date() if callable(latest_date.date) else latest_date
        if isinstance(latest_date, date) and (target_date - latest_date).days > self.staleness_threshold_days:
            stale = self.feature_names

        # Overnight gap: (today's open - yesterday's close) / yesterday's close
        gap = NAN
        if len(bars) >= 2:
            prev_close = bars[-2]["close"]
            today_open = bars[-1]["open"]
            if prev_close and prev_close > 0:
                gap = (today_open - prev_close) / prev_close

        # Pre-market range: (today's high - today's low) / prev close
        # Note: using daily H/L as a proxy since we don't have separate pre-market data
        # in the daily MV. For true pre-market, we'd query the 1-min table before 9:30.
        premarket_range = NAN
        if len(bars) >= 2:
            prev_close = bars[-2]["close"]
            today = bars[-1]
            if prev_close and prev_close > 0 and today["high"] and today["low"]:
                premarket_range = (today["high"] - today["low"]) / prev_close

        # Intraday momentum: close-to-close return
        momentum = NAN
        if len(bars) >= 2:
            prev_close = bars[-2]["close"]
            today_close = bars[-1]["close"]
            if prev_close and prev_close > 0:
                momentum = (today_close - prev_close) / prev_close

        # Realized vol: annualized std dev of daily returns
        rv_5d = self._realized_vol(bars, 5)
        rv_20d = self._realized_vol(bars, 20)

        return FeatureRow(
            features={
                "overnight_gap": gap,
                "premarket_range": premarket_range,
                "intraday_momentum": momentum,
                "realized_vol_5d": rv_5d,
                "realized_vol_20d": rv_20d,
            },
            stale=stale,
        )

    @staticmethod
    def _realized_vol(bars: list[dict], lookback: int) -> float:
        """Compute annualized realized vol from the last `lookback` daily bars."""
        if len(bars) < lookback + 1:
            return NAN

        # Use the most recent `lookback + 1` bars to get `lookback` returns
        window = bars[-(lookback + 1) :]
        returns = []
        for i in range(1, len(window)):
            prev = window[i - 1]["close"]
            curr = window[i]["close"]
            if prev and prev > 0 and curr:
                returns.append((curr - prev) / prev)

        if len(returns) < lookback:
            return NAN

        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        daily_vol = math.sqrt(variance)
        return daily_vol * math.sqrt(252)  # Annualize
