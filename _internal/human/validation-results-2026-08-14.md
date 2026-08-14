# Per-Instrument Validation Results — 2026-08-14 (VAST, RTX 5060 Ti)

Setup: pretrained Kronos-small (zero-shot), M5 broker CFD data (~13 months, 100k candles each),
walk-forward, stride 24, **N=5 averaged samples**, pred_len 24. 4,145 predictions per instrument.

| Symbol | h=24 raw acc | h=12 raw acc | 55% gate | Verdict |
|---|---|---|---|---|
| XAUUSD | **48.4%** (n=4141) | 50.9% | FAIL | coin flip |
| XAGUSD | **50.1%** (n=4069) | 50.7% | FAIL | coin flip |
| GBPUSD | **51.1%** (n=4124) | 50.7% | FAIL | coin flip |

Confidence filters (|pred move| ≥ 0.1/0.2/0.3%) do NOT rescue any instrument — every slice ~48–51%.

## Conclusion

**The BTCUSD edge (54.7% @ h=24, N=1, Binance spot) does not transfer** to gold/silver/cable
CFDs on this broker's feed at N=5. All three active instruments are statistically
indistinguishable from coin flips. The 2026-08-10 week (+$14, mostly one XAUUSD trade) was
luck, not edge.

Open caveats (why this isn't yet the final word on Kronos here):
- N=5 vs the N=1-validated edge — averaging may smooth away signal; an N=1 run on the same
  data is cheap (~$0.12) and would close this hole.
- Different data source (CFD feed vs Binance spot).
- One year of data; regime-dependent edges possible but unproven.

Artifacts: `data/validate_<SYM>_5m_n5_pretrained.jsonl` (checkpoints, resumable),
`data/vast_validate_2026-08-14.log` (full report). Instance 47724905 can be destroyed.

---

## UPDATE 2026-08-15: N=1 run (same data, same stride) — averaging theory DISPROVEN

Hypothesis under test: "N=5 averaging flattens the N=1 edge to coin-flip."

| Symbol | h=24 N=1 | h=24 N=5 | Δ |
|---|---|---|---|
| XAUUSD | 48.8% (n=4141) | 48.4% (n=4141) | +0.4 |
| XAGUSD | 49.7% (n=4069) | 50.1% (n=4069) | −0.4 |
| GBPUSD | 50.3% (n=4124) | 51.1% (n=4124) | −0.8 |

**N=1 ≈ N=5 on every instrument.** Averaging changed nothing because there was no signal
to flatten — the edge is absent on these instruments at both sample counts, not hidden by
averaging. XAUUSD is consistently ~1–1.6σ BELOW 50% across both runs. Only the sample size
changed between runs (identical data/stride/horizons), so the comparison is clean.

Artifacts: `data/validate_<SYM>_5m_n1_pretrained.jsonl`, `data/vast_validate_n1_2026-08-15.log`.

Remaining untested: BTCUSD at N=5 on Binance data (would confirm whether even the original
edge survives averaging) — moot for live trading since BTC isn't offered as traded here, but
would settle whether N=5 was ever a sane choice.
