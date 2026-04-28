"""Macro / FRED features from rates, macro_daily, macro_weekly, macro_monthly, labor_market.

These features have mixed frequencies:
- rates, macro_daily: updated daily
- macro_weekly: updated weekly (Thursday)
- macro_monthly, labor_market: updated monthly

Forward-fill logic handles the gaps. Staleness tracking flags when
data is older than expected for its frequency.
"""

from __future__ import annotations

from datetime import date, timedelta

from dataplat.algo.features.base import FeatureModule, FeatureRow
from dataplat.algo.features.registry import register

NAN = float("nan")


@register
class MacroFeatures(FeatureModule):
    name = "macro"
    staleness_threshold_days = 3  # Macro data can lag a few days

    @property
    def feature_names(self) -> list[str]:
        return [
            "real_yield_10y",
            "real_yield_momentum_5d",
            "yield_curve_10y2y",
            "yield_curve_10y3m",
            "cp_stress_spread",
            "hy_oas",
            "vix",
            "financial_stress",
            "financial_conditions",
            "sahm_rule",
            "jobless_claims_4wk_avg",
            "jobless_claims_momentum",
        ]

    def compute(self, target_date: date) -> FeatureRow:
        stale: list[str] = []
        features: dict[str, float] = {}

        # ── Daily: rates table ──────────────────────────────────────
        rates = self._get_rates(target_date)
        features["real_yield_10y"] = rates.get("tips_10y", NAN)
        features["cp_stress_spread"] = self._cp_stress(rates)
        features["hy_oas"] = rates.get("hy_oas", NAN)
        if not rates:
            stale.extend(["real_yield_10y", "cp_stress_spread", "hy_oas"])

        # Real yield momentum: 5-day change in TIPS 10Y
        features["real_yield_momentum_5d"] = self._real_yield_momentum(target_date)

        # ── Daily: macro_daily table ────────────────────────────────
        macro_d = self._get_macro_daily(target_date)
        features["yield_curve_10y2y"] = macro_d.get("yield_curve_10y2y", NAN)
        features["yield_curve_10y3m"] = macro_d.get("yield_curve_10y3m", NAN)
        features["vix"] = macro_d.get("vix", NAN)
        if not macro_d:
            stale.extend(["yield_curve_10y2y", "yield_curve_10y3m", "vix"])

        # ── Weekly: macro_weekly table ──────────────────────────────
        weekly = self._get_macro_weekly(target_date)
        features["financial_stress"] = weekly.get("financial_stress", NAN)
        features["financial_conditions"] = weekly.get("financial_conditions", NAN)
        if not weekly:
            stale.extend(["financial_stress", "financial_conditions"])

        # ── Weekly: jobless claims features ─────────────────────────
        claims_4wk, claims_mom = self._compute_jobless_features(target_date)
        features["jobless_claims_4wk_avg"] = claims_4wk
        features["jobless_claims_momentum"] = claims_mom

        # ── Monthly: Sahm rule ──────────────────────────────────────
        features["sahm_rule"] = self._get_sahm(target_date)

        return FeatureRow(features=features, stale=stale)

    def _get_rates(self, target_date: date) -> dict:
        """Latest rates row on or before target_date (forward-fill up to 5 days)."""
        return (
            self._query_single(
                """
            SELECT tips_10y, hy_oas, commercial_paper_3m, tbill_3m
            FROM rates
            WHERE date <= {target:Date}
              AND date >= {earliest:Date}
            ORDER BY date DESC
            LIMIT 1
            """,
                {"target": target_date, "earliest": target_date - timedelta(days=5)},
            )
            or {}
        )

    def _cp_stress(self, rates: dict) -> float:
        """Commercial paper stress spread = CP 3M minus T-bill 3M."""
        cp = rates.get("commercial_paper_3m")
        tb = rates.get("tbill_3m")
        if cp is not None and tb is not None:
            return cp - tb
        return NAN

    def _real_yield_momentum(self, target_date: date) -> float:
        """5-day change in 10Y TIPS yield."""
        rows = self._query(
            """
            SELECT date, tips_10y
            FROM rates
            WHERE date BETWEEN {start:Date} AND {end:Date}
              AND tips_10y IS NOT NULL
            ORDER BY date
            """,
            {"start": target_date - timedelta(days=10), "end": target_date},
        )
        if len(rows) < 2:
            return NAN

        latest = rows[-1]["tips_10y"]
        # Find the observation ~5 days ago
        target_lookback = target_date - timedelta(days=5)
        older = None
        for r in rows:
            if r["date"] <= target_lookback:
                older = r["tips_10y"]
        if older is None:
            older = rows[0]["tips_10y"]

        if latest is not None and older is not None:
            return latest - older
        return NAN

    def _get_macro_daily(self, target_date: date) -> dict:
        """Latest macro_daily row on or before target_date."""
        return (
            self._query_single(
                """
            SELECT yield_curve_10y2y, yield_curve_10y3m, vix
            FROM macro_daily
            WHERE date <= {target:Date}
              AND date >= {earliest:Date}
            ORDER BY date DESC
            LIMIT 1
            """,
                {"target": target_date, "earliest": target_date - timedelta(days=5)},
            )
            or {}
        )

    def _get_macro_weekly(self, target_date: date) -> dict:
        """Latest macro_weekly row on or before target_date (up to 10 days back for weekly)."""
        return (
            self._query_single(
                """
            SELECT financial_stress, financial_conditions, initial_claims
            FROM macro_weekly
            WHERE date <= {target:Date}
              AND date >= {earliest:Date}
            ORDER BY date DESC
            LIMIT 1
            """,
                {"target": target_date, "earliest": target_date - timedelta(days=10)},
            )
            or {}
        )

    def _compute_jobless_features(self, target_date: date) -> tuple[float, float]:
        """4-week average initial claims and 13-week momentum.

        Returns (4wk_avg, 13wk_momentum).
        Momentum = current 4wk avg - 4wk avg from 13 weeks ago.
        """
        rows = self._query(
            """
            SELECT date, initial_claims
            FROM macro_weekly
            WHERE date BETWEEN {start:Date} AND {end:Date}
              AND initial_claims IS NOT NULL
            ORDER BY date
            """,
            {"start": target_date - timedelta(weeks=16), "end": target_date},
        )
        if len(rows) < 4:
            return NAN, NAN

        claims = [r["initial_claims"] for r in rows if r["initial_claims"] is not None]
        if len(claims) < 4:
            return NAN, NAN

        # 4-week average (most recent 4)
        avg_4wk = sum(claims[-4:]) / 4

        # 13-week momentum: current 4wk avg minus 4wk avg from 13 weeks ago
        momentum = NAN
        if len(claims) >= 17:  # Need 13 + 4 observations
            avg_4wk_13w_ago = sum(claims[-17:-13]) / 4
            momentum = avg_4wk - avg_4wk_13w_ago

        return avg_4wk, momentum

    def _get_sahm(self, target_date: date) -> float:
        """Sahm Rule: latest monthly value on or before target_date."""
        row = self._query_single(
            """
            SELECT sahm_rule
            FROM macro_monthly
            WHERE date <= {target:Date}
              AND date >= {earliest:Date}
              AND sahm_rule IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
            """,
            {"target": target_date, "earliest": target_date - timedelta(days=45)},
        )
        if row and row["sahm_rule"] is not None:
            return row["sahm_rule"]
        return NAN
