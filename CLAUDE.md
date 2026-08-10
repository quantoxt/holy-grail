# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Holy Grail Is

An AI-enhanced algorithmic trading bot using the **Kronos foundation model** (AAAI 2026, MIT) to predict OHLCV candles on **live markets via a single MT5 broker** — forex/metals and crypto-CFDs (BTCUSD etc.) all through one logged-in account. The bot trades a validated directional edge on a goal-driven risk framework.

**The edge:** Pre-trained Kronos (zero-shot, no fine-tuning) on BTC/USDT 5m achieves **54.7% directional accuracy at h=24 (~3σ above coin-flip)**. This is a small but real edge, amplified to profit by the Sentinel risk architecture. **CFD caveat:** the edge was measured on Binance spot data; a broker's crypto-CFD feed differs (wider spread, not always 24/7), so direction transfers but magnitude/SL and spread won't match exactly — and non-24/7 CFDs can perturb the clean h=24 exit.

**Synthetics are dead:** Deriv CSRNG synthetics were exhaustively tested (direction, range, digits — all coin-flip or worse). The project pivoted to live markets. See `_archive/` for the synthetic-era research.

## Architecture — Three Layers + Providers + Dashboard

```
providers/     MarketProvider ABC → MT5Provider only (single broker: forex/metals/crypto-CFD)
soldier/       Layer 1 — SignalEngine (Kronos inference) + loop.py (trading loop + 5s telemetry heartbeat)
watcher/       Layer 2 — confidence gate + rolling-accuracy drift kill switch
sentinel/      Layer 3 — goal-driven risk manager (Sentinel v2: weekly goal, equity floor, lot sizing)
shared/        config.py (Settings) + runtime_config.py (Supabase-backed, dashboard-adjustable) + database.py (Supabase) + telegram.py
api/           FastAPI backend (REST + control endpoints + /api/account + /api/symbols)
frontend/      Vue 3 + Tailwind 4 dashboard (Dashboard, Trades, Risk, Config views)
supabase/      DB migrations (001_core_audit, 002_grants, 003_mt5_accounts, 004_runtime_state)
model/Kronos/  Kronos model code (model/ — inference; finetune_csv/ — future fine-tuning)
research/      Validators + analysis tools (validate.py, fetch_binance.py, rr_validation.py)
```

## Key Decisions (locked)

- **Single broker (MT5 only).** Binance is gone. All instruments — forex, metals, and crypto (as broker CFDs, e.g. `BTCUSD`) — trade through one logged-in MT5 account. Symbols are auto-discovered from the broker (`mt5.symbols_get`) and curated at runtime; the loop silently skips any active symbol the logged-in broker doesn't offer.
- **Live only, no paper mode.** All trading on demo/live MT5 accounts. The loop's `--live` flag places real orders.
- **Cross-process hot-reload.** `RuntimeConfig` is backed by the `bot_config` Supabase row. The API (dashboard writer) persists on PATCH; the bot re-reads it every ~5s from its telemetry task. So symbol/risk/Start-Stop edits reach a running bot within seconds — no restart.
- **Goal-aware exit (revised 2026-08-10, was "h=24 only").** 3:1 R:R was validated as non-viable (noise-killed SL). The bot enters on signal, places a hard SL safety net (2× predicted move), and **three** exits now apply: (a) h=pred_len horizon close (max hold), (b) **goal-aware profit-lock** — once a trade's floating P&L ≥ `profit_lock_target`, the SL ratchets to lock profit so a winner can't become a loss, and once **live equity** ≥ `baseline + weekly_goal` the bot closes ALL positions and stops for the week (banks the goal; this is what the overnight run exposed — a +$14 floating held to horizon became −$7). No fixed TP that would cut every winner at h=24; the trail only ever exits in profit.
- **Min-lot risk reality (revised 2026-08-10).** The broker floors lot to 0.01, so the actual $-at-SL is whatever min-lot dictates — NOT `max_risk_per_trade`. The bot **accepts min-lot** (scales risk to it) but refuses any trade whose actual $-at-SL exceeds `risk_cap_pct` (3%) of equity — the guard against the overnight blowup where a "$1 risk" trade risked ~$100. Actual risk is computed, logged, and stored per position.
- **Crash-resilient positions.** On startup the loop **reconciles `self.open` from the broker's real positions** (filtered by magic `MAGIC=234000`) — a restart/crash never orphans an open trade. The bot only ever manages its own positions, never a manual one.
- **Pre-trained Kronos, no fine-tuning.** Kronos-small (`NeoQuasar/Kronos-small`) works zero-shot on live markets. Fine-tuning on CSRNG synthetics FAILED (47% directional). Fine-tuning on live data is optional future work.
- **Sentinel v2 risk framework:** weekly $14 goal on $50 baseline, anti-compounding (profit withdrawn weekly), **min-lot-scaled risk capped at `risk_cap_pct` of equity**, `$baseline+$goal` equity ceiling (close-all + stop), $3 daily loss cap, $40 equity floor, max 2 positions, Thursday aggression boost. All dashboard-adjustable via RuntimeConfig.
- **MT5 runs on Windows** (MetaTrader5 Python package is Windows-only). The bot runs under Windows Python. Dev/analysis on Linux/WSL; production on a Windows VPS.
- **Multi-account MT5:** `data/mt5_accounts.json` holds named accounts; switch via `--account name` or the JSON `active` field (also switchable from the dashboard).

## How to Run

**Windows (MT5 forex — primary):**
```bat
cd C:\holy-grail-win
set PYTHONPATH=C:\holy-grail-win\model\Kronos
C:\holy-grail-venv\Scripts\python -m soldier.loop --live --account demo
```

**WSL/Linux (dev only — MT5 won't run here):**
```bash
./venv-torch/bin/uvicorn api.main:app --port 8000         # API
cd frontend && npm run dev                                 # dashboard (:5173)
```

**Dashboard:** `localhost:5173` — 4 views: Dashboard (live account state + signals + stats), Trades (history), Risk (events), Config (control panel — set goal, adjust params, pick symbols, start/stop).

## Environment

- **Bot venv:** `venv-torch/` (Python 3.12 via uv, torch CPU + fastapi + supabase + dotenv). For MT5 on Windows: separate `C:\holy-grail-venv\` (Windows Python 3.12 + MetaTrader5).
- **.env** (gitignored): `TIMEFRAME`, `BASE_STAKE`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `KRONOS_PATH`, Telegram creds. MT5 creds in `data/mt5_accounts.json`. (`MARKET_MODE` is vestigial — provider selection no longer branches on it.)
- **Supabase:** local Docker (54321 API, 54322 DB). Tables: kronos_predictions, signals, trades, risk_events, bot_sessions, mt5_accounts, bot_config (single row), account_state (per-login heartbeat). Migrations in `supabase/migrations/`.
- **RuntimeConfig** (`shared/runtime_config.py`): mutable params (weekly_goal, risk caps, active_symbols, bot_running) — Supabase-backed (`bot_config` row); PATCHed live from the dashboard, the bot re-reads every ~5s, no restart.

## Frontend Conventions

Vue 3 + Tailwind CSS 4. Add `@reference "tailwindcss";` in `<style>` blocks. Read `frontend/src/assets/default.css` for color tokens — use `bg-(--bg)`, `text-(--text)`, `text-(--profit)`, etc. (not invented classes).

## Working in This Repo

- **`_archive/`** contains dead Deriv/synthetic research (reference only — don't modify or revive).
- **`_internal/fine-tune.md`** is the risk framework spec (implemented in Sentinel v2).
- **`_internal/build/frontend-plan.md`** has the full dashboard design (6 views, API contract).
- The bot is designed for **Windows VPS deployment** (MT5 native). Dev on Linux/WSL; production on Windows.
