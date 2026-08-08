# Forex Trading Bot – Weekly $14 Goal on $50 Account  
## Micro Risk Calculations & Hard Stop Logic

---

## 1. Weekly Logic
- **Monday 00:00 broker time**: reset `weekly_pnl = 0`, set `trading_allowed = True`.
- After any trade closes: update `weekly_pnl`.
- If `weekly_pnl >= $14` → `trading_allowed = False` for the rest of the week.
- End of week (Friday close): if `weekly_pnl < $14`, accept the result, do nothing.
- Manual withdrawal of profit; account returns to $50 for the next week.

---

## 2. Risk Guardrails
These protect the account from a single bad day.

| Parameter               | Value    | Reason                                    |
|-------------------------|----------|-------------------------------------------|
| Max risk per trade      | $1.00    | 2% of $50 – low ruin risk                 |
| Max daily loss          | $3.00    | 6% of account – forces a cool‑off         |
| Max open positions      | 2        | limits correlated exposure                |
| Min Reward:Risk ratio   | 3:1      | needed to hit $14 with a 50% win rate     |
| Max weekly drawdown     | $10      | stops trading if equity ≤ $40             |

**Math behind 3:1 with $1 risk**  
With 50% win rate: 14 trades → (7 × $3) – (7 × $1) = $21 – $7 = $14.  
Higher win rate → fewer trades required.

---

## 3. Position Sizing – Micro Calculations per Symbol

### General Formula
```
lot_size = risk_per_trade / (sl_points * point_value_per_lot)
```
Where `sl_points` = stop‑loss distance in the symbol’s smallest price increment,  
`point_value_per_lot` = $ value of 1 point movement for 1 standard lot.

### 3.1 XAUUSD (Gold)
- Standard lot: 100 oz  
- 1 point = 0.01 price move → **value = $1 per lot**
- **Example**: SL = 50 points (e.g., 1900.00 → 1899.50)  
  `lot_size = 1.00 / (50 * 1) = 0.02 lots` (2 micro lots / 2 oz)  
- Minimum tradeable: typically 0.01 lot → perfect.

### 3.2 XAGUSD (Silver)
- Standard lot: 5000 oz  
- 1 point = 0.01 → **value = $50 per lot**  
- **Problem**: $1 risk requires very tight stops and fractional lots below broker minimums.
- **Solution**:  
  - Only trade silver with tight technical stops, or  
  - Raise risk to $2 for silver trades.  
  - Example: SL = 4 points (0.04) → `lot_size = 2 / (4*50) = 0.01 lots` (minimum).  
  - If broker allows 0.001 lots, $1 risk with SL = 20 points (0.20) → `1/(20*50) = 0.001 lots`.  
- **Bot priority**: Gold and Bitcoin first, silver only when signal demands a very tight stop.

### 3.3 BTCUSDT (Bitcoin)
- Usually 1 lot = 1 BTC, price change by $1 → **point value = $1 per lot** (if USDT quoted to two decimals).
- **Example**: SL = 1000 points ($10 move)  
  `lot_size = 1.00 / (1000 * 1) = 0.001 lots` (0.001 BTC)  
- Most crypto brokers allow 0.001 increment → feasible.  
- If minimum lot = 0.01, must use SL = 100 points (100 * $0.01 = $1) → `lot_size = 1/100 = 0.01 lots`.

---

## 4. Dynamic Adjustments (Bot Flexibility)
- **Time‑weighted aggression** (Thursday): If `weekly_pnl < $7`, risk can increase to **$1.50** (3%) only on A‑grade signals. Never exceed 5% risk.
- **Pair filter**: Remove XAGUSD from watchlist when lot size calculation fails the minimum trade size.
- **Correlation check**: If XAUUSD and XAGUSD signal simultaneously, take only the stronger one.
- **Compounding rule**: Risk is always based on original $50 starting equity (no intra‑week compounding) to prevent giving back gains.

---

## 5. Hard Stop – Python Skeleton

```python
def calculate_lot_size(symbol, sl_points, risk_amount):
    point_values = {
        'XAUUSD': 1.0,
        'XAGUSD': 50.0,
        'BTCUSDT': 1.0
    }
    pv = point_values[symbol]
    lot = risk_amount / (sl_points * pv)
    # round down to broker allowed step
    return round_down(lot, symbol)

def weekly_trade_cycle():
    weekly_pnl = 0
    daily_loss = 0
    while market_open() and weekly_pnl < 14 and account_equity() > 40:
        signal = kronos_ai.get_signal()   # returns symbol, entry, sl, tp
        if signal is None: continue

        sl_points = abs(signal.entry - signal.sl) / symbol_point_size(signal.symbol)
        risk = 1.0
        if day_of_week() >= 4 and weekly_pnl < 7:
            risk = 1.5 if signal.confidence > 0.9 else 1.0

        if risk > daily_loss_limit_left():
            continue

        lot = calculate_lot_size(signal.symbol, sl_points, risk)
        if lot < min_lot(signal.symbol): continue

        # Execute trade...
        # After close, update weekly_pnl, daily_loss, check guards
```

---

## 6. Quick‑Reference Calculations Table

| Calculation                    | Formula / Value                             |
|--------------------------------|---------------------------------------------|
| SL distance in points          | `abs(entry - sl) / tick_size`               |
| Lot size (XAUUSD)              | `risk / (sl_points * 1.0)`                  |
| Lot size (XAGUSD)              | `risk / (sl_points * 50.0)`                 |
| Lot size (BTCUSDT)             | `risk / (sl_points * 1.0)`                  |
| Weekly target in R multiples   | `14 / risk_per_trade` = 14R (if $1 risk)    |
| Maximum trades needed (50% WR) | 14                                           |
| Lot rounding                   | Always floor to broker step (0.01 / 0.001)  |
```
