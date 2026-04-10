"""Options-derived features from the option_chains table.

All features are SPY-centric (the primary trading instrument).
Queries option_chains for snapshots on or near the target date.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from dataplat.algo.features.base import FeatureModule, FeatureRow
from dataplat.algo.features.registry import register

NAN = float("nan")


@register
class OptionsFeatures(FeatureModule):
    name = "options"
    staleness_threshold_days = 1  # Options data must be fresh daily

    @property
    def feature_names(self) -> list[str]:
        return [
            "iv_rank",
            "iv_current",
            "term_structure_slope",
            "skew_25d",
            "gex_net",
            "gex_sign",
            "put_call_ratio",
            "vol_risk_premium",
            "zero_dte_put_volume",
            "zero_dte_call_volume",
            "zero_dte_pc_ratio",
        ]

    def compute(self, target_date: date) -> FeatureRow:
        stale: list[str] = []

        # Find the actual latest snapshot date on or before target
        snapshot = self._resolve_snapshot_date(target_date)
        if snapshot is None:
            return FeatureRow(features={k: NAN for k in self.feature_names}, stale=self.feature_names)

        if (target_date - snapshot).days > self.staleness_threshold_days:
            stale = self.feature_names  # All features are stale

        iv_current, iv_rank = self._compute_iv_rank(snapshot)
        term_slope = self._compute_term_structure_slope(snapshot)
        skew = self._compute_skew_25d(snapshot)
        gex_net, gex_sign = self._compute_gex(snapshot)
        pc_ratio = self._compute_put_call_ratio(snapshot)
        vrp = self._compute_vol_risk_premium(snapshot, iv_current)
        zero_dte = self._compute_zero_dte_flow(snapshot)

        return FeatureRow(
            features={
                "iv_rank": iv_rank,
                "iv_current": iv_current,
                "term_structure_slope": term_slope,
                "skew_25d": skew,
                "gex_net": gex_net,
                "gex_sign": gex_sign,
                "put_call_ratio": pc_ratio,
                "vol_risk_premium": vrp,
                "zero_dte_put_volume": zero_dte[0],
                "zero_dte_call_volume": zero_dte[1],
                "zero_dte_pc_ratio": zero_dte[2],
            },
            stale=stale,
        )

    def _resolve_snapshot_date(self, target_date: date) -> date | None:
        """Find the most recent option_chains snapshot date <= target_date."""
        row = self._query_single(
            """
            SELECT max(snapshot_date) AS snap
            FROM option_chains
            WHERE underlying = 'SPY'
              AND snapshot_date <= {target:Date}
              AND snapshot_date >= {earliest:Date}
            """,
            {"target": target_date, "earliest": target_date - timedelta(days=5)},
        )
        if row and row["snap"]:
            return row["snap"]
        return None

    def _compute_iv_rank(self, snapshot: date) -> tuple[float, float]:
        """ATM 30-DTE IV and its percentile rank over trailing 252 days.

        ATM = closest strike to underlying_price, 20-40 DTE, calls.
        IV rank = % of days in last year where ATM IV was lower.
        """
        # Current ATM IV (30-DTE-ish)
        row = self._query_single(
            """
            SELECT avg(implied_vol) AS atm_iv
            FROM option_chains
            WHERE underlying = 'SPY'
              AND snapshot_date = {snap:Date}
              AND put_call = 'call'
              AND implied_vol > 0
              AND (expiration - snapshot_date) BETWEEN 20 AND 40
              AND abs(strike - underlying_price) / underlying_price < 0.02
            """,
            {"snap": snapshot},
        )
        iv_current = row["atm_iv"] if row and row["atm_iv"] else NAN

        if math.isnan(iv_current):
            return NAN, NAN

        # Historical ATM IV for each of the last 252 trading days
        hist = self._query(
            """
            SELECT snapshot_date, avg(implied_vol) AS atm_iv
            FROM option_chains
            WHERE underlying = 'SPY'
              AND snapshot_date BETWEEN {start:Date} AND {end:Date}
              AND put_call = 'call'
              AND implied_vol > 0
              AND (expiration - snapshot_date) BETWEEN 20 AND 40
              AND abs(strike - underlying_price) / underlying_price < 0.02
            GROUP BY snapshot_date
            ORDER BY snapshot_date
            """,
            {"start": snapshot - timedelta(days=365), "end": snapshot},
        )
        if len(hist) < 20:
            return iv_current, NAN

        iv_values = [r["atm_iv"] for r in hist if r["atm_iv"]]
        rank = sum(1 for v in iv_values if v < iv_current) / len(iv_values)
        return iv_current, rank

    def _compute_term_structure_slope(self, snapshot: date) -> float:
        """IV term structure slope: front-month ATM IV minus back-month ATM IV.

        Positive = backwardation (front > back, fear).
        Negative = contango (front < back, normal).
        """
        row = self._query_single(
            """
            WITH atm AS (
                SELECT
                    expiration,
                    (expiration - snapshot_date) AS dte,
                    avg(implied_vol) AS iv
                FROM option_chains
                WHERE underlying = 'SPY'
                  AND snapshot_date = {snap:Date}
                  AND put_call = 'call'
                  AND implied_vol > 0
                  AND abs(strike - underlying_price) / underlying_price < 0.02
                GROUP BY expiration, snapshot_date
                HAVING dte BETWEEN 7 AND 90
                ORDER BY dte
            )
            SELECT
                argMin(iv, dte) AS front_iv,
                argMax(iv, dte) AS back_iv
            FROM atm
            """,
            {"snap": snapshot},
        )
        if row and row["front_iv"] and row["back_iv"]:
            return row["front_iv"] - row["back_iv"]
        return NAN

    def _compute_skew_25d(self, snapshot: date) -> float:
        """25-delta skew: 25-delta put IV minus 25-delta call IV.

        Higher = more demand for downside protection.
        Uses the 20-40 DTE expiration for stability.
        """
        row = self._query_single(
            """
            SELECT
                avgIf(implied_vol, put_call = 'put'   AND delta BETWEEN -0.30 AND -0.20) AS put_25d_iv,
                avgIf(implied_vol, put_call = 'call'  AND delta BETWEEN  0.20 AND  0.30) AS call_25d_iv
            FROM option_chains
            WHERE underlying = 'SPY'
              AND snapshot_date = {snap:Date}
              AND implied_vol > 0
              AND (expiration - snapshot_date) BETWEEN 20 AND 40
            """,
            {"snap": snapshot},
        )
        if row and row["put_25d_iv"] and row["call_25d_iv"]:
            return row["put_25d_iv"] - row["call_25d_iv"]
        return NAN

    def _compute_gex(self, snapshot: date) -> tuple[float, int]:
        """Net Gamma Exposure (GEX) — dealer gamma from open interest.

        GEX = Σ (OI × gamma × contract_multiplier × spot × spot × 0.01)
        Convention: calls = +gamma (dealers long), puts = -gamma (dealers short).
        Positive net GEX = dealer-long-gamma → suppresses vol.
        Negative net GEX = dealer-short-gamma → amplifies moves.
        """
        row = self._query_single(
            """
            SELECT
                sum(
                    CASE
                        WHEN put_call = 'call' THEN open_interest * gamma * underlying_price * underlying_price * 0.01
                        ELSE -open_interest * gamma * underlying_price * underlying_price * 0.01
                    END
                ) AS net_gex
            FROM option_chains
            WHERE underlying = 'SPY'
              AND snapshot_date = {snap:Date}
              AND gamma > 0
              AND open_interest > 0
              AND (expiration - snapshot_date) BETWEEN 0 AND 60
            """,
            {"snap": snapshot},
        )
        if row and row["net_gex"] is not None:
            net = row["net_gex"]
            sign = 1 if net > 0 else (-1 if net < 0 else 0)
            return net, sign
        return NAN, 0

    def _compute_put_call_ratio(self, snapshot: date) -> float:
        """Put/call volume ratio on SPY for the snapshot date."""
        row = self._query_single(
            """
            SELECT
                sumIf(volume, put_call = 'put')  AS put_vol,
                sumIf(volume, put_call = 'call') AS call_vol
            FROM option_chains
            WHERE underlying = 'SPY'
              AND snapshot_date = {snap:Date}
              AND volume > 0
            """,
            {"snap": snapshot},
        )
        if row and row["call_vol"] and row["call_vol"] > 0:
            return row["put_vol"] / row["call_vol"]
        return NAN

    def _compute_vol_risk_premium(self, snapshot: date, iv_current: float) -> float:
        """Vol risk premium = current ATM IV - trailing 20-day realized vol.

        Positive VRP = options are expensive relative to realized moves.
        """
        if math.isnan(iv_current):
            return NAN

        # 20-day realized vol from daily returns
        row = self._query_single(
            """
            SELECT stddevPop(ret) * sqrt(252) AS rv_20d
            FROM (
                SELECT
                    (close - lagInFrame(close) OVER (ORDER BY day))
                    / lagInFrame(close) OVER (ORDER BY day) AS ret
                FROM ohlcv_daily_mv
                WHERE ticker = 'SPY'
                  AND day BETWEEN {start:Date} AND {end:Date}
                ORDER BY day
            )
            WHERE ret IS NOT NULL
            """,
            {"start": snapshot - timedelta(days=35), "end": snapshot},
        )
        if row and row["rv_20d"]:
            return iv_current - row["rv_20d"]
        return NAN

    def _compute_zero_dte_flow(self, snapshot: date) -> tuple[float, float, float]:
        """0DTE options flow — volume on contracts expiring same day (SPY).

        Returns (put_volume, call_volume, put_call_ratio).
        """
        row = self._query_single(
            """
            SELECT
                sumIf(volume, put_call = 'put')  AS put_vol,
                sumIf(volume, put_call = 'call') AS call_vol
            FROM option_chains
            WHERE underlying = 'SPY'
              AND snapshot_date = {snap:Date}
              AND expiration = {snap:Date}
              AND volume > 0
            """,
            {"snap": snapshot},
        )
        if row and row["put_vol"] is not None and row["call_vol"] is not None:
            pv = float(row["put_vol"])
            cv = float(row["call_vol"])
            ratio = pv / cv if cv > 0 else NAN
            return pv, cv, ratio
        return NAN, NAN, NAN
