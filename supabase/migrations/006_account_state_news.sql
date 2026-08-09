-- 006_account_state_news.sql
-- News-blackout status published by the bot's heartbeat so the dashboard can show
-- a banner without calling the Python news module itself.
alter table public.account_state
  add column if not exists news_blackout boolean default false,
  add column if not exists news_reason text default '';

grant all on public.account_state to service_role, anon, authenticated;
