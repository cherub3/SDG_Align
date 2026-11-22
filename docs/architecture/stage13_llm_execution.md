# Stage 13 — LLM Execution

Stages 0–12 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 13 turns Stage 12's `PromptPackage` into an `LLMResponse`: it invokes a configured LLM provider
exactly once per request (subject to the Retry Policy), and captures a deterministic, structured
result — response text, finish reason, token usage, latency, provider metadata, and a normalized error
outcome if the call failed — regardless of which provider or model produced it. It performs no
generation logic of its own; it is a thin, structured execution-and-capture layer around a small,
provider-independent `LLMAdapter` contract, mirroring the `ProviderAdapter` (Stage 8) and `IndexAdapter`
(Stage 9) pattern one layer further downstream. `execute_prompt(prompt_package, llm_adapter,
execution_config)` is the sole public entrypoint.

Stage 13 is the first stage in this pipeline whose own primary output content
(`LLMResponse.response_text`) cannot be claimed as deterministic under Principle 1 — an explicit,
named, precisely-scoped exception, not an oversight (see Determinism).

## Scope

Stage 13 answers exactly one question — given a `PromptPackage`, what did the configured LLM provider
return, captured completely and structurally, with full execution metadata — and stops there. It never
judges, formats, validates, or fact-checks the model's own output; it never decides whether the answer
is good, correct, or safe; it never invokes a second model call to critique or refine the first; it
never remembers a prior turn; it never calls a tool or function on the model's behalf; it never streams
a partial response to any caller (Stage 13 always returns one fully-materialized result per request,
even if an adapter's own SDK uses a streaming transport internally to assemble it — that is an adapter
implementation detail, never an architectural surface Stage 13 exposes). Those boundaries are restated
in Future Stage Boundaries.

## Responsibilities

Stage 13 shall: receive a `PromptPackage`; structurally validate it before use; skip invocation
entirely when the upstream package carries no usable content (`status == "FAIL"`); construct a
deterministic request from the package's `system_prompt`/`user_prompt` and a caller-supplied
`LLMExecutionConfig`; invoke a caller-supplied `LLMAdapter`, applying a fixed, named retry policy to
transient failures; capture the response text, finish reason, token usage, latency, attempt count, and
provider metadata exactly as the adapter reports them; normalize any invocation failure into a small,
closed set of named codes; and assemble an `LLMResponse` whose own internal invariants are self-checked
before it is ever returned.

## Non-Responsibilities

Stage 13 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: citation generation; hallucination detection; answer validation or fact-checking;
answer or Markdown formatting; JSON repair or output coercion; tool calling or function calling;
conversation memory or multi-turn orchestration; agent planning; retrieval or reranking of any kind;
prompt construction or context assembly (both already frozen, upstream); any hybrid or non-vector
retrieval strategy; and any Stage 14+ concern in general (evaluation, response caching, a network-facing
API, or a UI). Every one of these remains reserved for a later, separate design (Future Stage
Boundaries).

## Inputs

Two required inputs, only one of them in-memory:

- `PromptPackage` (Stage 12's own output schema, unchanged) — the sole source of `system_prompt`,
  `user_prompt`, `prompt_package_id`, `status`, and upstream `findings`.
- An `LLMAdapter` instance (or factory), plus an `LLMExecutionConfig` (model selection, sampling
  parameters, `max_output_tokens`, `timeout_seconds`) — runtime configuration, supplied by the caller,
  never hard-coded (Configuration).

No other input is read. `manifest.json`, `chunks.json`, `metadata.json`, vector indexes, embeddings,
and any earlier-stage artifact are never opened — every field Stage 13 needs already exists on
`PromptPackage`, verbatim (see Design Decisions #1). No PDF is ever reopened; no chunk is ever
regenerated; no vector search or embedding call is ever performed here; Stage 13 never reads
`ContextPackage` or `RetrievalResult` directly — only what `PromptPackage` already carries forward from
them (`context_findings`, itself already carrying `retrieval_findings`). Stage 13's own `assembled_prompt`
field on the input `PromptPackage` is read but never sent to the adapter — see Design Decisions #4.

## Outputs

None persisted. Stage 13 produces zero artifacts and writes to no file — the fourth consecutive fully
read-only, zero-manifest-interaction stage in this pipeline's query-time path, extending the posture
Stage 10, Stage 11, and Stage 12 each already established. Its sole output is an in-memory `LLMResponse`
(see Schemas) returned directly to the caller. The one genuine external side effect Stage 13 performs
is the outbound network call to the LLM provider itself — the same class of side effect Stage 8's
`embed_batch` and Stage 10's `embed_query` already make; nothing new in kind, only in purpose
(generation rather than embedding).

## Schemas

All in-memory Python structures — none persisted, no file format to version.

**`LLMExecutionConfig`**
```jsonc
{
  "model_name": "claude-...",                // required — no default; a caller must always name a model
  "temperature": 0.0,                        // optional, adapter-defined range; passed through verbatim
  "max_output_tokens": 2000,                 // optional, clamped to [1, MAX_OUTPUT_TOKENS_CEILING]
  "timeout_seconds": 60,                     // optional, clamped to [1, MAX_TIMEOUT_SECONDS]
  "max_retry_attempts": 3                    // optional, clamped to [1, MAX_RETRY_ATTEMPTS_CEILING]
}
```

**`LLMResponse`**
```jsonc
{
  "llm_response_id": "...",                  // deterministic hash over request-identity inputs only —
                                              // see Determinism; identifies this REQUEST, never this
                                              // response's own content
  "llm_execution_pipeline_version": "1.0.0",
  "executed_at": "2026-07-20T12:00:00Z",     // timestamp, excluded from every determinism comparison
  "prompt_package_id": "...",                // copied verbatim from the input PromptPackage
  "status": "PASS",                          // SKIPPED | FAIL | PARTIAL | PASS — see Validation; NOT a
                                              // passthrough of PromptPackage.status (Design Decisions #7)
  "provider_name": "...",                    // from the LLMAdapter, e.g. "anthropic"
  "model_name": "...",                       // copied verbatim from LLMExecutionConfig.model_name
  "model_version": null,                     // provider-reported if available, else null; informational
  "response_text": "...",                    // "" when status is SKIPPED or FAIL
  "finish_reason": "complete",               // normalized closed vocabulary: complete | length |
                                              // content_filter | other | null (SKIPPED/FAIL only) —
                                              // see Constants
  "prompt_tokens": 7910,                     // provider-reported; null if unavailable, SKIPPED, or FAIL
  "completion_tokens": 340,                  // provider-reported; null under the same conditions
  "total_tokens": 8250,                      // provider-reported, or prompt_tokens + completion_tokens
                                              // if the provider doesn't report a total directly
  "latency_ms": 1423,                        // wall-clock duration of the invocation that produced this
                                              // result, excluded from every determinism comparison;
                                              // null if SKIPPED
  "attempt_count": 1,                        // total invocation attempts made, 1..max_retry_attempts
  "provider_request_id": "...",              // provider-native trace id, opaque passthrough,
                                              // informational only; null if SKIPPED or never assigned
  "prompt_budget_tokens": 8000,              // copied verbatim from PromptPackage, for reference
  "prompt_utilization": 0.989,               // copied verbatim from PromptPackage, for reference
  "findings": [ /* this stage's own findings: {severity, code, message} */ ],
  "prompt_findings": [ /* PromptPackage.findings[], copied verbatim — full upstream provenance */ ]
}
```

## Backends (`LLMAdapter` contract)

Stage 13 defines one new pluggable-backend contract, `LLMAdapter`, mirroring Stage 8's `ProviderAdapter`
and Stage 9's `IndexAdapter` exactly — no orchestration logic in Stage 13 (retry decisions, status
computation, response validation) ever branches on `provider_name` or on a provider-specific exception
type or `finish_reason` string:

- `provider_name` (str), `model_version_reported` (str or None, informational only).
- `invoke(system_prompt: str, user_prompt: str, config: LLMExecutionConfig) -> RawLLMResult` — issues
  one single request/response call to the hosted provider; returns a structure already carrying
  `response_text`, a *normalized* `finish_reason` (one of the four closed values — normalization is the
  adapter's own responsibility, never Stage 13's), `prompt_tokens`, `completion_tokens`,
  `total_tokens`, and `provider_request_id`.
- On failure, raises exactly one of a small, closed set of adapter-level exception types —
  `LLMTransientError` (timeout, rate limit, 5xx — retryable), `LLMAuthError`, `LLMContentPolicyError`,
  `LLMInvalidRequestError` (all three non-retryable) — never a raw provider-SDK exception class or a
  free-text error message Stage 13 would need to pattern-match. Translating a provider's own error
  taxonomy into this closed set is the adapter's job, identical to how Stage 9's `IndexAdapter`
  isolates backend-specific behavior behind one contract.

The adapter (or a factory producing one) is runtime configuration, supplied by the caller — never
hard-coded, matching Stage 8/9/10's own `adapter_factory` convention.

## Retry Policy

Applies only to `LLMTransientError` (timeout, rate limit, 5xx-class failures) — every other adapter
exception (`LLMAuthError`, `LLMContentPolicyError`, `LLMInvalidRequestError`) is non-retryable by
definition and fails the invocation on the first occurrence. The policy itself is fixed and named,
consistent with Principle 5 (deterministic before probabilistic):

- Up to `execution_config.max_retry_attempts` total attempts (including the first), clamped to
  `[1, MAX_RETRY_ATTEMPTS_CEILING]`.
- Backoff before attempt `n` (n ≥ 2) is exactly `RETRY_BACKOFF_BASE_SECONDS *
  RETRY_BACKOFF_MULTIPLIER ** (n - 2)` — a fixed, deterministic function of the attempt index alone; no
  jitter, no randomness. (The *decision* of how long to wait is deterministic; the real-world wall-clock
  moment any given run actually resumes obviously is not — the same distinction Principle 1 already
  draws for timestamps generally.)
- Every attempt increments `attempt_count`; the final `LLMResponse.attempt_count` is however many
  attempts were actually made (1 if the first attempt succeeded or failed non-retryably; up to
  `max_retry_attempts` if every attempt hit a transient error).
- Exhausting every attempt on `LLMTransientError` produces `status="FAIL"` with an `LLM_RETRY_EXHAUSTED`
  finding, alongside one `LLM_INVOCATION_TRANSIENT_ERROR` or `LLM_INVOCATION_TIMEOUT` finding per failed
  attempt (Validation).

## Timeout Policy

`execution_config.timeout_seconds` (clamped to `[1, MAX_TIMEOUT_SECONDS]`, defaulting to
`DEFAULT_TIMEOUT_SECONDS`) bounds each individual invocation attempt, not the whole retry sequence — a
timed-out attempt is classified as `LLMTransientError` (via the adapter) and is therefore retryable
under the same policy as a rate-limit or 5xx failure, up to `max_retry_attempts`.

## Pipeline

```
PromptPackage { status, system_prompt, user_prompt, prompt_package_id, findings[], ... }
      │
      ▼
[1] validate_prompt_package(prompt_package)   — Stage 13's own structural input check: required keys
      present, correctly typed. Malformed input raises LLMExecutionInputError immediately — this
      should never happen under correct operation, since Stage 12 already self-validates its own
      output before returning it (see Validation). Distinct from, and never calling, Stage 12's own
      identically-named internal function.
      │
      ▼
[2] resolve execution_config   — caller-supplied or defaulted/clamped (Configuration); no global or
      environment state consulted
      │
      ▼
[3] prompt_package["status"] == "FAIL"?
      ├─yes──▶ LLMResponse{status="SKIPPED", response_text="", ...}, done — no adapter call is ever
      │        made (Design Decisions #2)
      │no
      ▼
[4] invoke_with_retry(system_prompt, user_prompt, adapter, execution_config)   — applies the Retry
      Policy; returns either a successful RawLLMResult or a terminal (non-retryable, or
      retries-exhausted) adapter exception
      │
      ▼
[5] map_adapter_error(exception) -> normalized finding code   — only reached if invocation ultimately
      failed (Error Mapping); no raw adapter/provider exception ever escapes this stage
      │
      ▼
[6] build_llm_response(prompt_package, execution_config, raw_result_or_error, attempt_count, latency_ms)
      — computes llm_response_id, status, and this stage's own findings
      │
      ▼
[7] validate_llm_response(response)   — internal invariant self-check on the assembled output; raises
      LLMExecutionInternalError on violation
      │
      ▼
LLMResponse { status, response_text, finish_reason, token usage, findings[], ... }
```

## LLM Execution Pipeline Diagram

```
                    ┌──────────────────────┐
                    │     PromptPackage      │
                    └──────────┬────────────┘
                               │
                    validate_prompt_package()
                               │
                     status == "FAIL"? ──yes──▶ LLMResponse(SKIPPED, "")
                               │ no
                     invoke_with_retry() ──── Retry Policy (transient errors only)
                               │
                    success ───┴─── terminal error
                       │                │
                       │        map_adapter_error()
                       │                │
                       └───────┬────────┘
                               ▼
                      build_llm_response()
                               │
                     validate_llm_response()
                               │
                               ▼
                          LLMResponse
```

## Error Mapping

A closed, named vocabulary — every adapter exception maps to exactly one Stage 13 finding code, and no
other code is ever produced by an invocation failure:

| Adapter exception | Retryable? | Finding code | Terminal effect (after retries, if any, are exhausted) |
|---|---|---|---|
| `LLMTransientError` (timeout) | Yes | `LLM_INVOCATION_TIMEOUT` (per attempt) | `LLM_RETRY_EXHAUSTED`, `status="FAIL"` |
| `LLMTransientError` (rate limit / 5xx) | Yes | `LLM_INVOCATION_TRANSIENT_ERROR` (per attempt) | `LLM_RETRY_EXHAUSTED`, `status="FAIL"` |
| `LLMAuthError` | No | `LLM_INVOCATION_AUTH_ERROR` | `status="FAIL"` immediately, no retry attempted |
| `LLMContentPolicyError` | No | `LLM_INVOCATION_CONTENT_POLICY_ERROR` | `status="FAIL"` immediately, no retry attempted |
| `LLMInvalidRequestError` | No | `LLM_INVOCATION_INVALID_REQUEST_ERROR` | `status="FAIL"` immediately, no retry attempted |

Stage 13's own orchestration never inspects an adapter exception's message text or provider-specific
type — only its membership in this closed five-way vocabulary, entirely the adapter's own
responsibility to classify correctly (Backends).

## Design Decisions

1. **`PromptPackage` alone is sufficient input; no earlier-stage artifact is ever opened.** Every field
   Stage 13 needs (`system_prompt`, `user_prompt`, `prompt_package_id`) already exists, verbatim, on
   `PromptPackage` — re-reading `ContextPackage`, `RetrievalResult`, or any corpus artifact would only
   duplicate work Stages 10–12 already did, for no gain (the identical call each of those stages already
   made one stage upstream, for the identical reason).
2. **LLM invocation is skipped entirely when `PromptPackage.status == "FAIL"`**, unlike Stage 12's own
   uniform, no-short-circuit pipeline. The two situations are not analogous: rendering an empty
   `context_text` (Stage 12) is a cheap, pure, side-effect-free string operation, so a uniform pipeline
   cost nothing. Invoking an LLM is an expensive, real, side-effecting network call — sending a request
   built from zero retrieved context serves no purpose and wastes cost, latency, and quota. `SKIPPED` is
   therefore a first-class `LLMResponse.status` value, distinct from `FAIL` (which means an invocation
   was attempted and did not succeed).
3. **The `LLMAdapter` contract mirrors Stage 8's `ProviderAdapter` and Stage 9's `IndexAdapter`
   exactly** — a small, closed set of methods and a closed exception vocabulary, with all
   provider-specific normalization (error classification, `finish_reason` mapping) isolated inside the
   adapter. No orchestration function in this stage's Pipeline ever branches on `provider_name` or a
   provider-native type.
4. **The adapter is invoked with `system_prompt` and `user_prompt` as two separate fields, never the
   flattened `assembled_prompt`.** Modern hosted chat-completion APIs — the ones this project would
   actually integrate — take structured system/user messages, not one concatenated string;
   `assembled_prompt` remains available on the input `PromptPackage` for a caller building a legacy
   single-string completion path outside this stage, but Stage 13's own adapter contract prefers the
   structured form, since it requires no re-parsing of a separator Stage 12 already discarded.
5. **`response_text`, `finish_reason`, and token usage are never asserted deterministic, at any
   `temperature` setting, for any provider.** This is Stage 13's one deliberate, explicitly-scoped
   departure from Principle 1 — restated in full under Determinism. Unlike Stage 8/10's embedding calls
   (where determinism is a reasonable working assumption, since no sampling is involved), an LLM
   completion is a sampling process by construction; assuming reproducibility here would be dishonest,
   not merely optimistic.
6. **`llm_response_id` is a deterministic hash over request-identity inputs only — `prompt_package_id`,
   `model_name`, and the resolved `execution_config` — never over `response_text` or any other captured
   response field.** Every earlier stage's own id (`index_fingerprint`, `context_package_id`,
   `prompt_package_id`) could safely exclude its derived payload because that payload was *fully
   determined* by the hashed inputs. That does not hold here: two calls sharing an identical
   `llm_response_id` may legitimately carry different `response_text`. This id identifies *the
   execution request*, never *the response's own content* — a deliberate, named reframing, not an
   oversight (see Determinism).
   ```python
   hash_input = {
       "prompt_package_id": prompt_package["prompt_package_id"],
       "model_name": execution_config["model_name"],
       "execution_config": {  # only the fields that affect the request itself
           "temperature": execution_config.get("temperature"),
           "max_output_tokens": resolved_max_output_tokens,
       }
   }
   llm_response_id = sha256(canonical_json(hash_input)).hexdigest()
   ```
7. **`LLMResponse.status` is computed from this stage's own invocation outcome, never inherited as a
   passthrough of `PromptPackage.status`.** Stage 10 → Stage 11 → Stage 12 each established "status is a
   pure passthrough; a local WARNING never downgrades it," because each of those stages could only ever
   *lose* information relative to what it received (an exclusion, a truncation) — never independently
   fail on its own terms. Stage 13 breaks that assumption: a `PASS`-status `PromptPackage` can still
   yield `LLMResponse.status="FAIL"` (an auth error, a content-policy rejection, exhausted retries),
   because success now genuinely depends on a live network operation this stage itself performs. This is
   the first stage in the chain where that is true, and the departure from the passthrough convention is
   named explicitly rather than left as an unstated inconsistency.
8. **Retry policy governs only `LLMTransientError`; every other adapter exception fails on first
   occurrence.** Retrying an auth failure, a content-policy rejection, or a malformed request can never
   succeed on a later attempt with identical input — retrying them would only waste latency and quota
   for a guaranteed-identical outcome. Only genuinely transient conditions (timeout, rate limit, 5xx) are
   retried, per Error Mapping.
9. **No conversation memory, no multi-turn state, no tool/function calling.** Stage 13 executes exactly
   one request built from exactly one `PromptPackage`; nothing about a prior call is ever read, stored,
   or referenced. Introducing any of these is explicitly a Stage 14+ concern (Future Stage Boundaries,
   Non-Responsibilities).
10. **`LLMResponse` is fully in-memory, never persisted, matching Stage 10/11/12's own posture exactly.**
    The fourth consecutive zero-artifact, zero-manifest-interaction stage in this pipeline's query-time
    path; a future Stage 14+ is expected to consume the returned object directly in-process.
11. **`response_text` is treated as untrusted, opaque model output — never interpreted, executed, or
    acted upon by Stage 13 itself.** Symmetric with Stage 12's own treatment of corpus text as
    potentially adversarial input to the *model*: here, the model's own output is potentially
    adversarial input to *whatever consumes `LLMResponse` next* (a prompt-injection payload the model
    itself echoed or was steered into producing). Stage 13 performs no sanitization, no instruction
    detection, and no filtering of `response_text` — establishing any such defense is explicitly a
    Stage 14+ or consumer-level concern, never Stage 13's (Security Considerations).
12. **Findings are named `findings`, and upstream provenance is named `prompt_findings`** — exact
    naming symmetry with `context_findings` (Stage 12) and `retrieval_findings` (Stage 11), extending
    the same verbatim-carry-forward convention one stage further.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md` §4's
Critical/Recoverable document-quarantine model, since Stage 13 has no document to quarantine and no
persisted artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10, 11, and 12 each
already gave for their own Validation sections).

**1. Input validation codes** — raised, never returned as part of any `LLMResponse`:

| Code | Raised as | Trigger |
|---|---|---|
| `PROMPT_PACKAGE_MALFORMED` | `LLMExecutionInputError` | the received `PromptPackage` is missing a required key or has a wrong-typed value (Pipeline [1]); no `LLMResponse` is produced at all |

**2. Package-level findings** — recorded in `LLMResponse.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `LLM_INVOCATION_SKIPPED_UPSTREAM_FAIL` | WARNING | package | `PromptPackage.status == "FAIL"`; no adapter call made; `status="SKIPPED"` |
| `LLM_INVOCATION_TIMEOUT` | WARNING | per-attempt | one attempt timed out; retried per Retry Policy unless attempts are exhausted |
| `LLM_INVOCATION_TRANSIENT_ERROR` | WARNING | per-attempt | one attempt hit a rate-limit/5xx-class error; retried per Retry Policy unless attempts are exhausted |
| `LLM_RETRY_EXHAUSTED` | FAIL | package | every retry attempt failed on a transient error; `status="FAIL"` |
| `LLM_INVOCATION_AUTH_ERROR` | FAIL | package | non-retryable; `status="FAIL"` immediately |
| `LLM_INVOCATION_CONTENT_POLICY_ERROR` | FAIL | package | non-retryable; `status="FAIL"` immediately |
| `LLM_INVOCATION_INVALID_REQUEST_ERROR` | FAIL | package | non-retryable; `status="FAIL"` immediately |
| `LLM_RESPONSE_TRUNCATED` | WARNING | package | invocation succeeded but `finish_reason == "length"`; `status="PARTIAL"` |
| `LLM_RESPONSE_EMPTY` | WARNING | package | invocation succeeded (`finish_reason == "complete"`) but `response_text == ""`; `status` unaffected by this finding alone |

`status` is computed once, from this truth table (evaluated top-to-bottom, first matching row wins):

| Condition | `status` |
|---|---|
| `PromptPackage.status == "FAIL"` | `SKIPPED` — invocation never attempted |
| Invocation raised a non-retryable error, or every retry attempt on a transient error was exhausted | `FAIL` |
| Invocation succeeded and `finish_reason == "length"` (response cut short) | `PARTIAL` |
| Invocation succeeded and `finish_reason` indicates natural completion | `PASS` |

A WARNING-severity finding (`LLM_INVOCATION_TIMEOUT`/`LLM_INVOCATION_TRANSIENT_ERROR` on a *retried and
eventually successful* attempt, or `LLM_RESPONSE_EMPTY`) never by itself changes `status` away from
whatever the final invocation outcome already determined — exactly the same "WARNING is informational,
never a status driver on its own" posture Stage 10/11/12 each established, applied here to Stage 13's
own newly-independent status computation (Design Decisions #7).

**3. Internal invariant codes** — raised by `validate_llm_response()`, run unconditionally on the
assembled response before it is ever returned; never returned as part of any `LLMResponse`:

| Code | Trigger |
|---|---|
| `RESPONSE_STATUS_TEXT_MISMATCH` | `status` in `{SKIPPED, FAIL}` but `response_text != ""`, or `status` in `{PASS, PARTIAL}` but `response_text == ""` without an accompanying `LLM_RESPONSE_EMPTY` finding |
| `FINISH_REASON_STATUS_MISMATCH` | `status == "PASS"` but `finish_reason == "length"`, or `status == "PARTIAL"` but `finish_reason != "length"` |
| `TOKEN_COUNT_MISMATCH` | `prompt_tokens` and `completion_tokens` are both non-null and `total_tokens != prompt_tokens + completion_tokens` |
| `ATTEMPT_COUNT_INVALID` | `attempt_count < 1`, or `attempt_count > execution_config.max_retry_attempts`, or `attempt_count != 0` when `status == "SKIPPED"` |
| `PROMPT_PACKAGE_ID_MISMATCH` | `response.prompt_package_id != input PromptPackage.prompt_package_id` |

Any of these five raises `LLMExecutionInternalError` rather than being returned as a malformed
`LLMResponse` — the same fail-loud posture as Stage 10/11/12's own internal-invariant exceptions, and
never expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage13_llm_execution"`, `doc_id: null` always — entries
are request-scoped, not document-scoped). New codes this stage adds: `WARNING_LLM_INVOCATION_TIMEOUT`,
`WARNING_LLM_INVOCATION_TRANSIENT_ERROR`, `WARNING_LLM_RESPONSE_TRUNCATED`,
`WARNING_LLM_RESPONSE_EMPTY`, `FATAL_LLM_RETRY_EXHAUSTED`, `FATAL_LLM_INVOCATION_AUTH_ERROR`,
`FATAL_LLM_INVOCATION_CONTENT_POLICY_ERROR`, `FATAL_LLM_INVOCATION_INVALID_REQUEST_ERROR`. No manifest
`error_code` is ever set — Stage 13 never touches the manifest at all (see Manifest Interaction); these
`FATAL_*` codes are structured-log-only, describing a request-level outcome, not a document-level one.

## Manifest Interaction

None. Stage 13 never opens, reads, or writes `manifest.json` — the third stage in this pipeline with
zero manifest interaction of any kind, extending Stage 11 and Stage 12's own posture: every field it
needs already arrived on `PromptPackage`, and an LLM provider is runtime configuration, never something
the manifest describes.

## Artifact Interaction

None on disk. Stage 13 performs zero local file reads and zero local file writes. Its only input is an
in-memory `PromptPackage`; its only output is an in-memory `LLMResponse`. The one genuine I/O this stage
performs is the outbound network call to the LLM provider via the `LLMAdapter` — entirely the adapter's
own concern, never a local filesystem interaction, and outside Stage 13's own atomicity/persistence
model because nothing is written to disk on either side of that call.

## Directory Structure

None added. Stage 13 introduces no new artifact directory — there is no artifact.

## Determinism

Stage 13 is the first stage in this pipeline to draw an explicit line between what it guarantees
deterministic and what it does not — restated here in full, not left to inference:

**Deterministic (guaranteed, byte-identical across runs, given identical input):**
- **Request construction.** Given an identical `(PromptPackage, execution_config)`, the exact request
  sent to the adapter (`system_prompt`, `user_prompt`, `model_name`, `temperature`,
  `max_output_tokens`) is byte-identical every time.
- **Stable `llm_response_id`.** A pure function of `prompt_package_id`, `model_name`, and the
  request-affecting fields of `execution_config` alone (Design Decisions #6) — never a function of
  `response_text` or any other captured response field.
- **Retry/backoff decision logic.** Which errors are retryable, the backoff formula for attempt `n`,
  and the attempt ceiling are all fixed, named functions of the attempt index and error classification
  alone (Retry Policy) — never randomized.
- **Error mapping.** A given adapter exception type always maps to the same finding code (Error
  Mapping) — a pure, total function with no provider-specific branching in Stage 13's own orchestration.
- **`validate_llm_response()`'s own outcome.** Identical `LLMResponse` content always produces an
  identical validation outcome.

**Explicitly NOT deterministic (inherent to LLM invocation; never assumed, never hidden):**
- **`response_text`.** The model's own generated content; may differ across two calls sharing an
  identical request, at any `temperature` setting, depending on the provider. Never assumed
  byte-identical, unlike every other content field in this pipeline.
- **`finish_reason`, `prompt_tokens`, `completion_tokens`, `total_tokens`.** Provider-reported, and
  covary with `response_text` — inherit the same non-determinism.
- **`latency_ms`.** Wall-clock by definition; excluded from every determinism comparison, the same
  treatment every other stage already gives its own timestamp field.
- **`provider_request_id` and `model_version` (when reported).** Provider-assigned identifiers; never
  reproducible across calls.
- **`attempt_count`.** Depends on whether a transient failure actually occurred on a given call — not
  reproducible in the presence of real network conditions, even though the *policy* governing it is
  fully deterministic.

## Read-Only Guarantees

Stage 13 never modifies `manifest.json`, any `PromptPackage`, `ContextPackage`, `RetrievalResult`, any
chunk, any metadata, any vector index, or any embedding. No upstream artifact is ever mutated; no write
capability exists anywhere in this design, on disk. The one caveat, stated explicitly rather than left
implicit: Stage 13's own outbound request necessarily leaves this pipeline's control boundary — the LLM
provider itself may log, cache, or retain the transmitted `system_prompt`/`user_prompt` server-side,
entirely outside this design's visibility or control (Known Limitations). "Read-only" here describes
every artifact and state this pipeline itself owns; it cannot describe what a third-party provider does
with a request after receiving it.

## Failure Handling

- **A malformed `PromptPackage`** (missing/wrong-typed required key) — `LLMExecutionInputError`
  (`PROMPT_PACKAGE_MALFORMED`) raised immediately; no `LLMResponse` returned.
- **`PromptPackage.status == "FAIL"`** — `LLMResponse{status="SKIPPED", response_text=""}`; no adapter
  call is ever made; `LLM_INVOCATION_SKIPPED_UPSTREAM_FAIL` finding recorded; `prompt_findings` carries
  `PromptPackage.findings[]` forward verbatim.
- **A single attempt times out or hits a rate-limit/5xx error** — classified `LLMTransientError`;
  retried per the Retry Policy up to `max_retry_attempts`; each failed attempt records its own
  `LLM_INVOCATION_TIMEOUT` or `LLM_INVOCATION_TRANSIENT_ERROR` finding.
- **Every retry attempt on a transient error is exhausted** — `LLM_RETRY_EXHAUSTED`, `status="FAIL"`;
  `response_text=""`.
- **An auth, content-policy, or invalid-request error occurs on any attempt** — non-retryable;
  `status="FAIL"` immediately, with the matching finding (`LLM_INVOCATION_AUTH_ERROR`,
  `LLM_INVOCATION_CONTENT_POLICY_ERROR`, or `LLM_INVOCATION_INVALID_REQUEST_ERROR`); no further attempt
  is made.
- **The invocation succeeds but `finish_reason` indicates truncation** — `status="PARTIAL"`;
  `LLM_RESPONSE_TRUNCATED` WARNING; `response_text` still fully captured, just incomplete per the
  provider's own signal.
- **The invocation succeeds with a natural completion but `response_text == ""`** — `status="PASS"`
  still (a successful, if unusual, outcome); `LLM_RESPONSE_EMPTY` WARNING recorded, never downgrading
  `status`.
- **`execution_config` fields omitted** — defaulted per Constants (`DEFAULT_TIMEOUT_SECONDS`,
  `DEFAULT_MAX_OUTPUT_TOKENS`), clamped where a ceiling applies; `model_name` has no default and its
  omission is a caller/configuration error handled by the adapter layer, not a Stage 13 finding.
- **A genuine Stage 13 bug** (one of the five named internal invariant codes in Validation §3) —
  `LLMExecutionInternalError` raised, not returned as a malformed `LLMResponse`.

## Configuration

`execution_config` (model, sampling parameters, `max_output_tokens`, `timeout_seconds`,
`max_retry_attempts`) is per-request configuration, never defaulted from any global or environment
state except via the named `DEFAULT_TIMEOUT_SECONDS`/`DEFAULT_MAX_OUTPUT_TOKENS` constants when the
caller omits them — the same per-request convention Stage 10/11/12 each already established for their
own tunables. `model_name` has no default; a caller must always name one explicitly. The `LLMAdapter`
itself (or a factory producing one) is likewise runtime-supplied, never hard-coded, matching Stage
8/9/10's own `adapter_factory` convention — Stage 13 never imports a specific provider SDK by name in
its own orchestration path.

## Concurrency

Safe under concurrent calls, with one caveat distinct from every earlier query-time stage: Stage 13
performs zero local writes and holds no shared mutable state of its own, so any number of
`execute_prompt()` calls may run simultaneously with no locking and no local race condition — the same
guarantee Stage 10/11/12 each already give. The caveat is that the LLM provider itself may impose its
own rate limits across concurrent calls sharing one account/API key; that is entirely the provider's
and the `LLMAdapter`'s own concern (surfaced, if it occurs, as a retryable `LLMTransientError` —
Backends, Error Mapping), never a concurrency control Stage 13 itself implements.

## Security Considerations

- **Prompt injection, inherited.** `context_text` embedded in the input `PromptPackage` may already
  carry adversarial instructions from corpus content (Stage 12's own accepted risk). Stage 13 performs
  no additional sanitization on the outbound request — that risk passes through unchanged, still
  explicitly out of scope here.
- **Untrusted model output.** `response_text` is opaque, model-generated content — never interpreted,
  executed, or interpolated into a path/shell/eval by this stage. A model can itself be steered (via
  the corpus-content injection above, or otherwise) into producing output that looks like an instruction
  to whatever consumes `LLMResponse` next; Stage 13 establishes no defense against this, by design
  (Design Decisions #11) — that is explicitly a Stage 14+ or consumer-level concern.
- **Credential handling.** API keys or other provider credentials are `LLMAdapter`-level configuration,
  supplied by the caller to the adapter, never passed through, logged, or included in `LLMResponse`,
  `findings`, or any log entry Stage 13 itself emits.
- **Provider-side retention.** The transmitted `system_prompt`/`user_prompt` leaves this pipeline's
  control boundary once sent; whether/how the provider logs, caches, or retains it is outside this
  design's visibility (Read-Only Guarantees, Known Limitations).
- **No local write capability anywhere in this design** — eliminates an entire class of
  injection/corruption risk against this pipeline's own artifacts by construction, not by runtime
  validation.

## Public Function Contracts

- `validate_prompt_package(package: PromptPackage) -> None` — Stage 13's own structural input check;
  raises `LLMExecutionInputError` (code `PROMPT_PACKAGE_MALFORMED`) on a missing/wrong-typed required
  key. Distinct from, and never calling, Stage 12's own function of the same name.
- `resolve_execution_config(config: Optional[LLMExecutionConfig]) -> LLMExecutionConfig` — applies
  defaults/clamps (Configuration); raises if `model_name` is missing.
- `invoke_with_retry(system_prompt: str, user_prompt: str, adapter: LLMAdapter, config:
  LLMExecutionConfig) -> Tuple[Optional[RawLLMResult], Optional[Exception], int, int]` — returns
  `(result_or_none, terminal_exception_or_none, attempt_count, latency_ms)`; applies the Retry Policy
  internally; never lets a retryable `LLMTransientError` escape uncaught before attempts are exhausted.
- `map_adapter_error(exception: Exception) -> str` — the fixed, total mapping from an adapter exception
  type to one Error Mapping finding code; never inspects a message string or provider-specific type
  beyond the five-way closed vocabulary.
- `build_llm_response(prompt_package: PromptPackage, execution_config: LLMExecutionConfig,
  raw_result: Optional[RawLLMResult], terminal_error_code: Optional[str], attempt_count: int,
  latency_ms: Optional[int]) -> LLMResponse` — computes `llm_response_id`, `status`, and this stage's
  own `findings`; sets `prompt_findings` from `prompt_package["findings"]` verbatim.
- `validate_llm_response(response: LLMResponse) -> None` — internal invariant self-check; raises
  `LLMExecutionInternalError` (one of the five named codes in Validation §3) on violation.
- `execute_prompt(prompt_package: PromptPackage, llm_adapter: LLMAdapter, execution_config:
  Optional[LLMExecutionConfig] = None) -> LLMResponse` — the sole public entrypoint; orchestrates
  Pipeline [1]–[7]; never reads or writes any local artifact and never touches the manifest; the only
  I/O it performs is via `llm_adapter.invoke()`.

## Constants

```python
LLM_EXECUTION_PIPELINE_VERSION = "1.0.0"
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 300            # hard ceiling — guards a pathological request, never silently raised
DEFAULT_MAX_OUTPUT_TOKENS = 2000
MAX_OUTPUT_TOKENS_CEILING = 32000    # hard ceiling — guards a pathological request, never silently raised
DEFAULT_MAX_RETRY_ATTEMPTS = 3
MAX_RETRY_ATTEMPTS_CEILING = 5       # hard ceiling — guards a pathological/misconfigured request
RETRY_BACKOFF_BASE_SECONDS = 1.0
RETRY_BACKOFF_MULTIPLIER = 2.0       # deterministic exponential backoff: base * multiplier ** (attempt - 2)
FINISH_REASONS = ("complete", "length", "content_filter", "other")   # closed vocabulary; adapter-normalized
```

## Known Limitations

- **`response_text` reproducibility is never guaranteed, at any `temperature`.** The first genuinely
  non-deterministic content this pipeline produces — inherent to LLM sampling, not a Stage 13 defect
  (Determinism).
- **Provider-side retention of the transmitted prompt is outside this design's visibility.** Whether a
  given provider logs, caches, trains on, or otherwise retains `system_prompt`/`user_prompt` after
  receiving it is a provider-policy question this stage cannot observe or control (Read-Only
  Guarantees, Security Considerations).
- **Retry backoff timing is deterministic in decision, not in wall-clock outcome.** Two runs hitting an
  identical sequence of transient failures will wait the identical *scheduled* durations, but real
  network conditions mean the actual sequence of failures itself is not reproducible run-to-run.
- **No local caching of identical requests.** Two calls with byte-identical `(PromptPackage,
  execution_config)` each issue a fresh network call — Stage 13 makes no attempt to recognize or dedupe
  a repeated request; introducing a cache is explicitly a Stage 14+ concern (Future Stage Boundaries).
- **`finish_reason` normalization depends entirely on the adapter's own correctness.** Stage 13 trusts
  the adapter's mapping into the four-value closed vocabulary; a provider introducing a new native
  finish reason the adapter doesn't yet recognize is an adapter-level gap, not something Stage 13's own
  orchestration can detect or correct.
- **A single, non-streaming request/response model only.** No partial-result delivery to a caller while
  the model is still generating — a real latency cost for a long response, accepted in exchange for a
  single, fully-validated result per call (Scope).

## Accepted Tradeoffs

- **Determinism is explicitly not claimed for generated content.** The alternative — pretending an LLM
  call is reproducible, or silently omitting the question — would be dishonest given this project's own
  stated Principle 1; naming the exception precisely was judged strictly better than either.
- **A fixed, closed retry policy, not an adaptive or provider-tuned one.** Simple, predictable, fully
  specified by two constants (base, multiplier) and a ceiling — accepts that a provider with very
  different rate-limit characteristics might benefit from a different schedule, deferred to a future
  per-provider tuning pass if ever needed.
- **`LLMResponse.status` breaks the passthrough convention Stage 10–12 established.** A deliberate,
  named departure (Design Decisions #7) rather than a forced, unstated inconsistency — accepted because
  the underlying situation (a stage whose own work can newly fail) is itself genuinely new at this
  stage.
- **No local response caching, no request deduplication.** Simplicity and statelessness over avoiding a
  redundant paid API call on identical repeated input; a future caching layer is a bounded addition, not
  a redesign, should it prove necessary (Known Limitations).
- **Skip-on-upstream-FAIL, not a uniform pipeline like Stage 12's.** Accepts one additional branch in
  the pipeline (Pipeline [3]) in exchange for never spending real cost/latency/quota on a request built
  from zero context — judged the correct tradeoff specifically because, unlike Stage 12, the operation
  being skipped has a real-world cost.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not this
document.

- A malformed `PromptPackage` is rejected deterministically, every time, without producing any
  `LLMResponse` and without any adapter call being made.
- `PromptPackage.status == "FAIL"` always produces `LLMResponse.status == "SKIPPED"` with
  `response_text == ""`, and the adapter's `invoke()` is never called (verifiable via a call-count
  assertion against a stub adapter).
- Given an identical `(PromptPackage, execution_config)`, the request passed to `adapter.invoke()`
  (`system_prompt`, `user_prompt`, `model_name`, `temperature`, `max_output_tokens`) is byte-identical
  across repeated calls; `llm_response_id` is byte-identical across repeated calls, even when a stub
  adapter is configured to return different `response_text` on each call.
- A `LLMTransientError` on attempt 1 that succeeds on attempt 2 produces `attempt_count == 2`,
  `status` reflecting the eventual success (`PASS` or `PARTIAL`), and exactly one
  `LLM_INVOCATION_TIMEOUT` or `LLM_INVOCATION_TRANSIENT_ERROR` finding for the failed attempt.
- Exhausting `max_retry_attempts` on `LLMTransientError` produces `status == "FAIL"`,
  `attempt_count == max_retry_attempts`, one `LLM_RETRY_EXHAUSTED` finding, and `response_text == ""`.
- Each of `LLMAuthError`, `LLMContentPolicyError`, `LLMInvalidRequestError` produces `status == "FAIL"`
  on the very first attempt (`attempt_count == 1`), with its own matching finding code, and is never
  retried.
- `finish_reason == "length"` on a successful invocation always produces `status == "PARTIAL"` and an
  `LLM_RESPONSE_TRUNCATED` finding; every other successful `finish_reason` produces `status == "PASS"`.
- `total_tokens == prompt_tokens + completion_tokens` whenever both are non-null, for every successful
  invocation.
- Every one of the five internal invariant codes (`RESPONSE_STATUS_TEXT_MISMATCH`,
  `FINISH_REASON_STATUS_MISMATCH`, `TOKEN_COUNT_MISMATCH`, `ATTEMPT_COUNT_INVALID`,
  `PROMPT_PACKAGE_ID_MISMATCH`) fires under its documented condition and only that condition.
- Immutability: the input `PromptPackage` object is never mutated by any Stage 13 function, regardless
  of invocation outcome.
- No local file is ever read or written by any Stage 13 function, under any input or outcome, verifiable
  by asserting zero filesystem calls against a stub adapter across every test scenario.

## Real Corpus Verification

Against a real `PromptPackage` produced by the live Stage 10 → 11 → 12 chain, executed against a real
(or a realistic, contract-conformant sandboxed) provider via a concrete `LLMAdapter` implementation: a
representative real `PromptPackage` invoked successfully produces a well-formed `LLMResponse` with
`status == "PASS"`, non-empty `response_text`, `latency_ms > 0`, and `attempt_count == 1`; a
deliberately invalid `model_name` produces `LLM_INVOCATION_INVALID_REQUEST_ERROR` with `status ==
"FAIL"`; a `PromptPackage` with `status == "FAIL"` (e.g. from an empty retrieval result upstream) never
issues a network call at all, verified via the adapter's own call-count; a small `max_output_tokens`
against a real provider produces `finish_reason == "length"` and `status == "PARTIAL"`, with
`response_text` still non-empty and usable; two separate real invocations of the identical
`PromptPackage` and `execution_config` produce two `LLMResponse`s sharing an identical
`llm_response_id` and identical `prompt_tokens` (input-side token accounting is provider-deterministic
even though generated content is not) but potentially differing `response_text` — both are correct
outcomes, and this is confirmed by inspection rather than asserted as a bug.

**Determinism, explicitly:** unlike every earlier stage's Real Corpus Verification, this section
cannot state "two identical calls produce a byte-identical result" for the response as a whole — that
would misstate what this stage actually guarantees. Instead: two identical calls are confirmed to (a)
send a byte-identical request, (b) share an identical `llm_response_id`, and (c) each independently
produce an internally self-consistent `LLMResponse` that satisfies every Validation §3 invariant — while
`response_text` itself is explicitly permitted, and expected, to potentially differ.

Immutability: the input `PromptPackage` object is confirmed byte-identical before and after the call;
no artifact from any earlier stage is touched at all, since Stage 13 opens none.

## Future Stage Boundaries

Stage 14+ (not designed here) owns everything Stage 13 deliberately excludes: citation formatting,
answer or hallucination validation, response streaming to a caller or UI, tool/function calling,
conversation memory or multi-turn orchestration, agent planning, response caching or deduplication,
retrieval-quality or answer-quality evaluation, and any network-facing API or UI serving a response to
an end user. Stage 13 hands an `LLMResponse` back in memory; how a caller formats, validates, caches,
streams, or builds a multi-turn conversation on top of it is entirely out of this design's scope.
