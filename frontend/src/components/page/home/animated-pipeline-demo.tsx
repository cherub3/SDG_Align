import { useEffect, useState } from "react"
import { ExecutionTimeline } from "../../visualization/execution-timeline"
import { ObservationRecord } from "../../shared/observation-record"
import { useBackendAdapter } from "../../../lib/backend-adapter"
import type { QueryResult } from "../../../lib/backend-adapter"
import { useOperatingMode } from "../../../providers/operating-mode-provider"

// getSampleQuery() is intentionally unsupported in Mode A (Version 1.3 Decision 4 — there is no
// live equivalent of "the sample query"). This fixed string stands in for it only in that mode.
const LIVE_MODE_DEMO_QUERY = "What SDG goals are addressed?"

export function AnimatedPipelineDemo() {
  const adapter = useBackendAdapter()
  const { mode } = useOperatingMode()
  const [runId, setRunId] = useState(0)
  const [query, setQuery] = useState<string | null>(null)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const replay = () => setRunId((id) => id + 1)

  useEffect(() => {
    let cancelled = false
    setError(null)
    const queryPromise =
      mode === "Mode A (Live)" ? Promise.resolve(LIVE_MODE_DEMO_QUERY) : adapter.getSampleQuery()
    queryPromise
      .then((q) => {
        if (cancelled) return
        setQuery(q)
        return adapter.runQuery(q)
      })
      .then((r) => {
        if (cancelled || !r) return
        setResult(r)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setError(err.message)
      })
    return () => {
      cancelled = true
    }
    // adapter identity changes whenever the operating mode changes — re-fetch on mode change too.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adapter, runId])

  return (
    <section aria-labelledby="pipeline-preview-heading" className="py-16 px-4 bg-background">
      <div className="max-w-5xl mx-auto space-y-8">
        <div className="text-center space-y-2">
          <h2 id="pipeline-preview-heading" className="text-3xl font-bold tracking-tight">
            Interactive Pipeline Demo
          </h2>
          {query && <p className="text-muted-foreground">Query: "{query}"</p>}
        </div>

        {error && (
          <div className="max-w-5xl mx-auto text-sm text-destructive border border-destructive/30 rounded-lg p-4">
            {error}
          </div>
        )}

        {result && (
          <div className="p-6 md:p-8 border rounded-xl bg-card shadow-sm space-y-3">
            <ExecutionTimeline stages={result.stages} runId={runId} />

            <div className="pt-4 border-t flex flex-wrap items-center gap-3 text-sm">
              <span>{result.answer}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-semibold">
                {result.citations === null ? "Citation data unavailable in Mode A" : `${result.citationCount} citations ✓`}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-semibold">
                {result.groundedness}
              </span>
              <span className="text-muted-foreground text-xs" title="0.7 x verbatim overlap + 0.3 x citation presence. Strict: a correct paraphrase scores low.">Strict quality score: {result.qualityScore}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-semibold">
                {result.outcome}
              </span>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <ObservationRecord
                correlationId={result.correlationId}
                outcome={result.observationOutcome}
                duration={result.durationSeconds}
              />
              <div className="flex gap-3 text-xs">
                <button
                  onClick={replay}
                  className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  Replay ↺
                </button>
                <a
                  href="/pipeline-explorer"
                  className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                >
                  Open in Explorer →
                </a>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
