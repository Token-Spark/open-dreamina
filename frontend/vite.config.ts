import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// Vite dev server runs on 10131, proxies /api -> backend on 10130
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 10131,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:10130',
        changeOrigin: true,
      },
    },
  },
})
