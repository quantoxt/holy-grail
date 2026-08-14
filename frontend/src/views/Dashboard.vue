<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { supabase } from '../lib/supabase'

const perf = ref({ total_trades: 0, closed: 0, wins: 0, win_rate: 0, net_pnl: 0 })
const signals = ref<any[]>([])
const trades = ref<any[]>([])
const account = ref<any>({})
const weekly = ref<any>({ weekly_pnl: 0, weekly_goal: 14, weekly_progress_pct: 0, daily_pnl: 0, total_trades: 0, win_rate: 0, consecutive_losses: 0 })
const now = ref(Date.now())
let timer: number

// Heartbeat staleness — the bot writes account_state every ~5s. If the row is
// older than 30s the bot process is dead/stuck and the numbers shown are stale
// (exactly the "dashboard stuck at 2 trades after reconnect" symptom).
const STALE_MS = 30_000
const heartbeatAge = computed(() => {
  const ts = account.value?.updated_at
  if (!ts) return null
  const age = now.value - new Date(ts).getTime()
  return Number.isFinite(age) ? age : null
})
const botOnline = computed(() => heartbeatAge.value !== null && heartbeatAge.value < STALE_MS)

const computeWeekly = (rows: any[], goal: number) => {
  const closed = rows.filter((t) => t.result === 'win' || t.result === 'loss')
  const now = new Date()
  const weekStart = new Date(now); weekStart.setHours(0, 0, 0, 0); weekStart.setDate(now.getDate() - ((now.getDay() + 6) % 7))
  const dayStart = new Date(now); dayStart.setHours(0, 0, 0, 0)
  const inWeek = (t: any) => t.exit_time && new Date(t.exit_time) >= weekStart
  const inDay = (t: any) => t.exit_time && new Date(t.exit_time) >= dayStart
  const weeklyPnl = closed.filter(inWeek).reduce((s, t) => s + (Number(t.pnl) || 0), 0)
  const wins = closed.filter((t) => t.result === 'win').length
  // trailing losing streak from most recent closed
  const byTime = [...closed].sort((a, b) => new Date(b.exit_time).getTime() - new Date(a.exit_time).getTime())
  let streak = 0
  for (const t of byTime) { if (t.result === 'loss') streak++; else break }
  return {
    weekly_pnl: weeklyPnl,
    weekly_goal: goal,
    weekly_progress_pct: goal > 0 ? (weeklyPnl / goal) * 100 : 0,
    daily_pnl: closed.filter(inDay).reduce((s, t) => s + (Number(t.pnl) || 0), 0),
    total_trades: closed.length,
    win_rate: closed.length ? wins / closed.length : 0,
    consecutive_losses: streak,
  }
}

const fetchData = async () => {
  now.value = Date.now()
  try {
    const [{ data: acctRow }, { data: sigRows }, { data: tradeRows }] = await Promise.all([
      supabase.from('account_state').select('*').order('updated_at', { ascending: false }).limit(1),
      supabase.from('signals').select('*').order('signal_time', { ascending: false }).limit(10),
      supabase.from('trades').select('*').order('created_at', { ascending: false }).limit(500),
    ])
    account.value = (acctRow && acctRow[0]) || {}
    signals.value = sigRows || []
    // scope stats/history to the ACTIVE account — a newly-connected account the
    // bot hasn't traded starts at a clean slate (no carryover from prior accounts)
    const login = account.value?.login
    const all = (tradeRows || []).filter((t) => !login || Number(t.mt5_login) === Number(login))
    trades.value = all.slice(0, 10)
    const closed = all.filter((t) => t.result === 'win' || t.result === 'loss')
    const wins = closed.filter((t) => t.result === 'win').length
    perf.value = {
      total_trades: all.length,
      closed: closed.length,
      wins,
      win_rate: closed.length ? wins / closed.length : 0,
      net_pnl: all.reduce((s, t) => s + (Number(t.pnl) || 0), 0),
    }
    // Compute weekly goal progress for dashboard. Prefer the bot's broker-truth
    // weekly_pnl (deal history since Monday, incl. swap/commission) from the
    // heartbeat; fall back to trades-table recomputation when the bot hasn't
    // written it yet. The recomputed number drifts from the balance — that was
    // the "514.87 balance vs 12.57/14 card" gap.
    const goal = Number(weekly.value.weekly_goal) || 14
    const fromHeartbeat = Number(account.value?.weekly_pnl)
    const computed = computeWeekly(all, goal)
    if (account.value?.weekly_pnl !== null && account.value?.weekly_pnl !== undefined && Number.isFinite(fromHeartbeat)) {
      // progress follows the DISPLAYED number so the bar fills with it
      weekly.value = { ...computed, weekly_pnl: fromHeartbeat,
        weekly_progress_pct: goal > 0 ? (fromHeartbeat / goal) * 100 : 0 }
    } else {
      weekly.value = computed
    }
  } catch {}
}
const fmtAge = (ms: number) => ms < 60_000 ? `${Math.round(ms / 1000)}s ago` : `${Math.round(ms / 60_000)}m ago`
onMounted(() => { fetchData(); timer = setInterval(fetchData, 5000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="space-y-4 md:space-y-6">
    <h2 class="text-xl font-semibold">Dashboard</h2>

    <!-- Bot liveness banner (stale heartbeat = dead process) -->
    <div v-if="account.login && !botOnline"
         class="bg-(--card) border border-(--loss) rounded-lg p-3 flex items-center gap-3">
      <span class="text-(--loss) text-lg">●</span>
      <div>
        <div class="font-medium text-sm text-(--loss)">BOT OFFLINE</div>
        <div class="text-xs text-(--muted)">
          Last heartbeat {{ heartbeatAge !== null ? fmtAge(heartbeatAge) : '—' }}. The numbers below are stale;
          a dashboard "restart" can't relaunch a dead process — restart the scheduled task on the VPS.
        </div>
      </div>
    </div>

    <!-- Live account state (bot heartbeat) -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-4 md:p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-medium text-(--muted) uppercase">Account</h3>
        <span v-if="account.login" class="text-xs text-(--muted)">
          {{ account.broker || 'broker' }} · #{{ account.login }}
        </span>
      </div>

      <template v-if="account.login">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Balance</div>
            <div class="text-lg md:text-xl font-bold mt-1">${{ (account.balance ?? 0).toFixed(2) }}</div>
          </div>
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Equity</div>
            <div class="text-lg md:text-xl font-bold mt-1">${{ (account.equity ?? 0).toFixed(2) }}</div>
          </div>
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Floating P&L</div>
            <div class="text-lg md:text-xl font-bold mt-1"
                 :class="(account.floating_pnl ?? 0) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
              {{ (account.floating_pnl ?? 0) >= 0 ? '+' : '' }}{{ (account.floating_pnl ?? 0).toFixed(2) }}
            </div>
          </div>
          <div>
            <div class="text-(--muted) text-xs uppercase tracking-wide">Open</div>
            <div class="text-lg md:text-xl font-bold mt-1">{{ (account.open_positions ?? []).length }}</div>
          </div>
        </div>

        <!-- Open positions -->
        <div v-if="(account.open_positions ?? []).length" class="overflow-x-auto rounded border border-(--border)">
          <table class="w-full text-sm min-w-[28rem]">
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

    <!-- Weekly Goal Progress -->
    <div class="bg-(--card) border border-(--border) rounded-lg p-4 md:p-5">
      <h3 class="text-sm font-medium text-(--muted) uppercase mb-3">Weekly Goal</h3>
      <div class="flex items-baseline gap-3 mb-2">
        <span class="text-3xl font-bold" :class="(weekly.weekly_pnl ?? 0) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
          ${{ (weekly.weekly_pnl ?? 0).toFixed(2) }}
        </span>
        <span class="text-(--muted)">/ ${{ (weekly.weekly_goal ?? 14).toFixed(2) }}</span>
      </div>
      <div class="w-full h-3 rounded-full bg-(--bg) overflow-hidden mb-3">
        <div class="h-full rounded-full transition-all duration-500"
          :style="{ width: Math.min(100, weekly.weekly_progress_pct ?? 0) + '%', background: (weekly.weekly_progress_pct ?? 0) >= 100 ? 'var(--profit)' : (weekly.weekly_progress_pct ?? 0) >= 50 ? 'var(--warning)' : 'var(--primary)' }" />
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div><span class="text-(--muted)">Today</span><br>${{ (weekly.daily_pnl ?? 0).toFixed(2) }}</div>
        <div><span class="text-(--muted)">Trades</span><br>{{ weekly.total_trades ?? 0 }}</div>
        <div><span class="text-(--muted)">Win Rate</span><br>{{ ((weekly.win_rate ?? 0) * 100).toFixed(1) }}%</div>
        <div><span class="text-(--muted)">Streak</span><br>{{ weekly.consecutive_losses ?? 0 }}</div>
      </div>
    </div>

    <!-- Stat cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
      <div class="bg-(--card) border border-(--border) rounded-lg p-3 md:p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">Net P&L</div>
        <div class="text-xl md:text-2xl font-bold mt-1"
             :class="perf.net_pnl >= 0 ? 'text-(--profit)' : 'text-(--loss)'">
          {{ perf.net_pnl >= 0 ? '+' : '' }}{{ perf.net_pnl.toFixed(2) }}
        </div>
      </div>
      <div class="bg-(--card) border border-(--border) rounded-lg p-3 md:p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">Win Rate</div>
        <div class="text-xl md:text-2xl font-bold mt-1">{{ (perf.win_rate * 100).toFixed(1) }}%</div>
      </div>
      <div class="bg-(--card) border border-(--border) rounded-lg p-3 md:p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">Trades</div>
        <div class="text-xl md:text-2xl font-bold mt-1">{{ perf.total_trades }}</div>
      </div>
      <div class="bg-(--card) border border-(--border) rounded-lg p-3 md:p-4">
        <div class="text-(--muted) text-xs uppercase tracking-wide">W / L</div>
        <div class="text-xl md:text-2xl font-bold mt-1">{{ perf.wins }} / {{ perf.closed - perf.wins }}</div>
      </div>
    </div>

    <!-- Recent signals -->
    <div>
      <h3 class="text-sm font-medium text-(--muted) uppercase mb-2">Recent Signals</h3>
      <div class="bg-(--card) border border-(--border) rounded-lg overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm min-w-[28rem]">
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
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
