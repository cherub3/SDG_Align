export interface StageTimelineItem {
  stage_number: number
  stage_name: string
  elapsed_ms: number
  // "incomplete" is Mode A-only: a step whose backend status was neither COMPLETED nor FAILED
  // (e.g. a plan truncated by STEP_LIMIT_REACHED) — not a real failure, and not the same concept
  // as "cache_miss" (unrelated backend semantics). See Track B Phase 7 plan, Finding 2 fix 4a.
  status: "completed" | "failed" | "cache_miss" | "incomplete"
  summary_line: string
}

export const pipelineTrace: StageTimelineItem[] = [
  { stage_number: 10, stage_name: "Retrieval", elapsed_ms: 38, status: "completed", summary_line: "3 chunks retrieved" },
  { stage_number: 11, stage_name: "Context", elapsed_ms: 12, status: "completed", summary_line: "1,842 tokens assembled" },
  { stage_number: 12, stage_name: "Prompt", elapsed_ms: 8, status: "completed", summary_line: "prompt fingerprint shown" },
  { stage_number: 17, stage_name: "Cache", elapsed_ms: 2, status: "cache_miss", summary_line: "MISS → proceeds to LLM" },
  { stage_number: 13, stage_name: "LLM", elapsed_ms: 842, status: "completed", summary_line: "gemini-2.0 · 412 tokens · finish_reason: complete" },
  { stage_number: 14, stage_name: "Citations", elapsed_ms: 14, status: "completed", summary_line: "2 citations matched" },
  { stage_number: 15, stage_name: "Groundedness", elapsed_ms: 11, status: "completed", summary_line: "GROUNDED" },
  { stage_number: 16, stage_name: "Quality", elapsed_ms: 9, status: "completed", summary_line: "score: 0.87" },
  { stage_number: 18, stage_name: "APIResponse", elapsed_ms: 18, status: "completed", summary_line: "SUCCESS" },
  { stage_number: 19, stage_name: "Memory", elapsed_ms: 5, status: "completed", summary_line: "1 turn appended" },
  { stage_number: 20, stage_name: "Tools", elapsed_ms: 3, status: "completed", summary_line: "no tool invoked" },
  { stage_number: 21, stage_name: "Planner", elapsed_ms: 22, status: "completed", summary_line: "COMPLETED" },
]

export const pipelineTraceTotalMs = pipelineTrace.reduce((sum, s) => sum + s.elapsed_ms, 0)

export const dominantStage = pipelineTrace.reduce((max, s) => (s.elapsed_ms > max.elapsed_ms ? s : max), pipelineTrace[0])

export const dominantStagePercent = Math.round((dominantStage.elapsed_ms / pipelineTraceTotalMs) * 100)

export const sampleQuery = "What financing gaps exist in climate proposals?"

export interface Citation {
  chunkText: string
  sourceDocTitle: string
  sourceDocId: string
  retrievalRank: number
  similarityScore: number
}

// Illustrative content, consistent with this dataset's existing illustrative convention
// (§0 "Illustrative vs. canonical values") — no canonical citation text is named anywhere
// in the frozen documents.
export const sampleCitations: Citation[] = [
  {
    chunkText:
      "…the reviewed proposals collectively identify a $4.2B shortfall between requested and committed climate financing across the sampled corpus…",
    sourceDocTitle: "Climate Finance Proposal — Annex B",
    sourceDocId: "doc-04",
    retrievalRank: 1,
    similarityScore: 0.91,
  },
  {
    chunkText:
      "…mitigation-track funding requests exceed adaptation-track requests by a ratio of roughly 3:1 in the current cycle…",
    sourceDocTitle: "Regional Adaptation Funding Summary",
    sourceDocId: "doc-07",
    retrievalRank: 2,
    similarityScore: 0.86,
  },
]

export const sampleResult = {
  answer: "Climate proposals show a $4.2B financing gap…",
  citationCount: 2,
  groundedness: "GROUNDED" as const,
  qualityScore: 0.87,
  outcome: "SUCCESS" as const,
  correlationId: "abc-123",
  durationSeconds: 0.984,
  observationOutcome: "completed" as const,
}

export interface ObservationRecordItem {
  correlationId: string
  outcome: "completed" | "failed"
  duration: number
  // null only ever occurs for Mode A: the backend's GET /observation-records has no timestamp
  // field (Track B Phase 7 plan, Finding 3). Modes B/C always provide a real ISO string.
  timestamp: string | null
}

// Illustrative — first entry restates sampleResult's own record (same query/request, not a
// duplicate value); remaining entries are additional illustrative session records, per the
// "extend existing datasets" Dataset Rule (never a second, parallel ObservationRecord source).
export const sampleObservationRecords: ObservationRecordItem[] = [
  { correlationId: sampleResult.correlationId, outcome: sampleResult.observationOutcome, duration: sampleResult.durationSeconds, timestamp: "2026-07-23T14:02:11Z" },
  { correlationId: "def-456", outcome: "completed", duration: 0.921, timestamp: "2026-07-23T13:58:47Z" },
  { correlationId: "ghi-789", outcome: "failed", duration: 0.123, timestamp: "2026-07-23T13:55:02Z" },
  { correlationId: "jkl-012", outcome: "completed", duration: 1.042, timestamp: "2026-07-23T13:51:30Z" },
  { correlationId: "mno-345", outcome: "completed", duration: 0.877, timestamp: "2026-07-23T13:47:18Z" },
  { correlationId: "pqr-678", outcome: "completed", duration: 0.965, timestamp: "2026-07-23T13:43:09Z" },
  { correlationId: "stu-901", outcome: "failed", duration: 0.201, timestamp: "2026-07-23T13:39:52Z" },
  { correlationId: "vwx-234", outcome: "completed", duration: 0.899, timestamp: "2026-07-23T13:36:14Z" },
  { correlationId: "yza-567", outcome: "completed", duration: 1.108, timestamp: "2026-07-23T13:32:41Z" },
  { correlationId: "bcd-890", outcome: "completed", duration: 0.933, timestamp: "2026-07-23T13:29:05Z" },
]

export interface StageMetadataItem {
  stage_number: number
  abbreviation: string
  name: string
  lane: "Ingestion" | "RAG" | "Agent"
}

export const stageMetadata: StageMetadataItem[] = [
  { stage_number: 0, abbreviation: "PDF", name: "PDF Ingestion", lane: "Ingestion" },
  { stage_number: 1, abbreviation: "Reg", name: "Registration", lane: "Ingestion" },
  { stage_number: 2, abbreviation: "Int", name: "Integrity Check", lane: "Ingestion" },
  { stage_number: 3, abbreviation: "Ext", name: "Extraction", lane: "Ingestion" },
  { stage_number: 4, abbreviation: "Det", name: "Detection", lane: "Ingestion" },
  { stage_number: 5, abbreviation: "Cln", name: "Cleaning", lane: "Ingestion" },
  { stage_number: 6, abbreviation: "Str", name: "Structuring", lane: "Ingestion" },
  { stage_number: 7, abbreviation: "Val", name: "Validation", lane: "Ingestion" },
  { stage_number: 8, abbreviation: "Emb", name: "Embedding Generation", lane: "Ingestion" },
  { stage_number: 9, abbreviation: "Idx", name: "Indexing", lane: "Ingestion" },
  { stage_number: 10, abbreviation: "Ret", name: "Retrieval", lane: "RAG" },
  { stage_number: 11, abbreviation: "Ctx", name: "Context Assembly", lane: "RAG" },
  { stage_number: 12, abbreviation: "Pmt", name: "Prompt Assembly", lane: "RAG" },
  { stage_number: 17, abbreviation: "Cch", name: "Cache Check", lane: "RAG" },
  { stage_number: 13, abbreviation: "LLM", name: "LLM Execution", lane: "RAG" },
  { stage_number: 14, abbreviation: "Cit", name: "Citation Extraction", lane: "RAG" },
  { stage_number: 15, abbreviation: "Grd", name: "Groundedness Validation", lane: "RAG" },
  { stage_number: 16, abbreviation: "Qty", name: "Quality Evaluation", lane: "RAG" },
  { stage_number: 18, abbreviation: "API", name: "API Response", lane: "RAG" },
  { stage_number: 19, abbreviation: "Mem", name: "Memory", lane: "Agent" },
  { stage_number: 20, abbreviation: "Tool", name: "Tool Execution", lane: "Agent" },
  { stage_number: 21, abbreviation: "Plan", name: "Agent Planning", lane: "Agent" },
]
