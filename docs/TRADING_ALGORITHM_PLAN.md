# Argus — Autonomous Trading Algorithm

**Version 1.0 | April 2026**

---

## 1. Executive Summary

Argus is an autonomous options trading system built on top of an existing ClickHouse data infrastructure. The system ingests historical and real-time financial data, engineers predictive features, detects market regimes, generates trading signals, and executes options strategies on SPY and QQQ — all with automated risk management and position sizing.

The algorithm operates as a seven-layer pipeline, running on a daily schedule with intraday checkpoints. Each layer is a standalone Python module that reads from and writes to ClickHouse, enabling independent development, testing, and iteration.

**Core thesis:** Sell options premium in stable regimes (capturing theta decay and volatility risk premium), buy options in compression regimes (anticipating volatility expansion), and go directional in trending regimes — all gated by a quantitative risk manager that enforces strict portfolio limits.

---

## 2. Existing Data Infrastructure

The algorithm builds on an extensive data platform already in production. No new data sources are required for the initial deployment.

### 2.1 ClickHouse Tables


| Table             | Content                                            | Depth      | Resolution |
| ----------------- | -------------------------------------------------- | ---------- | ---------- |
| `ohlcv`           | Equity price bars (3,000+ tickers)                 | ~5 years   | 1-minute   |
| `ohlcv_daily_mv`  | Auto-aggregated daily bars                         | ~5 years   | Daily      |
| `option_chains`   | Full option snapshots with greeks (1st–3rd order)  | ~8 years   | EOD        |
| `rates`           | Fed funds, SOFR, TIPS, HY/IG OAS, CP 3M, T-bill 3M | Since 1954 | Daily      |
| `macro_daily`     | VIX, USD index, yield curve spreads, WTI crude     | Since 1976 | Daily      |
| `macro_weekly`    | Financial stress, NFCI, initial/continued claims   | Since 1971 | Weekly     |
| `macro_monthly`   | Sahm rule, M2, GDP, consumer sentiment, payrolls   | Since 1919 | Monthly    |
| `treasury_yields` | 1M through 30Y Treasury yields                     | Since 1962 | Daily      |
| `inflation`       | CPI, core CPI, PCE, core PCE                       | Since 1947 | Monthly    |
| `labor_market`    | Unemployment, participation, hourly earnings       | Since 1948 | Monthly    |


### 2.2 Materialized Views

ClickHouse materialized views auto-aggregate 1-minute bars into 5-min, 15-min, hourly, and daily resolutions on every INSERT. The algorithm exclusively uses the daily materialized view for feature computation, meaning zero manual aggregation overhead.

### 2.3 Data Platform Tooling

The `argus-dataplat` package provides: a Python ingestion framework (Schwab, Polygon, SEC EDGAR, FRED, ThetaData), a TypeScript SDK for typed read-only queries, a CLI for backfills, and a migration runner for schema changes. The trading algorithm extends this same package — same config, same ClickHouse client, same `just` task runner.

---

## 3. Pipeline Architecture

The system is organized as a seven-layer pipeline. Each layer is a self-contained Python module that reads inputs from ClickHouse and writes outputs back, creating a clean audit trail for every decision.


| Layer | Name                | Input                             | Output                                                   | Status    |
| ----- | ------------------- | --------------------------------- | -------------------------------------------------------- | --------- |
| 1     | Feature Engineering | Raw ClickHouse tables             | `algo_feature_matrix` (40+ features + 10 PCA components) | **Built** |
| 2     | Regime Detector     | PCA components from Layer 1       | Regime label, state probabilities, transition alerts     | Next      |
| 2.5   | Signal Model        | Regime outputs + raw features     | P(vol expansion), directional score, conviction          | Planned   |
| 3     | Decision Layer      | Regime + signals                  | Trade proposals (strategy, instrument, direction, size)  | Planned   |
| 4     | Risk Manager        | Trade proposals + portfolio state | Approved/rejected trades with reasons                    | Planned   |
| 5     | Execution           | Approved trades                   | Orders placed, fills confirmed, positions tracked        | Planned   |
| 6     | Orchestration       | Clock                             | Scheduled runs of Layers 1–5, logging, alerts            | Planned   |
| 7     | LLM News Agent      | Overnight news/earnings           | Structured sentiment/shock JSON score                    | Optional  |


---

## 4. Layer 1 — Feature Engineering (Built)

Layer 1 is fully implemented and operational. It computes 40+ daily features from ClickHouse and compresses them into 10 principal components via PCA. The pipeline processed 2 years of trading data (539 rows, 2023–2024) in ~80 seconds, with the 10 PCA components explaining 70.5% of variance.

### 4.1 Feature Groups

#### Options Features (SPY)

All options features are computed from the `option_chains` table, targeting SPY as the primary trading instrument.


| Feature                | Computation                              | Signal                                               |
| ---------------------- | ---------------------------------------- | ---------------------------------------------------- |
| `iv_rank`              | ATM IV percentile over trailing 252 days | Low = cheap options, high = expensive                |
| `iv_current`           | 30-DTE ATM implied volatility            | Current market fear level                            |
| `term_structure_slope` | Front-month IV minus back-month IV       | Positive = backwardation (fear)                      |
| `skew_25d`             | 25-delta put IV minus 25-delta call IV   | Higher = more demand for downside protection         |
| `gex_net`              | Net dealer gamma exposure                | Positive = vol suppression, negative = amplification |
| `gex_sign`             | Sign of GEX (+1, 0, −1)                  | Regime context for position sizing                   |
| `put_call_ratio`       | Put volume / call volume on SPY          | Sentiment gauge                                      |
| `vol_risk_premium`     | ATM IV minus 20-day realized vol         | Positive = options expensive vs realized             |


#### 0DTE Flow Features (SPY)

Zero-days-to-expiration options flow captures intraday speculative activity, particularly relevant for gamma exposure dynamics near expiration.


| Feature                | Computation                          |
| ---------------------- | ------------------------------------ |
| `zero_dte_put_volume`  | Same-day expiring put volume on SPY  |
| `zero_dte_call_volume` | Same-day expiring call volume on SPY |
| `zero_dte_pc_ratio`    | 0DTE put/call volume ratio           |


#### Equity / Price Features


| Feature             | Computation                        | Signal                            |
| ------------------- | ---------------------------------- | --------------------------------- |
| `overnight_gap`     | (Open − prev close) / prev close   | Gap-and-go or gap-and-fade setup  |
| `premarket_range`   | (High − Low) / prev close          | Pre-market volatility proxy       |
| `intraday_momentum` | Close-to-close 1-day return        | Trend continuation/exhaustion     |
| `realized_vol_5d`   | Annualized 5-day stdev of returns  | Short-term realized vol for VRP   |
| `realized_vol_20d`  | Annualized 20-day stdev of returns | Medium-term realized vol baseline |


#### Cross-Asset Features

Daily returns and 20-day rolling correlations across six ETFs that represent distinct asset classes. Correlation regime shifts (e.g., SPY-TLT flipping from negative to positive) are strong signals for risk-off environments.


| Feature                                                          | Computation                                    |
| ---------------------------------------------------------------- | ---------------------------------------------- |
| `ret_spy`, `ret_gld`, `ret_tlt`, `ret_hyg`, `ret_dbc`, `ret_uup` | Daily close-to-close returns for each ETF      |
| `corr_spy_tlt_20d`                                               | 20-day rolling Pearson correlation: SPY vs TLT |
| `corr_spy_gld_20d`                                               | 20-day rolling Pearson correlation: SPY vs GLD |
| `corr_spy_hyg_20d`                                               | 20-day rolling Pearson correlation: SPY vs HYG |


#### Polymarket Sentiment Features

Prediction market probabilities from Polymarket, providing real-money consensus estimates on binary events that drive vol shocks. These are additive signals — they provide context the decision layer can use but never override the risk manager.

The feature module queries the Polymarket CLOB API (or Gamma API) for a curated registry of event markets. Each market slug is mapped to a named feature. The registry requires manual curation when new markets appear (e.g., a new FOMC meeting, a new election cycle).

| Feature | Source | Computation |
|---------|--------|-------------|
| `pm_fed_cut_prob` | Polymarket CLOB | Probability of a Fed rate cut at next FOMC meeting |
| `pm_fed_hike_prob` | Polymarket CLOB | Probability of a Fed rate hike at next FOMC meeting |
| `pm_recession_prob` | Polymarket CLOB | Probability of US recession within 12 months |
| `pm_fed_cut_delta_7d` | Polymarket CLOB | 7-day change in Fed cut probability (momentum of repricing) |
| `pm_recession_delta_7d` | Polymarket CLOB | 7-day change in recession probability |
| `pm_shock_flag` | Polymarket CLOB | Boolean: did any tracked market move >15 percentage points in 24 hours |

**Staleness:** Polymarket markets trade 24/7, so data is always fresh. The staleness threshold is 24 hours. If the API is unreachable, all Polymarket features default to NaN and the pipeline continues without them — they are strictly additive.

**Why this matters:** FOMC probability shifts often lead VIX moves by 1-2 days. A sudden repricing of rate cut odds (e.g., from 80% to 40% in a week) signals that the market is about to reprice vol, which directly impacts the sell-premium vs buy-vol decision in Layer 3. Recession probability provides a slow-moving macro backdrop that confirms or contradicts the HMM's regime classification.

**Registry design:** A `PolymarketRegistry` dataclass maps market slugs to feature names, with expiration dates so stale markets are automatically dropped. New markets are added via config, not code changes.

#### Macro / FRED Features

Macro features handle mixed-frequency alignment: daily rates are direct, weekly data forward-fills up to 10 days, monthly data forward-fills up to 45 days. Every feature tracks staleness so the pipeline knows when it is operating on lagged data.


| Feature                   | Source Table    | Computation                                     |
| ------------------------- | --------------- | ----------------------------------------------- |
| `real_yield_10y`          | `rates`         | 10Y TIPS real yield                             |
| `real_yield_momentum_5d`  | `rates`         | 5-day change in 10Y TIPS yield                  |
| `yield_curve_10y2y`       | `macro_daily`   | 10Y − 2Y Treasury spread                        |
| `yield_curve_10y3m`       | `macro_daily`   | 10Y − 3M Treasury spread                        |
| `cp_stress_spread`        | `rates`         | Commercial paper 3M − T-bill 3M (credit stress) |
| `hy_oas`                  | `rates`         | High-yield option-adjusted spread               |
| `vix`                     | `macro_daily`   | CBOE VIX close                                  |
| `financial_stress`        | `macro_weekly`  | St. Louis Fed Financial Stress Index            |
| `financial_conditions`    | `macro_weekly`  | Chicago Fed National Financial Conditions Index |
| `sahm_rule`               | `macro_monthly` | Sahm Rule recession indicator                   |
| `jobless_claims_4wk_avg`  | `macro_weekly`  | 4-week moving average of initial claims         |
| `jobless_claims_momentum` | `macro_weekly`  | 13-week change in 4-week average claims         |


### 4.2 PCA Compression

All raw features are standardized (z-score) and compressed to 10 principal components using sklearn PCA. This serves three purposes: dimensionality reduction for the HMM (which struggles with >15 dimensions), decorrelation of inputs for LightGBM, and noise filtering (the tail components capture noise, not signal). In the initial backfill, 10 components captured 70.5% of total variance.

### 4.3 Staleness Tracking

Every feature row includes a `stale_features` array and a `feature_count` integer. Options and equity features flag as stale after 1 day without fresh data. Weekly macro features allow up to 10 days. Monthly features allow up to 45 days. Downstream layers (regime detector, signal model) can filter or down-weight rows with excessive staleness.

### 4.4 Module Structure

Layer 1 lives in `src/dataplat/algo/features/` with this structure:

- `base.py` — FeatureModule ABC, FeatureRow dataclass
- `registry.py` — @register decorator, module discovery
- `options.py` — 8 options features + 3 0DTE features
- `equity.py` — 5 equity/price features
- `macro.py` — 12 macro/FRED features
- `cross_asset.py` — 6 return features + 3 correlation features
- `polymarket.py` — 6 prediction market sentiment features
- `pipeline.py` — Orchestrator: runs all modules, PCA, writes to ClickHouse

### 4.5 Usage

```bash
# Backfill features for a date range
just compute-features --start 2023-01-01 --end 2024-12-31

# Compute today only (for the daily scheduler)
just compute-features --today

# Dry run (compute but don't write)
just compute-features --today --dry-run

# List all registered features
just compute-features --list
```

---

## 5. Layer 2 — Regime Detector (Next)

A Hidden Markov Model with Gaussian Mixture emissions (GMMHMM) trained on the PCA-compressed features. Standard Gaussian HMMs assume normal distributions, which misclassify fat-tailed financial returns. GMM emissions capture the kurtosis and skew inherent in market data.

### 5.1 Target Regimes


| Regime                         | Character                                                       | Typical Strategy                        |
| ------------------------------ | --------------------------------------------------------------- | --------------------------------------- |
| Low-vol trending               | VIX < 18, positive momentum, tight spreads, positive GEX        | Sell premium (iron condors, strangles)  |
| High-vol risk-off              | VIX > 25, negative momentum, widening spreads, negative GEX     | Buy puts, reduce exposure               |
| Vol compression / pre-breakout | VIX falling, IV rank < 20, term structure steep contango        | Buy vol (straddles, calendar spreads)   |
| Choppy / mean-reverting        | Range-bound price action, mixed signals, high correlation noise | Reduce size, short-dated credit spreads |
| Event / catalyst               | Transition alert firing, macro shock, earnings cluster          | Hold cash, hedge existing positions     |


### 5.2 Outputs

- **Regime label:** Integer ID mapped to a named regime (determined post-training by cluster inspection)
- **State probabilities:** Posterior probability for each regime (always sums to 1.0)
- **Transition alert:** Boolean — fires when the highest-probability regime changed from yesterday
- **Run length:** Days in the current regime (resets on transition)

### 5.3 Training Approach

The number of regimes (4–6) will be selected by BIC/AIC rather than hardcoded. Training uses multiple random initializations (20+) to avoid local optima, selecting the model with the best log-likelihood. The model is retrained monthly on a rolling 3-year window.

---

## 6. Layer 2.5 — Supervised Signal Model

A LightGBM gradient-boosted classifier trained on HMM outputs (state probabilities, transition alert, run length) combined with raw features. This layer bridges regime context with forward-looking predictions.

### 6.1 Labels (from ClickHouse)

- **Vol expansion 3d:** Did trailing realized vol expand >30% over the next 3 trading days? (Binary)
- **Vol expansion 5d:** Same metric over 5 trading days
- **Forward return sign:** Was the 5-day forward return positive or negative? (Binary)

Labels are computed from `ohlcv_daily_mv` with explicit alignment to avoid look-ahead bias. The 30% threshold is relative to the trailing 20-day realized vol as of the label date.

### 6.2 Outputs

- **P(vol expansion 3d):** Probability of vol expanding >30% over 3 days (0 to 1)
- **P(vol expansion 5d):** Same for 5-day horizon
- **Directional score:** Continuous score from −1 (bearish) to +1 (bullish)
- **Signal conviction:** Model confidence (0 to 1), derived from prediction margin

### 6.3 Validation

Walk-forward expanding window with 6+ folds (not fixed-split cross-validation, which leaks temporal structure). Exponential time-weighting to favor recent data. Feature importance stability across folds is tracked — if rankings shuffle dramatically, the model is fragile and should not be deployed.

---

## 7. Layer 3 — Decision Layer

Pure functions that take a `RegimeState` and `SignalOutput` and return a `TradeProposal`. No side effects, fully testable, fully backtestable independently from the models.

### 7.1 Regime-Conditional Rules


| Condition                                | Strategy                                     | Instruments                   |
| ---------------------------------------- | -------------------------------------------- | ----------------------------- |
| Low-vol trending + low P(vol expansion)  | Sell premium: iron condor or short straddle  | SPY 30-45 DTE, 16-delta wings |
| Vol compression + high P(vol expansion)  | Buy vol: long straddle or calendar spread    | SPY 14-30 DTE ATM             |
| High-vol risk-off + negative directional | Buy puts (directional)                       | SPY 20-30 DTE, 30-delta       |
| Transition alert firing                  | Reduce/hold: no new positions, tighten stops | N/A                           |
| Choppy + low conviction                  | Small credit spreads or sit out              | SPY 7-14 DTE, wide strikes    |


### 7.2 Position Sizing

Scaled Kelly criterion: base allocation = Kelly fraction, scaled by conviction score, capped at 2% portfolio risk per trade. In practice this means most trades risk 0.5–1.5% of portfolio. The transition alert decay window (configurable, default 3 days) determines how long positions stay reduced after a regime change.

---

## 8. Layer 4 — Risk Manager

Every trade proposal passes through the risk manager before execution. No exceptions. The risk manager is the final gate — it can reject or reduce any trade.

### 8.1 Portfolio Limits


| Constraint            | Limit            | Action on Breach                    |
| --------------------- | ---------------- | ----------------------------------- |
| Max portfolio vol     | 15% annualized   | Reject new trades until vol drops   |
| Max single trade risk | 2% of portfolio  | Scale down position size            |
| Max drawdown          | 8% from peak     | Pause ALL trading (circuit breaker) |
| Position correlation  | 70% pairwise max | Reject correlated additions         |
| Max open positions    | 8 concurrent     | Queue until a position closes       |


### 8.2 Drawdown Circuit Breaker

At 8% drawdown from equity peak, all new trading pauses. A 5-day cooling-off period begins. Trading resumes only if: (a) the cool-off period has elapsed, (b) current drawdown has recovered to <5%, and (c) the regime detector does not show risk-off. This prevents whipsaw re-entry during sustained drawdowns.

---

## 9. Layer 5 — Execution

Broker integration via the Schwab API (`schwabdev` library), which is already configured in the `dataplat` package with OAuth credentials. Schwab supports programmatic options orders including single legs, verticals, and multi-leg combos. Phase 1 targets paper trading only — all decisions are logged to ClickHouse without sending real orders.

### 9.1 Paper Trading Mode

A global `paper_mode` flag in the algo config. When True, the execution layer writes trade proposals and simulated fills to a `trade_log` table in ClickHouse but never calls the Schwab order API. Schwab does not have a dedicated paper trading environment (unlike IBKR), so this flag-based approach is the correct design. When ready for live trading, flipping the flag routes the same code path to real Schwab order endpoints.

### 9.2 Order Types

Phase 1: Single-leg options orders only (puts, calls). Phase 2: Vertical spreads as two legs. Phase 3: Multi-leg combos (iron condors as two vertical spreads submitted as separate verticals).

### 9.3 Schwab API Considerations

The Schwab API uses OAuth2 with a one-time browser login flow (already implemented in `dataplat.ingestion.schwab.client`). Order status is polled rather than streamed — this adds a few seconds of latency per fill check, which is acceptable for the daily algo (30-45 DTE positions) but becomes a factor for the 0DTE bot (see Section 16). The execution module reuses the existing `schwabdev` client and config singleton rather than introducing a second broker dependency.

---

## 10. Layer 6 — Orchestration Loop

A daily scheduler that runs the full pipeline at fixed times. Each run is idempotent — if a run crashes midway, the next run picks up cleanly because ClickHouse tables use ReplacingMergeTree.

### 10.1 Daily Schedule


| Time (ET) | Run                  | Purpose                                               |
| --------- | -------------------- | ----------------------------------------------------- |
| 6:00 AM   | Data refresh         | Pull overnight FRED updates, refresh feature matrix   |
| 9:00 AM   | Pre-market analysis  | Run regime detector + signal model on fresh features  |
| 9:25 AM   | Pre-open positioning | Run decision layer + risk manager, stage orders       |
| 3:45 PM   | EOD management       | Manage expiring positions, theta decay, stop losses   |
| 4:15 PM   | Post-close logging   | Log P&L, update portfolio state, write trade outcomes |


### 10.2 Failure Recovery

Every pipeline run writes a `run_id` and status to a runs table. If the 9:25 AM run fails, the 3:45 PM run checks for missing morning runs and executes them first. No double-counting of positions because the `trade_log` deduplicates on (date, strategy, instrument).

---

## 11. Layer 7 — LLM News Agent (Optional)

A Claude API call at market open that reads overnight news and earnings headlines, outputting a structured JSON with a sentiment score (−1 to +1) and a shock indicator (boolean). This feeds as an additive feature into the decision layer, never as a primary signal.

**Constraints:** The LLM score is clamped to −1/0/+1 with a confidence threshold. It cannot override the risk manager. If the API call fails or times out, the pipeline proceeds without it (the feature defaults to 0/neutral).

---

## 12. 0DTE Trading Bot

A separate, intraday trading system that operates on zero-days-to-expiration options for SPY, QQQ, and IWM. Unlike the daily algorithm (Layers 1–7), which thinks overnight and acts in the morning, the 0DTE bot makes decisions every few minutes during market hours based on real-time gamma dynamics, underlying price action, and intraday vol surface shifts.

The 0DTE bot shares the regime detector and risk manager with the daily algo but has its own feature engine, decision logic, and execution loop.

### 12.1 Why 0DTE

0DTE options are the fastest-growing segment of the options market. SPY alone trades over 1 million 0DTE contracts per day. The gamma exposure on these contracts is extreme — as expiration approaches, small moves in the underlying cause massive delta swings in the option, which forces dealers to hedge aggressively. This dealer hedging creates predictable intraday patterns (mean-reversion around GEX-pinned levels, breakouts when gamma flips negative) that a systematic bot can exploit.

Most retail traders approach 0DTE as a lottery ticket. The edge comes from treating it quantitatively: modeling the intraday gamma surface, tracking dealer positioning in real time, and sizing trades based on measured expected value rather than gut feel.

### 12.2 Data Requirements

#### What we already have

| Data | Source | Use |
|------|--------|-----|
| 8 years of EOD option chain snapshots | `option_chains` (ThetaData) | Historical GEX patterns, IV surface modeling, backtest labels |
| 1-minute equity OHLCV (5 years, 3,000+ tickers) | `ohlcv` | Intraday price action, realized vol, gap analysis |
| Daily regime state | `algo_regime_states` (Layer 2) | Gate: don't run 0DTE in risk-off regimes |
| FRED macro context | `algo_feature_matrix` (Layer 1) | Background context for vol expectations |

#### What we need to add

| Data | Source | Resolution | Estimated Volume |
|------|--------|------------|-----------------|
| Intraday option snapshots (SPY, QQQ, IWM) | Schwab API | 1-minute | ~50 strikes × 390 min × 252 days × 3 tickers = ~15M rows/year |
| Real-time underlying quotes | Schwab API streaming | Sub-second | In-memory only (not persisted) |
| Real-time option quotes (near-ATM) | Schwab API (if available) | Per-second | In-memory for execution, 1-min snapshots to ClickHouse |

The intraday option snapshot table is scoped to a narrow band: strikes within 2–3% of the underlying price, for expirations on the current day (and optionally the next day for comparison). This keeps the data volume manageable — ~15 million rows per year versus the billions in the full `option_chains` table.

Only 1–2 years of intraday backfill is needed. 0DTE options on SPY became liquid after the 2022 expansion to daily expirations (MWF → every trading day). Pre-2022 data is sparse and not representative of current market microstructure.

### 12.3 New ClickHouse Table

```sql
CREATE TABLE option_chains_intraday (
    underlying       LowCardinality(String),
    snapshot_time    DateTime64(3),           -- Minute-level timestamp
    expiration       Date,
    strike           Float64,
    put_call         LowCardinality(String),  -- 'put' or 'call'
    bid              Float64,
    ask              Float64,
    last             Float64,
    volume           UInt64,
    open_interest    UInt64,
    implied_vol      Float64,
    delta            Float64,
    gamma            Float64,
    theta            Float64,
    vega             Float64,
    underlying_price Float64,
    ingested_at      DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY (underlying, toYYYYMM(toDate(snapshot_time)))
ORDER BY (underlying, snapshot_time, expiration, strike, put_call)
```

### 12.4 Intraday Feature Engine

The 0DTE feature engine computes features every minute during market hours (9:30 AM – 4:00 PM ET). Features are computed in-memory from the latest snapshot — not written to ClickHouse on every tick.

#### Gamma Surface Features

| Feature | Computation | Signal |
|---------|-------------|--------|
| `gex_net_realtime` | Live GEX from current 0DTE open interest + gamma | Positive = dealer long gamma (mean-reversion), negative = amplified moves |
| `gex_flip_strike` | Strike price where GEX flips from positive to negative | Key support/resistance level for the day |
| `gex_imbalance` | Ratio of call GEX to put GEX | Directional bias in dealer hedging |
| `gamma_wall_distance` | Distance from current price to highest-GEX strike (%) | How far price is from the "magnet" |

#### Vol Surface Features

| Feature | Computation | Signal |
|---------|-------------|--------|
| `iv_atm_0dte` | ATM implied vol on 0DTE contracts | Current intraday fear level |
| `iv_skew_0dte` | 25-delta put IV minus 25-delta call IV (0DTE) | Intraday demand for downside protection |
| `iv_term_spread` | 0DTE ATM IV minus next-day ATM IV | Term structure inversion = intraday panic |
| `iv_velocity` | 5-minute rate of change in ATM IV | Accelerating fear (or complacency) |

#### Price Action Features

| Feature | Computation | Signal |
|---------|-------------|--------|
| `price_vs_gex_flip` | Current price relative to GEX flip strike | Above = positive gamma zone, below = negative |
| `vwap_distance` | Distance from current price to session VWAP (%) | Mean-reversion anchor |
| `range_pct` | Current session range as % of expected move | How much of the daily range has been used |
| `momentum_5m` | 5-minute price momentum (regression slope) | Short-term trend direction |
| `volume_surge` | Current minute volume vs 20-minute average | Unusual activity detection |

#### Context Features (from daily algo)

| Feature | Source | Signal |
|---------|--------|--------|
| `daily_regime` | `algo_regime_states` | Gate: suppress 0DTE in risk-off regimes |
| `daily_iv_rank` | `algo_feature_matrix` | Is vol cheap or expensive today? |
| `daily_gex_sign` | `algo_feature_matrix` | Daily-level dealer positioning context |
| `pm_shock_flag` | `algo_feature_matrix` | Polymarket event risk flag |

### 12.5 0DTE Strategies

| Strategy | Entry Condition | Entry | Exit | Typical Hold |
|----------|----------------|-------|------|-------------|
| **GEX Pin** | Price near GEX flip strike, positive net GEX, low IV velocity | Sell 0DTE iron condor (wings at ±1σ of expected remaining move) | 50% profit, or GEX flips negative, or 2:30 PM time stop | 1–4 hours |
| **Gamma Breakout** | Price breaks through GEX flip, negative net GEX, rising IV velocity | Buy 0DTE straddle at the flip strike | 30% profit, or momentum stalls (5m slope reverses), or 3:00 PM time stop | 15 min – 2 hours |
| **Morning Fade** | Large overnight gap (>0.5%), first 15 min of session, positive GEX | Sell 0DTE puts (if gap down) or calls (if gap up) at the gap fill level | Gap fills, or 30 min time stop, or stop loss at 1.5× premium | 10–30 min |
| **VWAP Reversion** | Price >0.3% from VWAP, positive GEX, low volume surge | Buy 0DTE options in the direction of VWAP | Price returns to VWAP ±0.05%, or 30 min time stop | 10–45 min |
| **Catalyst Vol** | CPI/FOMC/NFP day, pre-release window, IV term spread inverted | Buy 0DTE straddle 5 min before release | IV crush post-release (sell within 2 min), or stop loss at 30% of premium | 2–10 min |

### 12.6 0DTE Risk Controls

The 0DTE bot has its own risk limits, stricter and separate from the daily algo:

| Constraint | Limit | Rationale |
|------------|-------|-----------|
| Max daily loss | 1% of portfolio | Hard stop — bot shuts down for the rest of the day |
| Max single trade risk | 0.25% of portfolio | 0DTE positions are high-gamma; small sizing is mandatory |
| Max concurrent positions | 3 | Prevents overexposure to correlated intraday moves |
| No trading in risk-off regime | Gate from daily algo | If the HMM says risk-off, the 0DTE bot sits out entirely |
| Mandatory exit by 3:30 PM | Time-based | Gamma acceleration in the last 30 min is unpredictable |
| No trading first 5 min | Cool-off | Opening cross creates artificial vol that decays immediately |
| Circuit breaker: 3 consecutive losses | Pause 60 min | Prevents tilt-driven overtrading |

### 12.7 0DTE Execution via Schwab

The 0DTE bot requires a persistent process during market hours (not a cron job). The execution loop:

1. **9:25 AM** — Connect to Schwab API, authenticate, load today's regime state from ClickHouse
2. **9:35 AM** — Begin computing intraday features (skip first 5 min)
3. **Every 1 min** — Pull option snapshots, compute features, evaluate strategy conditions
4. **On signal** — Submit order via Schwab API, log to `zero_dte_trade_log` in ClickHouse
5. **On fill** — Poll Schwab for fill confirmation (2–5 second latency), update position state
6. **Continuous** — Monitor open positions, check stop losses, enforce time stops
7. **3:30 PM** — Close all remaining positions (mandatory exit)
8. **3:45 PM** — Log daily P&L, write session summary to ClickHouse

Schwab's order API supports limit orders on options which is sufficient for 0DTE. The 2–5 second fill polling latency is acceptable — we're not trying to scalp sub-second moves. The strategies target 10-minute to 4-hour holds where a few seconds of latency doesn't materially impact edge.

### 12.8 0DTE Backtesting

Backtesting 0DTE strategies requires the intraday option snapshot data (Section 12.3). The backtest engine replays minute-by-minute snapshots from ClickHouse, running the same feature engine and decision logic as the live bot. Fill simulation assumes mid-price minus half the bid-ask spread (conservative estimate of real slippage).

Key metrics tracked per backtest:

- **Win rate** — % of trades that are profitable (target: >55% for selling premium, >40% for buying vol)
- **Profit factor** — Gross profit / gross loss (target: >1.5)
- **Max intraday drawdown** — Worst peak-to-trough within a single session
- **Sharpe (daily)** — Daily P&L Sharpe ratio across all sessions
- **Edge decay** — Does the strategy degrade over time? (walk-forward check)

### 12.9 Module Structure

```
algo/
├── zero_dte/
│   ├── __init__.py
│   ├── features.py         # Intraday feature engine (gamma, vol surface, price action)
│   ├── strategies.py       # Strategy definitions (GEX pin, breakout, fade, reversion, catalyst)
│   ├── risk.py             # 0DTE-specific risk limits (separate from daily risk manager)
│   ├── execution.py        # Schwab order submission + position monitoring
│   ├── runner.py           # Main loop: connect → compute → decide → execute → log
│   ├── backtest.py         # Replay engine for historical minute snapshots
│   └── config.py           # 0DTE config (max loss, position limits, time stops)
├── ingestion/
│   └── schwab/
│       └── options_intraday.py   # Minute-level option snapshot ingestion
```

---

## 13. ClickHouse Schema Extensions

The trading algorithm adds tables for both the daily algo and the 0DTE bot.

### Daily Algo Tables

| Table                  | Purpose                                        | Key Columns                                                                   |
| ---------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------- |
| `algo_feature_matrix`  | Daily feature vectors + PCA (Layer 1 output)   | date, 40+ features, pc_1–pc_10, stale_features                                |
| `algo_regime_states`   | Regime labels + probabilities (Layer 2 output) | date, regime_id, regime_name, state_probs[], transition_alert, run_length     |
| `algo_signals`         | Model predictions (Layer 2.5 output)           | date, p_vol_exp_3d, p_vol_exp_5d, directional_score, conviction               |
| `algo_trade_log`       | Every decision + outcome (all layers)          | date, strategy, instrument, direction, size, fill_price, pnl, regime_at_entry |
| `algo_portfolio_state` | EOD portfolio snapshot                         | date, positions[], total_equity, drawdown, portfolio_vol                      |

### 0DTE Bot Tables

| Table                       | Purpose                                             | Key Columns                                                                           |
| --------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `option_chains_intraday`    | Minute-level option snapshots (SPY, QQQ, IWM)       | underlying, snapshot_time, expiration, strike, put_call, bid, ask, greeks, OI          |
| `zero_dte_trade_log`        | Every 0DTE trade decision + outcome                 | date, time, strategy, underlying, strike, put_call, direction, premium, pnl, hold_time |
| `zero_dte_session_summary`  | Daily rollup of 0DTE bot performance                | date, trades, wins, losses, gross_pnl, net_pnl, max_intraday_drawdown, regime         |
| `zero_dte_features_snapshot`| Periodic intraday feature snapshots (for debugging) | date, time, all intraday features (gamma, vol surface, price action)                  |


---

## 14. Module Structure

All algo code lives in `src/dataplat/algo/` within the existing argus-dataplat package:

```
algo/
├── features/                   # Layer 1: Feature engineering (built)
│   ├── base.py                 #   FeatureModule ABC, FeatureRow
│   ├── registry.py             #   @register decorator
│   ├── options.py              #   Options features (11 features)
│   ├── equity.py               #   Equity/price features (5 features)
│   ├── macro.py                #   Macro/FRED features (12 features)
│   ├── cross_asset.py          #   Cross-asset features (9 features)
│   ├── polymarket.py           #   Polymarket sentiment features (6 features)
│   └── pipeline.py             #   Orchestrator + PCA
├── regime/                     # Layer 2: HMM regime detector (next)
├── signals/                    # Layer 2.5: LightGBM classifier
├── decision/                   # Layer 3: Regime-conditional trade rules
├── risk/                       # Layer 4: Portfolio risk manager
├── execution/                  # Layer 5: Broker integration (Schwab API)
│   ├── broker.py               #   Abstract broker interface
│   ├── schwab.py               #   Schwab API implementation (schwabdev)
│   ├── paper.py                #   Paper trading (logs to ClickHouse)
│   └── orders.py               #   Order types, combo construction
├── orchestrator.py             # Layer 6: Daily scheduler
├── config.py                   # Algo configuration (paper_mode, thresholds, limits)
│
├── zero_dte/                   # 0DTE Bot (separate intraday system)
│   ├── features.py             #   Intraday feature engine (gamma, vol, price action)
│   ├── strategies.py           #   Strategy definitions (GEX pin, breakout, fade, etc.)
│   ├── risk.py                 #   0DTE-specific risk limits
│   ├── execution.py            #   Schwab order submission + position monitoring
│   ├── runner.py               #   Main loop: connect → compute → decide → execute
│   ├── backtest.py             #   Replay engine for minute snapshots
│   └── config.py               #   0DTE config (max loss, time stops, position limits)
│
└── ingestion/
    └── schwab/
        └── options_intraday.py  # Minute-level option snapshot ingestion
```

---

## 15. Risks & Mitigations

### Daily Algo Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Look-ahead bias in labels | Model appears profitable but fails live | Walk-forward validation only, explicit date alignment, no same-day features in labels |
| HMM overfitting to historical regimes | Misclassifies novel regime | BIC model selection, monthly retrain on rolling window, regime probability thresholds |
| Options slippage on live execution | Fills worse than backtested | Conservative fill assumptions in paper mode (mid minus 1 tick), wide strike selection |
| Correlated positions compounding losses | Effective risk exceeds limits | Pairwise correlation gate + portfolio-level VaR in risk manager |
| FRED data publication delays | Stale macro features | Staleness tracking flags stale features; regime detector down-weights stale inputs |
| Polymarket API downtime | Missing sentiment features | Features default to NaN; pipeline continues without them (strictly additive) |
| Schwab API rate limits | Missed order submissions | Exponential backoff + retry queue; daily algo has wide time windows between runs |

### 0DTE Bot Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Bid-ask spread widening near close | Slippage exceeds modeled estimates | Mandatory exit by 3:30 PM; avoid OTM strikes after 2 PM |
| Gamma explosion on 0DTE positions | Rapid, outsized losses on directional moves | 0.25% max single trade risk; GEX sign gating suppresses entries in negative gamma zones |
| Schwab API latency (2-5s fill polling) | Stale position state, missed stop losses | Time-based stops in addition to price-based; conservative sizing accounts for latency |
| Flash crash / circuit breaker halt | Positions stuck during halt, resume at gap | Max daily loss circuit breaker at 1%; mandatory 3:30 PM exit prevents overnight exposure |
| Overfitting to recent 0DTE microstructure | Edge decays as market structure evolves | Walk-forward backtests with edge decay tracking; monthly strategy performance review |
| Correlated 0DTE and daily algo positions | Combined risk exceeds total portfolio limits | 0DTE risk budget is carved out of daily algo limits; shared risk manager enforces total |

---

## 16. Implementation Roadmap

### Daily Algo Roadmap

| Phase | Layers | Milestone | Dependencies |
|-------|--------|-----------|-------------|
| **Phase 1 (complete)** | Layer 1 | Feature matrix backfilled, 539 rows, 70.5% PCA variance | None |
| Phase 2 | Layer 1 (additive) | Polymarket feature module integrated | Phase 1 + Polymarket API access |
| Phase 3 | Layer 2 | HMM trained, regimes validated against known market events | Phase 1 |
| Phase 4 | Layer 2.5 | LightGBM trained, walk-forward metrics meet thresholds | Phase 3 |
| Phase 5 | Layers 3 + 4 | Decision rules + risk manager, backtested 2023–2024 | Phase 4 |
| Phase 6 | Layers 5 + 6 | Paper trading live (Schwab) with daily scheduler, 30-day observation | Phase 5 |
| Phase 7 | Layer 5 (live) | Live trading with real capital (small allocation) | Phase 6 + manual review |
| Phase 8 (optional) | Layer 7 | LLM news agent integrated as additive signal | Phase 6 |

### 0DTE Bot Roadmap

| Phase | Work | Milestone | Dependencies |
|-------|------|-----------|-------------|
| 0DTE-1 | Data ingestion | Schwab intraday option snapshot pipeline built, 1-2 years backfilled for SPY | Schwab API access |
| 0DTE-2 | Feature engine | Intraday feature engine computing gamma surface, vol surface, price action features | 0DTE-1 |
| 0DTE-3 | Backtest engine | Replay engine running all 5 strategies against historical minute data, metrics tracked | 0DTE-2 |
| 0DTE-4 | Strategy validation | Walk-forward backtest results meet thresholds (>55% win rate selling, >1.5 profit factor) | 0DTE-3 |
| 0DTE-5 | Paper trading | Live 0DTE bot running during market hours, logging to ClickHouse, no real orders | 0DTE-4 + daily algo Phase 3 (regime gate) |
| 0DTE-6 | Live trading | Real 0DTE orders via Schwab with strict risk limits, 30-day ramp | 0DTE-5 + manual review |

The daily algo and 0DTE bot roadmaps are independent — 0DTE data ingestion (0DTE-1) can begin in parallel with daily algo Phase 3 (regime detector). The 0DTE bot depends on the daily algo's regime detector (Layer 2) for its regime gate, so 0DTE-5 (paper trading) requires daily algo Phase 3 to be complete.

**Current status:** Phase 1 complete. Ready to begin Phase 3 (regime detector) and Phase 2 (Polymarket features) in parallel.