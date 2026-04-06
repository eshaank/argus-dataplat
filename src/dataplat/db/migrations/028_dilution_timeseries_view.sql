-- 028_dilution_timeseries_view: Time series of dilution metrics per ticker
-- Used by the Dilution tab to chart shares outstanding, SBC, etc. over time

CREATE OR REPLACE VIEW v_dilution_timeseries AS
SELECT
    ticker,
    period_end,
    fiscal_year,
    fiscal_period,
    shares_outstanding,
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
    round((shares_authorized - shares_outstanding)
        / nullIf(shares_outstanding, 0) * 100, 1)                  AS headroom_pct,
    revenue
FROM financials
WHERE source = 'sec_edgar'
  AND fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')
ORDER BY ticker, period_end ASC;
