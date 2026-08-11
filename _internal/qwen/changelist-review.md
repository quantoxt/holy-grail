# Review of `changelist.md` (for the Aug-14 work)

Honest engineering vet of Qwen's proposal against what the codebase **actually does today**
and the **validated edge**. Status legend: ✅ already done · 🟢 agree, do it · ⚠️ blocked / needs
a decision · 🔴 conflicts with the validated edge — do not do without a deliberate call.

---

## 1. Signal generation & validation

### 1.1 Plausibility caps (reject |move| > ~1.5%) — 🟢 TOP PRIORITY, cheap
The single highest-value fix and the root cause of the "long-shot SL" problem
(see `docs/kronos-predictions.md` §4–7). ~5 lines in `signal.py`. **Make it a runtime knob**
(`max_move_pct`), per-asset-class (metals/forex ~1.5%, crypto higher), not hardcoded.
This alone defangs most of the oversized SLs. **Do first.**

### 1.2 Ensemble averaging (N=50) — ⚠️ BLOCKED by hardware, needs a decision
We measured the VPS: **i5-4210U, 2 cores, 11.6 s/symbol at N=1**. N=50 ≈ **~10 min/symbol**
on this CPU — infeasible for scanning any symbol list. Realistic options:
- **N=5–10** as a compromise (≈ 60–120 s/symbol) — real variance cut, still tractable with
  fewer symbols + longer cycle.
- **Offload inference** to a GPU/cloud box, feed predictions in — then N=50 is fine.
- **Drop it.** Once 2.1 (ATR-SL) is in, the SL no longer depends on the prediction magnitude,
  so prediction-variance matters far less. N=50's main payoff was calmer SLs; ATR-SL achieves
  that directly. **My lean: do 2.1 first, then N=50 may not be worth the CPU cost.**

### 1.3 Per-instrument calibration — ⚠️ can't just "implement"; needs DATA first
The edge was measured on **BTCUSD only**. Calibration for XAUUSD/XAGUSD/EURUSD requires
collecting live per-instrument outcomes and running the `research/validate.py` path on them.
That's a **research/data-accumulation task**, not a code toggle. Interim: per-instrument
`max_move_pct` caps (from 1.1) + start logging per-instrument realized accuracy now so we
have the data by the time we revisit. Don't trade unvalidated instruments at size meanwhile.

---

## 2. Risk management & stop loss

### 2.1 ATR-based stop loss (decouple SL from prediction) — 🟢 TOP PRIORITY
Agree completely. `SL = k × ATR` (real volatility) instead of `2 × |predicted_move|`.
Cheap because `signal.py` **already computes** `vol = std(returns)·√pred_len` — that's an
ATR-equivalent realized-vol measure sitting unused for sizing. Use it for the SL. This is the
fix that makes stops sane regardless of Kronos's magnitude hallucinations. Pair with 1.1.

### 2.2 Dynamic sizing to "always risk 1% of equity" — ⚠️ partially done; the rest is impossible
The intent already exists: `risk_cap_pct` IS the per-trade % ceiling, and lot is min-lot-bound
with a skip when it blows the cap. The part Qwen is asking for ("always 1%") is **mathematically
impossible** whenever `min_lot × SL_distance > 1% × equity` — and that's exactly the Headway
case (0.1 lot = 13% min). You cannot size below the broker's min-lot. The honest design is what
we have: **target the risk, floor to min-lot, skip if it exceeds the cap.** Don't promise "always
1%"; it's a ceiling you respect by declining, not a value you always hit. (4.1 below covers the
broker-constraint side.)

---

## 3. Exit strategy — 🔴 the dangerous section, needs your explicit call

### 3.1 Dynamic Take Profit (1× move / 1:1.5 R:R) — 🔴 CONFLICTS with the current design
We **already reversed the old "no TP" lock this session** to a **goal-aware trailing profit-lock**
(`docs/risk-framework.md`, `docs/trade-lifecycle.md`): once floating ≥ `profit_lock_target`, the
SL ratchets into profit; at `baseline+goal` equity, close all and bank the week. A **fixed** TP
at 1:1.5 R:R is a different philosophy that **cuts every winner at a fixed level** — which works
*against* a 54% directional edge (you need winners to run to outweigh losers). 
**Decision needed:** keep the trailing lock (my recommendation), switch to fixed R:R TP, or layer
a fixed TP as a *secondary* ceiling above the trail. With 2.1 (ATR-SL) an R:R TP becomes more
meaningful since R is real-volatility-based — but I'd still lean trailing-only. Don't just add it.

### 3.2 Replace the h=24 time-horizon close — 🔴 DO NOT. This abandons the validated edge.
The 54.7% directional accuracy was measured **at the h=24 (2 h) close**. That close *is* the
exit the edge was validated against. Replacing it with "momentum-decay detection / time-decay
weighting" means trading a **different, unvalidated strategy** — those heuristics have never been
backtested here and can easily cut the measured edge short. We already have: trailing profit-lock
(protects winners), breakeven-lock (downside), and h=24 as the **max hold / resolution**. That's
the right shape. **Keep h=24 as the resolution.** If anything, *add* research validating a
momentum-decay exit offline before ever letting it override the horizon — until then it's speculation.

---

## 4. Operational & execution

### 4.1 Respect min_lot / step before sizing — ✅ ALREADY DONE
Lot is computed from `volume_min`/`volume_step`/`contract_size` (`providers/mt5.py`
`get_symbol_info` + `sentinel.lot_size`), and over-cap trades are **skipped before** order send
(`loop.py` risk-cap check). That's why Headway's 0.1-lot trades never reached the broker — they
were filtered. Order *rejections* we still see are retcode-level (10027 AutoTrading off, 10018
market closed), not sizing. No code needed.

### 4.2 "Kill → Confirm → Run" protocol — ✅ ALREADY DONE
Documented in `docs/vps-troubleshooting.md` §4 and `docs/running-the-bot.md`. Plus
`_reconcile_positions()` on startup rebuilds `self.open` from the broker's real positions, so a
restart **never** double-counts. No code needed.

### 4.3 Floating P&L in the weekly-goal kill switch — ✅ ALREADY DONE
`check_kill` uses **live equity** (includes floating) for the ceiling, and `_maybe_bank_goal`
closes all when realized+floating ≥ goal. This was the direct fix for the overnight +$14→−$7
incident. No code needed.

---

## Recommended Aug-14 priority (my call)

1. **2.1 ATR-SL** + **1.1 plausibility cap** — together, the two cheap fixes that solve the
   long-shot/oversized-SL problem at the source. Do these first, as one unit.
2. **1.3 (interim):** per-instrument `max_move_pct` caps + start logging per-instrument realized
   accuracy so calibration has data later.
3. **Decide 3.1:** trailing-lock vs fixed TP (I recommend keeping the trail).
4. **Do NOT do 3.2** (don't touch the h=24 horizon without offline validation first).
5. **Revisit 1.2 (N=50)** only after 2.1 — it may no longer be worth the CPU. If still wanted,
   decide offload-vs-compromise.
6. **Skip 4.1 / 4.2 / 4.3** — already shipped.

## Open questions to settle before writing code
- 3.1: trailing lock only, fixed TP, or both?
- 1.2: is moving inference off the VPS on the table (unlocks N=50 and full symbol scans)?
- 1.3: are we willing to **restrict trading to validated instruments (BTCUSD)** until per-instrument
  calibration data exists? (Today we trade metals/forex on faith.)
