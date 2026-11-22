import { useEffect, useRef, type ReactNode } from "react"

interface DrawerPanelProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

// Shared focus-trap mechanism for any right-side slide-in overlay (Observability Record Detail
// today; the mobile nav drawer is a separate, already-built consumer of the same pattern).
export function DrawerPanel({ open, onClose, title, children }: DrawerPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement
      panelRef.current?.focus()
    } else {
      triggerRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close drawer"
        onClick={onClose}
        className="absolute inset-0 bg-background/60"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative w-full max-w-sm h-full bg-card border-l shadow-lg p-6 space-y-4 overflow-y-auto focus-visible:outline-none"
      >
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-bold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded px-2 py-1"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
