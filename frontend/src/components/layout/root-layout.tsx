import { Outlet } from "react-router-dom"
import { ThemeProvider } from "../../providers/theme-provider"
import { OperatingModeProvider } from "../../providers/operating-mode-provider"
import { ReducedMotionProvider } from "../../providers/reduced-motion-provider"
import { NavBar } from "./nav-bar"
import { BackendStatusBanner } from "./backend-status-banner"

export function RootLayout() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="app-theme">
      <OperatingModeProvider>
        <ReducedMotionProvider>
          <div className="min-h-screen bg-background text-foreground flex flex-col font-sans antialiased">
            <a
              href="#main-content"
              className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:p-4 focus:bg-background focus:text-foreground"
            >
              Skip to content
            </a>
            <NavBar />
            <BackendStatusBanner />
            <main id="main-content" className="flex-1 focus-visible:outline-none" tabIndex={-1}>
              <Outlet />
            </main>
            <footer className="border-t h-16 flex items-center justify-center px-4">
              <p className="text-sm text-muted-foreground">SDG Align — a 22-stage RAG + agent pipeline with content-deterministic ingestion</p>
            </footer>
          </div>
        </ReducedMotionProvider>
      </OperatingModeProvider>
    </ThemeProvider>
  )
}
