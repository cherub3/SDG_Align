# Stage 18 — API / Response Serving

Stages 0–17 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 18 turns an external `APIRequest` into an `APIResponse`: it validates the request's own structural
shape, assigns it a correlation `request_id`, drives the already-frozen query-time pipeline end to end —
Stage 10 (retrieval) → Stage 11 (context assembly) → Stage 12 (prompt construction) → Stage 17 (cache-
wrapped LLM execution) → Stage 14 (citation extraction) → Stage 15 (groundedness validation) → Stage 16
(answer quality evaluation), in that fixed order — and serializes the combined result into one
deterministic, transport-framework-agnostic response object. It performs no retrieval, no context
assembly, no prompt construction, no LLM invocation, no caching decision, no citation matching, no
groundedness scoring, and no quality scoring of its own; every one of those remains exactly what its own
frozen stage already computed, untouched. `handle_request(request, deps)` is the sole public entrypoint.

Stage 18 is this pipeline's first true end-to-end orchestrator — no stage before it calls another stage
(see Design Decisions #1) — and the first stage whose own primary identity field (`request_id`) is
deliberately, explicitly non-deterministic, a second and final departure from Principle 1's byte-
identical-output guarantee, precisely scoped and never left implicit (see Determinism, Correlation IDs).

## Scope

Stage 18 answers exactly one question — given an external request, what is the complete, correctly-
labeled, transport-agnostic answer this pipeline's already-frozen stages produce for it — and stops
there. It never performs retrieval, embedding, or reranking; never constructs a prompt or assembles
context; never invokes an LLM directly (it only ever calls Stage 17's own `execute_with_cache()`, which
itself only ever calls Stage 13's own unmodified `execute_prompt()`); never extracts, re-attaches, or
reformats a citation beyond copying what Stage 14 already produced; never re-verifies groundedness or
re-scores answer quality; never decides what a caller should do with a low-quality or poorly-grounded
answer (that remains the caller's own decision, informed by the data Stage 18 surfaces); never remembers
a prior turn or maintains conversation state; never calls a tool or function on the model's behalf; never
plans multiple steps; never streams a partial response (Streaming Strategy); never chooses or imports a
concrete transport framework. Those boundaries are restated in Non-Responsibilities and Future Stage
Boundaries.

## Responsibilities

Stage 18 shall: receive an `APIRequest`; structurally validate it before use (shape, types, required-
field presence only — never a semantic/business-logic check any downstream stage already owns; see
Request Validation); assign a fresh `request_id`; construct a `RetrievalRequest` from the validated
`APIRequest` and invoke the fixed, ordered pipeline chain (Request Lifecycle); map the final,
already-computed `status` from the chain's own terminal object into one of Stage 18's own three
transport-agnostic response categories (Error Mapping); assemble an `APIResponse` embedding the answer
text, its citations, its groundedness classification, its quality metrics, its cache provenance, and
every upstream stage's own identity-chain ids and findings; and self-check the assembled response's own
internal invariants before it is ever returned.

## Non-Responsibilities

Stage 18 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: retrieval, embedding, reranking, or any change to how a document is found (Stage 10's
frozen job); context assembly or budget enforcement (Stage 11's frozen job); prompt construction or
template rendering (Stage 12's frozen job); direct LLM invocation of any kind — every generation call is
made exclusively through Stage 17's own `execute_with_cache()`, itself calling only Stage 13's own
unmodified `execute_prompt()` (Stage 13/17's frozen jobs); cache-worthiness or freshness decisions
(Stage 17's frozen job); citation extraction, matching, or re-attachment (Stage 14's frozen job);
groundedness re-verification (Stage 15's frozen job); answer-quality re-scoring (Stage 16's frozen job);
any decision about what to *do* with a low-scoring or poorly-grounded answer (regenerate, reject,
escalate — a caller's own concern, informed by, never made by, this stage); response streaming of any
kind (Streaming Strategy); conversation memory, multi-turn session state, or turn-to-turn continuity;
tool or function calling; agent planning; choosing, importing, or depending on any concrete transport
framework (FastAPI, Flask, Django, gRPC, or any other HTTP/RPC library); **retrying a failed invocation
of any kind — Stage 18 performs no retries.** Retry logic already belongs exclusively to Stage 13's own
frozen Retry Policy, scoped to one LLM invocation attempt; Stage 18 never wraps a stage call (its own or
any other's) in a retry loop, and in particular never retries the whole seven-stage chain on a
downstream `FAIL`, which would silently multiply cost/latency and risk re-triggering a non-idempotent
side effect (a fresh cache write) more than once per external request; **any timeout logic — Stage 18
owns no timeout logic of its own.** Every timeout boundary in this pipeline, including
`timeout_seconds`, belongs to Stage 13 (bounding one invocation attempt) and is forwarded from
`pipeline_options` unmodified (Request Schema) — `handle_request()` itself imposes no wall-clock deadline
on the overall call. Every one of these remains reserved for a later, separate design, is permanently
frozen upstream, or is a caller-side concern outside this pipeline's own scope (Future Stage Boundaries).

## Inputs

Two required inputs, both supplied by the caller, at two different scopes:

- `APIRequest` (this stage's own new schema, see Request Schema) — per-call, the sole source of `query`,
  `index_fingerprints`, `filters`, and every optional per-request pipeline tuning knob
  (`pipeline_options`). This is the only input an external caller ever supplies.
- `PipelineDependencies` (this stage's own new schema, see Configuration) — per-deployment, supplied once
  at wiring time, never per-call: a pre-configured `retrieve` entrypoint (Stage 10's own frozen
  `retrieve(request)`, already closed over whatever adapter factories and manifest access it needs — an
  implementation detail entirely internal to Stage 10, opaque to Stage 18), an `llm_adapter` and
  `cache_adapter` (Stage 13/17's own frozen parameters), and a `default_model_name` (Configuration).

No other input is read. `manifest.json`, `chunks.json`, `metadata.json`, vector indexes, embeddings, and
every prompt template file are never opened directly by Stage 18 — every one of them is already handled
by whichever frozen stage owns it (Design Decisions #2). Stage 11 through Stage 16 need no injected
adapter of any kind, per their own frozen Configuration sections, so `PipelineDependencies` carries
nothing for them.

## Outputs

`APIResponse` (see Response Schema) is Stage 18's sole return value — never persisted by Stage 18 itself
as a distinct artifact, matching the zero-artifact posture Stage 10 through Stage 17 each already
established for their own return values. The one genuinely new, externally-visible effect of a call to
`handle_request()` is whatever Stage 17 itself may write to the cache store on a miss — an effect Stage
18 does not cause, only triggers by calling Stage 17's own already-frozen contract.

## Pipeline Ordering

Stage 18's own **design sequence number** (18) matches its **runtime invocation position** exactly —
unlike Stage 17, Stage 18 sits at the very end of the query-time chain, invoked directly by an external
caller, and is itself the orchestrator that invokes every stage before it. There is no numbering caveat
to resolve here (contrast Stage 17's own Pipeline Ordering section).

## Request Lifecycle

The one and only valid ordering, elaborating the task brief's own simplified diagram into the full chain
every intermediate stage's own frozen contract requires (Design Decisions #1):

```
Receive APIRequest
      │
      ▼
[1] validate_api_request(request)   — structural shape only (Request Validation); malformed input
      raises APIRequestInputError immediately, nothing downstream is ever touched
      │
      ▼
[2] request_id = assign_request_id()   — fresh, random, per-call (Correlation IDs)
      │
      ▼
[3] retrieval_request = build_retrieval_request(request)   — query, index_fingerprints, filters, top_k
      │
      ▼
[4] retrieval_result = deps.retrieve(retrieval_request)                              — Stage 10
      │
      ▼
[5] context_package = assemble_context(retrieval_result, context_budget_tokens)      — Stage 11
      │
      ▼
[6] prompt_package = construct_prompt(context_package, template_version,
      prompt_budget_tokens)                                                          — Stage 12
      │
      ▼
[7] execution_config = resolve_execution_config_for_api(request, deps)   — Stage 18's own thin
      resolution: request.pipeline_options fields, or deps.default_model_name when model_name is
      omitted (Configuration); every other field left as None, deferring to Stage 13's own defaults
      │
      ▼
[8] cached_result = execute_with_cache(prompt_package, deps.llm_adapter, deps.cache_adapter,
      execution_config, cache_ttl_seconds)                                           — Stage 17
      │
      ▼
[9] cited_response = extract_citations(cached_result.llm_response, prompt_package,
      context_package, citation_match_threshold)                                    — Stage 14
      │
      ▼
[10] groundedness_report = validate_groundedness(cited_response, context_package,
      groundedness_threshold)                                                        — Stage 15
      │
      ▼
[11] quality_report = evaluate_answer_quality(groundedness_report)                   — Stage 16
      │
      ▼
[12] response_status = map_pipeline_status(quality_report["status"])   — Error Mapping
      │
      ▼
[13] response = build_api_response(request_id, retrieval_result, context_package, prompt_package,
      cached_result, cited_response, groundedness_report, quality_report, response_status)
      │
      ▼
[14] validate_api_response(response)   — internal invariant self-check; raises
      APIResponseInternalError on violation
      │
      ▼
Return APIResponse
```

Every step [4]–[11] calls exactly one already-frozen stage's own unmodified public entrypoint, in this
exact order, with no step skipped and no step reordered — the "only one valid ordering" the frozen
upstream contracts themselves already impose (each step's own required arguments are only available once
the step before it has returned).

## Request Schema

```jsonc
APIRequest {
  "query": "climate adaptation financing mechanisms",  // required, non-empty string
  "index_fingerprints": ["a3f9..."],                    // required, non-empty list of strings —
                                                          // mirrors Stage 10's own explicit-fingerprints
                                                          // requirement (Stage 10 Design Decisions #1)
  "filters": {                                           // optional; passed through verbatim to Stage 10
    "category": null, "doc_type": null, "doc_ids": null
  },
  "pipeline_options": {                                  // optional; every field individually optional;
                                                          // omitted == None == "defer to the owning
                                                          // stage's own default" (Configuration)
    "top_k": null,                    // Stage 10
    "context_budget_tokens": null,    // Stage 11
    "template_version": null,         // Stage 12
    "prompt_budget_tokens": null,     // Stage 12
    "model_name": null,               // Stage 13, via Stage 17 — the one field with a Stage-18-level
                                       // fallback (deps.default_model_name) rather than a Stage 13
                                       // default, since Stage 13 itself defines none
    "temperature": null,              // Stage 13
    "max_output_tokens": null,        // Stage 13
    "timeout_seconds": null,          // Stage 13
    "max_retry_attempts": null,       // Stage 13
    "cache_ttl_seconds": null,        // Stage 17
    "citation_match_threshold": null, // Stage 14
    "groundedness_threshold": null    // Stage 15
  }
}
```

Every `pipeline_options` field is forwarded, unmodified, to exactly the one downstream stage that already
owns its default/clamp logic (Request Validation, Design Decisions #7) — Stage 18 never re-implements or
duplicates a clamp, default, or ceiling any frozen stage already enforces.

## Response Schema

```jsonc
APIResponse {
  "request_id": "...",                       // Stage 18's own correlation id — random, see Correlation IDs
  "api_pipeline_version": "1.0.0",
  "received_at": "2026-07-21T12:00:00Z",     // when handle_request() began; excluded from determinism
  "resolved_at": "2026-07-21T12:00:03Z",     // when handle_request() finished; excluded from determinism
  "status": "SUCCESS",                       // SUCCESS | PARTIAL_SUCCESS | PIPELINE_FAILURE — Error Mapping
  "query": "...",                            // copied verbatim from RetrievalResult.query (post Stage 10's
                                              // own preprocessing), never re-derived from the raw request
  "answer": {
    "response_text": "...",                  // verbatim from LLMResponse.response_text
    "finish_reason": "complete",              // verbatim from LLMResponse.finish_reason
    "spans": [ /* ResponseSpan, verbatim from CitedResponse.spans — text, offsets, citations */ ]
  },
  "groundedness": {
    "groundedness_score": 0.667,
    "grounded_span_count": 4, "weakly_grounded_span_count": 1, "unsupported_span_count": 1,
    "span_groundedness": [ /* SpanGroundedness, verbatim from GroundednessReport.span_groundedness */ ]
  },
  "quality": {
    "answer_quality_score": 0.786,
    "citation_presence_ratio": 0.833,
    "response_length_chars": 1523, "response_length_words": 240,
    "lexical_diversity_ratio": 0.62, "average_span_length_chars": 253.83, "span_count": 6
  },
  "cache": {
    "cache_hit": true, "cache_key": "...", "cached_at": "2026-07-20T09:00:00Z",
    "cache_backend_name": "..."
  },
  "provenance": {                            // every frozen-pipeline identity id for this one call, for
                                              // cross-stage correlation and debugging — never re-derived,
                                              // always copied verbatim from the object that produced it
    "requested_index_fingerprints": [...], "searched_index_fingerprints": [...],
    "context_package_id": "...", "prompt_package_id": "...", "llm_response_id": "...",
    "cited_response_id": "...", "groundedness_report_id": "...", "answer_quality_report_id": "..."
  },
  "findings": [ /* this stage's own findings: {severity, code, message} — Validation §2 */ ],
  "pipeline_findings": {                     // every upstream stage's own findings[], grouped by stage,
                                              // copied verbatim — full provenance, one level deep, never
                                              // merged into one undifferentiated list
    "retrieval": [...], "context_assembly": [...], "prompt_construction": [...],
    "response_caching": [...], "citation_extraction": [...], "groundedness_validation": [...],
    "answer_quality_evaluation": [...]
  }
}
```

Unlike every internal stage's own minimality convention (Stage 15/16's own "read but never re-state"
posture toward an upstream field), `APIResponse` is deliberately the full terminal payload — an external
caller has no other channel to reach `GroundednessReport`/`AnswerQualityReport`/`CitedResponse`
internals, so every field a caller could plausibly need is flattened directly into `answer`/
`groundedness`/`quality`, never left as a link-only reference (Design Decisions #8). What is still
excluded, deliberately: the full raw `GroundednessReport`/`AnswerQualityReport`/`CitedResponse` objects
themselves (their own `*_pipeline_version`, `validated_at`/`evaluated_at`/`extracted_at` timestamps, and
already-echoed threshold values are not re-embedded a second time under `APIResponse`'s own top level) —
only their content-bearing fields are selected.

## API Adapter Abstraction

Stage 18 defines **no** new pluggable-backend contract with swappable methods, unlike every prior backend
abstraction (`ProviderAdapter`, `IndexAdapter`, `LLMAdapter`, `CacheAdapter`) — a genuine architectural
difference from those, not an oversight (Design Decisions #3). Those contracts abstract over
interchangeable *implementations of one shared operation* (embed text, search a vector space, invoke a
completion, get/put a cache entry) — a transport boundary has no such shared shape: an HTTP request and a
gRPC message do not present the same interface at any useful level of abstraction, so a
`TransportAdapter.handle(request) -> response` contract would either leak a specific framework's own
request/response types into this design, or be so generic (`bytes -> bytes`) as to add no real value over
what `handle_request()` already provides.

Framework-independence is instead achieved structurally: `handle_request(request: APIRequest,
deps: PipelineDependencies) -> APIResponse` operates exclusively on plain, transport-agnostic dict
structures — it never imports, references, or depends on any web framework, RPC library, or ASGI/WSGI
type. A concrete **transport binding** — a FastAPI route handler, a gRPC servicer method, a CLI command,
a test harness — is a thin translation layer living entirely outside this design's scope: its only job is
(a) parsing whatever wire format it owns into an `APIRequest` dict and (b) serializing the returned
`APIResponse` dict back into that wire format. No transport framework is chosen, implied, or precluded by
this design.

## Request Validation

**Stage 18 validates only request structure, never request semantics.** Structural, deterministic, and
strictly scoped to the shape of `APIRequest` itself — never a semantic/business-logic check any
downstream stage already owns (Responsibilities, Design Decisions #7). This one-sentence boundary is
stated explicitly so a future implementer is never tempted to migrate a retrieval-level or
prompt-level validation rule into this stage — every such rule already has exactly one home, in the
stage that owns it, and moving or duplicating it here would create a second source of truth:

- `query` present, and a string (type only — emptiness/whitespace-only content is never checked here; an
  empty query is Stage 10's own `QUERY_EMPTY` concern, surfaced later as `RetrievalResult.status ==
  "FAIL"`, rolled up like any other downstream failure).
- `index_fingerprints` present, a list, and non-empty (list-emptiness is checked here, since an empty
  list would prevent `build_retrieval_request` from even constructing a well-typed `RetrievalRequest` —
  distinct from `INDEX_FINGERPRINTS_EMPTY`, which is Stage 10's own concern for an index fingerprint that
  *is* present but doesn't resolve to a live index).
- `filters`, if present, is a dict containing only the three recognized keys (`category`, `doc_type`,
  `doc_ids`) — an unrecognized key raises `UNSUPPORTED_OPTION`, never silently ignored or silently
  forwarded.
- `pipeline_options`, if present, is a dict containing only the twelve recognized keys listed in Request
  Schema, each of the documented type when present — an unrecognized key, or a wrong-typed recognized
  key, raises `UNSUPPORTED_OPTION`/`PIPELINE_OPTIONS_MALFORMED` respectively.

Never included, by design: value-range checks that some downstream stage already clamps (`top_k`'s own
`[1, MAX_TOP_K]`, `groundedness_threshold`'s own `[0.0, 1.0]`, etc.) — Stage 18 forwards the raw value and
lets the owning stage's own frozen clamp/default logic run exactly once, never duplicated here.

## Response Serialization

Four guarantees, stated explicitly rather than assumed, matching every earlier stage's own repeated
emphasis on deterministic serialization:

- **Deterministic key order.** `APIResponse` is a plain dict with the fixed, documented key set in
  Response Schema — Stage 18 never reorders or conditionally includes a top-level key based on content;
  the same fixed key order is produced for every outcome (`SUCCESS`, `PARTIAL_SUCCESS`,
  `PIPELINE_FAILURE` alike). Stage 18 itself does not serialize to any wire format (JSON, protobuf, or
  otherwise); that remains the transport binding's own job (API Adapter Abstraction). If a transport
  binding chooses to serialize via `canonical_json` (the same key-sorted convention every prior stage's
  own identity hash already relies on), the resulting bytes are deterministic by construction of that
  function, not by any guarantee Stage 18 itself makes about wire-level byte ordering.
- **UTF-8, NFC preserved.** `query`, `response_text`, and every span's own `text` may contain arbitrary
  Unicode; Stage 18 never re-encodes, re-normalizes (no NFC/NFKC pass of its own), or otherwise alters
  them — the same byte-for-byte preservation rule every prior stage already applies to text it passes
  through. Where a transport binding must produce bytes, UTF-8 is the assumed encoding, matching every
  other text artifact in this pipeline; Stage 18 introduces no second encoding convention.
- **Identical serialization for identical pipeline output.** Given byte-identical upstream objects
  (`retrieval_result` through `quality_report`) and a byte-identical `response_status`,
  `build_api_response()` produces a byte-identical `APIResponse` body every time (`request_id`,
  `received_at`, `resolved_at` excluded, per Determinism's own explicit scope).
- **Immutability.** Once constructed and self-checked by `validate_api_response()`, `APIResponse` is
  never modified — the same documented (not language-enforced) contract every prior stage's own returned
  package already carries.
- **Omission rules.** Every field named in Response Schema is always present — never conditionally
  omitted based on content (e.g., `answer.spans == []` is a valid, present empty list, never a missing
  key). This keeps `APIResponse`'s own shape identical across every possible outcome, simplifying any
  transport binding's own deserialization logic.
- **Null handling.** Stage 18 introduces no new null-vs-omitted convention of its own; a field is `null`
  only where the upstream schema it was copied from already uses `null` for "not applicable under this
  outcome" (e.g., `answer.finish_reason` is `null` when `cached_result.llm_response.status == "SKIPPED"`,
  mirroring `LLMResponse.finish_reason`'s own frozen convention exactly).

## Error Mapping

A closed, three-row, deterministic mapping — never a new judgment, only a relabeling of a value the
frozen chain's own status-passthrough convention has already fully computed by the time it reaches
`AnswerQualityReport.status` (Context, Design Decisions #4):

| `AnswerQualityReport.status` | `APIResponse.status` |
|---|---|
| `PASS` | `SUCCESS` |
| `PARTIAL` | `PARTIAL_SUCCESS` |
| `FAIL` or `SKIPPED` | `PIPELINE_FAILURE` |

**Internal pipeline findings are propagated unchanged. Stage 18 maps only transport status, never
rewrites findings.** Stage 18 never modifies, filters, reorders, or reinterprets any pipeline finding
while performing this mapping — every `findings[]` list from every stage in the chain is carried forward
into `pipeline_findings`, grouped by stage, byte-for-byte (Response Schema). This keeps a hard line
between the one thing Stage 18 is allowed to compute (the transport-facing `status` category) and
everything it is not (any finding's own content or meaning, which remains entirely owned by the stage
that produced it). `APIResponse.status` is a transport-agnostic **category**, deliberately not a literal
HTTP status code or any other framework-specific value — mapping `PIPELINE_FAILURE` to `502` vs. `200`
with an error body, or `PARTIAL_SUCCESS` to `200` vs. `206`, is a transport binding's own decision,
entirely outside this design (Known Limitations).

A malformed `APIRequest` (Request Validation) is a distinct, fourth case — raised as
`APIRequestInputError`, never returned as an `APIResponse` with any `status` value at all (Failure
Handling) — since no pipeline call was ever attempted, there is no pipeline-level status to map.

A genuine internal-invariant exception from any upstream frozen stage (`RetrievalInternalError`,
`ContextAssemblyInternalError`, `PromptConstructionInternalError`, `LLMExecutionInternalError`,
`ResponseCachingInternalError`, `CitationExtractionInternalError`, `GroundednessValidationInternalError`,
`AnswerQualityEvaluationInternalError`) is never expected under correct operation — Stage 18 propagates
it unchanged, wrapped in its own `PipelineOrchestrationError` carrying the original exception, rather
than silently converting a genuine upstream bug into a degraded-but-plausible-looking `APIResponse`
(Failure Handling).

## Correlation / Request IDs

**Generation.** `request_id = assign_request_id()` — a randomly-generated UUID4 string, generated fresh
for every call, with no dependence on `APIRequest` content of any kind. This is a deliberate, named
departure from every prior stage's own "hash the identity-determining inputs" `*_id` convention (Context,
Determinism): two API calls carrying byte-identical `APIRequest` content are still two distinct events a
caller needs to trace independently, and a content-hash `request_id` would silently collapse them.

**Propagation.** `request_id` is never threaded *into* any frozen stage's own call — none of
`retrieve`/`assemble_context`/`construct_prompt`/`execute_with_cache`/`extract_citations`/
`validate_groundedness`/`evaluate_answer_quality`'s own frozen signatures accepts one, and none of their
own internal structured log entries (`pipeline_principles.md` §2's fixed seven-key shape) carries a
`request_id` field. Stage 18 attaches `request_id` only to its own request-scoped log entries and to the
returned `APIResponse` itself — cross-stage log correlation for one call is therefore achievable only by
temporal proximity or an external tracing system, never by a shared `request_id` field inside any
upstream stage's own frozen log shape (Known Limitations).

**Relationship to pipeline ids.** `request_id` is Stage 18's own transport-level correlation id — entirely
separate from, and never a substitute for, any of the seven deterministic pipeline-internal ids surfaced
under `provenance` (`context_package_id`, `prompt_package_id`, `llm_response_id`, `cited_response_id`,
`groundedness_report_id`, `answer_quality_report_id`, plus `cache_key` under `cache`). A caller correlates
one `request_id` to all seven of those for one call by reading them together off one `APIResponse`.

**Reproducibility.** `request_id` is never reproducible — rerunning an identical `APIRequest` produces a
new `request_id` every time. Every pipeline-internal id it is returned alongside remains exactly as
reproducible as its own owning stage already guarantees; on a cache hit, two different `request_id`s can
legitimately be paired with the identical `llm_response_id`/`cache_key` — a deliberate, useful signal
that two distinct calls hit the identical cached answer, not a bug.

## Streaming Strategy

**Stage 18 returns complete responses only. Incremental token streaming is intentionally outside this
architecture and belongs to a future extension.** Excluded, explicitly, not deferred by silent omission.
Stage 13 is frozen as a single, fully-materialized, non-streaming request/response call (Stage 13's own
Scope: "Stage 13 always returns one fully-materialized result per request... never an architectural
surface Stage 13 exposes"); every object Stage 18 assembles from — `CachedExecutionResult`,
`CitedResponse`, `GroundednessReport`, `AnswerQualityReport` — likewise only ever exists as one complete
object, never a partial or in-progress one. There is no partial-result signal anywhere in the frozen
chain for Stage 18 to forward even if it wanted to. Introducing real token-level streaming would require
reopening Stage 13's own frozen `LLMAdapter` contract to add a streaming transport surface — the Stage 14
Roadmap Definition Pass already names exactly this as Stage 20 (Tool/Function Calling)'s own territory,
"the riskiest item... because it revises an earlier frozen contract," deliberately scoped last among the
near-term items. Stage 18 does not anticipate, partially design around, or leave a hook for a future
streaming capability; introducing one is a new, separate design pass against Stage 13 (or a genuinely new
stage), never a silent extension of this one — stated here unambiguously to avoid future scope creep.

## Design Decisions

1. **Stage 18 is this pipeline's first true end-to-end orchestrator, resolving the task brief's own
   under-specified "Invoke Stage 17" lifecycle step into its necessary full form.** No stage from Stage
   10 through Stage 17 calls another; nothing upstream threads a query all the way to a cited,
   groundedness-checked, quality-scored answer in one call. Stage 17 alone cannot produce that answer —
   it only wraps Stage 13. Stage 18's own Request Lifecycle therefore calls Stage 10, 11, 12, 17, 14, 15,
   and 16, in that fixed order, each one exactly once, each one's own already-frozen public entrypoint
   completely unmodified.
2. **`manifest.json`, every corpus artifact, and every prompt template file are never opened by Stage 18
   directly.** Every one of them is already owned and read by whichever frozen stage needs it (Stage 10
   for the manifest and vector index, Stage 12 for prompt templates) — Stage 18 only ever calls that
   stage's own already-frozen entrypoint and receives its already-assembled output back.
3. **No new pluggable "APIAdapter" backend contract, unlike `ProviderAdapter`/`IndexAdapter`/
   `LLMAdapter`/`CacheAdapter`.** A transport boundary has no shared interchangeable-operation shape the
   way an embedding provider, a vector index backend, an LLM provider, or a cache store each do —
   framework-independence is achieved structurally instead, via `handle_request()`'s own plain-dict-only
   signature (API Adapter Abstraction).
4. **`APIResponse.status` requires no new judgment — it is a three-row relabeling of
   `AnswerQualityReport.status`, itself already the fully-rolled-up terminus of every upstream stage's
   own pure-passthrough `status` convention.** Stage 11 through Stage 16 each already established "status
   is inherited, never independently recomputed" (with Stage 13 the sole exception, computing its own
   status from a live network outcome, itself then passed through unchanged by every stage after it).
   Stage 18 adds no new FAIL/PARTIAL condition of its own at the pipeline-outcome level — its own
   `findings[]` (Validation §2) are informational only.
5. **`PipelineDependencies` carries only what each frozen stage's own contract literally requires as a
   parameter, and nothing more.** `retrieve` is injected as an opaque, pre-configured callable (never as
   raw adapter factories plus a manifest path) because `retrieve(request)`'s own frozen signature takes
   exactly one argument — Stage 18 has no visibility into, and makes no assumption about, how Stage 10
   itself resolves its own adapters or manifest internally. `llm_adapter`/`cache_adapter` are injected
   directly because Stage 17's own frozen `execute_with_cache()` signature names them explicitly as
   parameters. Stage 11/12/14/15/16 receive nothing injected, since none of their own frozen
   Configuration sections names an adapter of any kind.
6. **`default_model_name` is the one deployment-level default Stage 18 itself supplies, and the only
   one.** Every other `pipeline_options` field defers entirely to its owning stage's own already-frozen
   default/clamp logic when omitted (`None` passed straight through) — `model_name` is the sole exception
   because `LLMExecutionConfig.model_name` has no default anywhere in the frozen chain (Stage 13's own
   Schemas: "required — no default; a caller must always name a model"). Supplying this one fallback at
   the deployment level, rather than requiring every external caller to always name a model explicitly,
   is judged the right tradeoff for a network-facing API — but it is stated as a deliberate, narrow
   exception, never generalized to any other field.
7. **Request validation is purely structural; it never re-implements a semantic check a downstream stage
   already owns.** An empty `query` string, an unresolvable `index_fingerprint`, an invalid
   `groundedness_threshold` outside `[0.0, 1.0]` — every one of these is already a named, deterministic
   finding or clamp in some frozen stage's own Validation/Configuration section. Stage 18 checking any of
   them a second time would either duplicate logic (a maintenance risk: two places that must agree) or
   risk disagreeing with the owning stage's own frozen behavior. Stage 18's own Request Validation is
   confined to what only *it* can check: is this dict shaped like a well-formed `APIRequest` at all.
8. **`APIResponse` deliberately duplicates upstream content, breaking every internal stage's own
   minimality convention — because it is this pipeline's first and only externally-facing terminus.**
   Stage 15/16 each read a field but declined to re-state it because a caller could always read it off
   the upstream object directly (linked by id). An external API caller has no such channel — there is no
   way for them to separately fetch a `GroundednessReport` or `AnswerQualityReport`, since neither is ever
   persisted (Stage 15/16's own Outputs). `APIResponse` therefore flattens every content-bearing field a
   caller could plausibly need directly into its own `answer`/`groundedness`/`quality` sections, while
   still excluding what remains genuinely redundant (raw upstream objects, their own internal pipeline
   versions and timestamps, already-echoed threshold values) — see Response Schema.
9. **`request_id` is randomly generated, never a content hash — this pipeline's second and final,
   explicitly-named exception to Principle 1, after Stage 13's `response_text`.** Every prior `*_id`
   field could safely be, and was, a deterministic hash precisely because sameness of input was supposed
   to mean sameness of id (that is exactly what makes Stage 17's own cache key useful). `request_id`
   needs the opposite property: two calls with identical content must still be traceable as two distinct
   events. Naming this precisely, rather than silently making `request_id` a hash (which would quietly
   break correlation) or silently making it random without ever discussing Principle 1 (which would leave
   an unstated inconsistency), is judged the only honest choice, mirroring exactly how Stage 13 named its
   own `response_text` exception (Determinism, Correlation IDs).
10. **`APIResponse` is fully in-memory, never persisted by Stage 18 itself as a distinct artifact** —
    matching the zero-artifact posture Stage 10 through Stage 16 each already established for their own
    return value (Stage 17 is the one exception, owning its cache store, which Stage 18 never touches
    directly). Whether or how a transport binding logs, stores, or forwards a returned `APIResponse` is
    entirely outside this design's scope.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md` §4's
Critical/Recoverable document-quarantine model, since Stage 18 has no document to quarantine and no
persisted-per-document artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10
through Stage 17 each already gave for their own Validation sections).

**1. Input validation codes** — raised, never returned as part of any `APIResponse`:

| Code | Raised as | Trigger |
|---|---|---|
| `QUERY_MISSING_OR_INVALID_TYPE` | `APIRequestInputError` | `request["query"]` is absent or not a string |
| `INDEX_FINGERPRINTS_MISSING_OR_EMPTY` | `APIRequestInputError` | `request["index_fingerprints"]` is absent, not a list, or an empty list |
| `UNSUPPORTED_OPTION` | `APIRequestInputError` | `filters` or `pipeline_options` contains a key outside its own documented, closed set |
| `PIPELINE_OPTIONS_MALFORMED` | `APIRequestInputError` | a recognized `pipeline_options` key is present with a wrong type |

**2. Package-level findings** — recorded in `APIResponse.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `PIPELINE_STATUS_PARTIAL` | WARNING | package | `AnswerQualityReport.status == "PARTIAL"`; `APIResponse.status = PARTIAL_SUCCESS` |
| `PIPELINE_STATUS_FAILED` | WARNING | package | `AnswerQualityReport.status in {"FAIL", "SKIPPED"}`; `APIResponse.status = PIPELINE_FAILURE` |
| `MODEL_NAME_DEFAULTED` | INFO | package | `pipeline_options.model_name` was omitted; `deps.default_model_name` was used instead |

Neither `PIPELINE_STATUS_PARTIAL` nor `PIPELINE_STATUS_FAILED` is itself the source of truth for
`APIResponse.status` — both are informational restatements of a value Error Mapping already computed
directly from `AnswerQualityReport.status`; a finding never independently drives `status` the way it does
in this design's own package-level findings elsewhere (contrast Stage 10 through Stage 17, where a
finding can be the *reason* a status was set, not merely an echo of it) — Stage 18's own status is fully
determined before any of its own findings are even constructed.

**3. Internal invariant codes** — raised by `validate_api_response()`, run unconditionally on the
assembled response before it is ever returned; never returned as part of any `APIResponse`:

| Code | Trigger |
|---|---|
| `RESPONSE_STATUS_MAPPING_MISMATCH` | `response["status"]` does not equal `map_pipeline_status(quality_report["status"])`, recomputed fresh |
| `PROVENANCE_ID_CHAIN_BROKEN` | any of `context_package_id`/`prompt_package_id`/`llm_response_id`/`cited_response_id`/`groundedness_report_id`/`answer_quality_report_id` under `provenance` disagrees with the corresponding id on the object that produced it |
| `ANSWER_TEXT_MISMATCH` | `answer["response_text"] != cached_result["llm_response"]["response_text"]` |
| `SPANS_MISMATCH` | `answer["spans"] != cited_response["spans"]` |
| `REQUEST_ID_MISSING_OR_MALFORMED` | `response["request_id"]` is absent, empty, or not a valid UUID4-shaped string |
| `PIPELINE_FINDINGS_INCOMPLETE` | `pipeline_findings` is missing any of the seven documented per-stage keys, or any key's own list does not exactly match the corresponding stage's own `findings`/`llm_findings`/`citation_findings`/`groundedness_findings` list |

Any of these six raises `APIResponseInternalError` rather than being returned as a malformed
`APIResponse` — the same fail-loud posture as every prior stage's own internal-invariant exceptions, and
never expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage18_api_response_serving"`, `doc_id: null` always —
entries are request-scoped, not document-scoped). New codes this stage adds:
`INFO_MODEL_NAME_DEFAULTED`, `WARNING_PIPELINE_STATUS_PARTIAL`, `WARNING_PIPELINE_STATUS_FAILED`. No new
`FATAL_*` code — Stage 18 never sets a manifest `error_code`, since it never touches the manifest at all
(see Manifest Interaction). `request_id` is included only inside these entries' own `event`/message
content, never as a new top-level key on the shared seven-field log shape (Correlation IDs, Known
Limitations).

## Manifest Interaction

None, directly. Stage 18 never opens, reads, or writes `manifest.json` itself — every manifest read is
already performed internally by whichever frozen stage needs it (Stage 10). This extends the
zero-manifest-interaction posture Stage 11 through Stage 17 each already established, one further layer
downstream, at the orchestration level rather than the leaf-stage level.

## Artifact Interaction

None, directly. Stage 18 performs zero local file reads and zero local file writes of its own; every
corpus artifact, vector index, and prompt template read happens entirely inside whichever frozen stage
already owns it. The one genuinely new I/O this stage *triggers* (never performs itself) is whatever
Stage 17's own `cache_adapter.put()` may do on a miss — Stage 18 calls `execute_with_cache()` exactly
once per request and never inspects, bypasses, or duplicates its own internal cache-write decision.

## Directory Structure

None added. Stage 18 introduces no new artifact directory — there is no artifact of its own.

## Determinism

Stage 18 is the third stage in this pipeline (after Stage 13 and Stage 17) to draw an explicit line
between what it guarantees deterministic and what it does not — for a third, distinct reason: Stage 13's
non-determinism is inherent to LLM sampling; Stage 17's is inherent to a stateful cache; Stage 18's is a
deliberate design choice about what `request_id` needs to mean (Context, Correlation IDs).

**Scope of the determinism guarantee, stated explicitly so this section is never read as contradicting
Correlation IDs' own claim that `request_id` is intentionally random:** determinism applies to the
serialized response *body* — every field derived from the pipeline's own already-computed output
(`answer`, `groundedness`, `quality`, `cache`, `provenance`, `pipeline_findings`) — excluding
transport-generated metadata that exists only to identify or timestamp this one call
(`request_id`, `received_at`, `resolved_at`). Principle 1's byte-identical-output guarantee is therefore
not violated by this stage; it is scoped precisely to the content a caller actually asked for, the same
way Stage 13 scoped its own exception to `response_text` alone rather than to the whole `LLMResponse`.

**Deterministic (guaranteed, byte-identical across runs, given identical input, identical cache state,
and an identical `request_id`):**
- **Request Lifecycle ordering and argument-passing.** Given an identical `(APIRequest,
  PipelineDependencies)` and an identical downstream cache state, every argument passed to every stage in
  the chain (Steps [3]–[11]) is byte-identical every time.
- **Status mapping.** `map_pipeline_status` is a pure, three-row, total function of
  `AnswerQualityReport.status` alone (Error Mapping) — no randomness, no external state.
- **Response assembly, given an identical set of upstream objects.** `build_api_response` is a pure
  function of its own arguments; identical upstream objects always produce a byte-identical
  `APIResponse`, `request_id`/`received_at`/`resolved_at` aside.
- **`validate_api_response()`'s own outcome.** Identical `APIResponse` content always produces an
  identical validation outcome.

**Explicitly NOT deterministic (by design, or inherited unchanged from an upstream stage; never assumed,
never hidden):**
- **`request_id`.** Randomly generated, fresh per call, by design (Correlation IDs) — this pipeline's
  second and final explicit exception to Principle 1.
- **`received_at`, `resolved_at`.** Wall-clock by definition; excluded from every determinism comparison,
  the same treatment every prior stage already gives its own timestamp field.
- **Cache hit/miss outcome, and everything downstream of it.** Inherited unchanged from Stage 17's own
  explicit non-determinism (Stage 17's Determinism) — whether a given call reaches Stage 13 at all
  depends on the cache store's own prior contents, entirely outside Stage 18's own control.
- **`response_text`, `finish_reason`, token counts, `latency_ms`, `attempt_count`,
  `provider_request_id`.** Inherited unchanged from Stage 13's own explicit non-determinism, passed
  through every stage after it without alteration.

## Read-Only Guarantees

Stage 18 never modifies `manifest.json`, any `RetrievalResult`, `ContextPackage`, `PromptPackage`,
`CachedExecutionResult`, `LLMResponse`, `CitedResponse`, `GroundednessReport`, `AnswerQualityReport`, any
chunk, any metadata, any vector index, or any embedding. No upstream artifact or in-memory object is ever
mutated by Stage 18 itself. The one inherited, indirect exception: Stage 18's own call to
`execute_with_cache()` may cause Stage 17 to write a fresh cache entry, exactly as it would for any other
caller of that already-frozen contract — Stage 18 triggers this by calling Stage 17 normally, it does not
perform, bypass, or duplicate the write itself (Artifact Interaction, mirrors Stage 17's own Design
Decisions #2 one layer further downstream).

## Failure Handling

- **A malformed `APIRequest`** (missing/wrong-typed `query`/`index_fingerprints`, an unsupported
  `filters`/`pipeline_options` key, or a wrong-typed recognized `pipeline_options` value) —
  `APIRequestInputError` raised immediately, with the matching code; no pipeline call is ever made, no
  `APIResponse` is returned.
- **`RetrievalResult.status == "FAIL"`** (e.g., an empty query, no resolvable index) — the chain proceeds
  normally through every remaining stage (each already handles an empty/FAIL upstream input gracefully,
  per its own frozen Failure Handling); `AnswerQualityReport.status` ends up `FAIL`;
  `APIResponse.status = PIPELINE_FAILURE`; every stage's own `findings[]` — including Stage 10's own
  specific reason — is fully visible under `pipeline_findings.retrieval`.
- **`LLMResponse.status == "SKIPPED"`** (Stage 12's own `PromptPackage.status == "FAIL"` reached Stage 13
  via Stage 17) — the chain still proceeds through Stage 14/15/16, each of which already handles a
  `SKIPPED`/`FAIL` upstream input gracefully (empty spans, vacuous scores); `AnswerQualityReport.status`
  stays `SKIPPED`; `APIResponse.status = PIPELINE_FAILURE`.
- **A cache hit** — `execute_with_cache()` never calls Stage 13 at all; Stage 18's own Request Lifecycle
  is otherwise identical — Steps [9]–[13] proceed exactly as on a miss, operating on the cached
  `llm_response` exactly as if it had just been generated.
- **`pipeline_options.model_name` omitted** — `deps.default_model_name` is used instead;
  `MODEL_NAME_DEFAULTED` INFO finding recorded; every other omitted `pipeline_options` field is simply
  passed through as `None` to its owning stage, deferring entirely to that stage's own default (no Stage
  18 finding is recorded for any of the other eleven).
- **A genuine internal-invariant exception from any frozen upstream stage** — never caught or converted;
  propagated as `PipelineOrchestrationError`, wrapping the original exception; no `APIResponse` is
  returned (Error Mapping).
- **A genuine Stage 18 bug** (one of the six named internal invariant codes in Validation §3) —
  `APIResponseInternalError` raised, not returned as a malformed `APIResponse`.

## Configuration

`PipelineDependencies` — supplied once, at deployment/wiring time, never per-request:

```jsonc
{
  "retrieve": "<Callable[[RetrievalRequest], RetrievalResult]>",  // a pre-configured Stage 10 entrypoint
  "llm_adapter": "<LLMAdapter>",                                   // Stage 13's own frozen contract
  "cache_adapter": "<CacheAdapter>",                                // Stage 17's own contract
  "default_model_name": "claude-..."                                // required; the sole deployment-level
                                                                     // fallback this stage itself defines
}
```

Every `pipeline_options` field is per-request configuration, never defaulted from any global or
environment state, except `model_name`'s own single documented fallback above — the same per-request
convention Stage 10 through Stage 17 each already established for their own tunables, extended here at
the orchestration level. Stage 18 never imports a specific transport framework, LLM provider SDK, cache
backend, or vector index library by name anywhere in its own orchestration path.

**Pipeline dependency ownership — stated as one table, removing any ambiguity about which stage owns
which logic:**

| Dependency | Owning stage |
|---|---|
| Retrieval | Stage 10 |
| Context assembly | Stage 11 |
| Prompt construction | Stage 12 |
| Cache lookup / LLM execution | Stage 17 (wrapping Stage 13) |
| Citation extraction | Stage 14 |
| Groundedness validation | Stage 15 |
| Answer quality evaluation | Stage 16 |

Stage 18 itself owns none of the logic in the right-hand column — it owns only the fixed sequencing of
calls into it (Request Lifecycle) and the assembly of the final response (Response Schema).

## Concurrency

Fully safe under concurrent calls, inheriting exactly the concurrency guarantees of every stage it calls:
Stage 18 itself performs zero writes and holds no shared mutable state of its own — `handle_request()` is
a pure orchestration function over its own arguments plus whatever each frozen stage it calls does
internally. Stage 10 through Stage 16 are each independently safe under concurrency (their own
Concurrency sections); Stage 17's own documented "cache stampede" limitation (two concurrent identical
calls may both miss and both invoke Stage 13) applies unchanged here — Stage 18 adds no additional
coordination of its own, and does not attempt to.

## Security Considerations

- **Untrusted external input.** `query` and every `filters`/`pipeline_options` value originate from an
  external, potentially adversarial caller — Request Validation checks shape only; Stage 18 performs no
  content sanitization, injection defense, or intent inspection of `query` itself (that risk is the same
  one Stage 10 already accepts for query text, and Stage 12 already accepts for corpus content embedded
  in a prompt — neither is newly introduced here).
- **Untrusted model output, inherited.** `response_text` and every span's own `text` remain opaque,
  model-generated content, now additionally exposed directly to an external caller via `APIResponse` —
  the same "potentially adversarial input to whatever consumes it next" risk Stage 13 first accepted
  (Stage 13's own Design Decisions #11), now terminating at this pipeline's actual external boundary. Any
  defense against a caller-facing prompt-injection payload (output encoding, content-security policies,
  client-side rendering precautions) is entirely the transport binding's own concern, outside this
  design.
- **Credential handling.** `llm_adapter`/`cache_adapter` (and whatever Stage 10 itself was wired with)
  are deployment-level `PipelineDependencies`, never exposed on `APIRequest` or `APIResponse`, never
  logged by Stage 18 itself.
- **No local write capability of its own anywhere in this design** — the one write Stage 18 can trigger
  (Stage 17's own cache write) is entirely Stage 17's own already-frozen, already-reviewed behavior;
  Stage 18 adds no new write surface.

## Public Function Contracts

- `validate_api_request(request: APIRequest) -> None` — Stage 18's own structural input check (Request
  Validation); raises `APIRequestInputError` (one of the four codes in Validation §1) on violation.
- `assign_request_id() -> str` — returns a fresh, random UUID4 string; total (always succeeds); the one
  function in this stage's own contract that is intentionally non-deterministic (Correlation IDs).
- `build_retrieval_request(request: APIRequest) -> RetrievalRequest` — maps `query`,
  `index_fingerprints`, `filters`, and `pipeline_options.top_k` into Stage 10's own frozen request shape;
  pure function of its one argument.
- `resolve_execution_config_for_api(request: APIRequest, deps: PipelineDependencies) ->
  LLMExecutionConfig` — returns a dict with `model_name` defaulted from `deps.default_model_name` when omitted, and every other field passed through as given. (Note: The return type is not `Optional` because Stage 13 specifies `model_name` is strictly required and has no fallback; thus Stage 18 must always resolve and supply at least the model name).
- `map_pipeline_status(answer_quality_status: str) -> str` — the fixed three-row mapping (Error Mapping);
  pure, total function of its one argument.
- `build_api_response(request_id: str, received_at: str, resolved_at: str, retrieval_result: RetrievalResult, context_package: ContextPackage,
  prompt_package: PromptPackage, cached_result: CachedExecutionResult, cited_response: CitedResponse,
  groundedness_report: GroundednessReport, quality_report: AnswerQualityReport, response_status: str, findings: List[Dict[str, str]]) ->
  APIResponse` — assembles the final response (Response Schema); pure function of its own arguments.
- `validate_api_response(response: APIResponse, quality_report: AnswerQualityReport, retrieval_result: RetrievalResult, context_package: ContextPackage, prompt_package: PromptPackage, cached_result: CachedExecutionResult, cited_response: CitedResponse, groundedness_report: GroundednessReport) -> None` — internal invariant self-check; raises
  `APIResponseInternalError` (one of the six named codes in Validation §3) on violation. (Note: Upstream objects are required as parameters because the specified invariant checks mathematically require comparing the assembled response against the original upstream payload, rather than weakening the check to only test the response's internal shape).
- `handle_request(request: APIRequest, deps: PipelineDependencies) -> APIResponse` — the sole public
  entrypoint; orchestrates the Request Lifecycle [1]–[14] in full; the only Stage 18 function that
  actually invokes any other stage.

## Constants

```python
API_PIPELINE_VERSION = "1.0.0"
SUPPORTED_FILTER_KEYS = ("category", "doc_type", "doc_ids")
SUPPORTED_PIPELINE_OPTION_KEYS = (
    "top_k", "context_budget_tokens", "template_version", "prompt_budget_tokens",
    "model_name", "temperature", "max_output_tokens", "timeout_seconds", "max_retry_attempts",
    "cache_ttl_seconds", "citation_match_threshold", "groundedness_threshold",
)
```

No numeric threshold, ceiling, or default of its own is defined here — every one Stage 18 might otherwise
need (`top_k`'s ceiling, `groundedness_threshold`'s range, etc.) already lives, exactly once, in the
frozen stage that owns it (Design Decisions #7); duplicating any of them here would create two sources of
truth that could silently drift apart.

## Known Limitations

- **`request_id` cannot be propagated into any upstream stage's own frozen structured log shape.**
  `pipeline_principles.md` §2's seven-key Logging Specification is shared, frozen infrastructure this
  design does not modify; cross-stage log correlation for one call relies on temporal proximity or an
  external tracing system, never a shared `request_id` field inside a frozen stage's own log entry
  (Correlation IDs).
- **`APIResponse.status`'s three values are a category, not an HTTP status code or any other
  transport-specific value.** A transport binding must supply its own mapping (e.g., `PIPELINE_FAILURE`
  → `502` vs. a `200` with an error body) — this design deliberately does not make that choice (Error
  Mapping).
- **No streaming, at all, by design — not a deferred feature.** Reintroducing it requires reopening Stage
  13's own frozen contract, explicitly reserved for a future Stage 20 design (Streaming Strategy).
- **A cache hit's own `latency_ms`/`attempt_count`/`provider_request_id`, inherited via `answer` and
  `cache`, describe the original miss that produced the cached entry, never the current call** — the same
  limitation Stage 17 already names one layer upstream, now visible directly to an external caller.
- **No rate limiting, authentication, or authorization of any kind.** This design defines only what
  happens *after* a request is accepted; gating who may call `handle_request()` at all, and how often, is
  entirely a transport binding's or deployment's own concern, never addressed here.
- **`default_model_name` is a single, global fallback — not per-caller or per-tenant configurable** at
  this design's own layer; a deployment needing different default models for different callers would need
  to resolve that before constructing `PipelineDependencies`, outside this design's scope.

## Accepted Tradeoffs

- **No new pluggable "APIAdapter" backend contract.** Simpler, and honest about a genuine architectural
  difference (a transport boundary isn't an interchangeable-operation backend) — accepts that a caller
  must write their own thin, framework-specific translation layer, entirely outside this design (API
  Adapter Abstraction).
- **`request_id` is random, not a content hash.** Breaks this pipeline's otherwise-universal "identical
  input, identical id" convention, deliberately, for the one field where that convention would actively
  hurt correlation (Design Decisions #9).
- **`APIResponse` deliberately duplicates upstream content.** A departure from every internal stage's own
  minimality convention, accepted because Stage 18 is this pipeline's only externally-facing terminus —
  there is no other channel for a caller to reach the data (Design Decisions #8).
- **One deployment-level `default_model_name` fallback**, rather than requiring every external caller to
  always name a model. Simpler for a typical API caller, at the cost of one narrow, explicitly-named
  exception to the "every default already lives in its owning stage" rule (Design Decisions #6, #7).
- **No rate limiting, auth, or streaming.** Each is a deliberate scope limit, not an oversight — bounding
  Stage 18 to "orchestrate the frozen pipeline and serialize its result" keeps this stage's own contract
  small and matches the task brief's own explicit exclusions.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not this
document.

- A malformed `APIRequest` (any of the four named input-validation conditions) is rejected
  deterministically, every time, without any downstream stage being called and without any `APIResponse`
  being produced.
- Given an identical `(APIRequest, PipelineDependencies)` and an identical cache state, every argument
  passed to `retrieve`/`assemble_context`/`construct_prompt`/`execute_with_cache`/`extract_citations`/
  `validate_groundedness`/`evaluate_answer_quality` is byte-identical across repeated calls.
- `APIResponse.status` always equals `map_pipeline_status(quality_report["status"])` recomputed fresh,
  for each of `PASS`/`PARTIAL`/`FAIL`/`SKIPPED`.
- Every `provenance` id (`context_package_id`, `prompt_package_id`, `llm_response_id`,
  `cited_response_id`, `groundedness_report_id`, `answer_quality_report_id`) always equals the
  corresponding field on the object that produced it — never re-derived, never independently computed.
- `answer.response_text` is always byte-identical to `cached_result.llm_response.response_text`;
  `answer.spans` is always byte-identical to `cited_response.spans`.
- `pipeline_findings` always contains exactly the seven documented keys, each holding exactly the
  corresponding stage's own `findings`/`llm_findings`/`citation_findings`/`groundedness_findings` list,
  verbatim.
- `pipeline_options.model_name` omitted always results in `deps.default_model_name` being passed as
  `LLMExecutionConfig.model_name`, with `MODEL_NAME_DEFAULTED` recorded; every other omitted
  `pipeline_options` field always results in `None` being passed through to its owning stage, with no
  Stage 18 finding recorded for that omission.
- A cache hit (Stage 17) results in zero calls to `deps.llm_adapter.invoke()` for that request, verifiable
  via a call-count assertion, while every other Request Lifecycle step still runs normally.
- Every one of the six internal invariant codes (`RESPONSE_STATUS_MAPPING_MISMATCH`,
  `PROVENANCE_ID_CHAIN_BROKEN`, `ANSWER_TEXT_MISMATCH`, `SPANS_MISMATCH`,
  `REQUEST_ID_MISSING_OR_MALFORMED`, `PIPELINE_FINDINGS_INCOMPLETE`) fires under its documented condition
  and only that condition.
- `request_id` is confirmed different across two calls sharing byte-identical `APIRequest` content.
- Immutability: `APIRequest`, `PipelineDependencies`, and every object returned by an intermediate stage
  are never mutated by any Stage 18 function.
- No file, manifest, or network endpoint is ever touched directly by any Stage 18 function — every I/O
  observed during a `handle_request()` call is attributable entirely to one of the frozen stages it
  calls, verifiable via call-count/no-direct-I/O assertions against stub versions of every injected
  dependency.

## Real Corpus Verification

Against a real deployment wiring (`PipelineDependencies` built from the live Stage 10 → 17 chain, a real
or realistic contract-conformant `LLMAdapter`/`CacheAdapter`): a representative real `APIRequest` (a real
`query` against a real, live `index_fingerprint`) produces a well-formed `APIResponse` with
`status == "SUCCESS"`, non-empty `answer.response_text`, at least one span under `answer.spans`, and every
`provenance` id resolvable back to the real object that produced it; a request naming a nonexistent
`index_fingerprint` still produces a well-formed `APIResponse` (never an exception) with
`status == "PIPELINE_FAILURE"` and Stage 10's own `INDEX_NOT_FOUND`/empty-searched-fingerprints reasoning
visible under `pipeline_findings.retrieval`; two back-to-back identical real requests against the same
live cache produce two `APIResponse`s with two different `request_id`s but an identical
`provenance.llm_response_id`/`cache.cache_key`, the second call's `cache.cache_hit == true`; a malformed
`APIRequest` (missing `query`) never reaches any real stage, verified via a zero-call assertion against
the real `retrieve` entrypoint.

**Determinism, explicitly:** like Stage 13 and Stage 17, this section cannot state "two identical calls
always produce a byte-identical result" for `APIResponse` as a whole — `request_id`,
`received_at`/`resolved_at`, and everything inherited from Stage 13/17's own non-determinism differ.
Instead: two identical calls are confirmed to (a) send byte-identical arguments to every intermediate
stage, (b) produce an identical `provenance` id set whenever the cache state is identical, and (c) each
independently satisfy every Validation §3 invariant.

Immutability: the input `APIRequest` and `PipelineDependencies` objects, and every real upstream artifact
(`manifest.json`, every `chunks.json`, `embeddings.parquet`, `metadata.json`, everything under
`vector_index/`, every on-disk prompt template file, and the cache store's own contents beyond the one
expected new entry on a miss) are confirmed byte-identical/consistent before and after each call.

## Future Stage Boundaries

Stage 19+ (not designed here) owns everything Stage 18 deliberately excludes:

- **Stage 19 — Conversation Memory / Multi-Turn Orchestration** owns session-level state across repeated
  calls to `handle_request()` — Stage 18 itself is fully stateless between calls (beyond whatever Stage
  17's own cache store already persists, keyed by request content, never by session); a future
  conversation layer sits *above* Stage 18, calling it once per turn, never modifying it.
- **Stage 20 — Tool/Function Calling** owns extending the LLM invocation model itself, requiring a
  revision to Stage 13's own frozen `LLMAdapter` contract — entirely out of scope here; Stage 18 only
  ever reaches Stage 13 indirectly, through Stage 17's own unmodified `execute_with_cache()`.
- **Stage 21 — Agent Planning** owns multi-step autonomous reasoning built on Stage 19 and Stage 20 — no
  part of that responsibility is touched here.
- Real-time token streaming to a caller, should it ever be introduced, requires its own new design against
  Stage 13's own frozen contract (Streaming Strategy), never a silent extension of Stage 18.
- Authentication, authorization, and rate limiting are entirely a transport binding's or deployment's own
  concern, never addressed by any stage in this pipeline.

Stage 18 hands an `APIResponse` back in memory to whichever transport binding called `handle_request()`;
how that binding serves it over HTTP/gRPC/any other wire protocol, authenticates the caller, rate-limits
requests, or builds a multi-turn conversation on top of it is entirely out of this design's scope.
