-- Net P&L card: broker-truth all-time realized P&L (deal history, incl.
-- swap/commission) written by the bot heartbeat. Replaces the dashboard's
-- trades-table estimate (12.57) which drifted from the broker's 14.87.
alter table account_state add column if not exists realized_pnl double precision;
