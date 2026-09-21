import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    allowedHosts: true,
    proxy: {
      // 联调真实后端时：VITE_USE_MOCK=false，请求经此代理到 Flask，浏览器无跨域
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
	rewrite:(p)=>p.replace(/^\/api/,''),
      },
    },
  },
})
