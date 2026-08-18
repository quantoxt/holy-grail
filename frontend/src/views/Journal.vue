<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { supabase } from '../lib/supabase'

const banks = ref<any[]>([])
const selected = ref<string | null>(null)
const today = new Date()
const viewYear = ref(today.getUTCFullYear())
const viewMonth = ref(today.getUTCMonth())   // 0-based, UTC months

onMounted(async () => {
  try {
    const { data } = await supabase.from('risk_events')
      .select('created_at, reason')
      .eq('event_type', 'goal_banked')
      .order('created_at', { ascending: true })
      .limit(500)
    banks.value = data || []
    const last = banks.value[banks.value.length - 1]
    if (last) selected.value = dayKey(new Date(last.created_at))
  } catch {}
})

const dayKey = (d: Date) => d.toISOString().slice(0, 10)

// banked events keyed by UTC day
const byDay = computed(() => {
  const m: Record<string, any> = {}
  for (const b of banks.value) m[dayKey(new Date(b.created_at))] = b
  return m
})

// time-to-goal: from the goal period start (Monday 00:00 UTC of that week)
const mondayOf = (iso: string) => {
  const d = new Date(iso)
  const day = d.getUTCDay()                       // 0=Sun … 6=Sat
  const diff = day === 0 ? 6 : day - 1             // back to Monday
  const mon = new Date(d)
  mon.setUTCDate(d.getUTCDate() - diff)
  mon.setUTCHours(0, 0, 0, 0)
  return mon
}
const hoursToGoal = (iso: string) =>
  (new Date(iso).getTime() - mondayOf(iso).getTime()) / 3600000
const fmtDuration = (h: number) => {
  const d = Math.floor(h / 24)
  const hr = Math.round(h % 24)
  return d > 0 ? `${d}d ${hr}h` : `${hr}h`
}

// calendar grid for the viewed month — Monday-first weeks
const grid = computed(() => {
  const first = new Date(Date.UTC(viewYear.value, viewMonth.value, 1))
  const daysInMonth = new Date(Date.UTC(viewYear.value, viewMonth.value + 1, 0)).getUTCDate()
  const lead = (first.getUTCDay() + 6) % 7        // blanks before the 1st
  const cells: (string | null)[] = Array(lead).fill(null)
  for (let d = 1; d <= daysInMonth; d++)
    cells.push(`${viewYear.value}-${String(viewMonth.value + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`)
  while (cells.length % 7) cells.push(null)
  return cells
})

const monthLabel = computed(() =>
  new Date(Date.UTC(viewYear.value, viewMonth.value, 1))
    .toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' }))

const shiftMonth = (delta: number) => {
  const m = viewMonth.value + delta
  viewMonth.value = ((m % 12) + 12) % 12
  viewYear.value += Math.floor(m / 12)
}

const banksThisMonth = computed(() => {
  const prefix = `${viewYear.value}-${String(viewMonth.value + 1).padStart(2, '0')}`
  return banks.value.filter((b) => b.created_at.startsWith(prefix))
})

const selectedBank = computed(() => (selected.value ? byDay[selected.value] : null))
const selectedHours = computed(() =>
  selectedBank.value ? hoursToGoal(selectedBank.value.created_at) : null)
</script>

<template>
  <div class="space-y-4">
    <h2 class="text-xl font-semibold">Journal</h2>
    <p class="text-(--muted) text-sm -mt-2">
      Days the weekly $14 goal was banked, and how long into the goal week (Mon 00:00 UTC) it took.
    </p>

    <div class="grid md:grid-cols-2 gap-4 items-start">
      <!-- Calendar -->
      <div class="bg-(--card) border border-(--border) rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <button @click="shiftMonth(-1)" class="text-(--muted) hover:text-(--text) px-2">‹</button>
          <div class="font-medium">{{ monthLabel }}</div>
          <button @click="shiftMonth(1)" class="text-(--muted) hover:text-(--text) px-2">›</button>
        </div>
        <div class="grid grid-cols-7 text-center text-xs text-(--muted) mb-1">
          <span v-for="d in ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']" :key="d">{{ d }}</span>
        </div>
        <div class="grid grid-cols-7 gap-1 text-center text-sm">
          <template v-for="(cell, i) in grid" :key="i">
            <div v-if="cell === null"></div>
            <button v-else @click="byDay[cell] && (selected = cell)"
              class="aspect-square rounded flex items-center justify-center relative transition-colors"
              :class="[
                byDay[cell] ? 'bg-(--profit)/15 text-(--profit) font-semibold cursor-pointer'
                            : 'text-(--muted)',
                selected === cell ? 'ring-1 ring-(--primary)' : '',
                cell === dayKey(new Date()) ? 'outline outline-1 outline-(--border)' : '',
              ]">
              {{ Number(cell.slice(8)) }}
              <span v-if="byDay[cell]" class="absolute bottom-1 w-1 h-1 rounded-full bg-(--profit)"></span>
            </button>
          </template>
        </div>
        <div class="mt-3 text-xs text-(--muted) flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-(--profit) inline-block"></span>
          goal banked
        </div>
      </div>

      <!-- Detail + history -->
      <div class="space-y-4">
        <div v-if="selectedBank" class="bg-(--card) border border-(--border) rounded-lg p-4">
          <div class="text-(--profit) font-semibold mb-1">🎯 Goal banked — {{ selected }}</div>
          <div class="text-sm space-y-1">
            <div>Time to goal: <span class="text-(--text) font-medium">{{ fmtDuration(selectedHours ?? 0) }}</span> into the goal week</div>
            <div class="text-(--muted) text-xs">{{ selectedBank.reason }}</div>
            <div class="text-(--muted) text-xs">{{ new Date(selectedBank.created_at).toUTCString() }}</div>
          </div>
        </div>
        <div v-else class="bg-(--card) border border-(--border) rounded-lg p-4 text-(--muted) text-sm">
          Select a highlighted day to see its details.
        </div>

        <div v-if="banksThisMonth.length" class="bg-(--card) border border-(--border) rounded-lg divide-y divide-(--border)">
          <div v-for="b in [...banksThisMonth].reverse()" :key="b.created_at"
               class="p-3 flex items-center gap-3 text-sm cursor-pointer hover:bg-(--bg)"
               @click="selected = dayKey(new Date(b.created_at))">
            <span class="text-(--profit)">●</span>
            <span class="flex-1">{{ dayKey(new Date(b.created_at)) }}</span>
            <span class="text-(--muted)">{{ fmtDuration(hoursToGoal(b.created_at)) }}</span>
          </div>
        </div>
        <div v-else class="text-(--muted) text-sm">No goals banked this month yet.</div>
      </div>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
