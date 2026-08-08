"""
3:1 Reward:Risk validation — does Kronos's predicted magnitude support
a 3:1 R:R exit strategy?

Uses the existing BTC validation checkpoint (988 predictions with predicted +
actual moves). For each confident signal (the ones the bot would actually trade),
simulates: SL at various fractions of the predicted move, TP at 3x SL. Checks
whether the actual candle-path hit TP before SL within the h=24 horizon.

This is a PATH-DEPENDENT test — it checks the actual OHLC path (high/low over
the horizon), not just the close-to-close result. That's what determines whether
SL or TP gets hit first in reality.

Run:  ./venv-torch/bin/python -m research.rr_validation
"""
import json
import sys
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CKPT = ROOT / "data" / "validate_BTCUSDT_5m_pretrained.jsonl"
CSV = ROOT / "data" / "ohlcv" / "BTCUSDT" / "5m.csv"
HORIZON = 24


def load_predictions():
    """Load {i: {predicted_move, actual_move_h}} from checkpoint."""
    preds = {}
    if CKPT.exists():
        for line in CKPT.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            # res has {"1": [correct, pm, am], "24": [correct, pm, am], ...}
            h24 = r["res"].get("24")
            if h24:
                preds[r["i"]] = {"predicted_move": h24[1], "actual_move": h24[2]}
    return preds


def main():
    df = pd.read_csv(CSV)
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    preds = load_predictions()
    print(f"loaded {len(preds)} predictions from checkpoint, {n} candles in CSV\n")

    # SL fractions: SL = fraction * |predicted_move| * current_close
    # TP = 3 * SL
    SL_FRACTIONS = [0.5, 0.75, 1.0, 1.5]  # SL is 50%-150% of the predicted move distance

    # Only trade confident signals (same threshold as the bot)
    CONFIDENCE_THRESHOLD = 0.003  # |predicted_move| >= 0.3%

    print(f"{'SL frac':<10}{'trades':<10}{'TP hit':<10}{'SL hit':<10}{'neither':<10}{'win%':<10}{'expectancy/trade':<18}")
    print("-" * 78)

    for sl_frac in SL_FRACTIONS:
        tp_hits = 0
        sl_hits = 0
        neither = 0
        total_pnl = 0.0  # in R multiples

        for i, p in preds.items():
            pm = p["predicted_move"]
            am = p["actual_move"]

            # only trade confident signals
            if abs(pm) < CONFIDENCE_THRESHOLD:
                continue

            if i + HORIZON >= n:
                continue

            cur = closes[i - 1]
            direction = 1 if pm > 0 else -1

            # SL distance = sl_frac * |predicted_move| * current_close
            sl_distance = abs(pm) * sl_frac * cur
            tp_distance = sl_distance * 3.0  # 3:1 R:R

            # entry price
            entry = cur

            # SL and TP levels
            if direction == 1:  # BUY
                sl = entry - sl_distance
                tp = entry + tp_distance
            else:  # SELL
                sl = entry + sl_distance
                tp = entry - tp_distance

            # check the actual path: did high/low hit TP or SL first within HORIZON?
            hit_tp = False
            hit_sl = False
            for j in range(i, min(i + HORIZON, n)):
                if direction == 1:  # BUY
                    if lows[j] <= sl:
                        hit_sl = True
                        break
                    if highs[j] >= tp:
                        hit_tp = True
                        break
                else:  # SELL
                    if highs[j] >= sl:
                        hit_sl = True
                        break
                    if lows[j] <= tp:
                        hit_tp = True
                        break

            if hit_tp:
                tp_hits += 1
                total_pnl += 3.0  # +3R
            elif hit_sl:
                sl_hits += 1
                total_pnl -= 1.0  # -1R
            else:
                neither += 1
                # neither hit — close at horizon close (mark-to-close)
                exit_price = closes[min(i + HORIZON - 1, n - 1)]
                actual_move_price = (exit_price - entry) * direction
                pnl_r = actual_move_price / sl_distance  # in R multiples
                total_pnl += pnl_r

        trades = tp_hits + sl_hits + neither
        win_rate = tp_hits / trades * 100 if trades else 0
        expectancy = total_pnl / trades if trades else 0

        print(f"{sl_frac:<10.2f}{trades:<10}{tp_hits:<10}{sl_hits:<10}{neither:<10}{win_rate:<10.1f}{expectancy:+.4f}R")

    print(f"\n--- Interpretation ---")
    print("win% = how often TP (3R) hit before SL (-1R)")
    print("expectancy = average R per trade (positive = profitable)")
    print("Breakeven win rate at 3:1 R:R = 25% (1 in 4 trades must hit TP)")
    print("If win% > 25% AND expectancy > 0 → 3:1 R:R is viable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
