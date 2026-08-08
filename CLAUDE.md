# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Holy Grail Is

An AI-enhanced algorithmic trading bot using the **Kronos foundation model** (AAAI 2026, MIT) to predict OHLCV candles on **live markets** (forex/metals via MT5, crypto via Binance). The bot trades a validated directional edge on a goal-driven risk framework.

**The edge:** Pre-trained Kronos (zero-shot, no fine-tuning) on BTC/USDT 5m achieves **54.7% directional accuracy at h=24 (~3σ above coin-flip)**. This is a small but real edge, amplified to profit by the Sentinel risk architecture.

**Synthetics are dead:** Deriv CSRNG synthetics were exhaustively tested (direction, range, digits — all coin-flip or worse). The project pivoted to live markets. See `_archive/` for the synthetic-era research.

## Architecture — Three Layers + Providers + Dashboard

```
providers/     MarketProvider ABC → BinanceProvider (crypto) + MT5Provider (forex/metals)
soldier/       Layer 1 — SignalEngine (Kronos inference) + loop.py (trading loop)
watcher/       Layer 2 — confidence gate + rolling-accuracy drift kill switch
sentinel/      Layer 3 — goal-driven risk manager (Sentinel v2: weekly goal, equity floor, lot sizing)
shared/        config.py (Settings) + runtime_config.py (dashboard-adjustable) + database.py (Supabase) + telegram.py
api/           FastAPI backend (REST + control endpoints)
frontend/      Vue 3 + Tailwind 4 dashboard (Dashboard, Trades, Risk, Config views)
supabase/      DB migrations (001_core_audit, 002_grants)
model/Kronos/  Kronos model code (model/ — inference; finetune_csv/ — future fine-tuning)
research/      Validators + analysis tools (validate.py, fetch_binance.py, rr_validation.py)
```

## Key Decisions (locked)

- **Live only, no paper mode.** All trading on demo/live accounts via MT5 (or Binance futures). The loop's `--live` flag places real orders.
- **Time-based exit (h=24), not 3:1 R:R.** 3:1 R:R was validated as non-viable (noise-killed SL, unreachable TP). The bot enters on signal, places a hard SL as a safety net (2× predicted move), and closes at the h=24 horizon.
- **Pre-trained Kronos, no fine-tuning.** Kronos-small (`NeoQuasar/Kronos-small`) works zero-shot on live markets. Fine-tuning on CSRNG synthetics FAILED (47% directional). Fine-tuning on live data is optional future work.
- **Sentinel v2 risk framework:** weekly $14 goal on $50 baseline, anti-compounding (profit withdrawn weekly), $1/trade risk, $3 daily loss cap, $40 equity floor, max 2 positions, Thursday aggression boost. All dashboard-adjustable via RuntimeConfig.
- **MT5 runs on Windows** (MetaTrader5 Python package is Windows-only). The bot runs under Windows Python for forex. Crypto (Binance) can run in WSL or Windows.
- **Multi-account MT5:** `data/mt5_accounts.json` holds named accounts; switch via `--account name` or the JSON `active` field.

## How to Run

**Windows (MT5 forex — primary):**
```bat
cd C:\holy-grail-win
set PYTHONPATH=C:\holy-grail-win\model\Kronos
C:\holy-grail-venv\Scripts\python -m soldier.loop --live --account demo
```

**WSL/Linux (crypto or dev):**
```bash
./venv-torch/bin/python -m soldier.loop --live           # bot (live)
./venv-torch/bin/uvicorn api.main:app --port 8000         # API
cd frontend && npm run dev                                 # dashboard (:5173)
```

**Dashboard:** `localhost:5173` — 4 views: Dashboard (signals + stats), Trades (history), Risk (events), Config (control panel — set goal, adjust params, start/stop).

## Environment

- **Bot venv:** `venv-torch/` (Python 3.12 via uv, torch CPU + ccxt + fastapi + supabase + dotenv). For MT5 on Windows: separate `C:\holy-grail-venv\` (Windows Python 3.12 + MetaTrader5).
- **.env** (gitignored): `MARKET_MODE`, `TIMEFRAME`, `BASE_STAKE`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `KRONOS_PATH`, provider creds. MT5 creds in `data/mt5_accounts.json`.
- **Supabase:** local Docker (54321 API, 54322 DB). Tables: kronos_predictions, signals, trades, risk_events, bot_sessions. Migrations in `supabase/migrations/`.
- **RuntimeConfig** (`shared/runtime_config.py`): mutable params (weekly_goal, risk caps, symbols, bot_running) — PATCHed live from the dashboard, no restart.

## Frontend Conventions

Vue 3 + Tailwind CSS 4. Add `@reference "tailwindcss";` in `<style>` blocks. Read `frontend/src/assets/default.css` for color tokens — use `bg-(--bg)`, `text-(--text)`, `text-(--profit)`, etc. (not invented classes).

## Working in This Repo

- **`_archive/`** contains dead Deriv/synthetic research (reference only — don't modify or revive).
- **`_internal/fine-tune.md`** is the risk framework spec (implemented in Sentinel v2).
- **`_internal/build/frontend-plan.md`** has the full dashboard design (6 views, API contract).
- The bot is designed for **Windows VPS deployment** (MT5 native). Dev on Linux/WSL; production on Windows.
