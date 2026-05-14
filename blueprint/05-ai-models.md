# AI Models — Watcher & Sentinel

---

## Layer 2: Watcher — Regime Detection

### The Problem
The Soldier's strategy only works in certain market conditions. In choppy markets, it generates false signals and bleeds money. The Watcher's job is to classify the current market "regime" and tell the Soldier when to trade and when to sit out.

### Regime Types

| Regime | Characteristics | Soldier Action |
|--------|----------------|---------------|
| **Trending** | Clear direction, low noise | ✅ Full trade |
| **Choppy** | Sideways, high noise | 🛑 Stop trading |
| **High Volatility** | Large moves, erratic | ⚠️ Reduced position |

### Feature Engineering

Input features extracted from rolling window of candle data:

| Feature | Description | Why It Matters |
|---------|-------------|----------------|
| **ATR** (Average True Range) | Volatility measure | High ATR = volatile regime |
| **ADX** (Average Directional Index) | Trend strength | Low ADX = choppy |
| **RSI variance** | Oscillation of RSI over window | High variance = erratic |
| **Price entropy** | Shannon entropy of price changes | High entropy = noisy |
| **Volatility ratio** | Short ATR / Long ATR | Spike = regime shift |
| **BB width** | Bollinger Band squeeze/expand | Squeeze = low vol, expand = high vol |
| **Return autocorrelation** | Serial correlation of returns | Significant = trending |

### Model Options

#### Option A: Hidden Markov Model (HMM)
- **Library:** `hmmlearn`
- **Approach:** Unsupervised — model discovers hidden states automatically
- **Pros:** No labeling needed, naturally models regime transitions, theoretically sound
- **Cons:** Needs hyperparameter tuning (number of states), can be unstable
- **Best for:** When we don't have labeled regime data (which we don't, initially)

#### Option B: XGBoost Classifier
- **Library:** `xgboost`
- **Approach:** Supervised — train on labeled data
- **Pros:** Fast, accurate, handles non-linear relationships well
- **Cons:** Needs labeled training data (we'd need to manually classify historical regimes)
- **Best for:** After we have enough labeled data from manual review

#### Option C: K-Means Clustering
- **Library:** `scikit-learn`
- **Approach:** Unsupervised — group similar feature vectors
- **Pros:** Simple, fast, easy to interpret
- **Cons:** Assumes spherical clusters, less nuanced
- **Best for:** Quick baseline / prototyping

### Recommended Approach

1. **Start with HMM** — unsupervised, no labeling needed, good fit for regime detection
2. **Collect labeled data** during paper trading — log HMM outputs + manual regime labels
3. **Train XGBoost** once we have enough labeled data — likely more accurate
4. **Ensemble** — combine HMM + XGBoost for robustness

### Training Pipeline

```
Historical tick data (from Deriv ticks_history)
    │
    ▼
Build OHLC candles (M1, M5)
    │
    ▼
Calculate feature set (rolling window)
    │
    ▼
Train HMM (3 hidden states → trending/choppy/high-vol)
    │
    ▼
Validate against walk-forward backtest
    │
    ▼
Deploy model → classify each new candle in real-time
```

### Retraining Cadence
- Regime patterns may drift over time (CSRNG algorithm updates)
- Retrain weekly or monthly using recent data
- Always validate new model against recent performance before deploying

---

## Layer 3: Sentinel — Risk & Confidence Manager

### The Problem
Even with regime detection, the bot needs dynamic risk management. The Sentinel monitors overall performance, enforces hard limits, and scales lot sizes based on confidence.

### Responsibilities

#### 1. Kill Switch Enforcement (Rule-Based)
These are hard rules, no AI needed:

| Trigger | Action |
|---------|--------|
| Daily loss > X% | Stop trading for the day |
| Consecutive losses > N | Cooldown period (minutes) |
| Drawdown > X% from session high | Pause + alert |
| Win rate < Y% over last N trades | Reduce lot size |
| No signal for Z minutes | Health check |

#### 2. Confidence Scoring (AI-Assisted)
Composite score from multiple inputs:

| Input | Weight | Source |
|-------|--------|--------|
| Regime alignment | 30% | Watcher output |
| Indicator confluence | 25% | Multiple indicators agree |
| Recent performance | 20% | Rolling win rate |
| Volatility favorability | 15% | ATR within optimal range |
| Entropy level | 10% | Low entropy = more predictable |

**Confidence Score** = weighted average → maps to lot multiplier (see architecture doc)

#### 3. Performance Monitoring
- Rolling P&L chart
- Win rate by regime type
- Win rate by signal type
- Drawdown tracking
- Comparison to backtest baseline

### LLM Usage (GLM API)

The Sentinel uses the LLM for higher-level reasoning:
- **Anomaly detection:** "The last 20 trades deviate significantly from backtest expectations — investigate why"
- **Strategy adjustment suggestions:** "Choppy regime persists longer than expected — consider tightening RSI thresholds"
- **Daily summaries:** Generate human-readable performance reports
- **Alert context:** "Kill switch triggered — 5 consecutive losses in trending regime, which is unusual"

**Why LLM is fine here:**
- Runs every few minutes, not per-tick
- Latency of seconds is acceptable
- Complex reasoning that pure code handles poorly
- GLM-5 / GLM-5-turbo are strong at this kind of analytical reasoning

### Sentinel as Advisor, Not Autocrat

Critical design decision: The Sentinel **advises and enforces hard limits** but doesn't make discretionary trades. It can:
- ✅ Kill the bot (hard limit breached)
- ✅ Scale lot size (confidence scoring)
- ✅ Alert you (anomaly detected)
- ❌ Override the Soldier's signal (no "I think this trade is better")
- ❌ Change strategy parameters on its own

Strategy parameter changes require human review + approval.

---

## Model Performance Tracking

Every model decision gets logged:

```
[timestamp] regime=trending confidence=0.87 model=hmm_v3 features={atr: 0.45, adx: 32.1, ...}
[timestamp] signal=BUY strength=0.92 indicators={ema_cross: true, rsi: 28, bb: lower}
[timestamp] trade_executed contract=CALL stake=$10 lot=2x sentinel_confidence=0.87
[timestamp] trade_result=win profit=$8.20
```

This data feeds back into model retraining and strategy optimization.
