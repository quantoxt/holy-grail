# The Life of a Trade

Exactly what happens from "Kronos sees something" to "position closed." Read this once and
you'll understand every line in the log.

## 1. Signal generation (every cycle, per active symbol)
- `SignalEngine` feeds the last 512 candles to Kronos, gets 24 predicted candles, reads the
  close 24 ahead → `predicted_close`.
- `move = (predicted_close − current) / current`.
- Direction: `BUY` if move ≥ +0.3%, `SELL` if ≤ −0.3%, else `HOLD` (skip).
- SL price = `2 × |move|` away from entry (the safety net).
- Computes SNR (signal/noise) and confidence.

## 2. The gates (a signal must pass ALL of these to trade)
In order, in `loop.py` Phase 5:
1. **Offered?** — the broker must offer the symbol (resolved through its naming). Skip if not.
2. **Watcher drift gate** — if Kronos's recent resolved accuracy is at coin-flip, block *all*
   trading this cycle (global kill).
3. **Correlation filter** — if a correlated pair already opened this cycle, skip the weaker.
4. **Spread filter** — skip if spread > 25% of `|move|` (edge eaten by cost).
5. **SNR gate** — skip if `|move|/noise < 1` (signal lost in chop).
6. **Risk cap** — compute actual $-at-SL at min-lot; **skip if > `risk_cap_pct × equity`**.
   (This is the guard that refuses suicide — and the most common reason a signal doesn't trade.)
7. **Lot/size sanity** — lot ≥ broker min, risk > 0.

## 3. Open
- Send a market order (magically tagged `magic=234000`) with the SL attached.
- Record the position in `self.open` (direction, entry, lot, ticket, SL, predicted move,
  actual risk, peak-profit tracker).
- Log the trade open to the `trades` table (tagged with the current `mt5_login`).
- Telegram alert.

## 4. While open — managed every ~5s by telemetry
Two SL-management tiers (ratchet-only; never widens):
- **Breakeven-lock:** before profit target, once price moved ≥ `1× |move|` in favor, slide SL
  to ~entry. Pure downside protection.
- **Profit-lock:** once floating profit ≥ `profit_lock_target` ($5 default), ratchet SL to
  lock `max(profit_lock_min, peak_profit × profit_lock_fraction)`. A winner cannot become a loss.
- **Goal/ceiling bank:** if live equity ≥ `baseline + weekly_goal` (or realized+floating ≥
  goal), **close ALL positions** and latch stopped-for-the-week.

## 5. Exit — the five ways a position closes
| Exit | Trigger | Who |
|---|---|---|
| **Horizon** | `pred_len` cycles elapsed (2h) | loop `_resolve_positions` |
| **Hard SL** | broker stop-loss hit (2× move, or a trailed level) | broker |
| **Profit-lock** | trailed SL hit after locking profit | broker (SL set by bot) |
| **Close-all** | goal/ceiling/daily-loss/equity-floor kill switch | loop `_close_all` |
| **External** | SL between ticks, manual close, crash mid-close | detected + logged by close-reconciler from deal history |

Every close: accounts P&L into `weekly_pnl`/`daily_pnl`, records win/loss for the Watcher's
accuracy tracking, logs to the `trades` table, and sends a Telegram alert with P&L + balance.

## 6. Crash resilience (a restart never orphans a trade)
- On startup, `_reconcile_positions()` rebuilds `self.open` from the broker's **real** open
  positions (filtered to magic 234000). Entry/SL/lot/age are recovered, so the horizon exit
  and trails still work after a restart.
- The close-reconciler catches anything that closed while the bot was down — logged from MT5
  deal history, never stuck at "open."

## Reading it in the log
```
[OPEN]   symbol=XAUUSD dir=SELL lot=0.01 risk=$1.00 actual_risk=$7.50 conf=0.83 entry=2310.5
[TRAIL]  symbol=XAUUSD SL → 2310.2 (floating $6.10, peak $9.40)        ← profit-lock ratcheted
[CLOSE]  symbol=XAUUSD dir=SELL reason=horizon entry=2310.5 exit=2302.1 pnl=+$8.40 result=WIN ✅
```
- `actual_risk` is the **real** $-at-SL (not `risk`). That's the number that must fit the cap.
- `reason=` on CLOSE tells you which of the five exits fired.
