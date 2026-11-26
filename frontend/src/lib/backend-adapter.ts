import { documentTitle } from "../content/corpus-documents"
import type { StageTimelineItem, Citation, ObservationRecordItem } from "../content/demo-data/pipeline-trace"

/**
 * The backend adapter seam (React Frontend Architecture §7: "UI components must never call
 * APIs directly... backend ownership belongs exclusively to the adapter layer"). Pages call
 * only this interface — never a demo-data import or a network client directly.
 */
export interface QueryResult {
  stages: StageTimelineItem[]
  answer: string
  // null means "citation metadata not exposed by this backend" (Mode A only — Track B Phase 7
  // plan, Finding 2). [] means the backend genuinely returned zero citations. Never conflate
  // the two: components must render a distinct message for null, not the "no citations" empty
  // state.
  citationCount: number | null
  citations: Citation[] | null
  groundedness: string
  qualityScore: number
  outcome: string
  // null means no per-query correlation/timing data exists for this call (Mode A only —
  // Finding 3). Never defaulted to "" / 0.
  correlationId: string | null
  // ISO 8601 UTC time of that request's observation record, or null if it could not be looked up.
  timestamp: string | null
  durationSeconds: number | null
  // "unavailable" is Mode A-only: no per-query outcome signal exists to distinguish
  // completed/failed at the observation layer for a specific call (Finding 3).
  observationOutcome: "completed" | "failed" | "unavailable"
  // true: the backend has no LLM configured (or the request was retrieval only), so there is no generated answer.
  retrievalOnly: boolean
  // One line the page shows next to the result (retrieval-only explanation), or null.
  note: string | null
  // True when the top retrieved chunk's dense similarity is below LOW_RELEVANCE_DENSE_THRESHOLD; null when the backend sent no dense score.
  lowRelevance?: boolean | null
  // Set only when the optional multi-agent path (ADK) produced this result.
  agents?: AgentsInfo | null
}

export interface AgentStep {
  agent: string
  kind: "model" | "tool"
  name?: string
  ms: number
  tokensIn?: number
  tokensOut?: number
  hits?: number
  refused?: boolean
}

export interface AgentsInfo {
  agentsUsed: string[]
  steps: AgentStep[]
  calls: number
  toolCalls: number
  tokens: { in: number; out: number; thought: number }
  queries: string[]
  revisionCount: number
  verdict: string | null
  capHit: string | null
  wallMs: number
}

export interface BackendCapabilities {
  llmConfigured: boolean
  retrievalAvailable: boolean
  // The backend's query length limit (MAX_QUERY_CHARS); null when the backend does not report it.
  maxQueryChars: number | null
  // The server was started with AGENTS_ENABLED=true, so the optional multi-agent path can be requested.
  agentsAvailable: boolean
}

// The backend's default limit (DEFAULT_MAX_QUERY_CHARS in scripts/backend_server.py), used only if /capabilities is missing.
export const DEFAULT_MAX_QUERY_CHARS = 4000

export interface BackendAdapter {
  runQuery(query: string, options?: { useAgents?: boolean }): Promise<QueryResult>
  getObservationRecords(): Promise<ObservationRecordItem[]>
  getCapabilities(): Promise<BackendCapabilities | null>
}

/**
 * The three failure categories approved by Version 1.3 Decision 6: unreachable, timeout,
 * execution failure. Thrown only by LiveBackendAdapter.
 */
export class LiveBackendError extends Error {
  readonly category: "unreachable" | "timeout" | "execution_failure"

  constructor(category: "unreachable" | "timeout" | "execution_failure", message: string) {
    super(message)
    this.name = "LiveBackendError"
    this.category = category
  }
}

export const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://localhost:8000"

type RawStep = {
  step_index: number
  step_type: string
  step_status: string
  step_rationale?: string
  started_at: string | null
  completed_at: string | null
}

type RawAgentResult = {
  status: string
  plan: { steps: RawStep[] }
  correlation_id?: string
  final_response: {
    answer: { response_text: string }
    groundedness: { groundedness_score: number }
    quality: { answer_quality_score: number }
  } | null
}

type RawChunk = {
  chunk_id: string
  doc_id: string
  text: string
  score: number
  dense_score?: number
  heading_path?: string[]
  page_start?: number
  page_end?: number
  title?: string
}

type RawAgentsResult = {
  status: string
  correlation_id?: string
  final_response: { answer: { response_text: string } }
  chunks: RawChunk[]
  agents: {
    agents_used: string[]
    steps: { agent: string; kind: "model" | "tool"; name?: string; ms: number; tokens_in?: number; tokens_out?: number; hits?: number; refused?: boolean }[]
    calls: number
    tool_calls: number
    tokens: { in: number; out: number; thought: number }
    queries: string[]
    revision_count: number
    verdict: string | null
    cap_hit: string | null
    wall_ms: number
  }
}

type RawRetrievalOnly = { retrieval_only: true; correlation_id?: string; status?: string; chunks: RawChunk[]; findings?: { code?: string }[] }

type RawObservationRecord = {
  correlation_id: string
  outcome: "completed" | "failed"
  duration: number
  timestamp?: string
}

function mapStageStatus(stepStatus: string): StageTimelineItem["status"] {
  if (stepStatus === "COMPLETED") return "completed"
  if (stepStatus === "FAILED") return "failed"
  // Neither COMPLETED nor FAILED (e.g. PENDING/EXECUTING surviving a STEP_LIMIT_REACHED plan) —
  // genuinely unknown/incomplete, never "failed" and never "cache_miss" (unrelated backend
  // semantics). See Track B Phase 7 plan, Finding 2 fix 4a.
  return "incomplete"
}

/**
 * Display-only threshold for the "low relevance" note (never a refusal). Source: eval/results/3d_abstention.json, rule fixed
 * before it was computed: the largest dense cosine threshold at which at most 1 of the 12 DEV answerable items falls below it
 * (0.6604). On TEST that value flagged 5 of 44 answerable and 4 of 8 unanswerable questions, so it is a weak signal.
 */
export const LOW_RELEVANCE_DENSE_THRESHOLD = 0.6604

export function isLowRelevance(topDenseScore: number | undefined): boolean | null {
  return typeof topDenseScore === "number" ? topDenseScore < LOW_RELEVANCE_DENSE_THRESHOLD : null
}

export function verbatimOverlapLabel(score: number): string {
  return `Verbatim overlap: ${Math.round(score * 100)}% of sentences (strict; paraphrase scores 0)`
}

function elapsedMs(startedAt: string | null, completedAt: string | null): number {
  if (!startedAt || !completedAt) return 0
  const elapsed = new Date(completedAt).getTime() - new Date(startedAt).getTime()
  return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : 0
}

function mapAgentResultToQueryResult(raw: RawAgentResult): QueryResult {
  return {
    stages: raw.plan.steps.map((step) => ({
      stage_number: step.step_index,
      stage_name: step.step_type,
      elapsed_ms: elapsedMs(step.started_at, step.completed_at),
      status: mapStageStatus(step.step_status),
      summary_line: step.step_rationale?.trim() || `raw step_status: ${step.step_status}`,
    })),
    answer: raw.final_response?.answer.response_text ?? "",
    qualityScore: raw.final_response?.quality.answer_quality_score ?? 0,
    // Stage 15's groundedness_score is the share of answer sentences that are at least 80% a verbatim copy of a
    // retrieved chunk. A correct paraphrase scores 0, so it is labelled as what it measures, not as "groundedness".
    groundedness: raw.final_response ? verbatimOverlapLabel(raw.final_response.groundedness.groundedness_score) : "",
    outcome: raw.status,
    // Finding 2: citation metadata is not exposed by AgentResult at all — null, not [].
    citations: null,
    citationCount: null,
    correlationId: raw.correlation_id ?? null,
    timestamp: null,
    durationSeconds: null,
    observationOutcome: "unavailable",
    retrievalOnly: false,
    note: null,
  }
}

function chunkToCitation(c: RawChunk, rank: number): Citation {
  const heading = (c.heading_path ?? []).filter(Boolean).join(" > ") || c.title || ""
  const p0 = c.page_start ?? 0
  const p1 = c.page_end ?? p0
  return {
    chunkText: c.text,
    sourceDocTitle: documentTitle(c.doc_id),
    sourceDocId: c.chunk_id,
    retrievalRank: rank,
    similarityScore: c.score,
    section: heading || undefined,
    pages: p0 ? (p1 && p1 !== p0 ? `${p0}-${p1}` : `${p0}`) : undefined,
  }
}

/** One readable line from a 422 body: either {category, message} or FastAPI's {detail: [{msg}]}. */
async function rejectionReason(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { message?: string; detail?: { message?: string }[] | string }
    const raw = body.message ?? (Array.isArray(body.detail) ? body.detail[0]?.message : body.detail)
    if (raw) return String(raw).replace(/^Value error, /, "")
  } catch {
    /* fall through */
  }
  return "the query is not valid."
}

async function liveFetch(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${BACKEND_URL}${path}`, init)
  } catch {
    throw new LiveBackendError("unreachable", `Could not reach the backend at ${BACKEND_URL}${path}.`)
  }
  if (response.status === 504) {
    throw new LiveBackendError("timeout", "The backend timed out processing this request.")
  }
  if (response.status === 422) {
    throw new LiveBackendError("execution_failure", `The backend rejected the query: ${await rejectionReason(response)}`)
  }
  if (response.status === 500) {
    throw new LiveBackendError("execution_failure", "The backend failed to execute this request.")
  }
  if (!response.ok) {
    throw new LiveBackendError("execution_failure", `The backend returned an error (HTTP ${response.status}).`)
  }
  return response
}

/** Live probe for the home page's health panel: /health plus /capabilities. null means the backend did not answer. */
export async function probeBackend(): Promise<{ healthy: boolean; capabilities: BackendCapabilities | null } | null> {
  try {
    const health = await fetch(`${BACKEND_URL}/health`)
    if (!health.ok) return null
    return { healthy: true, capabilities: await liveBackendAdapter.getCapabilities() }
  } catch {
    return null
  }
}

class LiveBackendAdapter implements BackendAdapter {
  async getCapabilities(): Promise<BackendCapabilities | null> {
    try {
      const response = await fetch(`${BACKEND_URL}/capabilities`)
      if (!response.ok) return null   // an older backend without /capabilities: unknown, not "no LLM"
      const raw = (await response.json()) as { llm_configured: boolean; retrieval_available: boolean; max_query_chars?: number; agents_available?: boolean }
      return {
        llmConfigured: raw.llm_configured,
        retrievalAvailable: raw.retrieval_available,
        maxQueryChars: raw.max_query_chars ?? null,
        agentsAvailable: raw.agents_available ?? false,
      }
    } catch {
      return null
    }
  }

  /** The backend's own timestamp for a request, looked up in /observation-records by correlation id. */
  private async timestampFor(correlationId: string | undefined): Promise<string | null> {
    if (!correlationId) return null
    try {
      const records = await this.getObservationRecords()
      return records.find((r) => r.correlationId === correlationId)?.timestamp ?? null
    } catch {
      return null
    }
  }

  /** The optional multi-agent path (ADK). One call to /run-query with use_agents; several model calls on the backend. */
  private async runAgentsQuery(query: string, started: number): Promise<QueryResult> {
    const raw = (await (
      await liveFetch("/run-query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, use_agents: true }),
      })
    ).json()) as RawAgentsResult
    const a = raw.agents
    const citations = raw.chunks.map((c, i) => chunkToCitation(c, i + 1))
    return {
      stages: a.steps.map((s, i) => ({
        stage_number: i + 1,
        stage_name: s.kind === "tool" ? s.agent + ": " + (s.name ?? "tool") : s.agent + ": model call",
        elapsed_ms: Math.round(s.ms),
        status: s.refused ? "failed" : "completed",
        summary_line: s.kind === "tool" ? (s.hits ?? 0) + " hits" : (s.tokens_in ?? 0) + " tokens in, " + (s.tokens_out ?? 0) + " out",
      })),
      answer: raw.final_response.answer.response_text,
      citations,
      citationCount: citations.length,
      groundedness: "",
      qualityScore: 0,
      outcome: raw.status,
      correlationId: raw.correlation_id ?? null,
      timestamp: await this.timestampFor(raw.correlation_id),
      durationSeconds: Math.round(performance.now() - started) / 1000,
      observationOutcome: raw.status === "PASS" ? "completed" : "failed",
      retrievalOnly: false,
      note: "Multi-agent mode (optional). The chunks listed are the context the answer agent was given, from up to two searches. The strict verbatim-overlap score is not computed in this mode.",
      lowRelevance: null,
      agents: {
        agentsUsed: a.agents_used,
        steps: a.steps.map((s) => ({ agent: s.agent, kind: s.kind, name: s.name, ms: s.ms, tokensIn: s.tokens_in, tokensOut: s.tokens_out, hits: s.hits, refused: s.refused })),
        calls: a.calls,
        toolCalls: a.tool_calls,
        tokens: a.tokens,
        queries: a.queries,
        revisionCount: a.revision_count,
        verdict: a.verdict,
        capHit: a.cap_hit,
        wallMs: a.wall_ms,
      },
    }
  }

  async runQuery(query: string, options?: { useAgents?: boolean }): Promise<QueryResult> {
    const started = performance.now()
    if (options?.useAgents) return this.runAgentsQuery(query, started)
    const caps = await this.getCapabilities()
    // 1. Retrieved chunks: always, and the only thing available when no LLM is configured. No LLM call.
    const retrieved = (await (
      await liveFetch("/run-query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, retrieval_only: true }),
      })
    ).json()) as RawRetrievalOnly
    const retrievalMs = Math.round(performance.now() - started)
    const citations = retrieved.chunks.map((c, i) => chunkToCitation(c, i + 1))
    const retrievalStage: StageTimelineItem = {
      stage_number: 10,
      stage_name: "Retrieval",
      elapsed_ms: retrievalMs,
      status: "completed",
      summary_line: `${citations.length} chunks retrieved (client-measured, includes network)`,
    }
    const base = { citations, citationCount: citations.length, lowRelevance: isLowRelevance(retrieved.chunks[0]?.dense_score) }
    if (caps !== null && !caps.llmConfigured) {
      return {
        ...base,
        stages: [retrievalStage],
        answer: "",
        groundedness: "",
        qualityScore: 0,
        outcome: "RETRIEVAL_ONLY",
        correlationId: retrieved.correlation_id ?? null,
        timestamp: await this.timestampFor(retrieved.correlation_id),
        durationSeconds: Math.round(retrievalMs) / 1000,
        observationOutcome: "completed",
        retrievalOnly: true,
        note: "Retrieval only: no LLM configured. These are the chunks the pipeline retrieved; no answer was generated.",
      }
    }
    // 2. Full question answering (one LLM call, counted against the backend's daily cap).
    const raw = (await (
      await liveFetch("/run-query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      })
    ).json()) as RawAgentResult
    const mapped = mapAgentResultToQueryResult(raw)
    return {
      ...mapped,
      ...base,
      stages: [retrievalStage, ...mapped.stages],
      timestamp: await this.timestampFor(raw.correlation_id),
      durationSeconds: Math.round(performance.now() - started) / 1000,
      observationOutcome: raw.status === "PASS" ? "completed" : "failed",
      retrievalOnly: false,
      note:
        "The chunks listed are the retrieved context (top results); the backend does not report which sentences of the answer cite which chunk.",
    }
  }

  async getObservationRecords(): Promise<ObservationRecordItem[]> {
    const response = await liveFetch("/observation-records")
    const raw = (await response.json()) as RawObservationRecord[]
    return raw.map((r) => ({
      correlationId: r.correlation_id,
      outcome: r.outcome,
      duration: r.duration,
      // From the backend; null only for a backend too old to send it. Never a client-clock value.
      timestamp: r.timestamp ?? null,
    }))
  }
}

const liveBackendAdapter = new LiveBackendAdapter()

/** Pages call this: there is only the live adapter. When the backend is down the pages show an offline message. */
export function useBackendAdapter(): BackendAdapter {
  return liveBackendAdapter
}
