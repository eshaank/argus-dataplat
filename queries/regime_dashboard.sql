-- Regime Dashboard — composite view of vol, yield curve, inflation, and jobs regimes
-- Run: just ch-query queries/regime_dashboard.sql

WITH
vol_regime AS (
    SELECT day,
        stddevPop(ret) OVER (ORDER BY day ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) * sqrt(252) * 100 AS vol
    FROM (
        SELECT day, log(close) - log(lagInFrame(close) OVER (ORDER BY day)) AS ret
        FROM ohlcv_daily_mv WHERE ticker = 'VIXY'
    )
),
curve AS (
    SELECT date,
        yield_10_year - yield_1_year AS spread_1s10s
    FROM treasury_yields
    WHERE yield_10_year IS NOT NULL AND yield_1_year IS NOT NULL
),
infl AS (
    SELECT date, cpi,
        cpi - lagInFrame(cpi, 12) OVER (ORDER BY date) AS cpi_yoy_change
    FROM inflation WHERE cpi IS NOT NULL
),
jobs AS (
    SELECT date, unemployment_rate,
        unemployment_rate - lagInFrame(unemployment_rate, 6) OVER (ORDER BY date) AS unemp_6m_delta
    FROM labor_market WHERE unemployment_rate IS NOT NULL
)
SELECT
    formatDateTime(toStartOfMonth(v.day), '%Y-%m') AS month,

    leftPad(toString(round(avg(v.vol), 1)), 6, ' ') AS vol,
    leftPad(multiIf(avg(v.vol) < 15, '▁ CALM',
                    avg(v.vol) < 25, '▃ NORMAL',
                    avg(v.vol) < 40, '▅ ELEVATED',
                    '▇ CRISIS'), 12, ' ') AS vol_regime,

    leftPad(toString(round(avg(c.spread_1s10s), 2)), 6, ' ') AS spread,
    leftPad(multiIf(avg(c.spread_1s10s) < -0.5, '◀◀ DEEP INV',
                    avg(c.spread_1s10s) < 0,     '◀  INVERTED',
                    avg(c.spread_1s10s) < 1,     '─▶ FLAT',
                    '──▶ STEEP'), 12, ' ') AS curve,

    leftPad(toString(round(max(i.cpi_yoy_change), 1)), 6, ' ') AS cpi,
    leftPad(multiIf(max(i.cpi_yoy_change) > 15, '██ HOT',
                    max(i.cpi_yoy_change) > 8,  '█░ WARM',
                    max(i.cpi_yoy_change) > 0,  '░░ STABLE',
                    '·· DEFLATION'), 14, ' ') AS cpi_regime,

    leftPad(concat(toString(round(max(j.unemployment_rate), 1)), '%'), 6, ' ') AS unemp,
    leftPad(multiIf(max(j.unemp_6m_delta) > 0.5, '↑ DETERIORATE',
                    max(j.unemp_6m_delta) > 0,   '↗ SOFTENING',
                    '↓ STRONG'), 14, ' ') AS jobs

FROM vol_regime v
LEFT JOIN curve c ON toStartOfMonth(v.day) = toStartOfMonth(c.date)
LEFT JOIN infl i ON toStartOfMonth(v.day) = toStartOfMonth(i.date)
LEFT JOIN jobs j ON toStartOfMonth(v.day) = toStartOfMonth(j.date)
WHERE v.day >= '2021-01-01'
GROUP BY month
ORDER BY month
FORMAT PrettyCompactMonoBlock
