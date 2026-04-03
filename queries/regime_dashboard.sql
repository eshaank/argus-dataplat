-- Regime Dashboard — composite view of vol, yield curve, inflation, and jobs regimes
-- Run in: just ch-shell

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
    toStartOfMonth(v.day) AS month,
    round(avg(v.vol), 1) AS avg_vol,
    multiIf(avg(v.vol) < 15, '🟢 LOW VOL',
            avg(v.vol) < 25, '🟡 NORMAL',
            avg(v.vol) < 40, '🟠 ELEVATED',
            '🔴 CRISIS') AS vol_regime,
    round(avg(c.spread_1s10s), 2) AS curve_spread,
    if(avg(c.spread_1s10s) < 0, '🔴 INVERTED', '🟢 NORMAL') AS curve_regime,
    round(max(i.cpi_yoy_change), 1) AS cpi_yoy,
    multiIf(max(i.cpi_yoy_change) > 15, '🔴 HOT',
            max(i.cpi_yoy_change) > 8, '🟠 WARM',
            max(i.cpi_yoy_change) > 0, '🟢 STABLE',
            '🔵 DEFLATION') AS inflation_regime,
    round(max(j.unemployment_rate), 1) AS unemp,
    multiIf(max(j.unemp_6m_delta) > 0.5, '🔴 DETERIORATING',
            max(j.unemp_6m_delta) > 0, '🟡 SOFTENING',
            '🟢 STRONG') AS jobs_regime
FROM vol_regime v
LEFT JOIN curve c ON v.day = c.date
LEFT JOIN infl i ON toStartOfMonth(v.day) = i.date
LEFT JOIN jobs j ON toStartOfMonth(v.day) = j.date
WHERE v.day >= '2022-01-01'
GROUP BY month
ORDER BY month;
