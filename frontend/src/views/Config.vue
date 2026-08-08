<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const config = ref<any>({})
const weekly = ref<any>({})
const accounts = ref<any[]>([])
const botState = ref('running')
const news = ref<any>({})
const saving = ref(false)
const calibrating = ref(false)
const showAddAccount = ref(false)
const newAccount = ref({ name: '', login: 0, password: '', server: '', broker: '' })
let timer: number

const fetchData = async () => {
  try {
    const [c, w, n, a] = await Promise.all([
      fetch('/api/config').then(r => r.json()),
      fetch('/api/weekly').then(r => r.json()),
      fetch('/api/news').then(r => r.json()),
      fetch('/api/accounts').then(r => r.json()),
    ])
    config.value = c
    weekly.value = w
    news.value = n
    accounts.value = a
    botState.value = c.trading_paused ? 'paused' : (c.bot_running ? 'running' : 'stopped')
  } catch {}
}

const save = async () => {
  saving.value = true
  try {
    await fetch('/api/config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        weekly_goal: Number(config.value.weekly_goal),
        baseline_equity: Number(config.value.baseline_equity),
        max_risk_per_trade: Number(config.value.max_risk_per_trade),
        max_daily_loss: Number(config.value.max_daily_loss),
        max_weekly_drawdown: Number(config.value.max_weekly_drawdown),
        max_open_positions: Number(config.value.max_open_positions),
        sl_multiplier: Number(config.value.sl_multiplier),
        thursday_aggression: config.value.thursday_aggression,
        active_symbols: config.value.active_symbols,
      }),
    })
  } finally { saving.value = false; await fetchData() }
}

const calibrate = async () => {
  calibrating.value = true
  try {
    await fetch('/api/calibrate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        balance: Number(config.value.baseline_equity),
        weekly_goal: Number(config.value.weekly_goal),
      }),
    })
  } finally { calibrating.value = false; await fetchData() }
}

const control = async (action: string) => {
  await fetch(`/api/control/${action}`, { method: 'POST' })
  await fetchData()
}

const addAccount = async () => {
  await fetch('/api/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(newAccount.value),
  })
  newAccount.value = { name: '', login: 0, password: '', server: '', broker: '' }
  showAddAccount.value = false
  await fetchData()
}

const activateAccount = async (id: number) => {
  await fetch(`/api/accounts/${id}/activate`, { method: 'POST' })
  await fetchData()
}

const deleteAccount = async (id: number) => {
  await fetch(`/api/accounts/${id}`, { method: 'DELETE' })
  await fetchData()
}

onMounted(() => { fetchData(); timer = setInterval(fetchData, 5000) })
onUnmounted(() => clearInterval(timer))

const progressColor = (pct: number) => pct >= 100 ? 'var(--profit)' : pct >= 50 ? 'var(--warning)' : 'var(--primary)'
</script>

<template>
  <div class="space-y-6">
    <!-- Weekly progress + controls -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Weekly Goal</h2>
        <div class="flex gap-2">
          <button @click="control('start')" class="px-3 py-1 rounded text-sm font-medium"
            :class="botState === 'running' ? 'bg-(--profit) text-black' : 'bg-(--card) border border-(--border)'">Start</button>
          <button @click="control('pause')" class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)"
            :class="botState === 'paused' ? 'text-(--warning)' : ''">Pause</button>
          <button @click="control('stop')" class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)"
            :class="botState === 'stopped' ? 'text-(--loss)' : ''">Stop</button>
        </div>
      </div>
      <div class="flex items-baseline gap-3 mb-2">
        <span class="text-3xl font-bold" :class="(weekly.weekly_pnl ?? 0) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
          ${{ (weekly.weekly_pnl ?? 0).toFixed(2) }}
        </span>
        <span class="text-(--muted)">/ ${{ (weekly.weekly_goal ?? 14).toFixed(2) }}</span>
      </div>
      <div class="w-full h-3 rounded-full bg-(--bg) overflow-hidden mb-3">
        <div class="h-full rounded-full transition-all duration-500"
          :style="{ width: Math.min(100, weekly.weekly_progress_pct ?? 0) + '%', background: progressColor(weekly.weekly_progress_pct ?? 0) }" />
      </div>
      <div class="grid grid-cols-4 gap-4 text-sm">
        <div><span class="text-(--muted)">Today</span><br>${{ (weekly.daily_pnl ?? 0).toFixed(2) }}</div>
        <div><span class="text-(--muted)">Trades</span><br>{{ weekly.total_trades ?? 0 }}</div>
        <div><span class="text-(--muted)">Win Rate</span><br>{{ ((weekly.win_rate ?? 0) * 100).toFixed(1) }}%</div>
        <div><span class="text-(--muted)">Streak</span><br>{{ weekly.consecutive_losses ?? 0 }}</div>
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
      <div class="flex gap-4 items-end mb-4">
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
      <div class="grid grid-cols-3 gap-4">
        <label class="block">
          <span class="text-xs text-(--muted)">Risk / Trade ($)</span>
          <input v-model.number="config.max_risk_per_trade" type="number" step="0.1"
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

    <!-- MT5 Accounts -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-medium text-(--muted) uppercase">MT5 Accounts</h3>
        <button @click="showAddAccount = !showAddAccount"
          class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)">+ Add</button>
      </div>

      <!-- Add form -->
      <div v-if="showAddAccount" class="mb-4 p-3 bg-(--bg) rounded grid grid-cols-2 gap-3">
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
