import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // caminhos relativos: o app de bandeja carrega o mesmo build por file://
  base: './',
  server: {
    port: 8042,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8040', ws: true },
      '/audio': 'http://127.0.0.1:8040',
      '/api': 'http://127.0.0.1:8040',
    },
  },
})
