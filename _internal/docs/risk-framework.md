# The Risk Framework (Sentinel) — Explained

Sentinel (`sentinel/risk.py`) is the goal-driven risk brain. This doc explains every rule,
every number, and every knob — in plain language — so you can tune it without guessing.

## The philosophy

The bot is built around a **thin edge** (Kronos is only ~55% right on direction). You can't
win by risking big on any single trade — one loss would erase many wins. So the framework is
**goal-driven, not growth-driven**: hit a modest weekly profit target, bank it, rest. Capital
survival beats capital growth. Every rule below serves either "bank the goal" or "don't blow
the account getting there."

## The core loop (what Sentinel tracks)
- `weekly_pnl` — realized profit this week (resets Monday).
- `daily_pnl` — realized profit today (resets at UTC midnight).
- `consecutive_losses` — losing streak (resets on a win).
- `weekly_goal_locked` — a latch: once the goal is banked, stay stopped until next week.

## The five protections (kill switches)

`check_kill(equity, open_positions, symbols, floating_pnl)` returns `(stop?, reason, close_all?)`.
If `stop=True`, no new trades. If `close_all=True` too, the bot **closes every open position
right now**.

| Switch | Triggers when | close_all? | What it means |
|---|---|---|---|
| **weekly goal** | `weekly_pnl + floating ≥ weekly_goal` (or latched) | ✅ | In-flight profit counts. Bank everything, rest for the week. |
| **equity ceiling** | live `equity ≥ baseline + weekly_goal` | ✅ | Same idea in dollars — reached the target account size. |
| **equity floor** | `equity ≤ baseline − max_weekly_drawdown` | ✅ | Stop the bleed. |
| **daily loss cap** | `daily_pnl ≤ −max_daily_loss` | ✅ | Bad day — close out, cool off. |
| **consecutive losses** | 5 losses in a row | ✅ | Model may be broken — stop. |
| **max positions** | already at `max_open_positions` | ❌ | Just don't open more (keep existing). |
| **news blackout** | high-impact news window | ❌ | Don't trade into volatility spikes. |
| **bot stopped / paused** | dashboard toggle | ❌ | Manual control. |

> Note: the goal/ceiling checks use **live equity** (which includes floating profit), so a
> +$14 trade that's still open *counts toward the goal* and gets banked. This is the direct
> fix for the overnight incident where a +$14 winner was held to horizon and became −$7.

## Lot sizing — and why it's "min-lot-bound"

This is the single most important thing to understand about real trading on retail MT5.

```
intended:   risk $X per trade  →  solve for the lot that loses $X if SL hits
            lot = risk / (|entry − SL| × contract_size)
reality:    the broker floors lot to its minimum (0.01 on MetaQuotes, 0.10 on Headway)
            → so the ACTUAL $-at-SL is whatever min-lot dictates, often >> $X
```

So `max_risk_per_trade` is a **reference**, not the real risk. The real per-trade risk is
`lot × |entry−SL| × contract_size`, and the **risk cap** is the only thing keeping it sane:

> **`risk_cap_pct`** — skip any trade whose actual $-at-SL exceeds `risk_cap_pct × equity`.
> (e.g. 0.08 × $500 = $40.) This is the guard against the overnight blowup where a "$1 risk"
> trade actually risked ~$100.

If you see `[SKIP] risk $X > cap $Y (lot Z floored to min)` in the log: the broker's min-lot
made the trade too big for the account. **Raising the cap is rarely the right answer** — if
`Z` is `0.1` (not `0.01`), the broker is a 0.1-min-lot broker and you need a bigger account
or a different broker, not a higher cap. See `accounts-and-brokers.md`.

## The exits (how a trade closes)

A position can close five ways — see `trade-lifecycle.md` for the full flow:
1. **Horizon** — held to `pred_len` (24 × 5m = 2h), then closed (the max hold).
2. **Hard SL** — the broker's stop-loss (2× predicted move) gets hit.
3. **Profit-lock** — once floating profit ≥ `profit_lock_target`, the SL ratchets up to lock
   profit (`max(profit_lock_min, peak × profit_lock_fraction)`). A winner can't become a loss.
4. **Breakeven-lock** — before the profit target, once price moved ≥ `breakeven_lock_mult ×
   |move|` in favor, slide SL to ~entry (downside protection only).
5. **Goal/ceiling/daily-floor close-all** — a kill switch with `close_all=True` liquidates
   everything.

Plus: if a position closes *outside* the bot (SL between ticks, manual close, crash), the
**close-reconciler** picks it up from the MT5 deal history and logs it — so trades never get
stuck at "open" in the dashboard.

## Thursday aggression
If `thursday_aggression` is on, it's Thursday, you're behind target (`weekly_pnl < thursday_threshold`),
and the signal is A-grade (`confidence ≥ min_confidence_for_boost`), risk is bumped from
`max_risk_per_trade` to `thursday_risk` — a last-day push to hit the weekly goal.

## Anti-compounding
Risk is based on the **baseline**, not current equity. Profit is "withdrawn" weekly
(`weekly_pnl` resets Monday; `weekly_withdrawn` accumulates). The account doesn't snowball —
each week starts fresh from the baseline. This is deliberate: a thin edge amplified by
compounding is a thin edge amplified toward ruin.

## Calibration shortcut (`auto_calibrate`)
On the dashboard, "Auto-Calibrate" derives risk params from your typed balance + goal:
- risk/trade = 2% of balance
- daily loss cap = 6% of balance
- weekly drawdown = 20% of balance → floor = balance − 20%
- max positions = `min(5, max(1, goal / (risk×2)))`

> ⚠️ Auto-calibrate is tuned for a **personal** account. Its 6%-daily / 20%-drawdown defaults
> **violate prop-firm rules**. For a prop account, set daily loss + drawdown **manually** to
> the firm's actual limits (typical: 5% daily, 10% total), and set the bot's floor *above*
> the firm's kill level so the bot stops first. See `configuration.md`.

## Tuning cheat sheet
| Symptom | Knob | Direction |
|---|---|---|
| No trades fire (all "risk > cap") | check broker min-lot first; if 0.01, nudge `risk_cap_pct` up | ↑ cap |
| Too many tiny stopped-out trades | `sl_multiplier` (wider stop) or `snr_min` (filter noise) | ↑ |
| Winners cut too early | `profit_lock_target` / `profit_lock_fraction` | ↑ |
| Want more aggressive last-day push | `thursday_risk` | ↑ |
| Bot stops too early on losses | `max_daily_loss` | ↑ (carefully) |
