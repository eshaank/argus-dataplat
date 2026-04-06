"""Cross-asset features: daily returns and rolling correlations.

Tracks SPY, GLD, TLT, HYG, DBC, UUP from ohlcv_daily_mv.
Computes rolling 20-day correlations between SPY and each cross-asset.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from dataplat.algo.features.base import FeatureModule, FeatureRow
from dataplat.algo.features.registry import register

NAN = float("nan")

# Cross-asset tickers and their feature name prefixes
CROSS_ASSETS = ["SPY", "GLD", "TLT", "HYG", "DBC", "UUP"]
CORRELATION_PAIRS = [("SPY", "TLT"), ("SPY", "GLD"), ("SPY", "HYG")]
CORR_WINDOW = 20


@register
class CrossAssetFeatures(FeatureModule):
    name = "cross_asset"
    staleness_threshold_days = 1

    @property
    def feature_names(self) -> list[str]:
        ret_names = [f"ret_{t.lower()}" for t in CROSS_ASSETS]
        corr_names = [f"corr_{a.lower()}_{b.lower()}_{CORR_WINDOW}d" for a, b in CORRELATION_PAIRS]
        return ret_names + corr_names

    def compute(self, target_date: date) -> FeatureRow:
        stale: list[str] = []

        # Pull daily closes for all cross-asset tickers over lookback window
        lookback_start = target_date - timedelta(days=CORR_WINDOW + 15)  # extra buffer for non-trading days
        rows = self._query(
            """
            SELECT ticker, date, close
            FROM ohlcv_daily_mv
            WHERE ticker IN {tickers:Array(String)}
              AND date BETWEEN {start:Date} AND {end:Date}
            ORDER BY ticker, date
            """,
            {
                "tickers": CROSS_ASSETS,
                "start": lookback_start,
                "end": target_date,
            },
        )

        # Organize: {ticker: [(date, close), ...]}
        by_ticker: dict[str, list[tuple[date, float]]] = {t: [] for t in CROSS_ASSETS}
        for r in rows:
            t = r["ticker"]
            if t in by_ticker and r["close"]:
                by_ticker[t].append((r["date"], float(r["close"])))

        features: dict[str, float] = {}

        # Daily returns (latest bar)
        for ticker in CROSS_ASSETS:
            key = f"ret_{ticker.lower()}"
            bars = by_ticker[ticker]
            if len(bars) >= 2:
                features[key] = (bars[-1][1] - bars[-2][1]) / bars[-2][1]
            else:
                features[key] = NAN
                stale.append(key)

        # Rolling correlations
        for ticker_a, ticker_b in CORRELATION_PAIRS:
            key = f"corr_{ticker_a.lower()}_{ticker_b.lower()}_{CORR_WINDOW}d"
            features[key] = self._rolling_corr(by_ticker[ticker_a], by_ticker[ticker_b], CORR_WINDOW)

        return FeatureRow(features=features, stale=stale)

    @staticmethod
    def _compute_returns(bars: list[tuple[date, float]]) -> list[tuple[date, float]]:
        """Compute daily returns from (date, close) pairs."""
        returns = []
        for i in range(1, len(bars)):
            prev = bars[i - 1][1]
            if prev > 0:
                returns.append((bars[i][0], (bars[i][1] - prev) / prev))
        return returns

    @staticmethod
    def _rolling_corr(
        bars_a: list[tuple[date, float]],
        bars_b: list[tuple[date, float]],
        window: int,
    ) -> float:
        """Pearson correlation of daily returns over the last `window` trading days."""
        # Compute returns
        rets_a = CrossAssetFeatures._compute_returns(bars_a)
        rets_b = CrossAssetFeatures._compute_returns(bars_b)

        if len(rets_a) < window or len(rets_b) < window:
            return NAN

        # Align on dates — use most recent `window` dates present in both
        dates_a = {d: r for d, r in rets_a}
        dates_b = {d: r for d, r in rets_b}
        common = sorted(set(dates_a.keys()) & set(dates_b.keys()))

        if len(common) < window:
            return NAN

        common = common[-window:]
        a_vals = [dates_a[d] for d in common]
        b_vals = [dates_b[d] for d in common]

        # Pearson correlation
        n = len(a_vals)
        mean_a = sum(a_vals) / n
        mean_b = sum(b_vals) / n
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(a_vals, b_vals, strict=True)) / n
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in a_vals) / n)
        std_b = math.sqrt(sum((b - mean_b) ** 2 for b in b_vals) / n)

        if std_a == 0 or std_b == 0:
            return NAN

        return cov / (std_a * std_b)
