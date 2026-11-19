#!/usr/bin/env python3
"""Heartbeat watchdog — run from HOST cron every minute (stdlib only, no venv):

    * * * * * /usr/bin/python3 /opt/holy-grail/deploy/watchdog.py >> /var/log/holygrail-watchdog.log 2>&1

The bot's telemetry task upserts `account_state.updated_at` every ~5s (independent
of bot_running). If the newest row is older than STALE_S (default 600s):
  1. Telegram alert,
  2. `docker compose restart bot` — at most once per COOLDOWN_S (default 600s) so a
     dead MT5 login can't cause a restart storm,
  3. one "recovered" message when the heartbeat comes back.

Reads SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / TELEGRAM_BOT_TOKEN /
TELEGRAM_CHAT_ID from the repo-root .env (the same file the bot uses).
Never prints secrets.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "deploy" / "docker-compose.yml"
STATE = Path(os.environ.get("WATCHDOG_STATE", "/var/tmp/holygrail-watchdog.json"))
# 600s, not 120s: a scan cycle runs Kronos on CPU and blocks the 5s heartbeat for
# ~2-3 min on a 2-vCPU box; 120s restarted the bot mid-cycle (mid-order risk).
STALE_S = int(os.environ.get("WATCHDOG_STALE_S", "600"))
COOLDOWN_S = int(os.environ.get("WATCHDOG_COOLDOWN_S", "600"))


def load_env(path: Path) -> dict:
    env = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


def log(msg: str):
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}", flush=True)


def telegram(env: dict, text: str):
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log("telegram not configured — alert not sent")
        return
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat, "text": text}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001
        log(f"telegram send failed: {type(e).__name__}")


def heartbeat_age(env: dict) -> float | None:
    """Seconds since the newest account_state.updated_at; None if unreadable."""
    url, key = env.get("SUPABASE_URL"), env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        log("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing in .env")
        return None
    q = urllib.parse.urlencode({"select": "updated_at", "order": "updated_at.desc", "limit": "1"})
    req = urllib.request.Request(f"{url.rstrip('/')}/rest/v1/account_state?{q}",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    try:
        rows = json.loads(urllib.request.urlopen(req, timeout=15).read())
    except Exception as e:  # noqa: BLE001
        log(f"supabase read failed: {type(e).__name__}")
        return None
    if not rows or not rows[0].get("updated_at"):
        return float("inf")
    ts = datetime.fromisoformat(rows[0]["updated_at"].replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - ts).total_seconds()


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_state(s: dict):
    try:
        STATE.write_text(json.dumps(s))
    except Exception as e:  # noqa: BLE001
        log(f"state write failed: {e}")


def compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", "-f", str(COMPOSE), *args],
                          capture_output=True, text=True, timeout=180)


def main() -> int:
    env = load_env(ROOT / ".env")
    state = load_state()
    age = heartbeat_age(env)
    now = time.time()

    if age is None:
        # Can't tell (Supabase/network down) — don't restart blindly; alert once/cooldown.
        if now - state.get("last_unknown_alert", 0) > COOLDOWN_S:
            telegram(env, "⚠️ Holy Grail watchdog: cannot read heartbeat from Supabase.")
            state["last_unknown_alert"] = now
            save_state(state)
        return 1

    if age <= STALE_S:
        if state.get("stale"):
            telegram(env, f"✅ Holy Grail heartbeat recovered ({age:.0f}s old).")
            log(f"recovered, age={age:.0f}s")
        save_state({"stale": False, "last_restart": state.get("last_restart", 0)})
        return 0

    age_txt = "never" if age == float("inf") else f"{age / 60:.1f} min"
    if now - state.get("last_restart", 0) < COOLDOWN_S:
        log(f"stale ({age_txt}) — in restart cooldown")
        return 2

    mt5_state = compose("ps", "--format", "{{.Service}}={{.State}}/{{.Health}}", "mt5").stdout.strip()
    res = compose("restart", "bot")
    ok = res.returncode == 0
    log(f"stale ({age_txt}); restart bot -> {'ok' if ok else 'FAILED: ' + res.stderr.strip()[:200]}")
    telegram(env, (
        f"🚨 Holy Grail heartbeat stale ({age_txt}). "
        f"Restarted bot container: {'ok' if ok else 'FAILED'}. "
        f"mt5: {mt5_state or 'unknown'}. If it stays stale, check the MT5 login / "
        f"AutoTrading over the VNC tunnel."))
    save_state({"stale": True, "last_restart": now})
    return 3


if __name__ == "__main__":
    sys.exit(main())
