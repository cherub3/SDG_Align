import { motion, AnimatePresence } from "framer-motion"
import { useReducedMotion } from "../../providers/reduced-motion-provider"
import { TooltipOverlay } from "../shared/tooltip-overlay"
import type { StageTimelineItem } from "../../content/demo-data/pipeline-trace"

const statusColor: Record<string, string> = {
  completed: "bg-emerald-500",
  failed: "bg-destructive",
  cache_miss: "bg-amber-500",
  incomplete: "bg-muted-foreground",
}

const MIN_BAR_PERCENT = 4

interface ExecutionTimelineProps {
  stages: StageTimelineItem[]
  runId?: number
  onStageClick?: (stageNumber: number) => void
}

export function ExecutionTimeline({ stages, runId = 0, onStageClick }: ExecutionTimelineProps) {
  const { reduceMotion } = useReducedMotion()
  const totalMs = stages.reduce((sum, s) => sum + s.elapsed_ms, 0)
  // No stage ran at all (e.g. the planner itself failed before executing any step) -- a real
  // possibility in Mode A that never occurs in Mode B/C's always-non-empty canned traces.
  const dominant =
    stages.length > 0 ? stages.reduce((max, s) => (s.elapsed_ms > max.elapsed_ms ? s : max), stages[0]) : null
  const dominantPercent = dominant ? Math.round((dominant.elapsed_ms / totalMs) * 100) : 0

  if (stages.length === 0) {
    return (
      <div className="space-y-3">
        <div className="flex items-baseline justify-between text-sm text-muted-foreground">
          <span>Execution Timeline</span>
        </div>
        <p className="text-sm text-muted-foreground">No stages executed.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between text-sm text-muted-foreground">
        <span>Execution Timeline</span>
        <span>Total: {totalMs}ms</span>
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={runId} className="space-y-2">
          {stages.map((stage, index) => {
            const percent = Math.max((stage.elapsed_ms / totalMs) * 100, MIN_BAR_PERCENT)
            const isDominant = dominant !== null && stage.stage_number === dominant.stage_number
            return (
              <TooltipOverlay
                key={stage.stage_number}
                content={`Stage ${stage.stage_number} ${stage.stage_name} — ${stage.summary_line}`}
              >
                <button
                  type="button"
                  onClick={() => onStageClick?.(stage.stage_number)}
                  className="w-full flex flex-col gap-1 md:flex-row md:items-center md:gap-3 text-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  <div className="flex items-center justify-between md:contents">
                    <span className="text-muted-foreground md:w-32 md:shrink-0">
                      Stage {stage.stage_number} {stage.stage_name}
                    </span>
                    <span className="flex items-center gap-2 md:hidden">
                      <span className="tabular-nums text-muted-foreground">{stage.elapsed_ms}ms</span>
                      <span aria-hidden="true">{stage.status === "completed" ? "✓" : stage.status === "incomplete" ? "…" : "✗"}</span>
                    </span>
                  </div>
                  <div className="flex-1 h-3 bg-muted rounded-full overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full ${statusColor[stage.status]}`}
                      initial={{ width: reduceMotion ? `${percent}%` : "0%" }}
                      animate={{ width: `${percent}%` }}
                      transition={
                        reduceMotion
                          ? { duration: 0 }
                          : { duration: 0.4, delay: index * 0.05, ease: [0, 0, 0.2, 1] }
                      }
                    />
                  </div>
                  <span className="hidden md:inline w-16 shrink-0 text-right tabular-nums text-muted-foreground">
                    {stage.elapsed_ms}ms
                  </span>
                  <span aria-hidden="true" className="hidden md:inline">
                    {stage.status === "completed" ? "✓" : stage.status === "incomplete" ? "…" : "✗"}
                  </span>
                  {stage.status === "cache_miss" && (
                    <span className="text-xs font-medium text-amber-600 dark:text-amber-400 shrink-0">MISS</span>
                  )}
                  {stage.status === "incomplete" && (
                    <span className="text-xs font-medium text-muted-foreground shrink-0">INCOMPLETE</span>
                  )}
                  {isDominant && (
                    <span className="text-xs font-medium text-primary shrink-0">
                      ↑ {dominantPercent}% of total
                    </span>
                  )}
                </button>
              </TooltipOverlay>
            )
          })}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
