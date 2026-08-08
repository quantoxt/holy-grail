"""MarketProvider — the seam between the bot and any market.

The Soldier/Watcher/Sentinel call this interface; they never touch MT5 directly.
Single broker: the concrete provider is MT5Provider (forex, metals, crypto-CFD
all via one logged-in MT5 account). Live trading is position-based (open a
long/short, hold ~h=24 candles, close) — so the interface is position-oriented,
not tick-contract.
"""
from abc import ABC, abstractmethod

import pandas as pd


class MarketProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def get_candles(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Recent OHLCV. Columns: timestamps, open, high, low, close, volume, amount."""

    @abstractmethod
    async def open_position(self, symbol: str, direction: str, size: float,
                            sl: float | None = None, tp: float | None = None) -> dict:
        """Open long/short. direction: 'BUY'|'SELL'. Returns {id, entry_price, size, ...}."""

    @abstractmethod
    async def close_position(self, position_id) -> dict:
        """Close a position. Returns {id, exit_price, pnl, ...}."""

    @abstractmethod
    async def get_balance(self) -> dict:
        """Returns {balance, currency, equity}."""

    @abstractmethod
    async def get_open_positions(self, symbol: str | None = None) -> list:
        """Currently open positions."""

    async def get_symbol_info(self, symbol: str) -> dict:
        """Contract specs for lot sizing: {contract_size, volume_min, volume_step}.
        Providers override with live values; default is a safe fallback."""
        return {"contract_size": 1.0, "volume_min": 0.01, "volume_step": 0.01}
