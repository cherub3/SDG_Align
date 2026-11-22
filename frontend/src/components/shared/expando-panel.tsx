import { useState, type ReactNode } from "react"

interface ExpandoPanelProps {
  summary: ReactNode
  children: ReactNode
  defaultExpanded?: boolean
}

export function ExpandoPanel({ summary, children, defaultExpanded = false }: ExpandoPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div className="border rounded-lg bg-card">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
      >
        {summary}
        <span aria-hidden="true" className="shrink-0 text-muted-foreground">
          {expanded ? "−" : "+"}
        </span>
      </button>
      {expanded && <div className="px-4 pb-4 text-sm text-muted-foreground">{children}</div>}
    </div>
  )
}
