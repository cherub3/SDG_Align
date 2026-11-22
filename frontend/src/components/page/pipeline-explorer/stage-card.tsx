import { ExpandoPanel } from "../../shared/expando-panel"
import { CodeBlock } from "../../shared/code-block"
import type { StageTimelineItem } from "../../../content/demo-data/pipeline-trace"

export function StageCard({ stage }: { stage: StageTimelineItem }) {
  const statusIcon =
    stage.status === "completed"
      ? "✓"
      : stage.status === "cache_miss"
        ? "✗ MISS"
        : stage.status === "incomplete"
          ? "… INCOMPLETE"
          : "✗"
  const raw = JSON.stringify(stage, null, 2)

  return (
    <ExpandoPanel
      summary={
        <span className="flex items-center gap-3">
          <span className="font-medium text-foreground">
            Stage {stage.stage_number} — {stage.stage_name}
          </span>
          <span aria-hidden="true" className="text-muted-foreground text-sm">
            {statusIcon} {stage.elapsed_ms}ms
          </span>
        </span>
      }
    >
      <p className="mb-2">{stage.summary_line}</p>
      <CodeBlock code={raw} label="Raw Output" />
    </ExpandoPanel>
  )
}
