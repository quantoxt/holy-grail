"""
Phase 0 — fetch the pretrained Kronos model we'll fine-tune, and verify it loads.

Downloads (into the HuggingFace cache, persisted) and instantiates:
  - KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
  - Kronos.from_pretrained("NeoQuasar/Kronos-small")        # blueprint's CPU starting point

Run with the torch venv:
  ./venv-torch/bin/python -m research.fetch_kronos
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KRONOS = ROOT / "model" / "Kronos"
sys.path.insert(0, str(KRONOS))  # so `from model import ...` finds model/Kronos/model

import torch  # noqa: E402
from model import Kronos, KronosTokenizer  # noqa: E402


def main():
    print(f"torch {torch.__version__} | device: {'cuda' if torch.cuda.is_available() else 'cpu'}")

    print("\n→ loading Kronos-Tokenizer-base …")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    print(f"  ✓ {type(tokenizer).__name__}")

    print("\n→ loading Kronos-small …")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  ✓ {type(model).__name__}  ({n_params / 1e6:.1f}M params)")

    # smoke: end-to-end prediction on a synthetic OHLCV series, on CPU
    import numpy as np
    import pandas as pd
    from model import KronosPredictor

    predictor = KronosPredictor(model, tokenizer, max_context=512)
    n = 100
    ts = pd.date_range("2026-01-01", periods=n + 10, freq="5min")
    rng = np.random.default_rng(0)
    close = 100.0 + np.cumsum(rng.standard_normal(n + 10) * 0.1)
    df = pd.DataFrame({
        "open": close, "high": close + 0.05, "low": close - 0.05,
        "close": close, "volume": 0.0, "amount": 0.0,
    })
    x_df = df.iloc[:n][["open", "high", "low", "close", "volume", "amount"]]
    pred = predictor.predict(x_df, pd.Series(ts[:n]), pd.Series(ts[n:n + 10]),
                             pred_len=10, sample_count=1, verbose=False)
    print(f"\n→ predict smoke: {len(pred)} future candles forecast, cols {list(pred.columns)}")
    print("\n✅ Kronos-small loads + runs end-to-end on CPU. Ready for fine-tuning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
