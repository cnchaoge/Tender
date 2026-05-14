import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { readFileSync } from 'fs'

function getApiUrl() {
  try {
    const envPath = resolve(__dirname, '.env.production')
    const content = readFileSync(envPath, 'utf-8')
    const match = content.match(/VITE_API_URL=(.+)/)
    return match ? match[1].trim() : 'http://localhost:8000'
  } catch {
    return 'http://localhost:8000'
  }
}

export default defineConfig({
  plugins: [vue()],
  define: {
    'import.meta.env.VITE_API_URL': JSON.stringify(getApiUrl()),
  },
  server: {
    port: 5173,
    proxy: {
      // 开发时代理 /api 请求到后端 8000，避免 CORS 问题
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
