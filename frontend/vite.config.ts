import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/* Vite configuration for the React frontend
 * - Dev server runs on port 5173 with HMR (hot module reload)
 * - API proxy redirects /api/* requests to FastAPI backend
 *   Set VITE_API_TARGET env var to toggle between:
 *   - http://localhost:8000 (local dev, default)
 *   - https://gene-curation-ai.app (production)
 * - Build minifies with esbuild and targets ES2020
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  plugins: [react(), tailwindcss()],
  server: {
    port: 8501,
    open: true,
    // proxy: {
    //   '/api': {
    //     target: process.env.VITE_API_URL || 'http://localhost:8000',
    //     changeOrigin: true,
    //     secure: false,
    //   },
    // },
  },
  build: {
    target: 'ES2020',
    minify: 'esbuild',
    sourcemap: false,
  },
})
