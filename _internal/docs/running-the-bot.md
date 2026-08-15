# Running the Bot — Start, Stop, Deploy, Lifecycle

Production runs on the **Windows VPS** (`<vps-user>@<vps-host>`) because the `MetaTrader5`
package is Windows-only. This doc covers everyday operation. For debugging commands, see
`vps-troubleshooting.md`.

## Normal state (you usually do nothing)
- **Scheduled Task `HolyGrail`** runs `venv\Scripts\pythonw.exe -u -m soldier.loop --interval 300`.
  `pythonw` = no console window (nothing to accidentally close). It restarts on failure.
- **Task `StartMT5`** launches the MT5 terminal at boot if it isn't running.
- Both tasks are AtStartup, so a VPS reboot self-recovers (~1 min; the bot retries the
  terminal bind until the terminal is ready).

## The two loops running inside the bot
1. **Trade cycle** (~every 5 min / `--interval 300`): resolve matured positions → kill-check →
   scan all active symbols → rank → open the best within the position limit. See
   `trade-lifecycle.md`.
2. **Telemetry** (every ~5s, concurrent): hot-reload config, check for an account switch,
   bank the weekly goal if reached, manage exits (profit/breakeven trails), publish live
   account state to Supabase.

Because config is re-read every 5s, **most changes need no restart** — only code (`.py`) and
`.env` changes do.

## Start / stop / restart

> ⚠️ The #1 operational gotcha: `schtasks /run` is a **silent no-op if the task is already
> running**. After any code deploy you must **kill → confirm empty → run**, or the old code
> stays in memory.

```bash
# STOP (kills the bot; open positions stay at the broker under their SL)
ssh <vps-user>@<vps-host> 'taskkill /F /IM pythonw.exe'

# START
ssh <vps-user>@<vps-host> 'schtasks /run /tn HolyGrail'

# CLEAN RESTART (the safe 3-step — use this after deploys)
ssh <vps-user>@<vps-host> 'taskkill /F /IM pythonw.exe'
ssh <vps-user>@<vps-host> 'tasklist /fi "imagename eq pythonw.exe"'   # MUST show "No tasks"
ssh <vps-user>@<vps-host> 'schtasks /run /tn HolyGrail'
```

After start, wait ~40s (Kronos imports) and confirm the boot line in the log:
```
Holy Grail | LIVE | symbols=[…] tf=5m goal=$14.0 ceiling=$64.0
```

## Soft controls (no process restart — from the dashboard)
- **Start / Pause / Stop** buttons on Config → write `bot_running` / `trading_paused` to
  `bot_config` → bot reads within 5s.
  - *Stop* = no new trades, existing positions keep resolving under their SL/horizon.
  - *Pause* = stay connected, no new trades.
- Note: these only affect a **running** bot. If the process is dead, the dashboard button
  can't relaunch it — use the scheduled task (above). The dashboard's red **"BOT OFFLINE"**
  badge tells you when the heartbeat is stale (>30s = process dead/stuck).

## Deploying code changes (from the Linux dev box)
```bash
# 1. syntax-check locally (MT5 won't import on Linux, but this catches syntax errors)
python3 -m py_compile soldier/loop.py providers/mt5.py && echo OK

# 2. push the changed files
scp soldier/loop.py <vps-user>@<vps-host>:"C:/path/to/holy-grail/soldier/loop.py"
#   (repeat per file; preserve the subdirectory path)

# 3. clean restart (the 3-step above)

# 4. verify the new code loaded
ssh <vps-user>@<vps-host> 'powershell -NoProfile -Command "Select-String -Path C:\path\to\holy-grail\soldier\loop.py -Pattern \"SOME_NEW_FUNCTION\" -Quiet"'
```
The **frontend** is separate — it deploys on Vercel (you redeploy there), not to the VPS.

## What to expect in the log
Every cycle logs a `[CYCLE]` summary: `scanned=N tradeable=N opened=N open_total=N holds=N`.
- `scanned=0` → no symbols resolved (broker offers none of your active list; see
  `accounts-and-brokers.md`).
- Lots of `[SKIP] … risk $X > cap $Y` → min-lot vs cap mismatch (the usual "no trades" cause).
- `[OPEN]` / `[CLOSE]` / `[TRAIL]` / `[GOAL]` / `[KILL]` — self-explanatory events.

## When the bot dies on its own (and how to know)
- The bot logs to `data/bot.log` (stdout) and `data/bot.err` (tracebacks). Under `pythonw`
  these files are opened by the bot itself in utf-8 — logging can't crash it (a hard-won fix;
  the 2026-08-10 overnight death was a unicode error in the logger).
- If it crashes, the scheduled task restarts it. If the task shows `Ready` and there are zero
  `pythonw` processes, it died and didn't relaunch — do the clean restart.
- Always check `data/bot.err` after a surprise death — the traceback is there.

## Quick health check (one command)
```bash
ssh <vps-user>@<vps-host> 'tasklist /fi "imagename eq pythonw.exe" /fo csv /nh && powershell -NoProfile -Command "Get-Content C:\path\to\holy-grail\data\bot.log -Tail 5 -Encoding UTF8"'
```
Expect: 2 pythonw lines + recent `[CYCLE]` lines with a current timestamp.
