"""MT5Provider — forex/metals (XAUUSD, XAGUSD, forex) via MetaTrader5.

Implements MarketProvider. REQUIRES the MetaTrader5 terminal running (Windows
native, or Wine on Linux) + the `MetaTrader5` Python package — so it CANNOT be
imported/tested on a plain Linux box. Deploy on the Windows VPS where the
terminal runs. Connects to the active account in data/mt5_accounts.json (or a
named account via `account=`); multi-account + switchable.

Size is USDT/USD notional at the interface; converted to LOTS per the symbol's
contract size (e.g. 100 oz gold, 100k base forex).
"""
import MetaTrader5 as mt5  # noqa: E402  (Windows/Wine + terminal required)
import pandas as pd

from providers.base import MarketProvider
from shared.mt5_accounts import get_account

_TF = {
    "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
    "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4, "1d": mt5.TIMEFRAME_D1,
}


class MT5Provider(MarketProvider):
    name = "mt5"

    def __init__(self, account: str | None = None):
        self._connect(account)
        self._watched_account = self.account_name

    def _connect(self, account: str | None = None):
        """Initialize or re-initialize MT5 with the given account."""
        try:
            mt5.shutdown()
        except Exception:
            pass
        acct = get_account(account)
        if not mt5.initialize(login=acct["login"], password=acct["password"], server=acct["server"]):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error}")
        self.account_name = account or "active"
        self._login = acct["login"]

    def check_account_switch(self) -> bool:
        """Returns True if the active account changed (caller should reconnect)."""
        try:
            current = get_account(None)  # reads the active account
            return current.get("login") != self._login
        except Exception:
            return False

    def reconnect(self):
        """Hot-swap to the currently active account."""
        self._connect(None)  # reconnect with whatever is active now

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
                 "volume": p.volume, "entry": p.price_open} for p in (positions or [])]

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
