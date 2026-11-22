import { useOperatingMode } from "../providers/operating-mode-provider"
import {
  pipelineTrace,
  sampleQuery,
  sampleResult,
  sampleCitations,
  sampleObservationRecords,
  type StageTimelineItem,
  type Citation,
  type ObservationRecordItem,
} from "../content/demo-data/pipeline-trace"

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
  durationSeconds: number | null
  // "unavailable" is Mode A-only: no per-query outcome signal exists to distinguish
  // completed/failed at the observation layer for a specific call (Finding 3).
  observationOutcome: "completed" | "failed" | "unavailable"
}

export interface BackendAdapter {
  getSampleQuery(): Promise<string>
  runQuery(query: string): Promise<QueryResult>
  getObservationRecords(): Promise<ObservationRecordItem[]>
}

/**
 * The three failure categories approved by Version 1.3 Decision 6: unreachable, timeout,
 * execution failure. Thrown only by LiveBackendAdapter — SampleDataAdapter never throws.
 */
export class LiveBackendError extends Error {
  readonly category: "unreachable" | "timeout" | "execution_failure"

  constructor(category: "unreachable" | "timeout" | "execution_failure", message: string) {
    super(message)
    this.name = "LiveBackendError"
    this.category = category
  }
}

/**
 * Raised only by `getSampleQuery()` in Mode A. Version 1.3 Decision 4 resolved that
 * `getSampleQuery()` has no live equivalent — Mode A has no notion of "the sample query" once
 * real queries are being run — so this operation is intentionally unsupported there.
 */
export class LiveOperationUnsupportedError extends Error {
  constructor(operation: string) {
    super(`Mode A (Live) does not support "${operation}" — it has no live equivalent (Version 1.3 Decision 4).`)
    this.name = "LiveOperationUnsupportedError"
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
  final_response: {
    answer: { response_text: string }
    groundedness: { groundedness_score: number }
    quality: { answer_quality_score: number }
  } | null
}

type RawObservationRecord = {
  correlation_id: string
  outcome: "completed" | "failed"
  duration: number
}

function mapStageStatus(stepStatus: string): StageTimelineItem["status"] {
  if (stepStatus === "COMPLETED") return "completed"
  if (stepStatus === "FAILED") return "failed"
  // Neither COMPLETED nor FAILED (e.g. PENDING/EXECUTING surviving a STEP_LIMIT_REACHED plan) —
  // genuinely unknown/incomplete, never "failed" and never "cache_miss" (unrelated backend
  // semantics). See Track B Phase 7 plan, Finding 2 fix 4a.
  return "incomplete"
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
    // Temporarily a stringified numeric score, not a real qualitative label ("HIGH"/"Grounded")
    // — no such label exists anywhere in AgentResult. See Track B Phase 7 plan, section 4a.
    groundedness: raw.final_response ? String(raw.final_response.groundedness.groundedness_score) : "",
    outcome: raw.status,
    // Finding 2: citation metadata is not exposed by AgentResult at all — null, not [].
    citations: null,
    citationCount: null,
    // Finding 3: no per-query correlation/timing/outcome data reaches /run-query's response.
    correlationId: null,
    durationSeconds: null,
    observationOutcome: "unavailable",
  }
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
  if (response.status === 500) {
    throw new LiveBackendError("execution_failure", "The backend failed to execute this request.")
  }
  if (!response.ok) {
    throw new LiveBackendError("execution_failure", `Unexpected backend response: HTTP ${response.status}.`)
  }
  return response
}

class LiveBackendAdapter implements BackendAdapter {
  async getSampleQuery(): Promise<string> {
    throw new LiveOperationUnsupportedError("getSampleQuery")
  }

  async runQuery(query: string): Promise<QueryResult> {
    const response = await liveFetch("/run-query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    })
    const raw = (await response.json()) as RawAgentResult
    return mapAgentResultToQueryResult(raw)
  }

  async getObservationRecords(): Promise<ObservationRecordItem[]> {
    const response = await liveFetch("/observation-records")
    const raw = (await response.json()) as RawObservationRecord[]
    return raw.map((r) => ({
      correlationId: r.correlation_id,
      outcome: r.outcome,
      duration: r.duration,
      // Finding 3: the backend response has no timestamp field — null, never a fabricated
      // client-clock value presented as authoritative.
      timestamp: null,
    }))
  }
}

/**
 * Mode B (Recorded Demonstration) and Mode C (Static) render identically per Dashboard
 * Specification §10.5 ("the observer cannot tell the difference") — both are implemented by
 * this one adapter reading the same bundled dataset, never two parallel implementations.
 */
class SampleDataAdapter implements BackendAdapter {
  async getSampleQuery(): Promise<string> {
    return sampleQuery
  }

  async runQuery(): Promise<QueryResult> {
    return {
      stages: pipelineTrace,
      answer: sampleResult.answer,
      citationCount: sampleResult.citationCount,
      citations: sampleCitations,
      groundedness: sampleResult.groundedness,
      qualityScore: sampleResult.qualityScore,
      outcome: sampleResult.outcome,
      correlationId: sampleResult.correlationId,
      durationSeconds: sampleResult.durationSeconds,
      observationOutcome: sampleResult.observationOutcome,
    }
  }

  async getObservationRecords(): Promise<ObservationRecordItem[]> {
    return sampleObservationRecords
  }
}

const liveBackendAdapter = new LiveBackendAdapter()
const sampleDataAdapter = new SampleDataAdapter()

export type OperatingMode = "Mode A (Live)" | "Mode B (Recorded Demonstration)" | "Mode C (Static)"

export function getBackendAdapter(mode: OperatingMode): BackendAdapter {
  if (mode === "Mode A (Live)") return liveBackendAdapter
  return sampleDataAdapter
}

/** Pages call this — never `getBackendAdapter` or a demo-data import directly. */
export function useBackendAdapter(): BackendAdapter {
  const { mode } = useOperatingMode()
  return getBackendAdapter(mode)
}
