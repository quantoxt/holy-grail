<script setup lang="ts">
import { computed, onUnmounted } from 'vue'
import {
  PhLeaf, PhMoonStars, PhPlugs, PhFlagCheckered, PhWarningOctagon, PhArrowUpRight, PhArrowDownRight,
  PhLightning, PhShieldWarning, PhCoffee, PhNewspaper,
} from '@phosphor-icons/vue'
import ChallengeTrack from '../components/ChallengeTrack.vue'
import { useLive, money, ago } from '../composables/useLive'

const { config, account, signals, riskEvents, online, heartbeatAge, challenge, today, closed, loaded, now, stop } = useLive()
onUnmounted(stop)

const equity = computed(() => (account.value?.equity != null ? Number(account.value.equity) : null))
const positions = computed<any[]>(() => account.value?.open_positions ?? [])

const state = computed(() => {
  if (!account.value?.login) return { icon: PhPlugs, tone: 'var(--muted)', title: 'Waiting for the bot', body: 'No heartbeat yet. Start the bot on the server and it will show up here.' }
  if (!online.value) return { icon: PhPlugs, tone: 'var(--loss)', title: 'Bot is offline', body: `Last heard from ${ago(heartbeatAge.value)}. Numbers below may be stale.` }
  if (challenge.value.status === 'passed') return { icon: PhFlagCheckered, tone: 'var(--profit)', title: 'Target reached', body: 'Everything is closed and trading has stopped. Start the next step in Settings.' }
  if (challenge.value.status === 'failed') return { icon: PhWarningOctagon, tone: 'var(--loss)', title: 'Stopped at the safety floor', body: 'Positions were closed before the account’s fail line. Trading stays off until you reset it in Settings.' }
  if (!config.value.bot_running) return { icon: PhMoonStars, tone: 'var(--muted)', title: 'Bot is stopped', body: 'Connected and watching, but it will not trade until you start it.' }
  if (config.value.trading_paused) return { icon: PhCoffee, tone: 'var(--warning)', title: 'Taking a break', body: 'No new trades — open positions are still managed. Signals keep firing while Signal Mode is on.' }
  if (account.value?.news_blackout) return { icon: PhNewspaper, tone: 'var(--warning)', title: 'Sitting out the news', body: account.value.news_reason || 'High-impact news is close, so no new trades.' }
  return { icon: PhLeaf, tone: 'var(--profit)', title: 'On the trail', body: 'Scanning for setups every 5 minutes and managing open trades.' }
})

const toPass = computed(() => (equity.value == null ? null : challenge.value.pass - equity.value))
const aboveFloor = computed(() => (equity.value == null ? null : equity.value - challenge.value.floor))

const dailyCap = computed(() => Number(config.value.max_daily_loss ?? 0))
const dailyUsed = computed(() => (dailyCap.value > 0 ? Math.min(1, Math.max(0, -today.value.pnl / dailyCap.value)) : 0))

const winRate = computed(() => {
  const c = closed.value
  return c.length ? c.filter((t) => t.result === 'win').length / c.length : null
})

const activity = computed(() => {
  const items = [
    ...riskEvents.value.map((e) => ({ id: `r${e.id}`, at: e.created_at, kind: 'risk', title: e.event_type.replace(/_/g, ' '), body: e.reason })),
    ...signals.value.map((s) => ({
      id: `s${s.id}`, at: s.signal_time, kind: s.direction,
      title: `${s.symbol} ${s.direction === 'HOLD' ? 'no trade' : s.direction.toLowerCase() + ' signal'}`,
      body: `${(Number(s.predicted_move) * 100).toFixed(2)}% predicted move, ${Math.round(Number(s.confidence) * 100)}% confidence`,
    })),
  ]
  return items.sort((a, b) => +new Date(b.at) - +new Date(a.at)).slice(0, 12)
})
const time = (iso: string) => {
  const ms = now.value - new Date(iso).getTime()
  return ms < 86_400_000 ? ago(ms) : new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div v-if="loaded" class="space-y-8">
    <!-- status -->
    <header class="flex items-start gap-4">
      <div class="grid place-items-center size-14 rounded-[20px] shrink-0" :style="{ background: `color-mix(in oklab, ${state.tone} 16%, transparent)`, color: state.tone }">
        <component :is="state.icon" :size="30" weight="duotone" />
      </div>
      <div class="min-w-0">
        <h1 class="font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-semibold tracking-tight leading-tight">{{ state.title }}</h1>
        <p class="text-(--muted) mt-1 max-w-prose">{{ state.body }}</p>
      </div>
      <div v-if="account.login" class="ml-auto hidden sm:block text-right text-sm text-(--muted) shrink-0">
        <div>{{ account.broker || 'Broker' }}</div>
        <div class="num">Account {{ account.login }}</div>
      </div>
    </header>

    <!-- the trail -->
    <section class="rounded-[28px] bg-(--card) px-5 pt-6 pb-5 md:px-8 md:pt-8">
      <div class="flex flex-wrap items-end gap-x-8 gap-y-3 mb-4">
        <div>
          <div class="text-sm text-(--muted)">Equity</div>
          <div class="font-display num text-[clamp(2.4rem,6vw,3.75rem)] font-semibold leading-none tracking-tight">{{ money(equity) }}</div>
        </div>
        <p v-if="toPass !== null" class="text-[15px] leading-relaxed text-(--muted) pb-1 max-w-md">
          <template v-if="toPass > 0"><span class="text-(--text) font-semibold num">{{ money(toPass) }}</span> to the pass line, </template>
          <template v-else>Past the pass line, </template>
          <span class="text-(--text) font-semibold num">{{ money(aboveFloor) }}</span> above where the bot stops itself.
        </p>
        <div v-if="account.floating_pnl" class="ml-auto text-right">
          <div class="text-sm text-(--muted)">Open trades</div>
          <div class="num text-xl font-semibold" :class="Number(account.floating_pnl) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">{{ money(account.floating_pnl, true) }}</div>
        </div>
      </div>
      <ChallengeTrack :equity="equity" :fail="challenge.fail" :floor="challenge.floor" :start="challenge.start" :pass="challenge.pass"
                      :floor-label="challenge.mode === 'weekly' ? 'Weekly floor' : 'Bot stops'" />
    </section>

    <div class="grid gap-8 lg:grid-cols-[1fr_1.15fr]">
      <!-- today -->
      <section>
        <h2 class="font-display text-xl font-semibold mb-4">Today</h2>
        <div class="flex items-baseline gap-3">
          <span class="font-display num text-4xl font-semibold" :class="today.pnl > 0 ? 'text-(--profit)' : today.pnl < 0 ? 'text-(--loss)' : ''">{{ money(today.pnl, true) }}</span>
          <span class="text-(--muted)">{{ today.trades }} closed, {{ today.wins }} won</span>
        </div>
        <div v-if="dailyCap > 0" class="mt-5">
          <div class="flex justify-between text-sm text-(--muted) mb-1.5">
            <span>Daily loss budget</span>
            <span class="num">{{ money(Math.max(0, dailyCap + Math.min(0, today.pnl))) }} left of {{ money(dailyCap) }}</span>
          </div>
          <div class="h-3 rounded-full bg-(--sunk) overflow-hidden">
            <div class="h-full rounded-full transition-[width] duration-700" :style="{ width: `${(1 - dailyUsed) * 100}%`, background: dailyUsed > 0.66 ? 'var(--loss)' : dailyUsed > 0.33 ? 'var(--warning)' : 'var(--profit)' }" />
          </div>
        </div>
        <dl class="mt-6 grid grid-cols-3 gap-4 text-sm">
          <div><dt class="text-(--muted)">All trades</dt><dd class="num text-lg font-semibold mt-0.5">{{ closed.length }}</dd></div>
          <div><dt class="text-(--muted)">Win rate</dt><dd class="num text-lg font-semibold mt-0.5">{{ winRate == null ? '—' : Math.round(winRate * 100) + '%' }}</dd></div>
          <div><dt class="text-(--muted)">Risk per trade</dt><dd class="num text-lg font-semibold mt-0.5">{{ config.account_mode === 'prop' ? money(Number(config.prop_start_balance) * Number(config.risk_pct_per_trade)) : money(config.max_risk_per_trade) }}</dd></div>
        </dl>
      </section>

      <!-- open positions -->
      <section>
        <h2 class="font-display text-xl font-semibold mb-4">Open now</h2>
        <ul v-if="positions.length" class="space-y-2.5">
          <li v-for="p in positions" :key="p.ticket" class="flex items-center gap-3 rounded-2xl bg-(--card) px-4 py-3">
            <div class="grid place-items-center size-10 rounded-xl" :class="p.type === 'BUY' ? 'text-(--profit)' : 'text-(--loss)'"
                 :style="{ background: `color-mix(in oklab, ${p.type === 'BUY' ? 'var(--profit)' : 'var(--loss)'} 14%, transparent)` }">
              <PhArrowUpRight v-if="p.type === 'BUY'" :size="22" weight="bold" />
              <PhArrowDownRight v-else :size="22" weight="bold" />
            </div>
            <div class="min-w-0">
              <div class="font-semibold">{{ p.symbol }} <span class="font-normal text-(--muted)">{{ p.type === 'BUY' ? 'long' : 'short' }} {{ p.volume }} lots</span></div>
              <div class="num text-sm text-(--muted)">in at {{ p.entry }}, now {{ p.price_current }}<template v-if="p.sl">, stop {{ p.sl }}</template></div>
            </div>
            <div class="ml-auto num font-semibold" :class="Number(p.profit) >= 0 ? 'text-(--profit)' : 'text-(--loss)'">{{ money(p.profit, true) }}</div>
          </li>
        </ul>
        <p v-else class="rounded-2xl border border-dashed border-(--border) px-4 py-6 text-(--muted)">No open trades. The bot opens one when a signal clears every risk check.</p>
      </section>
    </div>

    <!-- activity -->
    <section>
      <h2 class="font-display text-xl font-semibold mb-4">Recent activity</h2>
      <ol v-if="activity.length" class="relative space-y-1 before:absolute before:left-[19px] before:top-3 before:bottom-3 before:w-px before:bg-(--border)">
        <li v-for="a in activity" :key="a.id" class="relative flex gap-3 py-2">
          <div class="relative z-10 grid place-items-center size-10 rounded-full bg-(--bg) shrink-0"
               :class="a.kind === 'risk' ? 'text-(--warning)' : a.kind === 'BUY' ? 'text-(--profit)' : a.kind === 'SELL' ? 'text-(--loss)' : 'text-(--muted)'">
            <PhShieldWarning v-if="a.kind === 'risk'" :size="22" weight="duotone" />
            <PhLightning v-else :size="22" weight="duotone" />
          </div>
          <div class="min-w-0 pt-1">
            <div class="font-medium first-letter:uppercase">{{ a.title }}</div>
            <div class="text-sm text-(--muted) break-words">{{ a.body }}</div>
          </div>
          <time class="ml-auto pt-1 text-sm text-(--muted) shrink-0">{{ time(a.at) }}</time>
        </li>
      </ol>
      <p v-else class="text-(--muted)">Nothing yet. Signals and risk checks will appear here as the bot works.</p>
    </section>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
