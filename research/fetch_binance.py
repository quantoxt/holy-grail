"""
Fetch historical OHLCV from Binance public API (no auth) into the Kronos CSV
format. Used to validate pre-trained Kronos on a LIVE market.

  python -m research.fetch_binance                       # BTCUSDT 5m, 6 months
  python -m research.fetch_binance --symbol ETHUSDT --months 12 --interval 1h
"""
import argparse
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.binance.com/api/v3/klines"


def fetch(symbol, interval, months):
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - int(months * 30.44 * 86400 * 1000)
    rows, cur = [], start_ms
    while cur < end_ms:
        url = f"{BASE}?symbol={symbol}&interval={interval}&startTime={cur}&limit=1000"
        with urllib.request.urlopen(url, timeout=20) as r:
            kl = json.loads(r.read())
        if not kl:
            break
        rows.extend(kl)
        cur = kl[-1][0] + 1
        if len(kl) < 1000:
            break
        time.sleep(0.15)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--interval", default="5m")
    p.add_argument("--months", type=float, default=6)
    args = p.parse_args()

    print(f"fetching {args.symbol} {args.interval} (~{args.months} months) from Binance…")
    rows = fetch(args.symbol, args.interval, args.months)
    out = ROOT / "data" / "ohlcv" / args.symbol / f"{args.interval}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamps", "open", "close", "high", "low", "volume", "amount"])
        for k in rows:
            ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            w.writerow([ts, k[1], k[4], k[2], k[3], k[5], k[7]])  # o,c,h,l,vol,quoteVol
    print(f"saved {len(rows)} candles -> {out}")
    print(f"span: {rows[0][0]} -> {rows[-1][0]} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
