-- 005_bot_config_rpc.sql
-- Dashboard merges PATCHes into bot_config.config (jsonb). A direct REST PATCH on the
-- `config` column REPLACES the whole jsonb; this RPC merges so the frontend can update
-- one field (e.g. active_symbols) without clobbering the rest. Called by the Vercel app.
create or replace function public.update_bot_config(patch jsonb)
returns jsonb
language sql
security definer
as $$
  update public.bot_config
     set config = config || patch, updated_at = now()
   where id = 1
   returning config;
$$;

grant execute on function public.update_bot_config(jsonb) to anon, authenticated, service_role;
