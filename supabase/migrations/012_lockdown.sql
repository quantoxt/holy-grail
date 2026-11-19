-- 012_lockdown.sql — close the open database before the dashboard is hosted.
--
-- Before this: no RLS anywhere and `anon` held GRANT ALL on every table (002, 003,
-- 011). The anon key ships in the frontend bundle, so anyone could read MT5
-- passwords and start/stop/reconfigure the bot.
--
-- After this:
--   * anon            → nothing (no tables, no RPCs)
--   * authenticated   → read-only, and only if auth.uid() is the registered owner
--                        (private.app_owner). Writes go through owner-checked RPCs;
--                        journal_entries is the one directly-writable table.
--                        mt5_accounts.password is never readable (column grant).
--   * service_role    → unchanged (the bot; bypasses RLS)
--
-- Fail-closed: until the owner row is inserted, no logged-in user sees anything.
-- After creating your Supabase Auth user, run once (SQL editor):
--   insert into private.app_owner (user_id) values ('<your auth.users id>');

-- ── owner registry ────────────────────────────────────────────────────────────
create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;   -- policies call private.is_owner()

create table if not exists private.app_owner (
  user_id uuid primary key references auth.users (id) on delete cascade
);
revoke all on private.app_owner from public, anon, authenticated;

create or replace function private.is_owner()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from private.app_owner where user_id = (select auth.uid()));
$$;
revoke execute on function private.is_owner() from public, anon;
grant execute on function private.is_owner() to authenticated;

-- ── strip the old blanket grants ──────────────────────────────────────────────
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke execute on functions from public, anon;

-- ── RLS + owner-only read on every table ──────────────────────────────────────
do $$
declare t text;
begin
  foreach t in array array[
    'bot_config', 'account_state', 'mt5_accounts', 'kronos_predictions', 'signals',
    'trades', 'risk_events', 'bot_sessions', 'prediction_evaluations', 'journal_entries'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists owner_read on public.%I', t);
    execute format(
      'create policy owner_read on public.%I for select to authenticated using ((select private.is_owner()))', t);
    if t <> 'mt5_accounts' then
      execute format('grant select on public.%I to authenticated', t);
    end if;
  end loop;
end $$;

-- mt5_accounts: list without the password column
grant select (id, name, login, server, broker, is_active, balance, currency, created_at)
  on public.mt5_accounts to authenticated;

-- journal_entries: the dashboard edits it directly
grant insert, update, delete on public.journal_entries to authenticated;
drop policy if exists owner_write on public.journal_entries;
create policy owner_write on public.journal_entries for all to authenticated
  using ((select private.is_owner())) with check ((select private.is_owner()));

-- ── owner-checked write RPCs ──────────────────────────────────────────────────
create or replace function public.update_bot_config(patch jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare result jsonb;
begin
  if not private.is_owner() then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  update public.bot_config
     set config = config || patch, updated_at = now()
   where id = 1
   returning config into result;
  return result;
end;
$$;

create or replace function public.add_mt5_account(
  p_name text, p_login bigint, p_password text, p_server text, p_broker text default '')
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare new_id bigint;
begin
  if not private.is_owner() then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  insert into public.mt5_accounts (name, login, password, server, broker)
  values (p_name, p_login, p_password, p_server, coalesce(p_broker, ''))
  returning id into new_id;
  return new_id;
end;
$$;

create or replace function public.set_active_mt5_account(p_id bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not private.is_owner() then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  update public.mt5_accounts set is_active = (id = p_id);
end;
$$;

create or replace function public.delete_mt5_account(p_id bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not private.is_owner() then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  delete from public.mt5_accounts where id = p_id;
end;
$$;

revoke execute on function public.update_bot_config(jsonb)                      from public, anon;
revoke execute on function public.add_mt5_account(text, bigint, text, text, text) from public, anon;
revoke execute on function public.set_active_mt5_account(bigint)                from public, anon;
revoke execute on function public.delete_mt5_account(bigint)                    from public, anon;
grant  execute on function public.update_bot_config(jsonb)                      to authenticated, service_role;
grant  execute on function public.add_mt5_account(text, bigint, text, text, text) to authenticated, service_role;
grant  execute on function public.set_active_mt5_account(bigint)                to authenticated, service_role;
grant  execute on function public.delete_mt5_account(bigint)                    to authenticated, service_role;
