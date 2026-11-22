import { useEffect, useRef, useState } from "react"
import { NavLink } from "react-router-dom"

const NAV_ITEMS = [
  { to: "/", label: "Home" },
  { to: "/architecture", label: "Architecture" },
  { to: "/pipeline-explorer", label: "Pipeline Explorer" },
  { to: "/observability", label: "Observability" },
  { to: "/about", label: "About" },
]

function linkClass({ isActive }: { isActive: boolean }) {
  return `pb-1 border-b-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm ${
    isActive
      ? "border-primary text-foreground font-semibold"
      : "border-transparent text-muted-foreground hover:text-foreground"
  }`
}

export function NavBar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const drawerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (mobileOpen) {
      drawerRef.current?.focus()
    } else {
      triggerRef.current?.focus()
    }
  }, [mobileOpen])

  useEffect(() => {
    if (!mobileOpen) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false)
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [mobileOpen])

  return (
    <header className="sticky top-0 z-40 border-b h-16 flex items-center px-4 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex items-center gap-2 font-bold text-lg">
        <span aria-hidden="true" className="inline-block w-2 h-2 rounded-full bg-primary" />
        SDG Align
      </div>

      <nav aria-label="Main Navigation" className="hidden md:flex items-center gap-8 ml-10">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/"} className={linkClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <button
        ref={triggerRef}
        type="button"
        className="md:hidden ml-auto text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded p-2"
        aria-label={mobileOpen ? "Close menu" : "Open menu"}
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen((v) => !v)}
      >
        <span aria-hidden="true" className="text-xl leading-none">{mobileOpen ? "✕" : "☰"}</span>
      </button>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setMobileOpen(false)}
            className="absolute inset-0 bg-background/60"
          />
          <div
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Main Navigation"
            tabIndex={-1}
            className="relative h-full w-full bg-background flex flex-col items-center justify-center gap-8 focus-visible:outline-none"
          >
            <nav aria-label="Main Navigation (mobile)" className="flex flex-col items-center gap-6">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={linkClass}
                  onClick={() => setMobileOpen(false)}
                >
                  <span className="text-xl">{item.label}</span>
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      )}
    </header>
  )
}
