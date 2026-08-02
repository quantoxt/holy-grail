# QAI Review — Blueprint Checkpoint 2

**Date:** 2026-08-02  
**Reviewer:** QAI  
**Trigger:** Kronos integration — fundamental architecture shift

---

## Checkpoint 1 Recap (2026-06-25)

Five concerns raised:
1. ~~Sentinel as LLM is over-engineered~~ → ✅ Shelved to Phase 4+, confirmed
2. ~~HMM on CSRNG data is questionable~~ → ✅ **Solved by Kronos** — regime now derived from prediction variance, no hidden state assumption
3. ~~Tick storage will be a beast~~ → Still valid — recommend Parquet for cold storage
4. ~~5-15% monthly ROI projections are aggressive~~ → Still valid — data decides
5. ~~Missing contract type strategy~~ → Addressed — Rise/Fall recommended for Kronos directional predictions

---

## What Changed

| Component | Before | After | Impact |
|-----------|--------|-------|--------|
| Signal generation | Hand-coded indicators (EMA, RSI, BB) | Kronos OHLCV prediction → threshold | Major simplification |
| Regime detection | HMM/XGBoost (ML models) | Prediction variance + error tracking (pure Python) | Major simplification |
| Phase 0 blocker | "Which strategy to use?" | "Fine-tune Kronos on Deriv data" | **Blocker eliminated** |
| Code complexity | 3 ML systems (Soldier indicators + Watcher HMM + optional Sentinel LLM) | 1 ML system (Kronos inference) | Major reduction |
| New prerequisite | None | Mandatory fine-tuning on Deriv data | Added work, but necessary |
| Database | `indicators` table | `kronos_predictions` table | Schema changed |

---

## Checkpoint 2 Assessment

### What's Strong

- **Architecture simplification** — from 3 ML systems to 1. Less to debug, less to maintain, fewer failure modes
- **Kronos is peer-reviewed** — AAAI 2026 paper, not a random GitHub project
- **MIT license** — no GPL concerns, full freedom to modify
- **Fine-tuning pipeline exists** — finetune_csv is production-ready, tested on other datasets
- **Regime from prediction confidence** — elegant solution to the HMM-on-CSRNG problem. You're measuring what the model actually knows, not assuming hidden states exist
- **Prediction error tracking** — rolling MAE + directional accuracy gives a natural "model health" metric
- **Model versioning in database** — every prediction linked to model version, enables rollback

### Remaining Concerns

#### 1. Fine-tuning on CSRNG data might not work well

Kronos learned candlestick patterns from real markets where supply/demand/psychology drive price action. Synthetic indices have no fundamental drivers — patterns are purely algorithmic. The tokenizer might not find useful discrete representations in CSRNG-generated data.

**Mitigation:** Walk-forward backtest will reveal this quickly. If fine-tuned Kronos doesn't beat coin-flip on Deriv data (below 52% directional accuracy), we need to pivot:
- Try Kronos-mini (more capacity for different patterns)
- Try different timeframes (M1 vs M5 vs M15)
- Try different prediction lengths
- Fall back to indicator-based approach if Kronos fundamentally can't handle CSRNG

**This is the #1 risk of the entire project now.** The fine-tuning + validation step in Phase 0 is the make-or-break moment.

#### 2. Inference latency on CPU

Kronos-small (24.7M params) might take 200-500ms per prediction on CPU. On M1 candle close (every 60s) this is fine. But we need to benchmark early. If it's 2+ seconds, we either need GPU or Kronos-mini.

**Mitigation:** Benchmark in Phase 0 before building anything else.

#### 3. Contract type still undecided

Kronos predicts OHLCV (full candle), which naturally fits Rise/Fall (directional). But we haven't confirmed this is the optimal contract type for Deriv. Touch/No Touch could be more profitable if Kronos can accurately predict price extremes.

**Mitigation:** Research Deriv contract types in Phase 0. Kronos's `predicted_high_max` and `predicted_low_min` could potentially power Touch/No Touch signals.

#### 4. Tick storage

Same concern from Checkpoint 1. 2 ticks/sec × multiple symbols = millions of rows. Monthly Postgres partitioning is mentioned but Parquet for cold storage would be better.

**Mitigation:** Keep in design doc, implement when needed.

#### 5. ROI projections still aggressive

Same concern from Checkpoint 1. 5-8% monthly on a system with house edge is optimistic.

**Mitigation:** Let walk-forward backtest set expectations. Adjust projections based on actual data.

---

## Recommended Actions

### Before Coding Starts (Phase 0 Completion)

1. **Set up Deriv demo account** — API token + app_id
2. **Pull historical tick data** — 3-6 months for at least one index (start V75 or V100)
3. **Build tick → OHLCV CSV pipeline** — simple Python script, get clean CSVs
4. **Run Kronos vanilla (no fine-tuning) on Deriv data** — establish baseline accuracy
5. **Fine-tune Kronos on Deriv data** — tokenizer + predictor
6. **Walk-forward backtest** — compare fine-tuned vs vanilla
7. **If fine-tuned > 55% directional accuracy** → proceed to Phase 1
8. **If fine-tuned < 52% directional accuracy** → investigate, try different configs, or pivot
9. **Decide contract type** based on what Kronos predictions look like
10. **Benchmark inference latency** on target hardware

### Key Decision Points

| Decision | When | Criteria |
|---------|------|----------|
| Proceed to Phase 1 | After fine-tuning backtest | >55% directional accuracy |
| Pivot strategy | If fine-tuning fails | <52% accuracy after exhausting configs |
| Index selection | Before Phase 0 fine-tuning | Choose 1-2 indices to start |
| Contract type | After seeing Kronos output shape | Directional vs barrier-based |
| GPU requirement | After latency benchmark | If CPU > 1s per prediction |

---

## Status: Blueprint Updated

All 9 blueprint files updated for Kronos-era architecture. Phase 0 is clearly defined with fine-tuning as the gate. No coding until Phase 0 exit criteria are met.
