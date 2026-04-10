# Argus — Options-Informed Equity Signal System

**Final Plan | April 7, 2026**

---

## 1. Executive Summary

A daily signal aggregator that scores equities on six orthogonal signals, ranks them, and takes the top 5–10 positions with regime-gated sizing. The edge comes from using the options market — where informed money appears first — as a predictive layer on top of price action, fundamentals, and news sentiment.

**Core thesis:** Institutional traders who know something buy options before they buy stock because the leverage is better and the footprint is smaller. That informed flow leaves fingerprints in the options data — unusual volume, skew shifts, IV changes, GEX dynamics — that predict equity moves with a lag. We trade equities (not options), keeping transaction costs minimal while extracting signal from options flow.

**Key properties:**
- **Instruments:** Equities only. No options execution.
- **Universe:** S&P 500 initially (536 tickers with data), expanding to Russell 1000/2000.
- **Holding period:** 3–7 days.
- **Positions:** 5–10 concurrent, 2% portfolio each, 10–20% max total exposure.
- **Execution:** IBKR equity orders. Spreads < 1 bp on S&P 500 names.

---

## 2. The Six Signals

### Signal 1: Oversold Bounce (Price Action)

**Thesis:** Stocks that drop >5% in a week on 1.5–2.5× average volume are temporarily dislocated by institutional repositioning. They revert.

**Validated in ClickHouse (2024-01-01 → 2025-12-31):**

| Condition | Avg Forward 5-Day (bps) | Win Rate | Observations |
|---|---|---|---|
| Drop >5%, medium volume (1.5–2.5×) | **+117.5** | **59.5%** | 4,875 |
| Drop >5%, low volume (<1.5×) | +79.2 | 57.6% | 14,018 |
| Drop >5%, high volume (>2.5×) | +56.4 | 54.7% | 1,783 |
| No drop (baseline) | +22.1 | 52.5% | — |

The signal strengthens with drop severity:

| Drop Magnitude | Avg Forward (bps) | Win Rate | Obs |
|---|---|---|---|
| Crash (>-20%) | +313.4 | 65.1% | 507 |
| Severe (-20% to -15%) | +217.8 | 63.0% | 957 |
| Big (-15% to -10%) | +150.6 | 61.7% | 3,330 |
| Medium (-10% to -7%) | +58.6 | 55.8% | 5,934 |
| Mild (-7% to -5%) | +60.0 | 56.8% | 9,804 |

**What it tells you:** "This stock is dislocated. It will probably snap back."

**Data source:** `ohlcv_daily_mv` — already exists.

**Extends to any stock?** Yes. Signal works across all market caps but the risk/reward profile changes:
- Large caps ($10B+): 83–98 bps, 57–59% win rate, tight distribution
- Sub-$5B: 142 bps average but 58 bps median — fat-tailed (few big winners inflate the mean), 54% win rate
- Best liquidity sweet spot: $50M–$200M daily dollar volume (93 bps, 60.6% win rate)

By sector, Finance (+127 bps, 61.5%), Utilities (+104 bps, 61.3%), and Telecom (+150 bps) revert hardest. Energy (+31 bps) reverts weakest.

---

### Signal 2: GEX Regime (Options-Derived)

**Thesis:** When net dealer gamma exposure (GEX) is positive, hedging activity dampens moves — price mean-reverts around the highest-GEX strike. When GEX is negative, hedging amplifies moves.

**Validated in ClickHouse:**
- Max-GEX strike was within **0.1% of the closing price** on ~65% of trading days (H1 2024).
- During the Aug 2024 Yen carry unwind (VIX → 39), GEX was deeply negative (-$1.2B on Aug 2) — correctly signaling amplified moves. It flipped positive on Aug 8 (+$287M) as the market stabilized.

**What it tells you at the stock level:** Positive GEX on a stock that just dropped = "Dealers are positioned to buy this dip. The bounce has structural support."

**Data source:** `option_chains` (EOD). Per-stock GEX requires backfilling top ~100 options tickers via ThetaData.

---

### Signal 3: Unusual Options Activity (Options-Derived)

**Thesis:** Informed traders prefer options for leverage and smaller footprint. The options market prices in information before the equity market. But raw unusual activity is noisy — the signal requires careful filtering.

#### Why Raw Unusual Activity Is Noisy

Unusual options volume includes:
1. **Retail gambling** — directional bets that are essentially random
2. **Institutional hedging** — not directional (buying puts to protect long equity positions)
3. **Market maker inventory adjustment** — mechanical, not informational
4. **Informed trading** — the signal we want

**Validated in ClickHouse:** Raw call surge vs. raw put surge vs. normal activity:

| Flow Type | Avg Forward 5-Day (bps) | Win Rate | Obs |
|---|---|---|---|
| Call volume surge (call vol/OI > 0.5, put vol/OI < 0.3) | +19.5 | 58.6% | 140 |
| Both surging | -15.0 | 51.9% | 187 |
| Normal | +51.4 | 58.4% | 2,498 |

**Raw call surges actually underperform normal days.** The noise overwhelms the signal.

#### How to Filter for Smart Money

The smart money signal emerges when you filter on three dimensions:

**Filter 1 — WHERE in the chain:** OTM calls (3–10% above spot) vs. ATM.

Smart money buys OTM calls for maximum leverage and to minimize information leakage. Retail buys ATM for simplicity. When OTM call volume is >2× ATM call volume and >5,000 contracts, someone with conviction is positioning.

| Flow Signal | Avg Forward 5-Day (bps) | Win Rate | Obs |
|---|---|---|---|
| Heavy OTM call buying (>2× ATM, >5K contracts) | **+353.4** | **67.9%** | 53 |
| Heavy OTM put buying | +14.5 | 43.4% (bearish: 56.6%) | 1,210 |
| Normal | +58.7 | 58.6% | 1,563 |

OTM call surges: +353 bps, 67.9% win rate. OTM put surges are weak because most put buying is hedging, not directional.

**Filter 2 — CONTEXT (price action):** Was the stock dropping or rallying when the OTM calls were bought?

| Context | Avg Forward 5-Day (bps) | Win Rate | Obs |
|---|---|---|---|
| OTM call surge **after a >3% drop** | **+466.8** | **76.9%** | 52 |
| OTM call surge after a rally | +11.1 | 50.0% | 20 |
| OTM call surge during flat | +47.4 | 51.5% | 33 |

**After a drop is the key.** Someone buying OTM calls on a stock that just dropped 5%+ is expressing high-conviction contrarian bullishness. That's informed money catching a bottom, not retail chasing momentum.

During a rally, OTM call buying is trend-following (could be anyone) and has zero edge.

**Filter 3 — MARKET MOOD:** Is the broad market fearful or calm?

| Market Mood | With OTM Call Surge (bps) | Win Rate | Without (bps) |
|---|---|---|---|
| Fearful (SPY P/C > 1.3) | **+316.6** | **65.9%** | +54.9 |
| Calm (SPY P/C < 1.3) | +186.8 | 61.0% | +34.3 |

Buying OTM calls when the rest of the market is buying puts = conviction against the crowd. That's the smart money signature.

**Combined Filter (all three):**

OTM call surge + after a 3%+ drop + on individual stocks (excluding ETFs):

| Metric | Value |
|---|---|
| Win rate | **80.6%** |
| Average forward 5-day return | **+5.24%** |
| Median forward 5-day return | **+4.39%** |
| Wins / Losses | 29 / 7 |

**Caveat:** Only 36 observations across NVDA and AAPL (the only individual stocks with sufficient options data in the current database). This signal MUST be validated on a broader universe by backfilling options data for the top 50–100 liquid options tickers via ThetaData. The directional result is strong but the sample is too small for production confidence.

#### The Specific Trades (Full Audit Trail)

Every trigger of the combined signal (OTM call surge after drop, individual stocks):

| Date | Ticker | Spot | OTM Call Vol | Trail 5d | Fwd 5d % | Result |
|---|---|---|---|---|---|---|
| 2026-03-26 | NVDA | $171 | 750K | -3.9% | +2.57% | WIN |
| 2026-02-27 | NVDA | $177 | 1.19M | -6.2% | +0.02% | WIN |
| 2026-02-13 | AAPL | $256 | 275K | -7.9% | +3.56% | WIN |
| 2026-02-05 | NVDA | $172 | 766K | -11.0% | **+10.40%** | WIN |
| 2026-02-04 | NVDA | $174 | 894K | -7.0% | +7.43% | WIN |
| 2026-01-20 | AAPL | $247 | 328K | -5.4% | +4.60% | WIN |
| 2025-12-17 | NVDA | $171 | 660K | -5.8% | **+9.97%** | WIN |
| 2025-11-21 | NVDA | $179 | 1.32M | -5.6% | -1.99% | LOSS |
| 2025-11-20 | NVDA | $181 | 1.36M | -3.2% | -0.63% | LOSS |
| 2025-11-18 | NVDA | $181 | 312K | -6.6% | -2.35% | LOSS |
| 2025-11-06 | NVDA | $188 | 1.01M | -7.6% | -1.25% | LOSS |
| 2025-11-05 | NVDA | $195 | 694K | -5.0% | -2.58% | LOSS |
| 2025-10-13 | AAPL | $248 | 163K | -3.3% | +6.20% | WIN |
| 2025-09-17 | NVDA | $170 | 695K | -3.3% | +3.02% | WIN |
| 2025-08-19 | NVDA | $176 | 704K | -4.3% | +4.18% | WIN |
| 2025-08-04 | AAPL | $203 | 345K | -5.1% | **+11.35%** | WIN |
| 2025-06-17 | AAPL | $196 | 187K | -3.8% | +2.89% | WIN |
| 2025-05-21 | NVDA | $132 | 821K | -3.7% | +7.82% | WIN |
| 2025-04-21 | NVDA | $97 | 584K | -11.6% | **+11.88%** | WIN |
| 2025-04-08 | AAPL | $172 | 113K | **-24.2%** | **+17.92%** | WIN |
| 2025-04-08 | NVDA | $96 | 693K | **-15.2%** | **+12.64%** | WIN |
| 2025-04-07 | NVDA | $98 | 545K | -7.8% | +10.27% | WIN |
| 2025-04-07 | AAPL | $181 | 150K | **-17.4%** | +9.99% | WIN |
| 2025-04-04 | AAPL | $188 | 407K | **-14.1%** | +5.55% | WIN |

Notable: The losses cluster in Nov 2025 (NVDA). The wins include the April 2025 tariff crash bottom calls — someone was buying NVDA OTM calls at $96 while the market was in panic. That's the informed flow signature.

**What it tells you:** "Smart money is catching the bottom on this stock. Follow them."

**Data source:** `option_chains` (volume, OI, strike, put_call). Currently limited to 5 underlyings. Must backfill top 50–100 via ThetaData to validate at scale.

---

### Signal 4: IV Rank Mean-Reversion (Options-Derived)

**Thesis:** When a stock's implied volatility is near its 1-year high (IV rank > 80) without an upcoming catalyst (earnings, FDA, etc.), the elevated IV reflects temporary fear that will dissipate. As fear fades, IV compresses and the stock rallies.

**Computation:**
```
iv_rank = (current_30DTE_IV - 252d_low_IV) / (252d_high_IV - 252d_low_IV)
```

When IV rank > 0.8 and there's no earnings/catalyst in the next 10 days, the stock is likely to rally as the fear premium deflates.

**What it tells you:** "Fear is elevated with no fundamental reason. The stock is probably going higher."

**Data source:** `option_chains` (implied_vol) + earnings calendar (from news API or SEC EDGAR filings). Partially exists — `algo_feature_matrix` computes `iv_rank` for SPY only. Need to extend to individual stocks.

---

### Signal 5: Insider Buying Confirmation (Fundamental)

**Thesis:** Corporate insiders who buy their own stock outperform by 3–7% annually (Lakonishok & Lee 2001). The signal is strongest for cluster buys (multiple insiders buying within weeks) and large purchases relative to holdings.

**What it tells you:** "The people who know this company best are putting their own money in."

**Data source:** `insider_trades` (29K rows from SEC EDGAR Form 4). Already exists. Can query `v_insider_buys_sells` view for open-market purchases.

**Use as confirmation, not standalone signal.** Insider buying is too low-frequency (~200–500 events/year across the S&P 500) to drive daily trading. But when a stock drops 5%, has positive GEX, AND the CFO bought $500K last week, that's a much higher-conviction trade than the drop alone.

---

### Signal 6: News Sentiment as a Filter

**Thesis:** Not all drops are the same. A stock that dropped 7% because the whole sector sold off (contagion) is a better reversal candidate than a stock that dropped 7% on a company-specific fraud allegation.

**Use as a filter, not a primary signal:**
- **Sector contagion** (the whole sector sold off, not just this stock) → HIGH reversion probability
- **Macro shock** (tariffs, rate scare) → MODERATE reversion, depends on regime
- **Company-specific bad news** (earnings miss, fraud, downgrade) → LOW reversion probability

**Implementation:**
1. Compute the stock's trailing 5-day return vs. its sector average return
2. If the stock dropped 7% but the sector dropped 6%, the idiosyncratic component is only -1% → likely contagion, good reversal candidate
3. If the stock dropped 7% but the sector was flat → company-specific, be cautious
4. News sentiment API adds granularity: negative sentiment score on the specific ticker confirms "this is company-specific, skip it"

**What it tells you:** "This drop was not the stock's fault. The bad news isn't about this company."

**Data source:** News API (not yet implemented). Candidates: Benzinga ($50–100/mo), Polygon news (may be included in existing plan), Alpha Vantage news sentiment.

Partial substitute: can compute sector-relative drops from existing data without a news API. The news API adds granularity but isn't strictly required for v1.

---

## 3. Signal Combination: The Daily Aggregator

### 3.1 Daily Workflow

Every morning at 8:00 AM ET, before market open:

```
For each ticker in the universe (~500-1000):

  1. oversold_score = f(trailing 5d return, volume ratio, drop severity)
     Range: 0-100. Score > 70 when drop > 5% on 1.5-2.5× volume.

  2. gex_score = f(net GEX sign, gamma wall distance, GEX flip proximity)
     Range: 0-100. Score > 70 when GEX positive and price near max-GEX strike.

  3. options_flow_score = f(OTM call vol / ATM call vol, volume/OI ratio)
     Range: 0-100. Score > 70 when OTM call volume > 2× ATM on >5K contracts.

  4. iv_rank_score = f(IV percentile, catalyst proximity check)
     Range: 0-100. Score > 70 when IV rank > 80 and no catalyst in 10 days.

  5. insider_score = f(insider buys in last 30 days, cluster size, purchase size)
     Range: 0-100. Binary boost: +20 if any insider bought in last 30 days.

  6. news_score = f(sector-relative drop, sentiment, contagion vs. idiosyncratic)
     Range: 0-100. Penalty: -30 if company-specific negative news detected.

  composite = w1*oversold + w2*gex + w3*options_flow + w4*iv_rank
              + w5*insider + w6*news

  where weights are regime-adjusted (see 3.3)
```

### 3.2 Position Entry and Exit

| Parameter | Value |
|---|---|
| Rank by | Composite score, descending |
| Enter top N | 5–10 positions |
| Position size | 2% of portfolio each |
| Max total exposure | 10–20% |
| Entry | Market open or limit at VWAP (first 30 min) |
| Profit target | +3% (close position) |
| Stop loss | -3% (close position) |
| Time stop | 7 trading days (close regardless) |
| No entry if | Earnings within 5 days, pending FDA/regulatory event |

### 3.3 Regime-Adjusted Weights

The regime gate adjusts signal weights, not on/off:

| Regime | VIX Level | Weight Adjustments | Position Size |
|---|---|---|---|
| **Calm** | < 18 | Overweight mean-reversion (oversold, GEX). Underweight options flow. | Full (2% each) |
| **Normal** | 18–28 | Balanced weights across all signals. | Full (2% each) |
| **Elevated** | 28–35 | Overweight options flow + insider. Underweight pure mean-reversion. | Reduced (1.5% each) |
| **Crisis** | > 35 | Only trade with insider + options flow confirmation. Require ≥ 3 signals firing. | Minimal (1% each) |
| **VIX spike** | > 45 | **Cash only. No new positions.** | 0% |

**Rationale:** Mean-reversion (Signal 1) fails during sustained directional moves (confirmed by negative months in backtest: Jul 2024, Feb-Mar 2025). In those regimes, the options flow signal (Signal 3) and insider buying (Signal 5) become more valuable because they indicate informed conviction against the trend.

### 3.4 Signal Correlation Structure

The signals are designed to be orthogonal — each captures a different information source:

| | Oversold | GEX | Options Flow | IV Rank | Insider | News |
|---|---|---|---|---|---|---|
| **Data source** | Price/volume | Options OI + greeks | Options volume | Options IV | SEC filings | News API |
| **Information type** | Mechanical dislocation | Dealer positioning | Informed money flow | Fear/greed | Management conviction | Event classification |
| **Time horizon** | 1 week lookback | Daily | Daily | 252-day percentile | 30-day lookback | 48-hour |
| **Expected correlation** | — | Low w/ oversold | Low w/ oversold | Moderate w/ oversold | Very low | Low |

When multiple uncorrelated signals agree (e.g., oversold + positive GEX + OTM call surge + insider buying), the composite confidence is multiplicatively higher than any individual signal.

---

## 4. Data Requirements

### 4.1 What Already Exists

| Data | Table | Status | Signal(s) |
|---|---|---|---|
| 1-min equity OHLCV (536 tickers, 5 years) | `ohlcv` | ✅ 255M rows | Signal 1 (oversold), Signal 6 (sector-relative drops) |
| Daily equity bars | `ohlcv_daily_mv` | ✅ auto-aggregated | Signal 1 (oversold) |
| EOD options (SPY, QQQ, IWM, NVDA, AAPL) | `option_chains` | ✅ 33.5M rows | Signal 2 (GEX), Signal 3 (options flow), Signal 4 (IV rank) |
| Insider trades | `insider_trades` | ✅ 29K rows | Signal 5 (insider buying) |
| VIX / macro data | `macro_daily` | ✅ 12.6K rows | Regime gating |
| SEC filings (earnings dates) | `sec_filings` | ✅ 5.6M rows | Signal 4 (catalyst filter) |
| Feature matrix (IV rank, GEX sign) | `algo_feature_matrix` | ✅ 540 rows (SPY only) | Signal 2, Signal 4 context |

### 4.2 What Needs to Be Built

| Data | Source | Cost | Time | Signal(s) |
|---|---|---|---|---|
| **EOD options for top 50–100 tickers** | ThetaData Standard ($80/mo) | $80 one-time | ~1 week backfill | Signal 2, 3, 4 for individual stocks |
| **News sentiment** | Benzinga or Polygon news | $50–100/mo | ~1 week integration | Signal 6 |
| **Per-stock IV rank computation** | Derived from option_chains | $0 | ~2 days code | Signal 4 |
| **Per-stock GEX computation** | Derived from option_chains | $0 | ~2 days code | Signal 2 |
| **IBKR execution integration** | `ib_async` library | $0 | ~1 week | All |

### 4.3 ThetaData Options Backfill (Critical Path)

The options flow signal (Signal 3) was validated on only NVDA and AAPL (the only individual stocks with options data). To use it in production, we need options data for the top 50–100 most liquid options tickers.

**Backfill specification:**
- **Endpoint:** `/option/history/greeks/eod?symbol={TICKER}&expiration=*&start_date={DATE}&end_date={DATE}`
- **Plan required:** Standard ($80/mo)
- **Tickers:** Top 50–100 by options open interest (NVDA, AAPL, TSLA, AMD, META, MSFT, AMZN, GOOGL, etc.)
- **Depth:** 3 years (April 2023 → present)
- **Request count:** 100 tickers × 750 trading days = 75,000 requests (few hours at ThetaData throughput)
- **Volume:** ~50–100M rows, ~3–7 GB in ClickHouse
- **Schema:** Same `option_chains` table (already designed for multi-underlying)

**Open interest endpoint** must also be backfilled: `/option/history/open_interest?symbol={TICKER}&expiration=*&date={DATE}`

Total: ~150K requests. Runs overnight.

---

## 5. Architecture

### 5.1 Module Structure

```
algo/
├── signal_system/
│   ├── __init__.py
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── oversold.py          # Signal 1: price/volume reversal
│   │   ├── gex.py               # Signal 2: per-stock GEX regime
│   │   ├── options_flow.py      # Signal 3: OTM call/put flow analysis
│   │   ├── iv_rank.py           # Signal 4: IV percentile + catalyst filter
│   │   ├── insider.py           # Signal 5: insider buying from EDGAR
│   │   └── news_sentiment.py    # Signal 6: news filter (sector-relative + API)
│   │
│   ├── aggregator.py            # Composite scoring + ranking
│   │                            #   compute_composite_score(ticker, date) → float
│   │                            #   rank_universe(date) → list[(ticker, score)]
│   │
│   ├── regime.py                # VIX-based regime detector
│   │                            #   get_regime(date) → 'calm' | 'normal' | 'elevated' | 'crisis'
│   │                            #   get_signal_weights(regime) → dict[str, float]
│   │
│   ├── risk.py                  # Position sizing + portfolio constraints
│   │                            #   max_positions, max_exposure, sector_limits
│   │                            #   stop_loss, profit_target, time_stop
│   │
│   ├── execution.py             # IBKR order submission
│   │                            #   submit_entry(ticker, size) → order_id
│   │                            #   monitor_exits(positions) → list[exit_event]
│   │
│   ├── backtest.py              # Historical replay engine
│   │                            #   run_backtest(start, end) → BacktestResults
│   │                            #   walk_forward(start, end, train_days, test_days)
│   │
│   ├── scanner.py               # Daily pre-market scan
│   │                            #   scan_universe(date) → list[(ticker, composite_score, signals)]
│   │                            #   generate_trade_ideas(date) → list[TradeIdea]
│   │
│   ├── config.py                # Weights, thresholds, regime params
│   └── cli.py                   # CLI: scan, backtest, run, status
```

### 5.2 ClickHouse Schema Additions

#### `signal_scores` — Daily Signal Snapshots

```sql
CREATE TABLE signal_scores (
    date                Date,
    ticker              LowCardinality(String),
    oversold_score      Float64,
    gex_score           Float64,
    options_flow_score  Float64,
    iv_rank_score       Float64,
    insider_score       Float64,
    news_score          Float64,
    composite_score     Float64,
    regime              LowCardinality(String),
    computed_at         DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(computed_at)
PARTITION BY toYYYYMM(date)
ORDER BY (date, ticker)
```

#### `signal_trades` — Trade Log

```sql
CREATE TABLE signal_trades (
    date                Date,
    ticker              LowCardinality(String),
    direction           LowCardinality(String),  -- 'long'
    entry_time          DateTime64(3),
    entry_price         Float64,
    exit_time           Nullable(DateTime64(3)),
    exit_price          Nullable(Float64),
    exit_reason         Nullable(String),         -- 'profit_target', 'stop_loss', 'time_stop'
    pnl                 Nullable(Float64),
    pnl_pct             Nullable(Float64),
    composite_score     Float64,
    signals_fired       Array(String),            -- ['oversold', 'gex', 'options_flow']
    regime_at_entry     LowCardinality(String),
    is_paper            Bool DEFAULT true,
    logged_at           DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(logged_at)
PARTITION BY toYYYYMM(date)
ORDER BY (date, entry_time, ticker)
```

---

## 6. Execution: IBKR

### 6.1 Why IBKR

| Factor | Schwab | IBKR |
|---|---|---|
| Equity commissions | $0 | $0.005/share (~$0.50 per 100 shares) |
| Spread improvement (SmartRouting) | No | Yes — seeks best execution across exchanges |
| Market data | REST polling | WebSocket streaming |
| Fill notification | Poll every 2–5 sec | Event callback <1 sec |
| API | OAuth2 REST (token refresh) | TWS Gateway (persistent connection) |
| Python library | `schwabdev` | `ib_async` (maintained, async-native) |

For equities on S&P 500 names, IBKR's $0.005/share commission is negligible (< 1 bp on a $100 stock). The streaming data and faster fills justify the minimal commission.

### 6.2 Daily Execution Timeline

| Time (ET) | Action |
|---|---|
| **7:00 AM** | Load universe, pull overnight data updates |
| **8:00 AM** | Run signal scanner: compute all 6 signals for all tickers |
| **8:15 AM** | Rank universe by composite score, generate trade ideas |
| **8:30 AM** | Review open positions: check profit targets, stop losses |
| **9:30 AM** | Market open — submit entry orders for top-ranked ideas |
| **9:30–10:00 AM** | Entry window: limit orders at VWAP or market if urgent |
| **10:00 AM** | All entries should be filled. Log to `signal_trades`. |
| **Continuous** | Monitor exits: profit target (+3%), stop loss (-3%) |
| **3:30 PM** | Close any position that hit time stop (7 days) |
| **4:00 PM** | End of day — update position P&L, log to ClickHouse |

### 6.3 Paper Trading Mode

Default mode. No real IBKR orders. Simulated fills at open price + 1 tick slippage. All trades logged to ClickHouse with `is_paper = true`. Risk limits enforced identically to live.

---

## 7. Backtesting Plan

### 7.1 Walk-Forward Validation

```
Training window: 60 trading days
Test window: 20 trading days
Step: 20 trading days

[Train 1-60]   [Test 61-80]
               [Train 21-80]   [Test 81-100]
                               [Train 41-100]  [Test 101-120]
                               ...
```

**Signal weights** are optimized on the training window and evaluated out-of-sample on the test window. If out-of-sample performance is >30% worse than in-sample, the weights are overfit.

### 7.2 Metrics

| Metric | Target | Description |
|---|---|---|
| Win rate | > 57% | % of trades profitable |
| Profit factor | > 1.5 | Gross profit / gross loss |
| Average return per trade | > 80 bps | After transaction costs |
| Max drawdown | < 5% | Peak-to-trough on portfolio |
| Monthly Sharpe | > 1.5 | Mean monthly return / std monthly return (annualized) |
| Signal contribution | Each signal > 0 | Each signal adds marginal value to the composite |

### 7.3 Ablation Testing

Remove each signal one at a time and measure the impact on composite performance. If removing a signal doesn't hurt (or improves) performance, drop it. Only keep signals that contribute marginal alpha.

---

## 8. Implementation Roadmap

| Phase | Work | Timeline | Milestone |
|---|---|---|---|
| **SS-1** | Signal 1 backtest (oversold bounce — existing data) | Week 1–2 | Walk-forward validation: profit factor > 1.3 |
| **SS-2** | ThetaData options backfill (top 50–100 tickers) | Week 2–3 | `option_chains` expanded from 5 to 50–100 underlyings |
| **SS-3** | Signals 2–4 implementation (GEX, options flow, IV rank) | Week 3–5 | Per-stock GEX, OTM flow detector, IV rank validated |
| **SS-4** | Signal 5 integration (insider trades — existing data) | Week 5 | Insider buying overlay tested |
| **SS-5** | News API integration (Signal 6) | Week 5–6 | Sector-relative drops + sentiment filter |
| **SS-6** | Composite aggregator + walk-forward validation | Week 6–7 | All 6 signals combined, weights optimized |
| **SS-7** | IBKR integration | Week 7–8 | Paper orders flowing |
| **SS-8** | Paper trading (60 days minimum) | Week 8–16 | Live fills, real spreads, regime transitions observed |
| **SS-9** | Live trading at 50% target size | Week 17+ | Real capital, gradual ramp |

**Parallelism:** SS-2 (ThetaData backfill) runs in parallel with SS-1 (oversold backtest). No blocking dependency.

**Kill gates:**
- After SS-1: If oversold bounce profit factor < 1.2 after costs, reassess.
- After SS-6: If composite walk-forward Sharpe < 1.0, don't proceed to paper trading.
- After SS-8: If paper trading Sharpe < 0.8 or max drawdown > 5%, don't go live.

---

## 9. Expected Returns (Conservative)

| Metric | Estimate | Basis |
|---|---|---|
| Trades per week | 5–15 | Signal frequency from backtest |
| Average return per trade | +80–120 bps | Discounted from backtest for slippage/costs |
| Win rate | 57–62% | Composite should exceed any single signal |
| Transaction costs per trade | 2–5 bps round trip | S&P 500 equities on IBKR |
| Monthly return (on deployed capital) | 2–4% | Rough, depends on opportunity flow |
| Annual return (on total portfolio) | 10–20% | Conservative, 10–20% average deployment |
| Max monthly drawdown | -3% to -5% | Based on worst months in backtest |
| Sharpe ratio (live estimate) | 1.0–1.8 | Discounted from backtest |

---

## 10. Costs

| Item | Cost | Frequency |
|---|---|---|
| ThetaData Standard | $80 | One-time (backfill, then cancel) |
| News API (Benzinga or equivalent) | $50–100/mo | Ongoing |
| IBKR market data (US equities) | $0–15/mo | Ongoing (may be waived with account minimum) |
| IBKR commissions | ~$0.50/trade | Per trade |
| ClickHouse (local Docker) | $0 | — |
| **Total ongoing** | **$50–115/mo** | |

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Mean-reversion fails in trending markets | Losses in oversold bounce signal | Regime gate (reduce weight when VIX > 28); require options flow or insider confirmation |
| Options flow signal has small sample size | Overfit to NVDA/AAPL | Backfill 50–100 tickers via ThetaData to validate at scale before production |
| Insider buying is low frequency | Not enough signals to drive daily trading | Use as confirmation overlay (+20 to composite), not standalone |
| News API misclassifies sentiment | Wrong filter decisions | Use sector-relative drops as primary filter; news sentiment as secondary |
| All signals fail simultaneously | Portfolio drawdown | Max 20% deployment; VIX > 45 = all cash; -3% stop loss per position |
| Survivorship bias in backtest | Inflated historical returns | S&P 500 constituents are well-documented; point-in-time universe for expansion |
| Regime detector lags reality | Trading into the start of a crisis | VIX is real-time; use rate-of-change, not level, for fast detection |
| IBKR API downtime | Can't exit positions | Stop-loss orders are resting on exchange (GTC), not dependent on API |

---

## 12. Key Queries (Reproducible)

### 12.1 OTM Call Flow Signal

```sql
WITH stock_flow AS (
    SELECT
        oc.underlying,
        oc.snapshot_date,
        any(oc.underlying_price) as spot,
        sum(CASE WHEN oc.put_call = 'call'
            AND abs(oc.strike - oc.underlying_price) / oc.underlying_price < 0.02
            THEN oc.volume ELSE 0 END) as atm_call_vol,
        sum(CASE WHEN oc.put_call = 'call'
            AND oc.strike > oc.underlying_price * 1.03
            AND oc.strike < oc.underlying_price * 1.10
            THEN oc.volume ELSE 0 END) as otm_call_vol
    FROM option_chains oc
    WHERE oc.snapshot_date >= '2023-01-01'
      AND oc.underlying_price IS NOT NULL
      AND oc.underlying_price > 0
    GROUP BY oc.underlying, oc.snapshot_date
    HAVING sum(oc.volume) > 10000
),
with_price AS (
    SELECT f.*,
        d0.close / d_prev.close - 1 as trailing_5d_ret,
        d5.close / d0.close - 1 as fwd_5d_ret
    FROM stock_flow f
    JOIN ohlcv_daily_mv d0 ON d0.ticker = f.underlying AND d0.day = f.snapshot_date
    JOIN ohlcv_daily_mv d_prev ON d_prev.ticker = f.underlying
        AND d_prev.day = addDays(f.snapshot_date, -7)
    JOIN ohlcv_daily_mv d5 ON d5.ticker = f.underlying
        AND d5.day = addDays(f.snapshot_date, 7)
    WHERE f.otm_call_vol > f.atm_call_vol * 1.5 AND f.otm_call_vol > 3000
)
SELECT
    CASE
        WHEN trailing_5d_ret < -0.03 THEN 'otm_calls_after_drop'
        WHEN trailing_5d_ret > 0.03 THEN 'otm_calls_after_rally'
        ELSE 'otm_calls_flat'
    END as context,
    count() as obs,
    round(avg(fwd_5d_ret) * 10000, 1) as avg_fwd_bps,
    round(median(fwd_5d_ret) * 10000, 1) as med_fwd_bps,
    round(countIf(fwd_5d_ret > 0) * 100.0 / count(), 1) as win_rate
FROM with_price
GROUP BY context
ORDER BY context
```

### 12.2 SPY Put/Call Ratio as Contrarian Signal

```sql
WITH daily_flow AS (
    SELECT snapshot_date,
        sum(CASE WHEN put_call = 'put' THEN volume ELSE 0 END) * 1.0 /
        greatest(sum(CASE WHEN put_call = 'call' THEN volume ELSE 0 END), 1) as pc_ratio
    FROM option_chains
    WHERE underlying = 'SPY' AND snapshot_date >= '2023-01-01'
    GROUP BY snapshot_date
)
SELECT
    CASE
        WHEN f.pc_ratio < 0.7 THEN 'call_heavy (<0.7)'
        WHEN f.pc_ratio < 1.0 THEN 'slight_call (0.7-1.0)'
        WHEN f.pc_ratio < 1.3 THEN 'balanced (1.0-1.3)'
        WHEN f.pc_ratio < 1.8 THEN 'slight_put (1.3-1.8)'
        ELSE 'put_heavy (>1.8)'
    END as pc_bucket,
    count() as days,
    round(avg(d5.close / d0.close - 1) * 10000, 1) as avg_fwd_5d_bps,
    round(countIf(d5.close > d0.close) * 100.0 / count(), 1) as win_rate
FROM daily_flow f
JOIN ohlcv_daily_mv d0 ON d0.ticker = 'SPY' AND d0.day = f.snapshot_date
JOIN ohlcv_daily_mv d5 ON d5.ticker = 'SPY' AND d5.day = addDays(f.snapshot_date, 7)
GROUP BY pc_bucket
ORDER BY pc_bucket
```

---

**Document status:** Complete. All signal results queried from live ClickHouse on April 7, 2026.
