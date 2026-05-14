# Three-Layer Hybrid Intelligence Architecture

The "Sovereign-Subject" Model — splitting workload into specialized layers.

---

## Layer 1: The Soldier (Execution Bot)

**Technology:** Deriv WebSocket API (Python)  
**Speed:** Millisecond execution  
**Role:** High-speed, emotionless entry/exit based on fixed mathematical triggers

### Responsibilities
- Maintain WebSocket connection to Deriv
- Stream tick data in real-time
- Build OHLC candles from tick stream
- Calculate technical indicators (EMA, RSI, Bollinger Bands, ATR)
- Execute entries/exits when trigger conditions met
- Report every action to the Watcher

### Trigger Types
**Exact indicators TBD** after inspecting goldmine repos (see `07-open-source-resources.md`). Likely candidates:
- EMA crossovers (fast/slow)
- RSI overbought/oversold levels
- Bollinger Band touches/piercings
- Rejection candlestick patterns
- Whatever proven configs we find in existing bots

### Weakness
- **Blind to market context** — will trade in choppy conditions
- **No memory** — doesn't know if last 5 trades were losses
- **No self-preservation** — will keep trading until account is empty

This is why Layers 2 and 3 exist.

---

## Layer 2: The Watcher (AI Regime Detection)

**Technology:** Python — Scikit-Learn, XGBoost, or Hidden Markov Models  
**Speed:** Seconds (runs on each new candle close)  
**Role:** Classify current market regime → Kill switch for bad conditions

### Regime Types
| Regime | Bot Action | Description |
|--------|-----------|-------------|
| **Trending** | ✅ Trade | Clear directional movement, strategy works |
| **Choppy** | 🛑 Stop | Sideways noise, false signals everywhere |
| **High Volatility** | ⚠️ Caution | Big moves but erratic — reduce position size |

### How It Works
1. Ingests recent tick/candle data (rolling window)
2. Extracts features: volatility (ATR), trend strength (ADX), momentum (RSI), entropy
3. Classifies current regime using trained model
4. Sends regime signal to Soldier → Soldier pauses if regime = Choppy
5. Sends regime signal to Sentinel → Sentinel adjusts risk parameters

### Model Options
- **Hidden Markov Model (HMM)** — `hmmlearn` library, unsupervised, detects hidden states in price data
- **XGBoost Classifier** — supervised, train on labeled regime data
- **K-Means Clustering** — unsupervised regime grouping

### Key Insight
Regime changes are **not frequent** — they happen on the scale of hours, not milliseconds. The Watcher doesn't need sub-second speed. Running on candle close (every 1-5 minutes) is sufficient.

---

## Layer 3: The Sentinel (Risk & Confidence Manager)

**Technology:** LLM API (GLM/GPT) or dedicated Neural Network  
**Speed:** Minutes (runs periodically, not per-tick)  
**Role:** Monitor bot performance → Decide Rules of Engagement

### Responsibilities

#### Performance Monitoring
- Track win rate, loss streaks, drawdown over rolling windows
- Compare live performance vs backtest expectations
- Detect performance degradation early

#### Kill Switch Authority
- **Daily loss limit** hit → stop trading for the day
- **Consecutive loss streak** hit → cooldown period
- **Drawdown threshold** breached → pause + alert
- **Regime shift** detected by Watcher → confirm or override

#### Confidence Scaling ("The Sure Situation")
When AI detects **90%+ confidence** — alignment of indicators AND low entropy AND favorable regime:

| Confidence | Lot Size | Notes |
|-----------|---------|-------|
| < 50% | 0x | No trade |
| 50-70% | 1x (base) | Normal trading |
| 70-85% | 2x | Slightly aggressive |
| 85-90% | 3x | Confident |
| 90%+ | 5x | **Sure situation** — max scale |

### Sentinel Frequency
Since regime changes are infrequent, the Sentinel doesn't need millisecond execution either. A periodic check (every few minutes or on each trade completion) is adequate for:
- Updating confidence scores
- Adjusting lot sizes
- Monitoring drawdown limits
- Sending alerts via Telegram

---

## Layer Communication Flow

```
Deriv API (WebSocket)
    │
    ▼
┌─────────────────────────┐
│  Layer 1: Soldier       │  ← Tick stream, indicators, execution
│  (Python, real-time)    │
└─────────┬───────────────┘
          │ tick data + indicators
          ▼
┌─────────────────────────┐
│  Layer 2: Watcher       │  ← Regime classification
│  (ML model, per-candle) │  → Kill switch signal
└─────────┬───────────────┘
          │ regime + confidence
          ▼
┌─────────────────────────┐
│  Layer 3: Sentinel      │  ← Performance audit, risk scaling
│  (LLM/NN, periodic)    │  → Lot size adjustment, kill confirm
└─────────┬───────────────┘
          │
          ▼
    Telegram Alerts (to you)
    Supabase Logs (every decision)
```

## Design Decision: Sentinel Speed

Regime changes are **not frequent** — they shift over hours, not milliseconds. The Sentinel can run on a slower cadence (every few minutes or per-trade) without missing critical windows. This also means an LLM API call (which takes seconds, not milliseconds) is perfectly viable for the Sentinel role.

**Conclusion:** Keep the LLM as-is for the Sentinel. Millisecond execution is only needed for the Soldier (Layer 1) — which is pure Python/WebSocket, no AI needed there.

## Existing Code to Leverage

- **Telegram bot** — Quantoxt already has a TG bot project, reusable for alerts
- **Local Supabase** — Docker install ready, no cloud dependency
- **Goldmine repos** — pull down locally, inspect with AI model, extract proven configs
