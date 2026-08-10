# How Kronos Predicts — and Why It Calls "Long Shots" That Blow the SL Budget

A working technical explainer for the Holy Grail bot. Grounded in `soldier/signal.py`,
`shared/config.py`, and the live behaviour observed in the 2026-08-10 overnight +
Headway runs. Written so you can reason about *why* a predicted move produces an SL
bigger than the account can afford — and what actually fixes it.

---

## 1. What Kronos is

**Kronos** (AAAI 2026, MIT/NeoQuasar) is a **foundation model for time series** — think of
it as an LLM, but for sequences of numbers instead of words.

- **Tokenizer + Transformer.** A `KronosTokenizer` chops a continuous series (here: OHLCV
  candles) into discrete tokens, the way text is split into subwords. A transformer then
  autoregressively generates the *next* tokens — i.e. the future of the series.
- **Trained on massive, diverse time-series data** (not one market). That's the whole point
  of "foundation": it learns general sequential structure and is meant to generalize to
  series it has never seen.
- **Zero-shot.** We use the pre-trained `NeoQuasar/Kronos-small` with **no fine-tuning**.
  Fine-tuning on Deriv synthetics *failed* (47% directional, coin-flip). Fine-tuning on
  live data is future work. So every prediction today is the model reasoning about a live
  market it was never specifically taught.

In the bot (`signal.py`): `KronosPredictor(Kronos.from_pretrained("NeoQuasar/Kronos-small"),
KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base"), max_context=512)`.

---

## 2. How the bot actually extracts a signal (the mechanics)

From `SignalEngine.get_signal()` in `soldier/signal.py`:

```
INPUT:   last 512 candles (lookback=512) of OHLCV  →  ctx
PREDICT: pred_len = 24 future candles               →  pred
SIGNAL:  predicted_close = pred["close"].iloc[23]   (the close 24 candles ahead)
         move = (predicted_close - current_close) / current_close
         direction = BUY if move >= +0.003, SELL if move <= -0.003, else HOLD
```

So the **entire trade decision hangs on one number**: the close price at the 24th future
candle. Everything downstream — direction, confidence, the SL, the lot — is derived from
`predicted_close`.

Key derived quantities:

| Quantity | Formula | What it really is |
|---|---|---|
| `move` | `(pred_close − cur) / cur` | predicted % change over the horizon |
| `confidence` | `min(|move| / (0.003×3), 1)` | **a magnitude proxy, capped at 1** — *not* a probability |
| `sl_price` | `cur × (1 − 2·|move|)` (BUY) | safety stop = **2× the predicted move** away |
| `snr` | `|move| / (std(returns)·√24)` | signal-vs-noise; filters *small* moves, not large |
| `vol` | `std(returns)·√24` | expected noise over the horizon |

The horizon: **`pred_len=24` on 5-minute candles = 2 hours ahead** (not 24 hours). This
matches the validation setup.

---

## 3. The validated edge — and its hard limits

**Validated:** on **BTC/USDT 5-minute** candles, at **h=24 (2 hours)**, pre-trained Kronos
achieves **54.7% directional accuracy** — i.e. the 24th predicted close is on the correct
side of the current price 54.7% of the time. That is ~3σ above coin-flip, a small but real
edge. The Sentinel risk framework exists to *amplify* that thin edge into profit.

**The limits (this is where the trouble starts):**

1. **Validated on BTCUSD only.** Never measured on XAUUSD, XAGUSD, EURUSD, GBPUSD, or any
   forex pair. We are currently trading those on **borrowed faith**.
2. **Directional only.** 54.7% measures *up-vs-down*, **not magnitude**. It says nothing
   about whether the predicted *size* of the move is calibrated. (See §4 — this is the crux.)
3. **Point forecast, not a distribution.** We sample `sample_count=1` (CPU-bound on the VPS),
   so each prediction is a single noisy draw, not an averaged expectation.

---

## 4. Why it calls "long shots": the magnitude-calibration problem

The long shots are not a bug in the SL math. They come from **Kronos predicting move sizes
that are far larger than the instrument actually realizes**, combined with the SL being
mechanically pegged to that un-calibrated size. Six compounding reasons:

### 4.1 A direction model is not a magnitude model
54.7% directional accuracy can coexist with terrible magnitude calibration. Kronos can be
right that silver goes *down* while predicting it falls **4%** when reality is **0.4%**.
The endpoint of a generated 24-step path is a poor estimator of *how far* price moves,
even when it gets the *sign* right.

### 4.2 Foundation-model point forecasts drift, and endpoints exaggerate
Kronos autoregressively generates 24 tokens; small per-step errors **compound** along the
path, and the 24th-step close (the number we trade on) is the most error-prone. Sampled
foundation-model trajectories tend to **wander** — the endpoint can land far from the
current price simply because it's the tail of a generated walk, not because the model has
high conviction. There's no built-in "stay near reality" prior.

### 4.3 No magnitude priors for a new asset class (zero-shot)
Kronos was never told what a *plausible* 2-hour move looks like for gold vs. silver vs.
EURUSD. Its sense of "normal" is baked into whatever dominated its training data. The edge
was measured on **BTC** — an asset where multi-percent 2-hour swings are routine. When that
same model is pointed at metals/forex zero-shot, it happily imports crypto-scale volatility
expectations → it predicts 2–5% moves for instruments whose real 2-hour moves are usually
well under 1%.

### 4.4 The SL is pegged to the un-calibrated magnitude (2× move)
`sl_price = cur × (1 − 2·|move|)`. The stop distance is literally **twice the predicted
move**. So any magnitude overshoot flows straight into an oversized SL:
- Predict silver −2% → SL at −4% → on 0.1 lot (5000 oz) that's a **~$2900** stop.
- The SL inherits 100% of Kronos's magnitude error. There is no volatility/reality anchor.

### 4.5 The filters pass big moves, not reject them
- `confidence_threshold = 0.003` (0.3%) only gates tiny moves (HOLD vs trade). **There is
  no upper bound** — a 4% prediction sails through just like a 0.4% one.
- `snr_min = 1.0` rejects *low*-SNR (small-move-in-noise) signals. It does **nothing** about
  *high*-magnitude overshoots.
- `confidence` *rises* with |move|. So the bot effectively **prefers the biggest, wildest
  calls** — exactly the ones most likely to be magnitude hallucinations.

### 4.6 Single-sample noise (`sample_count=1`)
Each prediction is one Monte-Carlo draw from the model. Sampling once means we see maximum
variance — the tails. Averaging many samples (sample_count=8–16) would regress predictions
toward the mean and dampen the extremes, but the CPU VPS runs `sample_count=1`.

**Net effect:** the bot feeds a 2-hour-ahead endpoint forecast from an un-calibrated,
zero-shot, single-sampled, crypto-validated model into an SL formula that doubles it, with
no plausibility ceiling — and then trades instruments it has never been measured on. The
"long shots" are the predictable result.

---

## 5. Why the SL exceeds the budget (the triangle)

A trade is allowed only if its actual dollar risk fits the cap:

```
actual_risk  =  lot  ×  |entry − SL|  ×  contract_size
budget (cap) =  risk_cap_pct  ×  equity           (e.g. 0.08 × $500 = $40)
```

For the trade to pass, the **predicted move** must be small enough that `2×|move| × lot ×
contract ≤ cap`. Solve for the max allowable move:

| Broker min-lot | EURUSD max move to fit $40 | XAGUSD max move to fit $40 |
|---|---|---|
| 0.01 (MetaQuotes) | ~3% | ~0.5% |
| 0.10 (Headway) | ~0.3% | ~0.05% |

Kronos routinely predicts **1–4% moves** (see §6). So:
- On a **0.01** broker + $500: forex sometimes fits (move ≲3%), metals usually don't.
- On a **0.10** broker (Headway) + $500: **nothing fits** — even a 0.3% call blows the cap,
  because 0.1 lot is 10× the exposure.

This is a **three-way mismatch**: Kronos's natural move-magnitude (crypto-scale) vs. the
instrument's real move-size (sub-1%) vs. the account's allowable move-size (micro, set by
min-lot × equity). The SL is bigger than the budget whenever Kronos's prediction exceeds
that tiny allowable move — which is most of the time.

**Important:** the cap isn't malfunctioning here. It's correctly refusing positions that
would risk 10–500% of the account. The cap is the messenger.

---

## 6. Evidence from the live logs (2026-08-10)

The overshoot is directly observable, not theoretical:

```
MetaQuotes account ($61, 0.01 lot):
  XAGUSD  → risk $79   at 0.01 lot  → SL ≈ 1.6%  → implied |move| ≈ 0.8%... but
            some draws hit risk $2907+ → implied |move| ≈ 2.5–4.6%
  XAUUSD  → risk $173  at 0.01 lot  → SL ≈ 4%    → implied |move| ≈ 2%
  GBPJPY  → risk $2407              → implied |move| ≈ several %

Headway account ($500, 0.10 lot — 10× exposure):
  XAGUSD  → risk $2907 at 0.10 lot  → SL ≈ 9%    → implied |move| ≈ 4.6%
  AUDUSD  → risk $82                → implied |move| ≈ 0.8%
```

Real 2-hour moves for XAGUSD/XAUUSD/EURUSD are typically **<1%**. Kronos is predicting
**2–5× that**, and the SL (2× move) lands at 4–9% — which on any min-lot × small equity
vastly exceeds the cap. That is the long-shot problem in numbers.

---

## 7. What actually fixes it

Ordered cheapest → most work. None of these require touching Kronos itself.

### 7.1 Plausibility cap on the move (do this first — ~5 lines)
Reject any signal whose predicted magnitude is implausible for the instrument, e.g. in
`signal.py` / the loop:
```
if abs(move) > settings.max_move_pct:   # e.g. 0.015 (1.5%) — kills the long shots
    direction = "HOLD"
```
This single ceiling removes the giant SLs at the source. Tune per-asset-class (metals/forex
tighter than crypto).

### 7.2 Decouple the SL from Kronos's magnitude — use realized volatility
Replace `SL = 2 × |predicted_move|` with `SL = k × ATR` (or `k × std(returns)·√pred_len`,
which `signal.py` already computes as `vol`). The stop then reflects **real** volatility,
not an un-calibrated forecast. The predicted move still picks direction; ATR sizes the stop.

### 7.3 Raise `sample_count` (CPU permitting)
`sample_count=8` averages draws → predictions regress toward the mean → fewer extreme
endpoints → smaller, saner SLs. Costs inference time (×8 on CPU). Test the latency hit.

### 7.4 Validate Kronos per-instrument before trading it
The real fix. For each symbol we want to trade, run an offline backtest (like the BTCUSD
one in `research/validate.py`) measuring **both** directional accuracy **and** magnitude
calibration on live data. Only trade instruments that pass. Until then, BTCUSD is the only
justified instrument — metals/forex are speculative.

### 7.5 Size the account / broker to the SLs that survive
Even with the above, the SL must fit `risk_cap_pct × equity`. That needs either a **0.01
min-lot broker** (so a realistic SL is a small % of a $500 account) or a **bigger account**
(so 0.1-min-lot positions are ~1% each). Headway's 0.1 min-lot is untradeable below ~$5000.

---

## 8. The honest one-liner

Kronos gives us a thin **directional** edge on **BTCUSD**, but we've been using its raw
**magnitude** forecasts — which are un-calibrated, single-sampled, and crypto-scaled — to
size stops on instruments it was never validated for. The SLs exceed the budget because
the stops are 2× an exaggerated prediction, and the account is too small (or the min-lot
too large) to absorb a realistic stop, let alone an exaggerated one. Fix the magnitude
(§7.1–7.2), validate per-instrument (§7.4), and size the account to reality (§7.5) — in
that order.
