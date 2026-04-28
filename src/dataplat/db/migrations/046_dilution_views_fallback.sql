-- 046_dilution_views_fallback: Coalesce shares_outstanding with weighted avg
-- Many companies (e.g. SPIR) don't report CommonStockSharesOutstanding in XBRL.
-- Fall back to weighted_avg_shares_diluted → weighted_avg_shares_basic so the
-- Dilution tab isn't empty for these tickers.

-- ── v_dilution_snapshot ──
CREATE OR REPLACE VIEW v_dilution_snapshot AS
SELECT
    ticker,
    period_end,
    coalesce(shares_outstanding, weighted_avg_shares_diluted,
             weighted_avg_shares_basic)                             AS shares_outstanding,
    shares_authorized,
    shares_authorized
        - coalesce(shares_outstanding, weighted_avg_shares_diluted,
                   weighted_avg_shares_basic)                       AS authorized_headroom,
    round((shares_authorized
        - coalesce(shares_outstanding, weighted_avg_shares_diluted,
                   weighted_avg_shares_basic))
        / nullIf(coalesce(shares_outstanding, weighted_avg_shares_diluted,
                          weighted_avg_shares_basic), 0) * 100, 1) AS headroom_pct,
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
    antidilutive_shares,
    -- Total potential dilution (shares)
    coalesce(warrants_outstanding, 0)
        + coalesce(options_outstanding, 0)
        + coalesce(unvested_rsu_shares, 0)
        + coalesce(antidilutive_shares, 0)                         AS total_potential_dilution_shares,
    -- Total potential dilution as % of outstanding (with fallback)
    round((coalesce(warrants_outstanding, 0)
        + coalesce(options_outstanding, 0)
        + coalesce(unvested_rsu_shares, 0)
        + coalesce(antidilutive_shares, 0))
        / nullIf(coalesce(shares_outstanding, weighted_avg_shares_diluted,
                          weighted_avg_shares_basic), 0) * 100, 1) AS total_dilution_pct,
    -- Net share change signal: buybacks vs issuance
    coalesce(buyback_shares, 0)
        - coalesce(shares_issued_options, 0)
        - coalesce(shares_issued_rsu_vested, 0)
        - coalesce(shares_from_conversion, 0)                      AS net_buyback_shares,
    filing_url
FROM financials
WHERE source = 'sec_edgar'
  AND fiscal_period = 'FY'
ORDER BY ticker, period_end DESC;

-- ── v_dilution_timeseries ──
CREATE OR REPLACE VIEW v_dilution_timeseries AS
SELECT
    ticker,
    period_end,
    fiscal_year,
    fiscal_period,
    coalesce(shares_outstanding, weighted_avg_shares_diluted,
             weighted_avg_shares_basic)                             AS shares_outstanding,
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
    round((shares_authorized
        - coalesce(shares_outstanding, weighted_avg_shares_diluted,
                   weighted_avg_shares_basic))
        / nullIf(coalesce(shares_outstanding, weighted_avg_shares_diluted,
                          weighted_avg_shares_basic), 0) * 100, 1) AS headroom_pct,
    revenue
FROM financials
WHERE source = 'sec_edgar'
  AND fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')
ORDER BY ticker, period_end ASC;
