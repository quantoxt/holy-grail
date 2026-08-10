<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Dashboard from './views/Dashboard.vue'
import Trades from './views/Trades.vue'
import Risk from './views/Risk.vue'
import Config from './views/Config.vue'
import { supabase } from './lib/supabase'

const status = ref<any>({})
const view = ref('dashboard')
const now = ref(Date.now())
let timer: number

const navItems = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'trades', label: 'Trades' },
  { id: 'risk', label: 'Risk' },
  { id: 'config', label: 'Config' },
]

const fetchStatus = async () => {
  try {
    const { data } = await supabase.from('bot_config').select('config').eq('id', 1).limit(1).single()
    const cfg = (data?.config || {}) as Record<string, any>
    status.value = {
      symbols: cfg.active_symbols || [],
      running: cfg.bot_running,
      paused: cfg.trading_paused,
    }
  } catch {}
}
onMounted(() => { fetchStatus(); timer = setInterval(() => { fetchStatus(); now.value = Date.now() }, 5000) })
onUnmounted(() => clearInterval(timer))

const symsLabel = computed(() => (status.value.symbols ?? []).join(', ') || '…')
</script>

<template>
  <div class="min-h-screen flex flex-col md:flex-row bg-(--bg) text-(--text)">
    <!-- Sidebar (desktop) / top bar (mobile) -->
    <aside class="md:w-56 md:shrink-0 border-b md:border-b-0 md:border-r border-(--border) p-3 md:p-4 flex items-center md:flex-col gap-1 md:gap-1 overflow-x-auto md:overflow-visible">
      <h1 class="text-lg font-bold md:mb-6 text-(--primary) whitespace-nowrap mr-4 md:mr-0">Holy Grail</h1>
      <button v-for="item in navItems" :key="item.id"
              @click="view = item.id"
              class="px-3 py-1.5 rounded text-sm font-medium whitespace-nowrap transition-colors"
              :class="view === item.id ? 'bg-(--card)' : 'text-(--muted) hover:bg-(--card)'">
        {{ item.label }}
      </button>
      <div class="ml-auto md:ml-0 md:mt-auto text-xs text-(--muted) text-right md:text-left whitespace-nowrap md:whitespace-normal">
        <div class="hidden md:block truncate max-w-[12rem]">{{ symsLabel }}</div>
        <div v-if="status.paused" class="text-(--warning) font-medium">● PAUSED</div>
        <div v-else-if="status.running" class="text-(--profit) font-medium">● LIVE</div>
        <div v-else class="text-(--loss) font-medium">● STOPPED</div>
      </div>
    </aside>

    <main class="flex-1 p-3 md:p-6 overflow-auto">
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
