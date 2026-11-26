import { Link } from "react-router-dom"
import { useParams, Navigate } from "react-router-dom"
import { Breadcrumb } from "../components/layout/breadcrumb"
import { PhaseTimeline } from "../components/layout/phase-timeline"
import { ArchitectureDoc } from "../components/page/architecture/architecture-doc"
import { architecturePhases } from "../content/demo-data/architecture-phases"
import { phaseDetailContent } from "../content/demo-data/architecture-phase-detail"

export function PhaseDetailPage() {
  const { phaseId } = useParams<{ phaseId: string }>()
  const content = phaseId ? phaseDetailContent[phaseId] : undefined
  const phaseMeta = phaseId ? architecturePhases.find((p) => p.phaseId === phaseId) : undefined

  if (!content || !phaseMeta) {
    return <Navigate to="/architecture" replace />
  }

  const index = architecturePhases.findIndex((p) => p.phaseId === phaseId)
  const previous = index > 0 ? architecturePhases[index - 1] : undefined
  const next = index < architecturePhases.length - 1 ? architecturePhases[index + 1] : undefined

  return (
    <div className="max-w-7xl mx-auto px-4 py-12">
      <div className="flex flex-col md:flex-row gap-10">
        <aside className="md:w-56 shrink-0 md:sticky md:top-4 md:self-start">
          <PhaseTimeline orientation="vertical" activePhaseId={phaseId} />
        </aside>

        <div className="flex-1 min-w-0 space-y-6">
          <Breadcrumb
            items={[
              { label: "Architecture", href: "/architecture" },
              { label: `Phase ${phaseMeta.label.split(" ")[0]}`, href: undefined },
              { label: phaseMeta.name },
            ]}
          />

          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">{phaseMeta.name}</h1>
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/15 text-blue-700 dark:text-blue-400 px-2.5 py-0.5 text-xs font-semibold">
              {phaseMeta.status}
            </span>
          </div>

          <ArchitectureDoc content={content} />

          <nav aria-label="Phase navigation" className="flex items-center justify-between pt-6 border-t border-border">
            {previous ? (
              <Link
                to={`/architecture/${previous.phaseId}`}
                className="text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
              >
                ← Previous: {previous.label}
              </Link>
            ) : (
              <span />
            )}
            {next ? (
              <Link
                to={`/architecture/${next.phaseId}`}
                className="text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
              >
                Next: {next.label} →
              </Link>
            ) : (
              <span />
            )}
          </nav>
        </div>
      </div>
    </div>
  )
}
