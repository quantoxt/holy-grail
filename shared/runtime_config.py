"""RuntimeConfig — mutable, dashboard-adjustable trading parameters.

Unlike Settings (immutable, from .env), these are PATCHed live from the dashboard
via the API. The Sentinel reads from this object, so changing a value here
takes effect on the next trade cycle — no restart needed.

CROSS-PROCESS SYNC: the API (dashboard) and the bot (soldier.loop) are separate
processes. State is backed by the `bot_config` Supabase row (single row, id=1):
  * update()  → mutates in memory then persist()s to bot_config   (API side)
  * refresh() → re-reads bot_config into self                      (bot side)
The bot calls refresh() on boot and every ~5s from its telemetry task, so
dashboard edits (symbols, risk params, start/stop) reach the running bot
within seconds — genuinely hot, across processes.
"""
import json
from dataclasses import dataclass, field
from datetime import timezone
from threading import Lock


@dataclass
class RuntimeConfig:
    # --- weekly goal framework ---
    weekly_goal: float = 14.0           # $14 target per week
    baseline_equity: float = 50.0       # account resets to this each week (anti-compounding)
    withdraw_profit_weekly: bool = True # log profit as withdrawn at week boundary

    # --- risk guardrails ---
    max_risk_per_trade: float = 1.0     # reference risk (actual is min-lot-bound, see below)
    max_daily_loss: float = 3.0         # $3 daily loss cap
    max_weekly_drawdown: float = 10.0   # stop if equity <= $40
    max_open_positions: int = 2         # limit correlated exposure
    sl_multiplier: float = 2.0          # fallback SL = sl_multiplier × |move| (only when vol=0)
    sl_atr_mult: float = 2.0            # default SL = sl_atr_mult × realized horizon-vol (ATR-based)
    sl_atr_mults: dict = field(default_factory=lambda: {"XAGUSD": 1.0})  # per-symbol overrides (tighter for volatile instruments so they fit the cap)
    max_move_pct: float = 0.015         # plausibility cap: reject |predicted_move| > 1.5% (long-shots)

    # --- min-lot risk reality (observed overnight 2026-08-10) ---
    # Brokers floor lot to 0.01, so the $-at-SL is whatever min-lot dictates, NOT
    # max_risk_per_trade. We accept that (scale to min-lot) but cap each trade's
    # actual $-at-SL at risk_cap_pct of equity — refuse suicide, don't refuse trade.
    risk_cap_pct: float = 0.03          # skip if actual $-at-SL > 3% of equity

    # --- goal-aware exit (reverses the old "no TP" lock) ---
    # Hard weekly ceiling: baseline + weekly_goal. Once LIVE EQUITY (incl. floating)
    # reaches it, close ALL positions and stop for the week — bank the goal, don't
    # give it back (a +$14 floating held to horizon became -$7 overnight).
    # Per-trade: once floating profit >= profit_lock_target, ratchet SL to lock
    # max(profit_lock_min, peak_profit × profit_lock_fraction) of the gain.
    profit_lock_target: float = 5.0     # floating-$ at which profit-trailing engages
    profit_lock_min: float = 2.0        # minimum $ profit locked once trailing on
    profit_lock_fraction: float = 0.5   # lock this fraction of peak favorable $

    # --- dynamic adjustments ---
    thursday_aggression: bool = True    # boost risk to $1.50 on Thursday if behind
    thursday_threshold: float = 7.0     # only boost if weekly_pnl < this
    thursday_risk: float = 1.5          # boosted risk amount
    min_confidence_for_boost: float = 0.9  # only boost on A-grade signals

    # --- correlation filter ---
    correlation_filter: bool = True     # if XAUUSD + XAGUSD signal simultaneously, take only stronger
    correlated_pairs: list = field(default_factory=lambda: [["XAUUSD", "XAGUSD"]])

    # --- news blackout ---
    news_blackout_enabled: bool = True  # pause trading around high-impact news
    news_blackout_pre_min: int = 30     # stop N min before event
    news_blackout_post_min: int = 15    # resume N min after

    # --- bot control ---
    bot_running: bool = True            # dashboard start/stop toggle
    trading_paused: bool = False        # pause (stay connected, no new trades)

    # --- symbols (runtime-adjustable) ---
    active_symbols: list = field(default_factory=lambda: ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD"])

    _lock: Lock = field(default_factory=Lock, repr=False)
    _client: object = field(default=None, repr=False)

    # ---- Supabase client (lazy; avoids import-time dep + keeps this module standalone) ----
    @property
    def client(self):
        if self._client is None:
            from supabase import create_client
            from shared.config import settings
            self._client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        return self._client

    # ---- fields that are NOT persisted/read back from bot_config ----
    _internal = {"_lock", "_client"}

    def update(self, **kwargs):
        """PATCH values from the dashboard, then persist to Supabase."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k) and not k.startswith("_"):
                    setattr(self, k, v)
        self.persist()

    def snapshot(self) -> dict:
        """Read-only snapshot for the dashboard (excludes internal fields)."""
        with self._lock:
            return {k: v for k, v in self.__dict__.items()
                    if not k.startswith("_") and k not in self._internal}

    def persist(self):
        """Write the full snapshot to the bot_config singleton row (id=1)."""
        try:
            self.client.table("bot_config").upsert(
                {"id": 1, "config": self.snapshot(), "updated_at": "now()"}, on_conflict="id"
            ).execute()
        except Exception:
            # Supabase down / not configured — keep trading on in-memory values.
            pass

    def refresh(self):
        """Re-read bot_config(id=1) and apply to self. Called by the bot.
        Tolerant: no-op if the row is missing or Supabase is unreachable, so a
        fresh DB or offline DB never blocks the bot."""
        try:
            r = self.client.table("bot_config").select("config").eq("id", 1).limit(1).execute()
            cfg = (r.data or [{}])[0].get("config") if r.data else None
            if not isinstance(cfg, dict):
                return
            with self._lock:
                for k, v in cfg.items():
                    if k.startswith("_") or k in self._internal:
                        continue
                    # null in the stored row means "not configured" (e.g. a field added
                    # after the row was seeded) — keep the dataclass default rather than
                    # clobbering it with None (which would crash numeric math downstream).
                    if v is None:
                        continue
                    if hasattr(self, k):
                        setattr(self, k, v)
        except Exception:
            pass

    def auto_calibrate(self, balance: float, weekly_goal: float):
        """Derive risk params FROM balance + goal. Does NOT change balance/goal.

        Uses balance as a sizing guide (not necessarily the live account balance):
          risk/trade = 2% of balance
          daily loss = 6% of balance
          weekly drawdown = 20% of balance
          max positions = how many trades needed to hit goal (capped 1-5)
        """
        risk = round(balance * 0.02, 2)
        with self._lock:
            self.max_risk_per_trade = risk
            self.max_daily_loss = round(balance * 0.06, 2)
            self.max_weekly_drawdown = round(balance * 0.20, 2)
            self.max_open_positions = min(5, max(1, int(weekly_goal / (risk * 2))))
        self.persist()
        return self.snapshot()


# singleton — imported everywhere
runtime = RuntimeConfig()
