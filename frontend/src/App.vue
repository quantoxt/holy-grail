<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, defineAsyncComponent } from 'vue'
import type { Session } from '@supabase/supabase-js'
import {
  PhMountains, PhChartLineUp, PhListBullets, PhNotebook, PhSlidersHorizontal,
  PhSignOut, PhSun, PhMoon,
} from '@phosphor-icons/vue'
import { supabase } from './lib/supabase'
import Login from './views/Login.vue'
import Cockpit from './views/Cockpit.vue'
const Analytics = defineAsyncComponent(() => import('./views/Analytics.vue'))
const Trades = defineAsyncComponent(() => import('./views/Trades.vue'))
const Journal = defineAsyncComponent(() => import('./views/Journal.vue'))
const Settings = defineAsyncComponent(() => import('./views/Settings.vue'))

const session = ref<Session | null>(null)
const ready = ref(false)
let unsub: (() => void) | undefined

onMounted(async () => {
  const { data } = await supabase.auth.getSession()
  session.value = data.session
  ready.value = true
  const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => { session.value = s })
  unsub = () => sub.subscription.unsubscribe()
})
onUnmounted(() => unsub?.())

const views = [
  { id: 'cockpit', label: 'Cockpit', icon: PhMountains },
  { id: 'analytics', label: 'Analytics', icon: PhChartLineUp },
  { id: 'trades', label: 'Trades', icon: PhListBullets },
  { id: 'journal', label: 'Journal', icon: PhNotebook },
  { id: 'settings', label: 'Settings', icon: PhSlidersHorizontal },
] as const
type ViewId = typeof views[number]['id']

const readView = (): ViewId => {
  const h = location.hash.slice(1)
  return (views.some((v) => v.id === h) ? h : 'cockpit') as ViewId
}
const view = ref<ViewId>(readView())
watch(view, (v) => { if (location.hash.slice(1) !== v) location.hash = v })
window.addEventListener('hashchange', () => { view.value = readView() })

const current = computed(() => ({
  cockpit: Cockpit, analytics: Analytics, trades: Trades, journal: Journal, settings: Settings,
}[view.value]))

// theme: follow the system unless the user picked one (per-device convenience only)
const theme = ref<string>((() => { try { return localStorage.getItem('hg-theme') || '' } catch { return '' } })())
const applyTheme = () => {
  if (theme.value) document.documentElement.dataset.theme = theme.value
  else delete document.documentElement.dataset.theme
}
applyTheme()
const systemDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches
const isDark = computed(() => theme.value ? theme.value === 'dark' : systemDark())
const toggleTheme = () => {
  theme.value = isDark.value ? 'light' : 'dark'
  try { localStorage.setItem('hg-theme', theme.value) } catch { /* private mode */ }
  applyTheme()
}

const signOut = () => supabase.auth.signOut()
</script>

<template>
  <div v-if="!ready" class="min-h-dvh" />
  <Login v-else-if="!session" />
  <div v-else class="min-h-dvh md:flex">
    <!-- rail (desktop) -->
    <aside class="hidden md:flex md:w-60 md:shrink-0 flex-col gap-1 px-4 py-6 sticky top-0 h-dvh">
      <div class="flex items-center gap-2.5 px-2 mb-8">
        <svg viewBox="0 0 32 32" class="size-8" aria-hidden="true">
          <path d="M3 27 L13 9 L18 17 L22 12 L29 27 Z" fill="var(--primary)" />
          <circle cx="22" cy="7" r="3" fill="var(--honey)" />
        </svg>
        <span class="font-display text-xl font-semibold tracking-tight">Holy Grail</span>
      </div>
      <button v-for="v in views" :key="v.id" @click="view = v.id"
              class="nav-item" :class="{ active: view === v.id }">
        <component :is="v.icon" :size="22" :weight="view === v.id ? 'duotone' : 'regular'" />
        {{ v.label }}
      </button>
      <div class="mt-auto flex gap-1 px-1">
        <button class="icon-btn" @click="toggleTheme" :aria-label="isDark ? 'Use light theme' : 'Use dark theme'">
          <PhSun v-if="isDark" :size="20" /><PhMoon v-else :size="20" />
        </button>
        <button class="icon-btn" @click="signOut" aria-label="Sign out"><PhSignOut :size="20" /></button>
      </div>
    </aside>

    <main class="flex-1 min-w-0 px-4 pt-5 pb-28 md:px-10 md:py-8">
      <div class="mx-auto max-w-6xl">
        <component :is="current" />
      </div>
    </main>

    <!-- bottom bar (mobile) -->
    <nav class="md:hidden fixed inset-x-3 bottom-3 z-20 flex justify-around rounded-[22px] bg-(--card) border border-(--border) px-2 py-1.5">
      <button v-for="v in views" :key="v.id" @click="view = v.id"
              class="flex flex-col items-center gap-0.5 px-2 py-1 rounded-xl text-[11px]"
              :class="view === v.id ? 'text-(--primary)' : 'text-(--muted)'">
        <component :is="v.icon" :size="22" :weight="view === v.id ? 'duotone' : 'regular'" />
        {{ v.label }}
      </button>
    </nav>
  </div>
</template>

<style>
@reference "tailwindcss";
.nav-item {
  @apply flex items-center gap-3 rounded-2xl px-3 py-2.5 text-[15px] text-left transition-colors;
  color: var(--muted);
}
.nav-item:hover { color: var(--text); background: var(--card); }
.nav-item.active { color: var(--primary); background: var(--card); font-weight: 600; }
.icon-btn {
  @apply grid place-items-center size-10 rounded-xl transition-colors;
  color: var(--muted);
}
.icon-btn:hover { color: var(--text); background: var(--card); }
</style>
