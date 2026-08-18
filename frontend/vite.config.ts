import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// Vite dev server runs on 10131, proxies /api -> backend on 10130
// Docker 开发模式下，通过环境变量覆盖 host / proxy target / 文件监听方式
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: process.env.VITE_DEV_HOST || '127.0.0.1',
    port: 10131,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:10130',
        changeOrigin: true,
      },
    },
    // Docker Desktop (macOS/Windows) 卷挂载不支持原生 inotify，需启用轮询
    watch: {
      usePolling: process.env.VITE_USE_POLLING === 'true',
    },
  },
})
