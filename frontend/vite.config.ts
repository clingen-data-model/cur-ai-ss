import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/* Vite configuration for the React frontend
 * - Dev server runs on port 8501 with HMR (hot module reload)
 * - Build minifies with esbuild
 *
 * Deploy-time environment variables (both are set by the Ansible build step):
 * - VITE_BASE_PATH  Public path the app is served under. Defaults to '/' for local
 *                   dev; the VM build sets '/v2/' so the SPA can sit beside the
 *                   Streamlit UI that still owns '/'. Vite rewrites every emitted
 *                   asset URL against this and exposes it as import.meta.env.BASE_URL,
 *                   which the router and any root-relative asset must be built from.
 * - VITE_API_URL    Base URL the API is reached at. Unset locally, where lib/api.ts
 *                   falls back to http://localhost:8000; the VM build sets '/api' so
 *                   requests stay same-origin and are proxied by nginx.
 */
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? '/',
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  plugins: [react(), tailwindcss()],
  server: {
    port: 8501,
    open: true,
  },
  build: {
    minify: 'esbuild',
    sourcemap: false,
    cssMinify: false,
  },
})
