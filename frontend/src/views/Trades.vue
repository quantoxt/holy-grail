<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { PhArrowUpRight, PhArrowDownRight, PhListBullets } from '@phosphor-icons/vue'
import { useLive, money } from '../composables/useLive'

const { trades, stop } = useLive()
onUnmounted(stop)

const filter = ref<'all' | 'open' | 'win' | 'loss'>('all')
const filters = [
  { id: 'all', label: 'All' }, { id: 'open', label: 'Open' }, { id: 'win', label: 'Wins' }, { id: 'loss', label: 'Losses' },
] as const
const shown = computed(() => trades.value.filter((t) => filter.value === 'all' || t.result === filter.value).slice(0, 200))

const when = (iso?: string) => iso ? new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
const held = (t: any) => {
  if (!t.entry_time || !t.exit_time) return ''
  const m = Math.round((+new Date(t.exit_time) - +new Date(t.entry_time)) / 60000)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`
}
const px = (v: unknown) => (v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 5 }))
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end gap-4">
      <div>
        <h1 class="font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-semibold tracking-tight">Trades</h1>
        <p class="text-(--muted) mt-1">Every trade the bot placed on this account.</p>
      </div>
      <div class="ml-auto flex rounded-2xl bg-(--card) p-1" role="tablist">
        <button v-for="f in filters" :key="f.id" role="tab" :aria-selected="filter === f.id" @click="filter = f.id"
                class="rounded-xl px-3.5 py-1.5 text-sm transition-colors"
                :class="filter === f.id ? 'bg-(--primary) text-(--primary-ink) font-semibold' : 'text-(--muted) hover:text-(--text)'">{{ f.label }}</button>
      </div>
    </header>

    <ul v-if="shown.length" class="space-y-2">
      <li v-for="t in shown" :key="t.id" class="grid grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-1 rounded-2xl bg-(--card) px-4 py-3">
        <div class="grid place-items-center size-10 rounded-xl row-span-2 sm:row-span-1"
             :class="t.direction === 'BUY' ? 'text-(--profit)' : 'text-(--loss)'"
             :style="{ background: `color-mix(in oklab, ${t.direction === 'BUY' ? 'var(--profit)' : 'var(--loss)'} 14%, transparent)` }">
          <PhArrowUpRight v-if="t.direction === 'BUY'" :size="22" weight="bold" />
          <PhArrowDownRight v-else :size="22" weight="bold" />
        </div>
        <div class="min-w-0">
          <div class="font-semibold">{{ t.symbol }} <span class="font-normal text-(--muted)">{{ t.direction === 'BUY' ? 'long' : 'short' }}<template v-if="t.lots"> {{ Number(t.lots).toFixed(2) }} lots</template></span></div>
          <div class="num text-sm text-(--muted) truncate">{{ when(t.entry_time) }}, {{ px(t.entry_price) }} <template v-if="t.exit_price"> to {{ px(t.exit_price) }}</template><template v-if="held(t)">, held {{ held(t) }}</template></div>
        </div>
        <div class="text-right">
          <div v-if="t.result === 'open'" class="rounded-full bg-(--bg) px-3 py-1 text-sm text-(--muted)">open</div>
          <div v-else class="num font-semibold" :class="Number(t.pnl) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">{{ money(t.pnl, true) }}</div>
        </div>
      </li>
    </ul>
    <div v-else class="rounded-[28px] bg-(--card) px-6 py-14 text-center">
      <PhListBullets :size="44" weight="duotone" class="mx-auto text-(--primary)" />
      <p class="mt-3 font-display text-xl font-semibold">{{ filter === 'all' ? 'No trades yet' : 'Nothing here' }}</p>
      <p class="text-(--muted) mt-1">{{ filter === 'all' ? 'Trades appear as soon as the bot places one.' : 'Try another filter.' }}</p>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
