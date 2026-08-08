<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const events = ref<any[]>([])
let timer: number
const fetchRisk = async () => {
  try { events.value = await (await fetch('/api/risk?limit=30')).json() } catch {}
}
onMounted(() => { fetchRisk(); timer = setInterval(fetchRisk, 5000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="space-y-4">
    <h2 class="text-xl font-semibold">Risk Events</h2>
    <div class="space-y-2">
      <div v-for="e in events" :key="e.id"
           class="bg-(--card) border border-(--border) rounded-lg p-3 flex items-center gap-4">
        <div class="text-(--loss) text-lg">⚠</div>
        <div class="flex-1">
          <div class="font-medium text-sm">{{ e.event_type }}</div>
          <div class="text-(--muted) text-xs">{{ e.reason }}</div>
        </div>
        <div class="text-(--muted) text-xs">{{ new Date(e.created_at).toLocaleString() }}</div>
      </div>
      <div v-if="!events.length" class="text-center text-(--muted) py-8">
        No risk events — bot running normally.
      </div>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
</style>
