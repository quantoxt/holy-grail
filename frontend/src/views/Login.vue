<script setup lang="ts">
import { ref } from 'vue'
import { PhSignIn, PhCircleNotch } from '@phosphor-icons/vue'
import { supabase } from '../lib/supabase'

const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

const signIn = async () => {
  busy.value = true
  error.value = ''
  const { error: e } = await supabase.auth.signInWithPassword({ email: email.value.trim(), password: password.value })
  busy.value = false
  if (e) error.value = e.message === 'Invalid login credentials'
    ? 'That email and password don’t match. Check both and try again.'
    : e.message
}
</script>

<template>
  <div class="min-h-dvh grid place-items-center px-4">
    <div class="w-full max-w-sm">
      <svg viewBox="0 0 320 120" class="w-full mb-6" aria-hidden="true">
        <path d="M0 120 L70 52 L112 84 L170 18 L222 70 L262 44 L320 120 Z" fill="var(--sunk)" />
        <path d="M40 120 L118 64 L150 86 L204 40 L250 78 L284 62 L320 120 Z" fill="var(--primary)" opacity=".85" />
        <circle cx="204" cy="24" r="7" fill="var(--honey)" />
      </svg>
      <h1 class="font-display text-3xl font-semibold tracking-tight">Welcome back</h1>
      <p class="text-(--muted) mt-1 mb-6">Sign in to check on the bot.</p>

      <form @submit.prevent="signIn" class="space-y-3">
        <label class="block">
          <span class="text-sm text-(--muted)">Email</span>
          <input v-model="email" type="email" autocomplete="email" required class="field" />
        </label>
        <label class="block">
          <span class="text-sm text-(--muted)">Password</span>
          <input v-model="password" type="password" autocomplete="current-password" required class="field" />
        </label>
        <p v-if="error" role="alert" class="text-sm text-(--loss)">{{ error }}</p>
        <button type="submit" :disabled="busy"
                class="w-full mt-2 flex items-center justify-center gap-2 rounded-2xl bg-(--primary) text-(--primary-ink) py-3 font-semibold disabled:opacity-60">
          <PhCircleNotch v-if="busy" :size="20" class="animate-spin" />
          <PhSignIn v-else :size="20" weight="bold" />
          Sign in
        </button>
      </form>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";
.field {
  @apply mt-1 w-full rounded-xl px-3.5 py-2.5 text-base outline-none transition-colors;
  background: var(--card);
  border: 1px solid var(--border);
  color: var(--text);
}
.field:focus { border-color: var(--primary); }
</style>
