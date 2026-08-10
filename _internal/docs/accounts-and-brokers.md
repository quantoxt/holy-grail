# MT5 Accounts & Broker Quirks

The bot trades through **one MT5 broker at a time**, but you can have several accounts and
switch between them live. This doc covers switching, and the two broker quirks that cause
90% of "the bot won't trade" confusion.

## Source of truth: Supabase `mt5_accounts`
- The active account is whichever row has `is_active = true`. That's it — `data/mt5_accounts.json`
  on the VPS is **dead**, do not use it.
- **Switch:** Dashboard → Config → MT5 Accounts → Activate. Or via Supabase directly
  (`vps-troubleshooting.md` §10).
- On switch, the bot: hot-swaps the terminal connection, **clears per-account stats**
  (weekly/daily P&L reset → fresh start), drops the old account's in-memory positions, and
  re-resolves symbols for the new broker. Trades history is scoped per-login, so the new
  account's dashboard starts at zero.

> Cross-**broker** hot-swaps (e.g. Headway ↔ MetaQuotes) in one session can be flaky — the
> terminal sometimes needs a moment. If symbols don't resolve after switching, re-check the
> terminal is logged into the target account and do a clean restart.

## Quirk 1 — Minimum lot size (the big one)
Brokers set a **minimum trade size**. This single number determines whether the account can
trade at all:

| Broker type | min lot | Smallest EURUSD risk | Viable account size |
|---|---|---|---|
| 0.01 (MetaQuotes-Demo, most retail) | 0.01 | ~$6.5 (1.3% of $500) | $500+ |
| 0.10 (Headway/Jarocel) | 0.10 | ~$65 (13% of $500) | $5000+ |

**Why it matters:** the bot's per-trade risk = `lot × |entry−SL| × contract_size`. The lot
can't go below the broker's min. So on a 0.10-min broker, *every* trade risks ≥10× what a
0.01 broker would — and on a small account that's instantly over the risk cap, so **nothing
trades**.

**Check your broker's min-lot** (`vps-troubleshooting.md` §6b). If it's 0.10:
- On $500: don't trade this broker. Switch to a 0.01-min account, or fund to ~$5000+.
- Raising the risk cap to force trades = the blowup zone. Don't.

The `[SKIP] … lot 0.1 floored to min` log line is the signature of a 0.10-min broker.

## Quirk 2 — Symbol naming
Brokers rename the same instrument. Examples seen:
- **MetaQuotes-Demo:** `EURUSD`, `XAUUSD` (plain).
- **Headway (Jarocel):** `EURUSD.`, `XAGUSD.` (trailing dot). Others use `.r`, `.raw`, `_`.

The bot has a **symbol resolver**: for each friendly name in `active_symbols`, it tries an
exact match, then a prefix match against the broker's full symbol list. So `EURUSD` resolves
to `EURUSD.` on Headway automatically — you shouldn't have to do anything.

If a symbol you expect is skipped as "not offered":
1. Check what the broker actually calls it (`vps-troubleshooting.md` §6a).
2. If the name is totally different (e.g. `GOLD` not `XAUUSD…`), it may need adding to
   `shared/symbols.py` `PREFERRED_SYMBOLS`, or the resolver's prefix logic can't reach it.

## Per-account stats (the reset behavior)
- Trades are tagged `mt5_login`. The dashboard shows only the **active** account's trades +
  stats. Switch to a new account → clean slate (zero P&L). Switch back → that account's
  history is still there.
- The bot's *in-memory* weekly P&L also resets on switch (so kill-switch logic matches the
  account you're actually on).

## Quick decision guide
| Situation | Do |
|---|---|
| Bot on a 0.01-min broker, $500, no trades | Check `[SKIP]` reason — likely risk cap. Nudge `risk_cap_pct` up a little, or accept metals are too big. |
| Bot on a 0.10-min broker (Headway), no trades | Switch to a 0.01-min account. The cap can't help here. |
| Symbols all "not offered" | Run §6a probe; confirm broker's names; add to PREFERRED if totally renamed. |
| Switched account, dashboard still shows old data | Wait ~10s (poll); if stale, the switch was flaky — restart the task. |
| Want a fresh start mid-week | Toggle to another account and back, or restart the bot (in-memory P&L resets). |
