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

## Infrastructure

### Hardware Requirements (Kronos-specific)

Kronos inference needs consideration:

| Model | Params | GPU/CPU | Inference Time (est.) | Notes |
|-------|--------|---------|----------------------|-------|
| Kronos-mini | 4.1M | CPU OK | <100ms | 2048 context, less accurate |
| Kronos-small | 24.7M | GPU preferred | ~200ms | 512 context, good balance |
| Kronos-base | 102.3M | GPU required | ~500ms | 512 context, most accurate |

**Recommendation:** Start with Kronos-small on CPU for development. Move to Kronos-base on GPU for live trading. Benchmark during Phase 0.

### VPS Requirements
- **Location:** Near Deriv servers (check Deriv docs for server locations)
- **OS:** Ubuntu 22.04 LTS or similar Linux
- **RAM:** 4-8 GB (PyTorch + Kronos model in memory)
- **CPU:** 4 cores minimum (async bot + Kronos inference)
- **GPU:** Optional for dev, recommended for live (NVIDIA, CUDA 12+)
- **Storage:** 20 GB+ (tick data + model checkpoints)
- **Network:** Low latency, stable connection

### Why VPS Near Deriv?
Execution latency matters. Every millisecond between signal detection and order execution is slippage. A VPS in the same data center region as Deriv's matching engine minimizes this.

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
├── soldier/             # Layer 1 — Execution engine
│   ├── connection.py   # Deriv WebSocket management
│   ├── candles.py      # Tick → OHLCV aggregation (replaces indicators.py)
│   ├── executor.py     # Trade execution logic
│   └── signals.py      # Prediction → BUY/SELL signal extraction
├── watcher/             # Layer 2 — Confidence/Regime (simplified)
│   ├── regime.py       # Regime from Kronos variance + error (no ML)
│   └── tracker.py       # Rolling prediction error tracking
├── sentinel/            # Layer 3 — Risk management
│   ├── risk.py          # Risk calculations, drawdown tracking
│   ├── confidence.py   # Kronos-based confidence scoring
│   └── scaler.py       # Lot size scaling logic
├── shared/
│   ├── config.py       # Configuration management
│   ├── database.py     # Supabase connection & logging
│   ├── models.py       # Data models (trades, predictions, ticks)
│   └── telegram.py     # Alert system
├── api/                 # FastAPI backend + Vue static serving
│   ├── main.py
│   ├── routes/
│   └── ws/
├── frontend/            # Vue SPA dashboard
├── research/             # Fine-tuning experiments, backtesting
│   ├── data/            # Deriv historical OHLCV CSVs
│   ├── experiments/     # Fine-tune configs, results
│   └── notebooks/       # Analysis Jupyter notebooks
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

### What Changed in Structure

| Before | After |
|--------|-------|
| `soldier/indicators.py` | Removed — Kronos handles this |
| `soldier/signals.py` | Simplified — prediction threshold logic |
| `watcher/features.py` | Removed — no feature engineering needed |
| `watcher/model.py` | Removed — no HMM/XGBoost model |
| `watcher/classifier.py` | Replaced by `regime.py` (threshold-based) |
| N/A | `kronos/` — new, foundation model code |
| N/A | `research/data/` — Deriv historical data for fine-tuning |
| N/A | `research/experiments/` — fine-tune experiments |
