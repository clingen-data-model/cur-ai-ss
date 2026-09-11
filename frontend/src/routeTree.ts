/* The app's route table, assembled by hand.
 *
 * TanStack Router ships a codegen plugin that writes this file from the
 * filenames under routes/. It is not installed -- vite.config.ts loads only
 * react() and tailwindcss() -- so adding a component under routes/ does nothing
 * on its own. A new route needs three edits here: import it, declare a Route,
 * and list it in addChildren below.
 *
 * Previously named routeTree.gen.ts, which said the opposite: the docs told
 * people not to edit a file that nothing generates, and adding a route is
 * impossible without editing it. Not named routes.ts either -- that would sit
 * beside the routes/ directory and its index.tsx, and the two resolve
 * differently for the same import specifier.
 *
 * Every route nests under rootRoute, whose component is RootLayout -- which is
 * why the header, footer, auth gate and toaster render on every page.
 */
import { RootRoute, Route } from '@tanstack/react-router'
import { RootLayout } from './routes/__root'
import { HomePage } from './routes/index'
import { LoginPage } from './routes/login'
import { PatientsPage } from './routes/papers.$paperId.patients'
import { SettingsPage } from './routes/settings'

const rootRoute = new RootRoute({
  component: RootLayout,
})

const indexRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
})

const loginRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: LoginPage,
})

const settingsRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: SettingsPage,
})

const papersPatientRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/papers/$paperId/patients',
  component: PatientsPage,
})

export const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  settingsRoute,
  papersPatientRoute,
])

export { papersPatientRoute }
