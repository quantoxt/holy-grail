<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const config = ref<any>({})
const weekly = ref<any>({ weekly_pnl: 0, weekly_goal: 14, weekly_progress_pct: 0 })
const saving = ref(false)
const botState = ref('running')
let timer: number

const fetchData = async () => {
  try {
    const [c, w] = await Promise.all([
      fetch('/api/config').then(r => r.json()),
      fetch('/api/weekly').then(r => r.json()),
    ])
    config.value = c
    weekly.value = w
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
  } finally { saving.value = false }
}

const control = async (action: string) => {
  await fetch(`/api/control/${action}`, { method: 'POST' })
  await fetchData()
}

onMounted(() => { fetchData(); timer = setInterval(fetchData, 5000) })
onUnmounted(() => clearInterval(timer))

const progressColor = (pct: number) => pct >= 100 ? 'var(--profit)' : pct >= 50 ? 'var(--warning)' : 'var(--primary)'
</script>

<template>
  <div class="space-y-6">
    <!-- Weekly progress -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Weekly Goal</h2>
        <div class="flex gap-2">
          <button @click="control('start')" class="px-3 py-1 rounded text-sm font-medium"
            :class="botState === 'running' ? 'bg-(--profit) text-black' : 'bg-(--card) border border-(--border)'">
            Start</button>
          <button @click="control('pause')" class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)"
            :class="botState === 'paused' ? 'text-(--warning)' : ''">Pause</button>
          <button @click="control('stop')" class="px-3 py-1 rounded text-sm bg-(--card) border border-(--border)"
            :class="botState === 'stopped' ? 'text-(--loss)' : ''">Stop</button>
        </div>
      </div>
      <div class="flex items-baseline gap-3 mb-2">
        <span class="text-3xl font-bold" :class="weekly.weekly_pnl >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
          ${{ weekly.weekly_pnl?.toFixed(2) }}
        </span>
        <span class="text-(--muted)">/ ${{ weekly.weekly_goal?.toFixed(2) }}</span>
        <span v-if="weekly.withdrawn_total > 0" class="text-xs text-(--muted)">
          (withdrawn: ${{ weekly.withdrawn_total?.toFixed(2) }})
        </span>
      </div>
      <div class="w-full h-3 rounded-full bg-(--bg) overflow-hidden">
        <div class="h-full rounded-full transition-all duration-500"
          :style="{ width: Math.min(100, weekly.weekly_progress_pct || 0) + '%',
                    background: progressColor(weekly.weekly_progress_pct || 0) }" />
      </div>
      <div class="grid grid-cols-4 gap-4 mt-4 text-sm">
        <div><span class="text-(--muted)">Today</span><br>${{ weekly.daily_pnl?.toFixed(2) }}</div>
        <div><span class="text-(--muted)">Trades</span><br>{{ weekly.total_trades }}</div>
        <div><span class="text-(--muted)">Win Rate</span><br>{{ (weekly.win_rate * 100)?.toFixed(1) }}%</div>
        <div><span class="text-(--muted)">Loss Streak</span><br>{{ weekly.consecutive_losses }}</div>
      </div>
    </div>

    <!-- Risk params -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <h3 class="text-sm font-medium text-(--muted) uppercase mb-3">Risk Parameters</h3>
      <div class="grid grid-cols-2 gap-4">
        <label class="block">
          <span class="text-xs text-(--muted)">Weekly Goal ($)</span>
          <input v-model.number="config.weekly_goal" type="number" step="0.5"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Baseline Equity ($)</span>
          <input v-model.number="config.baseline_equity" type="number" step="1"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Max Risk / Trade ($)</span>
          <input v-model.number="config.max_risk_per_trade" type="number" step="0.1"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Max Daily Loss ($)</span>
          <input v-model.number="config.max_daily_loss" type="number" step="0.5"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Max Weekly Drawdown ($)</span>
          <input v-model.number="config.max_weekly_drawdown" type="number" step="1"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">Max Open Positions</span>
          <input v-model.number="config.max_open_positions" type="number" step="1" min="1" max="10"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block">
          <span class="text-xs text-(--muted)">SL Multiplier (× predicted move)</span>
          <input v-model.number="config.sl_multiplier" type="number" step="0.1" min="0.5" max="5"
            class="w-full mt-1 px-3 py-2 rounded bg-(--bg) border border-(--border) text-(--text)" />
        </label>
        <label class="block flex items-center gap-2 pt-6">
          <input v-model="config.thursday_aggression" type="checkbox"
            class="w-4 h-4 rounded bg-(--bg) border-(--border)" />
          <span class="text-sm">Thursday Aggression</span>
        </label>
      </div>
      <div class="mt-4">
        <button @click="save" :disabled="saving"
          class="px-4 py-2 rounded font-medium bg-(--primary) text-black">
          {{ saving ? 'Saving...' : 'Save & Apply' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
