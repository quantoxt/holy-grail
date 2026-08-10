<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { supabase } from '../lib/supabase'

const trades = ref<any[]>([])
let timer: number
const fetchTrades = async () => {
  try {
    const { data } = await supabase.from('trades')
      .select('*').order('created_at', { ascending: false }).limit(50)
    trades.value = data || []
  } catch {}
}
onMounted(() => { fetchTrades(); timer = setInterval(fetchTrades, 5000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="space-y-4">
    <h2 class="text-xl font-semibold">Trades</h2>
    <div class="bg-(--card) border border-(--border) rounded-lg overflow-hidden">
      <div class="overflow-x-auto">
      <table class="w-full text-sm min-w-[40rem]">
        <thead class="text-(--muted) border-b border-(--border)">
          <tr>
            <th class="text-left p-2">Time</th>
            <th class="text-left p-2">Symbol</th>
            <th class="text-left p-2">Dir</th>
            <th class="text-right p-2">Entry</th>
            <th class="text-right p-2">Exit</th>
            <th class="text-right p-2">Size</th>
            <th class="text-right p-2">P&L</th>
            <th class="text-center p-2">Result</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in trades" :key="t.id" class="border-b border-(--border) last:border-0">
            <td class="p-2 text-(--muted)">{{ new Date(t.entry_time).toLocaleTimeString() }}</td>
            <td class="p-2">{{ t.symbol }}</td>
            <td class="p-2 font-medium"
                :class="t.direction === 'BUY' ? 'text-(--profit)' : 'text-(--loss)'">{{ t.direction }}</td>
            <td class="p-2 text-right">{{ t.entry_price?.toFixed(2) ?? '—' }}</td>
            <td class="p-2 text-right">{{ t.exit_price?.toFixed(2) ?? '—' }}</td>
            <td class="p-2 text-right">{{ t.size?.toFixed(1) ?? '—' }}</td>
            <td class="p-2 text-right font-medium"
                :class="(t.pnl ?? 0) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
              {{ t.pnl != null ? (t.pnl >= 0 ? '+' : '') + t.pnl.toFixed(2) : '—' }}
            </td>
            <td class="p-2 text-center">
              <span v-if="t.result === 'win'" class="text-(--profit)">WIN</span>
              <span v-else-if="t.result === 'loss'" class="text-(--loss)">LOSS</span>
              <span v-else class="text-(--muted)">{{ t.result ?? '—' }}</span>
            </td>
          </tr>
          <tr v-if="!trades.length">
            <td colspan="8" class="p-4 text-center text-(--muted)">No trades yet.</td>
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
