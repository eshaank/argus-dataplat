-- 050_commodity_agg_views: Weekly, monthly, quarterly, yearly views from daily commodities_ohlcv

-- Weekly bars (Monday start)
CREATE OR REPLACE VIEW v_commodity_ohlcv_1wk AS
SELECT
    ticker,
    name,
    toMonday(date) AS date,
    argMin(open, date) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, date) AS close,
    sum(volume) AS volume
FROM commodities_ohlcv FINAL
GROUP BY ticker, name, toMonday(date)
ORDER BY ticker, date;

-- Monthly bars
CREATE OR REPLACE VIEW v_commodity_ohlcv_1mo AS
SELECT
    ticker,
    name,
    toStartOfMonth(date) AS date,
    argMin(open, date) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, date) AS close,
    sum(volume) AS volume
FROM commodities_ohlcv FINAL
GROUP BY ticker, name, toStartOfMonth(date)
ORDER BY ticker, date;

-- Quarterly bars
CREATE OR REPLACE VIEW v_commodity_ohlcv_3mo AS
SELECT
    ticker,
    name,
    toStartOfQuarter(date) AS date,
    argMin(open, date) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, date) AS close,
    sum(volume) AS volume
FROM commodities_ohlcv FINAL
GROUP BY ticker, name, toStartOfQuarter(date)
ORDER BY ticker, date;

-- Yearly bars
CREATE OR REPLACE VIEW v_commodity_ohlcv_1yr AS
SELECT
    ticker,
    name,
    toStartOfYear(date) AS date,
    argMin(open, date) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, date) AS close,
    sum(volume) AS volume
FROM commodities_ohlcv FINAL
GROUP BY ticker, name, toStartOfYear(date)
ORDER BY ticker, date;
