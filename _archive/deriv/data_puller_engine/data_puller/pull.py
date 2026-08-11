"""
Data-puller engine — interactive pull of Deriv synthetic-index tick history.

Interactive (default): presents a menu to choose the symbol and the number of
days, then pulls until the requested range is complete. Pulled data lands under
this engine's own data/ folder, and pulls are resumable (re-run to extend).

Run from the repo root:
    ./venv/bin/python -m _engines.data_puller.pull                 # interactive
    ./venv/bin/python -m _engines.data_puller.pull --symbol R_75 --days 90
    ./venv/bin/python -m _engines.data_puller.pull --symbol R_75 --days 90 --resume
    ./venv/bin/python -m _engines.data_puller.pull --symbol R_75 --days 90 --dry-run
"""
import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from _engines.data_puller import symbols as syms
from _engines.data_puller.collector import collect, existing_summary

# This engine is the trusted writer of ticks -> shared project data root
# (not engine-local). Other engines may keep local data; this one feeds `data/`.
REPO_ROOT = Path(__file__).resolve().parents[2]   # _engines/data_puller/pull.py -> repo root
DATA_DIR = REPO_ROOT / "data" / "ticks"


def _fmt_date(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def prompt_symbol():
    print("\nDeriv synthetic indices:")
    for i, (code, name, vol) in enumerate(syms.SYNTHETICS, 1):
        print(f"  {i:>2}. {code:<9} {name:<26} vol: {vol}")
    while True:
        choice = input("\nPick a symbol (number or code, e.g. 4 or R_75): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(syms.SYNTHETICS):
            return syms.SYNTHETICS[int(choice) - 1][0]
        up = choice.upper()
        if up in syms.BY_CODE:
            return up
        print("  ✗ invalid — try again")


def prompt_int(label, default):
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if raw == "":
            return default
        if raw.isdigit() and int(raw) >= 1:
            return int(raw)
        print("  ✗ enter a positive whole number")


def parse_end(end_str):
    if not end_str:
        return int(time.time())
    return int(datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default=None, help="synthetic code (skip the menu)")
    p.add_argument("--days", type=int, default=None, help="days of history (skip the prompt)")
    p.add_argument("--end", default=None, help="end date YYYY-MM-DD UTC (default: today)")
    p.add_argument("--rate", type=float, default=0.4, help="seconds between requests")
    p.add_argument("--no-resume", dest="resume", action="store_false", default=True,
                   help="start fresh instead of extending existing data")
    p.add_argument("--dry-run", action="store_true", help="show the plan, don't pull")
    args = p.parse_args()

    print("╔══ Data Puller — Deriv synthetics ══╗")
    symbol = args.symbol or prompt_symbol()
    days = args.days or prompt_int("How many days of history?", 90)
    end_epoch = parse_end(args.end)
    start_epoch = end_epoch - days * 86400

    info = existing_summary(symbol, DATA_DIR)
    resume = args.resume and info is not None
    print(f"\n  symbol : {symbol}  ({syms.BY_CODE[symbol][1]})")
    print(f"  days   : {days}  ({_fmt_date(start_epoch)} ← {_fmt_date(end_epoch)})")
    print(f"  output : {DATA_DIR / symbol}")
    if info:
        print(f"  have   : {info['total']:,} ticks  ({info['oldest']} → {info['newest']})")
        print(f"  mode   : {'RESUME / extend' if resume else 'fresh (--no-resume)'}")
    else:
        print("  mode   : fresh")

    if args.dry_run:
        print("\n[dry-run] no data pulled.")
        return 0

    if input("\nProceed? [Y/n]: ").strip().lower() in ("n", "no"):
        print("aborted.")
        return 0

    print()
    result = asyncio.run(collect(symbol, start_epoch, end_epoch, str(DATA_DIR),
                                 rate=args.rate, resume=resume))

    print(f"\n╔══ done ══╗")
    print(f"  pulled : {result['total']:,} new ticks")
    print(f"  span   : {_fmt_date(result['oldest'])} → {_fmt_date(result['newest'])}")
    n_files = len([f for f in os.listdir(DATA_DIR / symbol) if f.endswith(".csv.gz")])
    print(f"  files  : {n_files} day files under {DATA_DIR / symbol}")
    print(f"  tip    : re-run with --resume to extend further back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
