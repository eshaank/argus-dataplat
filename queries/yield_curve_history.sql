-- Yield Curve History — spread with visual bar chart
-- Inverted curve (negative spread) historically precedes recessions

SELECT date,
    round(yield_1_year, 2) AS y1,
    round(yield_5_year, 2) AS y5,
    round(yield_10_year, 2) AS y10,
    round(yield_10_year - yield_1_year, 2) AS spread_1s10s,
    bar(yield_10_year - yield_1_year, -2, 3, 30) AS visual
FROM treasury_yields
WHERE date >= '2020-01-01' AND yield_1_year IS NOT NULL
ORDER BY date;
