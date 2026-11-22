# Troubleshooting

Known failure modes for the Track B backend/frontend, with their exact error text, root cause, and
resolution. If you hit something not listed here, check the server log first (`backend_server`
logger) — client-facing error bodies are intentionally generic and never leak internals.

---

## Startup failures

### `ConfigurationWiringError: PROVIDER_NOT_REGISTERED: <seam> / <provider_name>`

A `.env` variable declares a provider seam (e.g. `INDEX_BACKEND=faiss`) that has no matching
registration in the `ProviderRegistry` built at startup. Only three registrations exist in this
repository: `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `PLANNER_LLM_PROVIDER` (all `gemini`). Remove or
comment out the offending variable — see the note already in `.env.example` next to
`# INDEX_BACKEND=faiss`.

### `ValueError: Gemini provider requires 'model_name' in extra settings`

`.env`'s `EMBEDDING_PROVIDER_EXTRA_*` variables don't use the names the embedding factory expects.
Required: `EMBEDDING_PROVIDER_EXTRA_MODEL_NAME` and `EMBEDDING_PROVIDER_EXTRA_MODEL_VERSION` (not
`EMBEDDING_PROVIDER_EXTRA_MODEL`). See `.env.example` for the correct names.

### `ValueError: Gemini provider requires a credential (API key)`

`GEMINI_API_KEY` isn't visible to the process at wiring time. Confirm:

1. `.env` exists at the repository root (`sdg-align/.env`), not just `.env.example`.
2. `GEMINI_API_KEY=<real value>` is set in it (not the `your_api_key_here` placeholder).
3. You're running from the `sdg-align/` directory, or passing the correct `dotenv_path`.

`load_raw_settings()` folds `.env` into `os.environ` itself (via `load_dotenv()`) when called with
`env=None` — you do not need to separately export the variable in your shell, but if you do, the
real shell/process environment always wins over `.env`.

### Backend process never starts, no clear error

Check `bootstrap_application()`'s exception isn't being silently swallowed by whatever process
manager you're using — `_create_application_instance()` in `scripts/backend_server.py`
deliberately does not catch startup exceptions, so the process should exit non-zero with a full
traceback on stderr/logs.

---

## CORS

### Browser network tab shows `OPTIONS /run-query → 405` and `POST /run-query → net::ERR_FAILED`, but `curl`/Postman work fine

This is a genuine cross-origin issue, not a backend outage — `curl` bypasses CORS entirely, so it
succeeding while the browser fails is the expected signature of this problem, not a contradiction.
The backend's `CORSMiddleware` allows the origin named by `FRONTEND_ORIGIN` (default
`http://localhost:5173`). If your frontend is served from a different origin (different port,
different host, a deployed domain), set `FRONTEND_ORIGIN` in the backend's environment to match it
exactly (scheme + host + port) before starting `uvicorn`.

---

## Planner / LLM failures

### `PLANNER_INVOCATION_FAILED` with `APIError: 429 RESOURCE_EXHAUSTED ... limit: 0 ...`

See [Quota failures](#quota-failures) below — this is not a code defect.

### Response body has `status: "FAIL"` but HTTP status is 200

This is correct, not a bug. `/run-query` returns HTTP 200 whenever the request was **transported**
successfully — `AgentResult.status: "FAIL"` describes a **business-level** outcome (the plan
failed, e.g. because the planner or a pipeline step failed), which is different from a transport
failure. Look at `findings[].code` in the response body for the actual cause
(`PLANNER_INVOCATION_FAILED`, `PLAN_STEP_EXECUTION_FAILED`, etc.).

### `conversation_id` in the response is always `null`, even though I sent one

Confirm you're running a version of `scripts/backend_server.py` where `RunQueryRequest` declares
`conversation_id: Optional[str] = None` and forwards it into `agent_request`. This was a real,
fixed defect (Track B Phase 15) in earlier revisions — the request model silently dropped
`conversation_id` before it ever reached `observe_request()`.

---

## Quota failures

### `429 RESOURCE_EXHAUSTED`, message includes `limit: 0` for `generate_content_free_tier_requests`

**This means the Google Cloud project behind your `GEMINI_API_KEY` has zero allocated free-tier
quota for the requested model** — the key itself is valid and authenticates correctly (this is not
an auth error; those return 401/403, not 429). Retrying does not help — `limit: 0` is a persistent
account/billing-tier ceiling, not a transient per-minute rate limit (confirmed by retrying after
the API's own suggested backoff and observing an identical `limit: 0` response both times).

**Resolution (operator action, external to this repository):**

1. Open the Google Cloud project associated with the key at
   [ai.google.dev](https://ai.google.dev/gemini-api/docs/rate-limits).
2. Enable billing on that project, or switch to a key from a project that already has usable
   quota for the model you configured (`gemini-2.0-flash` / `gemini-2.5-flash` /
   `text-embedding-004`).
3. Re-run the failing request — no code or configuration change is needed once quota is available.

Distinguishing this from other causes:

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 401 / `PermissionDenied` / "API key not valid" | Authentication — bad/revoked key | Replace the key |
| HTTP 403 / "permission denied" naming a specific API | Permissions — API not enabled on the project | Enable the Generative Language API on the project |
| HTTP 429, `limit: 0` in the quota violation | Quota/billing — no allocation at all | Enable billing / use a different project's key (this section) |
| HTTP 429, `limit: N` with N > 0, transient | Rate limiting — real traffic exceeded a real allowance | Back off and retry; consider request pacing |
| HTTP 404 / "model not found" | Model availability — wrong model name/region | Check the model name against the provider's current catalog |

---

## Retrieval failures

### Dimension mismatch / empty results against the shipped index

A fresh checkout's only vector index is a 4-dimensional **stub** (see
[`DEPLOYMENT.md` §5](DEPLOYMENT.md#5-retrieval-index)). Real Gemini embeddings are 768-dimensional.
Rebuild the index with Stages 8–9 against a real provider before running retrieval-backed queries.

### `INDEX_NOT_FOUND` finding

The `index_fingerprints` your query supplied don't match any fingerprint in
`data/proposals/manifest.json`. Check the manifest's `artifact_paths.vector_index` value for the
documents you expect to be searchable.

---

## Observation records

### Missing `timestamp` / `quality_score` fields on `GET /observation-records`

Not a bug — `ObservationRecord`'s frozen shape (Track B Phase 6) carries only `correlation_id`,
`outcome`, `duration`. Quality score lives on the `/run-query` response's
`final_response.quality.answer_quality_score`, not on the observation record.
