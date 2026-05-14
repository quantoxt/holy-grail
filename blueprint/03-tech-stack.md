# Technology Stack

---

## Core Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Execution** | Python + Deriv WebSocket API | Real-time tick streaming, trade execution |
| **AI Processing** | FastAPI | Middle-man between AI logic and broker |
| **Database** | Supabase via Docker (local) | Log every tick, bot decision, trade result |
| **ML Engine** | scikit-learn, XGBoost, hmmlearn | Regime detection, pattern recognition |
| **Risk AI** | LLM API (GLM) | Confidence scoring, performance audit |
| **Alerts** | Telegram Bot API | Real-time notifications to phone |
| **Hosting** | Local machine (VPS only for live phase) | Local dev, VPS near Deriv for live only |

## Python Libraries

### Execution Layer
- `python-deriv-api` — Official Deriv WebSocket client (PyPI)
- `websockets` — Low-level WebSocket if we need more control
- `asyncio` — Async event loop for concurrent operations
- `pandas` / `numpy` — Data processing, indicator calculation

### Technical Analysis
- `ta-lib` or `pandas-ta` — EMA, RSI, Bollinger Bands, ATR, ADX
- Custom indicator logic where libraries fall short

### Machine Learning
- `scikit-learn` — Clustering, classification, preprocessing
- `xgboost` — Gradient boosting for regime classification
- `hmmlearn` — Hidden Markov Models for unsupervised regime detection

### Data & Database
- `supabase-py` — Supabase Python client
- `psycopg2` — Direct PostgreSQL if needed

### Monitoring & Visualization
- Built-in dashboard (web-based, FastAPI served)
- `plotly` / `matplotlib` — Chart generation for analysis
- Telegram bot for mobile alerts

## Infrastructure

### VPS Requirements
- **Location:** Near Deriv servers (check Deriv docs for server locations)
- **OS:** Ubuntu 22.04 LTS or similar Linux
- **RAM:** 2-4 GB minimum
- **CPU:** 2 cores minimum
- **Storage:** 20 GB+ (tick data accumulates fast)
- **Network:** Low latency, stable connection

### Why VPS Near Deriv?
Execution latency matters. Every millisecond between signal detection and order execution is slippage. A VPS in the same data center region as Deriv's matching engine minimizes this.

## Existing Assets

- **Telegram bot project** — already built by Quantoxt, reuse for alert system
- **Local Supabase** — Docker install already running
- **AI codebase analysis model** — for deep-diving pulled-down GitHub repos

1. **Local development** — build and test on laptop with demo account
2. **Paper trading** — run on local or VPS with demo account, log everything
3. **Analysis** — review logs, tweak parameters, retrain models
4. **Small live** — minimum viable deposit, real money, strict limits
5. **Scale** — increase capital only after proven track record

## Project Structure (Proposed)

```
holy-grail/
├── blueprint/          # Documentation (this folder)
├── soldier/            # Layer 1 — Execution engine
│   ├── connection.py   # WebSocket management
│   ├── indicators.py   # Technical indicator calculations
│   ├── executor.py     # Trade execution logic
│   └── signals.py      # Signal generation
├── watcher/            # Layer 2 — Regime detection
│   ├── features.py     # Feature extraction from tick data
│   ├── model.py        # ML model training & inference
│   └── classifier.py   # Regime classification pipeline
├── sentinel/           # Layer 3 — Risk management
│   ├── risk.py         # Risk calculations, drawdown tracking
│   ├── confidence.py   # Confidence scoring
│   └── scaler.py       # Lot size scaling logic
├── shared/
│   ├── config.py       # Configuration management
│   ├── database.py     # Supabase connection & logging
│   ├── models.py       # Data models (trades, ticks, regimes)
│   └── telegram.py     # Alert system
├── dashboard/          # Web monitoring dashboard
├── research/           # Backtesting, analysis notebooks
│   ├── backtest.py
│   └── notebooks/
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```
