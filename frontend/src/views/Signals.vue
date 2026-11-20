<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { PhArrowUpRight, PhArrowDownRight, PhBell } from '@phosphor-icons/vue'
import { useLive, ago } from '../composables/useLive'

const { signalAlerts, signals, config, now, stop } = useLive()
onUnmounted(stop)

const filter = ref<'all' | 'BUY' | 'SELL'>('all')
const filters = [
  { id: 'all', label: 'All' }, { id: 'BUY', label: 'Long' }, { id: 'SELL', label: 'Short' },
] as const

// Prefer the dispatch log (one row per Telegram signal). Fall back to the raw
// scan table on backends that predate migration 014.
const alerts = computed(() => {
  const rows = (signalAlerts.value?.length ? signalAlerts.value : (signals.value || []).filter((s) => s.direction !== 'HOLD'))
    .filter((s) => filter.value === 'all' || s.direction === filter.value)
  return rows.slice(0, 100)
})

const enabled = computed(() => config.value?.signals_enabled !== false)
const cooldown = computed(() => Number(config.value?.signal_cooldown_min ?? 120))

const px = (v: unknown) => (v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }))
const when = (iso?: string) => {
  if (!iso) return '—'
  const ms = now.value - new Date(iso).getTime()
  return ms < 86_400_000 ? ago(ms) : new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end gap-4">
      <div>
        <h1 class="font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-semibold tracking-tight">Signals</h1>
        <p class="text-(--muted) mt-1">
          {{ enabled ? `Signal Mode is on — the bot alerts but never opens trades. One alert per symbol every ${cooldown} min unless direction flips.` : 'Signal Mode is off. Turn it on in Settings to stop live trading and get alerts only.' }}
          Setups use the same gates as live trades.
        </p>
      </div>
      <div class="ml-auto flex rounded-2xl bg-(--card) p-1" role="tablist">
        <button v-for="f in filters" :key="f.id" role="tab" :aria-selected="filter === f.id" @click="filter = f.id"
                class="rounded-xl px-3.5 py-1.5 text-sm transition-colors"
                :class="filter === f.id ? 'bg-(--primary) text-(--primary-ink) font-semibold' : 'text-(--muted) hover:text-(--text)'">{{ f.label }}</button>
      </div>
    </header>

    <ul v-if="alerts.length" class="space-y-2">
      <li v-for="s in alerts" :key="s.id" class="grid grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-1 rounded-2xl bg-(--card) px-4 py-3">
        <div class="grid place-items-center size-10 rounded-xl row-span-2 sm:row-span-1"
             :class="s.direction === 'BUY' ? 'text-(--profit)' : 'text-(--loss)'"
             :style="{ background: `color-mix(in oklab, ${s.direction === 'BUY' ? 'var(--profit)' : 'var(--loss)'} 14%, transparent)` }">
          <PhArrowUpRight v-if="s.direction === 'BUY'" :size="22" weight="bold" />
          <PhArrowDownRight v-else :size="22" weight="bold" />
        </div>
        <div class="min-w-0">
          <div class="font-semibold">{{ s.symbol }} <span class="font-normal text-(--muted)">{{ s.direction === 'BUY' ? 'long' : 'short' }}</span></div>
          <div class="num text-sm text-(--muted) truncate">
            {{ when(s.signal_time) }} · entry {{ px(s.entry_price ?? s.current_close) }}
            <template v-if="s.sl_price"> · SL {{ px(s.sl_price) }}</template>
            <template v-if="s.tp_price"> · TP {{ px(s.tp_price) }}</template>
            <template v-else-if="s.predicted_close"> · target {{ px(s.predicted_close) }}</template>
          </div>
        </div>
        <div class="text-right">
          <div class="num text-sm font-semibold">{{ Math.round(Number(s.confidence) * 100) }}%</div>
          <div class="num text-xs text-(--muted)">{{ (Number(s.predicted_move) * 100).toFixed(2) }}%</div>
        </div>
      </li>
    </ul>
    <div v-else class="rounded-[28px] bg-(--card) px-6 py-14 text-center">
      <PhBell :size="44" weight="duotone" class="mx-auto text-(--primary)" />
      <p class="mt-3 font-display text-xl font-semibold">No signals yet</p>
      <p class="text-(--muted) mt-1">They appear when a setup clears every trade gate.</p>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
