// Types shared by the live adapter and the pages, plus the static stage list. Nothing in this file is sample output:
// the earlier recorded-demonstration data (answer text, timings, scores, observation rows) was removed because it was invented.
export interface StageTimelineItem {
  stage_number: number
  stage_name: string
  elapsed_ms: number
  // "incomplete": a step whose backend status was neither COMPLETED nor FAILED (e.g. a plan truncated by STEP_LIMIT_REACHED).
  status: "completed" | "failed" | "cache_miss" | "incomplete"
  summary_line: string
}

export interface Citation {
  chunkText: string
  sourceDocTitle: string
  sourceDocId: string
  retrievalRank: number
  // Retrieval score of the chunk (hybrid BM25 + dense fusion in the live backend; not a cosine similarity).
  similarityScore: number
  // Heading path and page range of the chunk in its source document.
  section?: string
  pages?: string
}

export interface ObservationRecordItem {
  correlationId: string
  outcome: "completed" | "failed"
  duration: number
  // ISO 8601 UTC, written by the backend when the record was created.
  timestamp: string | null
}

export interface StageMetadataItem {
  stage_number: number
  abbreviation: string
  name: string
  lane: "Ingestion" | "RAG" | "Agent"
  role: string
}

export const stageMetadata: StageMetadataItem[] = [
  { stage_number: 0, abbreviation: "Reg", name: "Register", lane: "Ingestion", role: "Registers source documents in the manifest." },
  { stage_number: 1, abbreviation: "Int", name: "Integrity", lane: "Ingestion", role: "Checks that each PDF is readable." },
  { stage_number: 2, abbreviation: "Ext", name: "Extraction", lane: "Ingestion", role: "Extracts raw text and layout from each PDF." },
  { stage_number: 3, abbreviation: "Det", name: "Detection", lane: "Ingestion", role: "Detects scanned or empty pages and quarantines them." },
  { stage_number: 4, abbreviation: "Cln", name: "Cleaning", lane: "Ingestion", role: "Cleans and normalizes the extracted text." },
  { stage_number: 5, abbreviation: "Str", name: "Structure", lane: "Ingestion", role: "Tags headings and builds the section structure." },
  { stage_number: 6, abbreviation: "Val", name: "Validation", lane: "Ingestion", role: "Validates each document and assembles its metadata." },
  { stage_number: 7, abbreviation: "Chk", name: "Chunking", lane: "Ingestion", role: "Splits documents into semantic chunks." },
  { stage_number: 8, abbreviation: "Emb", name: "Embedding", lane: "Ingestion", role: "Generates an embedding for each chunk." },
  { stage_number: 9, abbreviation: "Idx", name: "Vector Indexing", lane: "Ingestion", role: "Builds and validates the searchable vector index." },
  { stage_number: 10, abbreviation: "Ret", name: "Retrieval", lane: "RAG", role: "Returns ranked relevant chunks for a query." },
  { stage_number: 11, abbreviation: "Ctx", name: "Context Assembly", lane: "RAG", role: "Builds a token-budgeted context package from the retrieved chunks." },
  { stage_number: 12, abbreviation: "Pmt", name: "Prompt Construction", lane: "RAG", role: "Renders the context and question into a deterministic prompt." },
  { stage_number: 17, abbreviation: "Cch", name: "Response Caching", lane: "RAG", role: "Wraps the LLM call with a deterministic cache." },
  { stage_number: 13, abbreviation: "LLM", name: "LLM Execution", lane: "RAG", role: "Sends the prompt to the LLM and returns its response." },
  { stage_number: 14, abbreviation: "Cit", name: "Citation Extraction", lane: "RAG", role: "Matches answer sentences to source chunks by n-gram overlap." },
  { stage_number: 15, abbreviation: "Grd", name: "Groundedness Validation", lane: "RAG", role: "Scores each cited sentence by its longest verbatim overlap with the source chunk." },
  { stage_number: 16, abbreviation: "Qty", name: "Answer Quality", lane: "RAG", role: "Combines groundedness and citation presence into a structural score." },
  { stage_number: 18, abbreviation: "API", name: "API / Response Serving", lane: "RAG", role: "Runs stages 10 to 17 and returns one API response." },
  { stage_number: 19, abbreviation: "Mem", name: "Conversation Memory", lane: "Agent", role: "Selects and stores multi-turn conversation state." },
  { stage_number: 20, abbreviation: "Tool", name: "Tool / Function Calling", lane: "Agent", role: "Invokes a single tool through a structured adapter." },
  { stage_number: 21, abbreviation: "Plan", name: "Agent Planning", lane: "Agent", role: "Plans and executes steps over stages 18 to 20." },
]
