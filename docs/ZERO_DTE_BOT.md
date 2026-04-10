# Argus — 0DTE Options Trading Bot

**Version 1.0 | April 2026**

---

## 1. Executive Summary

The 0DTE bot is an autonomous intraday options trading system that trades zero-days-to-expiration contracts on SPY, QQQ, and IWM. Unlike the daily trading algorithm (which thinks overnight and acts once per morning), the 0DTE bot makes decisions every minute during market hours based on real-time gamma dynamics, underlying price action, and intraday volatility surface shifts.

The core thesis: market makers who sell 0DTE options must delta-hedge continuously. When aggregate dealer gamma exposure (GEX) is positive, hedging activity dampens moves — price mean-reverts around the highest-GEX strike. When GEX flips negative, hedging amplifies moves — breakouts accelerate. By modeling these dynamics in real time, the bot trades the predictable consequences of dealer positioning.

The 0DTE bot shares infrastructure with the daily algo (same ClickHouse cluster, same Schwab broker connection, same risk budget envelope) but has its own feature engine, strategy logic, execution loop, and risk limits.

---

## 2. Why 0DTE

0DTE options are the fastest-growing segment of the options market. SPY alone trades over 1 million 0DTE contracts per day. The opportunity exists because of a structural asymmetry:

**Gamma acceleration:** As expiration approaches, gamma on ATM options grows exponentially. A 0DTE ATM SPY option might have 10× the gamma of a 30DTE option at the same strike. This means small moves in SPY create massive delta changes in the option, forcing dealers to buy or sell the underlying aggressively to stay hedged.

**Predictable dealer behavior:** Market makers don't have discretion — they must hedge. When you can measure their aggregate positioning (GEX), you can anticipate what they'll be forced to do when price moves. Positive net GEX = they buy dips and sell rips (mean-reversion). Negative net GEX = they sell into dips and buy into rips (momentum amplification).

**Retail mispricing:** Most retail 0DTE traders are directional gamblers buying cheap OTM options. This creates a persistent implied vol premium (paid by buyers, earned by sellers) and skewed open interest that the bot can read and trade against.

**Time decay weaponization:** 0DTE options lose their entire time value by close. Theta decay is fastest in the final hours, making premium-selling strategies (iron condors, credit spreads) mechanically profitable when the underlying doesn't move beyond expected range — and GEX analysis tells us when that's likely.

---

## 3. Relationship to the Daily Algorithm

The 0DTE bot is not independent — it operates within the daily algo's risk framework:

| Shared with Daily Algo | 0DTE Bot's Own |
|----------------------|----------------|
| Regime detector (HMM Layer 2) — gates 0DTE activity | Intraday feature engine (minute-level) |
| Portfolio risk budget (0DTE carved out of total) | 5 specialized strategies |
| Schwab broker connection | Sub-minute execution loop |
| ClickHouse data infrastructure | Intraday-specific risk limits |
| Daily feature context (IV rank, GEX sign, Polymarket shock flag) | Real-time position management |

**Regime gating:** If the daily algo's HMM labels the current regime as "risk-off," the 0DTE bot does not trade at all. This prevents the bot from selling premium into a crash or buying vol into a dead market.

**Risk carve-out:** The 0DTE bot's risk budget (max 1% daily loss) is deducted from the daily algo's total portfolio risk allocation. The shared risk manager enforces this — the combined exposure from daily positions and 0DTE positions can never exceed the total portfolio limit.

---

## 4. Data Infrastructure

### 4.1 Data We Already Have

The daily algo's ClickHouse tables provide critical context for 0DTE decisions:

| Table | Content | 0DTE Use |
|-------|---------|----------|
| `option_chains` | 8 years of EOD option snapshots with greeks | Historical GEX patterns, IV surface modeling, backtest labels |
| `ohlcv` | 1-minute equity OHLCV (5 years, 3,000+ tickers) | Intraday price action, realized vol, overnight gap computation |
| `ohlcv_daily_mv` | Auto-aggregated daily bars | Session VWAP, expected daily range, gap analysis |
| `algo_regime_states` | Daily regime labels + probabilities (Layer 2) | Gate: suppress 0DTE in risk-off regimes |
| `algo_feature_matrix` | 43+ daily features + PCA (Layer 1) | IV rank, GEX sign, Polymarket shock flag — context for intraday decisions |
| `rates` | Fed funds, SOFR, Treasury yields | Risk-free rate for options pricing |
| `macro_daily` | VIX, USD, yield curve | Background vol expectations |

### 4.2 New Data Sources Required

| Data | Source | Resolution | Estimated Volume | Storage |
|------|--------|------------|-----------------|---------|
| Intraday option snapshots (SPY, QQQ, IWM) | Schwab API | 1-minute | ~15M rows/year | ClickHouse |
| Real-time underlying quotes | Schwab streaming API | Sub-second | In-memory only (not persisted) |
| Real-time option quotes (near-ATM) | Schwab API (if available) | Per-second | In-memory for execution; 1-min to ClickHouse |

**Scope:** Intraday snapshots are limited to strikes within 2–3% of the underlying price, for the current-day expiration (plus optionally next-day for term structure comparison). This keeps volume manageable — ~15 million rows/year versus billions in the full `option_chains` table.

**Historical depth:** Only 1–2 years of intraday backfill is needed. SPY daily expirations (Mon-Fri) began in April 2022; pre-2022 data is sparse and not representative of current 0DTE microstructure.

### 4.3 Ingestion Pipeline

The intraday option snapshot ingestion follows the same `dataplat` patterns as EOD ingestion:

```python
class SchwabIntradayOptionsIngestion(IngestPipeline):
    """
    Runs every 1 minute during market hours (9:30-4:00 ET).
    Pulls option chain snapshots for SPY, QQQ, IWM — limited to near-ATM strikes.
    """

    def extract(self) -> pl.DataFrame:
        # Schwab API: get_option_chain() for each underlying
        # Filter: strikes within 2-3% of current price, 0DTE expiration only
        ...

    def transform(self, raw: pl.DataFrame) -> pl.DataFrame:
        # Normalize column names, compute mid-price, validate greeks
        ...

    def load(self, df: pl.DataFrame) -> int:
        # INSERT into option_chains_intraday via ClickHouse client
        ...
```

For historical backfill, ThetaData provides minute-level option snapshots for SPY/QQQ/IWM. The backfill pipeline queries ThetaData's bulk API, transforms to the same schema, and loads into the same `option_chains_intraday` table.

---

## 5. ClickHouse Schema

### 5.1 `option_chains_intraday` — Minute-Level Option Snapshots

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

**Design notes:**
- `ReplacingMergeTree(ingested_at)` deduplicates on re-ingestion (idempotent backfills)
- Partitioned by underlying + month for efficient pruning (queries always filter on underlying + date range)
- `LowCardinality` on underlying and put_call for ~40% storage savings on these columns
- Delta/ZSTD compression (inherited from ClickHouse server config)

### 5.2 `zero_dte_trade_log` — Every 0DTE Trade

```sql
CREATE TABLE zero_dte_trade_log (
    date             Date,
    entry_time       DateTime64(3),
    exit_time        Nullable(DateTime64(3)),
    strategy         LowCardinality(String),  -- 'gex_pin', 'gamma_breakout', etc.
    underlying       LowCardinality(String),
    strike           Float64,
    put_call         LowCardinality(String),
    direction        LowCardinality(String),  -- 'buy' or 'sell'
    quantity         UInt32,
    entry_premium    Float64,
    exit_premium     Nullable(Float64),
    pnl              Nullable(Float64),
    hold_time_min    Nullable(UInt32),
    exit_reason      Nullable(String),         -- 'profit_target', 'stop_loss', 'time_stop', 'eod_exit'
    regime_at_entry  LowCardinality(String),
    gex_at_entry     Float64,
    iv_at_entry      Float64,
    schwab_order_id  Nullable(String),
    is_paper         Bool DEFAULT true,
    logged_at        DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(logged_at)
PARTITION BY toYYYYMM(date)
ORDER BY (date, entry_time, strategy, underlying, strike, put_call)
```

### 5.3 `zero_dte_session_summary` — Daily Rollup

```sql
CREATE TABLE zero_dte_session_summary (
    date                   Date,
    total_trades           UInt32,
    wins                   UInt32,
    losses                 UInt32,
    gross_pnl              Float64,
    net_pnl                Float64,    -- After commissions
    max_intraday_drawdown  Float64,
    max_concurrent_pos     UInt32,
    regime                 LowCardinality(String),
    strategies_used        Array(String),
    bot_uptime_min         UInt32,     -- Minutes the bot was active
    is_paper               Bool DEFAULT true,
    logged_at              DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(logged_at)
PARTITION BY toYear(date)
ORDER BY date
```

### 5.4 `zero_dte_features_snapshot` — Periodic Feature Snapshots

```sql
CREATE TABLE zero_dte_features_snapshot (
    date             Date,
    snapshot_time    DateTime64(3),
    underlying       LowCardinality(String),
    -- Gamma surface
    gex_net          Float64,
    gex_flip_strike  Float64,
    gex_imbalance    Float64,
    gamma_wall_dist  Float64,
    -- Vol surface
    iv_atm_0dte      Float64,
    iv_skew_0dte     Float64,
    iv_term_spread   Float64,
    iv_velocity      Float64,
    -- Price action
    price_vs_gex_flip Float64,
    vwap_distance    Float64,
    range_pct        Float64,
    momentum_5m      Float64,
    volume_surge     Float64,
    -- Context from daily algo
    daily_regime     LowCardinality(String),
    daily_iv_rank    Float64,
    daily_gex_sign   Int8,
    pm_shock_flag    Bool,
    logged_at        DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(logged_at)
PARTITION BY toYYYYMM(date)
ORDER BY (date, snapshot_time, underlying)
```

Feature snapshots are written every 5 minutes (not every minute) for debugging and strategy analysis without creating excessive volume.

---

## 6. Intraday Feature Engine

The feature engine computes a full feature vector every minute during market hours (9:30 AM – 4:00 PM ET). All features are computed in-memory from the latest option snapshot and kept in a rolling state object — only periodic snapshots are persisted to ClickHouse.

### 6.1 Gamma Surface Features

These features model the aggregate dealer positioning and its mechanical consequences.

| Feature | Computation | Signal |
|---------|-------------|--------|
| `gex_net_realtime` | Sum of (OI × gamma × contract_multiplier × spot) across all 0DTE strikes, sign-adjusted by put/call | Positive = dealer long gamma → mean-reversion. Negative = dealer short gamma → amplified moves |
| `gex_flip_strike` | The strike price where cumulative GEX flips from positive to negative | Key level — acts as a "magnet" (support/resistance) for intraday price action |
| `gex_imbalance` | Ratio of total call GEX to total put GEX | >1 = upward dealer hedging bias, <1 = downward bias |
| `gamma_wall_distance` | `(current_price - highest_GEX_strike) / current_price × 100` | How far price is from the "magnet." Larger distance = more potential energy for a snap-back |

**GEX computation detail:**

```python
# For each 0DTE contract:
gex_i = OI_i × gamma_i × 100 × spot_price

# Sign convention:
#   Call OI → dealers are short calls → long gamma → positive GEX
#   Put OI  → dealers are short puts  → short gamma → negative GEX
# (Assumes retail is net buyer of both puts and calls — validated by flow data)

net_gex = sum(gex_calls) - sum(gex_puts)
```

### 6.2 Volatility Surface Features

These features capture the intraday demand/supply for protection and the term structure of fear.

| Feature | Computation | Signal |
|---------|-------------|--------|
| `iv_atm_0dte` | Implied vol of the nearest-to-ATM 0DTE straddle (average of call and put IV at closest strike) | Current intraday fear level — spikes on unexpected events |
| `iv_skew_0dte` | IV at 25-delta put minus IV at 25-delta call (0DTE contracts) | Positive = demand for downside protection. Extreme values = panic buying puts |
| `iv_term_spread` | 0DTE ATM IV minus next-trading-day ATM IV | Negative (inversion) = intraday panic exceeds overnight risk. Signals short-term vol buying opportunity |
| `iv_velocity` | Rate of change in `iv_atm_0dte` over the last 5 minutes (linear regression slope) | Accelerating fear (rising) or complacency (falling). Triggers catalyst strategy entries |

**25-delta strike interpolation:** For 0DTE options, exact 25-delta strikes may not exist. The engine interpolates by finding the two closest strikes that bracket 0.25 delta and linearly interpolating their IVs.

### 6.3 Price Action Features

These features capture the underlying's intraday behavior relative to statistical anchors.

| Feature | Computation | Signal |
|---------|-------------|--------|
| `price_vs_gex_flip` | `(current_price - gex_flip_strike) / gex_flip_strike × 100` | Above zero = in positive gamma zone (mean-reversion likely). Below = negative gamma zone (breakout risk) |
| `vwap_distance` | `(current_price - session_VWAP) / session_VWAP × 100` | VWAP acts as a fair-value anchor. Large deviations in positive GEX regimes → mean-reversion setups |
| `range_pct` | `(session_high - session_low) / expected_daily_move × 100` | How much of the expected daily range has been "used." >80% = likely range-bound. <30% early = expansion likely |
| `momentum_5m` | Slope of linear regression on last 5 one-minute closes | Positive = short-term uptrend. Negative = short-term downtrend. Near zero = consolidation |
| `volume_surge` | `current_minute_volume / rolling_20min_avg_volume` | >2.0 = unusual activity. Combined with GEX, identifies breakout vs trap |

**Expected daily move computation:** `expected_move = spot × iv_atm_0dte × sqrt(minutes_remaining / 252 / 390)`. This decreases through the day as time shrinks.

### 6.4 Context Features (from Daily Algo)

Loaded once at session start (9:25 AM) from ClickHouse:

| Feature | Source | Signal |
|---------|--------|--------|
| `daily_regime` | `algo_regime_states` (Layer 2) | Risk-off → bot sits out entirely. Vol-expansion → favor long-vol strategies. Stable → favor premium selling |
| `daily_iv_rank` | `algo_feature_matrix` (Layer 1) | High IV rank = vol is expensive historically → premium selling has better edge |
| `daily_gex_sign` | `algo_feature_matrix` (Layer 1) | Confirms or contradicts the intraday GEX reading — divergence = caution |
| `pm_shock_flag` | `algo_feature_matrix` (Layer 1) | Polymarket detected an event risk → widen stops, reduce position sizes |

---

## 7. Trading Strategies

The bot runs five strategies concurrently. Each has independent entry conditions, position sizing, and exit logic. The risk manager prevents conflicting positions across strategies (e.g., no selling premium in one strategy while buying vol in another on the same underlying).

### 7.1 GEX Pin (Premium Selling)

**Thesis:** When net GEX is positive and price is near the GEX flip strike, dealer hedging creates a "pinning" effect. Price oscillates in a narrow range around the highest-GEX strike. Sell an iron condor with wings at ±1 standard deviation of the expected remaining move.

| Parameter | Value |
|-----------|-------|
| **Entry conditions** | `gex_net > 0`, `gamma_wall_distance < 0.3%`, `iv_velocity` near zero, `range_pct < 60%` |
| **Instrument** | 0DTE iron condor (sell ATM put + call, buy OTM wings) |
| **Wing width** | ±1σ of expected remaining daily move |
| **Position size** | Max 0.25% portfolio risk (defined by max loss on the condor) |
| **Profit target** | 50% of premium collected |
| **Stop loss** | Price moves beyond either wing strike |
| **Time stop** | Close at 2:30 PM regardless of P&L |
| **Regime gate** | Suppressed in risk-off or vol-expansion regimes |

### 7.2 Gamma Breakout (Vol Buying)

**Thesis:** When GEX flips negative and IV velocity is rising, dealer hedging amplifies moves rather than dampening them. Buy a 0DTE straddle at the GEX flip strike — the directional move will overwhelm theta decay.

| Parameter | Value |
|-----------|-------|
| **Entry conditions** | Price crosses `gex_flip_strike` from positive to negative GEX zone, `iv_velocity > 0`, `momentum_5m` aligned with breakout direction |
| **Instrument** | 0DTE straddle at the GEX flip strike |
| **Position size** | Max 0.25% portfolio risk (premium paid) |
| **Profit target** | 30% of premium paid |
| **Stop loss** | Price reverses back through GEX flip strike |
| **Time stop** | Close at 3:00 PM |
| **Regime gate** | Suppressed in stable regime (low expected vol) |

### 7.3 Morning Fade (Directional Premium Selling)

**Thesis:** Large overnight gaps (>0.5%) tend to fill in the first 30 minutes when GEX is positive. The dealer hedging flow that supports mean-reversion is strongest in the morning when OI is freshest. Sell 0DTE options against the gap direction.

| Parameter | Value |
|-----------|-------|
| **Entry conditions** | Overnight gap > 0.5%, first 15 min of session, `gex_net > 0`, `daily_regime` is stable or trending |
| **Instrument** | Sell 0DTE puts (if gap down) or calls (if gap up) at the gap-fill level strike |
| **Position size** | Max 0.2% portfolio risk |
| **Profit target** | Gap fills (underlying returns to previous close) |
| **Stop loss** | 1.5× premium received |
| **Time stop** | Close at 10:00 AM (30 min max hold) |
| **Regime gate** | Suppressed in risk-off regime |

### 7.4 VWAP Reversion (Directional Vol Buying)

**Thesis:** When price deviates >0.3% from VWAP in a positive GEX environment with normal volume, the deviation is likely to revert. Buy cheap 0DTE options in the direction of VWAP.

| Parameter | Value |
|-----------|-------|
| **Entry conditions** | `vwap_distance > 0.3%`, `gex_net > 0`, `volume_surge < 1.5` (no unusual activity driving the move) |
| **Instrument** | Buy 0DTE calls (if price below VWAP) or puts (if price above VWAP) at nearest ATM strike |
| **Position size** | Max 0.15% portfolio risk (premium paid) |
| **Profit target** | Price returns to VWAP ±0.05% |
| **Stop loss** | `vwap_distance > 0.6%` (deviation doubles instead of reverting) |
| **Time stop** | Close after 30 minutes |
| **Regime gate** | Suppressed in vol-expansion regime (strong trends don't revert) |

### 7.5 Catalyst Vol (Event-Driven Vol Buying)

**Thesis:** On CPI, FOMC, and NFP release days, implied vol spikes before the release and crushes afterward. Buy a 0DTE straddle 5 minutes before the release, sell into the post-release IV crush within 2 minutes.

| Parameter | Value |
|-----------|-------|
| **Entry conditions** | Known catalyst day (FOMC at 2 PM, CPI/NFP at 8:30 AM), `iv_term_spread` inverted, 5 minutes before release |
| **Instrument** | 0DTE ATM straddle |
| **Position size** | Max 0.25% portfolio risk |
| **Profit target** | Sell within 2 minutes of release (capture realized vol vs. IV crush) |
| **Stop loss** | 30% of premium paid |
| **Time stop** | Close within 10 minutes of release regardless |
| **Regime gate** | None — catalysts override regime gating (the event itself IS the trade) |

**Catalyst calendar:** Maintained as a static JSON file mapping dates to event types and release times. Updated monthly from the Fed calendar and BLS schedule.

---

## 8. Risk Management

The 0DTE bot has its own risk limits, stricter and separate from the daily algo. These are hard-coded circuit breakers — the bot cannot override them.

### 8.1 Position-Level Risk

| Constraint | Limit | Rationale |
|------------|-------|-----------|
| Max single trade risk | 0.25% of portfolio | 0DTE gamma is extreme; small sizing is mandatory |
| Max position delta | ±0.15% of portfolio (in underlying-equivalent terms) | Prevents outsized directional exposure |
| Required exit by 3:30 PM | All positions | Gamma acceleration in the last 30 min is unpredictable |

### 8.2 Session-Level Risk

| Constraint | Limit | Rationale |
|------------|-------|-----------|
| Max daily loss | 1% of portfolio | Hard stop — bot shuts down for the rest of the day |
| Max concurrent positions | 3 | Prevents overexposure to correlated intraday moves |
| Circuit breaker: 3 consecutive losses | Pause for 60 minutes | Prevents tilt-driven overtrading |
| No trading first 5 minutes | Cool-off | Opening cross creates artificial vol that decays immediately |

### 8.3 Portfolio-Level Risk (Shared with Daily Algo)

| Constraint | Limit | Rationale |
|------------|-------|-----------|
| Combined 0DTE + daily algo max drawdown | 3% of portfolio | Daily algo's risk manager enforces total — 0DTE is carved out |
| No conflicting positions | 0DTE can't sell vol on SPY if daily algo is long vol on SPY | Shared risk manager checks for cross-strategy conflicts |
| Regime gate | No 0DTE in risk-off regime | HMM risk-off label = the bot sits out entirely |
| Polymarket shock flag | Reduce position sizes by 50% when `pm_shock_flag = true` | Event risk detected — trade smaller |

### 8.4 Risk State Machine

The bot operates in one of four states:

```
ACTIVE → trading normally, all strategies eligible
THROTTLED → 2 consecutive losses, reduced position sizes (50%)
PAUSED → 3 consecutive losses, no new trades for 60 min
HALTED → daily loss limit hit, no more trading today
```

Transitions are one-directional within a session (ACTIVE → THROTTLED → PAUSED → HALTED). A win resets the consecutive loss counter but does NOT downgrade the state (PAUSED stays PAUSED until the 60-min timer expires).

---

## 9. Execution via Schwab API

### 9.1 Broker Integration

The 0DTE bot uses the `schwabdev` Python library for Schwab API access. Authentication is OAuth2 with automatic token refresh (handled by the library). The same Schwab connection is shared with the daily algo's execution layer.

```python
import schwabdev

client = schwabdev.Client(
    app_key=os.environ["SCHWAB_APP_KEY"],
    app_secret=os.environ["SCHWAB_APP_SECRET"],
    callback_url="https://127.0.0.1",
)
```

### 9.2 Order Types

| Strategy | Order Type | Details |
|----------|-----------|---------|
| GEX Pin (iron condor) | 4-leg combo limit order | All 4 legs submitted as a single order; limit price = net credit target |
| Gamma Breakout (straddle) | 2-leg combo limit order | ATM call + ATM put; limit price = combined debit |
| Morning Fade (single leg) | Single limit sell | Sell to open a single put or call |
| VWAP Reversion (single leg) | Single limit buy | Buy to open a single call or put |
| Catalyst Vol (straddle) | 2-leg combo limit order | Same as breakout but with tighter urgency (market if no fill in 30s) |

### 9.3 Fill Management

```
Submit order → Poll every 2s → Fill confirmed?
  Yes → Update position state, start monitoring
  No after 30s → Cancel and resubmit at adjusted price (1 retry)
  No after 60s → Abandon signal (opportunity cost < bad fill)
```

The 2–5 second Schwab polling latency is acceptable for strategies with 10-minute to 4-hour expected hold times. The bot does not attempt sub-second scalping.

### 9.4 Daily Execution Timeline

| Time (ET) | Action |
|-----------|--------|
| **9:25 AM** | Connect to Schwab, authenticate, load today's regime from ClickHouse |
| **9:30 AM** | Market open — begin ingesting intraday option snapshots |
| **9:35 AM** | Begin computing features (skip first 5 min cool-off) |
| **9:35 AM – 3:30 PM** | Main loop: every 1 min → pull snapshot → compute features → evaluate strategies → execute if signal |
| **On signal** | Submit order, log to `zero_dte_trade_log` |
| **On fill** | Update position state, begin monitoring exits |
| **Continuous** | Monitor open positions: check stop losses, profit targets, time stops |
| **3:30 PM** | Close all remaining positions (mandatory exit) |
| **3:30 – 3:45 PM** | No new trades. Monitor final P&L. |
| **3:45 PM** | Log daily session summary to `zero_dte_session_summary` |
| **3:50 PM** | Disconnect, flush logs |

### 9.5 Paper Trading Mode

The bot defaults to paper trading mode (`is_paper = true`). In paper mode:

- Orders are simulated locally (no Schwab API calls)
- Fills assume mid-price minus half the bid-ask spread (conservative slippage estimate)
- All trades are logged to ClickHouse identically to live trades (with `is_paper = true`)
- Session summaries are generated identically
- Risk limits are enforced identically — paper mode is a full production simulation

Live mode is enabled by setting `ZERO_DTE_LIVE=true` in the environment. This flag is checked at startup; it cannot be toggled mid-session.

---

## 10. Backtesting

### 10.1 Backtest Engine

The backtest engine replays minute-by-minute option snapshots from `option_chains_intraday`, running the identical feature engine and strategy logic as the live bot. The engine processes one session (trading day) at a time, resetting state at 9:30 AM and closing all positions at 3:30 PM.

```python
class ZeroDteBacktest:
    def run(self, start_date: date, end_date: date) -> BacktestResults:
        for trading_day in get_trading_days(start_date, end_date):
            snapshots = load_intraday_snapshots(trading_day)  # From ClickHouse
            regime = load_regime_state(trading_day)             # From algo_regime_states
            daily_features = load_daily_features(trading_day)   # From algo_feature_matrix

            session = SimulatedSession(regime, daily_features)
            for minute_snapshot in snapshots:
                features = self.feature_engine.compute(minute_snapshot)
                signals = self.strategy_engine.evaluate(features, session.positions)
                for signal in signals:
                    session.execute(signal, minute_snapshot)  # Simulated fill
                session.check_exits(minute_snapshot)

            session.force_close_all(snapshots[-1])  # 3:30 PM mandatory exit
            self.results.add_session(session)
```

### 10.2 Fill Simulation

Backtested fills use conservative assumptions:

| Parameter | Live | Backtest |
|-----------|------|----------|
| Fill price | Actual Schwab fill | Mid-price minus half spread |
| Slippage | Real | Additional 1 tick ($0.01) per leg |
| Commission | Schwab rate ($0.65/contract) | Same |
| Partial fills | Possible | Always full fill (conservative for selling premium) |
| Fill latency | 2–5 seconds | Instantaneous (optimistic — offset by worse fill price) |

### 10.3 Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Win rate | % of trades profitable | >55% for selling premium, >40% for buying vol |
| Profit factor | Gross profit / gross loss | >1.5 |
| Max intraday drawdown | Worst peak-to-trough in a single session | <0.5% of portfolio |
| Daily Sharpe | Mean daily P&L / std daily P&L (annualized) | >2.0 |
| Edge decay | Does win rate / profit factor degrade over time? | Flat or improving in walk-forward |
| Strategy correlation | Pairwise correlation of daily P&L between strategies | <0.5 (diversification) |

### 10.4 Walk-Forward Validation

The backtest uses rolling walk-forward windows (never look-ahead):

```
Training window: 60 trading days
Test window: 20 trading days
Step: 20 trading days

[Train 1-60] [Test 61-80]
             [Train 21-80] [Test 81-100]
                           [Train 41-100] [Test 101-120]
                           ...
```

Strategy parameters (wing width, profit targets, stop distances) are optimized on the training window and evaluated out-of-sample on the test window. Only strategies that show consistent out-of-sample performance are enabled in production.

---

## 11. Module Structure

All 0DTE code lives in `src/dataplat/algo/zero_dte/` within the existing `argus-dataplat` package:

```
algo/
├── zero_dte/
│   ├── __init__.py
│   ├── features.py         # Intraday feature engine
│   │                       #   GammaSurfaceFeatures: gex_net, gex_flip, gex_imbalance, gamma_wall_dist
│   │                       #   VolSurfaceFeatures: iv_atm, iv_skew, iv_term_spread, iv_velocity
│   │                       #   PriceActionFeatures: price_vs_gex, vwap_dist, range_pct, momentum, vol_surge
│   │                       #   ContextFeatures: regime, iv_rank, gex_sign, pm_shock (from daily algo)
│   │
│   ├── strategies.py       # Strategy definitions
│   │                       #   GexPinStrategy: iron condor in positive-GEX pinning zones
│   │                       #   GammaBreakoutStrategy: straddle on GEX flip to negative
│   │                       #   MorningFadeStrategy: sell premium against overnight gaps
│   │                       #   VwapReversionStrategy: buy cheap options on VWAP deviation
│   │                       #   CatalystVolStrategy: straddle before FOMC/CPI/NFP releases
│   │
│   ├── risk.py             # 0DTE-specific risk limits (separate from daily risk manager)
│   │                       #   RiskState: ACTIVE → THROTTLED → PAUSED → HALTED
│   │                       #   PositionLimits: max_single_trade, max_concurrent, max_daily_loss
│   │                       #   ConflictChecker: no conflicting vol/premium positions on same underlying
│   │
│   ├── execution.py        # Schwab order submission + position monitoring
│   │                       #   OrderBuilder: single, combo (straddle), multi-leg (iron condor)
│   │                       #   FillPoller: 2s polling, 30s cancel-resubmit, 60s abandon
│   │                       #   PositionTracker: real-time P&L, exit checks
│   │
│   ├── runner.py           # Main loop: connect → compute → decide → execute → log
│   │                       #   ZeroDteRunner.run(): market-hours loop (9:25 AM → 3:50 PM)
│   │                       #   Session state management, feature → strategy → risk → execution pipeline
│   │
│   ├── backtest.py         # Replay engine for historical minute snapshots
│   │                       #   ZeroDteBacktest: loads snapshots from ClickHouse, replays per-day
│   │                       #   SimulatedSession: paper fills, same risk logic as live
│   │                       #   WalkForwardValidator: rolling train/test windows
│   │
│   ├── config.py           # 0DTE configuration
│   │                       #   ZeroDteConfig: max_daily_loss, max_single_risk, max_concurrent_positions
│   │                       #   StrategyConfig: per-strategy params (wing_width, profit_target, etc.)
│   │                       #   CatalystCalendar: JSON schedule of FOMC/CPI/NFP dates + times
│   │
│   └── cli.py              # CLI entry point
│                           #   uv run python -m dataplat.algo.zero_dte.cli
│                           #   Subcommands: run (live loop), backtest, validate, status
│
└── ingestion/
    └── schwab/
        └── options_intraday.py   # Minute-level option snapshot ingestion pipeline
```

---

## 12. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SCHWAB_APP_KEY` | Yes | Schwab developer app key |
| `SCHWAB_APP_SECRET` | Yes | Schwab developer app secret |
| `ZERO_DTE_LIVE` | No (default: false) | Enable live trading (real Schwab orders) |
| `ZERO_DTE_TICKERS` | No (default: SPY,QQQ,IWM) | Comma-separated list of underlyings to trade |
| `ZERO_DTE_MAX_DAILY_LOSS` | No (default: 0.01) | Max daily loss as fraction of portfolio |
| `ZERO_DTE_MAX_SINGLE_RISK` | No (default: 0.0025) | Max single trade risk as fraction of portfolio |
| `ZERO_DTE_MAX_CONCURRENT` | No (default: 3) | Max concurrent positions |
| `CLICKHOUSE_HOST` | Yes | ClickHouse connection (shared with dataplat) |

All Schwab secrets are read from `.env` via `pydantic-settings` — never hardcoded.

---

## 13. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Bid-ask spread widening near close | Slippage exceeds modeled estimates | Mandatory exit by 3:30 PM; avoid OTM strikes after 2 PM |
| Gamma explosion on 0DTE positions | Rapid, outsized losses on directional moves | 0.25% max single trade risk; GEX sign gating suppresses entries in negative gamma zones |
| Schwab API latency (2–5s fill polling) | Stale position state, missed stop losses | Time-based stops in addition to price-based; conservative sizing accounts for latency |
| Flash crash / circuit breaker halt | Positions stuck during halt, resume at gap | Max daily loss circuit breaker at 1%; mandatory 3:30 PM exit prevents overnight exposure |
| Overfitting to recent 0DTE microstructure | Edge decays as market structure evolves | Walk-forward backtests with edge decay tracking; monthly strategy performance review |
| Correlated 0DTE and daily algo positions | Combined risk exceeds total portfolio limits | 0DTE risk budget carved out of daily algo limits; shared risk manager enforces total |
| Schwab API downtime during market hours | Can't close positions | Positions sized to survive any single-day move within risk budget; alert-on-disconnect |
| Intraday snapshot ingestion failure | Stale features, stale GEX | Feature engine tracks snapshot freshness; auto-pause if data is >2 min stale |
| Model assumes retail is net buyer | GEX sign convention breaks if institutional flow dominates | Cross-validate GEX direction with daily EOD data from `option_chains`; monthly calibration |

---

## 14. Implementation Roadmap

| Phase | Work | Milestone | Dependencies |
|-------|------|-----------|-------------|
| **0DTE-1** | Data ingestion | Schwab intraday option snapshot pipeline built, 1–2 years of SPY backfilled from ThetaData, ClickHouse migration applied | Schwab API access, ThetaData account |
| **0DTE-2** | Feature engine | Intraday feature engine computing all 4 feature groups (gamma, vol, price, context) from snapshots | 0DTE-1 |
| **0DTE-3** | Backtest engine | Replay engine running all 5 strategies against historical minute data, metrics dashboard | 0DTE-2 |
| **0DTE-4** | Strategy validation | Walk-forward results meet thresholds (>55% win rate selling, >1.5 profit factor). Non-performing strategies disabled | 0DTE-3 |
| **0DTE-5** | Paper trading | Live 0DTE bot running during market hours, logging to ClickHouse, no real orders. 30-day observation period | 0DTE-4, daily algo Phase 3 (regime gate) |
| **0DTE-6** | Live trading | Real 0DTE orders via Schwab with strict risk limits, 30-day ramp starting at 50% of target position sizes | 0DTE-5, manual review |

**Parallelism with daily algo:** 0DTE-1 (data ingestion) can begin immediately, in parallel with the daily algo's Phase 3 (regime detector). The 0DTE bot depends on the regime detector for its regime gate, so 0DTE-5 (paper trading) requires daily algo Phase 3 to be complete.

**Estimated timeline:** 0DTE-1 through 0DTE-4 is approximately 4–6 weeks of implementation. 0DTE-5 is a 30-day observation period. 0DTE-6 is a 30-day ramp. Total: ~3–4 months from start to live trading with real capital.

---

## 15. CLI Commands

```bash
# Run the bot (paper mode by default)
just zero-dte-run

# Run with live trading enabled
ZERO_DTE_LIVE=true just zero-dte-run

# Backtest a date range
just zero-dte-backtest --start 2024-01-01 --end 2024-12-31

# Walk-forward validation
just zero-dte-validate --start 2024-01-01 --end 2024-12-31

# Check bot status (last session summary)
just zero-dte-status

# Backfill intraday option snapshots from ThetaData
just ingest-intraday-options --start 2024-01-01 --end 2024-12-31 --tickers SPY,QQQ,IWM
```

---

**Current status:** Not started. Awaiting 0DTE-1 (data ingestion pipeline).
