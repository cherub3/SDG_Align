# Deployment Guide

This document covers running SDG Align's Track B backend (FastAPI) and frontend (React/Vite)
together, in Mode A (Live). For the pipeline-only (Stages 0–21, no backend/frontend) setup, see
[`README.md`](README.md).

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Developed/tested on CPython 3.14 |
| Node.js 18+ / npm | For the frontend (`frontend/`) |
| A Gemini API key with usable quota | See [Troubleshooting §Quota](TROUBLESHOOTING.md#quota-failures) — a key that authenticates but has zero quota will not work |
| A production vector index matching your embedding model | See [Retrieval Readiness](#5-retrieval-index) below — a fresh checkout only ships a 4-dim stub index |

---

## 2. Environment configuration

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# The shipped example is SAFE BY DEFAULT: local embeddings (free, offline, matches the index) and
#   NETWORK_CALLS_PERMITTED=false  -> no paid or quota-limited call is possible.
# To answer questions you must opt in to a paid LLM + planner:
#   NETWORK_CALLS_PERMITTED=true
#   LLM_PROVIDER=gemini  LLM_PROVIDER_CREDENTIAL_REF=env:GEMINI_API_KEY  LLM_PROVIDER_EXTRA_MODEL=gemini-3.5-flash-lite
#   PLANNER_LLM_PROVIDER=gemini  PLANNER_LLM_PROVIDER_CREDENTIAL_REF=env:GEMINI_API_KEY  DEFAULT_PLANNER_MODEL_NAME=gemini-3.5-flash-lite
#   GEMINI_API_KEY=<your real key>        (or the OpenRouter / Groq blocks in .env.example)
# MAX_LLM_CALLS_PER_REQUEST (default 6) is a hard cap on LLM calls for one request.
#
# Embedding provider identity must match the index you actually built (see §5). pip install -r requirements-local.txt first.
EMBEDDING_PROVIDER=local
EMBEDDING_PROVIDER_EXTRA_MODEL_NAME=BAAI/bge-small-en-v1.5
EMBEDDING_PROVIDER_EXTRA_MODEL_VERSION=v1.5
```

At startup the server refuses to start (non-zero exit) if the manifest, chunks or index are missing or empty, if the index
was built with a different embedding model than configured, or if the local model is not in the Hugging Face cache.

See [`.env.example`](.env.example) for the full annotated list, including why `INDEX_BACKEND` is
commented out (no provider registration exists for that seam — `FAISSAdapter` is constructed
directly by `scripts/pipeline_deps_factory.py`).

**Request limits** (backend): `MAX_QUERY_CHARS` (default 4000) bounds the query length and
`REQUEST_TIMEOUT_SECONDS` (default 60) bounds one request. Blank or over-long queries get HTTP 422.
Note the timeout stops the *wait*, not the underlying LLM call.

**Frontend → backend origin** (only needed if not using the defaults): the frontend reads
`VITE_BACKEND_URL` (default `http://localhost:8000`); the backend reads `FRONTEND_ORIGIN` for CORS
(default `http://localhost:5173`). Set both in your respective `.env`/build environment if you
deploy them on different hosts/ports.

---

## 3. Backend startup

```bash
pip install -r requirements.txt
python -m uvicorn scripts.backend_server:app --host 127.0.0.1 --port 8000
```

Successful startup logs:

```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
... backend_server - INFO - Backend foundation started: application bootstrapped once.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

If this doesn't happen, see [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — most startup failures are
credential- or configuration-related and are listed there with their exact error text.

**Endpoints:**

| Route | Method | Purpose |
|---|---|---|
| `/run-query` | `POST` | Body `{"query": str, "conversation_id"?: str}` → native `AgentResult` JSON |
| `/observation-records` | `GET` | Snapshot list of `{correlation_id, outcome, duration}` |

---

## 4. Frontend startup

```bash
cd sdg-align/frontend
npm install
npm run dev
```

Opens on `http://localhost:5173` by default. **Mode A is detected automatically at startup** — the
app performs one short (1.5s timeout), one-time reachability check against the backend
(`GET /observation-records`) when it mounts; if the backend responds, the session runs in Mode A
(Live); otherwise it falls back to the build's default demonstration mode (Mode C, static). This
is a startup-only check — it does not re-poll mid-session (see `frontend/src/lib/mode-detection.ts`
and `Dashboard_Frontend_Architecture.md`'s Operating Mode state-ownership entry). Start the backend
**before** the frontend if you want a session to detect Mode A.

For a production build:

```bash
npm run build      # tsc -b && vite build
npm run preview     # serve the production build locally
```

---

## 5. Retrieval index

A fresh checkout contains **no corpus and no vector index** (`data/proposals/` is git-ignored; see the
README's "Source corpus" section and `scripts/download_corpus.py --check`). Retrieval-backed queries return
no results until you place the source PDFs and build an index with your embedding provider. An index built
with a different provider/model/version than the one in `.env` is **refused at query time**
(`INDEX_EMBEDDING_MODEL_MISMATCH`), and a dimension mismatch is reported as `EMBEDDING_DIMENSION_MISMATCH`.

**To regenerate a production index**, run the ingestion pipeline's embedding and indexing stages
against your configured provider, in order, from the repository root, with `.env` populated:

```bash
python scripts/stage0_register.py
python scripts/stage1_integrity.py
python scripts/stage2_extraction.py
python scripts/stage3_detection.py
python scripts/stage4_cleaning.py
python scripts/stage5_structure.py
python scripts/stage6_validation.py
python scripts/stage7_chunking.py
python scripts/stage8_embedding_generation.py    # uses the EMBEDDING_PROVIDER configured in .env (requires usable quota)
python scripts/stage9_vector_indexing.py         # builds the real index at the provider's dimension
```

This requires a provider with **actual usable quota** (not just a key that authenticates — see
[Troubleshooting §Quota](TROUBLESHOOTING.md#quota-failures)). Do not fabricate or hand-edit
embeddings/index files — they must come from a real provider run so `index_metadata.json`'s
`provider`/`model_name`/`model_version`/`embedding_dimension` fields are truthful.

**Important Note on Provider Switching**: A Hugging Face embedding model produces vectors (e.g. 384 dimensions) incompatible with an index generated using Gemini embeddings (768 dimensions). Do NOT attempt to reuse a Gemini FAISS index if you switch to Hugging Face or vice versa. You must regenerate the production index from scratch using the pipeline commands above when you change embedding providers.

Documents the pipeline cannot index (as of the last run on the 13-document corpus): 7 scanned PDFs
quarantined at Stage 3 as `FATAL_NO_TEXT` (they need an OCR step, not yet implemented) and 1 document that
fails Stage 6 with `DUPLICATE_SECTION_ID`. Each stage CLI exits non-zero when a document fails; scanned
PDFs exit 0 unless you pass `--strict`.

---

## 6. Verification checklist

```bash
python -m pytest                       # full backend/pipeline suite
cd frontend
npx tsc -b && npm run lint             # frontend type-check + lint
npm run build                          # production build
```

Then manually: start the backend, start the frontend, confirm the browser's console shows no
errors and the mode-detection check resolves (Mode A if backend reachable, fallback otherwise).

See [`OPERATIONAL_READINESS.md`](OPERATIONAL_READINESS.md) for the current, dated readiness status
of a specific deployment, and [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for known failure modes.
