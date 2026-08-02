# Roadmap — Build Phases (Kronos-Era)

**No coding until docs are complete.** This roadmap is for planning purposes.

---

## Phase 0: Research & Kronos Fine-Tuning 🔴 CURRENT

**Goal:** Fine-tune Kronos on Deriv data, validate predictions, calibrate signals.

- [x] Strategic blueprint overview
- [x] Deriv environment deep-dive
- [x] Architecture design (3 layers)
- [x] Tech stack decisions
- [x] Database schema design
- [x] AI model planning (Kronos integration)
- [x] Risk management framework
- [x] Open-source resource audit
- [x] Checkpoint 1 saved (2026-05-14)
- [x] Kronos forked, finetune_csv pipeline available
- [x] Checkpoint 2 saved (2026-08-02) — Kronos redesign
- [ ] **Set up Deriv demo account + API token**
- [ ] **Collect 3-6 months historical tick data** for target indices (start with V75 or V100)
- [ ] **Build tick → OHLCV CSV pipeline** — aggregate ticks into M1/M5 candles
- [ ] **Fine-tune Kronos tokenizer** on Deriv data
- [ ] **Fine-tune Kronos predictor** on Deriv data
- [ ] **Walk-forward backtest** — validate fine-tuned model on held-out data
- [ ] **Compare fine-tuned vs vanilla Kronos** — prove fine-tuning adds value
- [ ] **Calibrate signal thresholds** (LONG_THRESHOLD, SHORT_THRESHOLD)
- [ ] **Calibrate regime thresholds** (prediction variance limits)
- [ ] **Benchmark inference latency** on target hardware
- [ ] **Decide contract type** (Rise/Fall recommended — fits Kronos directional predictions)
- [ ] **Decide target index + timeframe** (V75 M1? V100 M5?)
- [ ] **Complete all open questions in docs**

**Exit criteria:** Fine-tuned Kronos model produces >55% directional accuracy on walk-forward backtest of Deriv data. Signal thresholds calibrated. Ready to build execution pipeline.

---

## Phase 1: Foundation — Soldier (Execution + Kronos Inference)

**Goal:** Working bot that connects to Deriv, streams ticks, runs Kronos, and executes trades on demo.

1. **Project setup** — folder structure, dependencies, config management
2. **Deriv API connection** — WebSocket connection, reconnection handling
3. **Tick streaming** — real-time tick ingestion from Deriv
4. **Tick → OHLCV builder** — aggregate ticks into candles (M1 or M5)
5. **Kronos inference wrapper** — load fine-tuned model, predict on candle close
6. **Signal extraction** — compare predicted close vs current → BUY/SELL/HOLD
7. **Trade executor** — place trades via Deriv API (proposal → buy)
8. **Supabase logging** — log ticks, candles, predictions, signals, trades
9. **Prediction error tracker** — rolling MAE + directional accuracy
10. **Paper trading mode** — everything above on demo account

**Exit criteria:** Bot runs on demo account, Kronos predicts each candle close, generates signals, executes trades, logs everything to Supabase. Running for 1+ week continuously.

---

## Phase 2: Intelligence — Watcher (Confidence Layer)

**Goal:** Extract regime from Kronos predictions, act as kill switch.

1. **Regime classifier** — threshold-based (prediction variance + error → trending/choppy/normal)
2. **Kill switch integration** — Soldier pauses when regime = choppy
3. **Confidence scoring** — composite from Kronos variance + accuracy + prediction magnitude
4. **Regime logging** — log all classifications to Supabase for audit
5. **Performance comparison** — bot with vs without regime filtering

**Exit criteria:** Watcher correctly identifies unfavorable conditions. Bot stops trading when Kronos is unreliable. Measurable improvement in win rate vs Phase 1 (no regime filter).

---

## Phase 3: Risk — Sentinel (Risk & Confidence)

**Goal:** Dynamic risk management with confidence-based lot scaling.

1. **Kill switch rules** — implement hard limits (daily loss, drawdown, consecutive losses)
2. **Kronos-based confidence scoring** — weighted composite from prediction confidence, accuracy, performance
3. **Lot scaling** — map confidence → lot multiplier (1x to 5x)
4. **Performance monitoring** — rolling P&L, win rate by regime, anomaly detection
5. **Telegram alerts** — real-time notifications for trades, kill switches, anomalies
6. **Daily report generation** — automated performance summary

**Exit criteria:** Sentinel manages risk autonomously. Lot sizes scale with Kronos confidence. Hard limits enforced. Telegram alerts working.

---

## Phase 4: Hardening & Dashboard

**Goal:** Production-ready system with monitoring UI.

1. **Vue dashboard build** — 6 views (Dashboard, Trades, Regime, Risk, Config, Settings)
2. **FastAPI backend** — REST endpoints + WebSocket events
3. **Model retraining pipeline** — automated monthly Kronos retrain on latest data
4. **Walk-forward backtesting tool** — comprehensive strategy validation
5. **VPS deployment** — move to dedicated server near Deriv
6. **Docker single-container** — multi-stage build (Vue → Python + Kronos)
7. **Error handling** — graceful degradation, auto-recovery
8. **Security** — API key management, encrypted connections

**Exit criteria:** Bot runs reliably on VPS for 2+ weeks on demo without intervention. Dashboard shows live state. Docker deploy works.

---

## Phase 5: Live Trading (Gradual)

**Goal:** Transition from demo to live with controlled risk.

1. **Small live account** — minimum viable deposit ($100-500)
2. **Minimum lot sizes** — 1x only, no scaling
3. **Strict daily limits** — tight loss limits
4. **2-week live trial** — validate real execution (slippage, fills, latency)
5. **Performance audit** — compare live vs demo vs backtest
6. **Kronos accuracy monitoring** — track if live predictions match backtest accuracy
7. **Gradual scaling** — increase capital and enable lot scaling only after proven results

**Exit criteria:** 1 month of profitable live trading with acceptable drawdown.

---

## Phase 6: Continuous Operation

**Goal:** Ongoing management of the autonomous hedge fund.

- Monthly Kronos retraining on latest Deriv data
- Walk-forward validation of each retrained model
- Performance reporting
- Prediction accuracy drift detection
- Infrastructure maintenance
- Gradual capital scaling

---

## No Timeline

**Build philosophy:** No deadlines. Build until satisfied. Rush leads to blown accounts.

Each phase completes fully before the next begins. No skipping to live trading without proven demo results.

---

## Dependencies Between Phases

```
Phase 0 (Fine-Tuning) → Phase 1 (Soldier) → Phase 2 (Watcher) → Phase 3 (Sentinel)
                                                              │
                                                              ▼
                                                    Phase 4 (Dashboard + Hardening)
                                                              │
                                                              ▼
                                                    Phase 5 (Live Trading)
                                                              │
                                                              ▼
                                                    Phase 6 (Continuous)
```

**Phase 0 is the gate.** Nothing starts until Kronos is validated on Deriv data. This is the highest-leverage work — get the prediction engine right and everything downstream is easier.

---

## What Changed vs Original Roadmap

| Original | Kronos-Era |
|----------|-----------|
| Phase 0: study indices, pick strategy, pull repos | Phase 0: fine-tune Kronos on Deriv data, validate |
| Phase 1: build indicator engine, signal gen, executor | Phase 1: build Kronos inference, thin signal layer, executor |
| Phase 2: train HMM, validate regime, build kill switch | Phase 2: extract regime from predictions, build kill switch |
| Phase 3: same (Sentinel) | Phase 3: same but Kronos-derived confidence |
| Phase 4: hardening + retraining + VPS | Phase 4: + dashboard, Kronos retrain pipeline |
| Frontend was a separate plan | Now integrated as Phase 4 |
