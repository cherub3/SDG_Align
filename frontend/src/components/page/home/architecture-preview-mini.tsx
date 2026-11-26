import { Link } from "react-router-dom"
import { TooltipOverlay } from "../../shared/tooltip-overlay"
import { stageMetadata, type StageMetadataItem } from "../../../content/demo-data/pipeline-trace"

const lanes: StageMetadataItem["lane"][] = ["Ingestion", "RAG", "Agent"]

const phaseLayers = ["Config", "Composition", "Bootstrap", "Runtime", "Obs"]

function StageNode({ stage }: { stage: StageMetadataItem }) {
  return (
    <TooltipOverlay content={`${stage.name} (Stage ${stage.stage_number})`}>
      <span className="flex items-center justify-center w-9 h-9 rounded-md border border-border bg-background text-[10px] font-semibold">
        {stage.abbreviation}
      </span>
    </TooltipOverlay>
  )
}

export function ArchitecturePreviewMini() {
  return (
    <section aria-labelledby="architecture-preview-heading" className="py-16 px-4 bg-muted/20 border-y border-border">
      <div className="max-w-7xl mx-auto space-y-8">
        <div className="text-center space-y-2">
          <h2 id="architecture-preview-heading" className="text-3xl font-bold tracking-tight">
            Architecture Preview
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            Three layers: ingestion, RAG, and agent. Backend stages are covered by pytest (about 87% of scripts/); the frontend has no automated tests.
          </p>
        </div>

        {/* Desktop / tablet: mini swimlane */}
        <div className="hidden md:flex gap-8 items-start">
          <div className="flex-1 space-y-3">
            {lanes.map((lane) => (
              <div key={lane} className="flex items-center gap-2">
                <span className="w-16 shrink-0 text-xs font-medium text-muted-foreground">{lane}</span>
                <div className="flex flex-wrap gap-1.5">
                  {stageMetadata
                    .filter((s) => s.lane === lane)
                    .map((s, i, arr) => (
                      <span key={s.stage_number} className="flex items-center">
                        <StageNode stage={s} />
                        {lane !== "Agent" && i === arr.length - 1 && (
                          <span aria-hidden="true" className="mx-1 border-l border-dashed border-border h-9" />
                        )}
                      </span>
                    ))}
                </div>
              </div>
            ))}
          </div>
          <div className="w-40 shrink-0 border-l border-border pl-4 space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Phase Layers</span>
            {phaseLayers.map((layer) => (
              <div key={layer} className="text-sm">
                {layer}
              </div>
            ))}
          </div>
        </div>

        {/* Mobile fallback: grouped numbered list */}
        <div className="md:hidden space-y-4">
          {lanes.map((lane) => (
            <div key={lane}>
              <h3 className="text-sm font-semibold mb-2">{lane}</h3>
              <ol className="text-sm text-muted-foreground space-y-1">
                {stageMetadata
                  .filter((s) => s.lane === lane)
                  .map((s) => (
                    <li key={s.stage_number}>
                      Stage {s.stage_number} — {s.name}
                    </li>
                  ))}
              </ol>
            </div>
          ))}
        </div>

        <div className="text-center">
          <Link
            to="/architecture"
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-primary bg-primary/10 rounded-md hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            View full architecture →
          </Link>
        </div>
      </div>
    </section>
  )
}
