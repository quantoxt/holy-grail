-- 013_fix_set_active_account.sql — cloud Supabase runs pg_safeupdate, which rejects
-- an UPDATE without a WHERE clause ("UPDATE requires a WHERE clause"). 012's
-- set_active_mt5_account flipped every row in one unqualified UPDATE; scope it to
-- the rows that actually change instead. Same behaviour, same owner check.
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
  update public.mt5_accounts
     set is_active = (id = p_id)
   where is_active or id = p_id;
end;
$$;

revoke execute on function public.set_active_mt5_account(bigint) from public, anon;
grant  execute on function public.set_active_mt5_account(bigint) to authenticated, service_role;
