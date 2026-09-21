/* Application entry point
 * Initializes React with Router and Query Client
 *
 * Router: TanStack Router (file-based, type-safe)
 * Alternatives: React Router v6 (config-based), Next.js (full-stack), Remix (full-stack)
 *
 * Query: TanStack Query (server state management)
 * Alternatives: SWR, RTK Query, Apollo Client, or manual fetch + useState
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { routeTree } from './routeTree'
import '@/lib/api'

// Server state management (caching, synchronization, background fetching)
const queryClient = new QueryClient()

// File-based routing with type-safe params.
//
// basepath comes from Vite's `base` (VITE_BASE_PATH), so the same bundle works at '/'
// locally and under '/v2/' on the VM, where the Streamlit UI still owns '/'. Without it
// the router would match against the full pathname and treat '/v2/papers/1' as unknown.
// The trailing slash Vite always includes is stripped: the router expects '/v2', not '/v2/'.
const basepath = import.meta.env.BASE_URL.replace(/\/$/, '') || '/'
const router = createRouter({ routeTree, basepath })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
)
