# Risk Management — Financial Projections & Safety

---

## Financial Targets

### Conservative Estimates ($10,000 Account)

| Scenario | Monthly ROI | Dollar Amount | Notes |
|----------|-------------|---------------|-------|
| Bad month | 0-3% | $0 - $300 | Regime unfavorable, bot mostly paused |
| Average month | 5-8% | $500 - $800 | Normal conditions |
| Good month | 8-12% | $800 - $1,200 | Favorable regime, high confidence signals |
| Exceptional | 12-15% | $1,200 - $1,500 | Everything aligns |

### Key Variables
- **Market Regime** — biggest factor, determines if bot trades at all
- **Execution Latency** — mitigated by VPS near Deriv servers
- **Slippage** — always exists, minimized by good infrastructure
- **Model Accuracy** — regime detection accuracy directly affects profit

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
| 10-15% | Lot size to 0.25x, review strategy parameters |
| 15-20% | **Hard stop** — pause bot, review, retrain if needed |
| > 20% | **Emergency stop** — manual intervention required |

### Daily Limits

| Parameter | Value (Example) | Notes |
|-----------|----------------|-------|
| Max daily loss | 3-5% of account | Hard kill switch |
| Max daily trades | 50-100 | Prevent over-trading |
| Max consecutive losses | 5-8 | Triggers cooldown |
| Cooldown after streak | 15-30 minutes | Let market settle |

---

## Position Sizing

### Base Stake
- Start with 0.5-1% of account per trade
- On $10,000 → $50-$100 base stake
- Never more than 2% base stake on any single trade

### Confidence Scaling (Sentinel-Driven)

| Confidence | Multiplier | Base $100 → Actual |
|-----------|-----------|-------------------|
| < 50% | 0x | No trade |
| 50-70% | 1x | $100 |
| 70-85% | 2x | $200 |
| 85-90% | 3x | $300 |
| 90%+ | 5x | $500 |

**Maximum single trade exposure: 5% of account** ($500 on $10K).  
Even at max confidence, we never risk more than 5% on one trade.

### Outlier Protection
- **Tight hard stops** on every trade — no exceptions
- Even in "sure situation," internal mathematical spikes can occur
- Stop-loss is non-negotiable regardless of confidence level

---

## Risk of Ruin Calculation

The bot must survive long enough for the statistical edge to play out.

**Example:**
- Win rate: 55%
- Average win: $90
- Average loss: $100
- Risk per trade: 1%

Risk of ruin (losing entire account) at these parameters: **~2%**

If win rate drops to 50%: risk of ruin jumps significantly. This is why the kill switches matter.

---

## Safety Rules (Non-Negotiable)

1. **Demo first** — minimum 1 month of paper trading with real data
2. **Small start** — smallest viable deposit when going live
3. **Never add money to a losing bot** — fix the bot first
4. **Daily review** — check bot performance every day, not just when winning
5. **No autotrading blind** — always have manual override / kill ability
6. **Outlier spikes** — tight hard stops on every trade, even "sure situations"
7. **Regime drift** — if bot was profitable last month but not this month, retrain models

---

## The "No Set and Forget" Rule

This system is an **Autonomous Hedge Fund**, not passive income.

| Activity | Frequency |
|----------|-----------|
| Check performance | Daily |
| Review regime accuracy | Weekly |
| Retrain ML models | Monthly or after regime drift detected |
| Full strategy review | Quarterly |
| Infrastructure check | Weekly (VPS, API status, logs) |

## Open Questions

- Exact account size to start
- Which indices (affects volatility and optimal stake sizing)
- Contract types (affects risk profile — Rise/Fall vs Touch/No Touch have different risk profiles)
- Minimum number of demo trades before going live?
