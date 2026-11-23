# Phase 3 Step 2: Gemini API adapters, 429 fix, container prep

No Gemini call, no GCP call, no build, no API enable, no git. Labels: VERIFIED = produced by a command in this pass.

## 429 finding (VERIFIED, was INFERRED)
`llm_provider_gemini.py` mapped HTTP 429 to `LLMTransientError`, and `invoke_with_retry` retries those with backoff. So a 429 was retried up to the configured attempts, each burning free-tier quota. Fixed:
- `LLMQuotaExhaustedError` (stage 13, subclass of `LLMInvalidRequestError`, so never retried). New terminal code `LLM_INVOCATION_QUOTA_EXHAUSTED`.
- Gemini LLM adapter: 429 -> quota error, one attempt. Gemini planner adapter: 429 -> `PlannerInvocationError(code="QUOTA_EXHAUSTED")`.
- Test that fails on the old code: `tests/test_quota_429.py` (old code: class missing; and its `call_count == 1` with 5 retries allowed could not hold, since 429 was transient).
- NOT changed: Groq, OpenRouter and the embedding providers still treat 429 as transient. Not used in this plan; say if you want them aligned.

## Daily cap and breaker (`scripts/quota_guard.py`)
- `DAILY_LLM_CALL_CAP`: default 10, range 0..18, invalid -> 10, never unlimited. 0 = retrieval only.
- Every attempted call counts (answer + planner share one counter). Cap reached -> refused without a network call.
- A 429 opens a breaker until midnight Pacific; the counter and breaker reset on the Pacific date change.
- Wired in `composition_root.py` inside the per-request cap. In-memory: resets if Cloud Run restarts the instance (Google's 20/day plus the breaker is the real hard stop).
- Defaults moved to pinned `gemini-2.5-flash-lite` (composition root, `.env.example`, `DEPLOYMENT.md`). The adapters already capture prompt/completion/total tokens per call.
- Tests: `tests/test_quota_guard.py` (12), fakes only. `test_composition_root.py` updated for the extra wrapper layer.

## Tests (VERIFIED, offline flags)
964 passed x3 identical, coverage 86.59% (gate 80%). Before: 944 passed, 86.43%.

## Cost (Gemini free tier)
Gemini $0 on the free tier (no billing on the key project). Paid-equivalent is not computed: pricing for the model was not confirmed from the page (UNKNOWN), and it would not be charged.

## Container prep (written, NOT built, NOT run: no Docker here)
`Dockerfile` (multi-stage, python:3.12-slim, CPU torch via the pytorch CPU index, bge-small baked at the pinned revision `5c38ec7c...` using the code's own loader with `ALLOW_MODEL_DOWNLOAD=true` in the builder only, runtime offline, non-root uid 10001, `uvicorn 0.0.0.0:$PORT`), `.dockerignore`, `.gcloudignore`, `cloudbuild.yaml` (build + push only, nothing deployed).
- VERIFIED locally: a tree containing only scripts, src, config, manifest, chunks and vector_index (2.1 MB of data; no PDFs, no extracted text) passes the startup checks and loads the embedder offline: 6 docs, 497 chunks.
- UNVERIFIED until the first Cloud Build: that the Dockerfile builds, final image size, cold start, warm p50/p95, and that the CPU torch pin resolves.
- Needs your decision: `data/proposals/` is git-ignored because the corpus licence is unconfirmed. The image would contain derived chunk text (not PDFs) in your private Artifact Registry. `.gcloudignore` is written so Cloud Build uploads the derived data despite `.gitignore`.
- Cloud Build is billable-adjacent (free tier 2,500 min/month per my Step 1 reading); not run. API enables needed first (Cloud Build, Artifact Registry, Cloud Run, Secret Manager): not enabled.

## Not done / next
Live smoke call (1 Gemini call) waits for your separate "go". Mutant probe for M59+ (guard/429) deferred to Step 9's single serial run.

## Files
Modified: `scripts/stage13_llm_execution.py`, `scripts/llm_provider_gemini.py`, `scripts/planner_provider_gemini.py`, `scripts/composition_root.py`, `tests/test_composition_root.py`, `.env.example`, `DEPLOYMENT.md`, `reports/PHASE_3_STEP1_GCP_READINESS.md`.
New: `scripts/quota_guard.py`, `tests/test_quota_429.py`, `tests/test_quota_guard.py`, `Dockerfile`, `.dockerignore`, `.gcloudignore`, `cloudbuild.yaml`, `reports/PHASE_3_STEP2_REPORT.md`.

## Update after the smoke call (2026-11-23)
- First call: `gemini-2.5-flash-lite` returned 404 (not available to new users). Switched everywhere to `gemini-3.5-flash-lite`, pinned in `config/llm_model.json` (`scripts/model_config.py`), plus `.env.example`, `DEPLOYMENT.md`, `tools/gemini_smoke.py`, composition root.
- Second call OK (see `reports/evidence/gemini_smoke.json`; budget and data-use facts in Revision 4 of `PHASE_3_STEP1_GCP_READINESS.md`).
- **Bug found by the live call, fixed:** the real SDK enum `FinishReason.STOP` stringifies as `FinishReason.STOP`, so every normal answer was labelled finish_reason "other" instead of "complete" (the old tests used plain strings). Same flaw would have mislabelled planner safety blocks as EMPTY_RESPONSE. Fixed with `_enum_name`; 4 tests on the real enum fail on the old code and pass now.
- Pacing added: `QuotaGuard(pace=12)` / `LLM_PACE_RPM`; smoke run paces at 12 RPM from config.
- Suite: 972 passed x3 identical, coverage 86.62%.
- New files: `config/llm_model.json`, `scripts/model_config.py`, `tools/gemini_smoke.py`, `reports/evidence/gemini_smoke.json`.
