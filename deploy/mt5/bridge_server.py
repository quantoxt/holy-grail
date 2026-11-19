"""MT5 RPyC bridge server — runs under WINE Python (3.9) next to the terminal.

Counterpart of providers/mt5_bridge.py. Exposes ONLY an allow-list of MetaTrader5
functions (not rpyc "classic" mode, which hands any client a remote Python shell).
Args/results travel as tuples of primitives:
  ("__nt__", typename, fields, values)  namedtuple (AccountInfo, TradePosition, ...)
  ("__np__", dtype_descr, rows)         numpy structured array (copy_rates_*)
  ("__seq__", items)                    tuple/list
  ("__dict__", pairs)                   dict   (order_send request)
  ("__dt__", epoch_seconds)             datetime (UTC)

Keep this file Python 3.9-compatible.
"""
import datetime
import sys
import threading

import MetaTrader5 as mt5
import rpyc
from rpyc.utils.server import ThreadedServer

ALLOWED = {
    "initialize", "login", "shutdown", "version", "last_error",
    "account_info", "terminal_info",
    "symbols_total", "symbols_get", "symbol_info", "symbol_info_tick", "symbol_select",
    "copy_rates_from", "copy_rates_from_pos", "copy_rates_range",
    "copy_ticks_from", "copy_ticks_range",
    "orders_total", "orders_get", "order_calc_margin", "order_calc_profit",
    "order_check", "order_send",
    "positions_total", "positions_get",
    "history_orders_total", "history_orders_get",
    "history_deals_total", "history_deals_get",
}

# MetaTrader5 is a single IPC channel to one terminal: serialise every call
# (the bot, the smoke test and the watchdog may connect at the same time).
_MT5_LOCK = threading.Lock()


def _plain(v):
    if v is None or isinstance(v, (bool, int, float, str, bytes)):
        return v
    if hasattr(v, "_asdict"):   # MetaTrader5 result structs (namedtuple-like)
        d = v._asdict()
        return ("__nt__", type(v).__name__, tuple(d.keys()), tuple(_plain(x) for x in d.values()))
    if hasattr(v, "dtype") and getattr(v.dtype, "names", None):   # structured ndarray
        return ("__np__", tuple((n, t) for n, t in v.dtype.descr),
                tuple(tuple(r) for r in v.tolist()))
    if hasattr(v, "item") and hasattr(v, "dtype"):                  # numpy scalar
        return v.item()
    if isinstance(v, (list, tuple)):
        return ("__seq__", tuple(_plain(x) for x in v))
    return str(v)


def _unplain(v):
    if not isinstance(v, tuple) or not v:
        return v
    tag = v[0]
    if tag == "__dt__":
        return datetime.datetime.fromtimestamp(v[1], datetime.timezone.utc)
    if tag == "__dict__":
        return {str(k): _unplain(x) for k, x in v[1]}
    if tag == "__seq__":
        return tuple(_unplain(x) for x in v[1])
    return v


class MT5Service(rpyc.Service):
    def exposed_ping(self):
        return True

    def exposed_constant(self, name):
        name = str(name)
        if not name.isupper():
            return None
        val = getattr(mt5, name, None)
        return val if isinstance(val, int) else None

    def exposed_call(self, name, args, kwargs):
        name = str(name)
        if name not in ALLOWED:
            raise ValueError("mt5 function not allowed: %s" % name)
        a = tuple(_unplain(x) for x in args)
        kw = {str(k): _unplain(x) for k, x in kwargs}
        fn = getattr(mt5, name)
        with _MT5_LOCK:
            # Never pass an empty **kw: MetaTrader5's C functions treat a non-NULL
            # (even empty) kwargs dict as named-args mode and reject the positional
            # request dict of order_send/order_check with (-2, 'Unnamed arguments
            # not allowed') — every order failed with retcode None.
            res = fn(*a, **kw) if kw else fn(*a)
        return _plain(res)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18812
    print("[bridge] MetaTrader5 %s, rpyc %s, listening on 0.0.0.0:%d"
          % (getattr(mt5, "__version__", "?"), rpyc.__version__, port), flush=True)
    ThreadedServer(
        MT5Service, hostname="0.0.0.0", port=port, reuse_addr=True,
        protocol_config={"allow_public_attrs": False, "allow_pickle": False,
                         "sync_request_timeout": 120},
    ).start()
