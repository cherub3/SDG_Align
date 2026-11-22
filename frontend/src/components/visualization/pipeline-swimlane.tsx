import { TooltipOverlay } from "../shared/tooltip-overlay"
import { stageMetadata, type StageMetadataItem } from "../../content/demo-data/pipeline-trace"
import { stageAnchorId } from "../../lib/stage-anchor"

const lanes: StageMetadataItem["lane"][] = ["Ingestion", "RAG", "Agent"]

const laneLabel: Record<StageMetadataItem["lane"], string> = {
  Ingestion: "Ingestion (Stages 0–9)",
  RAG: "Query-time RAG (Stages 10–18)",
  Agent: "Agent (Stages 19–21)",
}

function scrollToStage(stageNumber: number) {
  document.getElementById(stageAnchorId(stageNumber))?.scrollIntoView({ behavior: "smooth", block: "center" })
}

function downloadSwimlaneSvg() {
  const svg = document.getElementById("pipeline-swimlane-svg")
  if (!svg) return
  const serialized = new XMLSerializer().serializeToString(svg)
  const blob = new Blob([serialized], { type: "image/svg+xml" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "sdg-align-pipeline-swimlane.svg"
  a.click()
  URL.revokeObjectURL(url)
}

export function PipelineSwimlane() {
  return (
    <div className="space-y-4">
      <svg id="pipeline-swimlane-svg" role="img" aria-label="22-stage pipeline swimlane diagram" className="w-full" viewBox="0 0 100 30" preserveAspectRatio="none" style={{ height: 0, width: 0 }}>
        <title>22-stage pipeline swimlane diagram</title>
      </svg>

      {lanes.map((lane, laneIndex) => (
        <div key={lane}>
          <p className="text-xs font-medium text-muted-foreground mb-2">{laneLabel[lane]}</p>
          <div className="flex flex-wrap gap-2">
            {stageMetadata
              .filter((s) => s.lane === lane)
              .map((s) => (
                <TooltipOverlay key={s.stage_number} content={`${s.name} (Stage ${s.stage_number})`}>
                  <button
                    type="button"
                    onClick={() => scrollToStage(s.stage_number)}
                    className="flex items-center justify-center w-11 h-11 rounded-md border border-border bg-card text-xs font-semibold hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {s.abbreviation}
                  </button>
                </TooltipOverlay>
              ))}
          </div>
          {laneIndex !== lanes.length - 1 && (
            <div aria-hidden="true" className="border-t border-dashed border-border my-3 w-full" />
          )}
        </div>
      ))}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={downloadSwimlaneSvg}
          className="text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
        >
          Download SVG ↓
        </button>
      </div>
    </div>
  )
}
