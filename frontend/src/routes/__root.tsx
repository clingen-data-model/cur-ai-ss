/* Root layout component
 * This wraps all routes with common header/nav and outlet for child routes
 */
import '@/lib/api'
import React, { useEffect } from 'react'
import { Outlet, useNavigate, useRouterState } from '@tanstack/react-router'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Spinner } from '@/components/ui/spinner'
import { UserMenu } from '@/components/UserMenu'
import { AuthProvider, useAuth } from '@/lib/auth'

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

function Layout() {
  const { token } = useAuth()

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="gradient-header border-b border-slate-200">
        <div className="container mx-auto px-4 py-2 flex items-center justify-between">
          <a href="/" className="hover:opacity-80 transition-opacity">
            <img src="/clingen-logo.svg" alt="ClinGen" className="h-8 brightness-0 invert" />
          </a>
          <nav className="flex gap-4">{token && <UserMenu />}</nav>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 container mx-auto px-4 py-8">
        <AuthGate>
          <Outlet />
        </AuthGate>
      </main>

      {/* Footer */}
      <footer className="bg-slate-100 border-t border-slate-200">
        <div className="container mx-auto px-4 py-4 text-center text-sm text-slate-600">
          <p>Gene Curation w/ AI-Assistance</p>
        </div>
      </footer>

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
