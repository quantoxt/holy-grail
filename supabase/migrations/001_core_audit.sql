-- 001_core_audit.sql
-- Core audit tables for the Holy Grail live bot. Adapted from blueprint/04-database-design
-- for LIVE markets (symbol-agnostic, market_mode, pre-trained Kronos). Every decision the
-- bot makes is logged here — the prediction → signal → trade → risk chain.

--.extensions
create extension if not exists "pgcrypto";

-- ============ kronos_predictions (central audit: every Kronos inference) ============
create table if not exists public.kronos_predictions (
  id              bigserial primary key,
  symbol          text not null,
  timeframe       text not null,
  market_mode     text not null,                       -- crypto | forex
  candle_time     timestamptz not null,                -- time of the candle that triggered prediction
  model_version   text not null,                       -- e.g. 'NeoQuasar/Kronos-small'
  lookback        integer not null,
  pred_len        integer not null,
  sample_count    integer default 1,
  predictions     jsonb not null,                      -- [{open,high,low,close,...}, ...]
  predicted_close float,                               -- close at h=pred_len (the validated horizon)
  predicted_direction text,                            -- UP | DOWN
  predicted_magnitude double precision,
  actual_close    float,                               -- filled when the horizon elapses
  prediction_error double precision,
  direction_correct boolean,
  inference_ms    integer,
  created_at      timestamptz default now()
);
create index if not exists idx_kp_symbol_time on public.kronos_predictions(symbol, candle_time);
create index if not exists idx_kp_created on public.kronos_predictions(created_at);

-- ============ signals (Soldier's BUY/SELL/HOLD) ============
create table if not exists public.signals (
  id              bigserial primary key,
  symbol          text not null,
  timeframe       text not null,
  market_mode     text not null,
  signal_time     timestamptz not null,
  direction       text not null,                       -- BUY | SELL | HOLD
  confidence      double precision,                    -- 0..1
  predicted_move  double precision,
  current_close   float,
  predicted_close float,
  horizon         integer,
  regime          text,                                -- trending | normal | choppy (Watcher)
  regime_filtered boolean default false,               -- suppressed by regime/confidence?
  created_at      timestamptz default now()
);
create index if not exists idx_signals_time on public.signals(signal_time);

-- ============ trades (executed — paper or live) ============
create table if not exists public.trades (
  id              bigserial primary key,
  symbol          text not null,
  market_mode     text not null,
  paper           boolean default true,
  direction       text not null,                       -- BUY | SELL
  entry_price     float,
  exit_price      float,
  entry_time      timestamptz,
  exit_time       timestamptz,
  size            double precision,                    -- USDT notional
  lots            double precision,                    -- MT5 lots (forex) / contracts (crypto)
  pnl             double precision,
  confidence      double precision,
  regime          text,
  horizon         integer,
  result          text,                                -- win | loss | open | sold
  provider_ticket text,                                -- broker/exchange ticket
  created_at      timestamptz default now()
);
create index if not exists idx_trades_time on public.trades(entry_time);

-- ============ risk_events (Sentinel decisions) ============
create table if not exists public.risk_events (
  id              bigserial primary key,
  event_type      text not null,                       -- kill_switch | lot_scale | cooldown | daily_limit | drift
  reason          text not null,
  data            jsonb,
  lot_before      double precision,
  lot_after       double precision,
  created_at      timestamptz default now()
);
create index if not exists idx_risk_time on public.risk_events(created_at);

-- ============ bot_sessions (lifecycle) ============
create table if not exists public.bot_sessions (
  id              bigserial primary key,
  started_at      timestamptz not null,
  stopped_at      timestamptz,
  mode            text not null,                       -- paper | demo | live
  market_mode     text not null,
  symbols         text[],
  model_version   text,
  initial_balance float,
  final_balance   float,
  total_trades    integer default 0,
  wins            integer default 0,
  losses          integer default 0,
  net_profit      double precision,
  notes           text
);
