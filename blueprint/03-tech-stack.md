# Technology Stack (Kronos-Era)

---

## Core Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Prediction Engine** | Kronos (PyTorch + HuggingFace) | Foundation model for OHLCV candle prediction |
| **Execution** | Python + Deriv WebSocket API | Real-time tick streaming, trade execution |
| **API Layer** | FastAPI | Dashboard API, WebSocket event broadcasting |
| **Database** | Supabase via Docker (local) | Log every tick, prediction, trade, risk event |
| **Alerts** | Telegram Bot API | Real-time notifications to phone |
| **Frontend** | Vue 3 + Tailwind CSS 4 + shadcn-vue | Web monitoring dashboard |
| **Hosting** | Local machine (VPS only for live phase) | Local dev, VPS near Deriv for live only |

## Python Libraries

### Prediction Engine (NEW)
- `torch` — PyTorch, required for Kronos inference
- `transformers` / `safetensors` — HuggingFace model loading
- Kronos model code — `model.py` from quantoxt/Kronos repo
- `KronosPredictor` — prediction wrapper class from Kronos repo

### Execution Layer
- `python-deriv-api` — Official Deriv WebSocket client (PyPI)
- `websockets` — Low-level WebSocket if we need more control
- `asyncio` — Async event loop for concurrent operations
- `pandas` / `numpy` — Data processing, OHLCV aggregation

### Technical Analysis (REMOVED — replaced by Kronos)
~~- `ta-lib` or `pandas-ta`~~ — ~~EMA, RSI, Bollinger Bands, ATR, ADX~~
~~- Custom indicator logic~~ — ~~No longer needed~~

### Machine Learning (REPLACED by Kronos)
~~- `scikit-learn`~~ — ~~Clustering, classification~~
~~- `xgboost`~~ — ~~Gradient boosting for regime classification~~
~~- `hmmlearn`~~ — ~~Hidden Markov Models~~

**Retained for fine-tuning:**
- `scikit-learn` — Data preprocessing for fine-tuning pipeline
- PyTorch native — Kronos fine-tuning (tokenizer + predictor)

### Data & Database
- `supabase-py` — Supabase Python client
- `psycopg2` — Direct PostgreSQL if needed

### Monitoring & Visualization
- Built-in dashboard (Vue SPA, FastAPI served)
- `lightweight-charts` (TradingView) — Candlestick charts in dashboard
- Telegram bot for mobile alerts

## Infrastructure & Hosting

### Deployment Stages

| Stage | Environment | Purpose | When |
-------|-----------|---------|------|
| **Local dev** | Main laptop (Quantoxt's machine) | Build, test, fine-tune Kronos, Phase 0-3 | Phase 0-3 |
| **Local VPS** | Second laptop (always-on, WiFi) | Persistent demo trading, Phase 4-6 | Phase 4+ |
| **Cloud VPS** | Rental server near Deriv | Live trading with real money | Phase 5+ (future) |

### Stage 1: Local Development (Main Laptop)

- Build and test everything here first
- Run Kronos fine-tuning experiments
- Validate predictions on Deriv demo data
- No 24/7 uptime requirement — stop when you stop working

### Stage 2: Local VPS (Second Laptop — Always On)

**Hardware specs:**
- **CPU:** Intel Core i5 @ 2.50GHz max
- **RAM:** 8GB DDR3/DDR4
- **Storage:** 1TB HDD/SSD
- **GPU 1:** Intel HD Graphics 2GB
- **GPU 2:** AMD Radeon 4GB
- **Network:** WiFi via local router (needs outbound internet)

**OS:** Linux (Ubuntu 22.04 LTS recommended — native Docker, systemd, Python 3.10+)

**GPU assessment:**
- Intel HD 2GB — **No PyTorch support.** Not usable.
- AMD Radeon 4GB — **Limited PyTorch support via ROCm (Linux only), unstable.** Not recommended.
- **Conclusion: CPU-only inference.** Both GPUs are not useful for this workload.

**Kronos on CPU (this hardware):**

| Model | Params | RAM | CPU Inference (est.) | Candle Fit? |
|-------|--------|-----|----------------------|------------|
| Kronos-mini | 4.1M | ~100MB | <100ms | ✅ Trivial |
| Kronos-small | 24.7M | ~200MB | 200-500ms | ✅ Comfortable (M1 = 60s budget) |
| Kronos-base | 102.3M | ~500MB | 1-3s | ⚠️ Works but slow (M1 still OK, M5 very comfortable) |

**Recommendation for this hardware:** Kronos-small on CPU. Good accuracy-to-speed balance. Upgrade to Kronos-base on CPU if validation shows accuracy gain is worth the wait.

**Runtime RAM budget:**

| Component | RAM Usage |
|-----------|-----------|
| PyTorch + Kronos model (small) | ~300-500MB |
| Python bot + asyncio event loop | ~100-200MB |
| Supabase (PostgreSQL Docker container) | ~500MB-1GB |
| FastAPI + Vue static files | ~100MB |
| OS overhead (Ubuntu desktop/server) | ~1-2GB |
| **Total** | **~2-3GB** |
| **Available** | **8GB (5GB free)** |

**Verdict:** RAM is comfortable. No pressure.

**Storage:**
- Kronos models: ~50-200MB each (3-4 variants = ~500MB)
- Supabase/PostgreSQL data: grows with tick data
  - M1 ticks: ~2/sec × 86400 sec/day = ~170K rows/day per symbol
  - After 30 days: ~5M rows (~500MB-1GB with indexes)
  - Archive old ticks to Parquet: keeps DB lean
- Fine-tuning checkpoints: ~200MB per experiment
- Logs: negligible
- **Year 1 estimate:** 10-20GB total. Storage is not a concern.

**Network requirements:**
- **Outbound internet required** — bot connects to `ws.derivws.com` for ticks and trades
- **No inbound ports needed** — all connections are outbound (Deriv, Telegram, HuggingFace for model downloads)
- **No port forwarding needed** — dashboard accessed locally or via local network
- **No static IP needed** — outbound connections don't care about your IP
- **If router loses internet → bot stops.** This is true regardless of where you host.
- **Latency:** Local WiFi → ISP → Deriv servers. Estimated 50-150ms. For M1 trading (60s candle intervals), this is negligible.

**Laptop setup checklist:**
- [ ] Install Ubuntu 22.04 LTS (or use existing Linux)
- [ ] Disable sleep: `systemctl mask sleep.target suspend.target hibernate.target`
- [ ] Set up systemd service for auto-start on boot
- [ ] Install Docker (for Supabase)
- [ ] Install Python 3.10+
- [ ] Clone repo, install dependencies
- [ ] Test outbound connection: `wscat -c wss://ws.derivws.com/websockets/v3?app_id=1089`
- [ ] Set up Telegram bot token + chat ID in `.env`

**systemd service (example):**
```ini
# /etc/systemd/system/holy-grail.service
[Unit]
Description=Holy Grail Trading Bot
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=holygrail
WorkingDirectory=/opt/holy-grail
ExecStart=/opt/holy-grail/venv/bin/python -m soldier.run
Restart=always
RestartSec=10
EnvironmentFile=/opt/holy-grail/.env

[Install]
WantedBy=multi-user.target
```

### Stage 3: Cloud VPS (Future — Live Trading)

Move to a rental VPS only when going live with real money.

**Requirements:**
- **Location:** Near Deriv servers (check Deriv docs for server region)
- **OS:** Ubuntu 22.04 LTS
- **RAM:** 4-8GB
- **CPU:** 2-4 cores
- **GPU:** Optional (NVIDIA, CUDA 12+) — helps if using Kronos-base
- **Storage:** 20GB+ SSD
- **Network:** Low latency, stable, 99.9% uptime SLA

**Why cloud VPS for live:**
- Guaranteed uptime (no power outages, no sleep mode)
- Lower latency to Deriv (same DC region)
- Professional environment (monitoring, backups)
- **But:** Not needed for dev/demo. Don't pay for it until you need it.

### Why Local Laptop VPS Works for Dev/Demo

| Concern | Cloud VPS | Local Laptop VPS |
|---------|-----------|------------------|
| Uptime | 99.9% | ~95% (power/network dependent) |
| Latency to Deriv | ~10-30ms | ~50-150ms |
| Cost | $10-30/month | $0 |
| GPU | Optional (can rent NVIDIA) | Intel HD + AMD (not useful) |
| Convenience | SSH from anywhere | Same room, easy physical access |
| Risk | Provider outage, billing | Power cut, WiFi drop, OS crash |

**For demo trading, the laptop is fine.** A 50-100ms latency difference doesn't matter when you're trading on M1 candles. If the laptop crashes, no real money is at risk. Fix it, restart, move on.

## Project Structure (Updated)

```
holy-grail/
├── blueprint/          # Documentation (this folder)
├── kronos/              # Kronos model code (from quantoxt/Kronos fork)
│   ├── model.py         # Kronos, KronosTokenizer, KronosPredictor
│   └── finetune_csv/    # Fine-tuning pipeline
│       ├── train_sequential.py
│       ├── finetune_tokenizer.py
│       ├── finetune_base_model.py
│       └── configs/
├── providers/           # Market Provider abstraction (DESIGNED, NOT YET BUILT)
│   ├── base.py          # MarketProvider ABC (interface)
│   ├── deriv.py         # DerivProvider — Phase 1 (synthetic mode)
│   └── exchange.py      # ExchangeProvider — FUTURE (live markets)
├── soldier/             # Layer 1 — Execution engine
│   ├── candles.py      # Tick → OHLCV aggregation
│   ├── executor.py     # Trade execution (calls Market Provider)
│   └── signals.py      # Prediction → BUY/SELL signal extraction
├── watcher/             # Layer 2 — Confidence/Regime (market-agnostic)
│   ├── regime.py       # Regime from Kronos variance + error
│   └── tracker.py       # Rolling prediction error tracking
├── sentinel/            # Layer 3 — Risk management (market-agnostic)
│   ├── risk.py          # Risk calculations, drawdown tracking
│   ├── confidence.py   # Kronos-based confidence scoring
│   └── scaler.py       # Lot size scaling logic
├── shared/
│   ├── config.py       # Configuration (market_mode, model_version, thresholds)
│   ├── database.py     # Supabase connection & logging
│   ├── models.py       # Data models (trades, predictions, ticks)
│   └── telegram.py     # Alert system
├── api/                 # FastAPI backend + Vue static serving
│   ├── main.py
│   ├── routes/
│   └── ws/
├── frontend/            # Vue SPA dashboard
├── research/             # Fine-tuning experiments, backtesting
│   ├── data/            # Historical OHLCV CSVs (Deriv + future live data)
│   ├── experiments/     # Fine-tune configs, results
│   │   ├── synthetic/   # Deriv fine-tuning experiments
│   │   └── live/        # FUTURE: Exchange fine-tuning experiments
│   └── notebooks/       # Analysis Jupyter notebooks
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

### What Changed in Structure

| Before | After |
|--------|-------|
| `soldier/connection.py` | Moved to `providers/deriv.py` (Market Provider pattern) |
| `soldier/indicators.py` | Removed — Kronos handles this |
| `soldier/signals.py` | Simplified — prediction threshold logic |
| `watcher/features.py` | Removed — no feature engineering needed |
| `watcher/model.py` | Removed — no HMM/XGBoost model |
| `watcher/classifier.py` | Replaced by `regime.py` (threshold-based) |
| N/A | `kronos/` — new, foundation model code |
| N/A | `providers/base.py` — Market Provider interface (designed, not built) |
| N/A | `providers/deriv.py` — Deriv implementation |
| N/A | `providers/exchange.py` — Future live market implementation |
| N/A | `research/data/` — Historical data (split by market type) |
| N/A | `research/experiments/` — Fine-tune experiments (split by market type) |
