-- 019_financials_v2: Recreate financials with dilution tracking + SEC filing links
-- Source: SEC EDGAR /api/xbrl/companyfacts/CIK{cik}.json
-- Replaces Polygon-sourced data with full EDGAR coverage

DROP TABLE IF EXISTS financials;

CREATE TABLE IF NOT EXISTS financials (
    -- Identifiers
    ticker                  LowCardinality(String),
    cik                     Nullable(String),
    period_start            Nullable(Date),
    period_end              Date,
    fiscal_year             String,
    fiscal_period           LowCardinality(String),   -- Q1, Q2, Q3, FY
    form_type               LowCardinality(String),   -- 10-K, 10-Q, 20-F
    filed_date              Nullable(Date),
    accession_number        Nullable(String),

    -- Income Statement
    revenue                 Nullable(Float64),
    cost_of_revenue         Nullable(Float64),
    gross_profit            Nullable(Float64),
    operating_expenses      Nullable(Float64),
    operating_income        Nullable(Float64),
    net_income              Nullable(Float64),
    basic_eps               Nullable(Float64),
    diluted_eps             Nullable(Float64),
    research_and_dev        Nullable(Float64),
    sga_expenses            Nullable(Float64),
    income_tax              Nullable(Float64),
    interest_expense        Nullable(Float64),
    ebitda                  Nullable(Float64),

    -- Balance Sheet
    total_assets            Nullable(Float64),
    current_assets          Nullable(Float64),
    noncurrent_assets       Nullable(Float64),
    total_liabilities       Nullable(Float64),
    current_liabilities     Nullable(Float64),
    noncurrent_liabilities  Nullable(Float64),
    total_equity            Nullable(Float64),
    retained_earnings       Nullable(Float64),
    long_term_debt          Nullable(Float64),
    short_term_debt         Nullable(Float64),
    cash_and_equivalents    Nullable(Float64),
    inventory               Nullable(Float64),
    accounts_receivable     Nullable(Float64),
    accounts_payable        Nullable(Float64),
    goodwill                Nullable(Float64),

    -- Cash Flow
    operating_cash_flow     Nullable(Float64),
    investing_cash_flow     Nullable(Float64),
    financing_cash_flow     Nullable(Float64),
    capex                   Nullable(Float64),
    dividends_paid          Nullable(Float64),
    depreciation_amortization Nullable(Float64),

    -- Dilution & Share Activity
    shares_outstanding      Nullable(Float64),         -- CommonStockSharesOutstanding
    shares_issued           Nullable(Float64),         -- CommonStockSharesIssued
    weighted_avg_shares_basic    Nullable(Float64),    -- WeightedAverageNumberOfSharesOutstandingBasic
    weighted_avg_shares_diluted  Nullable(Float64),    -- WeightedAverageNumberOfDilutedSharesOutstanding
    stock_based_compensation     Nullable(Float64),    -- ShareBasedCompensation
    buyback_shares          Nullable(Float64),         -- StockRepurchasedAndRetiredDuringPeriodShares
    buyback_value           Nullable(Float64),         -- PaymentsForRepurchaseOfCommonStock
    shares_issued_options   Nullable(Float64),         -- StockIssuedDuringPeriodSharesStockOptionsExercised
    shares_issued_rsu_vested Nullable(Float64),        -- RSUs vested in period
    unvested_rsu_shares     Nullable(Float64),         -- RSU overhang (unvested)
    antidilutive_shares     Nullable(Float64),         -- Out-of-money options excluded from EPS
    dividends_per_share     Nullable(Float64),         -- CommonStockDividendsPerShareDeclared
    issuance_proceeds       Nullable(Float64),         -- ProceedsFromIssuanceOfCommonStock

    -- Authorized Headroom
    shares_authorized       Nullable(Float64),         -- CommonStockSharesAuthorized
    preferred_shares_authorized Nullable(Float64),
    stock_plan_shares_authorized Nullable(Float64),
    buyback_program_authorized  Nullable(Float64),     -- $ authorized for repurchases

    -- Warrants
    warrants_outstanding    Nullable(Float64),         -- ClassOfWarrantOrRightOutstanding
    warrant_exercise_price  Nullable(Float64),
    warrant_shares_callable Nullable(Float64),         -- shares callable by warrants
    warrants_fair_value     Nullable(Float64),
    warrant_proceeds        Nullable(Float64),         -- proceeds from warrant exercises

    -- Convertible Debt
    convertible_debt        Nullable(Float64),         -- total convertible debt outstanding
    convertible_debt_current Nullable(Float64),
    convertible_conversion_price Nullable(Float64),
    convertible_conversion_ratio Nullable(Float64),
    convertible_debt_proceeds   Nullable(Float64),
    convertible_debt_repayments Nullable(Float64),
    shares_from_conversion  Nullable(Float64),         -- shares issued from conversions

    -- Options Pool
    options_outstanding     Nullable(Float64),
    options_exercisable     Nullable(Float64),
    options_weighted_avg_price Nullable(Float64),
    options_intrinsic_value Nullable(Float64),

    -- Filing link
    filing_url              String                  DEFAULT '',
    source                  LowCardinality(String)  DEFAULT 'sec_edgar',
    ingested_at             DateTime                DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker, period_end, fiscal_period)
PARTITION BY toYear(period_end)
