"""Money-math tests for Sentinel's kill switches, lot sizing, prop mode and the
SL-modify throttle.

Run:  python -m pytest tests/   or   python tests/test_sentinel.py (plain asserts)
These are the functions whose silent bugs cost real dollars.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentinel.risk import Sentinel          # noqa: E402
from shared.runtime_config import PROP_PROFILE, RuntimeConfig, runtime   # noqa: E402


class _Res:
    def __init__(self, data):
        self.data = data


class FakeBotConfig:
    """In-memory stand-in for the bot_config row: persist() upserts here,
    refresh() reads it back — exercises the real cross-process round trip."""
    def __init__(self):
        self.row = None
        self.fail_writes = False

    def table(self, _name):
        return self

    def upsert(self, payload, on_conflict=None):
        if not self.fail_writes:
            self.row = json.loads(json.dumps(payload["config"]))
        return self

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        return _Res([{"config": self.row}] if self.row is not None else [])


DEFAULTS = RuntimeConfig()


def fresh(cfg=None):
    s = Sentinel()
    runtime._client = FakeBotConfig()   # persist/refresh hit memory, never Supabase
    # reset every persisted field to its code default (tests mutate the singleton)
    for k, v in DEFAULTS.snapshot().items():
        setattr(runtime, k, json.loads(json.dumps(v)))
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


# ---------------- prop mode (The5ers) ----------------

def prop(cfg=None):
    s = fresh()
    for k, v in PROP_PROFILE.items():
        setattr(runtime, k, json.loads(json.dumps(v)))
    runtime.news_blackout_enabled = False
    for k, v in (cfg or {}).items():
        setattr(runtime, k, v)
    return s


def test_prop_levels():
    s = prop()
    assert s.prop_levels() == (5300.0, 4800.0)


def test_prop_trades_inside_band():
    s = prop()
    stop, reason, _ = s.check_kill(equity=5299.99)
    assert not stop and reason == "ok"
    stop, reason, _ = s.check_kill(equity=4800.01)
    assert not stop
    assert runtime.prop_status == "active"


def test_prop_pass_latches_and_persists():
    s = prop()
    stop, reason, close_all = s.check_kill(equity=5301.0)
    assert stop and close_all and reason.startswith("prop_passed")
    assert runtime.prop_status == "passed"
    assert runtime._client.row["prop_status"] == "passed"   # written to bot_config
    # equity falls back into the band → still latched, no close-all spam
    stop, reason, close_all = s.check_kill(equity=5100.0)
    assert stop and not close_all and "latched" in reason


def test_prop_fail_latches_and_persists():
    s = prop()
    stop, reason, close_all = s.check_kill(equity=4799.0)
    assert stop and close_all and reason.startswith("prop_failed")
    assert runtime.prop_status == "failed"
    assert runtime._client.row["prop_status"] == "failed"
    stop, _, close_all = s.check_kill(equity=4900.0)
    assert stop and not close_all


def test_prop_latch_survives_refresh():
    s = prop()
    s.check_kill(equity=5301.0)
    runtime.prop_status = "active"          # in-memory clobber …
    runtime.refresh()                       # … refresh restores the persisted latch
    assert runtime.prop_status == "passed"
    # a fresh process (new Sentinel, row is the only memory) stays stopped too
    s2 = Sentinel()
    stop, reason, _ = s2.check_kill(equity=5000.0)
    assert stop and "prop_passed" in reason


def test_prop_latch_survives_lost_persist():
    s = prop()
    runtime.persist()                       # row says active
    runtime._client.fail_writes = True      # Supabase down when the fail latches
    s.check_kill(equity=4799.0)
    runtime.refresh()                       # stale row → "active" read back
    assert runtime.prop_status == "active"
    stop, reason, _ = s.check_kill(equity=4900.0)
    assert stop and "prop_failed" in reason  # in-process latch still holds
    assert runtime.prop_status == "failed"   # and re-asserted


def test_prop_reset_for_next_phase():
    s = prop()
    s.check_kill(equity=5301.0)
    # next evaluation step: new start balance + status reset from the dashboard
    runtime.prop_start_balance = 10000.0
    runtime.prop_status = "active"
    stop, reason, _ = s.check_kill(equity=10000.0)
    assert not stop and reason == "ok"


def test_prop_ignores_weekly_goal_and_ceiling():
    s = prop({"weekly_goal": 14.0, "baseline_equity": 50.0})
    s.weekly_pnl = 200.0                    # way past the weekly goal
    stop, reason, _ = s.check_kill(equity=5200.0, floating_pnl=50.0)
    assert not stop and reason == "ok"
    assert not s.weekly_goal_locked


def test_prop_fixed_risk():
    from datetime import date
    s = prop()
    thursday = date(2026, 11, 19)
    assert s.risk_amount(0.99, thursday) == 25.0      # no Thursday boost in prop
    runtime.thursday_aggression = True
    assert s.risk_amount(0.99, thursday) == 25.0
    assert s.risk_amount(0.5, date(2026, 11, 16)) == 25.0


def test_prop_daily_cap_interaction():
    from datetime import date
    s = prop()
    d = date(2026, 11, 17)
    s.daily_pnl = -60.0
    assert s.risk_amount(0.6, d) == 15.0              # only $15 left of the $75 budget
    s.daily_pnl = -75.0
    assert s.risk_amount(0.6, d) == 0
    stop, reason, close_all = s.check_kill(equity=4925.0)
    assert stop and close_all and "daily_loss_cap" in reason
    assert runtime.prop_status == "active"            # daily cap is not a prop fail


def test_prop_max_positions_still_applies():
    s = prop()
    stop, reason, close_all = s.check_kill(equity=5000.0, open_positions=2)
    assert stop and not close_all and "max_positions" in reason


def test_weekly_mode_unchanged_by_prop_fields():
    from datetime import date
    s = fresh()
    assert runtime.account_mode == "weekly"
    # prop thresholds are irrelevant in weekly mode
    stop, reason, _ = s.check_kill(equity=450.0)
    assert not stop and reason == "ok"
    assert s.risk_amount(0.6, date(2026, 11, 17)) == runtime.max_risk_per_trade
    runtime.thursday_aggression = True
    assert s.risk_amount(0.95, date(2026, 11, 19)) == runtime.thursday_risk
    assert runtime.prop_status == "active"


# ---------------- SL-modify throttle ----------------

class FakeProvider:
    def __init__(self):
        self.mods = []

    def modify_sl(self, ticket, sl):
        self.mods.append(sl)
        return True


def _trader_with(pos):
    from soldier.loop import Trader
    t = Trader.__new__(Trader)       # skip __init__ (no MT5 / Kronos)
    t.provider = FakeProvider()
    t.open = {"XAUUSD": pos}
    t.log = lambda **kw: None
    return t


def _gold_buy():
    # 0.1 lot × 100 oz → $10 per $1 move; $25 risk → R = $2.50 in price
    return {"direction": "BUY", "entry_price": 2000.0, "lot": 0.1,
            "contract_size": 100.0, "ticket": 1, "sl_price": 1997.5,
            "actual_risk": 25.0, "peak_profit": 0.0}


def _bp(cur, pos):
    return [{"symbol": "XAUUSD", "price_current": cur, "volume": pos["lot"],
             "profit": (cur - pos["entry_price"]) * pos["lot"] * pos["contract_size"]}]


def test_throttle_hourly_cap_over_rising_trade():
    fresh()
    pos = _gold_buy()
    t = _trader_with(pos)
    times = []
    for tick in range(720 * 2):                    # 2h of 5s telemetry ticks
        now = 1_000_000.0 + tick * 5
        cur = 2000.0 + tick * 0.5                  # relentless rise → wants an edit every tick
        n = len(t.provider.mods)
        t._manage_exits(_bp(cur, pos), now=now)
        if len(t.provider.mods) > n:
            times.append(now)
    assert times, "trail never fired"
    for i, ts in enumerate(times):                 # every rolling hour ≤ cap
        assert sum(1 for x in times if ts <= x < ts + 3600) <= 10
        if i:
            assert ts - times[i - 1] >= 60
    assert len(times) <= 20


def test_throttle_100_ticks():
    fresh()
    pos = _gold_buy()
    t = _trader_with(pos)
    for tick in range(100):
        t._manage_exits(_bp(2000.0 + tick * 0.3, pos), now=5_000.0 + tick * 5)
    assert len(t.provider.mods) <= 10


def test_throttle_min_step_blocks_tiny_moves_breakeven_exempt():
    fresh()
    pos = _gold_buy()
    t = _trader_with(pos)
    # 0.6R floating → breakeven move (exempt from step), allowed
    t._manage_exits(_bp(2001.5, pos), now=0.0)
    assert len(t.provider.mods) == 1 and abs(pos["sl_price"] - 1999.8) < 1e-6
    # 1.05R → trail wants SL≈entry+0.125: < 0.25R ($0.625) away from BE → blocked
    t._manage_exits(_bp(2002.625, pos), now=120.0)
    assert len(t.provider.mods) == 1
    # 1.4R → trail lock 0.4R → SL 2001.0: ≥ 0.25R step → allowed
    t._manage_exits(_bp(2003.5, pos), now=240.0)
    assert len(t.provider.mods) == 2 and abs(pos["sl_price"] - 2001.0) < 1e-6


def test_throttle_min_interval():
    fresh()
    pos = _gold_buy()
    t = _trader_with(pos)
    t._manage_exits(_bp(2003.5, pos), now=0.0)      # first trail edit
    assert len(t.provider.mods) == 1
    t._manage_exits(_bp(2010.0, pos), now=30.0)     # big move but only 30s later
    assert len(t.provider.mods) == 1
    t._manage_exits(_bp(2010.0, pos), now=61.0)
    assert len(t.provider.mods) == 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS {fn.__name__}")
    print(f"{len(fns)}/{len(fns)} passed")
