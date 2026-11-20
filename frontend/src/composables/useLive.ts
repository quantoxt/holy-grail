/// One shared 5s poll for everything the cockpit shows. Views read these refs
/// instead of each running their own timer.
import { ref, computed } from 'vue'
import { supabase } from '../lib/supabase'

export const STALE_MS = 30_000

const config = ref<Record<string, any>>({})
const account = ref<Record<string, any>>({})
const trades = ref<any[]>([])
const signals = ref<any[]>([])
const signalAlerts = ref<any[]>([])
const riskEvents = ref<any[]>([])
const now = ref(Date.now())
const loaded = ref(false)
let timer: number | undefined
let users = 0

async function refresh() {
  now.value = Date.now()
  try {
    const [cfg, acct, tr, sig, alerts, risk] = await Promise.all([
      supabase.from('bot_config').select('config').eq('id', 1).limit(1),
      supabase.from('account_state').select('*').order('updated_at', { ascending: false }).limit(1),
      supabase.from('trades').select('*').order('created_at', { ascending: false }).limit(1000),
      supabase.from('signals').select('*').order('signal_time', { ascending: false }).limit(20),
      supabase.from('signal_alerts').select('*').order('signal_time', { ascending: false }).limit(100),
      supabase.from('risk_events').select('*').order('created_at', { ascending: false }).limit(20),
    ])
    config.value = (cfg.data?.[0]?.config as Record<string, any>) || {}
    account.value = acct.data?.[0] || {}
    // scope history to the ACTIVE account — a new account starts with a clean slate
    const login = account.value?.login
    trades.value = (tr.data || []).filter((t) => !login || Number(t.mt5_login) === Number(login))
    signals.value = sig.data || []
    // signal_alerts table ships with migration 014 — tolerate backends that predate it
    signalAlerts.value = (alerts as any)?.data || []
    riskEvents.value = risk.data || []
  } catch { /* keep last good values */ }
  loaded.value = true
}

export function useLive() {
  if (users++ === 0) {
    refresh()
    timer = window.setInterval(refresh, 5000)
  }
  const stop = () => {
    if (--users === 0 && timer) { clearInterval(timer); timer = undefined }
  }

  const heartbeatAge = computed(() => {
    const ts = account.value?.updated_at
    if (!ts) return null
    const age = now.value - new Date(ts).getTime()
    return Number.isFinite(age) ? age : null
  })
  const online = computed(() => heartbeatAge.value !== null && heartbeatAge.value < STALE_MS)
  const closed = computed(() => trades.value.filter((t) => t.result === 'win' || t.result === 'loss'))

  /// The pass/fail rail. Prop mode: static start balance. Weekly mode: baseline ± goal/drawdown.
  const challenge = computed(() => {
    const c = config.value
    if (c.account_mode === 'prop') {
      const start = Number(c.prop_start_balance ?? 5000)
      const fail = start - Number(c.prop_max_loss ?? 250)
      return {
        mode: 'prop' as const,
        start, fail,
        floor: fail + Number(c.prop_floor_buffer ?? 50),
        pass: start + Number(c.prop_target ?? 300),
        status: (c.prop_status || 'active') as 'active' | 'passed' | 'failed',
      }
    }
    const start = Number(c.baseline_equity ?? 0)
    const floor = start - Number(c.max_weekly_drawdown ?? 0)
    return { mode: 'weekly' as const, start, fail: floor, floor, pass: start + Number(c.weekly_goal ?? 0), status: 'active' as const }
  })

  const today = computed(() => {
    const d = new Date()
    const dayStart = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())
    const rows = closed.value.filter((t) => t.exit_time && new Date(t.exit_time).getTime() >= dayStart)
    return {
      pnl: rows.reduce((s, t) => s + (Number(t.pnl) || 0), 0),
      trades: rows.length,
      wins: rows.filter((t) => t.result === 'win').length,
    }
  })

  return { config, account, trades, closed, signals, signalAlerts, riskEvents, now, loaded, online, heartbeatAge, challenge, today, refresh, stop }
}

export const money = (v: unknown, sign = false) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const s = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${n < 0 ? '−' : sign && n > 0 ? '+' : ''}$${s}`
}

export const ago = (ms: number | null) => {
  if (ms === null) return 'never'
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`
}
