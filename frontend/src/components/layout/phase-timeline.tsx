import { Link } from "react-router-dom"
import { StatusBadge } from "../shared/status-badge"
import { architecturePhases } from "../../content/demo-data/architecture-phases"

interface PhaseTimelineProps {
  orientation?: "horizontal" | "vertical"
  activePhaseId?: string
}

export function PhaseTimeline({ orientation = "horizontal", activePhaseId }: PhaseTimelineProps) {
  const isVertical = orientation === "vertical"

  return (
    <nav
      aria-label={isVertical ? "Architecture phase navigation" : "Architecture phase timeline"}
      className={isVertical ? "" : "overflow-x-auto"}
    >
      <ol className={isVertical ? "flex flex-col gap-1" : "flex items-center gap-2 min-w-max py-1"}>
        {architecturePhases.map((phase, i) => {
          const isActive = phase.phaseId === activePhaseId
          return (
            <li key={phase.phaseId} className={isVertical ? "" : "flex items-center gap-2"}>
              <Link
                to={`/architecture/${phase.phaseId}`}
                aria-current={isActive ? "page" : undefined}
                className={
                  isVertical
                    ? `flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${isActive ? "bg-primary/10 text-primary" : ""}`
                    : "inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border bg-card text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                }
              >
                {phase.label}
                {!isVertical && <StatusBadge status="FROZEN" label={phase.status} />}
              </Link>
              {!isVertical && i !== architecturePhases.length - 1 && (
                <span aria-hidden="true" className="text-muted-foreground">
                  →
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
