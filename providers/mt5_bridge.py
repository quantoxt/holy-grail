"""Linux-side MetaTrader5 stand-in: forwards calls over RPyC to the MT5 terminal
running under Wine (the `mt5` container, see deploy/mt5/bridge_server.py).

Why not the `mt5linux` client package:
  * mt5linux 1.1.x's MetaTrader5() constructor tries to START its own Docker
    container (needs a docker CLI inside the bot container) before connecting.
  * mt5linux 0.1.x pins 2021-era deps (cryptography 35, ...) and its
    history_deals_get(datetime, datetime) evaluates `datetime.datetime(...)` on a
    server that never imported datetime -> NameError.
  * Both use rpyc *classic* mode: anyone who reaches the port gets arbitrary code
    execution inside the terminal container.

This bridge instead talks to a tiny allow-listed rpyc Service. Arguments and results
cross the wire as plain tuples of primitives (rpyc passes those by value), and
results are rebuilt locally as real namedtuples / numpy arrays — so `._asdict()`,
attribute access (`info.balance`), `getattr(d, "fee", 0.0)`, iteration and
`pd.DataFrame(rates)` all behave exactly like the native Windows package. No
netref proxies ever leak into bot code.

Connection is lazy (first call), so `import providers.mt5` works with no server
running. A dropped connection (terminal container restarted) makes that one call
raise; the next call re-dials. Calls are never retried (order_send isn't idempotent).
"""
from __future__ import annotations

import collections
import os
import threading
from datetime import datetime, timezone

# MT5 enum values used by providers/mt5.py — needed at IMPORT time (module-level
# _TF dict) before any connection exists. Values are the official MetaTrader5
# constants (cross-checked against mt5linux constants.py). Anything not listed is
# fetched from the server on first use.
_LOCAL_CONSTANTS = {
    "TIMEFRAME_M1": 1, "TIMEFRAME_M5": 5, "TIMEFRAME_M15": 15,
    "TIMEFRAME_H1": 16385, "TIMEFRAME_H4": 16388, "TIMEFRAME_D1": 16408,
    "ORDER_FILLING_FOK": 0, "ORDER_FILLING_IOC": 1, "ORDER_FILLING_RETURN": 2,
    "TRADE_ACTION_DEAL": 1, "TRADE_ACTION_SLTP": 6,
    "ORDER_TYPE_BUY": 0, "ORDER_TYPE_SELL": 1, "ORDER_TIME_GTC": 0,
    "TRADE_RETCODE_DONE": 10009,
    "POSITION_TYPE_BUY": 0, "POSITION_TYPE_SELL": 1,
    "DEAL_ENTRY_IN": 0, "DEAL_ENTRY_OUT": 1,
}

_NT_CACHE: dict[tuple, type] = {}


def _encode(v):
    """Local arg -> wire form (tuples of primitives only)."""
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return ("__dt__", v.timestamp())
    if isinstance(v, dict):
        return ("__dict__", tuple((k, _encode(x)) for k, x in v.items()))
    if isinstance(v, (list, tuple)):
        return ("__seq__", tuple(_encode(x) for x in v))
    if hasattr(v, "item"):          # numpy scalar
        return v.item()
    return v


def _decode(v):
    """Wire form -> local namedtuple / ndarray / tuple / primitive."""
    if not isinstance(v, tuple) or not v:
        return v
    tag = v[0]
    if tag == "__nt__":
        _, name, fields, values = v
        key = (name, fields)
        cls = _NT_CACHE.get(key)
        if cls is None:
            cls = _NT_CACHE[key] = collections.namedtuple(name, fields)
        return cls(*(_decode(x) for x in values))
    if tag == "__np__":
        import numpy as np
        _, descr, rows = v
        return np.array([tuple(r) for r in rows], dtype=[(n, t) for n, t in descr])
    if tag == "__seq__":
        return tuple(_decode(x) for x in v[1])
    return v


class MT5Bridge:
    """Drop-in for the `MetaTrader5` module: `mt5.account_info()`, `mt5.TIMEFRAME_M5`, ..."""

    def __init__(self, host: str, port: int, timeout: float = 60.0):
        self._host, self._port, self._timeout = host, port, timeout
        self._conn = None
        self._lock = threading.Lock()
        self._consts = dict(_LOCAL_CONSTANTS)

    # --- connection ---
    def _connection(self):
        with self._lock:
            if self._conn is None or self._conn.closed:
                import rpyc
                self._conn = rpyc.connect(
                    self._host, self._port,
                    config={"sync_request_timeout": self._timeout,
                            "allow_public_attrs": False})
            return self._conn

    def _drop(self):
        with self._lock:
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _call(self, name: str, args: tuple, kwargs: dict):
        wire_args = tuple(_encode(a) for a in args)
        wire_kwargs = tuple((k, _encode(x)) for k, x in kwargs.items())
        conn = self._connection()   # (re)dials lazily; connect errors raise here
        try:
            return _decode(conn.root.call(name, wire_args, wire_kwargs))
        except (EOFError, ConnectionError, OSError):
            # Socket dropped / timed out (terminal container restarted). Never
            # retry here: order_send may already have executed server-side, and a
            # blind retry would double the position. The NEXT call redials.
            self._drop()
            raise

    # --- module-like surface ---
    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name.isupper():
            if name not in self._consts:
                val = self._connection().root.constant(name)
                if val is None:
                    raise AttributeError(f"MetaTrader5 has no constant {name}")
                self._consts[name] = val
            return self._consts[name]
        return lambda *a, **kw: self._call(name, a, kw)

    def ping(self) -> bool:
        try:
            return bool(self._connection().root.ping())
        except Exception:
            return False


def connect_from_env() -> MT5Bridge:
    """MT5_HOST / MT5_PORT (defaults: mt5:18812 — the compose service name)."""
    return MT5Bridge(os.environ.get("MT5_HOST", "mt5"),
                     int(os.environ.get("MT5_PORT", "18812")),
                     float(os.environ.get("MT5_TIMEOUT", "60")))
