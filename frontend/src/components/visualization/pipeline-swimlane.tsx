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

export function PipelineSwimlane() {
  return (
    <div className="space-y-4">
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

    </div>
  )
}
