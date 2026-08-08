<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const perf = ref({ total_trades: 0, closed: 0, wins: 0, win_rate: 0, net_pnl: 0 })
const signals = ref<any[]>([])
const trades = ref<any[]>([])
let timer: number

const fetchData = async () => {
  try {
    const [p, s, t] = await Promise.all([
      fetch('/api/performance').then(r => r.json()),
      fetch('/api/signals?limit=10').then(r => r.json()),
      fetch('/api/trades?limit=10').then(r => r.json()),
    ])
    perf.value = p; signals.value = s; trades.value = t
  } catch {}
}
onMounted(() => { fetchData(); timer = setInterval(fetchData, 5000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="space-y-6">
    <h2 class="text-xl font-semibold">Dashboard</h2>

    <!-- Stat cards -->
    <div class="grid grid-cols-4 gap-4">
      <div class="bg-(--card) border border-(--border) rounded-lg p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">Net P&L</div>
        <div class="text-2xl font-bold mt-1"
             :class="perf.net_pnl >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
          {{ perf.net_pnl >= 0 ? '+' : '' }}{{ perf.net_pnl.toFixed(2) }}
        </div>
      </div>
      <div class="bg-(--card) border border-(--border) rounded-lg p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">Win Rate</div>
        <div class="text-2xl font-bold mt-1">{{ (perf.win_rate * 100).toFixed(1) }}%</div>
      </div>
      <div class="bg-(--card) border border-(--border) rounded-lg p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">Trades</div>
        <div class="text-2xl font-bold mt-1">{{ perf.total_trades }}</div>
      </div>
      <div class="bg-(--card) border border-(--border) rounded-lg p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">W / L</div>
        <div class="text-2xl font-bold mt-1">{{ perf.wins }} / {{ perf.closed - perf.wins }}</div>
      </div>
    </div>

    <!-- Recent signals -->
    <div>
      <h3 class="text-sm font-medium text-(--muted) uppercase mb-2">Recent Signals</h3>
      <div class="bg-(--card) border border-(--border) rounded-lg overflow-hidden">
        <table class="w-full text-sm">
          <thead class="text-(--muted) border-b border-(--border)">
            <tr>
              <th class="text-left p-2">Time</th>
              <th class="text-left p-2">Symbol</th>
              <th class="text-left p-2">Dir</th>
              <th class="text-right p-2">Move</th>
              <th class="text-right p-2">Conf</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in signals" :key="s.id" class="border-b border-(--border) last:border-0">
              <td class="p-2 text-(--muted)">{{ new Date(s.signal_time).toLocaleTimeString() }}</td>
              <td class="p-2">{{ s.symbol }}</td>
              <td class="p-2 font-medium"
                  :class="s.direction === 'BUY' ? 'text-(--profit)' : s.direction === 'SELL' ? 'text-(--loss)' : 'text-(--muted)'">
                {{ s.direction }}
              </td>
              <td class="p-2 text-right">{{ (s.predicted_move * 100).toFixed(2) }}%</td>
              <td class="p-2 text-right">{{ (s.confidence * 100).toFixed(0) }}%</td>
            </tr>
            <tr v-if="!signals.length">
              <td colspan="5" class="p-4 text-center text-(--muted)">No signals yet — run the bot to populate.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
