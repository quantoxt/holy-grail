# VPS Troubleshooting Command Reference

Every command below is run **from the Linux dev box** (`~/Documents/PROJECTS/BOTS/holy-grail`)
and targets either the **Windows VPS** (the bot) or **Supabase cloud** (the DB the bot +
dashboard share). All have been verified working in this session.

---

## 0. The players (memorize these)

| Thing | Value |
|---|---|
| VPS host | `aurora@192.168.0.179` |
| Project on VPS | `C:\Users\Aurora\Documents\PROJECTS\holy-grail` |
| VPS Python (venv) | `C:\Users\Aurora\Documents\PROJECTS\holy-grail\venv\Scripts\python.exe` |
| Bot log | `…\holy-grail\data\bot.log` (stdout mirror) |
| Bot error log | `…\holy-grail\data\bot.err` (tracebacks) |
| JSONL audit | `…\holy-grail\data\paper_log.jsonl` (every decision, raw) |
| Scheduled task | `HolyGrail` (runs `pythonw -u -m soldier.loop --interval 300`) |
| MT5 terminal | `C:\Program Files\MetaTrader 5\terminal64.exe` (auto-start task `StartMT5`) |
| Supabase URL | `https://gpfudbncpmaabnszmztt.supabase.co` |
| Supabase anon key | public — see `SBKEY` below (RLS-open by design) |

```bash
# set these once per shell session:
VPS=aurora@192.168.0.179
PROJ='C:\Users\Aurora\Documents\PROJECTS\holy-grail'
SBKEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwZnVkYm5jcG1hYWJuc3ptenR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYyNjM1MTYsImV4cCI6MjEwMTgzOTUxNn0.rngWUQdtfw-xQ5DXWDhBk0AIHuTWtfKs4Y_QKe4Rinc'
SB=https://gpfudbncpmaabnszmztt.supabase.co
```

> **Quoting rules over SSH→Windows:** simple status commands use `ssh $VPS 'cmd'`.
> Anything with spaces/paths uses `ssh $VPS 'powershell -NoProfile -Command "…"'`
> (double-quotes inside). **Never use `timeout /t` over ssh** — it errors ("Input
> redirection is not supported"); use `Start-Sleep` in PowerShell instead.

---

## 1. Quick diagnosis flow ("the bot isn't trading")

Run these in order — each answers one question:

1. **Is the bot process alive?** → §2
2. **Is the heartbeat fresh?** (bot reaching Supabase) → §5
3. **What does the log say it's doing?** (SKIP / KILL / ERROR) → §3
4. **Are the symbols valid for this broker?** → §6
5. **Did a trade fail / get rejected?** → §7
6. **Is the risk cap blocking everything?** (min-lot vs cap) → §6 + §8

---

## 2. Is the bot alive? (process + task)

```bash
# pythonw processes — expect exactly 2: the venv stub (~5 MB) + the real bot (300+ MB).
# 0 lines = bot is DEAD.
ssh $VPS 'tasklist /fi "imagename eq pythonw.exe" /fo csv /nh'

# Scheduled-task status: "Running" = alive, "Ready" = died and waiting for next boot trigger.
ssh $VPS 'schtasks /query /tn HolyGrail /fo list' | grep -i 'status\|last'

# Is the MT5 terminal itself running? (bot can't work without it)
ssh $VPS 'tasklist /fi "imagename eq terminal64.exe" /fo csv /nh'
```

**Interpretation:** task `Ready` + 0 pythonw = the bot crashed and the AtStartup task
won't relaunch until reboot. Fix = clean restart (§4).

---

## 3. Logs — what is the bot actually doing?

```bash
# last 30 stdout lines (cycles, SKIPs, OPENs, CLOSEs, KILLs)
ssh $VPS "powershell -NoProfile -Command \"Get-Content '$PROJ\data\bot.log' -Tail 30 -Encoding UTF8\""

# last 20 ERROR/traceback lines (CRASHES live here)
ssh $VPS "powershell -NoProfile -Command \"Get-Content '$PROJ\data\bot.err' -Tail 20 -Encoding UTF8\""

# search the log for a specific event type (OPEN / CLOSE / SKIP / KILL / TRAIL / RECONCILE / ERROR / DRIFT)
ssh $VPS "powershell -NoProfile -Command \"Select-String -Path '$PROJ\data\bot.log' -Pattern 'OPEN|CLOSE' | Select-Object -Last 15 | ForEach-Object { \$_.Line }\""

# was there a crash? (any Traceback in bot.err)
ssh $VPS "powershell -NoProfile -Command \"Select-String -Path '$PROJ\data\bot.err' -Pattern 'Traceback|Error' | Select-Object -Last 10 | ForEach-Object { \$_.Line }\""
```

**Key line types in bot.log:**
- `[CYCLE] scanned=N tradeable=N opened=N` — a full scan. `scanned=0` = no symbols resolved (§6).
- `[SKIP] symbol=X reason=…` — symbol skipped. Reasons: `not offered by broker`, `spread …`, `low_snr …`, `risk $… > cap $…`.
- `[KILL] reason=…` — kill switch fired. Reasons: `max_positions`, `equity_floor`, `equity_ceiling`, `weekly_goal_hit`, `daily_loss_cap`, `bot_stopped`.
- `[OPEN]` / `[CLOSE]` / `[TRAIL]` / `[RECONCILE]` / `[ERROR]` / `[GOAL]` — self-explanatory.
- `[SKIP] … risk $X > NN% cap $Y (lot Z floored to min)` — the risk cap is blocking; X is the real $-at-SL at min-lot. If Z is `0.1` not `0.01`, the broker's min-lot is 0.1 (§6).

---

## 4. Restart the bot (the SAFE 3-step)

> ⚠️ `schtasks /run` is a **no-op if a task is already running** ("currently running").
> You MUST kill first and confirm zero processes, THEN run — otherwise the old code
> stays in memory and your deploy does nothing.

```bash
# 1. kill all pythonw (shows PIDs it killed)
ssh $VPS 'taskkill /F /IM pythonw.exe'

# 2. confirm ZERO are left
ssh $VPS 'tasklist /fi "imagename eq pythonw.exe"'
#   → must print "INFO: No tasks are running which match the specified criteria."

# 3. start fresh
ssh $VPS 'schtasks /run /tn HolyGrail'
```

Then wait ~40 s (Kronos import) and check the log (§3) for the boot line
`Holy Grail | LIVE | symbols=[…] …`.

**Auto-start the MT5 terminal** (if `terminal64.exe` isn't running):
```bash
ssh $VPS 'schtasks /run /tn StartMT5'
```

---

## 5. Heartbeat & account state (Supabase)

```bash
# latest account heartbeat the bot published (balance/equity/floating/login/updated_at)
curl -s "$SB/rest/v1/account_state?order=updated_at.desc&limit=1" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool

# heartbeat age only — if updated_at is > ~30s stale, the bot is DEAD/stuck
curl -s "$SB/rest/v1/account_state?select=login,broker,balance,updated_at&order=updated_at.desc&limit=1" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool

# all known accounts (to find a login to switch to)
curl -s "$SB/rest/v1/account_state?select=login,broker,balance&order=updated_at.desc" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool
```

**Interpretation:** if `updated_at` is minutes old, the bot process is dead (§2/§4) or
can't reach Supabase (internet). The dashboard's red "BOT OFFLINE" badge uses the same
>30 s rule.

---

## 6. Are the symbols valid for THIS broker? (the #1 cause of "bot won't trade")

Two read-only probes. They run a throwaway Python on the VPS that binds to the running
terminal, reads, and exits **without `mt5.shutdown()`** (so the bot's connection is untouched).

### 6a. What does the broker actually OFFER? (symbol-name discovery)

Brokers rename instruments (Headway uses a trailing dot: `EURUSD.`, `XAGUSD.`). The bot's
resolver prefix-matches, but if it's skipping everything as "not offered", check the raw list:

```bash
cat > /tmp/symprobe.py <<'EOF'
import re, MetaTrader5 as mt5
mt5.initialize()
alln = [s.name for s in (mt5.symbols_get() or [])]
print("TOTAL symbols on broker:", len(alln))
pat = re.compile(r'XAU|XAG|GOLD|SILVER|EUR|GBP|USD|JPY|BTC|ETH', re.I)
print("MATCHES:", sorted({n for n in alln if pat.search(n)}))
EOF
scp /tmp/symprobe.py $VPS:"$PROJ\\symprobe.py"
ssh $VPS "$PROJ\\venv\\Scripts\\python.exe $PROJ\\symprobe.py"
ssh $VPS 'del C:\Users\Aurora\Documents\PROJECTS\holy-grail\symprobe.py'   # cleanup
```

### 6b. What are the contract specs? (min-lot / contract size — the #2 cause)

If `[SKIP] … lot 0.1 floored to min`, the broker's **min-lot is 0.1** (e.g. Headway), which
makes every trade 10× riskier. Confirm with:

```bash
cat > /tmp/specprobe.py <<'EOF'
import MetaTrader5 as mt5
mt5.initialize()
for sym in ["EURUSD","GBPUSD","XAGUSD","XAUUSD","USDJPY","AUDUSD","BTCUSD"]:
    info = mt5.symbol_info(sym)
    name = sym
    if info is None:
        pref=[s.name for s in (mt5.symbols_get() or []) if s.name.startswith(sym)]
        if pref: name, info = pref[0], mt5.symbol_info(pref[0])
    if info is None: print(f"{sym}: NOT FOUND"); continue
    print(f"{sym} -> {name} | vol_min={info.volume_min} step={info.volume_step} "
          f"contract={info.trade_contract_size} point={info.point}")
EOF
scp /tmp/specprobe.py $VPS:"$PROJ\\specprobe.py"
ssh $VPS "$PROJ\\venv\\Scripts\\python.exe $PROJ\\specprobe.py"
ssh $VPS 'del C:\Users\Aurora\Documents\PROJECTS\holy-grail\specprobe.py'
```

**Read it like this:** `actual_risk at min-lot = vol_min × |entry−SL| × contract`. For a typical
0.3% Kronos move, SL ≈ 0.6%: EURUSD 0.01 lot ≈ **$6.5**; EURUSD **0.1** lot ≈ **$65**. The
bot's risk cap (`risk_cap_pct × equity`) must exceed that or the symbol is skipped. If the
broker is 0.1-min and the account is small, **no cap setting saves you — switch brokers or
fund bigger** (see §8).

### 6c. Which symbols did the bot resolve as offered? (its own published view)

```bash
LOGIN=5599311   # the active account's login
curl -s "$SB/rest/v1/account_state?login=eq.$LOGIN&select=symbols" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool
```
Empty `[]` = broker offers none of the curated `PREFERRED_SYMBOLS` under any name → the
resolver found nothing (check 6a for the broker's real names; may need to add them to
`shared/symbols.py`).

---

## 7. Did a trade fail / get rejected?

```bash
# last order rejections / open failures in the log
ssh $VPS "powershell -NoProfile -Command \"Select-String -Path '$PROJ\data\bot.log' -Pattern 'order rejected|open failed|ERROR' | Select-Object -Last 10 | ForEach-Object { \$_.Line }\""

# MT5 retcode meanings (when a log line shows retcode=NNNNN):
#   10004 = requote          10013 = invalid trade (AutoTrading OFF / fills disabled)
#   10018 = market closed    10021 = no prices / invalid fill
#   10027 = AutoTrading disabled in terminal (enable the Algo Trading button!)
#   10030 = unsupported filling mode
```

If `retcode 10027` → the terminal's **AutoTrading** button is off (no code can fix that;
click it in the MT5 terminal). `10018` → market closed (weekends / after-hours for the symbol).

**Risk-cap skips** (the most common "no trades" cause):
```bash
ssh $VPS "powershell -NoProfile -Command \"Select-String -Path '$PROJ\data\bot.log' -Pattern 'risk_cap_skip|risk \\\$' | Select-Object -Last 10 | ForEach-Object { \$_.Line }\""
```

---

## 8. Config — read it & change it live (Supabase, no restart)

The bot re-reads `bot_config` every ~5 s, so config edits take effect with **no restart**.

### 8a. Read the current config
```bash
curl -s "$SB/rest/v1/bot_config?select=config&id=eq.1" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" \
  | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin)[0]['config'],indent=2))"
```

### 8b. Patch any field(s) — via the merge RPC (NEVER a plain PATCH, it replaces the whole jsonb)
```bash
curl -s -X POST "$SB/rest/v1/rpc/update_bot_config" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" \
  -H "Content-Type: application/json" \
  -d '{"patch": {"risk_cap_pct": 0.08, "max_daily_loss": 50}}' | python3 -m json.tool
```

**Common knobs:**
| Field | What | Example |
|---|---|---|
| `risk_cap_pct` | per-trade $-at-SL ceiling = this × equity | `0.03` (3%) → `$15` on $500 |
| `max_risk_per_trade` | reference $ risk (Thursday boost / daily budget) | `10` |
| `max_daily_loss` | daily realized-loss kill | `50` |
| `weekly_goal` / `baseline_equity` | goal + ceiling = `baseline+goal` | `14` / `500` |
| `max_open_positions` | concurrent trades | `2` |
| `sl_multiplier` | SL = this × \|predicted move\| | `2.0` |
| `profit_lock_target/min/fraction` | profit-trail once floating ≥ target | `5/2/0.5` |
| `active_symbols` | what to scan | `["EURUSD","XAGUSD"]` |
| `bot_running` | start/stop | `true` |

### 8c. The cap-vs-min-lot cheat
If every symbol logs `risk $X > cap $Y`, compare:
- `cap = risk_cap_pct × equity` (e.g. 0.08 × 500 = $40)
- `X` from the log (the min-lot actual risk)

If `X` is ~10× expected, the broker is **0.1-min-lot** (§6b). No cap fixes that on a small
account — either switch to a 0.01-min broker, or fund so that 0.1 lot ≈ your risk budget.

---

## 9. Trades — inspect history & per-account stats

```bash
# all trades
curl -s "$SB/rest/v1/trades?order=id.asc" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool

# trades stuck at "open" (never got a close logged — crash/manual close)
curl -s "$SB/rest/v1/trades?result=eq.open&select=id,symbol,mt5_login,entry_time" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool

# one account's trades only (stats are scoped by mt5_login)
LOGIN=5599311
curl -s "$SB/rest/v1/trades?mt5_login=eq.$LOGIN&order=id.desc" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool
```

### 9a. Backfill a stuck/missing close (when a trade closed externally and never logged)
```bash
# PATCH the row directly (id = the trade id). Compute exit from pnl if needed.
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH "$SB/rest/v1/trades?id=eq.2" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" \
  -H "Content-Type: application/json" -H "Prefer: return=minimal" \
  -d '{"size":0.01,"exit_price":4318.46,"pnl":18.46,"result":"win","exit_time":"2026-08-10T07:00:00+00:00"}'
```

### 9b. Risk events (kill switches, drift, cap-skips, goal-banked)
```bash
curl -s "$SB/rest/v1/risk_events?order=created_at.desc&limit=20" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool
```

---

## 10. Switch the active MT5 account (Supabase = source of truth)

The bot hot-swaps to whichever row in `mt5_accounts` has `is_active=true`.
```bash
# list accounts
curl -s "$SB/rest/v1/mt5_accounts?select=id,name,login,server,is_active&order=created_at.desc" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool

# activate id=NN (deactivate all others first)
ID=7
curl -s -o /dev/null -X PATCH "$SB/rest/v1/mt5_accounts?neq&id=neq.$ID" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" -H "Prefer: return=minimal" \
  -d '{"is_active":false}'   # (refine the filter as needed)
curl -s -o /dev/null -X PATCH "$SB/rest/v1/mt5_accounts?id=eq.$ID" \
  -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" -H "Prefer: return=minimal" \
  -d '{"is_active":true}'
```
On switch, the bot **resets per-account stats** (fresh weekly P&L) and re-resolves symbols.
Caveat: cross-**broker** hot-swaps (e.g. Headway↔MetaQuotes) in one session can be flaky —
if symbols don't resolve after switching, re-check the terminal is logged into the target
account and restart the task (§4).

---

## 11. Deploy code changes to the VPS

```bash
# push one file (Python). SCP preserves the dir structure under $PROJ.
scp shared/runtime_config.py $VPS:"$PROJ\\shared\\runtime_config.py"
scp soldier/loop.py          $VPS:"$PROJ\\soldier\\loop.py"

# push several at once
for f in shared/runtime_config.py sentinel/risk.py providers/mt5.py soldier/loop.py shared/database.py; do
  scp "$f" $VPS:"$PROJ\\$f" && echo "pushed $f"
done

# verify a marker landed on disk
ssh $VPS "powershell -NoProfile -Command \"Select-String -Path '$PROJ\soldier\loop.py' -Pattern '_reconcile_positions' -Quiet\""
```
After pushing Python: **always restart** (§4) — the running process holds the old code in memory.
Frontend changes are deployed separately (Vercel), not to the VPS.

Before deploying, syntax-check locally (MT5 won't import on Linux, but `py_compile` catches syntax):
```bash
python3 -m py_compile soldier/loop.py providers/mt5.py && echo OK
```

---

## 12. Run an arbitrary one-off on the VPS (the escape hatch)

For anything not covered, write a small `.py`, scp it, run with the venv python, clean up:
```bash
cat > /tmp/x.py <<'EOF'
import MetaTrader5 as mt5
mt5.initialize()
print(mt5.account_info().balance)
# do NOT call mt5.shutdown() — leaves the bot's terminal connection intact
EOF
scp /tmp/x.py $VPS:"$PROJ\\x.py"
ssh $VPS "$PROJ\\venv\\Scripts\\python.exe $PROJ\\x.py"
ssh $VPS "del $PROJ\\x.py"
```
Rules: read-only is safe; **never `mt5.shutdown()`** in a probe (it can drop the bot's IPC
connection); wrap risky calls in try/except so the probe can't wedge anything.

---

## 13. Cheat sheet (copy-paste most-used)

```bash
VPS=aurora@192.168.0.179
PROJ='C:\Users\Aurora\Documents\PROJECTS\holy-grail'
SBKEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwZnVkYm5jcG1hYWJuc3ptenR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYyNjM1MTYsImV4cCI6MjEwMTgzOTUxNn0.rngWUQdtfw-xQ5DXWDhBk0AIHuTWtfKs4Y_QKe4Rinc'
SB=https://gpfudbncpmaabnszmztt.supabase.co

# alive?
ssh $VPS 'tasklist /fi "imagename eq pythonw.exe" /fo csv /nh'
# log tail
ssh $VPS "powershell -NoProfile -Command \"Get-Content '$PROJ\data\bot.log' -Tail 20 -Encoding UTF8\""
# crash?
ssh $VPS "powershell -NoProfile -Command \"Get-Content '$PROJ\data\bot.err' -Tail 10 -Encoding UTF8\""
# heartbeat fresh?
curl -s "$SB/rest/v1/account_state?select=login,balance,updated_at&order=updated_at.desc&limit=1" -H "apikey: $SBKEY" -H "Authorization: Bearer $SBKEY" | python3 -m json.tool
# clean restart (3-step!)
ssh $VPS 'taskkill /F /IM pythonw.exe'; ssh $VPS 'tasklist /fi "imagename eq pythonw.exe"'; ssh $VPS 'schtasks /run /tn HolyGrail'
```

---

### Golden rules
- **Kill → confirm empty → run.** `schtasks /run` is a no-op if the task is already running; skipping the kill means your deploy silently does nothing.
- **The cap isn't the enemy, min-lot is.** `risk $X > cap $Y` with X≈10×expected ⇒ 0.1-min broker ⇒ switch brokers or fund bigger, don't just raise the cap.
- **Never commit/push** without being asked; the service_role key stays off the VPS and out of Vercel.
- **Probes are read-only and never `mt5.shutdown()`** — they share the bot's terminal.
