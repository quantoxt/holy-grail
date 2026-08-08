"""
Phase 0 — Step 5: Walk-forward validation of the fine-tuned Kronos model.

Runs the model OUT-OF-SAMPLE over the held-out tail of the V75 M5 series and
measures DIRECTIONAL accuracy — the >55% gate. Pure CPU inference.

RESUMABLE: each prediction's result is appended to a JSONL checkpoint, so any
interruption (session exit, laptop sleep) resumes from where it stopped. The
report is computed from the checkpoint, so it can be reprinted anytime with
--report-only (no model load).

Run:
  ./venv-torch/bin/python -m research.validate                 # fresh or resume
  ./venv-torch/bin/python -m research.validate --report-only   # just print the report
  ./venv-torch/bin/python -m research.validate --pred-len 24 --test-size 600 --stride 3
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

HORIZONS = [1, 6, 12, 24, 48]
FILTER_THRESHOLDS = [0.001, 0.002, 0.003]
CKPT = ROOT / "data" / "validate_checkpoint.jsonl"


def sign(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def load_checkpoint(points_set):
    """Load {i: {str(h): [correct, pm, am]}} for indices still in the window."""
    done = {}
    if CKPT.exists():
        for line in CKPT.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["i"] in points_set:
                done[r["i"]] = r["res"]
    return done


def report(done, horizons, symbol, tf):
    tallies = {h: [] for h in horizons}
    for res in done.values():
        for h in horizons:
            key = str(h)
            if key in res:
                tallies[h].append(res[key])

    print("\n" + "=" * 64)
    print(f"  DIRECTIONAL ACCURACY — {symbol} {tf} (out-of-sample)")
    print("=" * 64)
    print(f"{'horizon':<10}{'n':<8}{'raw acc':<12}" + "".join(f"{f'≥{t*100:.1f}%':<12}" for t in FILTER_THRESHOLDS))
    any_pass = False
    for h in horizons:
        rows = tallies[h]
        if not rows:
            continue
        n_h = len(rows)
        raw = sum(r[0] for r in rows) / n_h
        cells = []
        for t in FILTER_THRESHOLDS:
            sub = [r for r in rows if abs(r[1]) >= t]
            cells.append(f"{sum(r[0] for r in sub)/len(sub)*100:.1f}%({len(sub)})"
                         if len(sub) >= 20 else "-")
        flag = "  >55%" if raw > 0.55 else ""
        if raw > 0.55:
            any_pass = True
        print(f"{h:<10}{n_h:<8}{raw*100:.1f}%{flag:<12}" + "".join(f"{c:<12}" for c in cells))
    print("\nraw acc  = directional accuracy over ALL predictions at that horizon")
    print(">=X% cols = accuracy on 'confident' predictions (|pred move|>=X); (n=subset)")
    print(f"\n55% GATE: {'PASS (>=55% at a tradeable horizon)' if any_pass else 'FAIL (no horizon > 55%)'}")


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
    p.add_argument("--resume", action="store_true", default=True, help="resume from checkpoint")
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.add_argument("--report-only", action="store_true", help="skip inference, print report from checkpoint")
    p.add_argument("--pause", type=float, default=0.0, help="seconds to idle between predictions (thermal pacing)")
    p.add_argument("--pretrained", action="store_true", help="load vanilla Kronos-small from HuggingFace (zero-shot) instead of the local fine-tuned model")
    args = p.parse_args()

    horizons = [h for h in HORIZONS if h <= args.pred_len]
    global CKPT
    tag = f"_{args.symbol}_{args.tf}{'_pretrained' if args.pretrained else ''}"
    CKPT = ROOT / "data" / f"validate{tag}.jsonl"

    csv = ROOT / "data" / "ohlcv" / args.symbol / f"{args.tf}.csv"
    df = pd.read_csv(csv)
    df["timestamps"] = pd.to_datetime(df["timestamps"])
    closes = df["close"].to_numpy()
    n = len(df)

    start = max(args.lookback, n - args.test_size)
    end = n - args.pred_len
    points = list(range(start, end, args.stride))
    points_set = set(points)

    done = load_checkpoint(points_set) if args.resume else {}
    if args.report_only:
        report(done, horizons, args.symbol, args.tf)
        return 0

    todo = [i for i in points if i not in done]
    print(f"{args.symbol} {args.tf}: {n} candles | window {start}..{end} stride {args.stride}")
    print(f"predictions: {len(done)} done, {len(todo)} to run (total {len(points)})")

    if todo:
        from model import Kronos, KronosTokenizer, KronosPredictor
        if args.pretrained:
            tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
            mdl = Kronos.from_pretrained("NeoQuasar/Kronos-small")
            print("loaded PRETRAINED Kronos-small (zero-shot) from HuggingFace")
        else:
            tok = KronosTokenizer.from_pretrained(f"{args.model_dir}/tokenizer/best_model")
            mdl = Kronos.from_pretrained(f"{args.model_dir}/basemodel/best_model")
        predictor = KronosPredictor(mdl, tok, max_context=args.lookback)
        print(f"model loaded (pred_len={args.pred_len}, samples={args.sample_count})\n")

        t0 = time.time()
        with open(CKPT, "a") as f:
            for k, i in enumerate(todo, 1):
                ctx = df.iloc[i - args.lookback:i][["open", "high", "low", "close", "volume", "amount"]]
                x_ts = pd.Series(df.iloc[i - args.lookback:i]["timestamps"].to_numpy())
                y_ts = pd.Series(df.iloc[i:i + args.pred_len]["timestamps"].to_numpy())
                pred = predictor.predict(ctx, x_ts, y_ts, pred_len=args.pred_len,
                                         sample_count=args.sample_count, verbose=False)
                pred_closes = pred["close"].to_numpy()
                cur = closes[i - 1]
                res = {}
                for h in horizons:
                    pm = (pred_closes[h - 1] - cur) / cur
                    am = (closes[i + h - 1] - cur) / cur
                    if sign(am) != 0:
                        res[str(h)] = [int(sign(pm) == sign(am)), pm, am]
                f.write(json.dumps({"i": i, "res": res}) + "\n")
                f.flush()
                done[i] = res
                if k % 10 == 0 or k == len(todo):
                    el = time.time() - t0
                    print(f"  [{len(done)}/{len(points)}] (+{k} new) {el:.0f}s "
                          f"({el/k:.1f}s/pred, eta {(len(todo)-k)*el/k:.0f}s)", flush=True)
                if args.pause:
                    time.sleep(args.pause)

    report(done, horizons, args.symbol, args.tf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
