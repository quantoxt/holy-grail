"""MT5Provider — forex/metals/crypto-CFD via MetaTrader5 (single broker).

Implements MarketProvider. REQUIRES the MetaTrader5 terminal running (Windows
native) + the `MetaTrader5` Python package — so it CANNOT be imported/tested on a
plain Linux box. Deploy on the Windows VPS where the terminal runs. The active
account comes from Supabase `mt5_accounts` (is_active=true) — the single source of
truth, swappable live from the dashboard. If none is configured, it binds the
already-running terminal session.

Size is USDT/USD notional at the interface; converted to LOTS per the symbol's
contract size (e.g. 100 oz gold, 100k base forex).
"""
import MetaTrader5 as mt5  # noqa: E402  (Windows/Wine + terminal required)
import pandas as pd
import threading
import time

from providers.base import MarketProvider
from shared.mt5_accounts import get_account, fetch_active_account

_TF = {
    "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
    "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1,
}

MAGIC = 234000   # every order the bot opens is tagged with this so it only ever
                 # manages ITS OWN positions (never a manual trade on the account)


class MT5Provider(MarketProvider):
    name = "mt5"

    def __init__(self, account: str | None = None):
        self._symbols: set[str] | None = None   # broker-discovered symbol cache
        self._symindex: list[str] | None = None  # full broker symbol list (for resolution)
        self._symap: dict[str, str | None] = {}  # friendly/base -> broker-exact name cache
        self._failed_login: int | None = None   # login we tried & failed — don't hammer it
        self._connect(account)
        self._watched_account = self.account_name

    # --- symbol resolution (brokers name the same instrument differently) ---
    def _load_symbol_index(self, force: bool = False):
        """Load the broker's full symbol list once (364 on Headway). Used to resolve
        friendly names like 'EURUSD' to the broker's exact 'EURUSD.' / 'EURUSD.r'."""
        if self._symindex is not None and not force:
            return
        try:
            self._symindex = sorted(s.name for s in (mt5.symbols_get() or []))
            self._symap = {}   # invalidate the friendly->broker cache on reload
        except Exception:
            self._symindex = self._symindex or []

    def _broker_symbol(self, base: str) -> str | None:
        """Map a friendly/base symbol ('EURUSD') to the broker's exact name
        ('EURUSD.' on Headway, 'EURUSD' on MetaQuotes-Demo). Exact match first, then
        prefix match (shortest suffix wins — 'EURUSD.' over 'EURUSD.raw'). None if
        the broker doesn't offer it. Cached per base."""
        self._load_symbol_index()
        if base in self._symap:
            return self._symap[base]
        if base in self._symindex:
            self._symap[base] = base
            return base
        pref = [s for s in self._symindex if s.startswith(base)]
        if pref:
            chosen = min(pref, key=len)   # nearest name (fewest extra chars)
            self._symap[base] = chosen
            return chosen
        self._symap[base] = None
        return None

    @staticmethod
    def _base_symbol(broker_name: str) -> str:
        """Inverse: broker-exact 'EURUSD.' -> base 'EURUSD' (strip suffix after a dot,
        which is how most brokers suffix variants: . , .r, .raw, _)."""
        return broker_name.split(".")[0].split("_")[0] if broker_name else broker_name

    def _init_timed(self, creds: dict, timeout: float = 40.0) -> bool:
        """mt5.initialize() is a BLOCKING C call that can hang for minutes on an
        unreachable server (and wedge the terminal). Run shutdown+initialize on a
        worker thread with a hard timeout so a bad account can't freeze the bot."""
        done = threading.Event()
        box = {"ok": False}

        def go():
            try:
                mt5.shutdown()
            except Exception:
                pass
            try:
                box["ok"] = bool(mt5.initialize(**creds))
            except Exception:
                box["ok"] = False
            finally:
                done.set()

        t = threading.Thread(target=go, daemon=True)
        t.start()
        if done.wait(timeout):
            return box["ok"]
        return False   # timed out — worker is abandoned (daemon); we proceed

    def _account_info(self, tries: int = 15, delay: float = 1.0):
        """account_info() returns None right after initialize/while the terminal is
        switching accounts (logging in takes a few seconds). Retry briefly. Returns
        None if the account still isn't up — callers must tolerate that (never crash)."""
        for _ in range(tries):
            try:
                info = mt5.account_info()
            except Exception:
                info = None
            if info is not None:
                return info
            time.sleep(delay)
        return None

    def _connect(self, account: str | None = None):
        """Connect MT5. ALWAYS binds the running terminal first (fast + safe, can't
        wedge startup), then — if a DIFFERENT account is active in Supabase and not
        known-bad — attempts a timed swap to it. A bad/unreachable account times out
        and the bot stays on the terminal instead of hanging or crashing. Tolerates
        account_info() returning None (terminal mid-login/switch)."""
        # 1) terminal bind first — guarantees a working connection
        if not self._init_timed({}, timeout=30):
            raise RuntimeError("MT5 terminal bind failed (IPC timeout) — the terminal "
                               "needs restarting")
        info = self._account_info()
        self._login = info.login if info else None
        self.account_name = account or "terminal"
        # 2) timed swap to the configured active account, if different & not known-bad
        acct = get_account(account)
        if not (acct and acct.get("login") and acct.get("password") and acct.get("server")):
            return
        try:
            desired = int(acct["login"])
        except Exception:
            return
        if desired == self._login or desired == self._failed_login:
            return
        if self._init_timed({"login": desired, "password": acct["password"],
                             "server": acct["server"]}, timeout=40):
            info = self._account_info()
            if info:
                self._login = info.login
                self.account_name = acct.get("name") or "active"
                self._failed_login = None
        else:
            print(f"[MT5] swap to {desired} ({acct.get('server')}) failed/timed out — "
                  f"staying on terminal login {self._login}", flush=True)
            self._failed_login = desired

    def check_account_switch(self) -> bool:
        """True if the Supabase active account differs from the one we're on AND
        isn't a login we already failed to initialize (so we don't retry a known-
        bad account every 5s). Never raises."""
        desired = fetch_active_account()
        if not desired:
            return False
        try:
            desired_login = int(desired["login"])
        except Exception:
            return False
        if desired_login == self._login:
            return False
        if self._failed_login is not None and desired_login == self._failed_login:
            return False
        return True

    def reconnect(self):
        """Hot-swap to the currently active account."""
        self._connect(None)  # reconnect with whatever is active now

    def shutdown(self):
        """Release the MT5 terminal connection on bot exit."""
        try:
            mt5.shutdown()
        except Exception:
            pass

    # --- broker symbol availability (single broker: forex/metals/crypto-CFD) ---
    def discover_symbols(self, force: bool = False) -> list[str]:
        """Which PREFERRED symbols this broker actually offers, resolved through the
        broker's naming (e.g. 'EURUSD' matches Headway's 'EURUSD.'). Cached; force=True
        to refresh the index (telemetry does this periodically)."""
        if self._symbols is None or force:
            from shared.symbols import PREFERRED_SYMBOLS
            self._load_symbol_index(force=force)
            self._symbols = {s for s in PREFERRED_SYMBOLS if self._broker_symbol(s) is not None}
        return sorted(self._symbols)

    def is_offered(self, symbol: str) -> bool:
        """True if the broker offers `symbol` under any naming variant."""
        return self._broker_symbol(symbol) is not None

    # --- data ---
    async def get_candles(self, symbol, timeframe, limit):
        b = self._broker_symbol(symbol) or symbol
        rates = mt5.copy_rates_from_pos(b, _TF.get(timeframe, mt5.TIMEFRAME_M5), 0, limit)
        df = pd.DataFrame(rates)
        df["timestamps"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M")
        df["volume"] = df.get("tick_volume", 0)
        df["amount"] = 0.0
        return df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]

    # --- sizing: USDT notional -> lots ---
    def _lots(self, symbol, notional_usd):
        b = self._broker_symbol(symbol) or symbol
        info = mt5.symbol_info(b)
        price = mt5.symbol_info_tick(b).ask
        lots = notional_usd / (info.trade_contract_size * price)
        return max(info.volume_min, round(lots / info.volume_step) * info.volume_step)

    # --- execution ---
    async def open_position(self, symbol, direction, size, sl=None, tp=None):
        b = self._broker_symbol(symbol) or symbol   # orders must use the broker-exact name
        info = mt5.symbol_info(b)
        if not info.visible:
            mt5.symbol_select(b, True)
        lots = self._lots(symbol, size)
        tick = mt5.symbol_info_tick(b)
        price = tick.ask if direction == "BUY" else tick.bid
        order = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": b, "volume": lots,
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price, "deviation": 20, "magic": MAGIC, "comment": "holygrail",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl:
            order["sl"] = sl
        if tp:
            order["tp"] = tp
        res = mt5.order_send(order)
        ok = res and res.retcode == mt5.TRADE_RETCODE_DONE
        return {"id": res.order if res else None, "symbol": symbol, "direction": direction,
                "entry_price": price, "size": size, "lots": lots, "ok": ok,
                "retcode": res.retcode if res else None}

    def get_spread(self, symbol) -> float:
        """Current spread in PRICE (ask - bid). 0 if unavailable."""
        try:
            t = mt5.symbol_info_tick(self._broker_symbol(symbol) or symbol)
            return (t.ask - t.bid) if t else 0.0
        except Exception:
            return 0.0

    def last_price(self, symbol) -> tuple[float, float] | None:
        """(bid, ask) or None."""
        try:
            t = mt5.symbol_info_tick(self._broker_symbol(symbol) or symbol)
            return (t.bid, t.ask) if t else None
        except Exception:
            return None

    def get_closed_deal(self, position_ticket):
        """Realized outcome of a CLOSED position (SL hit between ticks, manual
        close, crash mid-close) from the deal history — {pnl, price, time} or
        None if not found / history unavailable. Lets the loop log closes for
        positions it didn't close itself, so trades never stick at 'open'."""
        try:
            from datetime import datetime, timezone, timedelta
            to = datetime.now(timezone.utc)
            frm = to - timedelta(days=7)
            deals = mt5.history_deals_get(frm, to)
            for d in (deals or []):
                if (getattr(d, "position", 0) == position_ticket
                        and getattr(d, "entry", -1) == mt5.DEAL_ENTRY_OUT):
                    return {"pnl": float(d.profit), "price": float(d.price),
                            "time": int(getattr(d, "time", 0))}
        except Exception:
            return None
        return None

    def modify_sl(self, position_ticket, new_sl) -> bool:
        """Tighten a position's stop-loss (breakeven trail). Returns True on success."""
        try:
            pos = mt5.positions_get(ticket=position_ticket)
            if not pos:
                return False
            p = pos[0]
            order = {"action": mt5.TRADE_ACTION_SLTP, "symbol": p.symbol,
                     "position": position_ticket, "sl": new_sl, "tp": p.tp}
            res = mt5.order_send(order)
            return bool(res and res.retcode == mt5.TRADE_RETCODE_DONE)
        except Exception:
            return False

    async def close_position(self, position_id):
        pos = mt5.positions_get(ticket=position_id)
        if not pos:
            return {"id": position_id, "status": "no_position"}
        p = pos[0]
        tick = mt5.symbol_info_tick(p.symbol)
        price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
        order = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
            "type": mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": position_id, "price": price, "deviation": 20, "magic": 234000,
            "comment": "holygrail-close", "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(order)
        ok = res and res.retcode == mt5.TRADE_RETCODE_DONE
        return {"id": position_id, "status": "closed" if ok else "failed",
                "retcode": res.retcode if res else None}

    # --- account ---
    async def get_balance(self):
        info = mt5.account_info()
        return {"balance": info.balance, "currency": info.currency, "equity": info.equity}

    async def get_open_positions(self, symbol=None, magic=MAGIC):
        """Open positions, by default filtered to OUR magic (the bot only ever
        manages its own trades — never a manual position on the account). Includes
        sl + open time so the loop can reconcile after a restart and manage exits."""
        positions = mt5.positions_get(symbol) if symbol else mt5.positions_get()
        out = []
        for p in (positions or []):
            if magic is not None and getattr(p, "magic", 0) != magic:
                continue
            out.append({"ticket": p.ticket, "symbol": self._base_symbol(p.symbol),
                        "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                        "volume": p.volume, "entry": p.price_open,
                        "price_current": p.price_current,
                        "profit": p.profit,        # floating PnL (account currency)
                        "sl": p.sl, "time": p.time})
        return out

    async def account_summary(self) -> dict:
        """Full live account snapshot for the dashboard heartbeat. Raises if the
        terminal has no active account (e.g. mid-switch) — telemetry catches it."""
        info = self._account_info()
        if info is None:
            raise RuntimeError("no active MT5 account (terminal not logged in)")
        return {"login": info.login, "broker": getattr(info, "company", "") or "",
                "balance": info.balance, "equity": info.equity,
                "currency": info.currency}

    async def get_symbol_info(self, symbol: str) -> dict:
        """Live contract specs from MT5 — accurate per broker."""
        b = self._broker_symbol(symbol) or symbol
        info = mt5.symbol_info(b)
        if info is None:
            mt5.symbol_select(b, True)
            info = mt5.symbol_info(b)
        if info is None:
            return {"contract_size": 1.0, "volume_min": 0.01, "volume_step": 0.01}
        return {
            "contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_step": info.volume_step,
            "point_size": info.point,
        }
