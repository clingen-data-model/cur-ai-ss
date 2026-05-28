/* TanStack Router route tree
 * This file defines the structure of your routes
 * Generated from src/routes/ directory structure
 *
 * File-based routing convention:
 *   __root.tsx  → Root layout (always rendered)
 *   index.tsx   → Root path (/)
 *   papers/$paperId/graph.tsx  → /papers/:paperId/graph
 *   etc.
 */
import { RootRoute, Route } from '@tanstack/react-router'
import { RootLayout } from './routes/__root'
import { HomePage } from './routes/index'
import { PatientsPage } from './routes/papers.$paperId.patients'

const rootRoute = new RootRoute({
  component: RootLayout,
})

const indexRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
})

const papersPatientRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/papers/$paperId/patients',
  component: PatientsPage,
})

export const routeTree = rootRoute.addChildren([indexRoute, papersPatientRoute])

export { papersPatientRoute }
