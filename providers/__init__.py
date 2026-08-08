"""Provider factory — returns the concrete MarketProvider for the active market_mode."""
from providers.base import MarketProvider  # noqa: F401


def get_provider(market_mode: str, account: str | None = None) -> "MarketProvider":
    """Return the provider for the active mode. Imports lazily so missing optional
    deps (e.g. MetaTrader5 on Linux) don't break importing this package.
    `account` selects a named MT5 account (ignored for crypto)."""
    if market_mode == "crypto":
        from providers.binance import BinanceProvider
        return BinanceProvider()
    if market_mode == "forex":
        from providers.mt5 import MT5Provider
        return MT5Provider(account=account)
    raise ValueError(f"unknown market_mode: {market_mode!r} (expected 'crypto' or 'forex')")
