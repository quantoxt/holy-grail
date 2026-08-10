# Dashboard Guide

The dashboard is a Vue 3 app on **Vercel** (`https://holygrail.quantoxtinc.com`). It talks
**directly to Supabase** (no backend) using the public anon key, polls every ~5s, and works
on mobile. Four views:

## Status bar (top / side)
- `● LIVE` / `● PAUSED` / `● STOPPED` — the bot's run state (from `bot_config`).
- The active symbols list.
- On the Dashboard: a red **`● BOT OFFLINE`** banner appears if the heartbeat is >30s stale
  (the process is dead/stuck or has no internet). This is your single most important signal
  that something's wrong.

## Dashboard view — the home page
- **Account card** — live balance, equity, floating P&L, and open positions (from the bot's
  5s heartbeat). If it says "Awaiting bot heartbeat," the bot isn't publishing (dead or
  mid-account-switch).
- **Stat cards** — Net P&L, win rate, trade count, W/L. These are **per the active account**
  (filtered by `mt5_login`), so a newly-connected account starts at zero.
- **Recent Signals** — the last Kronos calls (direction, predicted move, confidence).

## Trades view
The trade ledger for the **active account only**. Shows lot, entry, exit, P&L, result.
- Each trade is tagged `mt5_login`, so switching accounts shows that account's history
  (empty for a new one). Old accounts' history is preserved, not deleted.
- A trade stuck at "open" with no exit/P&L means it closed externally (SL between ticks,
  manual close, crash) and wasn't logged — the close-reconciler normally fixes this within
  seconds; if one stays "open," backfill it (see `vps-troubleshooting.md` §9a).

## Risk view
The `risk_events` audit log: every kill switch, drift block, cap-skip, and goal-banked event
with timestamp + reason. Read this to understand *why* the bot did or didn't trade.

## Config view — the control panel
This is where you actually drive the bot. Sections:

### Weekly Goal + controls
- Big P&L number vs the weekly goal + a progress bar.
- **Start / Pause / Stop** buttons (soft controls — hot-reload, no restart).
- Today's P&L, trade count, win rate, losing streak.

### Account & Auto-Calibrate
- **Account Balance** = `baseline_equity` (the framework reference, set this to the account's
  real starting balance).
- **Weekly Goal** = `weekly_goal`.
- **⚙ Auto-Calibrate** — derives risk/daily/drawdown/positions from balance + goal.
  > ⚠️ Its defaults (6% daily, 20% drawdown) are for a personal account. For a **prop**
  > account, set daily loss + drawdown **manually** to the firm's rules after calibrating.
- All the risk knobs: risk/trade, **risk cap %**, daily loss cap, drawdown, max positions,
  SL multiplier.
- **Exit policy** fields: profit-lock target/min/fraction.

### Symbols
- The curated `PREFERRED_SYMBOLS` universe with checkboxes.
- A symbol shows "n/a" if the broker doesn't offer it under any name; active-but-not-offered
  symbols are flagged (they'll be silently skipped).
- **Apply Symbols** pushes to the bot (hot-reload, no restart). If the bot is mid-trade-cycle
  you may need to wait for the next cycle (~5 min) for it to scan the new set.

### MT5 Accounts
- List of accounts; **Activate** switches the bot to one (source of truth = `mt5_accounts.is_active`).
- On switch, the bot hot-swaps, **resets per-account stats** (fresh weekly P&L), and re-resolves
  symbols. See `accounts-and-brokers.md`.

## Live-edit rules (won't get bitten)
- The form holds a local buffer; polling doesn't clobber unsaved edits.
- **Save & Apply** writes via the `update_bot_config` merge RPC (a plain PATCH would replace
  the whole config — never do that).
- Edits reach the running bot within ~5s. No restart for any Config-page change.
