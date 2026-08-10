"""Preferred trading universe — the curated symbol list the bot may trade.

KEPT IN SYNC with frontend/src/views/Config.vue (PREFERRED_SYMBOLS). The bot checks
each against broker availability (mt5.symbol_info, NOT Market Watch visibility) and
silently skips any the logged-in broker doesn't offer.
"""
PREFERRED_SYMBOLS = [
    "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD",                                  # metals
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY",                                            # forex
    "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "SOLUSD",                        # crypto-CFD
]
