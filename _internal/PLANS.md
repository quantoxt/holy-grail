# Plans / Backlog

## Scalp-mode engine (proposed 2026-08-21)

**Goal:** a dedicated scalping engine for metals — the opposite of Kronos's 2h hold
(h=24 on 5m): seconds-to-minutes in and out, purely streamlined for XAU/XAG short
moves. Toggled on/off from the dashboard.

**Status:** NOT BUILT, deliberately. Decision (2026-08-21): build the trading engine
only after an edge is measured.

**Why it's parked:**
- The 2026-08-17 incident was accidental scalping: TP inside the spread, every "win"
  a real loss. XAU round trip ≈ $3.50 at 0.01 lots — a scalper must clear that per
  trade before profit #1. With ~50% measured hit rate, scalping pays spread faster
  than the horizon style.
- A second engine doubles the failure surface (orphaned positions, sizing races,
  slot contention with the Kronos loop) — the exact bug classes fixed in August.

**Agreed path when revisited:**
1. Shadow-measure first: short-horizon Kronos (`pred_len=2–6` on 1m candles) scored
   through the existing `prediction_evaluations` loop — zero money at risk.
2. Gate: per-symbol hit rate ≥ ~55% *after* spread cost over ≥ 2 weeks.
3. Only then build the engine (separate from the Kronos loop; separate magic number
   so positions never mix; its own risk caps).
