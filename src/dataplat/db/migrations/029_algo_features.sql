-- Daily feature matrix for the trading algorithm.
-- One row per date with all computed features + PCA components.
-- Written by the feature engineering pipeline, read by regime detector + signal model.

CREATE TABLE IF NOT EXISTS algo_feature_matrix
(
    date          Date,

    -- ── Options features (SPY-centric) ────────────────────────────
    iv_rank                Float64  COMMENT 'ATM IV percentile rank over trailing 252 days (0-1)',
    iv_current             Float64  COMMENT 'Current 30-DTE ATM implied vol',
    term_structure_slope   Float64  COMMENT 'IV slope: front-month minus back-month (contango < 0, backwardation > 0)',
    skew_25d               Float64  COMMENT '25-delta put IV minus 25-delta call IV',
    gex_net                Float64  COMMENT 'Net gamma exposure (positive = dealer long gamma)',
    gex_sign               Int8     COMMENT 'GEX sign: +1 (positive), -1 (negative), 0 (negligible)',
    put_call_ratio         Float64  COMMENT 'Put volume / call volume (SPY)',
    vol_risk_premium       Float64  COMMENT 'IV minus trailing 20-day realized vol',

    -- ── Equity / price features ───────────────────────────────────
    overnight_gap           Float64  COMMENT 'Overnight gap: (open - prev_close) / prev_close',
    premarket_range         Float64  COMMENT 'Pre-market high-low range as % of prev close',
    intraday_momentum       Float64  COMMENT 'Close-to-close 1-day return (SPY)',
    realized_vol_5d         Float64  COMMENT 'Trailing 5-day realized vol (annualized)',
    realized_vol_20d        Float64  COMMENT 'Trailing 20-day realized vol (annualized)',

    -- ── 0DTE flow features (SPY) ─────────────────────────────────
    zero_dte_put_volume     UInt64   COMMENT '0DTE put volume on SPY',
    zero_dte_call_volume    UInt64   COMMENT '0DTE call volume on SPY',
    zero_dte_pc_ratio       Float64  COMMENT '0DTE put/call volume ratio',

    -- ── Cross-asset features ──────────────────────────────────────
    ret_spy                 Float64  COMMENT 'SPY daily return',
    ret_gld                 Float64  COMMENT 'GLD daily return',
    ret_tlt                 Float64  COMMENT 'TLT daily return',
    ret_hyg                 Float64  COMMENT 'HYG daily return',
    ret_dbc                 Float64  COMMENT 'DBC daily return',
    ret_uup                 Float64  COMMENT 'UUP daily return',
    corr_spy_tlt_20d        Float64  COMMENT 'SPY-TLT 20-day rolling correlation',
    corr_spy_gld_20d        Float64  COMMENT 'SPY-GLD 20-day rolling correlation',
    corr_spy_hyg_20d        Float64  COMMENT 'SPY-HYG 20-day rolling correlation',

    -- ── Macro / FRED features ─────────────────────────────────────
    real_yield_10y          Float64  COMMENT '10Y TIPS real yield',
    real_yield_momentum_5d  Float64  COMMENT '5-day change in 10Y TIPS yield',
    yield_curve_10y2y       Float64  COMMENT '10Y - 2Y Treasury spread',
    yield_curve_10y3m       Float64  COMMENT '10Y - 3M Treasury spread',
    cp_stress_spread        Float64  COMMENT 'Commercial paper 3M minus T-bill 3M (credit stress)',
    hy_oas                  Float64  COMMENT 'High-yield OAS spread (bps)',
    vix                     Float64  COMMENT 'CBOE VIX close',
    financial_stress        Float64  COMMENT 'St. Louis Fed Financial Stress Index',
    financial_conditions    Float64  COMMENT 'Chicago Fed NFCI',
    sahm_rule               Float64  COMMENT 'Sahm Rule recession indicator',
    jobless_claims_4wk_avg  Float64  COMMENT '4-week average initial claims',
    jobless_claims_momentum Float64  COMMENT '13-week change in 4-week avg claims',

    -- ── PCA components ────────────────────────────────────────────
    pc_1  Float64  COMMENT 'Principal component 1',
    pc_2  Float64  COMMENT 'Principal component 2',
    pc_3  Float64  COMMENT 'Principal component 3',
    pc_4  Float64  COMMENT 'Principal component 4',
    pc_5  Float64  COMMENT 'Principal component 5',
    pc_6  Float64  COMMENT 'Principal component 6',
    pc_7  Float64  COMMENT 'Principal component 7',
    pc_8  Float64  COMMENT 'Principal component 8',
    pc_9  Float64  COMMENT 'Principal component 9',
    pc_10 Float64  COMMENT 'Principal component 10',

    -- ── Metadata ──────────────────────────────────────────────────
    feature_count       UInt16     COMMENT 'Number of non-null raw features on this row',
    stale_features      Array(String) COMMENT 'Feature names that used forward-filled stale data',
    computed_at         DateTime64(3) DEFAULT now64(3),

    INDEX idx_date date TYPE minmax GRANULARITY 1
)
ENGINE = ReplacingMergeTree(computed_at)
PARTITION BY toYear(date)
ORDER BY date
COMMENT 'Daily feature matrix for autonomous trading algorithm — Layer 1 output';
