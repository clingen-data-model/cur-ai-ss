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
import { PaperGraphPage } from './routes/papers/$paperId/graph'

const rootRoute = new RootRoute({
  component: RootLayout,
})

const indexRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
})

const papersRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/papers',
})

const paperIdRoute = new Route({
  getParentRoute: () => papersRoute,
  path: '$paperId',
})

const paperGraphRoute = new Route({
  getParentRoute: () => paperIdRoute,
  path: '/graph',
  component: PaperGraphPage,
})

export const routeTree = rootRoute.addChildren([
  indexRoute,
  papersRoute.addChildren([paperIdRoute.addChildren([paperGraphRoute])]),
])
