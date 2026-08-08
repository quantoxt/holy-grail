"""Soldier — Kronos inference + signal extraction (the prediction brain).

Loads pre-trained Kronos-small (zero-shot, no fine-tune) and extracts the
validated h=24 confident directional signal. Reuses the prediction logic proven
in research/validate.py. Market-agnostic — works for any provider's candles.
"""
import sys

import pandas as pd

from shared.config import settings


class SignalEngine:
    def __init__(self,
                 model: str = None, tokenizer: str = None,
                 lookback: int = None, pred_len: int = None, sample_count: int = None):
        sys.path.insert(0, settings.kronos_path)
        from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402

        self.predictor = KronosPredictor(
            Kronos.from_pretrained(model or settings.kronos_model),
            KronosTokenizer.from_pretrained(tokenizer or settings.kronos_tokenizer),
            max_context=lookback or settings.lookback,
        )
        self.lookback = lookback or settings.lookback
        self.pred_len = pred_len or settings.pred_len
        self.samples = sample_count or settings.sample_count

    def get_signal(self, candles: pd.DataFrame) -> dict:
        """candles: OHLCV df (timestamps, open, high, low, close, volume, amount).
        Returns the h=pred_len confident directional signal."""
        df = candles.tail(self.lookback).copy()
        df["timestamps"] = pd.to_datetime(df["timestamps"])
        ctx = df[["open", "high", "low", "close", "volume", "amount"]]
        x_ts = pd.Series(df["timestamps"].to_numpy())

        # future timestamps at the inferred candle interval
        if len(df) > 1:
            interval = df["timestamps"].diff().dropna().mode().iloc[0]
        else:
            interval = pd.Timedelta(minutes=5)
        last = df["timestamps"].iloc[-1]
        y_ts = pd.Series(pd.date_range(last + interval, periods=self.pred_len, freq=interval))

        pred = self.predictor.predict(ctx, x_ts, y_ts, pred_len=self.pred_len,
                                      sample_count=self.samples, verbose=False)
        cur = float(df["close"].iloc[-1])
        predicted_close = float(pred["close"].iloc[self.pred_len - 1])   # validated h=24 horizon
        move = (predicted_close - cur) / cur

        if move >= settings.confidence_threshold:
            direction = "BUY"
        elif move <= -settings.confidence_threshold:
            direction = "SELL"
        else:
            direction = "HOLD"

        # hard SL price: sl_multiplier × |predicted_move| (wide safety net, not noise-killed)
        from shared.runtime_config import runtime
        sl_dist = abs(move) * runtime.sl_multiplier
        if direction == "BUY":
            sl_price = cur * (1 - sl_dist)
        elif direction == "SELL":
            sl_price = cur * (1 + sl_dist)
        else:
            sl_price = None

        return {
            "direction": direction,
            "predicted_move": move,
            "current_close": cur,
            "predicted_close": predicted_close,
            "sl_price": sl_price,
            "horizon": self.pred_len,
            "confidence": min(abs(move) / (settings.confidence_threshold * 3), 1.0),  # 0..1 rough scale
        }
