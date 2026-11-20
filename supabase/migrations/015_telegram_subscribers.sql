-- 015_telegram_subscribers.sql — Telegram command-center subscribers.
-- The bot's command poller (shared/telegram_commands.py) reads/writes this
-- table: who receives signal/trade alerts, who muted, who the owner is.
-- Owner = the TELEGRAM_CHAT_ID from the bot env (ensured on boot).

create table if not exists public.telegram_subscribers (
  chat_id     bigint primary key,                -- Telegram chat id (users AND groups)
  status      text not null default 'active',    -- active | inactive (/unsubscribe keeps history)
  muted       boolean not null default false,    -- /pause notifications (proactive alerts off)
  is_owner    boolean not null default false,    -- env chat: /subscribers + /broadcast
  note        text not null default '',          -- e.g. first name / group title
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- RLS: same owner-only model as 012_lockdown.sql (service_role bypasses; the bot writes).
alter table public.telegram_subscribers enable row level security;
drop policy if exists owner_read on public.telegram_subscribers;
create policy owner_read on public.telegram_subscribers for select to authenticated
  using ((select private.is_owner()));
grant select on public.telegram_subscribers to authenticated;
