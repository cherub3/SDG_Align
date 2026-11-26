import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { NarrativeBlock } from "../components/shared/narrative-block"
import { ExecutionTimeline } from "../components/visualization/execution-timeline"
import { StageCard } from "../components/page/pipeline-explorer/stage-card"
import { CitationCard } from "../components/page/pipeline-explorer/citation-card"
import { ObservationRecord } from "../components/shared/observation-record"
import { BackendOfflineNotice } from "../components/shared/backend-offline-notice"
import { DEFAULT_MAX_QUERY_CHARS, LOW_RELEVANCE_DENSE_THRESHOLD, useBackendAdapter } from "../lib/backend-adapter"
import type { QueryResult } from "../lib/backend-adapter"
import { INDEXED_DOCUMENT_COUNT } from "../content/corpus-documents"
import { useOperatingMode } from "../providers/operating-mode-provider"

const DEFAULT_QUERY = "What are the main objectives of the project?"

type View = "timeline" | "cards"

export function PipelineExplorerPage() {
  const adapter = useBackendAdapter()
  const { backendStatus } = useOperatingMode()
  const [searchParams, setSearchParams] = useSearchParams()
  const view: View = searchParams.get("view") === "cards" ? "cards" : "timeline"
  const [runId, setRunId] = useState(0)
  const [queryText, setQueryText] = useState(DEFAULT_QUERY)
  const [maxChars, setMaxChars] = useState(DEFAULT_MAX_QUERY_CHARS)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [submitted, setSubmitted] = useState("")
  const [agentsAvailable, setAgentsAvailable] = useState(false)
  const [useAgents, setUseAgents] = useState(false) // off by default: the multi-agent path makes several model calls per question
  const [submittedAgents, setSubmittedAgents] = useState(false)
  const online = backendStatus === "live"

  // The backend reports its own query length limit (MAX_QUERY_CHARS).
  useEffect(() => {
    if (!online) return
    adapter.getCapabilities().then((c) => {
      if (c?.maxQueryChars) setMaxChars(c.maxQueryChars)
      setAgentsAvailable(c?.agentsAvailable ?? false)
    })
  }, [adapter, online])

  // Runs only on the button (runId > 0): a run can spend an LLM call, so nothing runs on page load.
  useEffect(() => {
    if (runId === 0) return
    let cancelled = false
    setResult(null) // old results never stay on screen under a new query
    setError(null)
    setRunning(true)
    adapter
      .runQuery(submitted, { useAgents: submittedAgents })
      .then((r) => {
        if (!cancelled) setResult(r)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setRunning(false)
      })
    return () => {
      cancelled = true
    }
  }, [adapter, runId, submitted, submittedAgents])

  const setView = (next: View) => {
    const params = new URLSearchParams(searchParams)
    params.set("view", next)
    setSearchParams(params, { replace: true })
  }

  const runQuery = () => {
    setSubmitted(queryText)
    setSubmittedAgents(agentsAvailable && useAgents)
    setRunId((id) => id + 1)
  }

  const citations = result?.citations ?? null

  return (
    <div className="max-w-7xl mx-auto px-4 py-12">
      <h1 className="sr-only">Pipeline Explorer</h1>

      <NarrativeBlock
        headline="Ask a question about the indexed proposals and see what the pipeline retrieves."
        body="Shows the retrieved chunks with their document, section and page, and the generated answer when an LLM is configured on the backend."
      />

      {!online ? (
        <div className="mt-8">
          <BackendOfflineNotice waking={backendStatus === "checking" || backendStatus === "waking"} />
        </div>
      ) : (
        <div className="flex flex-col md:flex-row gap-10 mt-8">
          <aside className="md:w-72 shrink-0 space-y-4">
            <div>
              <label htmlFor="query-input" className="block text-sm font-medium mb-1">
                Query
              </label>
              <textarea
                id="query-input"
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                maxLength={maxChars}
                rows={3}
                className="w-full rounded-md border border-border bg-card p-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <p className="text-xs text-muted-foreground text-right" aria-live="polite">
                {queryText.length} / {maxChars}
              </p>
            </div>
            <p className="text-sm text-muted-foreground">Searching all {INDEXED_DOCUMENT_COUNT} documents</p>
            {agentsAvailable && (
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={useAgents} onChange={(e) => setUseAgents(e.target.checked)} className="mt-1" />
                <span>
                  Multi-agent mode (optional, ADK)
                  <span className="block text-xs text-muted-foreground">
                    Retriever, answer and verifier agents. Uses about 4 model calls per question instead of 1.
                  </span>
                </span>
              </label>
            )}
            <button
              onClick={runQuery}
              disabled={running || queryText.trim() === ""}
              className="w-full px-4 py-2 bg-primary text-primary-foreground font-medium rounded-md hover:bg-primary/90 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {running ? "Running…" : "Run Query ▶"}
            </button>
          </aside>

          <div className="flex-1 min-w-0 space-y-6">
            {error && (
              <div role="alert" className="text-sm text-destructive border border-destructive/30 rounded-lg p-4">
                {error}
              </div>
            )}
            {!result && !error && (
              <p className="text-sm text-muted-foreground">
                {running ? "Running…" : "Press Run Query to ask the backend. A run with an LLM configured uses one LLM call."}
              </p>
            )}

            {result && (
              <>
                <div className="flex items-center gap-2" role="group" aria-label="View">
                  {(["timeline", "cards"] as const).map((v) => (
                    <button
                      key={v}
                      onClick={() => setView(v)}
                      aria-pressed={view === v}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        view === v ? "bg-primary text-primary-foreground border-primary" : "border-border bg-card"
                      }`}
                    >
                      {v === "timeline" ? "Timeline ▤" : "Cards ▦"}
                    </button>
                  ))}
                </div>

                {view === "timeline" ? (
                  <ExecutionTimeline stages={result.stages} runId={runId} />
                ) : (
                  <div className="space-y-2">
                    {result.stages.map((stage) => (
                      <StageCard key={stage.stage_number} stage={stage} />
                    ))}
                  </div>
                )}

                <div className="border rounded-xl bg-card shadow-sm p-6 space-y-4">
                  <h2 className="text-lg font-bold">Result</h2>
                  {result.note && (
                    <p className="text-sm rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2">{result.note}</p>
                  )}
                  {!result.retrievalOnly && <p>{result.answer}</p>}
                  {result.agents && (
                    <div role="group" aria-label="Multi-agent run" className="rounded-md border border-border p-3 text-sm space-y-2">
                      <p>
                        <span className="font-semibold">Agents:</span> {result.agents.agentsUsed.join(", ")}.{" "}
                        <span className="font-semibold">Model calls:</span> {result.agents.calls}.{" "}
                        <span className="font-semibold">Searches:</span> {result.agents.toolCalls}.{" "}
                        <span className="font-semibold">Tokens:</span> {result.agents.tokens.in} in, {result.agents.tokens.out} out.{" "}
                        <span className="font-semibold">Verifier:</span> {result.agents.verdict ?? "not run"}
                        {result.agents.revisionCount > 0 ? ", answer revised once" : ""}.
                        {result.agents.capHit ? " Cap hit: " + result.agents.capHit + ", so the answer is NOT_IN_CONTEXT." : ""}
                      </p>
                      {result.agents.queries.length > 0 && (
                        <p className="text-muted-foreground">Searches made: {result.agents.queries.map((q) => '"' + q + '"').join(" then ")}</p>
                      )}
                    </div>
                  )}
                  {!result.retrievalOnly && (
                    <div className="flex flex-wrap items-center gap-3 text-sm">
                      {result.groundedness && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-semibold">
                          {result.groundedness}
                        </span>
                      )}
                      <span
                        className="text-muted-foreground text-xs"
                        title="0.7 x verbatim overlap + 0.3 x citation presence. Strict: a correct paraphrase scores low."
                      >
                        Strict quality score: {result.qualityScore}
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-semibold">
                        {result.outcome}
                      </span>
                    </div>
                  )}

                  {result.lowRelevance && (
                    <p role="note" className="text-sm rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2">
                      Low relevance: the best retrieved chunk scores below {LOW_RELEVANCE_DENSE_THRESHOLD} on dense similarity, so the
                      documents may not contain this. This is a display note, not a refusal. On the TEST split this threshold flagged
                      4 of 8 unanswerable and 5 of 44 answerable questions, so treat it as a weak signal.
                    </p>
                  )}

                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold">
                      {citations === null ? "Retrieved chunks" : `Retrieved chunks (${citations.length})`}
                    </h3>
                    {citations === null ? (
                      <p className="text-sm text-muted-foreground">No chunk data returned.</p>
                    ) : (
                      citations.map((citation) => (
                        <CitationCard key={citation.sourceDocId + citation.retrievalRank} citation={citation} />
                      ))
                    )}
                  </div>

                  <ObservationRecord
                    correlationId={result.correlationId}
                    outcome={result.observationOutcome}
                    duration={result.durationSeconds}
                    timestamp={result.timestamp}
                  />

                  <div className="flex items-center gap-4 text-sm pt-2 border-t">
                    <Link
                      to="/observability"
                      className="text-primary font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                    >
                      View in Observability →
                    </Link>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
