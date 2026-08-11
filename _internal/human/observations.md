# HUMAN OBSERVATIONS AND THOUGHTS

This bot is **time based.** The prediction terminates the position at "Horizon". This is a good way IF the bot gets most of it's predictions right, but improvements can be made to enhance this. Here's one chain of thoughts that I got from Qwen:

"Yes, a bot that accurately predicts market direction for XAUUSD and XAGUSD over 2-hour periods could work, but your current time-based exit strategy has critical flaws. Even with high directional accuracy, markets rarely move in straight lines - they can reach your target, reverse below your stop loss, then recover to your prediction. This creates losing trades despite correct predictions. Additionally, holding positions until the full 2-hour period ends wastes opportunity when targets are hit early. For a solid system, keep your time-based approach but add dynamic take profits - lock profit with dymanic SL immediately when your predicted price level is reached, rather than waiting the full duration. This addresses both the path dependency risk and capital efficiency issues."

Something concerning the Confidence of signals generated and trades taken. So far, 10 trades have been taken of which 6 have been closed. Out of the closed 6, 4 trades won, 2 trades lost. Here is the breakdown:

[10/08/2026 13:50] Holy Grail ✝️: 📡 OPEN AUDUSD SELL
Lot: 0.01 | Risk @SL: $5.86
Confidence: 46% | Entry: 0.71
[10/08/2026 14:12] Holy Grail ✝️: 📡 OPEN GBPUSD SELL
Lot: 0.01 | Risk @SL: $10.48
Confidence: 43% | Entry: 1.35
[10/08/2026 16:13] Holy Grail ✝️: 📡 OPEN NZDUSD SELL
Lot: 0.01 | Risk @SL: $6.16
Confidence: 58% | Entry: 0.59
[10/08/2026 16:54] Holy Grail ✝️: 🔴 CLOSE AUDUSD SELL (horizon)
P&L: $-0.69 (LOSS ❌)
Balance: $499.46
Weekly P&L: $-0.69 / $14.00
[10/08/2026 17:16] Holy Grail ✝️: 🔴 CLOSE GBPUSD SELL (horizon)
P&L: $-2.26 (LOSS ❌)
Balance: $497.33
Weekly P&L: $-2.95 / $14.00
[10/08/2026 17:32] Holy Grail ✝️: 📡 OPEN AUDUSD SELL
Lot: 0.01 | Risk @SL: $7.89
Confidence: 62% | Entry: 0.71
[10/08/2026 17:32] Holy Grail ✝️: 📡 OPEN GBPUSD SELL
Lot: 0.01 | Risk @SL: $13.13
Confidence: 54% | Entry: 1.35
[10/08/2026 18:06] Holy Grail ✝️: 🟢 CLOSE USDCHF BUY (horizon)
P&L: $+0.30 (WIN ✅)
Balance: $497.70
Weekly P&L: $-2.65 / $14.00
[10/08/2026 18:22] Holy Grail ✝️: 📡 OPEN EURUSD SELL
Lot: 0.01 | Risk @SL: $12.33
Confidence: 59% | Entry: 1.15
[10/08/2026 19:06] Holy Grail ✝️: 🟢 CLOSE NZDUSD SELL (horizon)
P&L: $+0.56 (WIN ✅)
Balance: $498.16
Weekly P&L: $-2.09 / $14.00
[10/08/2026 19:08] Holy Grail ✝️: 📡 OPEN NZDUSD SELL
Lot: 0.02 | Risk @SL: $7.48
Confidence: 35% | Entry: 0.59
[10/08/2026 20:24] Holy Grail ✝️: 🟢 CLOSE AUDUSD SELL (horizon)
P&L: $+0.84 (WIN ✅)
Balance: $498.68
Weekly P&L: $-1.25 / $14.00
[10/08/2026 20:24] Holy Grail ✝️: 🟢 CLOSE GBPUSD SELL (horizon)
P&L: $+1.49 (WIN ✅)
Balance: $499.95
Weekly P&L: $0.24 / $14.00
[10/08/2026 20:57] Holy Grail ✝️: 📡 OPEN GBPUSD SELL
Lot: 0.03 | Risk @SL: $9.54
Confidence: 38% | Entry: 1.35
[10/08/2026 21:11] Holy Grail ✝️: 📡 OPEN XAUUSD BUY
Lot: 0.01 | Risk @SL: $20.10
Confidence: 100% | Entry: 4387.19
[10/08/2026 21:32] Holy Grail ✝️: 📡 OPEN XAGUSD BUY
Lot: 0.01 | Risk @SL: $25.53
Confidence: 100% | Entry: 65.84
[10/08/2026 23:36] Holy Grail ✝️: 🔴 CLOSE EURUSD SELL (horizon)
P&L: $-0.12 (LOSS ❌)
Balance: $499.76
Weekly P&L: $-0.12 / $14.00
[10/08/2026 23:36] Holy Grail ✝️: 🟢 CLOSE NZDUSD SELL (horizon)
P&L: $+0.02 (WIN ✅)
Balance: $499.70
Weekly P&L: $-0.10 / $14.00
[10/08/2026 23:43] Holy Grail ✝️: 🔴 CLOSE GBPUSD SELL (horizon)
P&L: $-0.03 (LOSS ❌)
Balance: $499.60
Weekly P&L: $-0.13 / $14.00
[10/08/2026 23:45] Holy Grail ✝️: 📡 OPEN GBPUSD SELL
Lot: 0.06 | Risk @SL: $9.54
Confidence: 52% | Entry: 1.35
[10/08/2026 23:45] Holy Grail ✝️: 📡 OPEN NZDUSD SELL
Lot: 0.09 | Risk @SL: $9.21
Confidence: 45% | Entry: 0.59
[10/08/2026 23:57] Holy Grail ✝️: 🟢 CLOSE XAUUSD BUY (horizon)
P&L: $+13.07 (WIN ✅)
Balance: $512.15
Weekly P&L: $12.94 / $14.00
[10/08/2026 23:59] Holy Grail ✝️: 📡 OPEN XAUUSD BUY
Lot: 0.01 | Risk @SL: $19.84
Confidence: 62% | Entry: 4400.36
[11/08/2026 00:00] Holy Grail ✝️: 🟢 CLOSE XAGUSD BUY (weeklygoalbanked)
P&L: $+2.00 (WIN ✅)
Balance: $513.65
Weekly P&L: $14.94 / $14.00
[11/08/2026 00:00] Holy Grail ✝️: 🔴 CLOSE AUDUSD SELL (weeklygoalbanked)
P&L: $-2.16 (LOSS ❌)
Balance: $513.31
Weekly P&L: $12.78 / $14.00
[11/08/2026 00:00] Holy Grail ✝️: 🔴 CLOSE GBPUSD SELL (weeklygoalbanked)
P&L: $-0.72 (LOSS ❌)
Balance: $513.17
Weekly P&L: $12.06 / $14.00
[11/08/2026 00:00] Holy Grail ✝️: 🔴 CLOSE NZDUSD SELL (weeklygoalbanked)
P&L: $-0.45 (LOSS ❌)
Balance: $513.03
Weekly P&L: $11.61 / $14.00
[11/08/2026 00:00] Holy Grail ✝️: 🟢 CLOSE XAUUSD BUY (weeklygoalbanked)
P&L: $+0.62 (WIN ✅)
Balance: $514.87
Weekly P&L: $12.23 / $14.00

From my observation, trades with confidence below 50% seem to close at a loss after the 2hrs elapses. If this is valid, then it will be solid to filter out trades whose confidence levels are low.

