# What to Steal from Freqtrade

**Date:** 2026-06-25  
**Context:** We're building on synthetic-indices-bot (MIT, Deriv-native). Freqtrade is GPL-3.0 so we can't copy code directly — but architectural patterns and concepts are free game.

---

## 1. FreqAI — Adaptive ML Pipeline (→ Watcher Layer)

Freqtrade's FreqAI module is exactly what our Watcher wants to be. Don't copy code, copy the **approach**:

**How FreqAI works:**
- Trains ML models on a rolling window of feature data
- Auto-retrains when performance degrades or on schedule
- Supports LightGBM, XGBoost, PyTorch
- Feature engineering pipeline: define features once, reuse for train + live inference
- Backtests using the same ML pipeline (no train/test leakage)

**What we take:**
- Rolling-window retraining concept (weekly/monthly cadence)
- Feature pipeline pattern: define features as a config, auto-compute on candle data
- Model versioning — track which model version produced each prediction
- Train/backtest parity: same feature extraction code path for both
- Degradation detection — monitor model accuracy drift over time, trigger retrain

**What we skip:**
- FreqAI's full framework (too heavy, GPL-3.0)
- PyTorch support (overkill for our regime detection)
- Their specific feature set (crypto-specific)

**Our implementation:** HMM (hmmlearn) for v1 unsupervised regime detection → XGBoost once we have labeled data → ensemble. Same rolling retrain pattern as FreqAI.

---

## 2. Hyperopt — Parameter Optimization Pattern

Freqtrade's `hyperopt` is essentially: run thousands of backtests with different parameters, find the best combo, validate with walk-forward.

**The pattern to steal:**
```
1. Define parameter space (ranges for RSI thresholds, EMA periods, ATR mults, etc.)
2. Objective function: maximize (win_rate × profit_factor) or minimize (drawdown)
3. Run backtest for each parameter combo
4. Walk-forward validate: train on window A, test on window B, slide forward
5. Check for overfitting: if train performance >> test performance, discard
```

**What we take:**
- Grid/random/Bayesian search over strategy parameters
- Walk-forward validation as the gold standard (synthetic-indices-bot already has `--walk-forward`)
- Overfitting detection: compare in-sample vs out-of-sample performance
- Parameter hash for reproducibility (synthetic-indices-bot already has `params_hash`)

**What we add:**
- Synthetic-index-specific objective: penalize false signals in choppy regimes more heavily
- Regime-conditional optimization: find parameters that work PER regime, not globally

---

## 3. Risk Management Framework Patterns

Freqtrade's risk system is layered. Our blueprint has something similar but freqtrade's abstractions are worth studying.

**Patterns worth adopting:**

### a) Stop-Loss Types
Freqtrade supports multiple stop-loss strategies:
- **Fixed stop-loss** (our current approach)
- **Trailing stop-loss** (lock in profit as price moves favorably)
- **Custom stop-loss** (Python function — dynamic based on indicators/regime)

→ We take: **regime-conditional stop-loss.** Tighter stops in trending, wider in high-vol. The Sentinel adjusts stop multiplier based on Watcher's regime call.

### b) ROI Tables
Freqtrade uses progressive ROI tables:
```
ROI: { "0": 0.10, "30": 0.05, "60": 0.02 }
→ Take 10% profit immediately, or 5% after 30 min, or 2% after 60 min
```

→ We take: **time-decay exit logic.** Synthetic indices contracts have fixed durations, but the concept maps to dynamic duration selection. Shorter contracts when confidence is high, longer when riding a trend.

### c) MaxDrawdown Protection
Freqtrade's 2026.2 release added account-drawdown circuit breakers.

→ We already have this in the blueprint (drawdown triggers at 5/10/15/20%). Adopt freqtrade's pattern of making it a separate, hardened module that can't be overridden by other components.

### d) Edge Position Sizing
Freqtrade's Edge module: calculates optimal position size per trade based on historical win rate + risk-reward ratio for that specific setup.

→ We take: **per-signal-type position sizing.** Track win rate and average P&L separately for each signal type (EMA cross, RSI extreme, BB touch). The Sentinel uses per-type stats to size positions, not just a flat confidence score.

---

## 4. Strategy Abstraction Pattern

Freqtrade forces strategies into a clean interface:
```python
class MyStrategy(IStrategy):
    def populate_indicators(self, dataframe) -> dataframe
    def populate_entry_trend(self, dataframe) -> dataframe
    def populate_exit_trend(self, dataframe) -> dataframe
```

**Why this matters:** It separates "what indicators do I compute" from "what signals do I act on" from "how do I exit." Makes it trivial to swap strategies, A/B test, and add new ones.

→ We adopt this pattern for synthetic-indices-bot. Currently their strategy is hardcoded in `strategy.py`. Refactor to:
```python
class BaseStrategy(ABC):
    def compute_indicators(self, candles) -> DataFrame
    def generate_signals(self, candles, indicators) -> list[Signal]
    def should_exit(self, trade, current_state) -> bool | ExitReason
```

This lets us test multiple strategies against the same execution + risk pipeline.

---

## 5. Backtesting Quality Checks

Freqtrade has learned the hard lessons on backtesting pitfalls. Worth adopting:

**a) Realistic fills:** Freqtrade adds slippage and spread to backtest fills. synthetic-indices-bot has `spread_points` and `slippage_points` knobs — keep those and calibrate from demo-vs-backtest comparison.

**b) Latency simulation:** synthetic-indices-bot already has `--latency-bars`. Extend this to simulate WebSocket round-trip time on Deriv (measure actual latency from demo, inject same delay in backtest).

**c) Out-of-sample discipline:** FreqAI explicitly separates train/test data windows. Never optimize and test on the same period. Walk-forward is the minimum bar.

**d) Multiple regime testing:** Backtest each strategy across trending, choppy, and high-vol periods separately. A strategy that looks good overall might be profitable in only one regime and bleeding in others.

---

## 6. Telegram Integration Patterns

Freqtrade's Telegram integration is mature — commands, keyboard shortcuts, formatted reports.

**Worth adopting:**
- `/status` — current open trades, active regime, confidence level
- `/profit` — session/day/week P&L summary
- `/performance` — per-signal-type win rates and P&L
- `/stop` / `/start` — remote bot control
- `/reload` — hot-reload config without restart

synthetic-indices-bot already has basic Telegram alerts. Extend with command handling for remote management.

---

## 7. Data Hygiene Patterns

**a) Parameter hashing:** synthetic-indices-bot already has `params_hash()` — every backtest result is tagged with a hash of its config. Keep this. Critical for reproducibility.

**b) Trade logging with context:** Freqtrade logs every trade with full indicator snapshot at entry/exit. synthetic-indices-bot's strategy produces "reason codes" for signals. Extend to log the full feature vector + regime + confidence at trade open and close.

**c) Model version tracking:** FreqAI tags every prediction with model version. Do the same for our Watcher — every regime classification gets `model_version` in the `regimes` table.

---

## Summary: Steal List

| Concept | Source | Where It Goes | Priority |
|---------|--------|---------------|----------|
| Rolling-window ML retrain | FreqAI | Watcher | Phase 2 |
| Walk-forward validation | Hyperopt | Research/backtest | Phase 1 |
| Overfitting detection | Hyperopt | Research/backtest | Phase 1 |
| Strategy abstraction interface | IStrategy pattern | Soldier refactor | Phase 1 |
| Regime-conditional stops | Custom stop-loss | Sentinel | Phase 3 |
| Per-signal-type position sizing | Edge module | Sentinel | Phase 3 |
| Hardened drawdown circuit breaker | MaxDrawdown | Sentinel | Phase 3 |
| Time-decay exit logic | ROI tables | Soldier | Phase 1-2 |
| Telegram command handling | TG integration | Shared/monitoring | Phase 1 |
| Latency simulation in backtest | Backtesting | Research | Phase 1 |
| Full-context trade logging | Trade logging | Database layer | Phase 1 |

---

## What NOT to Take

- CCXT or any exchange abstraction (useless for Deriv)
- Freqtrade's plugin system (overkill for our scale)
- Freqtrade's pairlist management (single-instrument focus)
- Freqtrade's GraphQL/webhook integrations (premature)
- Any GPL-3.0 code (concept only, clean-room implementation)
