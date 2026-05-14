# Roadmap — Build Phases

**No coding until docs are complete.** This roadmap is for planning purposes.

---

## Phase 0: Research & Documentation ✅ (Current)

- [x] Strategic blueprint overview
- [x] Deriv environment deep-dive
- [x] Architecture design (3 layers)
- [x] Tech stack decisions
- [x] Database schema design
- [x] AI model planning (Watcher + Sentinel)
- [x] Risk management framework
- [x] Open-source resource audit
- [ ] Study Deriv indices properly (which ones, contract types, tick behavior)
- [ ] Set up demo account on laptop
- [ ] Finalize strategy parameters (timeframes, indicators, thresholds)
- [ ] Complete all open questions in docs

---

## Phase 1: Foundation — Soldier (Execution Layer)

**Goal:** Working bot that connects to Deriv, streams ticks, and executes basic trades.

1. **Project setup** — folder structure, dependencies, config management
2. **Deriv API connection** — WebSocket connection, reconnection handling
3. **Tick streaming** — real-time tick ingestion from Deriv
4. **Tick → Candle builder** — aggregate ticks into OHLC candles (M1, M5)
5. **Indicator engine** — calculate EMA, RSI, Bollinger Bands, ATR, ADX
6. **Signal generator** — detect trading signals from indicators
7. **Trade executor** — place trades via Deriv API (proposal → buy)
8. **Supabase logging** — log ticks, candles, indicators, signals, trades
9. **Basic dashboard** — web view of current state, recent trades
10. **Paper trading mode** — everything above on demo account

**Exit criteria:** Bot runs on demo account, places trades based on fixed rules, logs everything to Supabase.

---

## Phase 2: Intelligence — Watcher (Regime Detection)

**Goal:** AI layer that classifies market regime and acts as kill switch.

1. **Feature engineering** — extract regime features from candle data (ATR, ADX, entropy, BB width, etc.)
2. **Historical data collection** — fetch large tick history from Deriv for training
3. **HMM training** — train Hidden Markov Model on feature data (3 regimes)
4. **Walk-forward validation** — test model accuracy on unseen data
5. **Real-time regime classifier** — integrate into live bot pipeline
6. **Kill switch integration** — Soldier pauses when regime = choppy
7. **Regime logging** — log all classifications to Supabase for audit
8. **Performance comparison** — bot with vs without regime detection

**Exit criteria:** Watcher correctly identifies regimes in real-time. Bot stops trading in choppy conditions. Measurable improvement in win rate vs Phase 1.

---

## Phase 3: Risk — Sentinel (Risk & Confidence)

**Goal:** Dynamic risk management with confidence-based lot scaling.

1. **Kill switch rules** — implement hard limits (daily loss, drawdown, consecutive losses)
2. **Confidence scoring** — weighted composite from regime, indicators, performance, volatility
3. **Lot scaling** — map confidence → lot multiplier (1x to 5x)
4. **Performance monitoring** — rolling P&L, win rate by regime, anomaly detection
5. **LLM integration** — GLM API for daily summaries, anomaly analysis, alert context
6. **Telegram alerts** — real-time notifications for trades, kill switches, anomalies
7. **Daily report generation** — automated performance summary

**Exit criteria:** Sentinel manages risk autonomously. Lot sizes scale with confidence. Hard limits enforced. Telegram alerts working.

---

## Phase 4: Hardening & Optimization

**Goal:** Production-ready system.

1. **Model retraining pipeline** — automated weekly/monthly HMM retraining
2. **XGBoost regime model** — train supervised model once labeled data accumulated
3. **Ensemble regime detection** — combine HMM + XGBoost
4. **Walk-forward backtesting** — comprehensive strategy validation
5. **VPS deployment** — move to dedicated server near Deriv
6. **Monitoring dashboard** — full web UI for real-time monitoring
7. **Error handling** — graceful degradation, auto-recovery, dead letter queues
8. **Security** — API key management, encrypted connections, access control

**Exit criteria:** Bot runs reliably on VPS for 2+ weeks on demo without intervention.

---

## Phase 5: Live Trading (Gradual)

**Goal:** Transition from demo to live with controlled risk.

1. **Small live account** — minimum viable deposit ($100-500)
2. **Minimum lot sizes** — 1x only, no scaling
3. **Strict daily limits** — tight loss limits
4. **2-week live trial** — validate real execution (slippage, fills, latency)
5. **Performance audit** — compare live vs demo vs backtest
6. **Gradual scaling** — increase capital and enable lot scaling only after proven results

**Exit criteria:** 1 month of profitable live trading with acceptable drawdown.

---

## Phase 6: Continuous Operation

**Goal:** Ongoing management of the autonomous hedge fund.

- Weekly model retraining
- Monthly strategy review
- Performance reporting
- Regime drift detection
- Infrastructure maintenance
- Gradual capital scaling

---

## No Timeline

**Build philosophy:** No deadlines. Build until satisfied. Rush leads to blown accounts.

Each phase completes fully before the next begins. No skipping to live trading without proven demo results.

---

## Dependencies Between Phases

```
Phase 0 (Docs) → Phase 1 (Soldier) → Phase 2 (Watcher) → Phase 3 (Sentinel)
                                                              │
                                                              ▼
                                                    Phase 4 (Hardening)
                                                              │
                                                              ▼
                                                    Phase 5 (Live Trading)
                                                              │
                                                              ▼
                                                    Phase 6 (Continuous)
```

Each phase produces something testable. No phase depends on future phases to function.
