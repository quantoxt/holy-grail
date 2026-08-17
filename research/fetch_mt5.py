"""Export historical candles from the MT5 terminal (Windows/VPS) for validation.

The validated instruments (XAUUSD, XAGUSD, GBPUSD) are broker CFDs — Binance
has no such feed, so the validation dataset must come from the terminal itself.
Attach to the already-running terminal (the bot keeps it logged in), pull ~2
years of M5 via chunked copy_rates_from_pos, and write the SAME CSV format as
research/fetch_binance.py so research/validate.py consumes it unchanged.

Run (on the VPS):
  C:\\holy-grail-venv\\Scripts\\python research\\fetch_mt5.py --years 2
"""
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 50_000   # per copy_rates_from_pos call


def resolve_symbol(name: str):
    """Exact match first, then broker-suffixed variants (e.g. 'XAUUSD.',
    'BTCUSD.m') — shortest suffixed name wins."""
    if mt5.symbol_info(name) is not None:
        return name
    cand = [s.name for s in (mt5.symbols_get() or [])
            if s.name.upper().startswith(name.upper())]
    if cand:
        return min(cand, key=len)
    return None


def fetch(symbol: str, years: float):
    start_pos = 0
    all_rows = []
    seen = set()
    cutoff = datetime.now(timezone.utc).timestamp() - years * 365.25 * 86400
    while True:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, start_pos, CHUNK)
        if rates is None or len(rates) == 0:
            break
        fresh = [r for r in rates if r["time"] not in seen]
        if not fresh:
            break
        for r in fresh:
            seen.add(r["time"])
        all_rows = list(fresh) + all_rows
        oldest = fresh[0]["time"]
        print(f"  {symbol}: {len(all_rows)} candles, oldest "
              f"{datetime.fromtimestamp(oldest, tz=timezone.utc):%Y-%m-%d}", flush=True)
        if oldest < cutoff or len(rates) < CHUNK:
            break
        start_pos += CHUNK
    return [r for r in all_rows if r["time"] >= cutoff]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["XAUUSD", "XAGUSD", "GBPUSD"])
    p.add_argument("--years", type=float, default=2.0)
    args = p.parse_args()

    if not mt5.initialize():
        print(f"mt5.initialize() failed: {mt5.last_error()}")
        return 1
    try:
        for name in args.symbols:
            sym = resolve_symbol(name)
            if sym is None:
                print(f"{name}: not offered by this broker — skipped")
                continue
            mt5.symbol_select(sym, True)
            rows = fetch(sym, args.years)
            out = ROOT / "data" / "ohlcv" / name / "5m.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["timestamps", "open", "close", "high", "low", "volume", "amount"])
                for r in rows:
                    ts = datetime.fromtimestamp(r["time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                    w.writerow([ts, r["open"], r["close"], r["high"], r["low"],
                                r["tick_volume"], r["tick_volume"] * r["close"]])
            print(f"saved {len(rows)} candles -> {out}", flush=True)
    finally:
        # NEVER mt5.shutdown() — the trading bot shares this terminal connection.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
