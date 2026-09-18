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
import { isPaperState, type PaperState, isReviewState, type ReviewState } from './lib/paperState'

import { RootLayout } from './routes/__root'
import { HomePage } from './routes/index'
import { LoginPage } from './routes/login'
import { ExtractionPage } from './routes/papers.$paperId.extraction'
import { SettingsPage } from './routes/settings'

const rootRoute = new RootRoute({
  component: RootLayout,
})

/** `?worked_by=` narrows the papers table to one person's work.
 *
 * In the URL rather than component state so a personal view is a link someone
 * can bookmark -- which is what replaced a separate "My Papers" tab -- and so
 * it survives a reload.
 *
 * Values: absent or 'anyone' for everything, 'me' for the signed-in user, or a
 * numeric user id. 'me' is a distinct value rather than that user's id so a
 * bookmarked link keeps meaning "mine" for whoever opens it.
 */
export interface IndexSearch {
  worked_by?: 'anyone' | 'me' | number
  /** A PaperState, or absent for every state. */
  status?: PaperState
  /** A ReviewState, or absent for every review state. */
  review_status?: ReviewState
}

const indexRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/',
  component: HomePage,
  validateSearch: (search: Record<string, unknown>): IndexSearch => {
    const parsed: IndexSearch = {}

    const who = search.worked_by
    if (who === 'me' || who === 'anyone') {
      parsed.worked_by = who
    } else {
      const id = Number(who)
      if (Number.isInteger(id) && id > 0) parsed.worked_by = id
    }

    // The four states the table speaks in, not the six the API reports -- see
    // lib/paperState. An old link carrying 'pending' or 'partial' simply falls
    // through to showing everything, which is the same forgiving behaviour as
    // any other unreadable filter below.
    const status = search.status
    if (isPaperState(status)) parsed.status = status

    // Review states for curation workflow filtering.
    const reviewStatus = search.review_status
    if (isReviewState(reviewStatus)) parsed.review_status = reviewStatus

    // Anything unreadable falls through to showing everything rather than
    // erroring: these are filters, and a broken one should not be a broken page.
    return parsed
  },
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

const papersExtractionRoute = new Route({
  getParentRoute: () => rootRoute,
  path: '/papers/$paperId/extraction',
  component: ExtractionPage,
})

export const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  settingsRoute,
  papersExtractionRoute,
])

export { papersExtractionRoute }
