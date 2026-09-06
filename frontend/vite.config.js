// Vite 配置：开发端口 5173，把 /api 请求代理到后端 Flask（5000），
// 避免前端跨域；生产构建由后端同源反代或静态托管负责（见 README）。
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
})
