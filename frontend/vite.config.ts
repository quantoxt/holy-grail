import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    proxy: {
      // (no /api proxy — the FastAPI layer was removed; frontend talks to Supabase directly)
    },
  },
  build: { outDir: 'dist' },
})
