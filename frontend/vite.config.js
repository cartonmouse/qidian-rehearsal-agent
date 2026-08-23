import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'
import process from 'node:process'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(() => {
  // Keep the dev proxy on the same IPv4 loopback address as Uvicorn.
  // On some Windows setups `localhost` resolves to a different local service.
  // qidian uses a dedicated host port because 8000 may be occupied by a
  // different WSL service (for example, a local Hermes/TechSpar process).
  const apiTarget = process.env.QIDIAN_API_TARGET || process.env.TECHSPAR_API_TARGET || 'http://127.0.0.1:18000'

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      proxy: {
        '/api': apiTarget,
        '/ws': {
          target: apiTarget,
          ws: true,
        },
      },
    },
  }
})
