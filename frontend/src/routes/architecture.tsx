import { NarrativeBlock } from "../components/shared/narrative-block"
import { ExpandoPanel } from "../components/shared/expando-panel"
import { PhaseTimeline } from "../components/layout/phase-timeline"
import { PipelineSwimlane } from "../components/visualization/pipeline-swimlane"
import { stageMetadata } from "../content/demo-data/pipeline-trace"
import { stageAnchorId } from "../lib/stage-anchor"

export function ArchitecturePage() {
  return (
    <div className="max-w-7xl mx-auto px-4 py-12 space-y-10">
      <h1 className="sr-only">Architecture Overview</h1>

      <NarrativeBlock
        headline="SDG Align is built in two layers."
        body="A frozen 22-stage pipeline that processes documents and answers questions, and an 8-phase application shell that wires, bootstraps, and orchestrates it. This page maps both."
      />

      <section aria-labelledby="phase-timeline-heading" className="space-y-3">
        <h2 id="phase-timeline-heading" className="sr-only">
          Phase Timeline
        </h2>
        <PhaseTimeline />
      </section>

      <section aria-labelledby="swimlane-heading" className="space-y-4">
        <h2 id="swimlane-heading" className="text-2xl font-bold tracking-tight">
          22-Stage Pipeline
        </h2>
        <PipelineSwimlane />
      </section>

      <section aria-labelledby="stage-detail-heading" className="space-y-4">
        <h2 id="stage-detail-heading" className="text-2xl font-bold tracking-tight">
          Stage Detail
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {stageMetadata.map((stage) => (
            <div key={stage.stage_number} id={stageAnchorId(stage.stage_number)}>
              <ExpandoPanel summary={<span className="font-medium text-foreground">Stage {stage.stage_number} — {stage.name}</span>}>
                <p>{stage.role}</p>
                <p className="mt-1 text-xs">Lane: {stage.lane}</p>
              </ExpandoPanel>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
