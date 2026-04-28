-- 034_commodity_eia_views: Convenience views for commodities + EIA petroleum data

-- Latest non-null price for each commodity (may come from different dates)
CREATE OR REPLACE VIEW v_commodity_latest AS
SELECT
    (SELECT toString(max(date)) FROM commodity_prices) AS date,
    (SELECT gold FROM commodity_prices WHERE gold IS NOT NULL ORDER BY date DESC LIMIT 1) AS gold,
    (SELECT silver FROM commodity_prices WHERE silver IS NOT NULL ORDER BY date DESC LIMIT 1) AS silver,
    (SELECT wti_crude FROM commodity_prices WHERE wti_crude IS NOT NULL ORDER BY date DESC LIMIT 1) AS wti_crude,
    (SELECT brent_crude FROM commodity_prices WHERE brent_crude IS NOT NULL ORDER BY date DESC LIMIT 1) AS brent_crude,
    (SELECT natural_gas FROM commodity_prices WHERE natural_gas IS NOT NULL ORDER BY date DESC LIMIT 1) AS natural_gas,
    (SELECT gasoline FROM commodity_prices WHERE gasoline IS NOT NULL ORDER BY date DESC LIMIT 1) AS gasoline,
    (SELECT heating_oil FROM commodity_prices WHERE heating_oil IS NOT NULL ORDER BY date DESC LIMIT 1) AS heating_oil,
    (SELECT copper FROM commodity_prices WHERE copper IS NOT NULL ORDER BY date DESC LIMIT 1) AS copper,
    (SELECT aluminum FROM commodity_prices WHERE aluminum IS NOT NULL ORDER BY date DESC LIMIT 1) AS aluminum,
    (SELECT wheat FROM commodity_prices WHERE wheat IS NOT NULL ORDER BY date DESC LIMIT 1) AS wheat,
    (SELECT corn FROM commodity_prices WHERE corn IS NOT NULL ORDER BY date DESC LIMIT 1) AS corn,
    (SELECT cotton FROM commodity_prices WHERE cotton IS NOT NULL ORDER BY date DESC LIMIT 1) AS cotton,
    (SELECT sugar FROM commodity_prices WHERE sugar IS NOT NULL ORDER BY date DESC LIMIT 1) AS sugar,
    (SELECT coffee FROM commodity_prices WHERE coffee IS NOT NULL ORDER BY date DESC LIMIT 1) AS coffee;

-- Brent-WTI spread (widens during international supply disruptions)
CREATE OR REPLACE VIEW v_brent_wti_spread AS
SELECT
    date,
    wti_crude,
    brent_crude,
    round(brent_crude - wti_crude, 2) AS spread,
    round((brent_crude - wti_crude) / wti_crude * 100, 2) AS spread_pct
FROM commodity_prices
WHERE wti_crude IS NOT NULL AND brent_crude IS NOT NULL
ORDER BY date;

-- Weekly petroleum: supply/demand balance + derived metrics
CREATE OR REPLACE VIEW v_petroleum_supply_demand AS
SELECT
    date,
    crude_production,
    crude_imports,
    crude_exports,
    round(crude_imports - crude_exports, 1) AS crude_net_imports,
    crude_stocks,
    spr_stocks,
    round(crude_stocks + spr_stocks, 1) AS total_stocks,
    product_supplied,
    gasoline_supplied,
    distillate_supplied,
    jet_fuel_supplied,
    refinery_utilization,
    refinery_inputs,
    -- Days of supply: commercial stocks / daily demand
    round(crude_stocks / greatest(product_supplied, 0.001), 1) AS days_of_supply,
    -- Week-over-week stock change
    round(crude_stocks - lagInFrame(crude_stocks) OVER (ORDER BY date), 1) AS crude_stocks_wow,
    round(spr_stocks - lagInFrame(spr_stocks) OVER (ORDER BY date), 1) AS spr_stocks_wow
FROM eia_petroleum_weekly
ORDER BY date;

-- Current stocks vs 5-year range for the same ISO week — the crisis indicator
CREATE OR REPLACE VIEW v_petroleum_stocks_vs_5yr AS
WITH
    current_year AS (SELECT toYear(max(date)) AS yr FROM eia_petroleum_weekly),
    weekly_stats AS (
        SELECT
            toISOWeek(date) AS iso_week,
            avg(crude_stocks) AS avg_stocks,
            min(crude_stocks) AS min_stocks,
            max(crude_stocks) AS max_stocks
        FROM eia_petroleum_weekly
        WHERE toYear(date) BETWEEN (SELECT yr - 5 FROM current_year) AND (SELECT yr - 1 FROM current_year)
          AND crude_stocks IS NOT NULL
        GROUP BY iso_week
    )
SELECT
    w.date,
    w.crude_stocks AS current_stocks,
    ws.avg_stocks AS five_yr_avg,
    ws.min_stocks AS five_yr_min,
    ws.max_stocks AS five_yr_max,
    round(w.crude_stocks - ws.avg_stocks, 1) AS vs_avg,
    round((w.crude_stocks - ws.avg_stocks) / ws.avg_stocks * 100, 2) AS vs_avg_pct
FROM eia_petroleum_weekly w
JOIN weekly_stats ws ON toISOWeek(w.date) = ws.iso_week
WHERE toYear(w.date) = (SELECT yr FROM current_year)
  AND w.crude_stocks IS NOT NULL
ORDER BY w.date;

-- OPEC share: each country's % of OPEC total + MoM change
CREATE OR REPLACE VIEW v_opec_share AS
SELECT
    date,
    opec_production,
    saudi_production,
    iran_production,
    iraq_production,
    uae_production,
    russia_production,
    us_production,
    world_production,
    round(saudi_production / greatest(opec_production, 0.001) * 100, 1) AS saudi_pct,
    round(iran_production / greatest(opec_production, 0.001) * 100, 1) AS iran_pct,
    round(iraq_production / greatest(opec_production, 0.001) * 100, 1) AS iraq_pct,
    round(uae_production / greatest(opec_production, 0.001) * 100, 1) AS uae_pct,
    -- MoM change
    round(opec_production - lagInFrame(opec_production) OVER (ORDER BY date), 1) AS opec_mom,
    round(iran_production - lagInFrame(iran_production) OVER (ORDER BY date), 1) AS iran_mom,
    round(us_production - lagInFrame(us_production) OVER (ORDER BY date), 1) AS us_mom
FROM eia_petroleum_monthly
WHERE opec_production IS NOT NULL
ORDER BY date;

-- Persian Gulf imports as % of total US crude imports — the Iran exposure metric
CREATE OR REPLACE VIEW v_persian_gulf_dependency AS
SELECT
    date,
    imports_persian_gulf,
    imports_total,
    round(imports_persian_gulf / greatest(imports_total, 0.001) * 100, 2) AS gulf_pct,
    round(imports_persian_gulf - lagInFrame(imports_persian_gulf) OVER (ORDER BY date), 1) AS gulf_mom,
    round(imports_total - lagInFrame(imports_total) OVER (ORDER BY date), 1) AS total_mom
FROM eia_petroleum_monthly
WHERE imports_total IS NOT NULL
ORDER BY date;
