"""
Phase 0 — Step 3: aggregate raw ticks into OHLCV candles (Kronos fine-tune format).

Reads research/data/ticks/{SYMBOL}/*.csv.gz (columns: epoch,price), groups ticks
into time-bucket candles (M1=60s, M5=300s, ...) and writes one Kronos-format CSV
per timeframe:

    timestamps,open,close,high,low,volume,amount

(volume/amount = 0 for synthetic indices — not meaningful.) Buckets are emitted
in chronological order. With --fill-gaps (default) any missing bucket is
forward-filled from the previous close so the series is contiguous — required by
Kronos's tokenizer. Pure Python (no pandas) so it runs on any Python, incl. 3.14.

Re-running after more ticks are collected just regenerates from whatever day
files are present.

Examples
  ./venv/bin/python -m research.ticks_to_ohlcv --symbol R_75
  ./venv/bin/python -m research.ticks_to_ohlcv --symbol R_75 --tf M1 M5 --no-fill-gaps
"""
import argparse
import csv
import gzip
import sys
from datetime import datetime, timezone
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
TICKS_DIR = ROOT / "data" / "ticks"
OHLCV_DIR = ROOT / "data" / "ohlcv"

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}

# Kronos finetune_csv column order (note: close comes before high/low).
HEADER = ["timestamps", "open", "close", "high", "low", "volume", "amount"]


def load_day_ticks(path: Path) -> dict:
    """Return {epoch: price} for one day file (dedupes on epoch)."""
    ticks = {}
    with gzip.open(path, "rt") as f:
        for row in csv.reader(f):
            if not row:
                continue
            try:
                epoch = int(row[0])
            except ValueError:
                continue  # header
            ticks[epoch] = float(row[1])
    return ticks


def bucketize(ticks: dict, tf: int):
    """Group {epoch: price} into ordered buckets -> {bucket_epoch: [prices] in time order}."""
    buckets = {}
    for epoch, price in ticks.items():
        b = (epoch // tf) * tf
        buckets.setdefault(b, []).append((epoch, price))
    out = {}
    for b, items in buckets.items():
        items.sort()
        out[b] = [p for _, p in items]
    return out


def fmt_ts(bucket_epoch: int) -> str:
    return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def build(symbol: str, tf_name: str, fill_gaps: bool):
    tf = TF_SECONDS[tf_name]
    day_files = sorted((TICKS_DIR / symbol).glob("*.csv.gz"))
    if not day_files:
        print(f"✗ no tick files for {symbol}")
        return 0, 0

    out_path = OHLCV_DIR / symbol / f"{tf_name}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    candle_count = 0
    gap_count = 0
    last_close = None
    next_expected = None

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for day_file in day_files:
            ticks = load_day_ticks(day_file)
            if not ticks:
                continue
            buckets = bucketize(ticks, tf)
            for b in sorted(buckets):
                prices = buckets[b]
                # gap-fill between previous candle and this bucket
                if fill_gaps and last_close is not None and next_expected is not None:
                    while b > next_expected:
                        w.writerow([fmt_ts(next_expected), last_close, last_close,
                                    last_close, last_close, 0, 0])
                        gap_count += 1
                        candle_count += 1
                        next_expected += tf
                o, c = prices[0], prices[-1]
                h = max(prices)
                lo = min(prices)
                w.writerow([fmt_ts(b), o, c, h, lo, 0, 0])
                candle_count += 1
                last_close = c
                next_expected = b + tf

    return candle_count, gap_count


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="R_75")
    p.add_argument("--tf", nargs="+", default=["M1", "M5"], choices=list(TF_SECONDS))
    p.add_argument("--fill-gaps", dest="fill_gaps", action="store_true", default=True)
    p.add_argument("--no-fill-gaps", dest="fill_gaps", action="store_false")
    args = p.parse_args()

    for tf_name in args.tf:
        candles, gaps = build(args.symbol, tf_name, args.fill_gaps)
        gaps_note = f", {gaps} gap-filled" if gaps else ""
        print(f"✓ {args.symbol} {tf_name}: {candles} candles{gaps_note} → "
              f"{OHLCV_DIR / args.symbol / f'{tf_name}.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
