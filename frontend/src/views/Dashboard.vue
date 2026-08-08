<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const perf = ref({ total_trades: 0, closed: 0, wins: 0, win_rate: 0, net_pnl: 0 })
const signals = ref<any[]>([])
const trades = ref<any[]>([])
const account = ref<any>({})
let timer: number

const fetchData = async () => {
  try {
    const [p, s, t, a] = await Promise.all([
      fetch('/api/performance').then(r => r.json()),
      fetch('/api/signals?limit=10').then(r => r.json()),
      fetch('/api/trades?limit=10').then(r => r.json()),
      fetch('/api/account').then(r => r.json()),
    ])
    perf.value = p; signals.value = s; trades.value = t; account.value = a || {}
  } catch {}
}
onMounted(() => { fetchData(); timer = setInterval(fetchData, 5000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="space-y-6">
    <h2 class="text-xl font-semibold">Dashboard</h2>

    <!-- Live account state (bot heartbeat) -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-medium text-(--muted) uppercase">Account</h3>
        <span v-if="account.login" class="text-xs text-(--muted)">
          {{ account.broker || 'broker' }} · #{{ account.login }}
        </span>
      </div>

      <template v-if="account.login">
        <div class="grid grid-cols-4 gap-4 mb-4">
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Balance</div>
            <div class="text-xl font-bold mt-1">${{ (account.balance ?? 0).toFixed(2) }}</div>
          </div>
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Equity</div>
            <div class="text-xl font-bold mt-1">${{ (account.equity ?? 0).toFixed(2) }}</div>
          </div>
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Floating P&L</div>
            <div class="text-xl font-bold mt-1"
                 :class="(account.floating_pnl ?? 0) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
              {{ (account.floating_pnl ?? 0) >= 0 ? '+' : '' }}{{ (account.floating_pnl ?? 0).toFixed(2) }}
            </div>
          </div>
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Open</div>
            <div class="text-xl font-bold mt-1">{{ (account.open_positions ?? []).length }}</div>
          </div>
        </div>

        <!-- Open positions -->
        <div v-if="(account.open_positions ?? []).length" class="overflow-hidden rounded border border-(--border)">
          <table class="w-full text-sm">
            <thead class="text-(--muted) border-b border-(--border) bg-(--bg)">
              <tr>
                <th class="text-left p-2">Symbol</th>
                <th class="text-left p-2">Side</th>
                <th class="text-right p-2">Vol</th>
                <th class="text-right p-2">Entry</th>
                <th class="text-right p-2">P&L</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in account.open_positions" :key="p.ticket" class="border-b border-(--border) last:border-0">
                <td class="p-2">{{ p.symbol }}</td>
                <td class="p-2 font-medium" :class="p.type === 'BUY' ? 'text-(--profit)' : 'text-(--loss)'">{{ p.type }}</td>
                <td class="p-2 text-right">{{ p.volume }}</td>
                <td class="p-2 text-right">{{ (p.entry ?? 0).toFixed(p.entry > 1000 ? 0 : 2) }}</td>
                <td class="p-2 text-right" :class="(p.profit ?? 0) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
                  {{ (p.profit ?? 0) >= 0 ? '+' : '' }}{{ (p.profit ?? 0).toFixed(2) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <div v-else class="text-center text-(--muted) text-sm py-6">
        Awaiting bot heartbeat — live balance, equity &amp; open positions appear here once the bot connects.
      </div>
    </div>

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
