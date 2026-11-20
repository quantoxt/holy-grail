-- 014_signal_alerts.sql — Signal Mode dispatch log (one row per Telegram signal).
-- The `signals` table logs EVERY scan (incl. HOLDs); this table logs only what
-- was actually alerted, so the dashboard Signals view shows sent history, not scans.

create table if not exists public.signal_alerts (
  id              bigserial primary key,
  symbol          text not null,
  timeframe       text not null,
  market_mode     text not null,
  signal_time     timestamptz not null,
  direction       text not null,                       -- BUY | SELL
  entry_price     double precision,
  sl_price        double precision,
  tp_price        double precision,
  confidence      double precision,
  predicted_move  double precision,
  snr             double precision,
  telegram_sent   boolean default true,
  created_at      timestamptz default now()
);
create index if not exists idx_signal_alerts_time on public.signal_alerts(signal_time desc);
create index if not exists idx_signal_alerts_symbol_time on public.signal_alerts(symbol, signal_time desc);

-- RLS: same owner-only model as 012_lockdown.sql (service_role bypasses; the bot writes).
alter table public.signal_alerts enable row level security;
drop policy if exists owner_read on public.signal_alerts;
create policy owner_read on public.signal_alerts for select to authenticated
  using ((select private.is_owner()));
grant select on public.signal_alerts to authenticated;
