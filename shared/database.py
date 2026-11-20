"""Supabase logging — logs every bot decision to the audit tables.

Uses the SERVICE ROLE key (backend, bypasses RLS) for full insert access. Every
prediction, signal, trade, and risk event flows here. Central audit trail — the
FastAPI backend and dashboard read from these same tables.
"""
import json
from datetime import datetime, timedelta, timezone

from supabase import create_client

from shared.config import settings


def _jsonable(obj):
    """Return obj as JSON-native Python (lists/dicts/str/num) with non-serializable
    values stringified. For jsonb columns pass the RESULT of this — NOT json.dumps,
    which double-encodes into a jsonb string and breaks the dashboard's array reads."""
    return json.loads(json.dumps(obj, default=str))


class DBLogger:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
        return self._client

    # --- predictions (every Kronos inference) ---
    def log_prediction(self, symbol, timeframe, candle_time, predictions_list,
                       predicted_close, predicted_direction, predicted_magnitude,
                       lookback, pred_len, sample_count, inference_ms):
        self.client.table("kronos_predictions").insert({
            "symbol": symbol, "timeframe": timeframe,
            "market_mode": settings.market_mode,
            "candle_time": candle_time,
            "model_version": settings.kronos_model,
            "lookback": lookback, "pred_len": pred_len, "sample_count": sample_count,
            "predictions": _jsonable(predictions_list),
            "predicted_close": predicted_close,
            "predicted_direction": predicted_direction,
            "predicted_magnitude": predicted_magnitude,
            "inference_ms": inference_ms,
        }).execute()

    # --- signals (Soldier's BUY/SELL/HOLD) ---
    def log_signal(self, symbol, timeframe, direction, confidence, predicted_move,
                   current_close, predicted_close, horizon, regime=None, filtered=False):
        self.client.table("signals").insert({
            "symbol": symbol, "timeframe": timeframe,
            "market_mode": settings.market_mode,
            "signal_time": datetime.now(timezone.utc).isoformat(),
            "direction": direction, "confidence": confidence,
            "predicted_move": predicted_move,
            "current_close": current_close,
            "predicted_close": predicted_close,
            "horizon": horizon, "regime": regime,
            "regime_filtered": filtered,
        }).execute()

    # --- trades (open + close) ---
    def log_trade_open(self, symbol, direction, entry_price, size, confidence, horizon, paper=True, ticket=None, mt5_login=None):
        resp = self.client.table("trades").insert({
            "symbol": symbol, "market_mode": settings.market_mode, "paper": paper,
            "direction": direction, "entry_price": entry_price,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "size": size, "lots": size, "confidence": confidence, "horizon": horizon,
            "result": "open", "provider_ticket": str(ticket) if ticket else None,
            "mt5_login": mt5_login,
        }).execute()
        return resp.data[0]["id"] if resp.data else None

    def log_trade_close(self, trade_id, exit_price, pnl, result):
        self.client.table("trades").update({
            "exit_price": exit_price, "pnl": pnl, "result": result,
            "exit_time": datetime.now(timezone.utc).isoformat(),
        }).eq("id", trade_id).execute()

    def update_trade_result(self, trade_id, exit_price, pnl, result):
        """Correct a closed trade's outcome with broker-truth numbers (deferred
        deal reconciliation). Does NOT re-stamp exit_time — the close moment
        already happened; only the numbers were estimates."""
        self.client.table("trades").update({
            "exit_price": exit_price, "pnl": pnl, "result": result,
        }).eq("id", trade_id).execute()

    # --- prediction evaluations (the measurement loop) ---
    def log_evaluation(self, symbol, timeframe, direction, predicted_move,
                       predicted_close, current_close, confidence, snr,
                       sample_count, horizon_min):
        """One row per prediction (traded OR skipped — the shadow record is the point).
        Resolved later against the actual close at due_time."""
        now = datetime.now(timezone.utc)
        self.client.table("prediction_evaluations").insert({
            "symbol": symbol, "timeframe": timeframe,
            "signal_time": now.isoformat(),
            "due_time": (now + timedelta(minutes=horizon_min)).isoformat(),
            "direction": direction,
            "predicted_move": predicted_move, "predicted_close": predicted_close,
            "current_close": current_close,
            "confidence": confidence, "snr": snr, "sample_count": sample_count,
        }).execute()

    def due_evaluations(self, limit=15):
        """Matured-but-unresolved evaluations (due_time passed)."""
        r = self.client.table("prediction_evaluations").select("*") \
            .is_("outcome", "null").lte("due_time", datetime.now(timezone.utc).isoformat()) \
            .order("due_time").limit(limit).execute()
        return r.data or []

    def resolve_evaluation(self, eval_id, outcome, actual_close, actual_move):
        self.client.table("prediction_evaluations").update({
            "outcome": outcome, "actual_close": actual_close,
            "actual_move": actual_move,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", eval_id).execute()

    def recent_resolved_evaluations(self, limit=20, direction_only=True):
        """Most recent resolved evaluations, newest first (feeds the Watcher)."""
        q = self.client.table("prediction_evaluations") \
            .select("direction,outcome").in_("outcome", ["hit", "miss"]) \
            .order("resolved_at", desc=True).limit(limit)
        if direction_only:
            q = q.neq("direction", "HOLD")
        return q.execute().data or []

    def prune_predictions(self, days=7):
        """Drop raw kronos_predictions older than N days (24-candle JSON per
        symbol per 5-min cycle bloats fast; evaluations keep the stats)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        self.client.table("kronos_predictions").lt("created_at", cutoff.isoformat()).delete().execute()

    # --- signal alerts (Signal Mode dispatches — one row per Telegram signal) ---
    def log_signal_alert(self, symbol, timeframe, direction, entry_price, sl_price,
                         tp_price, confidence, predicted_move, snr, telegram_sent=True):
        self.client.table("signal_alerts").insert({
            "symbol": symbol, "timeframe": timeframe,
            "market_mode": settings.market_mode,
            "signal_time": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "entry_price": entry_price, "sl_price": sl_price, "tp_price": tp_price,
            "confidence": confidence, "predicted_move": predicted_move, "snr": snr,
            "telegram_sent": bool(telegram_sent),
        }).execute()

    # --- telegram subscribers (command-center opt-ins) ---
    def ensure_owner_subscriber(self, chat_id):
        self.client.table("telegram_subscribers").upsert({
            "chat_id": int(chat_id), "status": "active",
            "is_owner": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="chat_id").execute()

    def subscribe_chat(self, chat_id, note=""):
        self.client.table("telegram_subscribers").upsert({
            "chat_id": int(chat_id), "status": "active", "muted": False,
            "note": (note or "")[:120],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="chat_id").execute()

    def unsubscribe_chat(self, chat_id):
        self.client.table("telegram_subscribers").update({
            "status": "inactive",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("chat_id", int(chat_id)).execute()

    def set_muted(self, chat_id, muted: bool):
        self.client.table("telegram_subscribers").update({
            "muted": bool(muted),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("chat_id", int(chat_id)).execute()

    def get_subscriber(self, chat_id):
        r = self.client.table("telegram_subscribers").select("*") \
            .eq("chat_id", int(chat_id)).limit(1).execute()
        return (r.data or [None])[0]

    def active_subscribers(self):
        """Everyone who gets proactive alerts: active + unmuted (owner included)."""
        r = self.client.table("telegram_subscribers").select("chat_id,note,is_owner") \
            .eq("status", "active").eq("muted", False).execute()
        return r.data or []

    def all_subscribers(self):
        r = self.client.table("telegram_subscribers").select("*") \
            .order("created_at").limit(100).execute()
        return r.data or []

    # --- status snapshot (feeds the /status command; tolerant, never raises) ---
    def status_snapshot(self):
        snap = {"account": {}, "config": {}, "trades": [], "signals": []}
        try:
            a = self.client.table("account_state").select("*") \
                .order("updated_at", desc=True).limit(1).execute()
            snap["account"] = (a.data or [{}])[0]
        except Exception:
            pass
        try:
            c = self.client.table("bot_config").select("config").eq("id", 1) \
                .limit(1).execute()
            snap["config"] = ((c.data or [{}])[0].get("config") or {})
        except Exception:
            pass
        try:
            t = self.client.table("trades").select(
                "symbol,direction,entry_price,exit_price,pnl,result,entry_time,exit_time") \
                .order("created_at", desc=True).limit(5).execute()
            snap["trades"] = t.data or []
        except Exception:
            pass
        try:
            s = self.client.table("signal_alerts").select(
                "symbol,direction,entry_price,sl_price,tp_price,confidence,signal_time,telegram_sent") \
                .order("signal_time", desc=True).limit(5).execute()
            snap["signals"] = s.data or []
        except Exception:
            pass
        return snap

    # --- risk events (Sentinel) ---
    def log_risk_event(self, event_type, reason, data=None, lot_before=None, lot_after=None):
        self.client.table("risk_events").insert({
            "event_type": event_type, "reason": reason,
            "data": _jsonable(data) if data else None,
            "lot_before": lot_before, "lot_after": lot_after,
        }).execute()

    # --- account state (live heartbeat — bot writes, dashboard reads) ---
    def upsert_account_state(self, login, broker, balance, equity, currency,
                             floating_pnl, open_positions, symbols,
                             news_blackout=False, news_reason="", weekly_pnl=None,
                             realized_pnl=None):
        """Upsert one row per MT5 login. Written by the bot's ~5s telemetry task;
        read directly by the Vercel dashboard. weekly_pnl is broker-realized
        (deal-history truth, incl. swap/commission) since week start when available."""
        row = {
            "login": login, "broker": broker,
            "balance": balance, "equity": equity, "currency": currency,
            "floating_pnl": floating_pnl,
            "open_positions": _jsonable(open_positions),
            "symbols": _jsonable(symbols),
            "news_blackout": bool(news_blackout),
            "news_reason": news_reason or "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if weekly_pnl is not None:
            row["weekly_pnl"] = weekly_pnl
        if realized_pnl is not None:
            row["realized_pnl"] = realized_pnl
        self.client.table("account_state").upsert(row, on_conflict="login").execute()


db = DBLogger()
