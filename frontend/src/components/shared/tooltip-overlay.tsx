import { useState, type ReactNode } from "react"

interface TooltipOverlayProps {
  content: string
  children: ReactNode
}

export function TooltipOverlay({ content, children }: TooltipOverlayProps) {
  const [visible, setVisible] = useState(false)

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span
          role="tooltip"
          className="absolute -top-9 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background shadow-md z-10"
          style={{
            animation: "tooltip-in var(--duration-fast) var(--ease-decelerate)",
          }}
        >
          {content}
        </span>
      )}
    </span>
  )
}
