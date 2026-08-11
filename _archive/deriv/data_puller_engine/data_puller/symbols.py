"""Deriv synthetic indices offered by this engine.

Source: blueprint/01-deriv-environment.md. Standard indices tick ~2/sec; the
1Hz variants tick exactly once per second. (symbol, display_name, volatility)
"""

SYNTHETICS = [
    ("R_10",    "Volatility 10 Index",     "Low"),
    ("R_25",    "Volatility 25 Index",     "Low-Med"),
    ("R_50",    "Volatility 50 Index",     "Medium"),
    ("R_75",    "Volatility 75 Index",     "Med-High"),
    ("R_100",   "Volatility 100 Index",    "High"),
    ("1HZ10V",  "Volatility 10 (1s)",      "Low"),
    ("1HZ25V",  "Volatility 25 (1s)",      "Low-Med"),
    ("1HZ50V",  "Volatility 50 (1s)",      "Medium"),
    ("1HZ75V",  "Volatility 75 (1s)",      "Med-High"),
    ("1HZ100V", "Volatility 100 (1s)",     "High"),
]

BY_CODE = {s[0]: s for s in SYNTHETICS}
