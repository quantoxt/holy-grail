Comprehensive List of Fixes Needed
1. Signal Generation & Validation Fixes
Plausibility Caps (Hard Rejection): Implement hard filter to reject predictions where predicted magnitude exceeds realistic asset volatility (>1.5% for Forex/Metals) to prevent unrealistic predictions like 5% moves on EURUSD
Ensemble Averaging: Change inference logic from single Monte Carlo sample to multiple samples (N=50) with averaging to reduce variance and noise
Per-Instrument Calibration: Stop applying BTCUSD-trained model to other assets; implement calibration layer or separate validation thresholds for XAUUSD, XAGUSD, and EURUSD

2. Risk Management & Stop Loss Fixes
Decouple Stop Loss from Prediction: Replace current SL = Entry ± (2 × Predicted Magnitude) with ATR-based stops using actual market volatility (e.g., 1.5 × ATR(14))
Dynamic Position Sizing: Recalculate lot sizes based on new ATR-based stop distance to maintain constant risk per trade (always risking 1% of equity)

3. Exit Strategy Architecture Overhaul
Implement Dynamic Take Profit: Add TP level based on predicted magnitude (Entry ± 1 × Predicted Move) or Risk:Reward ratio (1:1.5)
Replace Hard Time-Horizon: Replace 24-candle hard close with:
Momentum decay detection (close if momentum stalls/reverses)
Trailing stop engagement when in profit
Time-decay weighting (reduce confidence over time, close early if target not hit)

4. Operational & Execution Fixes
Broker Constraint Handling: Hard-code logic to respect min_lot and step_lot constraints before calculating trade size to prevent order rejections
"Kill → Confirm → Run" Protocol: Formalize restart sequence to ensure all positions are closed and confirmed empty before reinitializing to prevent double-counting
Floating P&L Integration: Update equity calculation for Weekly Goal kill switch to include unrealized profits, stopping when true account value hits target
Priority Order
High Priority: ATR-based stop loss decoupling and plausibility caps (prevents catastrophic losses)
Medium Priority: Take profit implementation and softening hard time-horizon (improves capital efficiency)
Low Priority: Ensemble averaging and per-instrument calibration (refines performance over time)