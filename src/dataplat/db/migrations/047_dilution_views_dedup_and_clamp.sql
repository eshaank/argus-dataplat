-- 047_dilution_views_dedup_and_clamp: Two fixes to dilution views
--
-- Fix 1: Add FINAL to financials reads to force ReplacingMergeTree dedup on read.
--   Without FINAL, duplicate rows (same accession ingested twice) survive until
--   ClickHouse background merges run, showing double-counted metrics.
--
-- Fix 2: Clamp antidilutive_shares to NULL when it exceeds 20× shares_outstanding.
--   AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount is
--   frequently mis-tagged by filers (reported in thousands/millions but unit=shares).
--   Affects: SPIR, ACHV, CHKP, EXPE, LCID, TACT, and others.
--   Threshold: > coalesce(shares_outstanding, weighted_avg_shares_diluted) * 20.

CREATE OR REPLACE VIEW v_dilution_snapshot AS
WITH deduped AS (
    SELECT *
    FROM financials FINAL
    WHERE source = 'sec_edgar' AND fiscal_period = 'FY'
),
clamped AS (
    SELECT *,
        coalesce(shares_outstanding, weighted_avg_shares_diluted,
                 weighted_avg_shares_basic)                         AS eff_shares,
        -- Clamp antidilutive_shares: NULL if > 20× effective shares outstanding
        CASE
            WHEN antidilutive_shares > coalesce(
                coalesce(shares_outstanding, weighted_avg_shares_diluted,
                         weighted_avg_shares_basic), 1) * 20
            THEN NULL
            ELSE antidilutive_shares
        END                                                         AS antidilutive_shares_clean
    FROM deduped
)
SELECT
    ticker,
    period_end,
    eff_shares                                                      AS shares_outstanding,
    shares_authorized,
    shares_authorized - eff_shares                                  AS authorized_headroom,
    round((shares_authorized - eff_shares)
        / nullIf(eff_shares, 0) * 100, 1)                          AS headroom_pct,
    weighted_avg_shares_basic,
    weighted_avg_shares_diluted,
    weighted_avg_shares_diluted - weighted_avg_shares_basic         AS dilutive_effect,
    stock_based_compensation,
    round(stock_based_compensation
        / nullIf(revenue, 0) * 100, 1)                             AS sbc_pct_of_revenue,
    buyback_shares,
    buyback_value,
    warrants_outstanding,
    warrant_exercise_price,
    convertible_debt,
    convertible_conversion_price,
    options_outstanding,
    options_exercisable,
    options_weighted_avg_price,
    unvested_rsu_shares,
    antidilutive_shares_clean                                       AS antidilutive_shares,
    -- Total potential dilution using clamped antidilutive
    coalesce(warrants_outstanding, 0)
        + coalesce(options_outstanding, 0)
        + coalesce(unvested_rsu_shares, 0)
        + coalesce(antidilutive_shares_clean, 0)                   AS total_potential_dilution_shares,
    round((coalesce(warrants_outstanding, 0)
        + coalesce(options_outstanding, 0)
        + coalesce(unvested_rsu_shares, 0)
        + coalesce(antidilutive_shares_clean, 0))
        / nullIf(eff_shares, 0) * 100, 1)                         AS total_dilution_pct,
    coalesce(buyback_shares, 0)
        - coalesce(shares_issued_options, 0)
        - coalesce(shares_issued_rsu_vested, 0)
        - coalesce(shares_from_conversion, 0)                      AS net_buyback_shares,
    filing_url
FROM clamped
ORDER BY ticker, period_end DESC;


CREATE OR REPLACE VIEW v_dilution_timeseries AS
WITH deduped AS (
    SELECT *
    FROM financials FINAL
    WHERE source = 'sec_edgar'
      AND fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')
),
clamped AS (
    SELECT *,
        coalesce(shares_outstanding, weighted_avg_shares_diluted,
                 weighted_avg_shares_basic)                         AS eff_shares,
        CASE
            WHEN antidilutive_shares > coalesce(
                coalesce(shares_outstanding, weighted_avg_shares_diluted,
                         weighted_avg_shares_basic), 1) * 20
            THEN NULL
            ELSE antidilutive_shares
        END                                                         AS antidilutive_shares_clean
    FROM deduped
)
SELECT
    ticker,
    period_end,
    fiscal_year,
    fiscal_period,
    eff_shares                                                      AS shares_outstanding,
    weighted_avg_shares_basic,
    weighted_avg_shares_diluted,
    weighted_avg_shares_diluted - weighted_avg_shares_basic         AS dilutive_effect,
    stock_based_compensation,
    round(stock_based_compensation
        / nullIf(revenue, 0) * 100, 2)                             AS sbc_pct_revenue,
    buyback_shares,
    buyback_value,
    shares_issued_options,
    shares_issued_rsu_vested,
    unvested_rsu_shares,
    options_outstanding,
    warrants_outstanding,
    convertible_debt,
    shares_authorized,
    round((shares_authorized - eff_shares)
        / nullIf(eff_shares, 0) * 100, 1)                         AS headroom_pct,
    revenue
FROM clamped
ORDER BY ticker, period_end ASC;


-- Also fix v_latest_financials to deduplicate
CREATE OR REPLACE VIEW v_latest_financials AS
SELECT *
FROM financials FINAL
WHERE source = 'sec_edgar'
  AND fiscal_period = 'FY'
  AND (ticker, period_end) IN (
      SELECT ticker, max(period_end)
      FROM financials FINAL
      WHERE source = 'sec_edgar' AND fiscal_period = 'FY'
      GROUP BY ticker
  );
