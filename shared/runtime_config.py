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
    max_daily_loss: float = 15.0        # daily loss cap ≈ 2 full SL hits at the 1.5% risk cap
    max_weekly_drawdown: float = 10.0   # stop if equity <= $40
    max_open_positions: int = 2         # limit correlated exposure
    sl_multiplier: float = 2.0          # fallback SL = sl_multiplier × |move| (only when vol=0)
    sl_atr_mult: float = 1.0            # default SL = sl_atr_mult × realized horizon-vol (ATR-based)
    sl_atr_mults: dict = field(default_factory=lambda: {"XAGUSD": 1.0})  # per-symbol overrides (tighter for volatile instruments so they fit the cap)
    max_move_pct: float = 0.015         # plausibility cap: reject |predicted_move| > 1.5% (long-shots)
    min_confidence: float = 0.50        # skip signals below this confidence (observed: sub-50% trades lose)
    tp_at_predicted: bool = True        # take profit when price reaches the predicted close (path-dependency fix)
    tp_fraction: float = 1.0            # target = entry + fraction × (predicted_close − entry). 1.0 = exactly
                                        # Kronos's predicted price. Data (2026-08-16): realized moves average
                                        # only ~25-35% of predicted — full targets were reached in just 9-17%
                                        # of evals, which is why trades rode to horizon. Lower to ~0.5 for
                                        # shorter holds (dashboard-adjustable).
    tp_vol_mult: float = 0.0            # >0 overrides the predicted target: target = entry ± mult × horizon-vol
    tp_rr_mult: float = 2.0               # TP = entry ± rr_mult × SL distance (R-multiple target).
                                          # Risking $10 to make $2.5 needs 80% wins — we have 50%. At 1:2
                                          # the math works even on a coin flip (breakeven at 33%). Takes
                                          # precedence over tp_vol_mult/tp_fraction when > 0.
    tp_vol_mults: dict = field(default_factory=dict)  # per-symbol override of tp_vol_mult (e.g. {"XAUUSD": 1.5}) — 0.7σ is
                                        # spread-scale on quiet metals/forex → the bot scalps itself broke
    tp_min_spread_mult: float = 3.0     # target must sit at least this many spreads from the FILL price —
                                        # a target inside the spread is a guaranteed spread-loss, not a win
                                        # (realized σ over 2h). Correlation of predicted vs actual size is ≈0
                                        # (even negative on XAUUSD) — predicted MAGNITUDE carries no information,
                                        # so exits sized to real volatility, not the forecast. ~0.7 = median
                                        # realized move (reachable ~50% of the time); 1.0 = one sigma.

    # --- min-lot risk reality (observed overnight 2026-08-10) ---
    # Brokers floor lot to 0.01, so the $-at-SL is whatever min-lot dictates, NOT
    # max_risk_per_trade. We accept that (scale to min-lot) but cap each trade's
    # actual $-at-SL at risk_cap_pct of equity — refuse suicide, don't refuse trade.
    risk_cap_pct: float = 0.015         # skip if actual $-at-SL > 1.5% of equity (~$7.5 at $500)

    # --- goal-aware exit (reverses the old "no TP" lock) ---
    # Hard weekly ceiling: baseline + weekly_goal. Once LIVE EQUITY (incl. floating)
    # reaches it, close ALL positions and stop for the week — bank the goal, don't
    # give it back (a +$14 floating held to horizon became -$7 overnight).
    # Per-trade: once floating profit >= profit_lock_target, ratchet SL to lock
    # max(profit_lock_min, peak_profit × profit_lock_fraction) of the gain.
    profit_lock_target: float = 5.0     # fixed fallback: floating-$ at which trailing engages
    profit_lock_min: float = 2.0        # fixed fallback: minimum $ profit locked once trailing on
    profit_lock_fraction: float = 0.5   # fixed fallback: lock this fraction of peak favorable $
    profit_lock_r: float = 1.0          # trailing engages at floating >= this × actual $-at-SL (R)
    trail_slack_r: float = 1.0          # once trailing, SL stays this many R behind live profit
    breakeven_lock_r: float = 0.5       # SL→entry at floating >= this × R (before full trailing)

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

    # --- signal mode (hybrid: trading continues, qualified setups also alert) ---
    signals_enabled: bool = True        # dashboard toggle: send Telegram signals
    signal_cooldown_min: int = 120      # one alert per symbol per N min unless direction flips

    # --- balance-based weekly P&L (broker history lags real closes) ---
    # Snapshot of the account balance at the start of the current trading week
    # (Monday 00:00 UTC). weekly_pnl = balance − week_start_balance − cashflow_since
    # (deposits/withdrawals). Deal-history sums miss closes made minutes ago;
    # balance arithmetic can't.
    week_start_balance: float = None
    week_start_cash: float = 0.0    # cashflow-since-Monday already embedded in week_start_balance —
                                     # only NEW deposits after the snapshot are backed out of weekly P&L
                                     # (guards against the broker indexing deposits late)    # None until first snapshot
    week_start_monday: str = ""         # 'YYYY-MM-DD' of the Monday this snapshot belongs to

    # --- symbols (runtime-adjustable) ---
    active_symbols: list = field(default_factory=lambda: ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD"])

    # --- account mode: "weekly" (Sentinel v2 goal/ceiling/withdraw) | "prop" ---
    # Prop mode (The5ers Bootcamp step 1) replaces the weekly goal/ceiling/withdraw
    # logic with a one-shot pass/fail evaluation against a STATIC start balance:
    #   pass  : equity >= prop_start_balance + prop_target                 ($5,300)
    #   fail  : equity <= prop_start_balance - prop_max_loss + floor_buffer ($4,800,
    #           $50 above The5ers' own $4,750 line so slippage can't breach theirs)
    # prop_status is a PERSISTED latch: once passed/failed, a restart never resumes
    # trading. Next evaluation step = set the new start balance + prop_status="active".
    account_mode: str = "weekly"
    prop_start_balance: float = 5000.0
    prop_target: float = 300.0
    prop_max_loss: float = 250.0
    prop_floor_buffer: float = 50.0
    prop_status: str = "active"         # "active" | "passed" | "failed"
    risk_pct_per_trade: float = 0.005   # prop: fixed $-risk = start balance × this ($25), NOT
                                        # live equity — consistent sizing (The5ers bans erratic lots)

    # --- SL-modify throttle (The5ers bans excessive server requests) ---
    sl_modify_min_step_r: float = 0.25     # an SL edit must move the stop >= this × R (price);
                                           # the breakeven move is exempt (single event)
    sl_modify_min_interval_s: float = 60.0  # >= this many seconds between edits per position
    sl_modify_max_per_hour: int = 10        # <= this many edit attempts per position per rolling hour

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

    def apply_prop_profile(self):
        """Switch to the The5ers prop profile (PROP_PROFILE) and persist it.
        Explicit opt-in — code defaults stay weekly-mode so an existing bot_config
        row/behaviour is unchanged until someone flips it."""
        self.update(**PROP_PROFILE)
        return self.snapshot()


# The5ers Bootcamp step-1 profile ($5,000 start, +$300 pass, $4,750 static fail).
# Applied via runtime.apply_prop_profile() or the same keys PATCHed from the dashboard.
PROP_PROFILE = {
    "account_mode": "prop",
    "prop_start_balance": 5000.0,
    "prop_target": 300.0,
    "prop_max_loss": 250.0,
    "prop_floor_buffer": 50.0,
    "prop_status": "active",
    "risk_pct_per_trade": 0.005,
    "max_daily_loss": 75.0,            # self-imposed (The5ers has none in steps 1-3)
    "active_symbols": ["XAUUSD", "GBPUSD", "BTCUSD"],
    "max_open_positions": 2,
    "thursday_aggression": False,
    "withdraw_profit_weekly": False,
}


# singleton — imported everywhere
runtime = RuntimeConfig()
