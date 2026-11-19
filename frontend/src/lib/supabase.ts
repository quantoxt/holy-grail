/// Supabase client — the dashboard reads/writes the cloud DB directly (no API server).
/// Access is locked down (migration 012): anon sees nothing; a signed-in OWNER
/// (private.app_owner) can read every table, and writes go through owner-checked RPCs.
import { createClient } from '@supabase/supabase-js'

// Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env.local (or the host).
const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(url, anonKey)

/// Merge a partial patch into bot_config.config (server-side jsonb merge via RPC).
export async function patchConfig(patch: Record<string, any>) {
  const { data, error } = await supabase.rpc('update_bot_config', { patch })
  if (error) throw error
  return data as Record<string, any>
}

// --- MT5 accounts (password is write-only: no read path exists) ---
export async function addMt5Account(a: { name: string; login: number; password: string; server: string; broker?: string }) {
  const { error } = await supabase.rpc('add_mt5_account', {
    p_name: a.name, p_login: a.login, p_password: a.password, p_server: a.server, p_broker: a.broker ?? '',
  })
  if (error) throw error
}
export async function setActiveMt5Account(id: number) {
  const { error } = await supabase.rpc('set_active_mt5_account', { p_id: id })
  if (error) throw error
}
export async function deleteMt5Account(id: number) {
  const { error } = await supabase.rpc('delete_mt5_account', { p_id: id })
  if (error) throw error
}
