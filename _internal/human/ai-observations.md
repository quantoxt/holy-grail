# AI Observations — Full Project Review (2026-08-14)

An honest, whole-system judgement: what's real, what's weak, what to add, what to cut.
Written after reading every layer: providers, soldier, watcher, sentinel, shared, api, frontend, migrations, and the live logs from the VPS.

> **Status 2026-08-14 (later same day):** #1 measurement loop, #3 Watcher seeding, #6 broker-deal
> P&L on close, kronos_predictions pruning, Config.vue dead code, log rename, UTC week boundary,
> and money-math tests are DONE and deployed. Shadow scanning runs even while the goal is banked.
> Still open: per-instrument validation on VAST AI (#2), ops watchdog (#4), api/ removal, HF_TOKEN.
> Note: `max_open_positions: 10` is INTENTIONAL (user decision) — do not "fix" it.

---

## The blunt verdict

**The engineering is ahead of the evidence.** The bot is well-built — crash reconciliation, goal-aware exits, risk caps, hot-reload config, broker-truth accounting — but it is elaborate infrastructure sitting on top of an edge that has been measured **once, on one instrument (BTCUSD spot, Binance), at N=1, in backtest**. You are now trading it on gold, silver, and cable CFDs, where **no validation has ever been done**. That is the single biggest risk in this project — not the code, the statistics.

Second structural weakness: **the bot is blind to its own performance.** It records trades, but it never systematically answers "was the model right?" per symbol, per hour, per regime. Without that loop, every tuning decision (N=5, confidence gates, SL multipliers) is done by vibes from n=6 Telegram anecdotes. Fixing measurement is cheaper and more valuable than any trading-logic change.

Third: **the process is one power-cut away from silence.** The scheduled task only starts at boot; a crash mid-week leaves the bot dead until you notice. We already lived this once (the unicode crash).

---

## What's genuinely good (keep, don't touch)

- **Position reconciliation on startup** (magic-number filter, deal-history close reconciliation). Most retail bots don't have this. It's the difference between "restarted" and "recovered."
- **Goal-aware exits**: equity ceiling close-all + profit-lock ratchet + predicted-level TP. The exit stack now matches the thesis (directional edge, distrust magnitude).
- **Min-lot risk reality check** (actual $-at-SL vs `risk_cap_pct`). This is what saved the account from the overnight blowup class of bug.
- **Broker-truth accounting** (weekly/realized P&L from deal history) — the dashboard now can't lie to you.
- **Hot-reload RuntimeConfig** across processes via Supabase. Genuinely good design.
- **Crash-proof logging** (utf-8, never-raise log()).

---

## Top priorities — in order of value

### 1. Close the measurement loop (highest value, low effort)
The bot already computes a prediction every cycle for every active symbol. Most are HOLD or skipped — **and then thrown away**. Log the *outcome* of every prediction, traded or not:

- At prediction time we know: symbol, direction, predicted move, confidence, SNR, N-sample path.
- Two hours later (h=24), fetch the actual close and record hit/miss.

This gives you, for free, within a week or two:
- Real per-symbol directional accuracy (is gold actually 54%, or 49%?)
- Whether N=5 beats N=1 (run both shadows if CPU allows, or alternate cycles)
- Whether the confidence score and SNR gate actually separate winners from losers — turning the current fake confidence into a calibrated one.

Implementation sketch: a `prediction_evaluations` table + a small task in the telemetry loop that resolves predictions whose horizon elapsed. This is *the* item I'd do before anything else. It also directly feeds the Watcher drift switch (see #3).

### 2. Validate before you trust the metals
Right now XAUUSD/XAGUSD/GBPUSD are active on **zero evidence**. The BTCUSD validation pipeline exists (`research/validate.py`, `fetch_binance.py`). Re-run it per instrument on data that matches the actual feed — MT5 CFD candles, not Binance spot — before believing last week's +$14 was skill rather than a lucky gold move. Be especially honest about this: one XAUUSD trade made +$13.07 of the +$14 week. **One trade is not an edge.** If gold's true accuracy is coin-flip, last week was a coin flip that happened to fund the goal.

### 3. The drift kill switch is effectively dead — and you haven't noticed
`watcher/regime.py` keeps a rolling accuracy deque **in memory**. Every restart (which happens on most deploys) wipes it, and warmup is 10 resolutions. Worse, it scores *trades taken*, not *predictions made* — a skipped signal teaches it nothing, and HOLDs are invisible to it. In production it has likely never once reached warmup before a restart reset it. Fix: persist resolutions to a table (which #1 gives you anyway) and have the Watcher read from it. Layer 2 currently exists mostly on paper.

### 4. Ops: make the bot unkillable-ish
- **Watchdog**: the Scheduled Task triggers AtStartup only. Add a second task (every 5 min) that starts HolyGrail if not running (`tasklist` check + `schtasks /run`), or run under NSSM as a real service with auto-restart. A crashed bot with open positions and no SL management is your worst case.
- **Heartbeat alerting**: the dashboard shows a red OFFLINE badge, but nobody looks at a dashboard at 3am. Send a Telegram message if telemetry hasn't run for >60s (a tiny second process, or the watchdog task).
- **Backups**: `data/mt5_accounts.json` and `.env` exist only on the VPS. Copy them somewhere safe (they're gitignored for good reason — back them up another way).
- **Power**: the VPS is on a LAN IP (<lan-ip>). If that box is at home, a power cut or ISP blip takes the bot down with open positions. The hard SLs make this survivable, but know that it's your design's tolerance: SL is the safety net, not the bot.

### 5. Config drift is silently contradicting the design
Current cloud `bot_config` row says `max_open_positions: 10`, `max_risk_per_trade: 10`, `max_weekly_drawdown: 100`. The documented design says 2 / ~$10 / $100-drawdown-on-$500... but **10 open positions on a $500 account is not the framework you described to me**. Likely leftovers from auto-calibrate or dashboard edits. Two fixes:
- Audit and reset these to intended values.
- Structural: the dashboard lets you edit numbers that interact fatally (e.g. daily loss cap > weekly drawdown). Add cheap cross-field validation in Config.vue (warn when max_open_positions > 3 on sub-$1k accounts, etc.). Guardrails on the guardrails.

### 6. Record broker-truth P&L on every close
`_close_position` still *computes* P&L from price diff and stores that in `trades`. The broker's deal history has the real number (incl. swap/commission — you already use it for externally-closed trades). After every close, look up the deal and store its P&L. Then the trades tab, win-rate, and everything downstream is exact, and the estimate/backfill mess we hand-fixed in August never recurs. Swap matters more than you'd think on metals CFDs held ~2h.

---

## What to REMOVE / simplify (scope is a feature)

1. **`api/` FastAPI backend** — the production dashboard (Vercel) reads Supabase directly; the bot doesn't call the API; the API isn't deployed anywhere in prod. It's a second, drift-prone copy of read paths (its `/api/performance` still returns the estimated P&L we just fixed in the frontend). Either delete it, or reduce it to the control endpoints only. Carrying dead layers means someday fixing a bug in the wrong place.
2. **`MARKET_MODE`** — admitted vestigial in CLAUDE.md. Delete the env var and its reference in `/api/status`.
3. **`_archive/`** — keep as read-only history if you want, but it's ~dead weight in every search and grep. Consider moving out of the repo tree.
4. **`paper_log.jsonl`** naming — the file is the LIVE audit log; the name lies. Rename to `bot_log.jsonl` (one line, one deploy).
5. **Config.vue's dead weekly computation** — after removing the card, `computeWeekly` and the `weekly` ref still run on every poll for nothing. Delete.
6. **`kronos_predictions` bloat** — it stores the full 24-candle prediction array per symbol per 5-min cycle. That's ~1k rows/day of mostly-duplicated JSON. Either store only summary fields + a hash of the path, or add a nightly prune (delete >7 days). Supabase cloud storage isn't free forever.
7. **`SYMBOL_SPECS` fallback in sentinel/risk.py** — broker specs are always fetched live; the hardcoded table is a stale-data trap (wrong contract size = wrong risk). Keep only as last-resort, or drop entirely and refuse to trade without live specs.

## Smaller things worth doing

- **Per-instrument `max_move_pct`** — a 1.5% cap is huge for GBPUSD (~0.3% typical 2h) and tight for gold on CPI days. Percentile-based per symbol (e.g. 95th percentile of realized 24-bar moves) is one small change now that `vol` is computed per symbol.
- **Week-boundary consistency** — bot resets Monday 00:00 **UTC**, dashboard computes week-start in **local time**. Harmless now; will produce one confusing Sunday-evening card a few times a year.
- **Trades tab "Result" for open positions** — show floating P&L or a clear "open" chip; mixing open rows into win/loss stats invites misreads.
- **Telegram daily digest** — one message a day (positions, weekly P&L, next news event). You already have the channel; make it summarise, not just event-spam.
- **Unit tests for the money math** — `lot_size`, `check_kill` boundaries (ceiling ±0.01, withdraw-unlatch, floor), `_manage_exits` ratchet logic. ~100 lines of pytest, no mocks needed, and these are exactly the functions whose silent bugs cost money.
- **Commit the work** — there are weeks of uncommitted changes on `main` right now. The repo is the backup of your own labor; a crash on the VPS + unpushed local = archaeology. (I haven't committed anything because you haven't asked me to — but you should.)
- **HF_TOKEN** — the VPS log spams unauthenticated HuggingFace warnings and risks rate-limiting model downloads. Free token, one env var.

## Things I'd explicitly NOT do (yet)

- **Fine-tuning Kronos** — already failed once on synthetics; live-data fine-tuning needs far more clean data than exists yet. Parked until #1 produces months of evaluations.
- **More symbols** — you just correctly pruned to 3. Adding instruments multiplies validation debt, not edge.
- **Fancy ML on top** (meta-labeling, ensemble models) — premature by ~2 months of data. The boring measurement loop first.
- **Bigger account / prop firm** — until gold/silver have per-instrument accuracy numbers behind them, scaling capital scales variance, not income.

---

## The one-paragraph summary

You've built a genuinely solid execution-and-risk machine around a hypothesis. The hypothesis is untested on the instruments it's currently trading, and the bot has no systematic way to tell you whether it's right. Before adding any trading intelligence, invest in: (1) evaluate every prediction against reality, (2) validate each instrument on broker-feed data, (3) make the process survive crashes and notify you when it can't, (4) delete the dead layers so the system you reason about is the system that runs. Then — and only then — the question "should this bot manage $5k?" becomes answerable with data instead of hope.
