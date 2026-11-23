# Operational Readiness Status

**Last validated:** 2026-07-25 (Track B Phase 16). Update this file's date whenever you re-run the
verification steps below against a real deployment — it is a snapshot, not a live dashboard.

---

## Summary

| Area | Status |
|---|---|
| Backend composition (`compose_application()`, all `AgentDependencies` fields) | ✅ Complete |
| Backend startup (real Gemini adapters, real `.env`) | ✅ Verified |
| CORS (browser ↔ backend) | ✅ Fixed and verified (Phase 15) |
| `conversation_id` forwarding | ✅ Fixed and verified (Phase 15) |
| Mode A auto-detection | ⚠️ Implemented. A connectivity check was reported in Phase 16, but no evidence file exists in this repository; **not verified end to end (Phase 3)** |
| Mode A query flow (Pipeline Explorer, home demo) | ✅ Fixed and verified (Phase 16) — see below |
| `ExecutionTimeline` empty-stages crash | ✅ Fixed and verified (Phase 16) |
| Full pytest suite | ✅ 944 passed, 0 failures (re-run 2026-11-23 after Phase 2.5; 633 at the original Phase 16 snapshot) |
| Frontend type-check / lint / build | ✅ Clean |
| Gemini planner/LLM calls (real answers) | ❌ Blocked — quota (external, see below) |
| Retrieval-backed queries | ⚠️ A 384-dim Hugging Face index exists only in the author's local working copy (corpus data is git-ignored); rebuild per [`DEPLOYMENT.md` §5](DEPLOYMENT.md#5-retrieval-index). Not run end-to-end through the backend |

**Bottom line:** every repository-owned defect found across Phases 15–16 has been fixed and
verified live. The two remaining blockers are both external runtime prerequisites, not code or
configuration defects — see [External Blockers](#external-blockers).

---

## What was fixed in Phase 16 (new this milestone)

1. **Mode A auto-detection did not exist.** `Dashboard_Frontend_Architecture.md` names Operating
   Mode as having a "startup-only fallback" and being "re-detected per session" — but no detection
   logic existed anywhere; `OperatingModeProvider` hardcoded `"Mode C (Static)"` permanently. Added
   `frontend/src/lib/mode-detection.ts` (one bounded, 1.5s-timeout reachability check against the
   backend, run once on mount) and wired it into `OperatingModeProvider`.

2. **Enabling Mode A detection immediately exposed two dormant defects** (invisible until Mode A
   was actually reachable):
   - `pipeline-explorer.tsx` and `animated-pipeline-demo.tsx` both unconditionally called
     `adapter.getSampleQuery()` first — unsupported in Mode A by design (Version 1.3 Decision 4).
     Both pages crashed to a raw error message in Mode A. Fixed: both now skip `getSampleQuery()`
     in Mode A and call `runQuery()` directly with a fixed query string.
   - `ExecutionTimeline` assumed `stages.length > 0` always (true for every Mode B/C canned trace,
     false for a real Mode A failure where the planner fails before any step executes — exactly
     what quota exhaustion currently produces). It crashed with `Cannot read properties of
     undefined (reading 'elapsed_ms')`, taking down the whole page via React Router's error
     boundary. Fixed: renders "No stages executed." when `stages` is empty.

All three fixes were verified live in a real browser (fresh tab, clean console) against the real
FastAPI backend — not mocked, not inferred from source reading alone.

---

## Runtime validation performed (this session)

- `python -m pytest` → 633 passed, 0 failures (Phase 16 snapshot; 944 passed on 2026-11-23, see summary table).
- `npx tsc -b && npm run lint && npm run build` → clean, 0 errors.
- Backend started via `python -m uvicorn scripts.backend_server:app`, with a real `.env` and real
  (but quota-exhausted) `GEMINI_API_KEY` — bootstrap, `compose_application()`, provider wiring all
  succeeded, no startup exceptions.
- `POST /run-query` → HTTP 200, `AgentResult.status: "FAIL"` with `PLANNER_INVOCATION_FAILED`
  (quota — see below). Confirms error handling is correct even though the underlying LLM call
  cannot succeed right now.
- `GET /observation-records` → HTTP 200, correct shape.
- Frontend started via `npm run dev`, Mode A auto-detected successfully (backend was reachable),
  `/`, `/pipeline-explorer`, `/observability` all rendered without crashing and with zero browser
  console errors, in a genuinely fresh browser tab.

---

## External blockers

These cannot be fixed by any change to this repository. They are documented here, with the exact
operator action required, per [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

### 1. Gemini quota exhaustion

```
APIError: 429 RESOURCE_EXHAUSTED
"Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests,
 limit: 0, model: gemini-2.0-flash"
```

**Classification: quota/billing, not authentication, not permissions, not model availability.**
Evidence:
- The key authenticates (no 401/`PermissionDenied`) — ruling out authentication.
- No "API not enabled" 403 — ruling out permissions.
- The model name is valid and recognized by the API (the error names it specifically, doesn't say
  "not found") — ruling out model availability.
- `limit: 0` — a persistent zero-allocation ceiling, not a transient rate limit. Confirmed
  non-transient by retrying after the API's own suggested backoff (39–58s) twice, on two separate
  validation sessions (Phase 15 and Phase 16), both returning the identical `limit: 0` response.

**Operator action required:** enable billing on the Google Cloud project behind this key, or
supply a different key from a project with usable quota. See
[`TROUBLESHOOTING.md` §Quota failures](TROUBLESHOOTING.md#quota-failures) for the full decision
table distinguishing this from other 4xx causes.

**What is blocked by this:** any query that requires an actual planner/LLM response — i.e. every
query, currently, since even a planner-only query needs one LLM call. Transport, composition,
error handling, and the frontend rendering of a `FAIL` result are all confirmed working around
this blocker; only the underlying model call itself cannot complete.

### 2. No vector index in the repository

This repository contains **no index and no corpus** (`data/proposals/` is git-ignored because the PDFs'
redistribution licence is unconfirmed). History: at the Phase 16 snapshot only a 4-dimensional stub index
was available, which is why retrieval was reported blocked. On 2026-07-25 a real 384-dimensional index
(`BAAI/bge-small-en-v1.5` via Hugging Face, 429 vectors from 5 documents) was built locally. In Phase 1 (2026-11-23) it was
rebuilt with the local embedding provider (same model, 497 vectors from 6 documents); neither is committed. Real Gemini embeddings would be 768-dimensional.

**Operator action required:** run Stages 8–9 (`stage8_embedding_generation.py`,
`stage9_vector_indexing.py`) against a Gemini key with usable quota — see
[`DEPLOYMENT.md` §5](DEPLOYMENT.md#5-retrieval-index) for the exact command sequence. This is
itself gated by blocker #1 (embedding generation is also a Gemini API call).

**What is blocked by this:** retrieval-backed queries specifically. Everything not requiring
retrieval (composition, transport, conversation memory wiring, observation logging, error
handling, Mode A connectivity) has been validated independently of this blocker.

---

## Re-validating after external blockers are resolved

Once a quota-enabled key and a real production index are available:

1. Re-run [`DEPLOYMENT.md`](DEPLOYMENT.md)'s verification checklist.
2. Confirm a planner-only query returns `AgentResult.status: "PASS"` (not `"FAIL"`) with a real
   `final_response.answer.response_text`.
3. Confirm a retrieval-backed query (with a real `index_fingerprints` value) returns non-empty
   `results`.
4. Confirm `ExecutionTimeline` on `/pipeline-explorer` shows real, populated stages rather than
   "No stages executed."
5. Update the date and status table at the top of this file.
