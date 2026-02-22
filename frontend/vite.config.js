import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/jobs': { target: 'http://localhost:8000', changeOrigin: true },
      '/transcribe': { target: 'http://localhost:8000', changeOrigin: true },
      '/status': { target: 'http://localhost:8000', changeOrigin: true },
      '/download': { target: 'http://localhost:8000', changeOrigin: true },
      '/openapi.json': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
