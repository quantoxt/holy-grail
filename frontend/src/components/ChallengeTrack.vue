<script setup lang="ts">
// The trail: fail line at the bottom-left, pass flag at the summit, live equity
// as the walker. Spending the page's boldness here and nowhere else.
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { money } from '../composables/useLive'

const props = defineProps<{ equity: number | null; fail: number; floor: number; start: number; pass: number; floorLabel?: string }>()

const TRAIL = 'M30 200 C 140 200, 190 170, 300 160 S 430 146, 520 122 S 650 104, 740 82 S 870 46, 960 28'
const pathEl = ref<SVGPathElement | null>(null)
const len = ref(1)
const pts = ref<Record<string, { x: number; y: number }>>({})

const span = computed(() => Math.max(1, props.pass - props.fail))
const frac = (v: number) => Math.min(1, Math.max(0, (v - props.fail) / span.value))
const t = computed(() => (props.equity == null ? null : frac(props.equity)))

const at = (f: number) => {
  const p = pathEl.value?.getPointAtLength(f * len.value)
  return p ? { x: p.x, y: p.y } : { x: 0, y: 0 }
}
const measure = () => {
  if (!pathEl.value) return
  len.value = pathEl.value.getTotalLength()
  pts.value = {
    fail: at(0), floor: at(frac(props.floor)), start: at(frac(props.start)), pass: at(1),
    walker: at(t.value ?? frac(props.start)),
  }
}
onMounted(measure)
watch(() => [props.equity, props.fail, props.floor, props.start, props.pass], () => nextTick(measure))

const marks = computed(() => [
  { key: 'fail', label: 'Account fails', value: props.fail, tone: 'var(--loss)' },
  { key: 'floor', label: props.floorLabel ?? 'Bot stops', value: props.floor, tone: 'var(--loss)' },
  { key: 'start', label: 'Start', value: props.start, tone: 'var(--muted)' },
].filter((m, i, a) => i === 0 || Math.abs(m.value - a[i - 1].value) > 0.01))
</script>

<template>
  <figure class="relative">
    <svg viewBox="0 0 1000 240" class="w-full h-auto overflow-visible" role="img"
         :aria-label="`Equity ${money(equity)}: fails at ${money(fail)}, passes at ${money(pass)}`">
      <!-- hills -->
      <path d="M0 240 L0 170 C 120 120, 200 180, 320 130 S 520 40, 640 90 S 820 10, 1000 40 L1000 240 Z" fill="var(--sunk)" />
      <path d="M0 240 L0 215 C 160 190, 300 230, 480 190 S 760 170, 1000 150 L1000 240 Z" fill="var(--border)" opacity=".7" />
      <!-- trail: whole route dotted, travelled part solid honey -->
      <path ref="pathEl" :d="TRAIL" fill="none" stroke="var(--primary)" stroke-width="3" stroke-dasharray="2 9" stroke-linecap="round" opacity=".55" />
      <path v-if="t !== null" :d="TRAIL" fill="none" stroke="var(--honey)" stroke-width="5" stroke-linecap="round"
            :stroke-dasharray="`${t * len} ${len}`" class="travel" />
      <!-- markers -->
      <g v-for="m in marks" :key="m.key">
        <circle v-if="pts[m.key]" :cx="pts[m.key].x" :cy="pts[m.key].y" r="6" :fill="m.key === 'fail' ? m.tone : 'var(--card)'" :stroke="m.tone" stroke-width="3" />
      </g>
      <!-- summit flag -->
      <g v-if="pts.pass" :transform="`translate(${pts.pass.x} ${pts.pass.y})`">
        <line x1="0" y1="0" x2="0" y2="-34" stroke="var(--text)" stroke-width="2.5" stroke-linecap="round" />
        <path d="M0 -34 L22 -27 L0 -20 Z" fill="var(--primary)" />
      </g>
      <!-- walker -->
      <g v-if="pts.walker && t !== null" class="walker" :style="{ transform: `translate(${pts.walker.x}px, ${pts.walker.y}px)` }">
        <circle r="17" fill="var(--honey)" opacity=".22" />
        <circle r="9" fill="var(--honey)" stroke="var(--card)" stroke-width="3" />
      </g>
    </svg>

    <figcaption class="mt-3 grid grid-cols-1 min-[480px]:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-2 text-sm">
      <div v-for="m in marks" :key="m.key" class="flex items-center gap-2">
        <span class="size-2.5 rounded-full shrink-0" :style="m.key === 'fail' ? { background: m.tone } : { border: `2px solid ${m.tone}` }" />
        <span class="text-(--muted)">{{ m.label }}</span>
        <span class="num ml-auto sm:ml-0 font-medium">{{ money(m.value) }}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="size-2.5 rounded-full shrink-0 bg-(--primary)" />
        <span class="text-(--muted)">Pass</span>
        <span class="num ml-auto sm:ml-0 font-medium">{{ money(pass) }}</span>
      </div>
    </figcaption>
  </figure>
</template>

<style>
@reference "tailwindcss";
.walker { transition: transform 900ms cubic-bezier(.3,.7,.2,1); }
.travel { transition: stroke-dasharray 900ms cubic-bezier(.3,.7,.2,1); }
</style>
