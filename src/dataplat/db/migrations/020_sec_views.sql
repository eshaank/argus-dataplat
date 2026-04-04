-- 020_sec_views: Convenience views for SEC EDGAR data
-- Easy-win queries for dilution, filings by type, insider signals, etc.

-- ── Dilution Snapshot: latest annual dilution picture per company ──
CREATE OR REPLACE VIEW v_dilution_snapshot AS
SELECT
    ticker,
    period_end,
    shares_outstanding,
    shares_authorized,
    shares_authorized - shares_outstanding                          AS authorized_headroom,
    round((shares_authorized - shares_outstanding)
        / nullIf(shares_outstanding, 0) * 100, 1)                  AS headroom_pct,
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
    -- Total potential dilution as % of outstanding
    round((coalesce(warrants_outstanding, 0)
        + coalesce(options_outstanding, 0)
        + coalesce(unvested_rsu_shares, 0)
        + coalesce(antidilutive_shares, 0))
        / nullIf(shares_outstanding, 0) * 100, 1)                  AS total_dilution_pct,
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

-- ── Latest Financials: most recent annual snapshot per company ──
CREATE OR REPLACE VIEW v_latest_financials AS
SELECT *
FROM financials
WHERE source = 'sec_edgar'
  AND fiscal_period = 'FY'
  AND (ticker, period_end) IN (
      SELECT ticker, max(period_end)
      FROM financials
      WHERE source = 'sec_edgar' AND fiscal_period = 'FY'
      GROUP BY ticker
  );

-- ── Filings by Type: easy filtering of sec_filings ──
CREATE OR REPLACE VIEW v_filings_10k AS
SELECT * FROM sec_filings WHERE form_type IN ('10-K', '10-K/A', '20-F', '20-F/A')
ORDER BY ticker, filed_date DESC;

CREATE OR REPLACE VIEW v_filings_10q AS
SELECT * FROM sec_filings WHERE form_type IN ('10-Q', '10-Q/A')
ORDER BY ticker, filed_date DESC;

CREATE OR REPLACE VIEW v_filings_8k AS
SELECT * FROM sec_filings WHERE form_type IN ('8-K', '8-K/A')
ORDER BY ticker, filed_date DESC;

CREATE OR REPLACE VIEW v_filings_insider AS
SELECT * FROM sec_filings WHERE form_type IN ('4', '3', '5')
ORDER BY ticker, filed_date DESC;

CREATE OR REPLACE VIEW v_filings_institutional AS
SELECT * FROM sec_filings WHERE form_type IN ('SC 13G', 'SC 13G/A', 'SC 13D', 'SC 13D/A', 'SCHEDULE 13G', 'SCHEDULE 13G/A', 'SCHEDULE 13D', 'SCHEDULE 13D/A')
ORDER BY ticker, filed_date DESC;

CREATE OR REPLACE VIEW v_filings_registration AS
SELECT * FROM sec_filings WHERE form_type IN ('S-1', 'S-1/A', 'S-3', 'S-3ASR', 'S-3/A', 'S-8', 'S-8 POS', 'F-1', 'F-3')
ORDER BY ticker, filed_date DESC;

CREATE OR REPLACE VIEW v_filings_prospectus AS
SELECT * FROM sec_filings WHERE form_type LIKE '424B%'
ORDER BY ticker, filed_date DESC;

-- ── Insider Buy/Sell Signal: open market purchases and sales only ──
CREATE OR REPLACE VIEW v_insider_buys_sells AS
SELECT
    ticker,
    filed_date,
    report_date,
    reporter_name,
    reporter_title,
    transaction_type,
    shares,
    price,
    value,
    shares_owned_after,
    filing_url
FROM insider_trades
WHERE transaction_code IN ('P', 'S')
ORDER BY ticker, report_date DESC;

-- ── Insider Buying Aggregated: net insider buying per ticker per month ──
CREATE OR REPLACE VIEW v_insider_monthly AS
SELECT
    ticker,
    toStartOfMonth(report_date)                                     AS month,
    countIf(transaction_code = 'P')                                 AS buy_count,
    countIf(transaction_code = 'S')                                 AS sell_count,
    sumIf(value, transaction_code = 'P')                            AS buy_value,
    sumIf(value, transaction_code = 'S')                            AS sell_value,
    coalesce(sumIf(value, transaction_code = 'P'), 0)
        - coalesce(sumIf(value, transaction_code = 'S'), 0)         AS net_value,
    sumIf(shares, transaction_code = 'P')                           AS buy_shares,
    sumIf(shares, transaction_code = 'S')                           AS sell_shares
FROM insider_trades
WHERE transaction_code IN ('P', 'S')
GROUP BY ticker, month
ORDER BY ticker, month DESC;

-- ── Material Events Timeline: human-readable 8-K events ──
CREATE OR REPLACE VIEW v_events_timeline AS
SELECT
    ticker,
    filed_date,
    report_date,
    item_code,
    item_description,
    filing_url
FROM material_events
ORDER BY filed_date DESC, ticker;

-- ── Institutional Holders: latest filing per holder per ticker ──
CREATE OR REPLACE VIEW v_institutional_latest AS
SELECT
    ticker,
    holder_name,
    shares_held,
    class_percent,
    sole_voting_power,
    shared_voting_power,
    filed_date,
    form_type,
    filing_url
FROM institutional_holders
WHERE (ticker, holder_name, filed_date) IN (
    SELECT ticker, holder_name, max(filed_date)
    FROM institutional_holders
    GROUP BY ticker, holder_name
)
ORDER BY ticker, shares_held DESC
