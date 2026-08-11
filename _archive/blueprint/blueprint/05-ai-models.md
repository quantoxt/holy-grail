# AI Models — Kronos Fine-Tuning & Inference

**Status:** Kronos replaces both the Watcher (HMM/XGBoost) and the Soldier's indicator engine.

---

## The Core Model: Kronos

**What:** Decoder-only foundation model pre-trained on K-line (OHLCV candle) data from 45+ global exchanges. Treats financial candles as a "language" — a specialized tokenizer quantizes continuous OHLCV into hierarchical discrete tokens, then a Transformer autoregressively generates future candles.

**Paper:** Accepted at AAAI 2026 — [arXiv](https://arxiv.org/abs/2508.02739)  
**License:** MIT  
**HuggingFace:** `NeoQuasar/Kronos-*` models  
**Repo:** `quantoxt/Kronos` (our fork, includes finetune_csv pipeline)

### Model Selection

| Model | Params | Context | Speed | Accuracy | When to Use |
|-------|--------|---------|-------|----------|-------------|
| Kronos-mini | 4.1M | 2048 | Fast (CPU OK) | Lower | Development, prototyping, testing |
| Kronos-small | 24.7M | 512 | Medium (GPU preferred) | Good | **Recommended starting point** |
| Kronos-base | 102.3M | 512 | Slow (GPU required) | Best | Production live trading |
| Kronos-large | 499.2M | 512 | Very slow | Best | Not open-source, unavailable |

**Start with Kronos-small for everything.** Upgrade to Kronos-base for live only if GPU is available and inference benchmarks are acceptable.

### Why 512 Context is Fine for Deriv

512 candles at:
- M1 → 8.5 hours of history
- M5 → 42 hours of history
- M15 → 5.2 days of history

Synthetic indices don't have macroeconomic regime shifts (no news, no geopolitical events). Patterns cycle on shorter timescales. 512 candles is more than enough to capture the local structure.

---

## Phase 0: Fine-Tuning on Deriv Data (MANDATORY)

**This is the critical prerequisite.** Kronos was trained on real exchange data. Synthetic indices have different microstructure — CSRNG-generated patterns don't behave exactly like real markets. The model MUST be fine-tuned on Deriv-specific data before any trading.

### Step 1: Collect Historical Data

Use Deriv API to pull tick history for target indices:
- `ticks_history` API call → raw tick data
- Aggregate ticks into OHLCV candles (M1 or M5)
- Target: **minimum 3-6 months of continuous data per index**
- Store as CSV: `timestamps, open, high, low, close, volume, amount`
- Volume/amount can be 0 for synthetic indices (not meaningful)

### Step 2: Prepare Fine-Tuning Data

Format required by finetune_csv pipeline:

```csv
timestamps,open,close,high,low,volume,amount
2026-01-15 00:00,1024.35,1025.12,1025.80,1023.90,0,0
2026-01-15 00:01,1025.12,1024.87,1025.50,1024.20,0,0
...
```

Split: 90% train / 10% validation (configurable)

### Step 3: Fine-Tune Tokenizer

```bash
python finetune_csv/finetune_tokenizer.py \
  --config research/experiments/deriv_v75_m5.yaml
```

The tokenizer learns to quantize Deriv's specific price distributions into discrete tokens. This adapts the "vocabulary" to synthetic index volatility profiles.

**Hyperparameters to tune:**
- `tokenizer_epochs`: 20-50 (start with 30)
- `tokenizer_learning_rate`: 0.0001-0.0003 (start with 0.0002)
- `batch_size`: 32

### Step 4: Fine-Tune Predictor

```bash
python finetune_csv/finetune_base_model.py \
  --config research/experiments/deriv_v75_m5.yaml
```

The predictor learns to generate accurate future candles for Deriv data specifically.

**Hyperparameters to tune:**
- `basemodel_epochs`: 10-30 (start with 20)
- `predictor_learning_rate`: 0.0000005-0.000002 (start with 0.000001)
- `predict_window`: 24-96 (how many future candles to predict)
- `lookback_window`: 256-512 (input context length)

### Step 5: Validate — Walk-Forward Backtest

**This is the most important step.** Before any live trading:

1. Split historical data into rolling windows (e.g., 2 months train, 1 month test)
2. Fine-tune on window A, predict on window B
3. Slide forward: fine-tune on A+B, predict on C
4. Walk forward across entire dataset
5. Measure: directional accuracy, MAE, prediction variance patterns
6. **Compare: model fine-tuned on Deriv vs vanilla Kronos (no fine-tuning)**
7. If fine-tuned model doesn't significantly outperform vanilla → investigate

### Step 6: Calibrate Signal Thresholds

From backtest results:
- Find `LONG_THRESHOLD` and `SHORT_THRESHOLD` that produce:
  - Win rate > 55%
  - Reasonable trade frequency (not too sparse, not over-trading)
  - Acceptable drawdown
- These thresholds are specific to each index + timeframe

### Step 7: Benchmark Inference Latency

Measure actual prediction time on target hardware:
- Kronos-small on CPU: expect ~100-500ms per prediction
- Kronos-small on GPU: expect ~50-100ms per prediction
- Must complete within candle interval (M1 = 60s margin, very comfortable)

---

## Live Inference Pipeline

### Per Candle Close (M1 or M5)

```python
# Pseudocode
ticker.subscribe(symbol)  # Stream ticks
on_candle_close():
    candles = get_last_512_candles(symbol, timeframe)
    predictions = kronos.predict(
        df=candles[['open','high','low','close']],
        x_timestamp=candles['timestamps'],
        y_timestamp=future_timestamps(pred_len=48),
        pred_len=48,
        T=1.0,
        top_p=0.9,
        sample_count=3  # Multiple paths, average for stability
    )
    signal = extract_signal(predictions, current_close)
    regime = classify_regime(predictions)
    log_to_supabase(candles, predictions, signal, regime)
    if signal != HOLD and regime != CHOPPY:
        execute_trade(signal, sentinel.lot_size)
```

### Sample Count for Stability

Use `sample_count=3` or higher — Kronos generates multiple probabilistic forecast paths and averages them. This reduces variance in predictions and produces more stable signals.

---

## Prediction Error Tracking (Replaces Regime ML)

### Rolling Metrics (maintain sliding window of last 50 predictions)

```python
class PredictionTracker:
    def __init__(self, window_size=50):
        self.predictions = deque(maxlen=window_size)
        self.actuals = deque(maxlen=window_size)
    
    def record(self, predicted_close, actual_close):
        self.predictions.append(predicted_close)
        self.actuals.append(actual_close)
    
    @property
    def rolling_mae(self):
        """Mean Absolute Error — lower = model more accurate"""
        return mean(abs(p - a) for p, a in zip(self.predictions, self.actuals))
    
    @property
    def directional_accuracy(self):
        """% of predictions where direction was correct"""
        correct = 0
        for i in range(1, len(self.predictions)):
            pred_dir = self.predictions[i] > self.predictions[i-1]
            actual_dir = self.actuals[i] > self.actuals[i-1]
            if pred_dir == actual_dir:
                correct += 1
        return correct / max(len(self.predictions) - 1, 1)
    
    @property
    def is_degraded(self):
        """True if model performance is dropping"""
        return self.directional_accuracy < 0.45  # Below coin-flip
```

### Regime from Predictions (Threshold-Based)

```python
def classify_regime(predictions_df, tracker):
    pred_variance = predictions_df['close'].std()
    pred_range = predictions_df['high'].max() - predictions_df['low'].min()
    
    if pred_variance < LOW_VOL_THRESH and tracker.directional_accuracy > 0.55:
        return "trending", 0.7 + tracker.directional_accuracy * 0.3
    elif pred_variance > HIGH_VOL_THRESH or tracker.directional_accuracy < 0.45:
        return "choppy", 0.3
    else:
        return "normal", 0.5
```

Thresholds (`LOW_VOL_THRESH`, `HIGH_VOL_THRESH`) calibrated during fine-tuning backtest.

---

## Model Maintenance

### When to Retrain

- **Monthly** at minimum — synthetic index patterns may shift if Deriv updates CSRNG
- **When prediction error spikes** — detected by Watcher, triggers auto-alert
- **After Deriv API changes** — if tick format or behavior changes

### Retraining Pipeline

1. Collect latest N months of Deriv tick data
2. Rebuild OHLCV CSVs
3. Re-run fine-tune tokenizer + predictor
4. Walk-forward validate new model vs old model
5. If new model wins → deploy, archive old model
6. If new model loses → investigate, keep old model

### Model Versioning

Every model prediction logged with:
- `model_version` (e.g., `kronos-small-v3-deriv-v75-m5`)
- `tokenizer_version` (e.g., `tokenizer-v3-deriv-v75-m5`)
- `fine_tune_date`

This enables rollback and comparison.

---

## What We Dropped

| Dropped | Why |
|---------|-----|
| Hidden Markov Models (hmmlearn) | No real hidden states in CSRNG data |
| XGBoost regime classifier | No labeled regime data available |
| Feature engineering pipeline | Kronos handles this internally |
| K-Means clustering | Unnecessary complexity |
| LLM for Sentinel | Over-engineered for v1, pure Python suffices |
| All indicator libraries (ta-lib, pandas-ta) | Kronos replaces indicator-based signals |
