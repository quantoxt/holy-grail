# Three-Layer Hybrid Intelligence Architecture (Kronos-Era)

The "Sovereign-Subject" Model — Kronos foundation model as the core intelligence, with execution and risk management layered on top. Market-agnostic by design.

---

## Market Abstraction Layer (Designed, Not Yet Built)

Before the three layers, there's a **Market Provider** abstraction that decouples the bot from any specific data source or exchange:

```
┌─────────────────────────────────────┐
│  Market Provider (interface)        │
├──────────────┬──────────────────────┤
│ DerivProvider│ ExchangeProvider     │
│ (synthetic)  │ (live - future)      │
├──────────────┴──────────────────────┤
│ - tick_stream() → async tick feed   │
│ - get_candles(symbol, tf) → OHLCV  │
│ - buy(signal) → trade result       │
│ - sell(trade_id) → close result    │
│ - get_balance() → float            │
│ - get_positions() → list            │
└─────────────────────────────────────┘
```

The Soldier, Watcher, and Sentinel call the Market Provider interface — they never touch Deriv API or exchange API directly.

**Phase 1 builds only `DerivProvider`.** `ExchangeProvider` is a future implementation.

### Switch Mechanism

```python
# config.py
market_mode = "synthetic"  # or "live" (future)

# Switch is atomic: config change + model reload
if market_mode == "synthetic":
    provider = DerivProvider(config.deriv)
    kronos_model = load_model("kronos-v3-deriv-v75-m5")
    thresholds = config.deriv_thresholds
else:
    provider = ExchangeProvider(config.exchange)
    kronos_model = load_model("kronos-v3-btcusdt-m5")
    thresholds = config.exchange_thresholds
```

---

## Layer 1: The Soldier (Execution + Prediction Engine)

**Technology:** Market Provider (Python) + Kronos (PyTorch)  
**Speed:** Seconds (per candle close — not per tick)  
**Role:** Predict future candles via Kronos, extract trade signals, execute emotionlessly

### How It Works Now (Synthetic Mode)

Every candle close (e.g., M1):
1. Feed last 512 candles of OHLCV data to Kronos
2. Kronos predicts next N candles (OHLCV)
3. Signal extraction logic compares predicted close vs current price
4. If predicted move exceeds threshold → generate BUY or SELL signal
5. Execute trade via Market Provider (Deriv WebSocket in synthetic mode)
6. Log everything

### Responsibilities
- Maintain WebSocket connection to Deriv
- Stream tick data in real-time
- Build OHLCV candles from tick stream
- **Run Kronos inference on each candle close**
- Extract trade signals from Kronos predictions
- Execute entries/exits when signal conditions met
- Report every action to Watcher + Sentinel

### Signal Extraction (Thin Logic Layer)

Replace complex indicator calculations with simple prediction comparison:

```
For each Kronos prediction (next N candles):
  predicted_close = mean of predicted closes
  current_close = last actual close
  predicted_move = (predicted_close - current_close) / current_close

  if predicted_move > LONG_THRESHOLD:
      signal = BUY, strength = predicted_move
  elif predicted_move < SHORT_THRESHOLD:
      signal = SELL, strength = abs(predicted_move)
  else:
      signal = HOLD
```

Threshold values determined during fine-tuning validation — calibrated to produce acceptable win rate without over-trading.

### Why This Replaces Indicators

- **No EMA periods to tune** — Kronos learned candle patterns from 45+ exchanges
- **No RSI levels to agonize over** — the model captures momentum internally
- **No Bollinger Band parameters** — Kronos understands volatility natively
- **No strategy abstraction class hierarchy** — one model, one prediction, one signal path

### What We Still Need
- Tick → OHLCV candle aggregation (steal from goldmine repos)
- Deriv WebSocket connection + reconnection (python-deriv-api)
- Trade execution via Deriv API (proposal → buy)
- Kronos inference wrapper (load model, feed candles, get predictions)

### Weakness
- **Predictions are seconds behind** — inference time means we trade on candle close, not real-time ticks
- **No tick-level precision** — fine for Deriv synthetic indices which are less time-sensitive than real markets
- **Model can be wrong** — confidence scoring + Sentinel kill switches handle this

---

## Layer 2: The Watcher (Kronos Confidence Layer)

**Technology:** Derived from Kronos prediction outputs (pure Python)  
**Speed:** Seconds (runs alongside each Kronos inference)  
**Role:** Extract market regime from Kronos's own predictions → Kill switch

### The Insight

In the original architecture, the Watcher used HMM/XGBoost to classify regime (trending/choppy/high-vol). **This is replaced.** Kronos implicitly reveals regime through its prediction characteristics:

| Kronos Output Signal | Regime Meaning | Bot Action |
|----------------------|----------------|------------|
| **Low prediction variance** (tight H-L spread) | Predictable, likely trending | ✅ Full trade |
| **High prediction variance** (wide H-L spread) | Noisy, uncertain | 🛑 Stop trading |
| **Prediction error rising** (pred vs actual diverging) | Model losing grip | ⚠️ Reduce position |
| **Low prediction variance + strong directional bias** | Strong trend, high confidence | 🔥 Scale up (Sentinel territory) |

### How It Works

1. Kronos generates prediction for next N candles
2. **Calculate prediction variance** — standard deviation of predicted close values across the N candles
3. **Track rolling prediction error** — compare Kronos's past predictions vs actual outcomes
4. Classify regime from these two metrics (simple thresholds, no ML needed)
5. Pass regime + confidence to Soldier → Soldier filters or executes signals
6. Pass regime + confidence to Sentinel → Sentinel adjusts risk parameters

### Regime Classification (Threshold-Based, No ML)

```python
def classify_regime(prediction_variance, rolling_error):
    if prediction_variance < LOW_VOL_THRESHOLD and rolling_error < ERROR_THRESHOLD:
        return "trending", high_confidence
    elif prediction_variance > HIGH_VOL_THRESHOLD or rolling_error > HIGH_ERROR_THRESHOLD:
        return "choppy", low_confidence
    else:
        return "normal", medium_confidence
```

Thresholds calibrated during fine-tuning backtesting. Simple, fast, no model to train or retrain.

### Why This Is Better Than HMM/XGBoost

- **No hidden state assumption** — HMM assumed hidden states exist in CSRNG data, which is questionable
- **No labeled training data needed** — XGBoost required manually labeled regimes, we didn't have any
- **No retraining pipeline** — no weekly/monthly model refresh, thresholds are stable
- **Directly coupled to prediction quality** — regime reflects whether Kronos is actually useful right now
- **Faster** — simple math, no ML inference on top of ML inference

### Rolling Prediction Error Tracking

Maintain a sliding window of Kronos predictions vs actual outcomes:

```
last 50 predictions:
  predicted_close_1 vs actual_close_1 → error_1
  predicted_close_2 vs actual_close_2 → error_2
  ...
  rolling_mae = mean(|error_i|) for i in last 50
  rolling_directional_accuracy = % of predictions where direction was correct
```

When rolling error spikes → model is confused → reduce confidence → smaller lots or pause.

---

## Layer 3: The Sentinel (Risk & Confidence Manager)

**Technology:** Rule-based Python (same as original)  
**Speed:** Minutes (runs periodically, not per-tick)  
**Role:** Monitor bot performance → Decide Rules of Engagement

**Unchanged from original design** — but receives better inputs.

### What Changed for Sentinel

**Old confidence inputs (5 abstract weighted factors):**
- Regime alignment (30%) — from HMM
- Indicator confluence (25%) — from EMA/RSI/BB agreement
- Recent performance (20%) — rolling win rate
- Volatility favorability (15%) — ATR range
- Entropy level (10%) — Shannon entropy

**New confidence inputs (Kronos-derived):**
| Input | Weight | Source |
|-------|--------|--------|
| Kronos prediction confidence | 35% | Prediction variance + directional bias strength |
| Rolling prediction accuracy | 25% | Last N predictions vs actuals |
| Recent trade performance | 20% | Rolling win rate (unchanged) |
| Regime state | 15% | Watcher classification (trending/choppy/normal) |
| Prediction magnitude | 5% | Size of expected move (avoid tiny moves) |

### Responsibilities (Unchanged)

#### Performance Monitoring
- Track win rate, loss streaks, drawdown over rolling windows
- Compare live performance vs backtest expectations
- Detect performance degradation early

#### Kill Switch Authority (Rule-Based)
- **Daily loss limit** hit → stop trading for the day
- **Consecutive loss streak** hit → cooldown period
- **Drawdown threshold** breached → pause + alert
- **Prediction accuracy dropping** → auto-pause + alert (NEW — Kronos-specific)
- **Regime = choppy** detected → confirm or override

#### Confidence Scaling ("The Sure Situation")

| Confidence | Lot Size | Notes |
|-----------|---------|-------|
| < 50% | 0x | No trade |
| 50-70% | 1x (base) | Normal trading |
| 70-85% | 2x | Slightly aggressive |
| 85-90% | 3x | Confident |
| 90%+ | 5x | **Sure situation** — max scale |

### Sentinel Frequency

Runs every few minutes or on each trade completion. Not per-tick, not per-candle.

### Sentinel as Advisor, Not Autocrat

Same rule as before:
- ✅ Kill the bot (hard limit breached)
- ✅ Scale lot size (confidence scoring)
- ✅ Alert you (anomaly detected)
- ❌ Override the Soldier's signal
- ❌ Change Kronos parameters on its own

---

## Layer Communication Flow (Kronos-Era, Multi-Market)

```
Market Provider (Deriv or Exchange)
    │
    ▼
┌─────────────────────────────────────┐
│  Layer 1: Soldier                   │  ← Tick stream → OHLCV candles
│  (Python + Kronos inference)        │  ← Kronos predicts future candles
│                                     │  ← Thin signal logic → BUY/SELL/HOLD
│                                     │  → Trade execution via Market Provider
└─────────┬───────────────────────────┘
          │ predictions + variance + error tracking
          ▼
┌─────────────────────────────────────┐
│  Layer 2: Watcher                   │  ← Extract regime from Kronos outputs
│  (Pure Python, threshold-based)     │  → Trending/choppy/normal classification
│  (NO ML model needed)               │  → Kill switch signal
│  (Market-agnostic)                   │
└─────────┬───────────────────────────┘
          │ regime + kronos_confidence
          ▼
┌─────────────────────────────────────┐
│  Layer 3: Sentinel                  │  ← Performance audit, risk scaling
│  (Rule-based Python)               │  → Lot size adjustment, kill confirm
│  (Market-agnostic)                   │  → Telegram alerts
└─────────┬───────────────────────────┘
          │
          ▼
    Telegram Alerts (to you)
    Supabase Logs (every decision)
```

## Design Decision: No LLM in Sentinel

The original design planned GLM API for Sentinel anomaly detection. **Shelved to Phase 4+.** The confidence scoring is a weighted formula — pure Python does that faster and more reliably. No LLM needed until the system is proven on demo.

## Existing Code to Leverage

- **Kronos (quantoxt/Kronos)** — foundation model, finetune_csv pipeline, backtest framework
- **Telegram bot** — Quantoxt already has a TG bot project, reusable for alerts
- **Local Supabase** — Docker install ready, no cloud dependency
- **Goldmine repos** — Deriv WebSocket patterns, tick→candle pipeline (for DerivProvider only, not strategy)
- **Market Provider pattern** — abstraction layer for future live market support
