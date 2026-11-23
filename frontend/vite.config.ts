import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The window opened by `python -m bosh_mow --dev` points to this exact address.
    port: 5173,
    strictPort: true,
    // In --dev mode, the API listens on this fixed port (see bosh_mow/app.py).
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
})
