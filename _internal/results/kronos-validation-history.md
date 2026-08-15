# Kronos Test History — All Symbols, All Results

Consolidated log of every validation/experiment run on Kronos in this project.
Gate: directional accuracy ≥ 55% at the traded horizon to consider an edge real.
Date of consolidation: 2026-08-15.

---

## Phase 1 — Synthetics era (Deriv CSRNG) — ALL DEAD

### 1.1 Pre-trained Kronos on Deriv synthetics (2026-07)
Direction/range/digits tested against R_75 and related synthetics — all coin-flip or
worse. Pre-condition for the fine-tune attempt below. (Details in `_archive/`.)

### 1.2 Fine-tuned Kronos-small on V75 M5 (trained 2026-08-02, validated 2026-08-03) — **FAIL**
- Data: 3.94M R_75 ticks → 26,288 M5 candles. Lookback 512, pred 48.
  Tokenizer val loss 0.0008, predictor val loss 1.4854. Model at
  `data/models/deriv-v75-m5/` (24.7M params = Kronos-small).
- Walk-forward directional accuracy (n=192, sample_count=1, h=1/6/12/24):
  **46.9% / 45.8% / 48.4% / 45.3%** — at/below coin-flip at every horizon.
  Best confidence slice 52.5% (h=12, |move|≥0.3%, n=120) — not significant, below gate.
- **Range/touch test (n=388): FAIL.** Touch precision == base rate (zero information);
  range-size MAE 51% WORSE than naive (model over-predicts V75's swing).
- **Digit test: FAIL.** Last-digit distribution uniform (chi2 4.0 @ 4dp; every digit
  ~10.00%) — nothing for Over/Under/Even-Odd/Match-Differ.
- **Verdict: V75 untradeable in all 3 dimensions (direction, range, digits).**
  Scripts: `research/range_test.py`, `research/digit_analysis.py`.

---

## Phase 2 — Live markets, pre-trained Kronos zero-shot (no fine-tuning)

### 2.1 BTCUSD (Binance spot) M5, N=1 — **PASS (the only validated edge)**
- Pre-trained Kronos-small, walk-forward, h=24 (~2h), sample_count=1.
- **54.7% directional accuracy at h=24 — ~3σ above coin-flip.**
- Caveats: directional only (magnitude uncalibrated); measured on Binance spot, not
  a broker's crypto-CFD feed (spread/session differences).
- Artifacts: `data/validate_BTCUSDT_5m_pretrained.jsonl`, `research/validate.py`.

### 2.2 R:R validation (2026-08-10) — **3:1 fixed TP non-viable**
Fixed take-profit at 3:1 reward:risk was killed by noise before the horizon — SL
hits dominated. Led to the goal-aware exit redesign (h=24 horizon close + predicted-
level TP + profit-lock ratchets, no fixed TP). Script: `research/rr_validation.py`.

### 2.3 XAUUSD / XAGUSD / GBPUSD (broker M5 CFDs, Just Global), N=5 (VAST RTX 5060 Ti, 2026-08-14) — **ALL FAIL**
- ~13 months broker M5 data (100k candles/symbol), walk-forward, stride 24,
  pred_len 24, **sample_count=5** (Kronos-averaged). 4,145 preds/symbol.
- h=24: **XAUUSD 48.4% (n=4141) · XAGUSD 50.1% (n=4069) · GBPUSD 51.1% (n=4124)**
- h=12: 50.9% / 50.7% / 50.7%. Confidence slices (|move| ≥ 0.1/0.2/0.3%) do NOT
  rescue any instrument — every slice ~48–51%.
- Artifacts: `data/validate_<SYM>_5m_n5_pretrained.jsonl`,
  `data/vast_validate_2026-08-14.log`. Full report:
  `_internal/human/validation-results-2026-08-14.md`.

### 2.4 Same three symbols, N=1 (VAST, 2026-08-15) — **ALL FAIL; averaging theory disproven**
- Identical data/stride/horizons, only sample count changed. h=24:
  **XAUUSD 48.8% · XAGUSD 49.7% · GBPUSD 50.3%**
- N=1 ≈ N=5 everywhere (Δ ≤ 0.8pp). Averaging changed nothing because there was no
  signal to flatten — the edge is **absent** on these instruments, not hidden.
- XAUUSD is consistently ~1–1.6σ **below** 50% across both runs.
- Artifacts: `data/validate_<SYM>_5m_n1_pretrained.jsonl`,
  `data/vast_validate_n1_2026-08-15.log`.

---

## Phase 3 — Live measurement (ongoing, 2026-08-14+)

### 3.1 Live shadow measurement via `prediction_evaluations`
Every live prediction (traded or not, incl. HOLD) on XAUUSD/XAGUSD/GBPUSD/BTCUSD is
logged and scored 2h later against the actual close, on the Just Global demo account
(login 1200341152, $500). This is the ground truth accumulating now — re-check per-
symbol hit rates once n≥100/symbol (cloud Supabase:
`rest/v1/prediction_evaluations?select=symbol,outcome&outcome=in.(hit,miss)`).

### 3.2 Watcher rolling accuracy (Layer 2 drift gate)
Seeded 79% (15/19) on the 2026-08-14 demo night — n far too small (95% CI ≈ 56–92%),
treat as flicker, not evidence. Verify regression or hold at n≥100.

### 3.3 Anecdote retired: the 2026-08-10 "+$14 week"
Mostly one lucky XAUUSD trade; backtests (2.3/2.4) show no persistent edge on the
instruments traded. Do not cite it as evidence.

---

## Summary table

| Test | Symbol(s) | Data | Config | Result | Verdict |
|---|---|---|---|---|---|
| Synthetic direction | V75 (fine-tuned) | Deriv M5 | N=1, h=1..24 | 45–48% | FAIL |
| Synthetic range/touch | V75 | Deriv M5 | n=388 | touch=base rate; MAE +51% | FAIL |
| Synthetic digits | V75 | Deriv ticks | chi2 | uniform | FAIL |
| Direction (zero-shot) | **BTCUSD** | Binance M5 | **N=1, h=24** | **54.7% (~3σ)** | **PASS** |
| Fixed 3:1 R:R | — | — | — | SL noise dominates | non-viable |
| Direction (zero-shot) | XAUUSD | broker M5 | N=5, h=24 | 48.4% | FAIL |
| Direction (zero-shot) | XAGUSD | broker M5 | N=5, h=24 | 50.1% | FAIL |
| Direction (zero-shot) | GBPUSD | broker M5 | N=5, h=24 | 51.1% | FAIL |
| Direction (zero-shot) | XAUUSD | broker M5 | N=1, h=24 | 48.8% | FAIL |
| Direction (zero-shot) | XAGUSD | broker M5 | N=1, h=24 | 49.7% | FAIL |
| Direction (zero-shot) | GBPUSD | broker M5 | N=1, h=24 | 50.3% | FAIL |
| Live shadow (ongoing) | XAU/XAG/GBP/BTC | live demo | N=5 | accumulating | TBD (n≥100) |

## Untested / open
- BTCUSD at N=5 on Binance data (would settle whether the original edge survives
  averaging; moot for live, curiosity only).
- BTCUSD on the broker's CFD feed (the 54.7% was Binance spot; weekend CFD spread
  and sessions differ). The live shadow table (3.1) is measuring this right now.
- Kronos fine-tune on live (non-synthetic) data — optional future work.
