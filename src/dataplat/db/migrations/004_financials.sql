-- 004_financials: Structured financial statements (replaces old fundamentals table)
-- Source: Polygon /vX/reference/financials
-- Wide table: income + balance sheet + cash flow + JSON overflow

DROP TABLE IF EXISTS fundamentals;

CREATE TABLE IF NOT EXISTS financials (
    -- Identifiers
    ticker                  LowCardinality(String),
    period_start            Date,
    period_end              Date,
    fiscal_year             String,
    fiscal_period           LowCardinality(String),
    timeframe               LowCardinality(String),
    filing_date             Nullable(Date),
    cik                     Nullable(String),

    -- Income Statement
    revenue                 Nullable(Float64),
    cost_of_revenue         Nullable(Float64),
    gross_profit            Nullable(Float64),
    operating_expenses      Nullable(Float64),
    operating_income        Nullable(Float64),
    net_income              Nullable(Float64),
    basic_eps               Nullable(Float64),
    diluted_eps             Nullable(Float64),
    basic_shares            Nullable(UInt64),
    diluted_shares          Nullable(UInt64),
    research_and_dev        Nullable(Float64),
    sga_expenses            Nullable(Float64),
    income_tax              Nullable(Float64),

    -- Balance Sheet
    total_assets            Nullable(Float64),
    current_assets          Nullable(Float64),
    noncurrent_assets       Nullable(Float64),
    total_liabilities       Nullable(Float64),
    current_liabilities     Nullable(Float64),
    noncurrent_liabilities  Nullable(Float64),
    total_equity            Nullable(Float64),
    long_term_debt          Nullable(Float64),
    inventory               Nullable(Float64),
    accounts_payable        Nullable(Float64),

    -- Cash Flow
    operating_cash_flow     Nullable(Float64),
    investing_cash_flow     Nullable(Float64),
    financing_cash_flow     Nullable(Float64),
    net_cash_flow           Nullable(Float64),

    -- Overflow + metadata
    raw_json                String,
    source                  LowCardinality(String) DEFAULT 'polygon',
    ingested_at             DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker, period_end, fiscal_period)
PARTITION BY toYear(period_end)
