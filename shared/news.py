"""News calendar — ForexFactory economic events via free JSON feed.

Provides blackout windows around high-impact news so the Sentinel can pause
trading when the market is unpredictable. Fetches once per hour (cached).

Feed: https://nfs.faireconomy.media/ff_calendar_thisweek.json (free, no auth).
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_CACHE_TTL = 3600  # refresh hourly
_cache: dict = {"data": None, "fetched": 0}

# symbol → currencies whose news affects that symbol
SYMBOL_CURRENCIES = {
    "XAUUSD": ["USD"], "XAGUSD": ["USD"],
    "EURUSD": ["USD", "EUR"], "GBPUSD": ["USD", "GBP"],
    "USDJPY": ["USD", "JPY"], "AUDUSD": ["USD", "AUD"],
    "USDCAD": ["USD", "CAD"], "NZDUSD": ["USD", "NZD"],
    "BTCUSDT": ["USD"],  # macro events affect crypto
}


def _fetch() -> list:
    now = time.time()
    if _cache["data"] is not None and now - _cache["fetched"] < _CACHE_TTL:
        return _cache["data"]
    try:
        req = urllib.request.Request(FEED_URL, headers={"User-Agent": "HolyGrail-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            _cache["data"] = json.loads(r.read())
        _cache["fetched"] = now
    except Exception:
        pass
    return _cache["data"] or []


def _currencies_for(symbols: list) -> set:
    out = set()
    for sym in symbols:
        out.update(SYMBOL_CURRENCIES.get(sym, []))
    return out


def get_high_impact(symbols: list, now: datetime | None = None) -> list:
    """High-impact events relevant to the active symbols, sorted by time."""
    if now is None:
        now = datetime.now(timezone.utc)
    currencies = _currencies_for(symbols)
    events = []
    for e in _fetch():
        if e.get("impact") != "High":
            continue
        country = e.get("country", "")
        if country not in currencies and country != "All":
            continue
        try:
            t = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        except Exception:
            continue
        events.append({"title": e["title"], "currency": country, "time": t,
                       "forecast": e.get("forecast", ""), "previous": e.get("previous", "")})
    events.sort(key=lambda x: x["time"])
    return events


def is_blackout(symbols: list, pre_min: int = 30, post_min: int = 15,
                now: datetime | None = None) -> tuple[bool, str]:
    """Returns (in_blackout, reason). Pre-event: stop trading. Post-event: wait."""
    if now is None:
        now = datetime.now(timezone.utc)
    for e in get_high_impact(symbols, now):
        delta_min = (e["time"] - now).total_seconds() / 60
        if -post_min <= delta_min <= pre_min:
            if delta_min > 0:
                return True, f"pre_news:{e['title']}({e['currency']})+{delta_min:.0f}min"
            else:
                return True, f"post_news:{e['title']}({e['currency']}){-delta_min:.0f}min"
    return False, "ok"


def next_event(symbols: list, now: datetime | None = None) -> dict | None:
    """Next upcoming high-impact event (for dashboard)."""
    if now is None:
        now = datetime.now(timezone.utc)
    for e in get_high_impact(symbols, now):
        if e["time"] > now:
            return {"title": e["title"], "currency": e["currency"],
                    "time": e["time"].isoformat(),
                    "minutes_until": round((e["time"] - now).total_seconds() / 60),
                    "forecast": e["forecast"]}
    return None
