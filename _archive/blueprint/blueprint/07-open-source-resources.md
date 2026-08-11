# Open-Source Resources (Kronos-Era)

---

## 🥇 Tier 0: The Core — Kronos

### quantoxt/Kronos (our fork)
**URL:** https://github.com/quantoxt/Kronos  
**Original:** https://github.com/shiyu-coder/Kronos  
**License:** MIT  
**Paper:** AAAI 2026 — [arXiv](https://arxiv.org/abs/2508.02739)

**What it does:** Foundation model for financial candlesticks. Trained on 45+ exchanges. Predicts future OHLCV from historical K-line data.

**What we use directly:**
- ✅ `KronosPredictor` — prediction wrapper (load model, feed candles, get predictions)
- ✅ `finetune_csv/` — complete fine-tuning pipeline for custom CSV data
- ✅ `finetune_tokenizer.py` — adapt tokenizer to Deriv's price distributions
- ✅ `finetune_base_model.py` — fine-tune predictor on Deriv data
- ✅ `train_sequential.py` — one-command tokenizer + predictor training
- ✅ HuggingFace pretrained models (`NeoQuasar/Kronos-small`, etc.)
- ✅ Example backtester (`examples/run_backtest_kronos.py`)

**This is the entire prediction + strategy engine.** Everything else is plumbing.

---

## 🥈 Tier 1: Deriv Infrastructure — What We Still Steal

### 1. leon-pixel/synthetic-indices-bot
**URL:** https://github.com/leon-pixel/synthetic-indices-bot  
**License:** MIT

**What we still steal (strategy layer REMOVED, infrastructure only):**
- ✅ Tick → candle pipeline (we need this for OHLCV generation)
- ✅ Risk manager (session window, cooldown, daily loss, consecutive losses, kill switch)
- ✅ Research CLI for fetching historical data from Deriv
- ✅ Paper streaming loop for demo testing
- ✅ Deriv API integration patterns

**What we NO LONGER need from here:**
- ❌ Strategy code (EMA, RSI, Bollinger Band signals) — Kronos handles this
- ❌ Backtesting framework — use Kronos's own backtester
- ❌ Walk-forward validation — use Kronos fine-tune pipeline's built-in validation

### 2. stephen-njiu/Trading-Pipeline
**URL:** https://github.com/stephen-njiu/Trading-Pipeline  
**License:** MIT

**What we still steal:**
- ✅ WebSocket connection boilerplate
- ✅ Tick to OHLCV conversion (clean reference)
- ✅ Trade execution via `api.proposal()` / `api.buy()`

**What we NO LONGER need:**
- ❌ Bollinger Band + RSI strategy — Kronos replaces

### 3. DavidKori/deriv-bots
**URL:** https://github.com/DavidKori/deriv-bots  
**License:** MIT

**What we still steal:**
- ✅ Dashboard implementation patterns (web UI reference)
- ✅ Deploy script pattern (start/stop/status/logs)
- ✅ Deriv API connection patterns

**What we NO LONGER need:**
- ❌ RSI strategy parameters — Kronos replaces
- ❌ Symbol-specific strategy tuning — Kronos handles this via fine-tuning

### 4. ~~Deriv Official: python-deriv-api~~ — DEPRECATED (2026-08-02)
**URL:** https://github.com/deriv-com/python-deriv-api

~~Essential — unchanged. This is the SDK we build on top of.~~

**No longer used.** Deriv migrated to PAT (Personal Access Token) auth. The
legacy library connects to `ws.derivws.com` and sends `{authorize: <token>}`,
which now returns **"The token is invalid"** for current PAT tokens. We instead
talk Deriv's **new Options API** directly over raw `websockets`:

1. `POST https://api.derivws.com/trading/v1/options/accounts/{accountId}/otp`
   with headers `Deriv-App-ID` + `Authorization: Bearer <PAT>`
2. Response gives an authenticated `wss://…?otp=…` URL — connect there.
3. Message protocol is legacy-compatible with renames (`symbol`→`underlying_symbol`).

Reference implementation: `research/test_connection.py`. See memory `deriv-new-api-auth`.

---

## 🥉 Tier 2: Inspiration Only

### 5. freqtrade/freqtrade
**URL:** https://github.com/freqtrade/freqtrade  
**License:** GPL-3.0

**Still relevant for patterns (concept only, no code copying):**
- ✅ Risk management framework design (kill switches, drawdown circuit breakers)
- ✅ Per-signal-type position sizing → adapt to per-confidence-level sizing
- ✅ Telegram command handling (`/status`, `/profit`, `/stop`, `/start`)
- ✅ Data hygiene (parameter hashing, trade logging with context)

**No longer relevant:**
- ❌ FreqAI (adaptive ML) — Kronos replaces this entirely
- ❌ Strategy abstraction — one model, no strategy classes
- ❌ Hyperopt parameter optimization — fine-tuning replaces indicator optimization

### 6. Deriv API Documentation
**URL:** https://developers.deriv.com/docs/  
**WebSocket Docs:** https://developers.deriv.com/docs/options/websocket/

- Official API docs — our bible during development
- `ticks_history` call — essential for collecting training data
- Contract types, parameters, responses

### 7. quantopian/pyfolio
**URL:** https://github.com/quantopian/pyfolio  
**License:** Apache-2.0

- Portfolio analytics, tear sheets, drawdown/Sharpe/Sortino
- Useful for evaluating Kronos backtest results

---

## What We DON'T Need to Build From Scratch

| Component | Source | Effort Saved |
|-----------|--------|-------------|
| **OHLCV prediction** | Kronos (core value) | Months |
| **Fine-tuning pipeline** | Kronos finetune_csv | Weeks |
| **WebSocket connection** | raw `websockets` + Trading-Pipeline (patterns) | Days |
| **Tick → OHLCV pipeline** | synthetic-indices-bot | Days |
| **Risk manager (kill switches)** | synthetic-indices-bot | Week+ |
| **Backtesting framework** | Kronos examples + pyfolio | Weeks |
| **Dashboard UI patterns** | deriv-bots + freqtrade WebUI | Week |
| **Telegram alerts** | synthetic-indices-bot | Day |

## What We STILL Need to Build

| Component | Why |
|-----------|-----|
| **Deriv historical data collector** | Pull months of ticks for Kronos fine-tuning |
| **Kronos inference wrapper** | Integrate model into live bot pipeline |
| **Prediction → signal logic** | Threshold-based BUY/SELL from predicted OHLCV |
| **Regime from predictions** | Variance + error tracking → regime classification |
| **Supabase logging layer** | Project-specific schema (predictions, trades, ticks) |
| **Sentinel confidence scoring** | Custom weighted composite from Kronos outputs |
| **Multi-layer orchestration** | Wiring Soldier ↔ Watcher ↔ Sentinel |
| **Vue dashboard** | Web monitoring UI (6 views) |
| **FastAPI backend** | REST + WebSocket for dashboard |
| **Model retraining pipeline** | Automated monthly Kronos retrain |
| **Docker deployment** | Single-container (Vue + Python + Kronos) |

---

## Research To-Do

- [x] Fork Kronos repo — done
- [x] Understand finetune_csv pipeline — done
- [ ] Set up Deriv demo account + API token
- [ ] Pull historical tick data via `ticks_history` API
- [ ] Test Kronos vanilla prediction on Deriv data (before fine-tuning, as baseline)
- [ ] Fine-tune and compare
- [ ] Browse Deriv docs for `ticks_history` rate limits and data availability
- [ ] Check if Deriv provides historical OHLCV directly (skip tick aggregation if so)
