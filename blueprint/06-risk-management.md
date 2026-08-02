# Risk Management (Kronos-Era)

---

## Financial Targets

### Conservative Estimates ($10,000 Account)

| Scenario | Monthly ROI | Dollar Amount | Notes |
|----------|-------------|---------------|-------|
| Bad month | 0-3% | $0 - $300 | Kronos predictions unreliable, bot mostly paused |
| Average month | 5-8% | $500 - $800 | Normal Kronos confidence levels |
| Good month | 8-12% | $800 - $1,200 | High Kronos confidence, favorable regime |
| Exceptional | 12-15% | $1,200 - $1,500 | Kronos highly accurate, everything aligns |

### Key Variables
- **Kronos prediction accuracy** — now the biggest factor (replaces "market regime")
- **Fine-tuning quality** — determines prediction ceiling
- **Execution latency** — mitigated by VPS near Deriv servers
- **Slippage** — always exists, minimized by good infrastructure

### Account Size Considerations
- Account size not yet determined — need to study Deriv indices properly first
- Start with demo → small live ($100-500) → scale based on proven results
- Minimum viable: enough to cover stakes for 50+ consecutive losses without blowup

---

## Drawdown Management

### Acceptable Drawdown: 15-20% to achieve high returns

This means: if you have $10,000, you accept that the account may temporarily drop to $8,000-$8,500 during a rough patch.

### Drawdown Triggers

| Drawdown Level | Action |
|---------------|--------|
| < 5% | Normal operation |
| 5-10% | Reduce lot size to 0.5x, increase monitoring |
| 10-15% | Lot size to 0.25x, review Kronos model accuracy |
| 15-20% | **Hard stop** — pause bot, check if Kronos needs retraining |
| > 20% | **Emergency stop** — manual intervention required |

### Daily Limits

| Parameter | Value (Example) | Notes |
|-----------|----------------|-------|
| Max daily loss | 3-5% of account | Hard kill switch |
| Max daily trades | 50-100 | Prevent over-trading |
| Max consecutive losses | 5-8 | Triggers cooldown |
| Cooldown after streak | 15-30 minutes | Let market settle |

---

## Kronos-Specific Risk Controls

### Prediction Accuracy Kill Switch

**NEW — unique to Kronos architecture.** If the model's rolling prediction accuracy drops below a threshold, the bot auto-pauses:

| Metric | Threshold | Action |
|--------|-----------|--------|
| Directional accuracy (last 50 preds) | < 45% | ⚠️ Reduce lot to 0.5x |
| Directional accuracy (last 50 preds) | < 40% | 🛑 Pause bot + alert |
| Rolling MAE spike (3x baseline) | Triggered | ⚠️ Alert + review |
| Prediction variance suddenly low | Triggered | ⚠️ Model may be broken (predicting flat) |

### Why This Matters

Kronos was fine-tuned on historical Deriv data. If Deriv changes their CSRNG algorithm or the index behavior drifts, prediction accuracy will degrade. These kill switches catch that automatically — no manual monitoring needed.

---

## Position Sizing

### Base Stake
- Start with 0.5-1% of account per trade
- On $10,000 → $50-$100 base stake
- Never more than 2% base stake on any single trade

### Confidence Scaling (Sentinel-Driven, Kronos-Fueled)

| Confidence | Multiplier | Base $100 → Actual |
|-----------|-----------|-------------------|
| < 50% | 0x | No trade |
| 50-70% | 1x | $100 |
| 70-85% | 2x | $200 |
| 85-90% | 3x | $300 |
| 90%+ | 5x | $500 |

**Maximum single trade exposure: 5% of account** ($500 on $10K).  
Even at max confidence, we never risk more than 5% on one trade.

### Kronos Confidence → Sentinel Confidence Mapping

| Kronos Signal | Sentinel Weight | Notes |
|---------------|----------------|-------|
| Prediction variance (low = good) | 35% | Tight predictions = more confidence |
| Rolling prediction accuracy | 25% | Model performing well historically |
| Recent trade win rate | 20% | Are trades actually winning |
| Regime classification | 15% | Trending vs choppy vs normal |
| Prediction magnitude | 5% | Tiny moves not worth trading |

### Outlier Protection
- **Tight hard stops** on every trade — no exceptions
- Even in "sure situation," internal mathematical spikes can occur
- Stop-loss is non-negotiable regardless of confidence level

---

## Risk of Ruin Calculation

The bot must survive long enough for the statistical edge to play out.

**Example (with Kronos):**
- Kronos directional accuracy: 58% (after fine-tuning)
- Average win: $90
- Average loss: $100
- Risk per trade: 1%

Risk of ruin at these parameters: **~1%**

If Kronos accuracy drops to 52%: risk of ruin jumps to ~8%. This is why the prediction accuracy kill switch matters.

---

## Safety Rules (Non-Negotiable)

1. **Fine-tune first** — no trading with vanilla Kronos on Deriv data
2. **Demo first** — minimum 1 month of paper trading with fine-tuned model
3. **Small start** — smallest viable deposit when going live
4. **Never add money to a losing bot** — fix the bot (or retrain Kronos) first
5. **Daily review** — check bot performance every day, not just when winning
6. **No autotrading blind** — always have manual override / kill ability
7. **Outlier spikes** — tight hard stops on every trade, even "sure situations"
8. **Kronos drift detection** — if accuracy drops below baseline, retrain before continuing
9. **Walk-forward validate every retrain** — never deploy without backtesting first

---

## The "No Set and Forget" Rule

This system is an **Autonomous Hedge Fund**, not passive income.

| Activity | Frequency |
|----------|-----------|
| Check performance | Daily |
| Check Kronos prediction accuracy | Daily |
| Review regime/threshold calibration | Weekly |
| Retrain Kronos model | Monthly or when accuracy drops |
| Full strategy review | Quarterly |
| Infrastructure check | Weekly (VPS, API status, logs) |

---

## Open Questions

- Exact account size to start
- Which indices (affects volatility and optimal stake sizing)
- Contract types — Rise/Fall recommended (directional, fits Kronos predictions)
- Minimum number of demo trades before going live?
- Exact drawdown trigger values (calibrate during demo)
