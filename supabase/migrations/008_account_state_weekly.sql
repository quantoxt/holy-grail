-- Weekly goal card: broker-realized weekly P&L written by the bot heartbeat.
-- Fixes the dashboard gap where the recomputed-from-trades-table number
-- diverged from the account balance (swap/commission + estimate drift).
alter table account_state add column if not exists weekly_pnl double precision;
