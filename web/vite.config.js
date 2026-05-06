import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { readFileSync } from 'fs'

// 读取 .env.production 中的 VITE_API_URL
function getApiUrl() {
  try {
    const envPath = resolve(__dirname, '.env.production')
    const content = readFileSync(envPath, 'utf-8')
    const match = content.match(/VITE_API_URL=(.+)/)
    return match ? match[1].trim() : 'http://localhost:18000'
  } catch {
    return 'http://localhost:18000'
  }
}

export default defineConfig({
  plugins: [vue()],
  define: {
    'import.meta.env.VITE_API_URL': JSON.stringify(getApiUrl()),
  },
})
