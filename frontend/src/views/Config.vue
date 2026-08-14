<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { supabase, patchConfig } from '../lib/supabase'

const config = ref<any>({})
// Defaults for fields that may be absent from an older bot_config row (they'd
// otherwise bind to undefined → show 0 → and a Save would write 0/null back).
const CONFIG_DEFAULTS: Record<string, any> = {
  risk_cap_pct: 0.03,
  profit_lock_target: 5.0,
  profit_lock_min: 2.0,
  profit_lock_fraction: 0.5,
  sl_multiplier: 2.0,
  max_open_positions: 2,
}
const weekly = ref<any>({ weekly_pnl: 0, weekly_goal: 14, weekly_progress_pct: 0, daily_pnl: 0, total_trades: 0, win_rate: 0, consecutive_losses: 0 })
const accounts = ref<any[]>([])
const botState = ref('running')
const news = ref<any>({})  // blackout banner — populated when the bot publishes it; {} = hidden
const saving = ref(false)
const calibrating = ref(false)
const showAddAccount = ref(false)
const newAccount = ref({ name: '', login: 0, password: '', server: '', broker: '' })
let timer: number

// --- symbol selection (broker-discovered, curated at runtime) ---
const discovered = ref<string[]>([])        // symbols the logged-in broker offers
const activeBuffer = ref<string[]>([])      // working set the user is toggling
const symbolsDirty = ref(false)             // pause server-sync once the user edits
const applyingSymbols = ref(false)

const fetchConfig = async () => {
  try {
    const { data } = await supabase.from('bot_config').select('config').eq('id', 1).limit(1).single()
    const c = (data?.config || {}) as Record<string, any>
    // fill any missing/blank field with its default so the form never shows 0 for
    // an unconfigured value (which would then get saved back as 0).
    for (const [k, d] of Object.entries(CONFIG_DEFAULTS)) {
      if (c[k] === undefined || c[k] === null || c[k] === '' || (typeof d === 'number' && Number(c[k]) === 0 && Number(d) !== 0)) {
        c[k] = d
      }
    }
    config.value = c
    if (!symbolsDirty.value) activeBuffer.value = [...(c.active_symbols || [])]
    botState.value = c.trading_paused ? 'paused' : (c.bot_running ? 'running' : 'stopped')
  } catch {}
}

// Live stats only — does NOT touch the editable form fields, so polling never
// wipes unsaved edits. Reads accounts, the bot heartbeat (discovered symbols),
// and computes weekly/performance client-side from the trades audit table.
const fetchLive = async () => {
  try {
    const [{ data: acct }, { data: accts }, { data: trs }] = await Promise.all([
      supabase.from('account_state').select('login,symbols,news_blackout,news_reason').order('updated_at', { ascending: false }).limit(1),
      supabase.from('mt5_accounts').select('*').order('created_at', { ascending: false }),
      supabase.from('trades').select('result,pnl,exit_time,mt5_login').order('created_at', { ascending: false }).limit(500),
    ])
    const hb = (acct && acct[0]) || {}
    discovered.value = (hb.symbols || []) as string[]
    news.value = { blackout: !!hb.news_blackout, blackout_reason: hb.news_reason || '' }
    accounts.value = accts || []
    // scope weekly/performance to the active account
    const login = hb && hb.login
    const acctTrs = (trs || []).filter((t) => !login || Number(t.mt5_login) === Number(login))
    weekly.value = computeWeekly(acctTrs, Number(config.value.weekly_goal) || 14)
  } catch {}
}

// Weekly goal progress + performance, computed client-side (Monday-start week).
const computeWeekly = (rows: any[], goal: number) => {
  const closed = rows.filter((t) => t.result === 'win' || t.result === 'loss')
  const now = new Date()
  const weekStart = new Date(now); weekStart.setHours(0, 0, 0, 0); weekStart.setDate(now.getDate() - ((now.getDay() + 6) % 7))
  const dayStart = new Date(now); dayStart.setHours(0, 0, 0, 0)
  const inWeek = (t: any) => t.exit_time && new Date(t.exit_time) >= weekStart
  const inDay = (t: any) => t.exit_time && new Date(t.exit_time) >= dayStart
  const weeklyPnl = closed.filter(inWeek).reduce((s, t) => s + (Number(t.pnl) || 0), 0)
  const wins = closed.filter((t) => t.result === 'win').length
  // trailing losing streak from most recent closed
  const byTime = [...closed].sort((a, b) => new Date(b.exit_time).getTime() - new Date(a.exit_time).getTime())
  let streak = 0
  for (const t of byTime) { if (t.result === 'loss') streak++; else break }
  return {
    weekly_pnl: weeklyPnl,
    weekly_goal: goal,
    weekly_progress_pct: goal > 0 ? (weeklyPnl / goal) * 100 : 0,
    daily_pnl: closed.filter(inDay).reduce((s, t) => s + (Number(t.pnl) || 0), 0),
    total_trades: closed.length,
    win_rate: closed.length ? wins / closed.length : 0,
    consecutive_losses: streak,
  }
}

const save = async () => {
  saving.value = true
  try {
    const merged = await patchConfig({
      weekly_goal: Number(config.value.weekly_goal),
      baseline_equity: Number(config.value.baseline_equity),
      max_risk_per_trade: Number(config.value.max_risk_per_trade),
      max_daily_loss: Number(config.value.max_daily_loss),
      max_weekly_drawdown: Number(config.value.max_weekly_drawdown),
      max_open_positions: Number(config.value.max_open_positions),
      sl_multiplier: Number(config.value.sl_multiplier),
      risk_cap_pct: Number(config.value.risk_cap_pct),
      profit_lock_target: Number(config.value.profit_lock_target),
      profit_lock_min: Number(config.value.profit_lock_min),
      profit_lock_fraction: Number(config.value.profit_lock_fraction),
      thursday_aggression: config.value.thursday_aggression,
      active_symbols: config.value.active_symbols,
    })
    config.value = merged
  } catch (e) { console.error(e); alert('Save failed — check Supabase connection.') }
  finally { saving.value = false }
}

const calibrate = async () => {
  calibrating.value = true
  try {
    // Mirrors RuntimeConfig.auto_calibrate: derive risk params from balance + goal.
    const balance = Number(config.value.baseline_equity) || 0
    const goal = Number(config.value.weekly_goal) || 0
    const risk = Math.round(balance * 0.02 * 100) / 100
    const derived = {
      max_risk_per_trade: risk,
      max_daily_loss: Math.round(balance * 0.06 * 100) / 100,
      max_weekly_drawdown: Math.round(balance * 0.20 * 100) / 100,
      max_open_positions: Math.min(5, Math.max(1, Math.floor(goal / (risk * 2)))),
    }
    const merged = await patchConfig(derived)
    config.value = merged
  } catch (e) { console.error(e); alert('Calibrate failed — check Supabase connection.') }
  finally { calibrating.value = false }
}

const control = async (action: string) => {
  const patch = action === 'start' ? { bot_running: true, trading_paused: false }
    : action === 'stop' ? { bot_running: false }
    : action === 'pause' ? { trading_paused: true }
    : {}
  try { await patchConfig(patch); await fetchConfig() } catch (e) { console.error(e) }
}

// --- symbol selection ---
// Curated universe of symbols we'd ever trade. The bot checks each ACTIVE one
// against the broker's offered set and silently skips any the broker lacks.
// (We do NOT pull + render the broker's full symbol list — that was the bloat.)
const PREFERRED_SYMBOLS = [
  'XAUUSD', 'XAGUSD', 'XPTUSD', 'XPDUSD',                                  // metals
  'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'NZDUSD', 'USDCAD',
  'EURGBP', 'EURJPY', 'GBPJPY',                                            // forex
  'BTCUSD', 'ETHUSD', 'LTCUSD', 'XRPUSD', 'SOLUSD',                        // crypto-CFD
]
const isActive = (sym: string) => activeBuffer.value.includes(sym)
const isOffered = (sym: string) => !discovered.value.length || discovered.value.includes(sym)
const toggleSymbol = (sym: string) => {
  symbolsDirty.value = true
  activeBuffer.value = isActive(sym)
    ? activeBuffer.value.filter(s => s !== sym)
    : [...activeBuffer.value, sym]
}
// preferred list, active first; unavailable-but-active flagged separately below
const preferredList = computed(() =>
  [...PREFERRED_SYMBOLS].sort((a, b) => Number(isActive(b)) - Number(isActive(a))))
const missingActive = computed(() =>
  activeBuffer.value.filter(s => discovered.value.length && !discovered.value.includes(s)))
const applySymbols = async () => {
  applyingSymbols.value = true
  try {
    const merged = await patchConfig({ active_symbols: activeBuffer.value })
    config.value = merged
    symbolsDirty.value = false
  } catch (e) { console.error(e); alert('Apply failed — check Supabase connection.') }
  finally { applyingSymbols.value = false }
}

const addAccount = async () => {
  try { await supabase.from('mt5_accounts').insert(newAccount.value) } catch (e) { console.error(e) }
  newAccount.value = { name: '', login: 0, password: '', server: '', broker: '' }
  showAddAccount.value = false
  await fetchLive()
}

const activateAccount = async (id: number) => {
  try {
    await supabase.from('mt5_accounts').update({ is_active: false }).neq('id', id)
    await supabase.from('mt5_accounts').update({ is_active: true }).eq('id', id)
  } catch (e) { console.error(e) }
  await fetchLive()
}

const deleteAccount = async (id: number) => {
  try { await supabase.from('mt5_accounts').delete().eq('id', id) } catch (e) { console.error(e) }
  await fetchLive()
}

onMounted(() => {
  fetchConfig()
  fetchLive()
  timer = setInterval(fetchLive, 5000)
})
onUnmounted(() => clearInterval(timer))

</script>

<template>
  <div class="space-y-6">
    <!-- Bot controls (weekly progress card lives on the Dashboard tab) -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold">Bot</h2>
      <div class="flex gap-2">
        <button @click="control('start')" class="px-3 py-1 rounded text-sm font-medium"
          :class="botState === 'running' ? 'bg-(--profit) text-black' : 'bg-(--card) border border-(--border)'">Start</button>
        <button @click="control('pause')" class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)"
          :class="botState === 'paused' ? 'text-(--warning)' : ''">Pause</button>
        <button @click="control('stop')" class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)"
          :class="botState === 'stopped' ? 'text-(--loss)' : ''">Stop</button>
      </div>
    </div>

    <!-- News blackout status -->
    <div v-if="news.blackout" class="bg-(--card) border border-(--warning) rounded-lg p-3 flex items-center gap-3">
      <span class="text-(--warning) text-lg">⚠</span>
      <div>
        <div class="font-medium text-sm text-(--warning)">News Blackout Active</div>
        <div class="text-xs text-(--muted)">{{ news.blackout_reason }}</div>
      </div>
    </div>

    <!-- Auto-calibrate -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <h3 class="text-sm font-medium text-(--muted) uppercase mb-3">Account & Auto-Calibrate</h3>
      <div class="flex flex-col sm:flex-row gap-4 items-stretch sm:items-end mb-4">
        <label class="block flex-1">
          <span class="text-xs text-(--muted)">Account Balance ($)</span>
          <input v-model.number="config.baseline_equity" type="number" step="1"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block flex-1">
          <span class="text-xs text-(--muted)">Weekly Goal ($)</span>
          <input v-model.number="config.weekly_goal" type="number" step="0.5"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <button @click="calibrate" :disabled="calibrating"
          class="px-4 py-2 rounded font-medium whitespace-nowrap"
          :class="calibrating ? 'bg-(--border)' : 'bg-(--primary) text-black'">
          {{ calibrating ? 'Calibrating...' : '⚙ Auto-Calibrate' }}
        </button>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <label class="block">
          <span class="text-xs text-(--muted)">Risk / Trade ($, reference)</span>
          <input v-model.number="config.max_risk_per_trade" type="number" step="0.1"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Risk Cap (% of equity)</span>
          <input v-model.number="config.risk_cap_pct" type="number" step="0.005" min="0.005" max="0.2"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Daily Loss Cap ($)</span>
          <input v-model.number="config.max_daily_loss" type="number" step="0.5"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Weekly Drawdown ($)</span>
          <input v-model.number="config.max_weekly_drawdown" type="number" step="1"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Max Positions</span>
          <input v-model.number="config.max_open_positions" type="number" step="1" min="1" max="10"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">SL Multiplier</span>
          <input v-model.number="config.sl_multiplier" type="number" step="0.1" min="0.5" max="5"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
      </div>

      <!-- Goal-aware exit (profit-lock + weekly equity ceiling) -->
      <p class="text-xs text-(--muted) mt-5 mb-2">
        Exit policy: at <strong>baseline + weekly goal</strong> in live equity, the bot closes all
        positions and rests for the week. Per trade, once floating profit hits the target, the SL
        ratchets to lock profit (min, or a fraction of the peak).
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <label class="block">
          <span class="text-xs text-(--muted)">Profit-Lock Target ($)</span>
          <input v-model.number="config.profit_lock_target" type="number" step="0.5" min="0"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Profit-Lock Min ($)</span>
          <input v-model.number="config.profit_lock_min" type="number" step="0.5" min="0"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Profit-Lock Fraction</span>
          <input v-model.number="config.profit_lock_fraction" type="number" step="0.05" min="0" max="1"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block flex items-center gap-2 pt-6">
          <input v-model="config.thursday_aggression" type="checkbox" class="w-4 h-4 rounded" />
          <span class="text-sm">Thursday Aggression</span>
        </label>
      </div>
      <div class="mt-4">
        <button @click="save" :disabled="saving"
          class="px-4 py-2 rounded font-medium" :class="saving ? 'bg-(--border)' : 'bg-(--primary) text-black'">
          {{ saving ? 'Saving...' : 'Save & Apply' }}
        </button>
      </div>
    </div>

    <!-- Symbol selection (curated preferred list; broker availability shown) -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <div class="flex items-center justify-between mb-1">
        <h3 class="text-sm font-medium text-(--muted) uppercase">Symbols</h3>
        <span class="text-xs text-(--muted)">{{ activeBuffer.length }} active</span>
      </div>
      <p class="text-xs text-(--muted) mb-3">
        Preferred instruments. Toggle what the bot trades — anything this broker doesn't
        offer is silently skipped. Applies live, no restart.
      </p>

      <!-- active-but-not-offered warning -->
      <div v-if="missingActive.length" class="mb-3 text-xs flex items-center gap-2 text-(--warning)">
        <span>⚠</span>
        <span>Not offered by this broker (will be skipped): {{ missingActive.join(', ') }}</span>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <label v-for="sym in preferredList" :key="sym"
          class="flex items-center gap-2 p-2 rounded bg-(--bg) cursor-pointer text-sm"
          :class="!isOffered(sym) ? 'opacity-50' : ''">
          <input type="checkbox" :checked="isActive(sym)" @change="toggleSymbol(sym)" class="w-4 h-4 rounded" />
          <span>{{ sym }}</span>
          <span v-if="discovered.length && !isOffered(sym)" class="ml-auto text-[10px] text-(--muted)">n/a</span>
        </label>
      </div>

      <div class="mt-4 flex items-center gap-3">
        <button @click="applySymbols" :disabled="!symbolsDirty || applyingSymbols"
          class="px-4 py-2 rounded font-medium"
          :class="(!symbolsDirty || applyingSymbols) ? 'bg-(--border)' : 'bg-(--primary) text-black'">
          {{ applyingSymbols ? 'Applying…' : 'Apply Symbols' }}
        </button>
        <span v-if="symbolsDirty" class="text-xs text-(--warning)">unsaved changes</span>
      </div>
    </div>

    <!-- MT5 Accounts -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-medium text-(--muted) uppercase">MT5 Accounts</h3>
        <button @click="showAddAccount = !showAddAccount"
          class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)">+ Add</button>
      </div>

      <!-- Add form -->
      <div v-if="showAddAccount" class="mb-4 p-3 bg-(--bg) rounded grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input v-model="newAccount.name" placeholder="Name (e.g. IC Markets Demo)"
          class="px-3 py-2 rounded bg-(--card) border border-(--border) text-(--text) text-sm col-span-2" />
        <input v-model.number="newAccount.login" placeholder="Login" type="number"
          class="px-3 py-2 rounded bg-(--card) border border-(--border) text-(--text) text-sm" />
        <input v-model="newAccount.server" placeholder="Server (e.g. MetaQuotes-Demo)"
          class="px-3 py-2 rounded bg-(--card) border border-(--border) text-(--text) text-sm" />
        <input v-model="newAccount.password" placeholder="Password" type="password"
          class="px-3 py-2 rounded bg-(--card) border border-(--border) text-(--text) text-sm" />
        <input v-model="newAccount.broker" placeholder="Broker (optional)"
          class="px-3 py-2 rounded bg-(--card) border border-(--border) text-(--text) text-sm" />
        <button @click="addAccount"
          class="px-3 py-2 rounded text-sm font-medium bg-(--profit) text-black">Add Account</button>
      </div>

      <!-- Account list -->
      <div class="space-y-2">
        <div v-for="a in accounts" :key="a.id"
          class="flex items-center gap-3 p-3 rounded bg-(--bg)">
          <div class="flex-1">
            <div class="font-medium text-sm">{{ a.name }}</div>
            <div class="text-xs text-(--muted)">{{ a.login }} · {{ a.server }}</div>
          </div>
          <button @click="activateAccount(a.id)"
            class="px-2 py-1 rounded text-xs font-medium"
            :class="a.is_active ? 'bg-(--profit) text-black' : 'bg-(--card) border border-(--border)'">
            {{ a.is_active ? '✓ Active' : 'Activate' }}
          </button>
          <button @click="deleteAccount(a.id)" class="text-(--loss) text-xs px-2">✕</button>
        </div>
        <div v-if="!accounts.length" class="text-center text-(--muted) text-sm py-4">No accounts yet.</div>
      </div>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
