"""Watcher — confidence/regime gate + model-drift kill switch (Layer 2).

Decides whether a SignalEngine signal should actually be traded. The validated
edge lives in CONFIDENT h=24 predictions (the SignalEngine already emits HOLD
below the confidence threshold); the Watcher adds a second layer: a rolling
accuracy check — if the model's recently RESOLVED predictions have gone cold
(rolling directional accuracy below coin-flip), trading is paused (drift).
"""
from collections import deque


class Watcher:
    def __init__(self, drift_window: int = 20, drift_floor: float = 0.50, warmup: int = 10):
        self.resolved = deque(maxlen=drift_window)   # 1=correct, 0=wrong, per resolved prediction
        self.drift_floor = drift_floor
        self.warmup = warmup                          # need this many before drift can trigger

    def record_resolution(self, correct: bool):
        """Call when a past prediction's horizon elapsed and we know if it was right."""
        self.resolved.append(1 if correct else 0)

    @property
    def rolling_accuracy(self):
        return sum(self.resolved) / len(self.resolved) if self.resolved else None

    def should_trade(self, signal: dict) -> tuple[bool, str]:
        if signal["direction"] == "HOLD":
            return False, "below_confidence_threshold"
        acc = self.rolling_accuracy
        if acc is not None and len(self.resolved) >= self.warmup and acc < self.drift_floor:
            return False, f"model_drift (rolling acc {acc:.0%} < {self.drift_floor:.0%})"
        return True, "ok"
