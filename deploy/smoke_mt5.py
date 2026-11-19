"""Read-only smoke test of the MT5 link through providers/mt5.py's import shim.

Calls initialize, account_info, symbols_get, copy_rates_from_pos, positions_get,
history_deals_get and checks the results look like the native package's
(namedtuples with ._asdict(), numpy rates that pd.DataFrame accepts).
NEVER sends an order.

    docker compose -f deploy/docker-compose.yml run --rm bot python deploy/smoke_mt5.py [SYMBOL]

Exit code 0 = all checks passed.
"""
import sys
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd

from providers.mt5 import mt5, _TF

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
failures = 0


def check(name, fn):
    global failures
    try:
        detail = fn()
        print(f"PASS  {name}: {detail}")
    except Exception as e:  # noqa: BLE001
        failures += 1
        print(f"FAIL  {name}: {type(e).__name__}: {e}")
        traceback.print_exc(limit=2)


def _initialize():
    ok = mt5.initialize()
    assert ok, f"initialize() returned {ok!r}, last_error={mt5.last_error()!r}"
    return f"ok, backend={type(mt5).__module__}"


def _account_info():
    info = mt5.account_info()
    assert info is not None, f"None (terminal not logged in?) last_error={mt5.last_error()!r}"
    d = info._asdict()
    assert {"login", "balance", "equity", "currency"} <= set(d)
    return (f"login={info.login} server={getattr(info, 'server', '?')} "
            f"balance={info.balance} equity={info.equity} {info.currency} "
            f"trade_allowed={getattr(info, 'trade_allowed', '?')}")


resolved = {"sym": SYMBOL}


def _symbols_get():
    syms = mt5.symbols_get()
    assert syms, "empty symbol list"
    names = sorted(s.name for s in syms)
    match = [n for n in names if n.startswith(SYMBOL)]
    if match:
        resolved["sym"] = min(match, key=len)
    return f"{len(names)} symbols; {SYMBOL} -> {resolved['sym'] if match else 'NOT OFFERED'}"


def _copy_rates():
    rates = mt5.copy_rates_from_pos(resolved["sym"], _TF["5m"], 0, 50)
    assert rates is not None and len(rates) > 0, f"no rates, last_error={mt5.last_error()!r}"
    df = pd.DataFrame(rates)
    assert {"time", "open", "high", "low", "close", "tick_volume"} <= set(df.columns)
    last = pd.to_datetime(int(df["time"].iloc[-1]), unit="s", utc=True)
    return f"{len(df)} M5 bars, last {last:%Y-%m-%d %H:%M} close={df['close'].iloc[-1]}"


def _positions():
    pos = mt5.positions_get()
    assert pos is not None, f"None, last_error={mt5.last_error()!r}"
    if pos:
        p = pos[0]
        _ = p._asdict(), p.ticket, p.magic, p.sl, p.type
    return f"{len(pos)} open (magic 234000: {sum(1 for p in pos if p.magic == 234000)})"


def _deals():
    to = datetime.now(timezone.utc)
    deals = mt5.history_deals_get(to - timedelta(days=7), to)
    assert deals is not None, f"None, last_error={mt5.last_error()!r}"
    if deals:
        d = deals[-1]
        _ = d._asdict(), d.profit, getattr(d, "position_id", None), d.entry
    return f"{len(deals)} deals in last 7 days"


check("initialize", _initialize)
check("account_info", _account_info)
check("symbols_get", _symbols_get)
check("copy_rates_from_pos", _copy_rates)
check("positions_get", _positions)
check("history_deals_get", _deals)

print(f"\n{'ALL PASSED' if not failures else f'{failures} FAILED'} (no orders sent)")
sys.exit(1 if failures else 0)
