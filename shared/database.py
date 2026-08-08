"""Supabase logging — logs every bot decision to the audit tables.

Uses the SERVICE ROLE key (backend, bypasses RLS) for full insert access. Every
prediction, signal, trade, and risk event flows here. Central audit trail — the
FastAPI backend and dashboard read from these same tables.
"""
import json
from datetime import datetime, timezone

from supabase import create_client

from shared.config import settings


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
            "predictions": json.dumps(predictions_list, default=str),
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
    def log_trade_open(self, symbol, direction, entry_price, size, confidence, horizon, paper=True, ticket=None):
        resp = self.client.table("trades").insert({
            "symbol": symbol, "market_mode": settings.market_mode, "paper": paper,
            "direction": direction, "entry_price": entry_price,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "size": size, "confidence": confidence, "horizon": horizon,
            "result": "open", "provider_ticket": str(ticket) if ticket else None,
        }).execute()
        return resp.data[0]["id"] if resp.data else None

    def log_trade_close(self, trade_id, exit_price, pnl, result):
        self.client.table("trades").update({
            "exit_price": exit_price, "pnl": pnl, "result": result,
            "exit_time": datetime.now(timezone.utc).isoformat(),
        }).eq("id", trade_id).execute()

    # --- risk events (Sentinel) ---
    def log_risk_event(self, event_type, reason, data=None, lot_before=None, lot_after=None):
        self.client.table("risk_events").insert({
            "event_type": event_type, "reason": reason,
            "data": json.dumps(data) if data else None,
            "lot_before": lot_before, "lot_after": lot_after,
        }).execute()

    # --- account state (live heartbeat — bot writes, dashboard reads) ---
    def upsert_account_state(self, login, broker, balance, equity, currency,
                             floating_pnl, open_positions, symbols):
        """Upsert one row per MT5 login. Written by the bot's ~5s telemetry task;
        read by GET /api/account for the dashboard."""
        self.client.table("account_state").upsert({
            "login": login, "broker": broker,
            "balance": balance, "equity": equity, "currency": currency,
            "floating_pnl": floating_pnl,
            "open_positions": json.dumps(open_positions, default=str),
            "symbols": json.dumps(symbols, default=str),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="login").execute()


db = DBLogger()
