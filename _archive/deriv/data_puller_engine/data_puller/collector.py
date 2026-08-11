"""Backward-paginating tick collector for the data-puller engine.

Pulls raw ticks via `ticks_history`, stores them append-safe + deduped as gzipped
CSV per UTC day, with a resume checkpoint. Proven against the live Options API
(1000 ticks/request cap, ~2s tick spacing on standard synthetics).

Storage:   <data_dir>/<SYMBOL>/<YYYY-MM-DD>.csv.gz   (columns: epoch,price)
Checkpoint:<data_dir>/<SYMBOL>/_checkpoint.json
"""
import asyncio
import csv
import gzip
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

from _engines.data_puller import deriv_ws

DEFAULT_BATCH = 1000   # new Options API caps ticks_history at 1000/request
DEFAULT_RATE_S = 0.4


class TickStore:
    """Append-safe, deduped gz-CSV store, one file per UTC day."""

    def __init__(self, symbol, data_dir):
        self.symbol = symbol
        self.dir = os.path.join(data_dir, symbol)
        os.makedirs(self.dir, exist_ok=True)
        self._seen = {}  # day -> set(epoch), lazily loaded

    def _path(self, day):
        return os.path.join(self.dir, f"{day}.csv.gz")

    def _load_seen(self, day):
        path = self._path(day)
        seen = set()
        if os.path.exists(path):
            with gzip.open(path, "rt") as f:
                for row in csv.reader(f):
                    if row:
                        try:
                            seen.add(int(row[0]))
                        except ValueError:
                            continue  # header / malformed
        self._seen[day] = seen
        return seen

    def write(self, times, prices) -> int:
        by_day = defaultdict(list)
        for epoch, price in zip(times, prices):
            day = datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d")
            by_day[day].append((int(epoch), price))

        added = 0
        for day, rows in by_day.items():
            seen = self._seen.get(day) or self._load_seen(day)
            fresh = [(e, p) for e, p in rows if e not in seen]
            if not fresh:
                continue
            path = self._path(day)
            new_file = not os.path.exists(path)
            with gzip.open(path, "at") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["epoch", "price"])
                for e, p in fresh:
                    w.writerow([e, p])
                    seen.add(e)
            added += len(fresh)
        return added


def _ckpt_path(symbol, data_dir):
    return os.path.join(data_dir, symbol, "_checkpoint.json")


def load_checkpoint(symbol, data_dir):
    p = _ckpt_path(symbol, data_dir)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def save_checkpoint(symbol, data_dir, cursor, oldest, newest, total):
    with open(_ckpt_path(symbol, data_dir), "w") as f:
        json.dump({
            "symbol": symbol, "cursor": cursor, "oldest": oldest,
            "newest": newest, "total": total,
            "updated": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)


def existing_summary(symbol, data_dir):
    """Return (total_ticks, day_count, oldest_date, newest_date) for stored data, or None."""
    ckpt = load_checkpoint(symbol, data_dir)
    if not ckpt:
        return None
    return {
        "total": ckpt.get("total", 0),
        "oldest": datetime.fromtimestamp(ckpt["oldest"], tz=timezone.utc).date().isoformat(),
        "newest": datetime.fromtimestamp(ckpt["newest"], tz=timezone.utc).date().isoformat(),
        "cursor": ckpt.get("cursor"),
    }


async def _request(ws, payload, timeout=30):
    req_id = (abs(hash(json.dumps(payload, sort_keys=True))) % 1_000_000) or 1
    await ws.send(json.dumps(dict(payload, req_id=req_id)))
    while True:
        data = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if data.get("req_id") == req_id or data.get("error"):
            return data


async def collect(symbol, start_epoch, end_epoch, data_dir,
                  batch=DEFAULT_BATCH, rate=DEFAULT_RATE_S, resume=False):
    """Pull ticks backward from end_epoch to start_epoch. Resumable."""
    store = TickStore(symbol, data_dir)
    ckpt = load_checkpoint(symbol, data_dir) if resume else None
    if ckpt:
        cursor, total = ckpt["cursor"], ckpt.get("total", 0)
        oldest, newest = cursor, ckpt.get("newest", 0)
        print(f"  ↻ resume from {datetime.fromtimestamp(cursor, tz=timezone.utc).date()} "
              f"(have {total:,} ticks)")
    else:
        cursor, total, oldest, newest = end_epoch, 0, end_epoch, 0

    print(f"  range: {datetime.fromtimestamp(start_epoch, tz=timezone.utc).date()} ← "
          f"{datetime.fromtimestamp(cursor, tz=timezone.utc).date()}  (batch={batch})")

    ws = await deriv_ws.connect()
    batches = 0
    try:
        while cursor > start_epoch:
            payload = {"ticks_history": symbol, "count": batch,
                       "start": str(start_epoch), "end": str(cursor), "style": "ticks"}
            data = None
            for attempt in range(5):
                try:
                    data = await _request(ws, payload)
                    break
                except Exception as e:
                    print(f"  ⏳ {type(e).__name__} — reconnect ({attempt + 1}/5)")
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                    ws = await deriv_ws.connect()
            if data is None:
                print("  ✗ repeated wire failures — stopping (checkpoint saved)")
                break

            if data.get("error"):
                err = data["error"]
                print(f"  ✗ error: {err.get('message', err)}")
                msg = str(err).lower()
                if any(k in msg for k in ("count", "limit", "maximum")):
                    batch = max(100, batch // 2)
                    print(f"     reducing batch → {batch}")
                await asyncio.sleep(max(rate, 1))
                continue

            times = data.get("history", {}).get("times", [])
            prices = data.get("history", {}).get("prices", [])
            if not times:
                print("  • no more ticks in range")
                break

            added = store.write(times, prices)
            total += added
            oldest = min(oldest, min(times))
            newest = max(newest, max(times))
            batch_oldest = min(times)
            print(f"    batch {batches + 1}: {len(times)} ticks (+{added} new) | "
                  f"oldest {datetime.fromtimestamp(batch_oldest, tz=timezone.utc).date()} | "
                  f"total {total:,}")

            if batch_oldest >= cursor:
                print("  • no backward progress — stopping")
                break
            cursor = batch_oldest - 1
            save_checkpoint(symbol, data_dir, cursor, oldest, newest, total)
            batches += 1
            await asyncio.sleep(rate)
    finally:
        await ws.close()
        save_checkpoint(symbol, data_dir, cursor, oldest, newest, total)

    return {"total": total, "oldest": oldest, "newest": newest,
            "cursor": cursor, "batches": batches}
