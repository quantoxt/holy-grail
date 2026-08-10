# Architecture — How the Bot Fits Together

## The layers

The bot is built as three cooperating layers (a "signal → risk → guard" pipeline) plus
providers, shared infra, and a dashboard. Each layer has one job and can veto the one below.

### Layer 1 — Soldier (the trader)
`soldier/signal.py` + `soldier/loop.py`
- **SignalEngine** loads Kronos and turns raw candles into a signal: direction (BUY/SELL/HOLD),
  predicted move, confidence, an SL price, and a signal-to-noise ratio.
- **loop.py (the Trader)** is the main loop. Every cycle (~5 min) it: resolves matured
  positions, checks the kill switch, scans every active symbol, ranks by opportunity, and
  opens the best trades within the position limit. A separate 5-second **telemetry** task
  publishes live account state, manages exits (profit-lock/breakeven trails), and banks the
  weekly goal.

### Layer 2 — Watcher (accuracy guard)
`watcher/regime.py`
- A confidence gate + a **drift kill switch**: it tracks whether Kronos's *resolved*
  predictions are actually right. If recent accuracy falls to coin-flip, it blocks all
  trading for the cycle — the safety net against the model going sideways in live conditions.

### Layer 3 — Sentinel (risk manager)
`sentinel/risk.py`
- The goal-driven risk brain. Owns: the weekly goal + equity ceiling, the daily loss cap,
  the equity floor, per-trade risk sizing, lot computation, the profit-lock, and all kill
  switches. Every risk number you see comes from here. See `risk-framework.md`.

### Providers (market access)
`providers/mt5.py` (+ `providers/base.py`)
- The only provider is **MT5** (single broker). It talks to the MetaTrader 5 terminal for
  candles, account info, positions, order send/close, SL modification, and symbol resolution
  (brokers name instruments differently — `EURUSD` vs `EURUSD.` — the resolver handles that).
- Every order is tagged with **magic 234000** so the bot only ever manages its own positions,
  never a manual trade on the account.

### Shared (plumbing)
- `shared/config.py` — **Settings**: immutable config from `.env` (model paths, timeframe, Supabase/Telegram creds, thresholds).
- `shared/runtime_config.py` — **RuntimeConfig**: the live, dashboard-adjustable params (goal, caps, symbols, start/stop). Supabase-backed.
- `shared/database.py` — the audit logger (predictions, signals, trades, risk events, account heartbeat).
- `shared/telegram.py` — trade open/close + alerts.
- `shared/mt5_accounts.py` — MT5 account switching (Supabase `mt5_accounts` is the single source of truth).
- `shared/symbols.py` — the curated `PREFERRED_SYMBOLS` list.
- `shared/news.py` — economic-news blackout check.

### API + Frontend
- `api/` (FastAPI) — largely **superseded**. The dashboard now talks to Supabase **directly** (Vercel → cloud Supabase, anon key). The API exists for local dev but isn't in the production path.
- `frontend/` (Vue 3 + Tailwind) — the dashboard on Vercel. Four views: Dashboard, Trades, Risk, Config.

## How data flows

```
MT5 terminal ──candles──> Soldier (Kronos signal)
      │                        │
      │                        ▼
      │                   Sentinel (risk/lot/stop) ──┐
      │                        │                     │
      │                        ▼                     ▼
      │ <──orders── Soldier ◄──┘                Watcher (accuracy gate)
      │
      └──account/positions──> telemetry (5s) ──> Supabase account_state
                                                      │
                                                      ▼
                                               Dashboard (Vercel, polls 5s)
```

- **Bot → Supabase:** every prediction/signal/trade/risk-event is logged; the 5s heartbeat
  writes live balance/equity/positions/symbols to `account_state`.
- **Dashboard → Supabase:** reads `account_state`/`trades`/`signals`/`risk_events`, and
  writes config via the `update_bot_config` merge RPC.
- **Bot ← Supabase:** re-reads `bot_config` every 5s (hot-reload) and the active MT5 account.
- **Bot ↔ MT5:** the only thing that actually places orders.

## The database tables (Supabase)
| Table | Who writes | What it's for |
|---|---|---|
| `bot_config` | dashboard (RPC) / bot reads | the live tunable settings (one row) |
| `account_state` | bot (5s heartbeat) | live balance/equity/positions per login |
| `signals` | bot | every BUY/SELL/HOLD call |
| `kronos_predictions` | bot | raw Kronos inference audit (predictions + timing) |
| `trades` | bot | trade open/close ledger (tagged `mt5_login` for per-account stats) |
| `risk_events` | bot | kill switches, drift, cap-skips, goal-banked |
| `mt5_accounts` | dashboard | the MT5 accounts + which is active |

## Where it physically runs
- **Bot + MT5 terminal:** Windows VPS (`aurora@192.168.0.179`). The `MetaTrader5` Python
  package is Windows-only, so production is Windows. Bot runs as Scheduled Task `HolyGrail`
  (`pythonw`, no console window), terminal auto-starts via task `StartMT5`.
- **Dashboard:** Vercel (`https://holygrail.quantoxtinc.com`).
- **Database:** Supabase cloud (project `holy-grail`, region eu-west-1).
- **Dev/analysis:** Linux/WSL (can't run MT5 here, but everything else builds/tests).
