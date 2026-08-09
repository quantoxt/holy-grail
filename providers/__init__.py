"""Provider factory — returns the concrete MarketProvider.

Single broker: all instruments (forex, metals, crypto-CFD) trade through one
logged-in MT5 account. The old crypto/Binance split is gone — the broker offers
crypto as CFDs (BTCUSD etc.), so one MT5 account covers everything. Symbols are
auto-discovered from the broker (mt5.symbols_get) and curated at runtime.
"""
from providers.base import MarketProvider  # noqa: F401


def get_provider(account: str | None = None) -> "MarketProvider":
    """Return the MT5 provider. `account` selects a named MT5 account from
    Supabase `mt5_accounts`; None uses the active (is_active=true) account.

    Imports lazily so this package imports cleanly on Linux where the
    Windows-only `MetaTrader5` package is absent.
    """
    from providers.mt5 import MT5Provider
    return MT5Provider(account=account)
