/* Root layout component
 * This wraps all routes with common header/nav and outlet for child routes
 */
import '@/lib/api'
import React, { useEffect } from 'react'
import { Link, Outlet, useNavigate, useParams, useRouterState } from '@tanstack/react-router'
import { Bug, GitBranch, Lightbulb } from 'lucide-react'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Spinner } from '@/components/ui/spinner'
import { ActivityIndicator } from '@/components/ActivityIndicator'
import { ChatBubble } from '@/components/ChatBubble'
import { useTaskTypes } from '@/components/TaskSuccessors'
import { UserMenu } from '@/components/UserMenu'
import { AuthProvider, useAuth } from '@/lib/auth'

/* Renders the chat bubble on every /papers/$paperId/* page. Reads the param
 * loosely (strict: false) so it works from any current or future route
 * nested under a paper, without each of those routes wiring it in itself. */
function PaperChatBubble() {
  const { paperId } = useParams({ strict: false })
  if (!paperId) return null
  return <ChatBubble paperId={Number(paperId)} />
}

/* Gate every route behind a token. Reads happen to be open on the API, but the
 * app is only useful signed in and every mutation would 401, so redirect rather
 * than render a half-working page.
 */
function AuthGate({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth()
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const onLoginPage = pathname === '/login'

  useEffect(() => {
    if (!token && !onLoginPage) navigate({ to: '/login' })
    if (token && onLoginPage) navigate({ to: '/' })
  }, [token, onLoginPage, navigate])

  if (onLoginPage) return <>{children}</>
  if (!token) return null
  // Hold the first paint until /auth/me resolves, so children never flash with a
  // token that turns out to be expired.
  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    )
  }
  return <>{children}</>
}

const REPO_URL = 'https://github.com/clingen-data-model/cur-ai-ss'

/* The footer's outbound links: the repository, and a new GitHub issue on the
 * bug-report or feature-request form (.github/ISSUE_TEMPLATE/) with its Page
 * field already filled in -- the one fact a report from a non-developer most
 * often leaves out. Built at render from the router's location so they
 * follow navigation. */
function FooterLinks() {
  useRouterState({ select: (s) => s.location.pathname })
  const issueUrl = (template: string) =>
    `${REPO_URL}/issues/new?${new URLSearchParams({ template, page: window.location.href }).toString()}`
  const linkClass = 'inline-flex items-center gap-1 hover:text-slate-900 hover:underline underline-offset-2'
  return (
    <nav className="flex items-center justify-center gap-5">
      <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className={linkClass}>
        <GitBranch className="size-3.5" aria-hidden="true" />
        GitHub
      </a>
      <a href={issueUrl('bug_report.yml')} target="_blank" rel="noopener noreferrer" className={linkClass}>
        <Bug className="size-3.5" aria-hidden="true" />
        Report a bug
      </a>
      <a href={issueUrl('feature_request.yml')} target="_blank" rel="noopener noreferrer" className={linkClass}>
        <Lightbulb className="size-3.5" aria-hidden="true" />
        Request a feature
      </a>
    </nav>
  )
}

function Layout() {
  const { token } = useAuth()
  // The re-run dialogs read these (what each task is for, what it triggers).
  // Fetched once when the app loads, signed in, rather than when the first
  // dialog opens, where the request made its contents pop in. Fixed for the
  // life of a deploy, so the cache keeps it.
  useTaskTypes(token !== null)

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      {/* w-full px-6, matching <main> below -- not `container`, or its
          per-breakpoint max-width centers the logo/nav in a narrower box
          than the now-full-width content, misaligning both edges. */}
      <header className="gradient-header border-b border-slate-200">
        <div className="w-full px-6 py-2 flex items-center justify-between">
          {/* Link (not <a href="/">) so the router prepends the basepath — a raw '/'
              would ignore the router's basepath if the app were served under a prefix. Likewise
              the logo resolves against BASE_URL, since public/ assets are emitted under
              the base path. */}
          <Link to="/" className="hover:opacity-80 transition-opacity">
            <img
              src={`${import.meta.env.BASE_URL}clingen-logo.svg`}
              alt="ClinGen"
              className="h-8 brightness-0 invert"
            />
          </Link>
          <nav className="flex items-center gap-4">
            {token && <ActivityIndicator />}
            {token && <UserMenu />}
          </nav>
        </div>
      </header>

      {/* Main content */}
      {/* No `container` here (unlike header/footer) -- its per-breakpoint
          max-width left a growing empty margin on wide screens where content
          like the extraction page's tables most wants the space. */}
      <main className="flex-1 w-full px-6 py-8">
        <AuthGate>
          <Outlet />
        </AuthGate>
      </main>

      {/* Footer */}
      <footer className="bg-slate-100 border-t border-slate-200">
        <div className="container mx-auto px-4 py-4 flex flex-col items-center gap-1.5 text-center text-sm text-slate-600">
          <p>Gene Curation w/ AI-Assistance</p>
          <FooterLinks />
        </div>
      </footer>

      <PaperChatBubble />
      <Toaster position="top-right" />
    </div>
  )
}

export function RootLayout() {
  return (
    <TooltipProvider>
      <AuthProvider>
        <Layout />
      </AuthProvider>
    </TooltipProvider>
  )
}
