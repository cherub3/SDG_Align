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
| Test suite | ✅ 813 tests passing, 85% line+branch coverage (`python -m pytest --cov`) |
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
plain, testable code with reproducible output (see [Determinism](#determinism-what-is-and-is-not-guaranteed)
for exactly what that does and does not cover); the LLM is confined to the narrow steps where judgment is
genuinely required, behind explicit adapter contracts.

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
| 14 | Citation Extraction | Match answer sentences to source chunks by word-n-gram overlap (lexical, not semantic) |
| 15 | Groundedness Validation | Score each cited sentence by longest-common-subsequence overlap with its source chunk (lexical: it rewards copying and cannot detect a wrong-but-quoted answer) |
| 16 | Answer Quality Evaluation | Structural score (0.7 x groundedness + 0.3 x citation presence); it does **not** measure whether the answer is correct |
| 17 | Response Caching | Cache-wrapped LLM execution via `CacheAdapter` (the shipped backend is in-memory, per process) |
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
pip install -r requirements-dev.txt   # only to run the tests
```

### Dependencies

[`requirements.txt`](requirements.txt) is the single, exactly-pinned source of truth for running the pipeline
and [`requirements-dev.txt`](requirements-dev.txt) pins the test tools (CI installs both and runs `pip check`;
`pyproject.toml` deliberately holds no second list). It covers PDF extraction
(`pymupdf`, `pymupdf4llm`), artifacts and search (`pyarrow`, `pandas`, `numpy`, `faiss-cpu`), the provider
SDKs (`google-genai`, `groq`, `openai`, `requests`) and the API server (`fastapi`, `uvicorn`, `pydantic`).
The dev file adds `pytest`, `pytest-cov` and `httpx`.

**The test suite needs no credentials and no network.** Running the ingestion pipeline on real documents
needs an embedding provider at Stage 8 (the local provider, or a hosted, rate- or quota-limited service such as
the Hugging Face Inference API or Gemini), and answering questions through the backend needs an LLM/planner provider key.

Currently supported implementations:
- **Planner:** Gemini, Groq, OpenRouter
- **LLM:** Gemini, Groq, OpenRouter
- **Embeddings:** Gemini, Hugging Face, local (sentence-transformers on CPU, no network: `EMBEDDING_PROVIDER=local`, needs `requirements-local.txt`)

Recommended Configuration:
- **Planner:** OpenRouter
- **LLM:** OpenRouter
- **Embeddings:** local (`BAAI/bge-small-en-v1.5`; its vectors matched the Hugging Face API vectors on a 10-chunk sample, cosine 1.000000)

*Important:* If you switch embedding providers (e.g., from Gemini to Hugging Face), you MUST regenerate the FAISS index (Stages 8 and 9) because the generated vectors will have different dimensions and characteristics. Stage 10 will actively prevent mismatched dimensions.

### Configuration

* **Tests and library use:** no environment variables.
* **Running the backend** (`scripts/backend_server.py`): copy [`.env.example`](.env.example) to `.env` and set
  the provider selection (`LLM_PROVIDER`, `PLANNER_LLM_PROVIDER`, `EMBEDDING_PROVIDER`), the matching
  credential variable (`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` or `HF_API_KEY`), and
  optionally `REQUEST_TIMEOUT_SECONDS` (default 60), `MAX_QUERY_CHARS` (default 4000; longer queries get
  HTTP 422) and `FRONTEND_ORIGIN` (CORS). The backend refuses to start without valid provider settings.
* **Embedding model consistency:** at query time Stage 10 only searches an index built with the *same*
  embedding provider, model and version as the wired adapter, and reports
  `INDEX_EMBEDDING_MODEL_MISMATCH` otherwise.
* Per-stage tunables (thresholds, budgets, ceilings) are module-level constants documented in each
  stage's architecture doc and source file.

### Process-local state

The backend keeps **conversation memory, the response cache and the request observation records in
process memory**. They are per instance, lost on restart and not shared between instances (observation
records are capped at 1000). Nothing here makes the server stateless; moving this state behind the
existing `ConversationStore` / `CacheAdapter` seams is future work.

### Determinism: what is and is not guaranteed

* **Deterministic** (identical inputs and an identical embedding source give identical output): chunk
  text and chunk ids, vector values, the `index.bin` file, retrieval ordering (ties broken by
  `chunk_id`), prompt rendering and cache keys. Verified on 2026-11-23 by rebuilding stages 0-9 twice with
  a local stub embedder: chunk text, ids, vectors and `index.bin` were identical.
* **Not byte-identical:** the JSON/parquet artifacts carry wall-clock fields (`generated_at`,
  `indexed_at`, `*_at`), so the files differ between runs even though their content does not.
* **Outside the guarantee:** hosted embedding and LLM APIs. A provider can change a model without notice
  and generation is not guaranteed reproducible even at temperature 0. The index fingerprint records the
  configured `model_version`; it cannot detect a silent provider-side change.

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

Each stage CLI prints a one-line summary and **exits non-zero when a document it attempted fails**
(unreadable, extraction/chunking/embedding failure, aborted index build). A scanned PDF quarantined as
`FATAL_NO_TEXT` is an expected outcome and exits 0 unless you pass `--strict`, which fails on any
quarantine. This lets a script or CI stop on a broken run.

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
- A comprehensive test suite (813 tests) and per-stage reproducibility of content (see Determinism above).

## Known limitations

- **Product goal not yet built.** The SDG-alignment features (extractor/verifier passes, evidence
  validator, gap analysis, Streamlit UI, `data/sdg_targets.json`) are not implemented; only the
  pipeline foundation is delivered.
- **Query/agent stages are verified by unit tests over in-memory adapters**, not by an end-to-end run
  against a live LLM; real-provider behaviour depends on the adapter supplied at wiring time.
- **No plan/response caching across requests** beyond Stage 17's per-call LLM cache.
- **`eval/gold_set` and `pages/` are reserved directories**, currently empty.
- **Retrieval and answer quality are unmeasured.** There is no gold set; an informal 15-question
  retrieval check (2026-11-23) found the right document ranked first for 9/9 document-specific
  questions but many chunk-level misses, and no answer-level evaluation has been run.
- **7 of 13 source PDFs are scanned** and are quarantined at Stage 3 (`FATAL_NO_TEXT`); there is no OCR
  path yet. One further document fails Stage 6 (`DUPLICATE_SECTION_ID`).
- **Windows:** directory swaps in Stage 9 retry a transient `PermissionError` (antivirus/indexer locks).

## License

See [`LICENSE`](LICENSE). **A license has not yet been chosen** — the current file is a placeholder
(all rights reserved). Select and add a license before any public release.

## Authors / contact

- `<AUTHOR NAME>` — `<contact / email>` *(placeholder — fill in before submission)*
