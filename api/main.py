"""FastAPI backend — serves the dashboard via REST (reads Supabase tables).

Run:  uvicorn api.main:app --port 8000 --reload
The Vue frontend proxies /api to here during dev; in prod, FastAPI serves the
built Vue static files too.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

import os
_url = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
sb = create_client(_url, _key)

app = FastAPI(title="Holy Grail API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/status")
async def status():
    """Bot status — always LIVE, reads from runtime config."""
    return {
        "market_mode": os.environ.get("MARKET_MODE", "forex"),
        "symbols": runtime.active_symbols,
        "model": "NeoQuasar/Kronos-small",
        "mode": "LIVE",
    }


@app.get("/api/signals")
async def signals(limit: int = 50):
    """Recent trading signals."""
    r = sb.table("signals").select("*").order("signal_time", desc=True).limit(limit).execute()
    return r.data


@app.get("/api/trades")
async def trades(limit: int = 50):
    """Recent trades."""
    r = sb.table("trades").select("*").order("created_at", desc=True).limit(limit).execute()
    return r.data


@app.get("/api/performance")
async def performance():
    """Aggregate stats: win rate, net P&L, trade count."""
    r = sb.table("trades").select("pnl,result").execute()
    trades = r.data or []
    closed = [t for t in trades if t.get("result") in ("win", "loss")]
    wins = sum(1 for t in closed if t["result"] == "win")
    total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
    return {
        "total_trades": len(trades),
        "closed": len(closed),
        "wins": wins,
        "win_rate": wins / len(closed) if closed else 0,
        "net_pnl": total_pnl,
    }


@app.get("/api/risk")
async def risk_events(limit: int = 20):
    """Recent risk events (Sentinel)."""
    r = sb.table("risk_events").select("*").order("created_at", desc=True).limit(limit).execute()
    return r.data


@app.get("/api/predictions")
async def predictions(limit: int = 50):
    """Recent Kronos predictions — the audit trail."""
    r = sb.table("kronos_predictions").select("*").order("created_at", desc=True).limit(limit).execute()
    return r.data


# ===== Control panel (dashboard-adjustable) =====

from shared.runtime_config import runtime
from sentinel.risk import sentinel
from pydantic import BaseModel


class ConfigUpdate(BaseModel):
    weekly_goal: float | None = None
    baseline_equity: float | None = None
    max_risk_per_trade: float | None = None
    max_daily_loss: float | None = None
    max_weekly_drawdown: float | None = None
    max_open_positions: int | None = None
    sl_multiplier: float | None = None
    thursday_aggression: bool | None = None
    active_symbols: list | None = None


@app.get("/api/config")
async def get_config():
    """Current runtime config (Sentinel params, symbols, etc.)."""
    return runtime.snapshot()


@app.patch("/api/config")
async def update_config(body: ConfigUpdate):
    """Update trading params live (no restart)."""
    updates = {k: v for k, v in body.dict().items() if v is not None}
    runtime.update(**updates)
    return {"status": "updated", "config": runtime.snapshot()}


@app.get("/api/weekly")
async def weekly_status():
    """Weekly P&L progress toward the goal."""
    return sentinel.weekly_status()


@app.post("/api/control/{action}")
async def control(action: str):
    """Start / stop / pause the bot."""
    if action == "start":
        runtime.bot_running = True
        runtime.trading_paused = False
    elif action == "stop":
        runtime.bot_running = False
    elif action == "pause":
        runtime.trading_paused = True
    elif action == "resume":
        runtime.trading_paused = False
    else:
        return {"error": f"unknown action: {action}"}
    return {"status": action, "bot_running": runtime.bot_running,
            "trading_paused": runtime.trading_paused}


@app.get("/api/news")
async def news():
    """Economic calendar — upcoming high-impact news + blackout status."""
    from shared.news import is_blackout, next_event, get_high_impact
    symbols = runtime.active_symbols
    blocked, reason = is_blackout(symbols, runtime.news_blackout_pre_min,
                                  runtime.news_blackout_post_min)
    upcoming = get_high_impact(symbols)
    return {
        "blackout": blocked,
        "blackout_reason": reason if blocked else None,
        "next": next_event(symbols),
        "upcoming": [{"title": e["title"], "currency": e["currency"],
                       "time": e["time"].isoformat()} for e in upcoming[:5]],
    }


# ===== Auto-calibrate =====

class CalibrateRequest(BaseModel):
    balance: float
    weekly_goal: float


@app.post("/api/calibrate")
async def calibrate(body: CalibrateRequest):
    """Auto-derive all risk params from account balance + weekly goal."""
    config = runtime.auto_calibrate(body.balance, body.weekly_goal)
    return {"status": "calibrated", "config": config}


# ===== MT5 Accounts (Supabase-managed) =====

class AccountCreate(BaseModel):
    name: str
    login: int
    password: str
    server: str
    broker: str = ""


@app.get("/api/accounts")
async def list_accounts():
    r = sb.table("mt5_accounts").select("*").order("created_at", desc=True).execute()
    return r.data


@app.post("/api/accounts")
async def add_account(body: AccountCreate):
    r = sb.table("mt5_accounts").insert(body.dict()).execute()
    return r.data[0] if r.data else {"error": "insert failed"}


@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: int):
    sb.table("mt5_accounts").delete().eq("id", account_id).execute()
    return {"status": "deleted"}


@app.post("/api/accounts/{account_id}/activate")
async def activate_account(account_id: int):
    """Set one account as active (deactivates all others)."""
    sb.table("mt5_accounts").update({"is_active": False}).neq("id", account_id).execute()
    sb.table("mt5_accounts").update({"is_active": True}).eq("id", account_id).execute()
    r = sb.table("mt5_accounts").select("*").eq("id", account_id).execute()
    acct = r.data[0] if r.data else {}
    # update the active account in the JSON file too (for the bot to pick up)
    if acct:
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "data" / "mt5_accounts.json"
        data = {"active": acct["name"], "accounts": {}}
        data["accounts"][acct["name"]] = {
            "login": acct["login"], "password": acct["password"], "server": acct["server"]}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))
    return {"status": "activated", "account": acct}


# ===== Live account state + broker symbols (read bot heartbeat) =====

def _active_login() -> int | None:
    """Login of the currently-active MT5 account, or None."""
    r = sb.table("mt5_accounts").select("login").eq("is_active", True).limit(1).execute()
    return r.data[0]["login"] if r.data else None


@app.get("/api/account")
async def account_state():
    """Live account snapshot written by the bot's ~5s telemetry task.
    Returns {} when no bot heartbeat has landed yet (dashboard shows 'awaiting bot')."""
    login = _active_login()
    if login is None:
        return {}
    r = sb.table("account_state").select("*").eq("login", login).limit(1).execute()
    return r.data[0] if r.data else {}


@app.get("/api/symbols")
async def symbols():
    """Discovered (broker-offered) + active (traded) symbol lists.
    `discovered` comes from the bot's heartbeat (account_state.symbols of the
    active login); `active` is the curated set from runtime config."""
    discovered: list = []
    login = _active_login()
    if login is not None:
        r = sb.table("account_state").select("symbols").eq("login", login).limit(1).execute()
        discovered = (r.data or [{}])[0].get("symbols") or []
    return {"discovered": discovered, "active": runtime.active_symbols}
