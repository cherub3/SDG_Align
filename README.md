# SDG Align

A deterministic, auditable **Retrieval-Augmented Generation (RAG) + agent-orchestration pipeline**
for analysing development-project proposals against the UN Sustainable Development Goals (SDGs).

---

## Delivery status

**"SDG Align" is the product goal.** The full product vision — automatically aligning proposal
content to specific SDG targets, with grounded evidence and gap analysis — is described in
[`docs/ARCHITECTURE_BLUEPRINT.md`](docs/ARCHITECTURE_BLUEPRINT.md).

**This repository delivers Phase 1: the pipeline foundation** the product sits on — a frozen,
fully-tested **22-stage pipeline (Stages 0–21)** covering document ingestion, retrieval-augmented
generation, and agent orchestration. It is the deterministic, auditable substrate onto which the
goal-level alignment features are intended to be built.

| | Status |
|---|---|
| Stages 0–21 pipeline (ingestion → RAG → agent orchestration) | ✅ Implemented & frozen |
| Test suite | ✅ Passing (`python -m pytest`) |
| Ingestion (Stages 0–9) verified on a real 13-document corpus | ✅ |
| Query/agent stages (10–21) verified via unit tests over abstract adapters | ✅ |
| Track B backend (FastAPI) + frontend (React dashboard), Mode A (Live) | ✅ Implemented & verified — see [`DEPLOYMENT.md`](DEPLOYMENT.md) |
| SDG-target alignment product (extractor/verifier passes, evidence validator, gap analysis, UI) | ⛔ Goal — not yet built |

**Running the backend + frontend (Track B):** see [`DEPLOYMENT.md`](DEPLOYMENT.md) for setup,
[`OPERATIONAL_READINESS.md`](OPERATIONAL_READINESS.md) for the current validated status, and
[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for known failure modes (CORS, quota, retrieval).

The alignment-specific components named in the blueprint (LLM Pass 1/Pass 2, SDG-target retriever
over `data/sdg_targets.json`, evidence validator, gap analysis, Streamlit UI under `pages/`) are
**not yet implemented** — they are the next phase, not part of this delivery.

---

## Source corpus (not included)

The 13 proposal PDFs and every file derived from them (extracted text, chunks, embeddings, vector
indexes) are **not** in this repository: their redistribution licence has not been confirmed, and
`data/proposals/` is git-ignored. To reproduce the corpus, obtain the PDFs from their original
publisher, place them under `data/proposals/raw/<category>/`, and verify them with:

```bash
python scripts/download_corpus.py --check
```

(`scripts/download_corpus.py` is currently a stub: it lists the expected files with SHA-256 hashes
but has no download URLs configured.) Then rebuild with the stage CLIs below. The test suite does
not need any corpus data.

## Purpose

Development organisations receive large volumes of project proposals and must understand how each
relates to the 17 SDGs and their 169 targets. SDG Align's goal is to make that analysis fast,
consistent, and **evidence-backed** — every machine-made claim traceable to exact source text.

The engineering thesis of Phase 1 is **"deterministic before probabilistic"**: everything that can be
a fixed, recitable rule (validation, chunking, retrieval bookkeeping, caching, orchestration) is
plain, testable code with byte-identical output; the LLM is confined to the narrow steps where
judgment is genuinely required, behind explicit adapter contracts.

## High-level overview

```
                Ingestion (Stages 0–9)                    Query-time RAG (Stages 10–18)
   PDF ──► register ─► integrity ─► extract ─► clean      query ─► retrieve ─► assemble context
        ─► structure ─► validate ─► chunk ─► embed              ─► build prompt ─► LLM (cached)
        ─► vector index                                        ─► citations ─► groundedness ─► quality
                                                               ─► APIResponse (Stage 18)

                                  Agent layer (Stages 19–21)
        conversation memory (19)   ·   tool / function calling (20)   ·   agent planning (21)
```

Each stage is a **single-responsibility design unit** with a frozen public contract, an explicit
schema, deterministic output, and its own test file. Stages read only the artifacts they own; a
shared set of conventions is defined once in [`docs/pipeline_principles.md`](docs/pipeline_principles.md).

## Architecture overview

- **Ingestion (0–9)** are runnable command-line stages that transform raw PDFs into validated,
  chunked, embedded, and vector-indexed artifacts under `data/proposals/`.
- **Query-time RAG (10–18)** are library modules. Stage 18 (`handle_request`) orchestrates the fixed
  chain 10 → 11 → 12 → 17 → 14 → 15 → 16 into a single transport-agnostic `APIResponse`.
- **Agent layer (19–21)** adds multi-turn conversation memory, structured tool invocation, and a
  top-level planner (`plan_and_execute`) that coordinates Stages 18–20.
- **Adapter boundaries** (`LLMAdapter`, `CacheAdapter`, `ToolAdapter`, `ConversationStore`,
  `PlannerLLMAdapter`, `IndexAdapter`) keep concrete providers, SDKs, and external services out of the
  core. Phase 1 ships the abstract contracts and a faiss-backed index adapter; other concrete
  adapters (e.g. a real LLM provider) are supplied by the caller at wiring time.

### Complete stage summary (0–21)

| Stage | Name | Role |
|------:|------|------|
| 0 | Register | Register source documents into the manifest |
| 1 | Integrity | PDF integrity / readability check |
| 2 | Extraction | Text + layout extraction (PyMuPDF) |
| 3 | Detection | Scanned/empty-page detection & quarantine |
| 4 | Cleaning | Whitespace, de-hyphenation, encoding, header/footer removal |
| 5 | Structure | Heading detection, section tree, appendices/references |
| 6 | Validation | Document-level validation & metadata assembly |
| 7 | Chunking | Deterministic semantic chunking |
| 8 | Embedding | Chunk embedding generation |
| 9 | Vector Indexing | faiss index build + id map |
| 10 | Retrieval | Query embedding + top-k retrieval |
| 11 | Context Assembly | Ordered, budgeted context package |
| 12 | Prompt Construction | Deterministic prompt/template rendering |
| 13 | LLM Execution | LLM invocation via `LLMAdapter` (retry policy, latency) |
| 14 | Citation Extraction | Extract & match citations to source chunks |
| 15 | Groundedness Validation | Verify answer claims against context |
| 16 | Answer Quality Evaluation | Structural answer-quality scoring |
| 17 | Response Caching | Cache-wrapped LLM execution via `CacheAdapter` |
| 18 | API / Response Serving | Orchestrates 10–17 into one `APIResponse` |
| 19 | Conversation Memory | Multi-turn memory selection & lifecycle |
| 20 | Tool / Function Calling | Structured single-tool invocation via `ToolAdapter` |
| 21 | Agent Planning | Top-level planner coordinating Stages 18–20 |

Per-stage design docs live in [`docs/architecture/`](docs/architecture/).

## Directory structure

```
sdg-align/
├── README.md                     # this file
├── LICENSE                       # license placeholder (choose before public release)
├── requirements.txt              # Python dependencies
├── .gitignore
├── src/
│   └── ingestion_types.py        # shared types (ManifestRecord, DocumentStatus)
├── scripts/
│   ├── stage0_register.py … stage9_vector_indexing.py   # runnable ingestion CLIs
│   └── stage10_retrieval.py … stage21_agent_planning.py # query/agent library modules
├── tests/
│   └── test_stage0_… … test_stage21_…                   # one test file per stage
├── docs/
│   ├── ARCHITECTURE_BLUEPRINT.md # full product vision (north star)
│   ├── INGESTION_ARCHITECTURE.md # ingestion-phase design
│   ├── pipeline_principles.md    # shared conventions cited by every stage
│   ├── IMPLEMENTATION_LOG.md     # historical build log
│   ├── VERIFICATION_LOG.md       # historical real-corpus run log
│   ├── END_TO_END_EXAMPLE.md     # documented Stage 0 → 21 walkthrough
│   └── architecture/             # stage10–21 + stage4–9 design docs
├── data/
│   ├── un_sdg_raw.json           # raw UN SDG API response (provenance)
│   └── proposals/                # corpus + generated artifacts (see .gitignore)
├── eval/gold_set/                # (reserved — evaluation set, not yet populated)
├── pages/                        # (reserved — future Streamlit UI, not yet built)
├── frontend/                     # Track B: React/Vite dashboard (Modes A/B/C)
├── DEPLOYMENT.md                 # Track B backend+frontend setup/deployment
├── OPERATIONAL_READINESS.md      # current validated deployment status
└── TROUBLESHOOTING.md            # known failure modes and fixes
```

`scripts/backend_server.py` (Track B) is a FastAPI process exposing `POST /run-query` and
`GET /observation-records` over the Stage 0–21 pipeline — see [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Installation

**Requirements:** Python 3.11+ (developed and tested on CPython 3.14).

```bash
# 1. Clone
git clone <repository-url>
cd sdg-align

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Dependencies

| Package | Used by |
|---------|---------|
| `pymupdf`, `pymupdf4llm` | PDF extraction (Stages 1–2) |
| `pyarrow` | Parquet artifacts (embeddings, id maps) |
| `faiss-cpu` | Vector index (Stage 9) |
| `pytest` | Test suite |

No paid services or API keys are required to run the ingestion pipeline or the test suite. A concrete
`LLMAdapter`/`PlannerLLMAdapter` (e.g. for a real LLM provider like Gemini, Groq, or OpenRouter) is only needed when wiring the
real pipeline inside `scripts/pipeline_deps_factory.py` — the tests use in-memory adapters, so **no credentials are needed
to build or verify the project**.

Currently supported implementations:
- **Planner:** Gemini, Groq, OpenRouter
- **LLM:** Gemini, Groq, OpenRouter
- **Embeddings:** Gemini, Hugging Face

Recommended Configuration:
- **Planner:** OpenRouter
- **LLM:** OpenRouter
- **Embeddings:** Hugging Face

*Important:* If you switch embedding providers (e.g., from Gemini to Hugging Face), you MUST regenerate the FAISS index (Stages 8 and 9) because the generated vectors will have different dimensions and characteristics. Stage 10 will actively prevent mismatched dimensions.

### Configuration

Phase 1 has no required environment variables. Per-stage tunables (thresholds, budgets, ceilings) are
module-level constants documented in each stage's architecture doc and source file. When a real LLM
adapter is later wired in, its credentials are owned by that adapter and supplied at wiring time — the
pipeline core never reads them.

## Running the pipeline

The ingestion stages (0–9) are runnable modules that operate on `data/proposals/`. Run them in order:

```bash
python scripts/stage0_register.py          # register documents into the manifest
python scripts/stage1_integrity.py         # integrity check
python scripts/stage2_extraction.py        # extract text + layout
python scripts/stage3_detection.py         # detect scanned/empty pages
python scripts/stage4_cleaning.py          # clean & normalize
python scripts/stage5_structure.py         # structural tagging
python scripts/stage6_validation.py        # validate & assemble metadata
python scripts/stage7_chunking.py          # semantic chunking
python scripts/stage8_embedding_generation.py   # generate embeddings
python scripts/stage9_vector_indexing.py   # build faiss index
```

The query/agent stages (10–21) are libraries, invoked programmatically. See
[`docs/END_TO_END_EXAMPLE.md`](docs/END_TO_END_EXAMPLE.md) for a full Stage 0 → 21 walkthrough,
including how `handle_request` (Stage 18) and `plan_and_execute` (Stage 21) are called with adapters.

## Running tests

```bash
python -m pytest
```

> Run tests with `python -m pytest` (not a bare `pytest`) so the repository root is on the import
> path for `scripts.*` and `src.*` imports.

Expected: **All tests passing**. Run a single stage's tests with, e.g.,
`python -m pytest tests/test_stage21_agent_planning.py`.

## Extension points

- **Concrete adapters.** Implement `LLMAdapter` (Stage 13), `PlannerLLMAdapter` (Stage 21),
  `CacheAdapter` (Stage 17), `ToolAdapter`/`ToolRegistry` (Stage 20), or `ConversationStore`
  (Stage 19) to connect real providers, caches, tools, or storage backends.
- **Index backend.** Stage 9 uses a faiss adapter; the `IndexAdapter` seam allows alternatives.
- **Next phase (product goal).** The alignment layer — SDG-target retriever, extractor/verifier
  passes, evidence validator, gap analysis, and UI — builds *on top of* these stages without
  modifying them.

## Current capabilities

- Deterministic, idempotent ingestion of PDF proposals into validated, chunked, embedded, and
  vector-indexed artifacts.
- A frozen query-time RAG chain (retrieval → context → prompt → cached LLM → citations →
  groundedness → quality) exposed as a single `APIResponse`.
- An agent layer: conversation memory, structured tool invocation, and a deterministic top-level
  planner.
- Comprehensive passing tests; byte-identical output guarantees documented per stage.

## Known limitations

- **Product goal not yet built.** The SDG-alignment features (extractor/verifier passes, evidence
  validator, gap analysis, Streamlit UI, `data/sdg_targets.json`) are not implemented; only the
  pipeline foundation is delivered.
- **Query/agent stages are verified by unit tests over in-memory adapters**, not by an end-to-end run
  against a live LLM; real-provider behaviour depends on the adapter supplied at wiring time.
- **No plan/response caching across requests** beyond Stage 17's per-call LLM cache.
- **`eval/gold_set` and `pages/` are reserved directories**, currently empty.

## License

See [`LICENSE`](LICENSE). **A license has not yet been chosen** — the current file is a placeholder
(all rights reserved). Select and add a license before any public release.

## Authors / contact

- `<AUTHOR NAME>` — `<contact / email>` *(placeholder — fill in before submission)*
