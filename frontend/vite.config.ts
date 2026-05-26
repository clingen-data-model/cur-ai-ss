import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/* Vite configuration for the React frontend
 * - Dev server runs on port 5173 with HMR (hot module reload)
 * - API proxy redirects /api/* requests to FastAPI backend (port 8000)
 *   Example: fetch('/api/papers') → http://localhost:8000/papers
 * - Build minifies with esbuild and targets ES2020
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    target: 'ES2020',
    minify: 'esbuild',
    sourcemap: false,
  },
})
