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
      <header className="gradient-header border-b border-slate-200">
        <div className="container mx-auto px-4 py-2 flex items-center justify-between">
          <a href="/" className="hover:opacity-80 transition-opacity">
            <img src="/clingen-logo.svg" alt="ClinGen" className="h-8 brightness-0 invert" />
          </a>
          <nav className="flex gap-4">
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
