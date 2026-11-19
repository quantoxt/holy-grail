<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { PhChartLineUp } from '@phosphor-icons/vue'
import { supabase } from '../lib/supabase'
import { useLive, money } from '../composables/useLive'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, MarkLineComponent])

const { closed, stop } = useLive()
onUnmounted(stop)

// --- theme-aware colours (re-read when the theme flips) ---
const tick = ref(0)
const css = (name: string) => { void tick.value; return getComputedStyle(document.documentElement).getPropertyValue(name).trim() }
let mo: MutationObserver | undefined
const mq = window.matchMedia('(prefers-color-scheme: dark)')
const bump = () => tick.value++
onMounted(() => {
  mo = new MutationObserver(bump)
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  mq.addEventListener('change', bump)
})
onUnmounted(() => { mo?.disconnect(); mq.removeEventListener('change', bump) })

// --- prediction accuracy (separate table, fetched once per visit) ---
const evals = ref<any[]>([])
onMounted(async () => {
  const { data } = await supabase.from('prediction_evaluations').select('symbol,outcome')
    .in('outcome', ['hit', 'miss']).order('signal_time', { ascending: false }).limit(5000)
  evals.value = data || []
})

const sorted = computed(() => [...closed.value].filter((t) => t.exit_time).sort((a, b) => +new Date(a.exit_time) - +new Date(b.exit_time)))

const stats = computed(() => {
  const pnls = sorted.value.map((t) => Number(t.pnl) || 0)
  const wins = pnls.filter((p) => p > 0), losses = pnls.filter((p) => p < 0)
  const gw = wins.reduce((s, p) => s + p, 0), gl = -losses.reduce((s, p) => s + p, 0)
  let peak = 0, run = 0, dd = 0
  for (const p of pnls) { run += p; peak = Math.max(peak, run); dd = Math.max(dd, peak - run) }
  return {
    net: run, n: pnls.length,
    pf: gl > 0 ? gw / gl : null,
    avgWin: wins.length ? gw / wins.length : null,
    avgLoss: losses.length ? -gl / losses.length : null,
    expectancy: pnls.length ? run / pnls.length : null,
    maxDd: dd,
  }
})

const base = () => ({
  textStyle: { fontFamily: 'Instrument Sans Variable, sans-serif', color: css('--muted') },
  grid: { left: 8, right: 12, top: 16, bottom: 8, containLabel: true },
  tooltip: {
    trigger: 'axis', backgroundColor: css('--card'), borderColor: css('--border'),
    textStyle: { color: css('--text') }, valueFormatter: (v: number) => money(v, true),
  },
})
const axisY = () => ({ type: 'value', splitLine: { lineStyle: { color: css('--border'), type: 'dashed' } }, axisLabel: { formatter: (v: number) => `$${v}` } })

const equityOpt = computed(() => {
  let run = 0
  const pts = sorted.value.map((t) => [t.exit_time, +(run += Number(t.pnl) || 0).toFixed(2)])
  return {
    ...base(),
    xAxis: { type: 'time', axisLine: { lineStyle: { color: css('--border') } }, splitLine: { show: false } },
    yAxis: axisY(),
    series: [{
      type: 'line', data: pts, smooth: 0.35, symbol: 'none',
      lineStyle: { width: 3, color: css('--primary') },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: css('--primary') + '55' }, { offset: 1, color: css('--primary') + '00' }] } },
      markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0 }], lineStyle: { color: css('--muted'), type: 'dotted' }, label: { show: false } },
    }],
  }
})

const bySymbol = computed(() => {
  const m = new Map<string, { pnl: number; n: number; w: number }>()
  for (const t of sorted.value) {
    const r = m.get(t.symbol) ?? { pnl: 0, n: 0, w: 0 }
    r.pnl += Number(t.pnl) || 0; r.n++; if (t.result === 'win') r.w++
    m.set(t.symbol, r)
  }
  return [...m.entries()].sort((a, b) => b[1].pnl - a[1].pnl)
})
const symbolOpt = computed(() => ({
  ...base(),
  xAxis: { type: 'category', data: bySymbol.value.map(([s]) => s), axisTick: { show: false }, axisLine: { lineStyle: { color: css('--border') } } },
  yAxis: axisY(),
  series: [{
    type: 'bar', barMaxWidth: 46,
    data: bySymbol.value.map(([, r]) => ({ value: +r.pnl.toFixed(2), itemStyle: { color: r.pnl >= 0 ? css('--profit') : css('--loss'), borderRadius: r.pnl >= 0 ? [10, 10, 4, 4] : [4, 4, 10, 10] } })),
  }],
}))

const histOpt = computed(() => {
  const pnls = sorted.value.map((t) => Number(t.pnl) || 0)
  const lo = Math.floor(Math.min(0, ...pnls) / 5) * 5, hi = Math.ceil(Math.max(0, ...pnls) / 5) * 5
  const step = Math.max(5, Math.ceil((hi - lo) / 14 / 5) * 5)
  const bins: { label: string; mid: number; n: number }[] = []
  for (let a = lo; a < hi || bins.length === 0; a += step) bins.push({ label: `${a}`, mid: a + step / 2, n: pnls.filter((p) => p >= a && p < a + step).length })
  return {
    ...base(),
    tooltip: { ...base().tooltip, valueFormatter: (v: number) => `${v} trades` },
    xAxis: { type: 'category', data: bins.map((b) => money(Number(b.label)).replace('.00', '')), axisTick: { show: false }, axisLine: { lineStyle: { color: css('--border') } } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: css('--border'), type: 'dashed' } } },
    series: [{ type: 'bar', barCategoryGap: '18%', data: bins.map((b) => ({ value: b.n, itemStyle: { color: b.mid >= 0 ? css('--profit') : css('--loss'), borderRadius: [8, 8, 2, 2] } })) }],
  }
})

const hourOpt = computed(() => {
  const h = Array.from({ length: 24 }, () => 0)
  for (const t of sorted.value) if (t.entry_time) h[new Date(t.entry_time).getUTCHours()] += Number(t.pnl) || 0
  return {
    ...base(),
    xAxis: { type: 'category', data: h.map((_, i) => `${i}`), axisTick: { show: false }, axisLine: { lineStyle: { color: css('--border') } } },
    yAxis: axisY(),
    series: [{ type: 'bar', data: h.map((v) => ({ value: +v.toFixed(2), itemStyle: { color: v >= 0 ? css('--honey') : css('--loss'), borderRadius: 6 } })) }],
  }
})

const accuracy = computed(() => {
  const m = new Map<string, { hit: number; n: number }>()
  for (const e of evals.value) {
    const r = m.get(e.symbol) ?? { hit: 0, n: 0 }
    r.n++; if (e.outcome === 'hit') r.hit++
    m.set(e.symbol, r)
  }
  return [...m.entries()].map(([symbol, r]) => ({ symbol, rate: r.hit / r.n, n: r.n })).sort((a, b) => b.n - a.n)
})
</script>

<template>
  <div class="space-y-10">
    <header>
      <h1 class="font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-semibold tracking-tight">Analytics</h1>
      <p class="text-(--muted) mt-1">How the bot has done on this account, closed trades only.</p>
    </header>

    <div v-if="!sorted.length" class="rounded-[28px] bg-(--card) px-6 py-14 text-center">
      <PhChartLineUp :size="44" weight="duotone" class="mx-auto text-(--primary)" />
      <p class="mt-3 font-display text-xl font-semibold">No closed trades yet</p>
      <p class="text-(--muted) mt-1">Charts fill in once the first trade on this account closes.</p>
    </div>

    <template v-else>
      <dl class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-6 gap-y-5">
        <div><dt class="text-sm text-(--muted)">Net result</dt><dd class="font-display num text-2xl font-semibold mt-0.5" :class="stats.net >= 0 ? 'text-(--profit)' : 'text-(--loss)'">{{ money(stats.net, true) }}</dd></div>
        <div><dt class="text-sm text-(--muted)">Trades</dt><dd class="font-display num text-2xl font-semibold mt-0.5">{{ stats.n }}</dd></div>
        <div><dt class="text-sm text-(--muted)">Profit factor</dt><dd class="font-display num text-2xl font-semibold mt-0.5">{{ stats.pf == null ? '—' : stats.pf.toFixed(2) }}</dd></div>
        <div><dt class="text-sm text-(--muted)">Average win</dt><dd class="font-display num text-2xl font-semibold mt-0.5 text-(--profit)">{{ money(stats.avgWin) }}</dd></div>
        <div><dt class="text-sm text-(--muted)">Average loss</dt><dd class="font-display num text-2xl font-semibold mt-0.5 text-(--loss)">{{ money(stats.avgLoss) }}</dd></div>
        <div><dt class="text-sm text-(--muted)">Deepest dip</dt><dd class="font-display num text-2xl font-semibold mt-0.5">{{ money(-stats.maxDd) }}</dd></div>
      </dl>

      <section class="rounded-[28px] bg-(--card) p-5 md:p-7">
        <h2 class="font-display text-xl font-semibold">Running result</h2>
        <p class="text-sm text-(--muted)">Cumulative profit after each closed trade.</p>
        <div class="h-72 mt-3"><VChart :option="equityOpt" autoresize style="height:100%;width:100%" /></div>
      </section>

      <div class="grid gap-6 lg:grid-cols-2">
        <section class="rounded-[28px] bg-(--card) p-5 md:p-7">
          <h2 class="font-display text-xl font-semibold">By instrument</h2>
          <p class="text-sm text-(--muted)">Net result per symbol, with win rate.</p>
          <div class="h-56 mt-3"><VChart :option="symbolOpt" autoresize style="height:100%;width:100%" /></div>
          <ul class="mt-3 flex flex-wrap gap-2 text-sm">
            <li v-for="[s, r] in bySymbol" :key="s" class="rounded-full bg-(--bg) px-3 py-1"><span class="font-medium">{{ s }}</span> <span class="num text-(--muted)">{{ Math.round(r.w / r.n * 100) }}% of {{ r.n }}</span></li>
          </ul>
        </section>
        <section class="rounded-[28px] bg-(--card) p-5 md:p-7">
          <h2 class="font-display text-xl font-semibold">Trade outcomes</h2>
          <p class="text-sm text-(--muted)">How many trades closed in each profit band.</p>
          <div class="h-64 mt-3"><VChart :option="histOpt" autoresize style="height:100%;width:100%" /></div>
        </section>
      </div>

      <div class="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section class="rounded-[28px] bg-(--card) p-5 md:p-7">
          <h2 class="font-display text-xl font-semibold">By hour opened</h2>
          <p class="text-sm text-(--muted)">Net result by the UTC hour each trade opened.</p>
          <div class="h-56 mt-3"><VChart :option="hourOpt" autoresize style="height:100%;width:100%" /></div>
        </section>
        <section class="rounded-[28px] bg-(--card) p-5 md:p-7">
          <h2 class="font-display text-xl font-semibold">Prediction accuracy</h2>
          <p class="text-sm text-(--muted)">How often the model called the 2-hour direction right. 50% is a coin flip.</p>
          <ul class="mt-5 space-y-4">
            <li v-for="a in accuracy" :key="a.symbol">
              <div class="flex justify-between text-sm"><span class="font-medium">{{ a.symbol }}</span><span class="num text-(--muted)">{{ (a.rate * 100).toFixed(1) }}% of {{ a.n }}</span></div>
              <div class="relative mt-1.5 h-2.5 rounded-full bg-(--sunk)">
                <div class="h-full rounded-full" :style="{ width: `${a.rate * 100}%`, background: a.rate >= 0.55 ? 'var(--profit)' : a.rate >= 0.5 ? 'var(--honey)' : 'var(--loss)' }" />
                <div class="absolute inset-y-[-3px] left-1/2 w-0.5 rounded bg-(--text) opacity-40" title="50%" />
              </div>
            </li>
            <li v-if="!accuracy.length" class="text-(--muted) text-sm">No scored predictions yet.</li>
          </ul>
        </section>
      </div>
    </template>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
