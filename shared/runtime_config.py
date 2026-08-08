"""RuntimeConfig — mutable, dashboard-adjustable trading parameters.

Unlike Settings (immutable, from .env), these are PATCHed live from the dashboard
via the API. The Sentinel reads from this object, so changing a value here
takes effect on the next trade cycle — no restart needed.
"""
from dataclasses import dataclass, field
from datetime import date, timezone
from threading import Lock


@dataclass
class RuntimeConfig:
    # --- weekly goal framework ---
    weekly_goal: float = 14.0           # $14 target per week
    baseline_equity: float = 50.0       # account resets to this each week (anti-compounding)
    withdraw_profit_weekly: bool = True # log profit as withdrawn at week boundary

    # --- risk guardrails ---
    max_risk_per_trade: float = 1.0     # $1 per trade (2% of $50)
    max_daily_loss: float = 3.0         # $3 daily loss cap
    max_weekly_drawdown: float = 10.0   # stop if equity <= $40
    max_open_positions: int = 2         # limit correlated exposure
    sl_multiplier: float = 2.0          # SL = sl_multiplier × |predicted_move|

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

    def update(self, **kwargs):
        """PATCH values from the dashboard."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k) and not k.startswith("_"):
                    setattr(self, k, v)

    def snapshot(self) -> dict:
        """Read-only snapshot for the dashboard."""
        with self._lock:
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

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
        return self.snapshot()


# singleton — imported everywhere
runtime = RuntimeConfig()
