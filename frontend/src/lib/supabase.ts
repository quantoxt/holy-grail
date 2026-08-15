/// Supabase client — the dashboard reads/writes the cloud DB directly (no FastAPI).
/// The bot (Windows VPS) writes account_state/signals/trades/bot_config here every ~5s;
/// this client reads them. Anon key is public by design (protected by RLS, currently open).
import { createClient } from '@supabase/supabase-js'

// Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env.local (or Vercel).
// No hardcoded fallbacks — each deployment points at its OWN Supabase project.
const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(url, anonKey)

/// Merge a partial patch into bot_config.config (server-side jsonb merge via RPC).
/// A plain update would replace the whole config object — never do that.
export async function patchConfig(patch: Record<string, any>) {
  const { data, error } = await supabase.rpc('update_bot_config', { patch })
  if (error) throw error
  return data as Record<string, any>
}
