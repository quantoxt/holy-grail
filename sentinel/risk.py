"""Sentinel v2 — goal-driven risk manager (Layer 3).

Implements the fine-tune.md risk framework with the REVISED exit strategy
(time-based close at h=24 + hard SL safety net, NOT 3:1 R:R TP/SL).

Guardrails:
  - Weekly goal hit → stop trading for the week.
  - Equity floor ($40) → stop trading.
  - Daily loss cap ($3) → cool-off.
  - Max open positions (2).
  - Anti-compounding: risk always based on baseline ($50), not current equity.
  - Profit withdrawal: weekly profit logged as withdrawn, baseline resets.
  - Thursday aggression: boost risk on A-grade signals if behind target.

All params are dashboard-adjustable via RuntimeConfig (live hot-reload).
"""
from datetime import date, timedelta

from shared.runtime_config import runtime


# Default per-symbol contract specs (MT5). The provider's get_symbol_info
# can override these with live broker values.
SYMBOL_SPECS = {
    "XAUUSD":  {"contract_size": 100.0,  "volume_min": 0.01, "volume_step": 0.01},
    "XAGUSD":  {"contract_size": 5000.0, "volume_min": 0.01, "volume_step": 0.01},
    "BTCUSDT": {"contract_size": 1.0,    "volume_min": 0.001, "volume_step": 0.001},
    "EURUSD":  {"contract_size": 100000.0, "volume_min": 0.01, "volume_step": 0.01},
    "GBPUSD":  {"contract_size": 100000.0, "volume_min": 0.01, "volume_step": 0.01},
}


class Sentinel:
    def __init__(self):
        self.cfg = runtime
        # weekly/daily tracking
        self.weekly_pnl = 0.0
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.last_day: date | None = None
        self.last_week_start: date | None = None
        self.weekly_withdrawn = 0.0
        self.weekly_goal_locked = False   # latched once the $-ceiling is banked this week
        # stats
        self.total_trades = 0
        self.wins = 0

    def reset_for_new_account(self):
        """Clear all P&L/streak tracking for a new active account. Called when the
        bot hot-swaps to a different MT5 login — a new account starts at a clean
        slate (no carryover of the prior account's wins/losses/goal progress)."""
        self.weekly_pnl = 0.0
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.total_trades = 0
        self.wins = 0
        self.weekly_goal_locked = False
        self.last_day = None
        self.last_week_start = None

    # ---- time resets ----

    def check_time_resets(self, current_date: date):
        """Detect day/week boundaries and reset tracking."""
        if self.last_day is None:
            self.last_day = current_date
            self.last_week_start = current_date - timedelta(days=current_date.weekday())
            return

        # daily reset
        if current_date > self.last_day:
            self.daily_pnl = 0.0
            self.last_day = current_date

        # weekly reset (Monday of a new week)
        week_start = current_date - timedelta(days=current_date.weekday())
        if week_start > self.last_week_start:
            if self.cfg.withdraw_profit_weekly and self.weekly_pnl > 0:
                self.weekly_withdrawn += self.weekly_pnl
                print(f"[Sentinel] weekly reset: withdrew ${self.weekly_pnl:.2f}, "
                      f"total withdrawn ${self.weekly_withdrawn:.2f}")
            self.weekly_pnl = 0.0
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self.weekly_goal_locked = False
            self.last_week_start = week_start

    # ---- kill switches ----

    def check_kill(self, equity: float, open_positions: int = 0,
                   symbols: list | None = None,
                   floating_pnl: float = 0.0) -> tuple[bool, str, bool]:
        """Returns (should_stop_trading, reason, close_all_open).

        close_all=True means "get out NOW" (bank the goal / stop the bleed) — the
        loop closes every open position. False means "just don't open more".

        equity is LIVE (includes floating), so a +$14 in-flight trade counts toward
        the goal — the overnight bug was holding a winner to horizon and giving it back.
        """
        if not self.cfg.bot_running:
            return True, "bot_stopped", False
        if self.cfg.trading_paused:
            return True, "paused", False
        # weekly goal — realized OR floating (in-flight profit counts)
        if self.weekly_goal_locked or (self.weekly_pnl + floating_pnl) >= self.cfg.weekly_goal:
            self.weekly_goal_locked = True
            return (True, f"weekly_goal_hit (${self.weekly_pnl + floating_pnl:.2f} "
                    f">= ${self.cfg.weekly_goal:.2f})", True)
        # hard equity ceiling: baseline + goal reached → bank everything, stop for the week
        ceiling = self.cfg.baseline_equity + self.cfg.weekly_goal
        if equity >= ceiling:
            self.weekly_goal_locked = True
            return True, f"equity_ceiling (${equity:.2f} >= ${ceiling:.2f})", True
        floor = self.cfg.baseline_equity - self.cfg.max_weekly_drawdown
        if equity <= floor:
            return True, f"equity_floor (${equity:.2f} <= ${floor:.2f})", True
        if self.daily_pnl <= -self.cfg.max_daily_loss:
            return True, f"daily_loss_cap (${self.daily_pnl:.2f})", True
        if open_positions >= self.cfg.max_open_positions:
            return True, f"max_positions ({open_positions})", False
        if self.consecutive_losses >= 5:
            return True, f"consecutive_losses ({self.consecutive_losses})", True
        # news blackout
        if self.cfg.news_blackout_enabled and symbols:
            from shared.news import is_blackout
            blocked, breason = is_blackout(
                symbols, self.cfg.news_blackout_pre_min, self.cfg.news_blackout_post_min)
            if blocked:
                return True, breason, False
        return False, "ok", False

    # ---- risk computation ----

    def risk_amount(self, signal_confidence: float, current_date: date) -> float:
        """Dollar risk for this trade, with Thursday aggression boost."""
        risk = self.cfg.max_risk_per_trade
        if (self.cfg.thursday_aggression and current_date.weekday() == 3
                and self.weekly_pnl < self.cfg.thursday_threshold
                and signal_confidence >= self.cfg.min_confidence_for_boost):
            risk = self.cfg.thursday_risk
        # cap: don't risk more than what's left of the daily loss budget
        remaining_daily = self.cfg.max_daily_loss + self.daily_pnl
        if risk > remaining_daily:
            risk = max(0, remaining_daily)
        return risk

    @staticmethod
    def lot_size(risk_amount: float, entry_price: float, sl_price: float,
                 contract_size: float, volume_min: float, volume_step: float) -> float:
        """Compute lot from risk + SL distance + symbol specs.
        lot = risk / (|entry - sl| × contract_size), floored to broker step."""
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0 or risk_amount <= 0:
            return 0.0
        lot = risk_amount / (sl_distance * contract_size)
        lot = max(volume_min, (lot // volume_step) * volume_step)
        return lot

    def get_symbol_spec(self, symbol: str) -> dict:
        """Contract specs for lot sizing."""
        return SYMBOL_SPECS.get(symbol, {"contract_size": 1.0, "volume_min": 0.01, "volume_step": 0.01})

    # ---- trade accounting ----

    def on_trade_closed(self, pnl: float, correct: bool):
        self.weekly_pnl += pnl
        self.daily_pnl += pnl
        self.total_trades += 1
        if correct:
            self.wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

    # ---- dashboard data ----

    def weekly_status(self) -> dict:
        goal = self.cfg.weekly_goal
        return {
            "weekly_pnl": round(self.weekly_pnl, 2),
            "weekly_goal": goal,
            "weekly_progress_pct": round(min(100, self.weekly_pnl / goal * 100), 1) if goal else 0,
            "daily_pnl": round(self.daily_pnl, 2),
            "max_daily_loss": self.cfg.max_daily_loss,
            "consecutive_losses": self.consecutive_losses,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.total_trades - self.wins,
            "win_rate": round(self.wins / self.total_trades, 3) if self.total_trades else 0,
            "withdrawn_total": round(self.weekly_withdrawn, 2),
            "baseline_equity": self.cfg.baseline_equity,
        }


# global singleton — the loop and API both use this instance
sentinel = Sentinel()
