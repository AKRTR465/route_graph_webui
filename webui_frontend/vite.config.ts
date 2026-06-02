import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const host = process.env.ROUTE_GRAPH_WEBUI_VITE_HOST
  ?? (process.env.ROUTE_GRAPH_WEBUI_ALLOW_LAN === '1' ? '0.0.0.0' : '127.0.0.1')
const backendHost = process.env.ROUTE_GRAPH_WEBUI_HOST ?? '127.0.0.1'
const backendPort = process.env.ROUTE_GRAPH_WEBUI_PORT ?? '8000'
const backendTarget = `http://${backendHost}:${backendPort}`

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    host,
    port: 5173,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
})
