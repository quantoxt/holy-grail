# Holy Grail 🏆

An AI-enhanced algorithmic trading bot that uses the **Kronos foundation model**
(AAAI 2026, MIT) to predict OHLCV candles on **live markets via a single MT5 broker**
— forex, metals, and crypto-CFDs all through one logged-in account — governed by a
goal-driven risk framework ("Sentinel v2").

> **Reality check before you run this:** the only statistically validated edge is
> **BTCUSD 5m, h=24 (2h horizon): 54.7% directional accuracy (~3σ above coin-flip)**,
> measured zero-shot with pre-trained Kronos on Binance spot data. Validation on
> XAUUSD / XAGUSD / GBPUSD (13 months of broker M5 data, N=1 and N=5) came back
> coin-flip — see `_internal/results/kronos-validation-history.md` for the full test
> log. **This is an experimental system. Run it on demo accounts. Expect nothing.**

---

## Architecture — three layers + providers + dashboard

```
providers/     MarketProvider ABC → MT5Provider only (single broker)
soldier/       Layer 1 — SignalEngine (Kronos inference) + loop.py (trading loop + 5s telemetry)
watcher/       Layer 2 — confidence gate + rolling-accuracy drift kill switch
sentinel/      Layer 3 — goal-driven risk manager (weekly goal, equity floor, lot sizing)
shared/        config.py + runtime_config.py (Supabase-backed hot-reload) + database.py + telegram.py
frontend/      Vue 3 + Tailwind 4 dashboard (Dashboard, Trades, Risk, Config views)
supabase/      DB migrations
model/Kronos/  Kronos model code (vendored; inference + optional fine-tuning)
research/      Validators + data tools (validate.py, fetch_mt5.py, fetch_binance.py)
_archive/      Dead synthetic-era research (reference only)
```

No API layer — the Vercel dashboard reads/writes Supabase directly via RPC.

### How a trade happens
1. Every 5 minutes the loop runs Kronos over each active symbol: 512-candle lookback
   → 24-candle (2h) prediction → direction/magnitude/confidence/SNR.
2. Filters: plausibility cap on predicted move, `min_confidence`, spread-vs-move,
   SNR, correlation, market-open checks, and a per-trade $-at-SL risk cap.
3. Exits: predicted-level take-profit, h=24 horizon close (max hold), SL ratchet
   (breakeven lock → profit lock), and the weekly-goal bank (close all at
   `baseline + weekly_goal`, stop for the week — resume by withdrawing the profit).
4. Layer 2 (Watcher) blocks trading if the model's rolling resolved-prediction
   accuracy drops below 50%. Layer 3 (Sentinel) enforces weekly goal, daily loss
   cap, equity floor, and max positions.

### Crash resilience
On startup the bot reconciles its open positions from the broker (filtered by its
magic number), re-seeds weekly/daily P&L from the broker's deal history, and
re-seeds the Watcher's drift window from the `prediction_evaluations` table — a
restart never orphans a trade or wipes risk state.

---

## Prerequisites

- **Windows** machine/VPS with the **MT5 terminal** installed and logged in
  (the `MetaTrader5` Python package is Windows-only; AutoTrading must be enabled)
- Python 3.12
- A **Supabase** project (free tier works)
- Node 20+ (only for the dashboard)
- Optional: Telegram bot for alerts; HuggingFace account to pull Kronos weights

## Setup

### 1. Clone + Python env
```bat
git clone <repo> C:\holy-grail-win
cd C:\holy-grail-win
python -m venv C:\holy-grail-venv
C:\holy-grail-venv\Scripts\pip install -r requirements.txt MetaTrader5
```

### 2. Supabase
1. Create a project at supabase.com.
2. Apply the migrations in order (SQL editor or `supabase db push`):
   `supabase/migrations/001_*.sql` … `010_*.sql`.
3. Copy the project URL and **service_role key** (Settings → API).

### 3. Configure
```bat
copy .env.example .env
notepad .env
```
Fill in `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, optionally Telegram creds.

MT5 credentials go in `data/mt5_accounts.json` (gitignored — copy the template):
```bat
copy data\mt5_accounts.example.json data\mt5_accounts.json
```
Add your broker account(s): login, password, server. Switch accounts by setting
`"active"`, or later from the dashboard.

### 4. Kronos weights
The bot loads `NeoQuasar/Kronos-small` + `NeoQuasar/Kronos-Tokenizer-base` from
HuggingFace on first run (set `HF_TOKEN` in `.env` if you hit rate limits). With
`KRONOS_PATH=model/Kronos` the vendored inference code is used as-is — no
fine-tuning required or recommended (it failed on synthetics; see the results log).

### 5. Run
```bat
set PYTHONPATH=C:\holy-grail-win\model\Kronos
C:\holy-grail-venv\Scripts\python -m soldier.loop --live --account demo
```
Flags: `--cycles N` (run N cycles and exit), `--interval SEC` (default 300),
`--account NAME` (pick from mt5_accounts.json).

For unattended running, wrap it in a Windows Scheduled Task; a watchdog task that
re-launches the bot every 5 minutes if it died is recommended.

### 6. Dashboard
```bash
cd frontend
npm install
cp .env.vercel .env.local   # then fill in YOUR Supabase URL + anon key
npm run dev                 # http://localhost:5173
```
Deploy the `frontend/` dir to Vercel for a hosted dashboard (env vars:
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`).

**Dashboard views:** Dashboard (live account state, signals, weekly goal bar),
Trades (history), Risk (kill-switch events), Config (adjust goal/risk/symbols,
switch MT5 account, start/stop — all hot-reloaded by the bot within ~5s).

---

## Configuration

Two layers:
- **`.env` / `shared/config.py`** — static: timeframe, lookback/pred_len,
  thresholds (see `.env.example`).
- **Supabase `bot_config` row / `shared/runtime_config.py`** — everything you'd
  want to tweak live from the dashboard: `weekly_goal`, `baseline_equity`,
  `risk_cap_pct`, `min_confidence`, `max_move_pct`, `active_symbols`,
  `max_open_positions`, `sl_atr_mult(s)`, `tp_at_predicted`, `bot_running`, …

**Defaults worth knowing:** `pred_len=24` on 5m = 2h horizon; SL is
ATR-based (per-instrument multipliers) with a 2× predicted-move fallback;
weekly goal $14 on a $500 baseline; trades are min-lot floored and refused if
the actual $-at-SL exceeds `risk_cap_pct` of equity.

## Validating a symbol before trading it

```bash
python research/fetch_mt5.py --symbol XAUUSD --timeframe 5m   # export candles (Windows)
python research/validate.py --symbol XAUUSD --tf 5m --pretrained --test-size 200000 --stride 24 --sample-count 5
```
Walk-forward directional accuracy is reported per horizon; confidence slices too.
**Gate: 55%+ at your traded horizon.** GPU (e.g. a rented RTX 5060 Ti) runs this
~30× faster than CPU for a couple of dollars at most. Full history of what has and
hasn't worked: `_internal/results/kronos-validation-history.md`.

## Tests

```bash
python -m tests.test_sentinel   # Sentinel risk-framework unit tests (7)
```

---

## Repo etiquette

- `.env` and `data/mt5_accounts.json` are **gitignored — never commit credentials**
  (rotate anything if they ever were).
- `_archive/` is dead-end research kept for reference; don't revive it.
- `_internal/` holds design docs and human notes; `CLAUDE.md` is the AI-assistant
  context.

## License / attribution

Kronos model code in `model/Kronos/` is vendored from the MIT-licensed
[NeoQuasar/Kronos](https://github.com/KronosKronos/Kronos) release — see its
README for terms. Everything else in this repo: use at your own risk.
