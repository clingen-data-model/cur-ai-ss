/* Root layout component
 * This wraps all routes with common header/nav and outlet for child routes
 */
import '@/lib/api'
import { Outlet } from '@tanstack/react-router'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

export function RootLayout() {
  return (
    <TooltipProvider>
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-900">CAA</h1>
          <nav className="flex gap-4">
            <a href="/" className="text-slate-600 hover:text-slate-900">
              Home
            </a>
          </nav>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 container mx-auto px-4 py-8">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="bg-slate-100 border-t border-slate-200">
        <div className="container mx-auto px-4 py-4 text-center text-sm text-slate-600">
          <p>Gene Curation w/ AI-Assistance</p>
        </div>
      </footer>

      <Toaster position="top-right" />
    </div>
    </TooltipProvider>
  )
}
