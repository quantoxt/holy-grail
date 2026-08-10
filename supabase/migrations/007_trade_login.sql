-- Per-account trade attribution. Each bot trade is tagged with the MT5 login that
-- opened it, so the dashboard can scope stats/history to the ACTIVE account. A
-- newly-connected account the bot has never traded starts at a clean slate — no
-- P&L/wins/losses carry over from a prior account. Existing rows are backfilled to
-- the account that made them (the abandoned MetaQuotes demo).
alter table public.trades add column if not exists mt5_login bigint;

-- backfill: the only trades so far belong to the MetaQuotes demo (login 5054187279)
update public.trades set mt5_login = 5054187279 where mt5_login is null;
