# QAI Review — Blueprint Checkpoint 1

**Date:** 2026-06-25  
**Reviewer:** QAI  
**Status:** Blueprint read, concerns logged

---

## What's Good

- Three-layer architecture (Soldier/Watcher/Sentinel) — clean separation of concerns, each with clear job and speed requirement
- Deriv synthetic indices choice — news-proof, 24/7, predictable volatility, CSRNG-based eliminates variables that break forex/crypto bots
- Data pipeline — full audit trail from tick to trade to risk event
- "No set and forget" philosophy — active fund mindset, not passive income
- Open-source audit — leon-pixel/synthetic-indices-bot alone saves weeks

---

## Concerns / Pushbacks

### 1. Sentinel as LLM is over-engineered for v1

Using GLM API for anomaly detection and daily summaries adds a dependency and latency for no real edge at the start. The confidence scoring is a weighted formula — pure Python does that faster and more reliably. **Shelve LLM integration to Phase 4+.**

### 2. HMM on CSRNG data — questionable

HMM assumes underlying hidden states with transition probabilities. On CSRNG-generated indices, there are no organic "hidden states" — the patterns are engineered in, not emergent. HMM might find "regimes" that are just artifacts of the random generation. Worth testing, but don't bet the whole architecture on it.

### 3. Tick storage will be a beast

2 ticks/sec × multiple symbols = millions of rows fast. Monthly partitioning in Postgres is mentioned but may not be enough. Consider TimescaleDB or Parquet files for raw ticks. Keep Supabase/Postgres for trades, decisions, sessions — the stuff you actually query.

### 4. 5-15% monthly ROI projections are aggressive

Even on synthetic indices, consistent 5-8% monthly is hedge-fund-level. The house edge on Deriv is real. Reframe as "can we break even + small profit after house edge" and let the data decide.

### 5. Missing: contract type strategy

The biggest open question. Rise/Fall, Touch/No Touch, Digit trades are fundamentally different games. Strategy parameters should be designed AROUND a specific contract type, not the other way around. **This needs to be decided before Phase 1.**

---

## Recommended Next Steps

1. Pick contract type and index — defines everything downstream
2. Pull and inspect goldmine repos (especially synthetic-indices-bot)
3. Get Deriv demo account + API token — start streaming ticks
4. Build Phase 1 Soldier only — prove execution pipeline before any AI
