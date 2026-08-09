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

from providers.base import MarketProvider
from shared.mt5_accounts import get_account, fetch_active_account

_TF = {
    "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
    "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1,
}


class MT5Provider(MarketProvider):
    name = "mt5"

    def __init__(self, account: str | None = None):
        self._symbols: set[str] | None = None   # broker-discovered symbol cache
        self._failed_login: int | None = None   # login we tried & failed — don't hammer it
        self._connect(account)
        self._watched_account = self.account_name

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

    def _connect(self, account: str | None = None):
        """Connect MT5. ALWAYS binds the running terminal first (fast + safe, can't
        wedge startup), then — if a DIFFERENT account is active in Supabase and not
        known-bad — attempts a timed swap to it. A bad/unreachable account times out
        and the bot stays on the terminal instead of hanging or crashing."""
        # 1) terminal bind first — guarantees a working connection
        if not self._init_timed({}, timeout=30):
            raise RuntimeError("MT5 terminal bind failed (IPC timeout) — the terminal "
                               "needs restarting")
        self._login = mt5.account_info().login
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
            self._login = mt5.account_info().login
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

    # --- broker symbol discovery (single broker: forex/metals/crypto-CFD) ---
    def discover_symbols(self, force: bool = False) -> list[str]:
        """Tradeable symbol names offered by this broker (visible in Market Watch).
        Cached on the provider; pass force=True to refresh (the telemetry task
        does this periodically). Used by the loop to skip active_symbols the
        logged-in broker doesn't actually offer (e.g. BTCUSD on a forex-only account)."""
        if self._symbols is None or force:
            try:
                all_syms = mt5.symbols_get() or []
                self._symbols = {s.name for s in all_syms if s.visible}
            except Exception:
                # keep whatever cache we have; empty-set on first failure
                self._symbols = self._symbols or set()
        return sorted(self._symbols)

    def is_offered(self, symbol: str) -> bool:
        """True if the broker offers `symbol`. Lazily fills the cache once."""
        if self._symbols is None:
            self.discover_symbols()
        return symbol in (self._symbols or set())

    # --- data ---
    async def get_candles(self, symbol, timeframe, limit):
        rates = mt5.copy_rates_from_pos(symbol, _TF.get(timeframe, mt5.TIMEFRAME_M5), 0, limit)
        df = pd.DataFrame(rates)
        df["timestamps"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M")
        df["volume"] = df.get("tick_volume", 0)
        df["amount"] = 0.0
        return df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]

    # --- sizing: USDT notional -> lots ---
    def _lots(self, symbol, notional_usd):
        info = mt5.symbol_info(symbol)
        price = mt5.symbol_info_tick(symbol).ask
        lots = notional_usd / (info.trade_contract_size * price)
        return max(info.volume_min, round(lots / info.volume_step) * info.volume_step)

    # --- execution ---
    async def open_position(self, symbol, direction, size, sl=None, tp=None):
        info = mt5.symbol_info(symbol)
        if not info.visible:
            mt5.symbol_select(symbol, True)
        lots = self._lots(symbol, size)
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if direction == "BUY" else tick.bid
        order = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lots,
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price, "deviation": 20, "magic": 234000, "comment": "holygrail",
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

    async def get_open_positions(self, symbol=None):
        positions = mt5.positions_get(symbol) if symbol else mt5.positions_get()
        return [{"ticket": p.ticket, "symbol": p.symbol,
                 "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                 "volume": p.volume, "entry": p.price_open,
                 "price_current": p.price_current,
                 "profit": p.profit} for p in (positions or [])]   # profit = floating PnL (acct ccy)

    async def account_summary(self) -> dict:
        """Full live account snapshot for the dashboard heartbeat."""
        info = mt5.account_info()
        return {"login": info.login, "broker": getattr(info, "company", "") or "",
                "balance": info.balance, "equity": info.equity,
                "currency": info.currency}

    async def get_symbol_info(self, symbol: str) -> dict:
        """Live contract specs from MT5 — accurate per broker."""
        info = mt5.symbol_info(symbol)
        if info is None:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
        if info is None:
            return {"contract_size": 1.0, "volume_min": 0.01, "volume_step": 0.01}
        return {
            "contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_step": info.volume_step,
            "point_size": info.point,
        }
