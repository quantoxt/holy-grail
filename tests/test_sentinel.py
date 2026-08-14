"""Money-math tests for Sentinel's kill switches and lot sizing.

Run:  python3 tests/test_sentinel.py   (plain asserts — no pytest dependency)
These are the functions whose silent bugs cost real dollars.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentinel.risk import Sentinel          # noqa: E402
from shared.runtime_config import runtime   # noqa: E402


def fresh(cfg=None):
    s = Sentinel()
    runtime.update = lambda **kw: None  # don't persist test mutations
    runtime.weekly_goal = 14.0
    runtime.baseline_equity = 500.0
    runtime.max_weekly_drawdown = 100.0
    runtime.max_daily_loss = 50.0
    runtime.max_open_positions = 10
    runtime.bot_running = True
    runtime.trading_paused = False
    runtime.news_blackout_enabled = False
    for k, v in (cfg or {}).items():
        setattr(runtime, k, v)
    return s


def test_goal_hit_banks_and_latches():
    s = fresh()
    stop, reason, close_all = s.check_kill(equity=510.0, floating_pnl=15.0)
    assert stop and close_all and "weekly_goal_hit" in reason
    assert s.weekly_goal_locked
    # latched: steady-state label, no close-all spam
    stop2, reason2, close2 = s.check_kill(equity=514.0)
    assert stop2 and not close2 and "banked" in reason2


def test_withdraw_resumes_trading():
    s = fresh()
    s.check_kill(equity=515.0)               # banks the goal, latches
    assert s.weekly_goal_locked
    # equity still >= ceiling -> stays latched
    assert s.check_kill(equity=514.5, open_positions=0)[0]
    # profit withdrawn -> equity below ceiling, flat -> unlatch + fresh slate
    stop, reason, _ = s.check_kill(equity=500.0, open_positions=0)
    assert not s.weekly_goal_locked and not stop
    assert s.weekly_pnl == 0.0


def test_withdraw_does_not_unlatch_with_open_positions():
    s = fresh()
    s.check_kill(equity=515.0)
    s.check_kill(equity=499.0, open_positions=2)   # transient dip, positions open
    assert s.weekly_goal_locked                   # must stay latched


def test_equity_ceiling_and_floor():
    s = fresh()
    stop, reason, _ = s.check_kill(equity=514.87)
    assert stop and "equity_ceiling" in reason and s.weekly_goal_locked
    s2 = fresh()
    stop, reason, close_all = s2.check_kill(equity=400.0)   # 500 - 100 floor
    assert stop and close_all and "equity_floor" in reason


def test_daily_loss_cap():
    s = fresh()
    s.daily_pnl = -50.0
    stop, reason, close_all = s.check_kill(equity=450.0)
    assert stop and close_all and "daily_loss_cap" in reason


def test_lot_size_min_and_risk():
    # 1.0 risk, 100-pip SL on EURUSD-style contract → sub-min → floored to min
    lot = Sentinel.lot_size(1.0, 1.1000, 1.0900, 100_000.0, 0.01, 0.01)
    assert lot == 0.01
    # large risk × tight SL → real sizing, stepped
    lot = Sentinel.lot_size(100.0, 4400.0, 4390.0, 100.0, 0.01, 0.01)
    assert abs(lot - 0.10) < 1e-9
    # degenerate: zero SL distance or zero risk → 0
    assert Sentinel.lot_size(1.0, 1.1, 1.1, 100_000.0, 0.01, 0.01) == 0.0
    assert Sentinel.lot_size(0.0, 1.1, 1.0, 100_000.0, 0.01, 0.01) == 0.0


def test_weekly_reset_clears_latch():
    from datetime import date
    s = fresh()
    s.check_kill(equity=515.0)
    s.weekly_pnl = 14.0
    s.check_time_resets(date(2026, 8, 14))   # initialize tracking (first call)
    s.check_time_resets(date(2026, 8, 17))   # next Monday resets
    assert not s.weekly_goal_locked and s.weekly_pnl == 0.0
    assert s.weekly_withdrawn == 14.0        # profit logged as withdrawn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS {fn.__name__}")
    print(f"{len(fns)}/{len(fns)} passed")
