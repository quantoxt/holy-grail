<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  PhPlay, PhPause, PhStop, PhFloppyDisk, PhPlus, PhTrash, PhCheckCircle, PhCircleNotch, PhMountains, PhCalendarCheck,
} from '@phosphor-icons/vue'
import { supabase, patchConfig, addMt5Account, setActiveMt5Account, deleteMt5Account } from '../lib/supabase'
import { useLive, money } from '../composables/useLive'

const { config, account, refresh, stop } = useLive()
onUnmounted(stop)

// ---- editable copy (polling never overwrites unsaved edits) ----
const form = ref<Record<string, any>>({})
const dirty = ref(false)
// Defaults for fields added after the bot_config row was seeded (cloud rows
// predate them, so config.value lacks the keys — show the bot's real defaults
// instead of an empty box, and write them through on first save).
const fieldDefaults: Record<string, any> = { signals_enabled: true, signal_cooldown_min: 120 }
const seed = () => { form.value = { ...fieldDefaults, ...JSON.parse(JSON.stringify(config.value || {})) }; dirty.value = false }
watch(config, () => { if (!dirty.value) seed() }, { immediate: true })
const edit = () => { dirty.value = true }

type Field = { key: string; label: string; hint?: string; step?: number; pct?: boolean; bool?: boolean; money?: boolean }
const propFields: Field[] = [
  { key: 'prop_start_balance', label: 'Start balance', money: true, step: 100 },
  { key: 'prop_target', label: 'Profit target', money: true, step: 10 },
  { key: 'prop_max_loss', label: 'Max loss allowed', hint: 'The firm’s fail line, measured from the start balance', money: true, step: 10 },
  { key: 'prop_floor_buffer', label: 'Safety buffer', hint: 'The bot closes everything this far above the fail line', money: true, step: 5 },
  { key: 'risk_pct_per_trade', label: 'Risk per trade', hint: 'Share of the start balance lost if a stop is hit', pct: true, step: 0.1 },
  { key: 'max_daily_loss', label: 'Daily loss limit', hint: 'Stops for the day after losing this much', money: true, step: 5 },
  { key: 'max_open_positions', label: 'Max open trades', step: 1 },
]
const weeklyFields: Field[] = [
  { key: 'baseline_equity', label: 'Baseline equity', money: true, step: 10 },
  { key: 'weekly_goal', label: 'Weekly goal', money: true, step: 1 },
  { key: 'max_weekly_drawdown', label: 'Weekly drawdown limit', money: true, step: 1 },
  { key: 'max_risk_per_trade', label: 'Reference risk per trade', money: true, step: 0.5 },
  { key: 'max_daily_loss', label: 'Daily loss limit', money: true, step: 1 },
  { key: 'max_open_positions', label: 'Max open trades', step: 1 },
]
const advancedFields: Field[] = [
  { key: 'tp_rr_mult', label: 'Take-profit (× stop distance)', step: 0.1 },
  { key: 'breakeven_lock_r', label: 'Move stop to entry at (× risk)', step: 0.1 },
  { key: 'profit_lock_r', label: 'Start trailing at (× risk)', step: 0.1 },
  { key: 'trail_slack_r', label: 'Trail distance (× risk)', step: 0.1 },
  { key: 'sl_atr_mult', label: 'Stop distance (× volatility)', step: 0.05 },
  { key: 'risk_cap_pct', label: 'Skip trades risking more than', pct: true, step: 0.1 },
  { key: 'min_confidence', label: 'Minimum signal confidence', pct: true, step: 1 },
  { key: 'sl_modify_min_interval_s', label: 'Seconds between stop edits', step: 5 },
  { key: 'sl_modify_max_per_hour', label: 'Stop edits per trade per hour', step: 1 },
  { key: 'news_blackout_enabled', label: 'Sit out high-impact news', bool: true },
  { key: 'thursday_aggression', label: 'Thursday risk boost (weekly mode)', bool: true },
]
const signalFields: Field[] = [
  { key: 'signals_enabled', label: 'Signal Mode — alerts only, never opens trades', bool: true },
  { key: 'signal_cooldown_min', label: 'Minutes between repeat alerts per symbol (direction flip always alerts)', step: 5 },
]

const isProp = computed(() => form.value.account_mode === 'prop')
const show = (f: Field) => (f.pct ? +(Number(form.value[f.key] ?? 0) * 100).toFixed(3) : form.value[f.key])
const set = (f: Field, v: string) => { form.value[f.key] = f.pct ? Number(v) / 100 : Number(v); edit() }

const saving = ref(false)
const saved = ref(false)
const err = ref('')
const save = async () => {
  saving.value = true; err.value = ''
  try {
    const keys = [...propFields, ...weeklyFields, ...advancedFields, ...signalFields].map((f) => f.key).concat(['account_mode'])
    const patch: Record<string, any> = {}
    for (const k of keys) if (form.value[k] !== undefined && JSON.stringify(form.value[k]) !== JSON.stringify(config.value[k])) patch[k] = form.value[k]
    if (Object.keys(patch).length) config.value = await patchConfig(patch)
    dirty.value = false; seed()
    saved.value = true; setTimeout(() => (saved.value = false), 2500)
  } catch (e: any) { err.value = `Couldn’t save: ${e.message ?? e}` }
  finally { saving.value = false }
}

// ---- bot control ----
const botState = computed(() => (config.value.trading_paused ? 'paused' : config.value.bot_running ? 'running' : 'stopped'))
const control = async (action: 'start' | 'pause' | 'stop') => {
  const patch = action === 'start' ? { bot_running: true, trading_paused: false } : action === 'stop' ? { bot_running: false } : { trading_paused: true }
  try { config.value = await patchConfig(patch) } catch (e: any) { err.value = `Couldn’t change the bot: ${e.message ?? e}` }
}

// ---- challenge status ----
const theFiveErsProfile = {
  account_mode: 'prop', prop_start_balance: 5000, prop_target: 300, prop_max_loss: 250, prop_floor_buffer: 50,
  prop_status: 'active', risk_pct_per_trade: 0.005, max_daily_loss: 75, active_symbols: ['XAUUSD', 'GBPUSD', 'BTCUSD'],
  max_open_positions: 2, thursday_aggression: false, withdraw_profit_weekly: false,
}
const applyProfile = async () => {
  if (!confirm('Switch to the The5ers $5,000 challenge profile? This replaces the risk settings above.')) return
  try { config.value = await patchConfig(theFiveErsProfile); dirty.value = false; seed() } catch (e: any) { err.value = e.message ?? String(e) }
}
const nextStep = ref<number | null>(null)
const resetChallenge = async () => {
  const bal = nextStep.value || Number(config.value.prop_start_balance)
  if (!confirm(`Restart the challenge from ${money(bal)}? Trading resumes once the bot is running.`)) return
  try {
    config.value = await patchConfig({ prop_status: 'active', prop_start_balance: bal })
    nextStep.value = null; dirty.value = false; seed()
  } catch (e: any) { err.value = e.message ?? String(e) }
}

// ---- symbols ----
const PREFERRED = ['XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'EURJPY', 'GBPJPY', 'BTCUSD', 'ETHUSD']
const active = ref<string[]>([])
const symbolsDirty = ref(false)
watch(config, (c) => { if (!symbolsDirty.value) active.value = [...(c.active_symbols || [])] }, { immediate: true })
const offered = computed<string[]>(() => account.value?.symbols || [])
const toggle = (s: string) => { symbolsDirty.value = true; active.value = active.value.includes(s) ? active.value.filter((x) => x !== s) : [...active.value, s] }
const applySymbols = async () => {
  try { config.value = await patchConfig({ active_symbols: active.value }); symbolsDirty.value = false } catch (e: any) { err.value = e.message ?? String(e) }
}

// ---- MT5 accounts (passwords are write-only) ----
const accounts = ref<any[]>([])
const loadAccounts = async () => {
  const { data } = await supabase.from('mt5_accounts').select('id,name,login,server,broker,is_active,created_at').order('created_at', { ascending: false })
  accounts.value = data || []
}
onMounted(loadAccounts)
const adding = ref(false)
const acct = ref({ name: '', login: '', password: '', server: '', broker: '' })
const addAcct = async () => {
  try {
    await addMt5Account({ ...acct.value, login: Number(acct.value.login) })
    acct.value = { name: '', login: '', password: '', server: '', broker: '' }; adding.value = false
    await loadAccounts()
  } catch (e: any) { err.value = `Couldn’t add the account: ${e.message ?? e}` }
}
const activate = async (id: number) => { try { await setActiveMt5Account(id); await loadAccounts(); refresh() } catch (e: any) { err.value = e.message ?? String(e) } }
const remove = async (a: any) => {
  if (!confirm(`Delete the account “${a.name}” (${a.login})? The bot can no longer log into it.`)) return
  try { await deleteMt5Account(a.id); await loadAccounts() } catch (e: any) { err.value = e.message ?? String(e) }
}
</script>

<template>
  <div class="space-y-10 pb-16">
    <header>
      <h1 class="font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-semibold tracking-tight">Settings</h1>
      <p class="text-(--muted) mt-1">Changes reach the running bot within about 5 seconds.</p>
    </header>

    <p v-if="err" role="alert" class="rounded-2xl px-4 py-3 text-(--loss)" style="background: color-mix(in oklab, var(--loss) 12%, transparent)">{{ err }}</p>

    <!-- bot -->
    <section class="flex flex-wrap items-center gap-4">
      <div>
        <h2 class="font-display text-xl font-semibold">Bot</h2>
        <p class="text-(--muted) text-sm">Currently {{ botState }}.{{ botState === 'paused' ? ' No new trades — signals keep firing while Signal Mode is on.' : '' }}</p>
      </div>
      <div class="ml-auto flex rounded-2xl bg-(--card) p-1">
        <button class="seg" :class="{ on: botState === 'running' }" @click="control('start')"><PhPlay :size="18" weight="fill" />Run</button>
        <button class="seg" :class="{ on: botState === 'paused' }" @click="control('pause')"><PhPause :size="18" weight="fill" />Pause</button>
        <button class="seg" :class="{ on: botState === 'stopped' }" @click="control('stop')"><PhStop :size="18" weight="fill" />Stop</button>
      </div>
    </section>

    <!-- challenge -->
    <section class="rounded-[28px] bg-(--card) p-5 md:p-7">
      <div class="flex flex-wrap items-center gap-3 mb-5">
        <h2 class="font-display text-xl font-semibold mr-auto">Goal</h2>
        <div class="flex rounded-2xl bg-(--bg) p-1">
          <button class="seg" :class="{ on: isProp }" @click="form.account_mode = 'prop'; edit()"><PhMountains :size="18" weight="duotone" />Prop challenge</button>
          <button class="seg" :class="{ on: !isProp }" @click="form.account_mode = 'weekly'; edit()"><PhCalendarCheck :size="18" weight="duotone" />Weekly goal</button>
        </div>
      </div>

      <div v-if="isProp && config.account_mode === 'prop'" class="mb-6 flex flex-wrap items-center gap-3 rounded-2xl bg-(--bg) px-4 py-3">
        <span>Challenge status:</span>
        <span class="font-semibold" :class="config.prop_status === 'passed' ? 'text-(--profit)' : config.prop_status === 'failed' ? 'text-(--loss)' : ''">{{ config.prop_status || 'active' }}</span>
        <template v-if="config.prop_status && config.prop_status !== 'active'">
          <label class="ml-auto flex items-center gap-2 text-sm text-(--muted)">Next start balance
            <input type="number" step="1000" :placeholder="String(config.prop_start_balance)" v-model.number="nextStep" class="input w-28" />
          </label>
          <button class="btn" @click="resetChallenge">Start next step</button>
        </template>
      </div>

      <div class="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <label v-for="f in (isProp ? propFields : weeklyFields)" :key="f.key" class="block">
          <span class="text-sm font-medium">{{ f.label }}</span>
          <div class="relative mt-1">
            <span v-if="f.money" class="absolute left-3 top-1/2 -translate-y-1/2 text-(--muted)">$</span>
            <input type="number" :step="f.pct ? f.step : f.step" :value="show(f)" @input="set(f, ($event.target as HTMLInputElement).value)"
                   class="input w-full" :style="{ paddingLeft: f.money ? '1.75rem' : undefined, paddingRight: f.pct ? '2rem' : undefined }" />
            <span v-if="f.pct" class="absolute right-3 top-1/2 -translate-y-1/2 text-(--muted)">%</span>
          </div>
          <span v-if="f.hint" class="block text-xs text-(--muted) mt-1">{{ f.hint }}</span>
        </label>
      </div>

      <div class="mt-6 flex flex-wrap items-center gap-3">
        <button class="btn-primary" :disabled="saving || !dirty" @click="save">
          <PhCircleNotch v-if="saving" :size="18" class="animate-spin" /><PhFloppyDisk v-else :size="18" weight="duotone" />Save changes
        </button>
        <span v-if="saved" class="flex items-center gap-1.5 text-(--profit) text-sm"><PhCheckCircle :size="18" weight="fill" />Saved</span>
        <button v-if="isProp" class="btn ml-auto" @click="applyProfile">Use The5ers $5K profile</button>
      </div>
    </section>

    <!-- symbols -->
    <section>
      <h2 class="font-display text-xl font-semibold">Instruments</h2>
      <p class="text-(--muted) text-sm mb-4">Tap to choose what the bot trades. Faded ones aren’t offered by the connected broker.</p>
      <div class="flex flex-wrap gap-2">
        <button v-for="s in PREFERRED" :key="s" @click="toggle(s)"
                class="rounded-full px-4 py-2 text-sm font-medium transition-colors border"
                :class="[active.includes(s) ? 'bg-(--primary) text-(--primary-ink) border-transparent' : 'bg-(--card) border-(--border) text-(--text)', offered.length && !offered.includes(s) ? 'opacity-45' : '']">
          {{ s }}
        </button>
      </div>
      <button v-if="symbolsDirty" class="btn-primary mt-4" @click="applySymbols"><PhCheckCircle :size="18" weight="duotone" />Apply instruments</button>
    </section>

    <!-- signal mode -->
    <section class="rounded-[28px] bg-(--card) p-5 md:p-7">
      <h2 class="font-display text-xl font-semibold">Signal Mode</h2>
      <p class="text-(--muted) text-sm mt-1 mb-5">A true mode, not an add-on. When on, the bot scans and sends full-ticket Telegram alerts but places zero orders — even on Run. Turn it off to resume live trading. Open positions are always still managed (stops, targets, safety rules).</p>
      <div class="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <label v-for="f in signalFields" :key="f.key" class="block" :class="{ 'flex items-center gap-3': f.bool }">
          <template v-if="f.bool">
            <input type="checkbox" :checked="!!form[f.key]" @change="form[f.key] = ($event.target as HTMLInputElement).checked; edit()" class="size-5 accent-(--primary)" />
            <span class="text-sm font-medium">{{ f.label }}</span>
          </template>
          <template v-else>
            <span class="text-sm font-medium">{{ f.label }}</span>
            <div class="relative mt-1">
              <input type="number" :step="f.step" :value="show(f)" @input="set(f, ($event.target as HTMLInputElement).value)" class="input w-full" />
            </div>
          </template>
        </label>
      </div>
      <button class="btn-primary mt-6" :disabled="saving || !dirty" @click="save"><PhFloppyDisk :size="18" weight="duotone" />Save changes</button>
    </section>

    <!-- accounts -->
    <section>
      <div class="flex items-center mb-4">
        <div class="mr-auto">
          <h2 class="font-display text-xl font-semibold">MT5 accounts</h2>
          <p class="text-(--muted) text-sm">Passwords are stored for the bot only and can’t be read back here.</p>
        </div>
        <button class="btn" @click="adding = !adding"><PhPlus :size="18" />Add account</button>
      </div>
      <form v-if="adding" @submit.prevent="addAcct" class="mb-4 grid gap-3 rounded-[22px] bg-(--card) p-5 sm:grid-cols-2">
        <label class="block"><span class="text-sm font-medium">Name</span><input v-model="acct.name" required placeholder="The5ers Bootcamp" class="input w-full mt-1" /></label>
        <label class="block"><span class="text-sm font-medium">Broker</span><input v-model="acct.broker" placeholder="The5ers" class="input w-full mt-1" /></label>
        <label class="block"><span class="text-sm font-medium">Login</span><input v-model="acct.login" required inputmode="numeric" class="input w-full mt-1" /></label>
        <label class="block"><span class="text-sm font-medium">Server</span><input v-model="acct.server" required placeholder="From the login email" class="input w-full mt-1" /></label>
        <label class="block sm:col-span-2"><span class="text-sm font-medium">Password</span><input v-model="acct.password" required type="password" autocomplete="new-password" class="input w-full mt-1" /></label>
        <div class="sm:col-span-2 flex gap-2"><button type="submit" class="btn-primary">Save account</button><button type="button" class="btn" @click="adding = false">Cancel</button></div>
      </form>
      <ul class="space-y-2">
        <li v-for="a in accounts" :key="a.id" class="flex flex-wrap items-center gap-3 rounded-2xl bg-(--card) px-4 py-3">
          <div class="min-w-0">
            <div class="font-semibold">{{ a.name }}</div>
            <div class="num text-sm text-(--muted)">{{ a.login }} on {{ a.server }}</div>
          </div>
          <span v-if="a.is_active" class="ml-auto flex items-center gap-1.5 text-sm text-(--profit) font-medium"><PhCheckCircle :size="18" weight="fill" />In use</span>
          <button v-else class="btn ml-auto" @click="activate(a.id)">Use this account</button>
          <button class="icon-btn" :aria-label="`Delete ${a.name}`" @click="remove(a)"><PhTrash :size="18" /></button>
        </li>
        <li v-if="!accounts.length" class="rounded-2xl border border-dashed border-(--border) px-4 py-6 text-(--muted)">No accounts yet. Add the MT5 login the bot should trade.</li>
      </ul>
    </section>

    <!-- advanced -->
    <details class="rounded-[28px] bg-(--card) p-5 md:p-7 group">
      <summary class="cursor-pointer font-display text-xl font-semibold">Advanced</summary>
      <p class="text-(--muted) text-sm mt-1 mb-5">Exit rules and filters. The defaults were tuned on past runs; change one at a time.</p>
      <div class="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <label v-for="f in advancedFields" :key="f.key" class="block" :class="{ 'flex items-center gap-3': f.bool }">
          <template v-if="f.bool">
            <input type="checkbox" :checked="!!form[f.key]" @change="form[f.key] = ($event.target as HTMLInputElement).checked; edit()" class="size-5 accent-(--primary)" />
            <span class="text-sm font-medium">{{ f.label }}</span>
          </template>
          <template v-else>
            <span class="text-sm font-medium">{{ f.label }}</span>
            <div class="relative mt-1">
              <input type="number" :step="f.step" :value="show(f)" @input="set(f, ($event.target as HTMLInputElement).value)" class="input w-full" :style="{ paddingRight: f.pct ? '2rem' : undefined }" />
              <span v-if="f.pct" class="absolute right-3 top-1/2 -translate-y-1/2 text-(--muted)">%</span>
            </div>
          </template>
        </label>
      </div>
      <button class="btn-primary mt-6" :disabled="saving || !dirty" @click="save"><PhFloppyDisk :size="18" weight="duotone" />Save changes</button>
    </details>
  </div>
</template>

<style>
@reference "tailwindcss";
.seg { @apply flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-sm transition-colors; color: var(--muted); }
.seg:hover { color: var(--text); }
.seg.on { background: var(--primary); color: var(--primary-ink); font-weight: 600; }
.input { @apply rounded-xl px-3 py-2 outline-none; background: var(--bg); border: 1px solid var(--border); color: var(--text); }
.input:focus { border-color: var(--primary); }
.btn { @apply flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition-colors; background: var(--bg); border: 1px solid var(--border); }
.btn:hover { border-color: var(--primary); }
.btn-primary { @apply flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50; background: var(--primary); color: var(--primary-ink); }
</style>
