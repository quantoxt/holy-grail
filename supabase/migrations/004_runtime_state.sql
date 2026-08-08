-- 004_runtime_state.sql — cross-process runtime config + live account telemetry.
--
-- WHY: the API (dashboard writer) and the bot (soldier.loop reader) are separate
-- processes. RuntimeConfig used to be in-memory only, so dashboard edits never
-- reached a running bot. These two tables are the shared source of truth:
--   * bot_config   — single row (id=1); API writes, bot reads each cycle (hot-reload).
--   * account_state — one row per MT5 login; bot writes a ~5s heartbeat, API/dashboard read.

-- ============ bot_config (dashboard-adjustable params, single row) ============
create table if not exists public.bot_config (
  id          smallint primary key default 1,
  config      jsonb not null,                -- full RuntimeConfig snapshot
  updated_at  timestamptz default now(),
  constraint bot_config_singleton check (id = 1)
);

-- seed the singleton with sensible defaults if it doesn't exist
insert into public.bot_config (id, config)
values (1, jsonb_build_object(
  'weekly_goal', 14.0,
  'baseline_equity', 50.0,
  'withdraw_profit_weekly', true,
  'max_risk_per_trade', 1.0,
  'max_daily_loss', 3.0,
  'max_weekly_drawdown', 10.0,
  'max_open_positions', 2,
  'sl_multiplier', 2.0,
  'thursday_aggression', true,
  'thursday_threshold', 7.0,
  'thursday_risk', 1.5,
  'min_confidence_for_boost', 0.9,
  'correlation_filter', true,
  'correlated_pairs', jsonb_build_array(jsonb_build_array('XAUUSD','XAGUSD')),
  'news_blackout_enabled', true,
  'news_blackout_pre_min', 30,
  'news_blackout_post_min', 15,
  'bot_running', true,
  'trading_paused', false,
  'active_symbols', jsonb_build_array('XAUUSD','XAGUSD','EURUSD','GBPUSD')
))
on conflict (id) do nothing;

-- ============ account_state (live account telemetry, one row per login) ============
create table if not exists public.account_state (
  login         bigint primary key,          -- MT5 login (matches mt5_accounts.login)
  broker        text default '',
  balance       double precision default 0,
  equity        double precision default 0,
  currency      text default 'USD',
  floating_pnl  double precision default 0,  -- sum of open-position profit (acct ccy)
  open_positions jsonb default '[]',         -- [{symbol, type, volume, entry, profit}, ...]
  symbols       jsonb default '[]',          -- broker-discovered tradeable symbols
  updated_at    timestamptz default now()
);

grant all on public.bot_config   to service_role, anon, authenticated;
grant all on public.account_state to service_role, anon, authenticated;
