"""Feature pipeline — orchestrates all feature modules, runs PCA, writes to ClickHouse.

Usage:
    from dataplat.algo.features.pipeline import FeaturePipeline
    from dataplat.db.client import get_client

    pipeline = FeaturePipeline(get_client())
    pipeline.run(start=date(2023, 1, 1), end=date(2024, 12, 31))
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

import polars as pl
from clickhouse_connect.driver import Client

from dataplat.algo.features.base import FeatureRow
from dataplat.algo.features.registry import get_all_modules

logger = logging.getLogger(__name__)

N_COMPONENTS = 10  # PCA output dimensions


class FeaturePipeline:
    """Runs all feature modules for a date range, applies PCA, writes to ClickHouse."""

    def __init__(self, client: Client, *, n_components: int = N_COMPONENTS) -> None:
        self.client = client
        self.n_components = n_components
        self.modules = get_all_modules(client)

    def run(
        self,
        start: date,
        end: date | None = None,
        *,
        dry_run: bool = False,
    ) -> int:
        """Compute features for each trading day in [start, end] and write to ClickHouse.

        Args:
            start: First date to compute.
            end: Last date (inclusive). Defaults to today.
            dry_run: If True, compute but don't write. Log results.

        Returns:
            Number of rows written.
        """
        if end is None:
            end = date.today()

        trading_dates = self._get_trading_dates(start, end)
        if not trading_dates:
            logger.warning("No trading dates found between %s and %s", start, end)
            return 0

        logger.info(
            "Computing features for %d trading days (%s → %s) across %d modules",
            len(trading_dates),
            trading_dates[0],
            trading_dates[-1],
            len(self.modules),
        )

        all_rows: list[dict] = []

        for target_date in trading_dates:
            row = self._compute_one_day(target_date)
            all_rows.append(row)

        if not all_rows:
            return 0

        # Apply PCA across the full date range
        df = pl.DataFrame(all_rows)
        df = self._apply_pca(df)

        if dry_run:
            logger.info("Dry run — %d rows computed, not writing to ClickHouse", len(df))
            logger.info("Sample row:\n%s", df.tail(1))
            return 0

        return self._write_to_clickhouse(df)

    def run_single(self, target_date: date, *, dry_run: bool = False) -> dict:
        """Compute features for a single date. Useful for daily runs.

        PCA is applied using the trailing 252 days of existing data for fitting,
        then projecting the new day's features.
        """
        row = self._compute_one_day(target_date)

        if dry_run:
            logger.info("Dry run — features for %s: %s", target_date, row)
            return row

        # For single-day PCA, we need historical data to fit the transform
        df_new = pl.DataFrame([row])
        df_hist = self._load_historical_features(target_date, lookback_days=252)

        if df_hist is not None and len(df_hist) >= 30:
            df_combined = pl.concat([df_hist, df_new], how="diagonal_relaxed")
            df_combined = self._apply_pca(df_combined)
            # Take only the new row (last row)
            df_result = df_combined.tail(1)
        else:
            # Not enough history — fill PCA columns with NaN
            for i in range(1, self.n_components + 1):
                df_new = df_new.with_columns(pl.lit(float("nan")).alias(f"pc_{i}"))
            df_result = df_new

        self._write_to_clickhouse(df_result)
        return row

    def _compute_one_day(self, target_date: date) -> dict:
        """Run all feature modules for a single date, merge into one row."""
        merged_features: dict[str, float] = {}
        all_stale: list[str] = []

        for module in self.modules:
            try:
                result: FeatureRow = module.compute(target_date)
                merged_features.update(result.features)
                all_stale.extend(result.stale)
            except Exception:
                logger.exception("Module %s failed for %s", module.name, target_date)
                # Fill this module's features with NaN
                for name in module.feature_names:
                    merged_features[name] = float("nan")
                all_stale.extend(module.feature_names)

        # Count non-NaN features
        feature_count = sum(1 for v in merged_features.values() if not (isinstance(v, float) and math.isnan(v)))

        return {
            "date": target_date,
            **merged_features,
            "feature_count": feature_count,
            "stale_features": list(set(all_stale)),
        }

    def _apply_pca(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply PCA compression to raw features → n_components principal components.

        Uses sklearn.decomposition.PCA. Features are standardized (z-score) before PCA.
        NaN values are filled with column means before PCA.
        """
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        # Select only numeric feature columns (exclude date, metadata, existing PC columns)
        exclude = {"date", "feature_count", "stale_features", "computed_at"}
        exclude.update(f"pc_{i}" for i in range(1, self.n_components + 1))
        feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in (pl.Float64, pl.Int8, pl.UInt64)]

        if not feature_cols:
            logger.warning("No feature columns found for PCA")
            for i in range(1, self.n_components + 1):
                df = df.with_columns(pl.lit(float("nan")).alias(f"pc_{i}"))
            return df

        # Extract numeric matrix, fill NaN with column means
        feature_df = df.select(feature_cols).cast({c: pl.Float64 for c in feature_cols})
        for col in feature_cols:
            col_mean = feature_df[col].drop_nulls().drop_nans().mean()
            if col_mean is None:
                col_mean = 0.0
            feature_df = feature_df.with_columns(pl.col(col).fill_null(col_mean).fill_nan(col_mean))

        matrix = feature_df.to_numpy()

        # Standardize
        scaler = StandardScaler()
        matrix_scaled = scaler.fit_transform(matrix)

        # PCA
        n_comp = min(self.n_components, matrix_scaled.shape[1], matrix_scaled.shape[0])
        pca = PCA(n_components=n_comp)
        components = pca.fit_transform(matrix_scaled)

        logger.info(
            "PCA: %d components explain %.1f%% of variance",
            n_comp,
            pca.explained_variance_ratio_.sum() * 100,
        )

        # Add PC columns to dataframe
        for i in range(n_comp):
            df = df.with_columns(pl.Series(f"pc_{i + 1}", components[:, i]))
        # Fill remaining PC columns with NaN if fewer components than requested
        for i in range(n_comp, self.n_components):
            df = df.with_columns(pl.lit(float("nan")).alias(f"pc_{i + 1}"))

        return df

    def _write_to_clickhouse(self, df: pl.DataFrame) -> int:
        """Write feature matrix rows to algo_feature_matrix table."""
        # Convert stale_features list to ClickHouse Array(String)
        # and ensure all columns match the table schema
        records = df.to_dicts()
        if not records:
            return 0

        # Build column list matching the table schema
        table_cols = [
            "date",
            # Options
            "iv_rank",
            "iv_current",
            "term_structure_slope",
            "skew_25d",
            "gex_net",
            "gex_sign",
            "put_call_ratio",
            "vol_risk_premium",
            # Equity
            "overnight_gap",
            "premarket_range",
            "intraday_momentum",
            "realized_vol_5d",
            "realized_vol_20d",
            # 0DTE
            "zero_dte_put_volume",
            "zero_dte_call_volume",
            "zero_dte_pc_ratio",
            # Cross-asset
            "ret_spy",
            "ret_gld",
            "ret_tlt",
            "ret_hyg",
            "ret_dbc",
            "ret_uup",
            "corr_spy_tlt_20d",
            "corr_spy_gld_20d",
            "corr_spy_hyg_20d",
            # Macro
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
            # PCA
            "pc_1",
            "pc_2",
            "pc_3",
            "pc_4",
            "pc_5",
            "pc_6",
            "pc_7",
            "pc_8",
            "pc_9",
            "pc_10",
            # Metadata
            "feature_count",
            "stale_features",
        ]

        # Build insert data
        insert_rows = []
        for rec in records:
            row = []
            for col in table_cols:
                val = rec.get(col)
                if val is None:
                    val = float("nan") if col != "date" and col != "stale_features" and col != "feature_count" else val
                # Convert NaN to 0 for integer columns
                if col in ("gex_sign",) and isinstance(val, float) and math.isnan(val):
                    val = 0
                if col in ("zero_dte_put_volume", "zero_dte_call_volume") and isinstance(val, float):
                    val = 0 if math.isnan(val) else int(val)
                if col == "feature_count" and val is None:
                    val = 0
                if col == "stale_features" and val is None:
                    val = []
                row.append(val)
            insert_rows.append(row)

        self.client.insert(
            "algo_feature_matrix",
            insert_rows,
            column_names=table_cols,
        )

        logger.info("Wrote %d rows to algo_feature_matrix", len(insert_rows))
        return len(insert_rows)

    def _get_trading_dates(self, start: date, end: date) -> list[date]:
        """Get dates where SPY traded (proxy for US market calendar)."""
        rows = self._query(
            """
            SELECT DISTINCT day
            FROM ohlcv_daily_mv
            WHERE ticker = 'SPY'
              AND day BETWEEN {start:Date} AND {end:Date}
            ORDER BY day
            """,
            {"start": start, "end": end},
        )
        return [r["day"] for r in rows]

    def _load_historical_features(self, before_date: date, lookback_days: int) -> pl.DataFrame | None:
        """Load existing feature rows from ClickHouse for PCA fitting."""
        rows = self._query(
            """
            SELECT *
            FROM algo_feature_matrix
            WHERE date BETWEEN {start:Date} AND {end:Date}
            ORDER BY date
            """,
            {
                "start": before_date - timedelta(days=lookback_days + 30),
                "end": before_date - timedelta(days=1),
            },
        )
        if not rows:
            return None
        return pl.DataFrame(rows)

    def _query(self, sql: str, params: dict | None = None) -> list[dict]:
        """Run a ClickHouse query and return rows as list of dicts."""
        result = self.client.query(sql, parameters=params or {})
        columns = result.column_names
        return [dict(zip(columns, row, strict=True)) for row in result.result_rows]
