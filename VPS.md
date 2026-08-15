# VPS deployment notes

> Credentials are NOT stored in this file (it is tracked by git).
> Keep real credentials in the VPS-local files listed below only.

## Where credentials live on the VPS
- MT5 accounts: `C:\holy-grail-win\data\mt5_accounts.json` (never commit)
- Bot env: `C:\holy-grail-win\.env` (Supabase service-role key, Telegram token, HF token — never commit)
- Windows account: your VPS provider's panel / your password manager
- Supabase DB password: Supabase dashboard → Settings → Database

## Runtime layout (Windows)
- Repo: `C:\holy-grail-win`, venv: `C:\holy-grail-venv` (Windows Python 3.12 + MetaTrader5)
- Scheduled Task `HolyGrail` runs the bot; `HolyGrailWatch` is the 5-minute watchdog
  (stop it with `schtasks /end /tn HolyGrailWatch` before manual restarts)
- MT5 terminal must be running and logged in; AutoTrading enabled (else retcode 10027)

See `_internal/docs/vps-troubleshooting.md` for the full runbook.
