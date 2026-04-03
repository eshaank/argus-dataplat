# Queries

Saved ClickHouse queries for the dataplat analytical store. Run any of them in `just ch-shell`.

## Market / Regime

| File | Description |
|------|-------------|
| `regime_dashboard.sql` | Composite regime view — vol, yield curve, inflation, jobs |
| `cross_asset_correlation.sql` | Correlation matrix: stocks vs bonds vs gold vs dollar |
| `sector_rotation.sql` | Sector ETF performance relative to SPY |
| `beta_vs_spy.sql` | Beta and correlation of every ticker vs SPY |
| `overnight_gaps.sql` | Biggest overnight price gaps in last 30 days |
| `volatility_surface.sql` | Intraday volume profile by hour |

## Economy

| File | Description |
|------|-------------|
| `yield_curve_history.sql` | 10y-1y spread with visual bar chart |
| `real_yield.sql` | Nominal treasury minus inflation expectations |
| `macro_dashboard.sql` | Monthly snapshot: unemployment, CPI, yields, SPY, TLT, GLD |

## Fundamentals

| File | Description |
|------|-------------|
| `fundamentals_screener.sql` | PE, margins, leverage, FCF, R&D for all tickers |
| `earnings_risk_premium.sql` | Earnings yield vs 10yr treasury |
| `dividend_yield_ranking.sql` | Current dividend yield from latest payout + price |

## Usage

```bash
# Interactive
just ch-shell
# Then paste any query

# Or pipe directly
cat queries/regime_dashboard.sql | just ch-shell
```
