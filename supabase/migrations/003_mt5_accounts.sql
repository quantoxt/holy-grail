-- 003_mt5_accounts.sql — broker accounts stored in Supabase (dashboard-managed).

create table if not exists public.mt5_accounts (
  id          serial primary key,
  name        text not null,          -- user-friendly label (e.g. "IC Markets Demo")
  login       bigint not null,
  password    text not null,
  server      text not null,          -- broker server (e.g. "MetaQuotes-Demo")
  broker      text default '',        -- broker name for display
  is_active   boolean default false,  -- only one active at a time
  balance     float default 0,        -- cached balance for display
  currency    text default 'USD',
  created_at  timestamptz default now()
);

create index if not exists idx_mt5_active on public.mt5_accounts(is_active);

grant all on public.mt5_accounts to service_role, anon, authenticated;
grant all on public.mt5_accounts_id_seq to service_role, anon, authenticated;
