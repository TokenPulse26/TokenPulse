import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev server proxies API calls to the local TokenPulse Rust proxy so the
// browser stays same-origin (the proxy's CORS allowlist only covers :4200).
// Override the target with TOKENPULSE_PROXY_URL if running on another port.
const proxyTarget = process.env.TOKENPULSE_PROXY_URL ?? 'http://127.0.0.1:4100'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': proxyTarget,
      '/health': proxyTarget,
    },
  },
})
