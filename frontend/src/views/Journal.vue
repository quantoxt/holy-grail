<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { supabase } from '../lib/supabase'

const banks = ref<any[]>([])
const entries = ref<Record<string, any>>({})
const selected = ref<string | null>(null)
const today = new Date()
const viewYear = ref(today.getUTCFullYear())
const viewMonth = ref(today.getUTCMonth())   // 0-based, UTC months
const saving = ref(false)
const savedFlash = ref(false)

const dayKey = (d: Date) => d.toISOString().slice(0, 10)

// editable draft for the selected day
const draft = ref({ title: '', note: '', tags: '' })
const loadDraft = (date: string) => {
  const e = entries.value[date]
  draft.value = { title: e?.title ?? '', note: e?.note ?? '', tags: e?.tags ?? '' }
}

const refresh = async () => {
  try {
    const [{ data: b }, { data: e }] = await Promise.all([
      supabase.from('risk_events').select('created_at, reason')
        .eq('event_type', 'goal_banked').order('created_at', { ascending: true }).limit(500),
      supabase.from('journal_entries').select('*').order('entry_date').limit(1000),
    ])
    banks.value = b || []
    const m: Record<string, any> = {}
    for (const row of e || []) m[row.entry_date] = row
    entries.value = m
  } catch {}
}
onMounted(async () => {
  await refresh()
  const last = banks.value[banks.value.length - 1]
  const start = selected.value = last
    ? dayKey(new Date(last.created_at))
    : dayKey(today)
  loadDraft(start)
})

// banked goal events keyed by UTC day
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

const pick = (cell: string | null) => {
  if (!cell) return
  selected.value = cell
  loadDraft(cell)
}

const banksThisMonth = computed(() => {
  const prefix = `${viewYear.value}-${String(viewMonth.value + 1).padStart(2, '0')}`
  return banks.value.filter((b) => b.created_at.startsWith(prefix))
})

const selectedBank = computed(() => (selected.value ? byDay[selected.value] : null))
const selectedHours = computed(() =>
  selectedBank.value ? hoursToGoal(selectedBank.value.created_at) : null)
const hasEntry = computed(() => !!(selected.value && entries.value[selected.value]))

const save = async () => {
  if (!selected.value) return
  saving.value = true
  try {
    const payload = { entry_date: selected.value, ...draft.value, updated_at: new Date().toISOString() }
    const { error } = await supabase.from('journal_entries').upsert(payload, { onConflict: 'entry_date' })
    if (!error) {
      entries.value[selected.value] = { ...(entries.value[selected.value] ?? {}), ...payload }
      savedFlash.value = true
      setTimeout(() => (savedFlash.value = false), 1500)
    }
  } finally { saving.value = false }
}

const remove = async () => {
  if (!selected.value || !hasEntry.value) return
  saving.value = true
  try {
    const { error } = await supabase.from('journal_entries').delete().eq('entry_date', selected.value)
    if (!error) {
      delete entries.value[selected.value]
      loadDraft(selected.value)
    }
  } finally { saving.value = false }
}
</script>

<template>
  <div class="space-y-4">
    <h2 class="text-xl font-semibold">Journal</h2>
    <p class="text-(--muted) text-sm -mt-2">
      Days the weekly $14 goal was banked (auto), with your own notes per day — editable right here.
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
            <button v-else @click="pick(cell)"
              class="aspect-square rounded flex items-center justify-center relative transition-colors"
              :class="[
                byDay[cell] ? 'bg-(--profit)/15 text-(--profit) font-semibold'
                            : 'text-(--muted) hover:text-(--text)',
                entries[cell] ? 'bg-(--primary)/15' : '',
                selected === cell ? 'ring-1 ring-(--primary)' : '',
                cell === dayKey(today) ? 'outline outline-1 outline-(--border)' : '',
              ]">
              {{ Number(cell.slice(8)) }}
              <span v-if="byDay[cell]" class="absolute bottom-1 w-1 h-1 rounded-full bg-(--profit)"></span>
              <span v-if="entries[cell]" class="absolute top-1 right-1 w-1 h-1 rounded-full bg-(--primary)"></span>
            </button>
          </template>
        </div>
        <div class="mt-3 text-xs text-(--muted) flex items-center gap-3">
          <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-(--profit) inline-block"></span> goal banked</span>
          <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-(--primary) inline-block"></span> has note</span>
        </div>
      </div>

      <!-- Detail + editor -->
      <div class="space-y-4">
        <div class="bg-(--card) border border-(--border) rounded-lg p-4 space-y-2">
          <div class="flex items-center justify-between">
            <div class="font-semibold">{{ selected ?? '—' }}
              <span v-if="selectedBank" class="text-(--profit) text-sm ml-2">🎯 goal banked · {{ fmtDuration(selectedHours ?? 0) }}</span>
            </div>
            <span v-if="savedFlash" class="text-(--profit) text-xs">saved ✓</span>
          </div>
          <div v-if="selectedBank" class="text-(--muted) text-xs">{{ selectedBank.reason }} · {{ new Date(selectedBank.created_at).toUTCString() }}</div>

          <div class="space-y-2 pt-1">
            <input v-model="draft.title" placeholder="Title (e.g. Scalping fix deployed)"
                   class="w-full bg-(--bg) border border-(--border) rounded px-2 py-1.5 text-sm" />
            <textarea v-model="draft.note" rows="4" placeholder="Notes for this day…"
                      class="w-full bg-(--bg) border border-(--border) rounded px-2 py-1.5 text-sm" />
            <input v-model="draft.tags" placeholder="tags, comma separated"
                   class="w-full bg-(--bg) border border-(--border) rounded px-2 py-1.5 text-sm" />
            <div class="flex gap-2">
              <button @click="save" :disabled="saving || !selected"
                      class="px-3 py-1.5 rounded text-sm bg-(--primary) text-(--bg) font-medium disabled:opacity-50">
                {{ saving ? 'Saving…' : hasEntry ? 'Update' : 'Add entry' }}
              </button>
              <button v-if="hasEntry" @click="remove" :disabled="saving"
                      class="px-3 py-1.5 rounded text-sm border border-(--border) text-(--loss) disabled:opacity-50">
                Delete
              </button>
            </div>
          </div>
        </div>

        <div v-if="banksThisMonth.length" class="bg-(--card) border border-(--border) rounded-lg divide-y divide-(--border)">
          <div v-for="b in [...banksThisMonth].reverse()" :key="b.created_at"
               class="p-3 flex items-center gap-3 text-sm cursor-pointer hover:bg-(--bg)"
               @click="pick(dayKey(new Date(b.created_at)))">
            <span class="text-(--profit)">●</span>
            <span class="flex-1">{{ dayKey(new Date(b.created_at)) }}</span>
            <span class="text-(--muted)">{{ fmtDuration(hoursToGoal(b.created_at)) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
