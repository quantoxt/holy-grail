# Open-Source Resources — GitHub Goldmines

Proven code, libraries, and frameworks we can leverage instead of reinventing the wheel.

---

## 🥇 Tier 1: Directly Usable — Deriv Synthetic Indices

### 1. leon-pixel/synthetic-indices-bot
**URL:** https://github.com/leon-pixel/synthetic-indices-bot  
**License:** MIT  
**What it does:** Mean-reversion bot specifically built for Deriv synthetic indices

**Why it's gold:**
- Shared tick → candle pipeline (we need this)
- Backtesting + walk-forward validation built-in
- Risk manager with session window, cooldown, daily loss, consecutive losses, **kill switch**
- Paper streaming loop for demo testing
- Research CLI with CSV or live Deriv tick fetching
- M1 + M5 indicators (EMA, RSI, ATR regime detection)
- Optional TradingView Pine Script integration
- Full Python project structure to learn from

**What we can steal:**
- ✅ Tick → candle pipeline
- ✅ Risk manager (session limits, cooldowns, kill switch)
- ✅ Backtesting framework
- ✅ Research CLI approach
- ✅ Deriv API integration patterns

---

### 2. stephen-njiu/Trading-Pipeline
**URL:** https://github.com/stephen-njiu/Trading-Pipeline  
**License:** MIT  
**What it does:** Algorithmic trading pipeline for Deriv — real-time streaming + Bollinger Bands + Rejection candle patterns

**Why it's gold:**
- Clean Deriv WebSocket connection pattern
- Tick → OHLC candle generation from live stream
- Bollinger Bands + RSI strategy implementation
- Signal → Trade execution flow
- Simple, readable codebase — good reference for Deriv API usage

**What we can steal:**
- ✅ WebSocket connection boilerplate
- ✅ Tick to OHLC conversion
- ✅ Bollinger Band signal generation
- ✅ Trade execution via `api.proposal()` / `api.buy()`

---

### 3. DavidKori/deriv-bots
**URL:** https://github.com/DavidKori/deriv-bots  
**License:** MIT  
**What it does:** RSI-based bot for Deriv synthetic indices (V100, V75, V50)

**Why it's interesting:**
- Claims **95%+ win rate** backtested on R_100 (487 trades)
- Claims **100% win rate** on R_75 (14 trades) and 1HZ75V (32 trades)
- Includes web dashboard for monitoring
- Deploy script with start/stop/status/logs
- Multiple symbol configurations

**⚠️ Take with grain of salt:** 100% win rate claims are suspicious. Backtest ≠ live. But the strategy parameters and symbol-specific RSI configs are worth studying.

**What we can study:**
- ✅ RSI parameters per volatility index
- ✅ Dashboard implementation
- ✅ Deploy script pattern
- ✅ Symbol-specific strategy tuning

---

### 4. Deriv Official: python-deriv-api
**URL:** https://github.com/deriv-com/python-deriv-api  
**License:** Official  
**PyPI:** `python-deriv-api`  
**What it does:** Official Python WebSocket client for Deriv API

**Essential — this is the SDK we build on top of.**
- WebSocket connection management
- API call helpers (ping, proposal, buy, sell, subscription)
- Async/await pattern
- Reconnection handling
- Examples included (`examples/simple_bot1.py`)

---

## 🥈 Tier 2: Architecture & ML Inspiration

### 5. freqtrade/freqtrade
**URL:** https://github.com/freqtrade/freqtrade  
**License:** GPL-3.0  
**What it does:** Full-featured crypto trading bot (35K+ stars)

**Why it's relevant even though it's crypto:**
- **FreqAI** — built-in adaptive ML that self-trains to market conditions (our Watcher concept)
- Strategy optimization by machine learning
- Backtesting framework with walk-forward
- Telegram integration for management
- WebUI for monitoring
- SQLite persistence
- Risk management system

**What we can learn from (not copy — different license, different market):**
- ✅ Architecture patterns for multi-component trading bot
- ✅ FreqAI approach to adaptive ML in trading
- ✅ Risk management framework design
- ✅ Backtesting + walk-forward methodology

---

### 6. hmmlearn/hmmlearn
**URL:** https://github.com/hmmlearn/hmmlearn  
**License:** BSD-3-Clause  
**What it does:** Hidden Markov Models in Python with scikit-learn API

**Why we need it:** Core library for our Watcher's regime detection. HMM is the natural mathematical tool for detecting hidden states (regimes) in sequential data.

- Gaussian HMM, GMM-HMM variants
- scikit-learn compatible API
- Well-documented
- pip install hmmlearn

---

### 7. quantopian/pyfolio
**URL:** https://github.com/quantopian/pyfolio  
**License:** Apache-2.0  
**What it does:** Portfolio and risk analytics in Python

**Useful for:**
- Tear sheets — comprehensive performance visualization
- Risk analysis (drawdown, Sharpe ratio, Sortino ratio)
- Benchmarking strategy vs baseline
- Works with backtest results

---

## 🥉 Tier 3: Worth Exploring

### 8. Deriv 4000+ Bot Collection
**URL:** https://github.com/topics/deriv  
**Note:** GitHub topics page lists repos including a collection claiming 4,000+ trading bots for Deriv

- Could contain niche strategies worth studying
- Need to browse and filter quality from noise

### 9. elkd/deriv
**URL:** https://github.com/elkd/deriv  
**What it does:** Playwright-based automation for Deriv website (not API)

- Less relevant (we use API, not browser automation)
- But useful reference for Deriv's UI flow if we ever need it

### 10. Deriv API Documentation
**URL:** https://developers.deriv.be/docs/  
**WebSocket Docs:** https://developers.deriv.com/docs/options/websocket/  
**Deep Reference:** https://deepwiki.com/deriv-com/python-deriv-api

- Official API docs — our bible during development
- WebSocket protocol reference
- Contract types, parameters, responses

---

## What We DON'T Need to Build From Scratch

| Component | Source | Effort Saved |
|-----------|--------|-------------|
| WebSocket connection | python-deriv-api + Trading-Pipeline | Days |
| Tick → OHLC pipeline | synthetic-indices-bot | Days |
| Risk manager (kill switches) | synthetic-indices-bot | Week+ |
| Backtesting framework | synthetic-indices-bot + freqtrade patterns | Weeks |
| HMM regime detection | hmmlearn library | Week |
| Dashboard UI | deriv-bots dashboard + freqtrade WebUI patterns | Week |
| Telegram alerts | synthetic-indices-bot implementation | Day |

## What We STILL Need to Build (No Good Existing Solutions)

| Component | Why |
|-----------|-----|
| **Sentinel (LLM risk manager)** | Nobody's doing this — unique to our architecture |
| **Confidence scoring system** | Custom weighted composite |
| **Supabase logging layer** | Project-specific schema |
| **Strategy parameter optimization** | Needs to be tailored to our specific indices/contract types |
| **Model retraining pipeline** | Automated HMM/XGBoost retraining on recent data |
| **Multi-layer orchestration** | Wiring Soldier ↔ Watcher ↔ Sentinel together |

---

## Research To-Do

- [ ] Browse the 4000+ bot collection on GitHub topics/deriv
- [ ] Deep-dive synthetic-indices-bot codebase — understand every module
- [ ] Study DavidKori's RSI params per volatility level
- [ ] Read freqtrade's FreqAI documentation for ML approach inspiration
- [ ] Check Deriv API docs for contract types we haven't considered
- [ ] Look for existing HMM regime detection examples in trading context
