<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import Dashboard from './views/Dashboard.vue'
import Trades from './views/Trades.vue'
import Risk from './views/Risk.vue'
import Config from './views/Config.vue'

const status = ref<any>({})
const view = ref('dashboard')
let timer: number

const navItems = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'trades', label: 'Trades' },
  { id: 'risk', label: 'Risk' },
  { id: 'config', label: 'Config' },
]

const fetchStatus = async () => {
  try { status.value = await (await fetch('/api/status')).json() } catch {}
}
onMounted(() => { fetchStatus(); timer = setInterval(fetchStatus, 5000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="min-h-screen flex bg-(--bg) text-(--text)">
    <aside class="w-56 shrink-0 border-r border-(--border) p-4 flex flex-col gap-1">
      <h1 class="text-lg font-bold mb-6 text-(--primary)">Holy Grail</h1>
      <button v-for="item in navItems" :key="item.id"
              @click="view = item.id"
              class="px-3 py-1.5 rounded text-sm font-medium text-left transition-colors"
              :class="view === item.id ? 'bg-(--card)' : 'text-(--muted) hover:bg-(--card)'">
        {{ item.label }}
      </button>
      <div class="mt-auto text-xs text-(--muted)">
        <div>{{ status.market_mode ?? '...' }} · {{ (status.symbols ?? []).join(', ') }}</div>
        <div :class="status.mode === 'live' ? 'text-(--loss)' : 'text-(--muted)'">{{ status.mode ?? 'paper' }}</div>
      </div>
    </aside>
    <main class="flex-1 p-6 overflow-auto">
      <Dashboard v-if="view === 'dashboard'" />
      <Trades v-else-if="view === 'trades'" />
      <Risk v-else-if="view === 'risk'" />
      <Config v-else-if="view === 'config'" />
    </main>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
