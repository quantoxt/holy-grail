"""BinanceProvider — Binance USD-M futures at 1x (the crypto MarketProvider).

Implements MarketProvider via ccxt (binanceusdm). Supports long AND short.
Paper mode (settings.paper) uses the Binance Futures TESTNET (set_sandbox_mode);
live uses mainnet. Needs BINANCE_API_KEY/SECRET — testnet keys from
testnet.binancefuture.com for paper (get_candles is public and works without keys).

Symbol convention: config uses broker style (BTCUSDT); ccxt uses BTC/USDT.
"""
import ccxt.async_support as ccxt
import pandas as pd

from providers.base import MarketProvider
from shared.config import settings


def _to_ccxt(symbol: str) -> str:
    """BTCUSDT -> BTC/USDT (ccxt convention)."""
    return symbol[:-4] + "/" + symbol[-4:] if symbol.endswith("USDT") else symbol


class BinanceProvider(MarketProvider):
    name = "binance"

    def __init__(self):
        self.ex = ccxt.binanceusdm({
            "apiKey": settings.binance_api_key,
            "secret": settings.binance_api_secret,
            "enableRateLimit": True,
        })
        if settings.paper:
            self.ex.set_sandbox_mode(True)   # route to futures testnet
        self._leverage_set: set = set()

    async def _ensure_1x(self, symbol: str):
        if symbol not in self._leverage_set:
            try:
                await self.ex.set_leverage(1, _to_ccxt(symbol))
            except Exception:
                pass  # already set or testnet quirk — non-fatal
            self._leverage_set.add(symbol)

    async def get_candles(self, symbol, timeframe, limit):
        ohlcv = await self.ex.fetch_ohlcv(_to_ccxt(symbol), timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["epoch", "open", "high", "low", "close", "volume"])
        df["timestamps"] = pd.to_datetime(df["epoch"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M")
        df["amount"] = 0.0
        return df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]

    async def open_position(self, symbol, direction, size, sl=None, tp=None):
        """size = USDT notional at 1x. Returns a position dict."""
        sym = _to_ccxt(symbol)
        await self._ensure_1x(symbol)
        price = (await self.ex.fetch_ticker(sym))["last"]
        amount = float(self.ex.amount_to_precision(sym, size / price))
        side = "buy" if direction == "BUY" else "sell"
        order = await self.ex.create_market_order(sym, side, amount)
        return {"id": symbol, "symbol": symbol, "direction": direction,
                "entry_price": price, "size": size, "contracts": amount, "order_id": order["id"]}

    async def close_position(self, position_id):
        """At 1x there is one position per symbol; position_id is the symbol.
        Close with an opposite reduce-only market order."""
        sym = _to_ccxt(position_id)
        positions = await self.ex.fetch_positions([sym])
        pos = next((p for p in positions if abs(float(p.get("contracts") or 0)) > 0), None)
        if not pos:
            return {"id": position_id, "status": "no_open_position"}
        amt = abs(float(pos["contracts"]))
        side = "sell" if pos["side"] == "long" else "buy"
        await self.ex.create_market_order(sym, side, amt, {"reduceOnly": True})
        return {"id": position_id, "status": "closed", "exit_price": pos.get("markPrice")}

    async def get_balance(self):
        bal = await self.ex.fetch_balance()
        usdt = bal.get("USDT", {})
        return {"balance": float(usdt.get("total", 0) or 0), "currency": "USDT",
                "equity": float(usdt.get("total", 0) or 0)}

    async def get_open_positions(self, symbol=None):
        syms = [_to_ccxt(symbol)] if symbol else None
        positions = await self.ex.fetch_positions(syms)
        return [{"symbol": p["symbol"], "side": p["side"],
                 "contracts": float(p.get("contracts") or 0),
                 "entry_price": p.get("entryPrice")} for p in positions
                if abs(float(p.get("contracts") or 0)) > 0]
