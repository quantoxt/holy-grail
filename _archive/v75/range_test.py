"""
Phase 0 — range/extreme prediction test for the fine-tuned Kronos model.

Hypothesis: CSRNG *direction* is coin-flip (validated), but CSRNG *volatility/
range* has real structure — so Kronos may predict BARRIERS and SWING SIZE well
enough to trade Touch/No-Touch contracts even though Rise/Fail failed.

Scores, out-of-sample on V75 M5:
  - Touch accuracy/precision/recall at several barriers (±0.3% … ±1.5%) over
    several horizons — directly the Touch/No-Touch contract decision.
  - Range-size MAE (predicted high-low span vs actual) vs a naive baseline.

Resumable (JSONL checkpoint). Runs on CPU or GPU (auto). For speed use a GPU.

  python -m research.range_test                          # run (resume)
  python -m research.range_test --report-only            # print report from checkpoint
"""
import argparse
import json
import sys
import time
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "Kronos"))

HORIZONS = [6, 12, 24]
BARRIERS = [0.003, 0.005, 0.0075, 0.01, 0.015]   # ±% from current close
CKPT = ROOT / "data" / "range_checkpoint.jsonl"


def load_checkpoint(points_set):
    done = {}
    if CKPT.exists():
        for line in CKPT.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["i"] in points_set:
                done[r["i"]] = r["res"]
    return done


def report(done):
    # touch tallies: (H,B) -> list of [pred_touch, act_touch]; span: H -> [pred_span, act_span]
    touch = {(h, b): [] for h in HORIZONS for b in BARRIERS}
    span = {h: [] for h in HORIZONS}
    for res in done.values():
        for h in HORIZONS:
            if f"span_{h}" in res:
                span[h].append(res[f"span_{h}"])
            for b in BARRIERS:
                k = f"{h}_{b}"
                if k in res:
                    touch[(h, b)].append(res[k])

    print("\n" + "=" * 78)
    print("  RANGE / TOUCH PREDICTION — Kronos on V75 M5 (out-of-sample)")
    print("=" * 78)
    print("-- Touch: 'does price reach ±B% within H candles?' (Touch/No-Touch contract) --")
    print(f"{'H\\B':<6}" + "".join(f"{f'{b*100:.2f}%':<20}" for b in BARRIERS))
    for h in HORIZONS:
        cells = []
        for b in BARRIERS:
            rows = touch[(h, b)]
            if len(rows) < 20:
                cells.append("n/a"); continue
            pt = sum(r[0] for r in rows); at = sum(r[1] for r in rows)
            tp = sum(1 for r in rows if r[0] and r[1])
            prec = tp / pt if pt else 0
            base = at / len(rows)
            cells.append(f"base {base*100:.0f}% prec {prec*100:.0f}%")
        print(f"{h:<6}" + "".join(f"{c:<20}" for c in cells))
    print("  (base = actual touch rate; prec = of model's 'will touch' calls, share that really did)")

    print("\n-- Range-size prediction (high-low span over H candles) --")
    print(f"{'H':<6}{'n':<8}{'pred MAE':<14}{'baseline MAE':<14}{'edge':<10}")
    for h in HORIZONS:
        rows = span[h]
        if len(rows) < 20:
            continue
        acts = np.array([r[1] for r in rows])
        mae_pred = np.mean(np.abs(np.array([r[0] for r in rows]) - acts))
        mae_base = np.mean(np.abs(np.mean(acts) - acts))
        edge = (mae_base - mae_pred) / mae_base * 100
        print(f"{h:<6}{len(rows):<8}{mae_pred:<14.4f}{mae_base:<14.4f}{edge:+.1f}%")
    print("\nRead: positive range 'edge' = model beats naive; touch prec > base = model adds info.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", default="R_75")
    p.add_argument("--tf", default="M5")
    p.add_argument("--model-dir", default="data/models/deriv-v75-m5")
    p.add_argument("--test-size", type=int, default=600)
    p.add_argument("--stride", type=int, default=3)
    p.add_argument("--lookback", type=int, default=512)
    p.add_argument("--pred-len", type=int, default=24)
    p.add_argument("--sample-count", type=int, default=1)
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args()

    horizons = [h for h in HORIZONS if h <= args.pred_len]
    csv = ROOT / "data" / "ohlcv" / args.symbol / f"{args.tf}.csv"
    df = pd.read_csv(csv)
    df["timestamps"] = pd.to_datetime(df["timestamps"])
    highs = df["high"].to_numpy(); lows = df["low"].to_numpy(); closes = df["close"].to_numpy()
    n = len(df)

    start = max(args.lookback, n - args.test_size)
    end = n - args.pred_len
    points = list(range(start, end, args.stride))
    done = load_checkpoint(set(points))
    if args.report_only:
        report(done); return 0
    todo = [i for i in points if i not in done]
    print(f"{args.symbol} {args.tf}: {n} candles | {len(done)} done, {len(todo)} to run")

    if todo:
        from model import Kronos, KronosTokenizer, KronosPredictor
        tok = KronosTokenizer.from_pretrained(f"{args.model_dir}/tokenizer/best_model")
        mdl = Kronos.from_pretrained(f"{args.model_dir}/basemodel/best_model")
        predictor = KronosPredictor(mdl, tok, max_context=args.lookback)
        dev = "GPU" if "cuda" in str(predictor.device) else "CPU"
        print(f"model loaded on {dev}; pred_len={args.pred_len}, samples={args.sample_count}\n")

        t0 = time.time()
        with open(CKPT, "a") as f:
            for k, i in enumerate(todo, 1):
                ctx = df.iloc[i - args.lookback:i][["open", "high", "low", "close", "volume", "amount"]]
                x_ts = pd.Series(df.iloc[i - args.lookback:i]["timestamps"].to_numpy())
                y_ts = pd.Series(df.iloc[i:i + args.pred_len]["timestamps"].to_numpy())
                pred = predictor.predict(ctx, x_ts, y_ts, pred_len=args.pred_len,
                                         sample_count=args.sample_count, verbose=False)
                p_high = pred["high"].to_numpy(); p_low = pred["low"].to_numpy()
                cur = closes[i - 1]
                res = {}
                for h in horizons:
                    pmx, pmn = p_high[:h].max(), p_low[:h].min()
                    amx, amn = highs[i:i + h].max(), lows[i:i + h].min()
                    res[f"span_{h}"] = [float(pmx - pmn), float(amx - amn)]
                    for b in BARRIERS:
                        up, dn = cur * (1 + b), cur * (1 - b)
                        pt = int(pmx >= up or pmn <= dn)
                        at = int(amx >= up or amn <= dn)
                        res[f"{h}_{b}"] = [pt, at]
                f.write(json.dumps({"i": i, "res": res}) + "\n"); f.flush()
                done[i] = res
                if k % 10 == 0 or k == len(todo):
                    el = time.time() - t0
                    print(f"  [{len(done)}/{len(points)}] {el:.0f}s ({el/k:.2f}s/pred)", flush=True)
    report(done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
