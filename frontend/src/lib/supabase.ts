/// Supabase client — the dashboard reads/writes the cloud DB directly (no FastAPI).
/// The bot (Windows VPS) writes account_state/signals/trades/bot_config here every ~5s;
/// this client reads them. Anon key is public by design (protected by RLS, currently open).
import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL || 'https://gpfudbncpmaabnszmztt.supabase.co'
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY ||
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwZnVkYm5jcG1hYWJuc3ptenR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYyNjM1MTYsImV4cCI6MjEwMTgzOTUxNn0.rngWUQdtfw-xQ5DXWDhBk0AIHuTWtfKs4Y_QKe4Rinc'

export const supabase = createClient(url, anonKey)

/// Merge a partial patch into bot_config.config (server-side jsonb merge via RPC).
/// A plain update would replace the whole config object — never do that.
export async function patchConfig(patch: Record<string, any>) {
  const { data, error } = await supabase.rpc('update_bot_config', { patch })
  if (error) throw error
  return data as Record<string, any>
}
