import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { NarrativeBlock } from "../components/shared/narrative-block"
import { ExecutionTimeline } from "../components/visualization/execution-timeline"
import { StageCard } from "../components/page/pipeline-explorer/stage-card"
import { CitationCard } from "../components/page/pipeline-explorer/citation-card"
import { PlannerStateCard } from "../components/page/pipeline-explorer/planner-state-card"
import { ObservationRecord } from "../components/shared/observation-record"
import { useBackendAdapter } from "../lib/backend-adapter"
import type { QueryResult } from "../lib/backend-adapter"
import { useOperatingMode } from "../providers/operating-mode-provider"

// getSampleQuery() is intentionally unsupported in Mode A (Version 1.3 Decision 4 — there is no
// live equivalent of "the sample query"). This fixed string stands in for it only in that mode.
const LIVE_MODE_DEFAULT_QUERY = "What SDG goals are addressed?"

type View = "timeline" | "cards"

export function PipelineExplorerPage() {
  const adapter = useBackendAdapter()
  const { mode } = useOperatingMode()
  const [searchParams, setSearchParams] = useSearchParams()
  const view: View = searchParams.get("view") === "cards" ? "cards" : "timeline"
  const [runId, setRunId] = useState(0)
  const [plannerExpanded, setPlannerExpanded] = useState(false)
  const [sampleQuery, setSampleQuery] = useState<string | null>(null)
  const [sampleResult, setSampleResult] = useState<QueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    const queryPromise =
      mode === "Mode A (Live)" ? Promise.resolve(LIVE_MODE_DEFAULT_QUERY) : adapter.getSampleQuery()
    queryPromise
      .then((q) => {
        if (cancelled) return
        setSampleQuery(q)
        return adapter.runQuery(q)
      })
      .then((r) => {
        if (cancelled || !r) return
        setSampleResult(r)
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

  const setView = (next: View) => {
    const params = new URLSearchParams(searchParams)
    params.set("view", next)
    setSearchParams(params, { replace: true })
  }

  const runQuery = () => setRunId((id) => id + 1)

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <h1 className="sr-only">Pipeline Explorer</h1>
        <div className="text-sm text-destructive border border-destructive/30 rounded-lg p-4">{error}</div>
      </div>
    )
  }

  if (!sampleResult || sampleQuery === null) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <h1 className="sr-only">Pipeline Explorer</h1>
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    )
  }

  const pipelineTrace = sampleResult.stages
  const sampleCitations = sampleResult.citations

  return (
    <div className="max-w-7xl mx-auto px-4 py-12">
      <h1 className="sr-only">Pipeline Explorer</h1>

      <NarrativeBlock
        headline="Submit a query. Watch it move through 12 pipeline stages in real time."
        body="Retrieval, context assembly, LLM execution, citation extraction, groundedness validation, and the agent planner. Every stage is timed, labeled, and inspectable."
      />

      <div className="flex flex-col md:flex-row gap-10 mt-8">
        <aside className="md:w-72 shrink-0 space-y-4">
          <div>
            <label htmlFor="query-input" className="block text-sm font-medium mb-1">
              Query
            </label>
            <textarea
              id="query-input"
              defaultValue={sampleQuery}
              rows={3}
              className="w-full rounded-md border border-border bg-card p-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label htmlFor="doc-select" className="block text-sm font-medium mb-1">
              Documents
            </label>
            <select
              id="doc-select"
              defaultValue="all"
              className="w-full rounded-md border border-border bg-card p-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="all">6 indexed docs</option>
            </select>
          </div>
          <button
            onClick={runQuery}
            className="w-full px-4 py-2 bg-primary text-primary-foreground font-medium rounded-md hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Run Query ▶
          </button>
        </aside>

        <div className="flex-1 min-w-0 space-y-6">
          <div className="flex items-center gap-2" role="group" aria-label="View">
            <button
              onClick={() => setView("timeline")}
              aria-pressed={view === "timeline"}
              className={`px-3 py-1.5 rounded-md text-sm font-medium border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                view === "timeline" ? "bg-primary text-primary-foreground border-primary" : "border-border bg-card"
              }`}
            >
              Timeline ▤
            </button>
            <button
              onClick={() => setView("cards")}
              aria-pressed={view === "cards"}
              className={`px-3 py-1.5 rounded-md text-sm font-medium border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                view === "cards" ? "bg-primary text-primary-foreground border-primary" : "border-border bg-card"
              }`}
            >
              Cards ▦
            </button>
          </div>

          {view === "timeline" ? (
            <ExecutionTimeline stages={pipelineTrace} runId={runId} />
          ) : (
            <div className="space-y-2">
              {pipelineTrace.map((stage) => (
                <StageCard key={stage.stage_number} stage={stage} />
              ))}
            </div>
          )}

          <div className="border rounded-xl bg-card shadow-sm p-6 space-y-4">
            <h2 className="text-lg font-bold">Result</h2>
            <p>{sampleResult.answer}</p>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-semibold">
                {sampleResult.groundedness}
              </span>
              <span className="text-muted-foreground text-xs">Quality: {sampleResult.qualityScore}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 text-xs font-semibold">
                {sampleResult.outcome}
              </span>
            </div>

            <div className="space-y-2">
              {sampleCitations === null ? (
                <p className="text-sm text-muted-foreground">Citation data unavailable in Mode A</p>
              ) : (
                sampleCitations.map((citation) => <CitationCard key={citation.sourceDocId} citation={citation} />)
              )}
            </div>

            <ObservationRecord
              correlationId={sampleResult.correlationId}
              outcome={sampleResult.observationOutcome}
              duration={sampleResult.durationSeconds}
            />

            <div className="flex items-center gap-4 text-sm pt-2 border-t">
              <button
                onClick={() => setPlannerExpanded((e) => !e)}
                aria-expanded={plannerExpanded}
                className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
              >
                Inspect Planner →
              </button>
              <a
                href="/observability"
                className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
              >
                View in Observability →
              </a>
            </div>

            {plannerExpanded && <PlannerStateCard />}
          </div>
        </div>
      </div>
    </div>
  )
}
