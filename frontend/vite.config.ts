import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 本地开发：将 API 请求代理到后端
      '/register': 'http://127.0.0.1:8000',
      '/login': 'http://127.0.0.1:8000',
      '/refresh': 'http://127.0.0.1:8000',
      '/users': 'http://127.0.0.1:8000',
      '/knowledge-bases': 'http://127.0.0.1:8000',
      '/conversations': 'http://127.0.0.1:8000',
      '/chat': 'http://127.0.0.1:8000',
      '/coding-agent': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
