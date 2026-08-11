"""
Phase 0 — last-digit distribution test for V75 (digit contracts).

Deriv digit contracts (Over/Under, Even/Odd, Match/Differ) bet on the LAST DIGIT
of the price. A fair CSRNG should produce uniform digits (0-9). If the digit
distribution is BIASED, that's an exploitable statistical edge that needs NO
direction/range prediction. This reads all V75 ticks, counts last digits at
several precisions, and runs a chi-square uniformity test + effect-size read.

Pure statistics — seconds of light CPU, no model.
  python -m research.digit_analysis
"""
import csv
import glob
import gzip
import sys
from collections import Counter
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
TICKS = ROOT / "data" / "ticks" / "R_75"

# chi-square critical values for 9 degrees of freedom (10 digits - 1)
CRIT = {0.05: 16.919, 0.01: 21.666, 0.001: 27.877}


def last_digit(price_str: str, precision: int) -> int:
    return int(f"{float(price_str):.{precision}f}"[-1])


def analyze(counts: Counter, label: str):
    n = sum(counts.values())
    if n == 0:
        return
    exp = n / 10
    chi2 = sum((counts[d] - exp) ** 2 / exp for d in range(10))
    sig = "not significant"
    for p, cv in sorted(CRIT.items(), reverse=True):
        if chi2 >= cv:
            sig = f"p < {p}"; break
    maxdev = max(abs(counts[d] / n - 0.10) for d in range(10)) * 100

    print(f"\n=== last digit @ {label} (n={n:,}) ===")
    print("digit:  " + " ".join(f"{d:>6d}" for d in range(10)))
    print("    % :  " + " ".join(f"{counts[d]/n*100:>6.2f}" for d in range(10)))
    print(f"chi2 = {chi2:.1f}  ({sig})   max |dev from 10%| = {maxdev:.3f} pp")

    # best Over/Under edge: P(digit >= t) vs fair (10-t)/10
    best = None
    for t in range(1, 10):
        obs = sum(counts[d] for d in range(t, 10)) / n
        fair = (10 - t) / 10
        edge = (obs - fair) * 100
        if best is None or abs(edge) > abs(best[2]):
            best = (t, obs * 100, edge)
    even = sum(counts[d] for d in (0, 2, 4, 6, 8)) / n * 100
    print(f"best Over/Under: threshold {best[0]} -> P(digit>={best[0]})={best[1]:.2f}% "
          f"(fair {(10-best[0])*10}%), edge {best[2]:+.2f} pp")
    print(f"Even digits: {even:.2f}% (fair 50%), edge {even-50:+.2f} pp")


def main():
    files = sorted(TICKS.glob("*.csv.gz"))
    if not files:
        print("no tick files"); return 1
    counts = {p: Counter() for p in (4, 2, 0)}  # 4dp, 2dp, integer-last-digit
    n = 0
    for fp in files:
        with gzip.open(fp, "rt") as f:
            for row in csv.reader(f):
                if not row or not row[0].isdigit():
                    continue
                price = row[1]
                for p in counts:
                    counts[p][last_digit(price, p)] += 1
                n += 1
    print(f"analyzed {n:,} V75 ticks across {len(files)} day-files")
    for p in (4, 2, 0):
        analyze(counts[p], f"{p}dp" if p else "integer")

    print("\nread: 'edge' = how far the model-free bet deviates from fair.")
    print("Digit payouts run ~90-95%, so an edge > ~5-10 pp is needed to be tradeable.")
    print("A significant chi2 with tiny max-dev = statistically biased but NOT tradeable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
