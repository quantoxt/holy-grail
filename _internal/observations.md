The bot picking up trades last night at about 11pm my time. These are my observations on the trading

 - OBSERVATION 1: The risk calculation is totally off because the size of one small lot size is not the same across all symbols. 0.01 on XAGUSD is not the same as XAGUSD on USDJPY. How do we go about this contract size difference across the pairs cocnerning the small account size? There were times during the trade where the floating P&L was -38 dollars, and the SL was set at a place on the XAGUSD chart where the calculation was about -100 dollars. The account would have blown before hitting the SL.That also brings up the reason to check HOW the SL is calculated. The SL might be calculated correctly, but remember different symbols should trigger different SL positions if the actual risk of $1 is to be maintianed. This also brings up the reasoning of: How will a SL of $1 be maintained of XAGUSD and XAUUSD because it's too small and will get triggered easily. Options for solution to the problem above are: Precise tiny scalping on XAUUSD and XAGUSD, where the $1 or $1.5 SL is maintained, and a TP of >$1 but  <$3. Second Option is Moving Towards trading forex pairs whose contracts are smaller than that of metals. You can pitch in your option as well.
 
-  OBSERVATION 2: The bot held the trade positions even when the one floating P&L was over $14, which is the weekly profit target. Apart from SL, what else will trigger when the bot should close a trade? The bot's goal is the $14 profit. If the floating P&L is even $10 or close to $14 why didn't it terminate the trade for the day and find another time to complete the remaining and rest for the week?

- OBSERVATION 3: I woke up in the middle of the night, there was wifi but no internet access. Before I rechargeed the wifi with data, this is what I observed from the open trades.
More than 14$ was made in a single trade and the bot didn't terminate the trade. The XAGUSD trade was terminated by something else at -$7.45, which should be investigated because that is nothing close to the SL so why was that position terminated?
I terminated the XAUUSD position at $18.46.

- OBSERVATION 4: Connection to the internet has been restored, but the dashboard is still stuck at two open trades. The dashboard is not picking up the new account balance and details. A bot restart was done from the dashboard but nothing changed on the dashboard.

- OBSERVATION 5: The dashboard on mobile is HIGHLY unresponsive to mobile screens. That should be fixed ASAP.

===MY INSTINCT===
I suspect that the bot was killed at some point in all of this. I suspect at the point of loss of internet connection (note that I terminated the XAUUSD position BEFORE restoring Internet access). So after the Internet was restored, the bot could not update the dashboard anymore.