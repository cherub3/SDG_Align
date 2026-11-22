# Phase 1.2 — LLM Provider Architecture

Stages 0–21, Phase 1.1 (Configuration Layer), and Phase 1.3 (Embedding Provider Architecture) remain
completely frozen; nothing below proposes any change to existing code or shipped docs. Phase 1.2
defines the architecture for a **concrete** implementation of the abstract `LLMAdapter` contract Stage
13 already declares (`docs/architecture/stage13_llm_execution.md` §"Backends",
`scripts/stage13_llm_execution.py:67`), registered under the `LLM_PROVIDER` seam Phase 1.1 already
recognizes (`SUPPORTED_SEAMS`).

**Provider-neutrality, stated once, governing this entire document, exactly as Phase 1.3 already
established for its own seam:** provider-specific terminology, SDK behavior, request formats, native
finish-reason vocabularies, and configuration field names may appear only as illustrative examples
(Gemini, OpenAI, Anthropic, or any other named only for illustration). Normative behavior — the
adapter contract, the identity split defined below, the exception taxonomy, the field-ownership rules
— must never depend on any specific vendor's semantics.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Stage 13's own Configuration section states the `LLMAdapter` contract in full and requires that "the
adapter itself (or a factory producing one) is likewise runtime-supplied, never hard-coded... Stage 13
never imports a specific provider SDK by name in its own orchestration path." Phase 1.1 closes the
*wiring* half of that gap — it defines how a concrete adapter, once it exists, is supplied to Stage 13
as configuration (`LLM_PROVIDER` seam, `ProviderSettings`, `wire_dependencies()`). Neither Stage 13 nor
Phase 1.1 defines what a concrete adapter itself must do internally to be a correct, safe,
production-grade implementation of that contract. That is the entire, narrow gap Phase 1.2 closes.

Phase 1.2 does not implement any adapter. It defines: (1) the architecture any concrete `LLMAdapter`
implementation must follow — SDK client ownership and lifecycle, credential consumption, the split
between an adapter's own stable identity and a per-request model identity, and per-field ownership of
every value a concrete implementation must produce on `RawLLMResult`; (2) the `ProviderRegistration`
contract a concrete implementation supplies to Phase 1.1's `build_provider_registry()`; and (3) the
exception-raising discipline a concrete implementation's `invoke()` must follow, translating real SDK
failures into exactly one of Stage 13's four already-closed exception types, without ever implementing
the retry loop that consumes them.

Phase 1.2 is architecturally close in shape to Phase 1.3's own Embedding Provider Architecture — both
close the identical kind of gap for a different seam — but Stage 13's actual, frozen contract differs
from Stage 8's in ways this document states explicitly rather than silently porting over Phase 1.3's
own shape:

1. **Failure classification is a typed-exception hierarchy, not a boolean classifier.** Stage 8's
   `ProviderAdapter.is_transient_error(exception) -> bool` has no analog on `LLMAdapter`. A concrete
   implementation translates real SDK exceptions into one of four types by *raising* the correct one
   from `invoke()`; Stage 13's own `map_adapter_error()` performs a fixed, total mapping from exception
   type to finding code, never inspecting a message string (Adapter Contract, Failure Handling).
2. **`model_name` is per-request configuration, never a per-adapter-instance property.** Unlike Stage
   8, where `model_name`/`model_version` are fixed properties of the constructed adapter, Stage 13's
   `LLMExecutionConfig.model_name` is supplied fresh on every `invoke()` call, with no default. This
   document therefore defines two distinct identity concepts rather than one triple (Provider Model).
3. **No `config_fingerprint_fields` analog exists.** `LLMResponse` is fully in-memory with no
   persisted artifact and no config-fingerprint concept of any kind; this document does not invent one
   (Determinism).
4. **`RawLLMResult`'s six fields each carry their own, individually stated ownership rule** — including
   two fields with an explicit normalization requirement (`finish_reason`, and the three token-count
   fields taken together) that Stage 8's own `embed_batch()` return shape never needed, since a vector
   list carries no comparable per-field ambiguity (Provider Model — RawLLMResult Mapping).

**Boundary rule, stated once, governing this entire document:** Stage 13's `LLMAdapter`/`RawLLMResult`/
exception-type contract is frozen and is never re-defined, extended, or altered here — it is quoted,
cited, and built against. Phase 1.1's `ApplicationSettings`/`ProviderSettings`/`ProviderRegistration`/
`wire_dependencies()` contracts are equally frozen and are never re-defined here. Phase 1.2 is the
thing standing between them: it describes how a real, concrete class satisfies the first contract
while being correctly constructible by the second.

## Scope

Phase 1.2 answers exactly one question — given a `ProviderSettings` object and (if `credential_ref`
was present) a resolved raw credential string, supplied by Phase 1.1's `wire_dependencies()` exactly
as its own Public Function Contracts already describe, what is the architecture of a concrete class
that (a) satisfies Stage 13's frozen `LLMAdapter` contract, (b) owns exactly one SDK client for its own
lifetime, and (c) can be supplied to `build_provider_registry()` as a `ProviderRegistration` — and
stops there.

It never selects which provider is active for the `LLM_PROVIDER` seam (Phase 1.1's own job, via
`ApplicationSettings`). It never constructs a prompt, assembles context, or budgets a prompt against a
token ceiling (Stage 12's own frozen job, restated in Non-Responsibilities and Future Phase
Boundaries). It never modifies Stage 13's own orchestration, retry policy, timeout policy, or
validation. It never implements the planner, a Streamlit UI, the RAG orchestration pipeline, or the
application composition root — each is either Phase 1.1's own named composition-root concern or an
explicitly separate future phase (Future Phase Boundaries).

## Responsibilities

Phase 1.2 shall: define the architecture of a concrete `LLMAdapter` subclass that fully and exactly
implements Stage 13's frozen abstract contract (Adapter Contract); define the ownership and lifecycle
of the one SDK client a concrete adapter instance holds, from construction through disposal, never
escaping the adapter instance (Prompt Lifecycle); define how a concrete adapter's constructor consumes
the `(ProviderSettings, Optional[str])` pair Phase 1.1's `wire_dependencies()` already calls a
registered factory with, and what it does with the resolved raw credential (Provider Configuration,
Security Considerations); define adapter identity (`provider_name`) and request identity
(`provider_name` plus the calling `LLMExecutionConfig.model_name`) as two distinct, explicitly
separated concepts (Provider Model); define the full lifecycle of `model_version_reported`, including
when it may be `None` and when a concrete adapter may populate it (Provider Model); define, per field,
the ownership of every value a concrete implementation must produce on `RawLLMResult`, including the
finish-reason normalization rule and the token-accounting ownership split (Provider Model —
`RawLLMResult` Mapping); define the `ProviderRegistration` a concrete implementation supplies to Phase
1.1's `build_provider_registry()`, including the correct `network_dependent` declaration (Public
Function Contracts); define the exception-raising discipline a concrete adapter's `invoke()` must
follow to satisfy Stage 13's closed, four-member exception vocabulary (Failure Handling); define the
one-attempt-per-`invoke()` retry boundary explicitly (Prompt Lifecycle, Failure Handling, Design
Decisions).

## Non-Responsibilities

Phase 1.2 explicitly does **not** perform, and no future patch to it may silently add without a new
design pass: select, implement, or import any specific concrete LLM provider SDK (this document
defines the architecture any provider-specific implementation must follow; the implementation itself,
for any named provider, is separate, future, per-provider work never designed here); construct a
prompt, assemble context, or budget a prompt against a token ceiling — prompt engineering, prompt
templates, prompt construction, and prompt budgeting all remain Stage 12's own frozen responsibility;
this document only ever receives already-assembled `system_prompt`/`user_prompt` strings via
`invoke()`'s own parameters, exactly as Stage 13 itself does, and interprets them no further than
Stage 13 already does; modify Stage 13's own orchestration, Retry Policy, Timeout Policy, or
Validation — every one of those is untouched and unduplicated here; implement retry, backoff, or
timeout *looping* logic of any kind (Stage 13's own frozen Retry Policy already owns the loop that
consumes a raised `LLMTransientError`; Phase 1.2 defines only the exception-raising discipline a
concrete adapter's `invoke()` must follow, never the loop — Failure Handling); construct a retrieval
closure, edit `ProviderRegistry`, or perform dependency wiring of any kind — every one of those remains
exclusively owned by Phase 1.1's own composition root, a deferred responsibility, not a permanent
prohibition; implement the planner, a Streamlit UI, the RAG orchestration pipeline, or the application
composition root — each an explicitly separate future phase or composition-root concern (Future Phase
Boundaries); choose which provider is active for the `LLM_PROVIDER` seam (`ApplicationSettings`, Phase
1.1's own job, never this document's); re-define, re-default, or re-clamp any tunable Stage 13's own
Configuration already owns (`DEFAULT_TIMEOUT_SECONDS`, `MAX_OUTPUT_TOKENS_CEILING`,
`MAX_RETRY_ATTEMPTS_CEILING`, or any other); hold any global mutable state; introduce a new logging
namespace, `stage` identifier, or closed log-code vocabulary distinct from Stage 13's own (Logging
Vocabulary); move a responsibility from Stage 12, Stage 13, or Phase 1.1 into this document, or from
this document into any of them; introduce streaming token generation, incremental responses,
server-sent events, chunked response delivery, partial-completion callbacks, or any streaming SDK API
of any kind — Stage 13's own frozen `invoke()` contract is synchronous request/response only (Prompt
Lifecycle, Adapter Contract, Future Phase Boundaries), and adding a streaming surface here would
expand that frozen contract, which this document is explicitly forbidden from doing; define
conversation history, chat session management, persistent conversations, provider-managed sessions,
conversational memory, or dialogue state of any kind — each `invoke()` call is architecturally
independent (Future Phase Boundaries); no state from one call is ever read, stored, or referenced by
a later call, by this document's own design or by anything Stage 13's own frozen contract permits.

## Inputs

Two inputs, both supplied by Phase 1.1's `wire_dependencies()` exactly as its own Public Function
Contracts already describe — a concrete adapter's constructor (or the factory function that builds
it) never reads any other source:

- **`ProviderSettings`** — the seam's resolved configuration object (Phase 1.1's own schema): names
  the active `provider_name`, carries an `extra: Dict[str, Any]` passthrough this document is the
  first to interpret for the `LLM_PROVIDER` seam (Provider Configuration), and a `credential_ref` (an
  opaque reference, never a raw value).
- **An optional resolved raw credential (`Optional[str]`)** — the second positional argument Phase
  1.1's `wire_dependencies()` already passes to every registered factory, resolved from
  `credential_ref` immediately before the factory call, and `None` if the seam carries no
  `credential_ref`.

No environment variable, `.env` file, or secret store is ever read directly by a concrete adapter or
its factory — that reading is Phase 1.1's own exclusive responsibility, already performed before
either of the two inputs above reaches this layer. At invocation time, a constructed adapter also
receives, per call, exactly what Stage 13's own frozen `invoke()` signature already names:
`system_prompt: str`, `user_prompt: str`, and `config: Dict[str, Any]` (Stage 13's own
`LLMExecutionConfig` shape) — never anything this document adds to that signature.

## Outputs

- **One constructed instance conforming to Stage 13's frozen `LLMAdapter` contract** — returned by the
  factory function `wire_dependencies()` invokes; nothing else is returned to Phase 1.1.
- **Per invocation, one `RawLLMResult`** (on success) **or a raised exception from Stage 13's closed
  four-member vocabulary** (on failure) — never anything else, and never `LLMResponse` itself, which
  remains exclusively Stage 13's own to assemble.

No file is written by any concrete adapter architected under this document. No new artifact directory
is introduced. There is no manifest interaction of any kind — the same zero-artifact posture Phase
1.1 and Phase 1.3 already established, extended here to the LLM provider layer.

## Provider Model

### Adapter identity vs. request identity

Stage 13's own frozen contract splits what Stage 8's contract keeps together. This document names
both halves explicitly, rather than collapsing them into a single identity concept the way Phase 1.3's
`(provider_name, model_name, model_version)` triple does for its own, differently-shaped seam:

- **Adapter identity** — the stable identity of the constructed `LLMAdapter` instance itself, fixed
  for the instance's entire lifetime: `provider_name` alone. The adapter instance is provider-specific
  (it wraps one SDK client, authenticated against one provider), but it is **not** model-specific — a
  single constructed instance may serve `invoke()` calls naming different models across its own
  lifetime, since `model_name` is never a property Stage 13's contract places on the adapter.
- **Request identity** — the effective model being invoked for one particular call: `provider_name`
  (from the adapter's own adapter identity) together with `model_name` (supplied fresh on that specific
  call via `config["model_name"]`, Stage 13's own `LLMExecutionConfig.model_name`, which "a caller must
  always name... explicitly" with no default). Request identity is scoped to one `invoke()` call; it
  is never cached, stored, or treated as a property of the adapter instance across calls.

Stage 13 intentionally keeps these separate because `model_name` is request-scoped, never
adapter-scoped (Design Decisions). A concrete adapter must never assume, cache, or hard-code a single
`model_name` as though it were part of its own adapter identity — doing so would silently narrow a
contract Stage 13 deliberately left open per-call.

### `model_version_reported` lifecycle

`model_version_reported` (Stage 13's own frozen property, `Optional[str]`, "informational only") has
a lifecycle this document states explicitly rather than leaving ambiguous:

- It may be `None` at construction, before any call has ever completed — a concrete adapter is not
  required to know a served model's version before it has made a single request.
- It may become populated only after a successful `invoke()`, if and only if the provider's own
  response exposes a version/revision value the adapter chooses to surface.
- A provider may report a different value on a later call than an earlier one (e.g., a hosted provider
  quietly rolls a serving version forward); this is not a contract violation, since Stage 13 never
  asserts this value is stable across calls.
- A provider that exposes no version metadata at all leaves this value `None` permanently — also not a
  contract violation.
- **Stage 13 never depends on this value for correctness**, at any point in its own orchestration
  (Determinism, Read-Only Guarantees) — it is informational metadata only, exactly as Stage 13's own
  schema comment already states ("provider-reported if available, else null; informational"). No
  concrete adapter architected under this document may treat `model_version_reported` as anything a
  caller could safely rely on for behavior, pinning, or identity purposes.

### Relationship to Stage 13's frozen contract

A concrete adapter is a plain subclass of Stage 13's `LLMAdapter` abstract base class
(`scripts/stage13_llm_execution.py:67`), implementing the single abstract method (`invoke`) that class
declares, with no additions to the class's own public surface visible to Stage 13's orchestration.
Stage 13 calls `invoke(system_prompt, user_prompt, config) -> RawLLMResult` (or a raised exception) on
the hot path, and reads `provider_name`/`model_version_reported` for `LLMResponse`'s own
`provider_name`/`model_version` fields; a concrete adapter's constructor and any private helper
methods are invisible to, and never called directly by, Stage 13's own orchestration code.

### Internal request/response shape — adapter-private, not a new public contract

A concrete adapter that wraps a hosted API necessarily constructs some request representation to send
to that API and parses some response representation it receives back. This document names the minimum
information such a representation must carry, illustratively, entirely internal to a concrete adapter,
and **never** a new public contract this document mandates verbatim or exposes past the adapter
boundary:

```
# Illustrative only — entirely private to a concrete adapter's own implementation.
# Never returned from invoke() directly, never seen by Stage 13, never a Phase 1.1 concern.
_RawLLMRequest:  { model_name, system_prompt, user_prompt, temperature, max_output_tokens, ... }
_RawLLMResponse: { text, native_finish_reason, native_usage: Optional[Dict], native_request_id }
```

`invoke(system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult` remains,
exactly as Stage 13 already froze it, the only shape a concrete adapter exposes outward on success.
Any internal representation a concrete implementation uses to talk to its own SDK is that
implementation's own private concern, never standardized by this document beyond the illustrative
shape above.

### `RawLLMResult` Mapping

Stage 13's own frozen `RawLLMResult` carries six fields. This document states, per field, who
supplies it, whether the adapter copies or normalizes it, whether it is required or optional, and
whether a missing value is acceptable — architecture only, no algorithm:

| Field | Supplied by | Copy or normalize? | Required/Optional | Missing value acceptable? |
|---|---|---|---|---|
| `response_text` | The provider's own SDK response | **Normalized into a plain Python string** — see response_text Normalization below (content is never edited, truncated, or reformatted; only its container shape is normalized) | Required | No — `""` is a valid empty string, but the field itself must always be present |
| `finish_reason` | The provider's own native finish signal, **normalized by the adapter** | **Normalized, never copied verbatim** — see Finish Reason Normalization below | Required | No — always one of Stage 13's four closed values |
| `prompt_tokens` | The provider's own token accounting, if reported | Normalized (see Token Accounting below) | Optional | Yes — `None` if the provider does not report it |
| `completion_tokens` | The provider's own token accounting, if reported | Normalized (see Token Accounting below) | Optional | Yes — `None` if the provider does not report it |
| `total_tokens` | The provider's own token accounting, or derived by the adapter | Normalized (see Token Accounting below) | Optional | Yes — `None` if the provider reports no usable count of any kind |
| `provider_request_id` | The provider's own native trace/request identifier, if exposed | Copied or normalized verbatim (an opaque passthrough — see Provider Request ID below) | Optional | Yes — `None` if the provider does not expose one |

**Finish Reason Normalization.** A provider's own native finish-reason vocabulary (whatever strings or
enum values that specific SDK uses) is never exposed outside the adapter, under any circumstance. The
adapter alone owns normalizing the provider's native signal into exactly one of Stage 13's four closed
values — `complete`, `length`, `content_filter`, `other` — before constructing `RawLLMResult`. Stage
13's own orchestration only ever sees the normalized value; it never inspects, pattern-matches, or
special-cases a provider-native string (mirroring exactly the discipline Stage 13's own Error Mapping
already applies to adapter exception types, extended here to finish reasons).

**Token Accounting.** A real provider may return all three counts, only a total, only
prompt/completion (with no total), or none at all. The adapter owns normalizing whatever subset the
provider actually returned into `RawLLMResult`'s three independently-nullable integer fields — if the
provider reports prompt and completion counts but no total, the adapter may compute
`total_tokens = prompt_tokens + completion_tokens` itself (matching Stage 13's own schema comment:
"provider-reported, or `prompt_tokens + completion_tokens` if the provider doesn't report a total
directly"); if the provider reports nothing, all three remain `None`. Stage 13 owns validating the
resulting values once received — its own frozen `TOKEN_COUNT_MISMATCH` internal invariant already
checks `total_tokens == prompt_tokens + completion_tokens` whenever both operands are non-null. This
document states the ownership split only: the adapter normalizes whatever the provider gave it; Stage
13 validates whatever the adapter produced. No filling-in algorithm beyond the one derivation named
above is defined here.

**response_text Normalization.** A provider's own SDK may represent generated content in whatever
internal shape that SDK uses — a single string, multiple parts, segments, or other structured content
— never assumed to be a plain string by default. Regardless of that internal shape, the adapter owns
normalizing it into a plain Python string before constructing `RawLLMResult`. This is an ownership
statement only, not a normalization algorithm: this document does not define how multiple parts or
segments are joined, in what order, or with what separator — that is each concrete implementation's
own concern, specific to its own provider's own content shape.

**Provider Request ID.** If the provider's own response supplies a trace/request identifier, the
adapter copies or normalizes it onto `provider_request_id`. If no such identifier exists on a given
provider's response, `provider_request_id` is `None`. The adapter never fabricates a synthetic
request identifier of its own when the provider supplies none — an absent identifier is always
represented as `None`, never as a generated placeholder value.

**`RawLLMResult` Structural Ownership.** Before returning from `invoke()`, the adapter is responsible
for ensuring the `RawLLMResult` it constructs satisfies Stage 13's own structural contract: correct
field types, the required/optional distinction stated in the table above, a normalized `finish_reason`
(Finish Reason Normalization), a normalized `response_text` (response_text Normalization above), and
correctly-nullable token fields and `provider_request_id`. Stage 13's own `validate_llm_response()`
validates the assembled result once received (Stage 13's own Validation §3); this document assigns no
new validation tier of its own — the adapter owns constructing a structurally correct `RawLLMResult`;
Stage 13 owns validating it. No validation algorithm is defined here.

## Prompt Lifecycle

A strictly linear construction-to-disposal model, never a stored, mutable state machine — mirroring
Phase 1.1's own Design Decision #3 reasoning and Phase 1.3's own Embedding Lifecycle: nothing in a
concrete adapter's own lifecycle branches on an external, non-deterministic decision the way Stage
21's planning loop does.

```
[1] Factory invocation           — wire_dependencies() invokes the registered factory with
      (ProviderSettings, Optional[str]); the second argument is the resolved raw credential, or None
      │
      ▼
[2] SDK client construction      — the factory (or the adapter's own __init__) constructs exactly one
      SDK client, consuming the resolved raw credential exactly once; the client is stored only as a
      private attribute on the constructed adapter instance
      │
      ▼
[3] Adapter instance returned    — the fully constructed, LLMAdapter-conforming instance is returned
      to wire_dependencies(), which places it in WiringResult.wired[LLM_PROVIDER]
      │
      ▼
[4] Repeated invoke() calls      — Stage 13's own orchestration calls invoke(system_prompt, user_prompt,
      config) zero or more times over the adapter instance's lifetime, each call using the same SDK
      client constructed in step [2]; no reconstruction, no reconnection between calls; config carries
      a fresh model_name and other request-scoped fields on every call (Provider Model — request
      identity)
      │
      ▼
[5] RawLLMResult mapping         — on a successful call, the adapter maps the provider's own response
      onto RawLLMResult per-field (Provider Model — RawLLMResult Mapping) and returns it; on a failed
      call, the adapter raises exactly one of Stage 13's four closed exception types (Failure Handling)
      │
      ▼
[6] Disposal                     — when the process holding the adapter instance ends (or, in a test
      harness, when the instance is explicitly discarded), the SDK client is released with it; this
      document defines no explicit disposal method beyond ordinary object lifetime, since no frozen
      stage's own contract calls one
```

**The retry boundary, stated explicitly, governing this entire document:** one call to `invoke()`
corresponds to exactly one provider invocation attempt. A concrete adapter performs exactly one
network call per `invoke()` invocation — never its own internal retry loop across multiple provider
calls within a single `invoke()`. If a retryable condition occurs (a timeout, a rate limit, a 5xx-class
error), the adapter raises `LLMTransientError` and returns control to Stage 13 immediately; the
adapter never re-attempts the call itself before raising. Stage 13 alone decides whether another
`invoke()` call happens, per its own frozen Retry Policy (up to `max_retry_attempts`, with the
already-fixed backoff formula) — this document defines no retry logic of its own (Failure Handling,
Design Decisions).

**The streaming boundary, stated explicitly.** Step [4]/[5] above describes exactly one materialized
result per `invoke()` call. This document does not introduce, and no concrete implementation
architected under it may introduce, streaming token generation, incremental responses, server-sent
events, chunked response delivery, or partial-completion callbacks of any kind. If a concrete
implementation wraps a provider whose own SDK is streaming-only, the adapter must fully consume that
stream internally, inside step [5], before ever returning — `invoke()` always returns one completed
`RawLLMResult`, or raises one of Stage 13's four typed exceptions; it never returns a partial result,
a generator, an iterator, or any construct a caller could consume incrementally. Introducing a
streaming surface would expand Stage 13's own frozen `invoke()` contract, which this document is
explicitly forbidden from doing (Adapter Contract, Non-Responsibilities, Future Phase Boundaries).

## Provider Configuration

### `ProviderSettings.extra` — interpreted here, for this seam only

Phase 1.1's own Configuration Model defines `ProviderSettings.extra: Dict[str, Any]` as a
"provider-specific, uninterpreted passthrough" that Phase 1.1 itself "never interprets, validates the
meaning of, or defaults." Phase 1.2 interprets this field for the `LLM_PROVIDER` seam, exactly as
Phase 1.3 already does for `EMBEDDING_PROVIDER`. A concrete adapter's own factory reads whichever of
the following keys its own provider needs; no key is mandatory across every concrete implementation,
and a concrete implementation is free to define additional keys of its own:

```
extra = {
    "default_model_name":       "<deployment-level default model, if the deployment wants one>",
    "api_base_url":             "<optional endpoint override>",
    "request_timeout_seconds":  "<optional per-call SDK-level timeout, distinct from Stage 13's own>",
    "sdk_max_retries":          "<optional SDK-internal connection-level retry count>",
    "safety_settings":          "<optional provider-specific safety/content-filter configuration>",
    "default_temperature":      "<optional provider-level default sampling temperature>",
}
```

### Provider-owned configuration vs. Stage 13 execution configuration — the explicit line

This line must never blur, because Stage 13's own frozen `LLMExecutionConfig` already owns the
per-request tunables a caller supplies on every call:

| Concern | Owner |
|---|---|
| `model_name` for a given call | Stage 13's own `LLMExecutionConfig.model_name`, supplied by the caller on every `invoke()` — never a Phase 1.2 concern, never defaulted by this document (a deployment-level *default* the composition root chooses to supply is `extra["default_model_name"]`, described only as available raw material for that future work, never consumed by this document itself) |
| `temperature`, `max_output_tokens`, `timeout_seconds`, `max_retry_attempts` for a given call | Stage 13's own `LLMExecutionConfig` fields, exactly as already frozen — clamped and defaulted by Stage 13's own `resolve_execution_config()`, never re-defined, re-defaulted, or re-clamped here |
| SDK client construction knobs (endpoint, SDK-level connection timeout, SDK-level connection retry count) | This document's own `extra` interpretation — provider-owned, never a Stage 13 concern, since Stage 13's own `LLMExecutionConfig` has no field for any of these |
| Safety/content-filter configuration applied at the SDK-client level (as opposed to a per-call parameter some SDKs also accept) | This document's own `extra` interpretation — provider-owned; Stage 13 itself has no safety-configuration field of any kind, only the closed `LLMContentPolicyError` outcome a triggered filter maps to |

### Model pinning — Phase 1.2's own operational recommendation, not a Stage 13 rule

Unlike Stage 8, whose own frozen contract explicitly disallows a floating `model_version` alias like
`"latest"`, **Stage 13 imposes no model-pinning requirement of its own.** `LLMExecutionConfig.
model_name` has no default and no format constraint beyond being present; Stage 13's own document
never states that `model_name` must avoid a floating alias.

Phase 1.2 recommends, as its own operational discipline layered on top of (never restating) Stage 13's
contract, that a deployment's own configured `model_name` value (wherever it is set — a caller's own
per-request value, or a deployment default surfaced through `extra["default_model_name"]`) avoid a
floating alias whose target can change without a deliberate configuration change, for the same
reproducibility reasons Stage 8's contract states explicitly for its own seam. This recommendation is
Phase 1.2's own addition; it is not, and must never be cited as, an existing Stage 13 rule.

## Adapter Contract

Restated here by citation, not redefinition — Stage 13's own frozen `LLMAdapter`/`RawLLMResult`/
exception-type contract (`docs/architecture/stage13_llm_execution.md` §"Backends",
`scripts/stage13_llm_execution.py:39-73`):

```python
class LLMAdapter(ABC):
    provider_name: str                       # adapter identity — Provider Model
    model_version_reported: Optional[str]    # informational only — Provider Model

    @abstractmethod
    def invoke(self, system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult:
        ...
        # raises exactly one of: LLMTransientError, LLMAuthError, LLMContentPolicyError,
        # LLMInvalidRequestError — on failure, never any other exception type

class RawLLMResult:
    response_text: str
    finish_reason: str            # one of ("complete", "length", "content_filter", "other")
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    provider_request_id: Optional[str]
```

This document adds nothing to this contract's own public surface — no new abstract method, no new
required property, no changed signature. Everything Phase 1.2 defines (SDK client ownership, the
adapter-identity/request-identity split, `model_version_reported`'s lifecycle, `RawLLMResult`
per-field ownership, model-pinning discipline, `extra` interpretation, exception-raising discipline)
governs how a concrete subclass is built and configured; none of it is visible to Stage 13's own
orchestration, which continues to see exactly the contract above and nothing more.

`invoke()`'s signature above is synchronous request/response only, by Stage 13's own frozen design —
one call in, one `RawLLMResult` out, or one raised exception. No concrete implementation may widen
this into a streaming, generator-based, or callback-based surface; doing so would be a change to Stage
13's own frozen public contract, which is outside this document's authority to make (Prompt Lifecycle
— streaming boundary, Non-Responsibilities, Future Phase Boundaries).

## Validation

Two distinct, clearly-scoped groups, deliberately kept separate — mirroring the same discipline Phase
1.3 already applied for its own seam:

**1. Construction-time validation** — a concrete adapter's own constructor (or factory) validates the
inputs it directly receives, before constructing its SDK client:

- `ProviderSettings.extra` carries whatever keys this specific provider requires — a missing required
  key is this concrete implementation's own error to raise, in whatever exception type is natural to
  it; this document mandates no closed vocabulary of construction-time error codes, since the set of
  possible concrete implementations, and their own required `extra` keys, is open-ended by design.
- If the provider requires a credential (`credential_ref` was present on `ProviderSettings`) and the
  resolved raw credential argument is `None` or empty, construction must fail — a concrete adapter
  never silently constructs an unauthenticated client when a credential was expected.

**2. Runtime validation** — remains exactly where Stage 13's own frozen contract already places it:
Stage 13's own `validate_prompt_package()`, `resolve_execution_config()`, and `validate_llm_response()`
validate the request package, the execution config, and the assembled `LLMResponse`, respectively —
none of that is duplicated or relaxed here. A concrete adapter's own `invoke()` is trusted to produce a
correctly-shaped `RawLLMResult` (per `RawLLMResult` Mapping above) or to raise one of the four closed
exception types; Stage 13's own `TOKEN_COUNT_MISMATCH` and other internal invariants (Validation §3 of
Stage 13's own document) are the mechanism that catches a malformed `RawLLMResult`, not a new
validation tier this document introduces.

There is no third, Phase-1.1-style "wiring-level" validation tier here — `build_provider_registry()`
and `wire_dependencies()` remain exactly as Phase 1.1 already froze them; this document supplies
inputs to that machinery (a `ProviderRegistration`) without adding a new validation tier of its own.

## Public Function Contracts

- **The factory function contract** — `Callable[[ProviderSettings, Optional[str]], LLMAdapter]` —
  exactly the signature Phase 1.1's own `ProviderRegistration.factory` field and `wire_dependencies()`
  contract already establish. A concrete implementation's factory: reads whatever keys it needs from
  `settings.extra`; performs Construction-time validation (above); constructs exactly one SDK client
  from the resolved raw credential (the second argument), if one was supplied; returns a fully
  constructed instance conforming to Stage 13's `LLMAdapter` contract; raises on any construction-time
  validation failure, in whatever exception type is natural to the concrete implementation — this
  document mandates no shared exception base class for construction failures, since Phase 1.1's own
  `wire_dependencies()` treats a factory's return value opaquely and propagates any exception a
  factory raises without inspecting its type.

- **The `ProviderRegistration` this document's implementations supply** — `seam="LLM_PROVIDER"`, a
  `provider_name` unique among registrations for that seam, `network_dependent` set truthfully by the
  concrete implementation (`True` for any adapter that opens a network socket during construction or
  during `invoke()` — the expected case for essentially every real hosted LLM provider), and the
  factory described above. This document defines the shape of this registration; it does not itself
  call `build_provider_registry()` or assemble a list of registrations — that remains the application
  composition root's own job (Future Phase Boundaries).

- **`invoke(self, system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult`** —
  Stage 13's own frozen abstract method, restated here only to state a concrete implementation's own
  obligations against it: perform exactly one network call to the provider (Prompt Lifecycle's retry
  boundary); construct the provider's own native request from `system_prompt`, `user_prompt`, and the
  relevant fields of `config` (at minimum `model_name`, since it has no default); on success, map the
  provider's native response onto `RawLLMResult` per `RawLLMResult` Mapping; on failure, raise exactly
  one of `LLMTransientError`, `LLMAuthError`, `LLMContentPolicyError`, or `LLMInvalidRequestError` —
  never a raw provider-SDK exception class, and never any exception outside this closed four-member
  vocabulary.

No function architected under this document ever imports Phase 1.1's own internals, ever reads
`os.environ` directly (the resolved credential always arrives as an argument, never read from the
environment by this layer), or ever opens a network socket outside of what its own SDK client does on
its own provider's behalf.

## Determinism

**Deterministic (guaranteed, given identical input):**

- **Adapter identity.** Which `provider_name` a concrete adapter exposes, given identical
  `ProviderSettings` — a pure function of the configuration it was constructed with.
- **Request identity, per call.** Which `(provider_name, model_name)` pair a given `invoke()` call
  targets is fully determined by the adapter's own fixed `provider_name` and the `model_name` present
  on that call's `config` — never ambiguous, never inferred.
- **Error-mapping outcome, at the adapter boundary.** Whether a given real SDK exception is translated
  into `LLMTransientError` vs. one of the three non-retryable types is a fixed function of that
  concrete implementation's own exception-mapping logic, applied consistently — the same discipline
  Stage 13's own `map_adapter_error()` already applies one layer up, extended here to the adapter's own
  translation step.
- Whether construction-time validation passes or fails, given identical `(ProviderSettings,
  Optional[str])` inputs.

**Explicitly NOT deterministic (inherent to a real provider; never assumed, never hidden):**

- **`response_text`.** The model's own generated content — Stage 13's own Determinism section already
  states this is the first genuinely non-deterministic content this pipeline produces, at any
  `temperature`, for any provider; this document does not weaken or restate that boundary differently.
- **`finish_reason`, `prompt_tokens`, `completion_tokens`, `total_tokens` (as observed values, though
  the *normalization rule* applied to them is itself deterministic — `RawLLMResult` Mapping).**
  Provider-reported, and covary with `response_text`.
- **`latency_ms`.** Wall-clock by definition, excluded from every determinism comparison, matching
  Stage 13's own treatment.
- **`provider_request_id`.** Provider-assigned, never reproducible across calls.
- **`model_version_reported`'s own presence and timing.** Whether it is populated at all, and when
  (Provider Model), depends entirely on what a live provider's own response exposes on a given call —
  never assumed stable or predictable.
- **SDK client construction side effects.** A real SDK client may perform its own connection setup or
  credential validation against a live endpoint at construction time; this document makes no claim
  about what a specific SDK does internally during Prompt Lifecycle step [2].

**No `config_fingerprint_fields` analog exists in this document, because none exists on Stage 13's own
frozen `LLMAdapter` contract.** `LLMResponse` is fully in-memory with no persisted artifact and no
config-fingerprint concept of any kind ("the fourth consecutive fully read-only,
zero-manifest-interaction stage" — Stage 13's own Overview). Introducing one here would extend Stage
13's frozen contract, which this document is explicitly forbidden from doing.

## Read-Only Guarantees

- Phase 1.2 never modifies `manifest.json`, any corpus artifact, any vector index, any embedding, any
  prompt template, or any cache store entry — it has no relationship to any of them at all, matching
  Stage 13's own zero-manifest, zero-artifact posture.
- A concrete adapter never modifies `ProviderSettings` after receiving it — it reads from `extra` and
  `credential_ref`/the resolved credential, never mutates either.
- A concrete adapter never modifies the `system_prompt`, `user_prompt`, or `config` it receives on
  `invoke()` — it reads from them to construct its own native request, never mutating the caller's own
  objects.
- A concrete adapter holds no module-level mutable state of its own; every piece of state it needs
  (its SDK client, its own `provider_name`, whatever `model_version_reported` it has observed so far)
  lives on the constructed instance itself, never in a module-level variable shared across instances.
- The only external side effects an SDK client may perform are whatever its own provider's SDK does on
  its own behalf (a network call) — this document defines no additional side effect of its own beyond
  what Prompt Lifecycle step [2] and step [4] already name.

## Failure Handling

- **A construction-time validation failure** (missing required `extra` key, missing credential when
  one was expected) — the factory raises immediately, before any SDK client is constructed;
  `wire_dependencies()` propagates whatever exception the factory raised (Phase 1.1's own
  `wire_dependencies()` contract already treats a factory's exceptions opaquely).
- **The provider exception boundary, stated explicitly.** Provider-native SDK exception types never
  cross the adapter boundary, under any circumstance — Stage 13's own orchestration, and every caller
  above it, only ever sees one of Stage 13's four closed exception types, never a raw SDK-specific
  exception class. This mirrors exactly the discipline Finish Reason Normalization already applies one
  layer over in `RawLLMResult` Mapping: a provider-native signal is translated at the adapter boundary
  and never leaks past it.
- **An SDK-level exception raised during `invoke()`** — translated by the concrete adapter into
  exactly one of Stage 13's four closed exception types, and only these four types are ever visible
  outside the adapter:
  - **`LLMTransientError`** — a timeout, rate limit, or 5xx-class failure. Retryable, per Stage 13's
    own Retry Policy.
  - **`LLMAuthError`** — an authentication/authorization failure. Non-retryable.
  - **`LLMContentPolicyError`** — a content-policy/safety rejection. Non-retryable.
  - **`LLMInvalidRequestError`** — a malformed request the provider rejected outright (e.g., an
    unrecognized `model_name`). Non-retryable.
- **The retry boundary, restated here in full.** One `invoke()` call is exactly one provider invocation
  attempt (Prompt Lifecycle). A raised `LLMTransientError` is the adapter's sole signal to Stage 13 that
  a retry may be warranted; the adapter itself never re-attempts the call before raising, and never
  implements backoff, a retry count, or a retry ceiling of its own. Retry ownership is Stage 13's
  alone — its own frozen Retry Policy decides whether, and how many times, another `invoke()` call
  happens. Duplicating any part of that decision here would violate this document's own
  Non-Responsibilities.
- **No fallback provider, no silent degradation.** If a concrete adapter's construction fails, or if
  `invoke()` raises a non-retryable exception, or if Stage 13's own retry budget on `LLMTransientError`
  is exhausted, the failure propagates exactly as Stage 13's own Failure Handling and Error Mapping
  already specify — never a silent substitution of a different provider or a degraded, partially
  computed response.

## Security Considerations

- **Credential consumption.** A concrete adapter's factory receives the resolved raw credential as its
  second positional argument, exactly as Phase 1.1's `wire_dependencies()` contract already supplies
  it. The factory consumes this value exactly once, at construction time, to build its SDK client; it
  retains no separate copy of the raw string after construction — the SDK client itself becomes the
  credential's sole holder, matching Phase 1.1's own Security Considerations and Phase 1.3's own
  corrected shape.
- **SDK client as sole credential holder.** After construction, only the SDK client instance held by
  the adapter carries the credential. No field on the adapter instance itself, and no field on any
  object this document defines, stores the raw credential as a plain, independently-readable value.
- **No credential serialization.** The resolved raw credential is never converted to JSON, a dict, or
  any other serializable form by this document's own architecture, for logging, caching, or transport.
  Whatever serialized form an SDK client constructs internally to authenticate its own requests (a
  signed header, a bearer token) is that SDK's own concern, inherited by a concrete adapter, never
  introduced by this document.
- **No credential persistence.** Nothing this document architects writes the resolved raw credential
  to disk, to a cache store, to the manifest, or to any artifact of any kind. If a specific SDK client
  persists its own token to a local cache as part of its normal operation, that is inherited SDK
  behavior, never something this document introduces or is responsible for.
- **No credential logging.** A concrete adapter never logs, prints, or serializes the resolved raw
  credential argument, at any severity, under any circumstance — the same hard constraint Phase 1.1
  and Phase 1.3 already state for their own layers.
- **Prompt content, inherited.** `system_prompt`/`user_prompt` arriving at `invoke()` may already carry
  adversarial content from upstream corpus injection (Stage 12's and Stage 13's own accepted,
  documented risk). A concrete adapter performs no additional sanitization on the outbound request —
  that risk passes through unchanged, exactly as Stage 13's own Security Considerations already state,
  never a new defense this document introduces.
- **Untrusted model output, inherited.** `response_text` is opaque, model-generated content; a
  concrete adapter's own `invoke()` implementation never interprets, executes, or acts on it beyond
  mapping it verbatim onto `RawLLMResult.response_text` — the same "never interpreted, executed, or
  interpolated" posture Stage 13's own Security Considerations already establish one layer up.
- **No network isolation guarantee.** A concrete adapter architected under this document opens a real
  network socket to its provider's own endpoint for essentially every real implementation. This
  document makes no claim that such an adapter is network-isolated; it only guarantees that the
  *credential* reaching that socket is handled exactly as described above.

## Logging Vocabulary

This section defines the vocabulary available to a concrete adapter **if** it emits logs; exactly like
Phase 1.1's and Phase 1.3's own Logging Vocabulary sections, it does not mandate that logging occur.

This document introduces no new `stage` identifier and no new closed-vocabulary log codes. A concrete
adapter operates inside Stage 13's own runtime; Stage 13's own shared Logging Specification already
owns the `stage: "stage13_llm_execution"` identifier and the closed codes that apply to an invocation
outcome (`WARNING_LLM_INVOCATION_TIMEOUT`, `WARNING_LLM_INVOCATION_TRANSIENT_ERROR`,
`FATAL_LLM_INVOCATION_AUTH_ERROR`, and the rest of Stage 13's own Logging section). Extending that
vocabulary is Stage 13's own revision path, never this document's.

A concrete adapter that wishes to emit its own internal diagnostic information (for example, "SDK
client constructed" or "SDK client construction failed") may do so at DEBUG severity or below the same
floor the shared Logging Specification already establishes for document content. Any such diagnostic
log entry is subject to the same hard constraint stated in Security Considerations: it may never
include the resolved raw credential, any raw prompt content, or any raw response content beyond what
Stage 13's own logging discipline already permits.

## Concurrency

A concrete adapter instance is constructed exactly once (Prompt Lifecycle step [2]) and its `invoke()`
method may be called repeatedly, including concurrently, over its lifetime (step [4]) — Stage 13's own
Concurrency section already states it is "safe under concurrent calls" with "no locking and no local
race condition." This document does not mandate that a concrete adapter's `invoke()` be safe to call
concurrently from multiple threads independent of that guarantee's real source — that safety is a
property of the specific SDK client a concrete implementation wraps, never something this architecture
can guarantee on that SDK's behalf. A concrete implementation that wraps a thread-safe SDK client
inherits that safety; one that wraps a non-thread-safe client does not.

Phase 1.2 defines no locking, no mutex, and no coordination of its own beyond what Prompt Lifecycle
already describes — the caveat Stage 13's own Concurrency section already names (a provider's own rate
limits across concurrent calls sharing one account/credential) is entirely the provider's and the
adapter's own concern, surfaced, if it occurs, as a retryable `LLMTransientError`, never a concurrency
control this document itself implements.

## Design Decisions

1. **This architecture is provider-neutral by construction, not by convention.** Every section above
   is written to hold for any concrete `LLMAdapter` implementation — any vendor — because the set of
   LLM providers this repository may eventually support is open-ended. Naming a provider anywhere in
   this document is illustrative only, never load-bearing.

2. **Adapter identity and request identity are defined as two separate concepts, not one triple.**
   Collapsing them, the way Phase 1.3's `(provider_name, model_name, model_version)` triple does for
   its own seam, would misstate Stage 13's actual contract: `model_name` is never a property of the
   adapter instance, only of a specific call's `LLMExecutionConfig`. Naming both concepts explicitly,
   rather than silently reusing Phase 1.3's shape, prevents a future implementer from assuming a
   constructed adapter is bound to one model for its own lifetime, when Stage 13's own contract never
   makes that guarantee.

3. **No shared exception base class is mandated for construction-time failures**, for the same reason
   Phase 1.3 already gives for its own seam: Phase 1.1's own `wire_dependencies()` already treats a
   factory's exceptions opaquely, so mandating a hierarchy here would add a cross-cutting contract
   neither Stage 13 nor Phase 1.1 asked for.

4. **The retry boundary — one `invoke()` call is exactly one provider attempt — is named as its own
   explicit decision, not left to inference.** Given how naturally a "provider adapter" document could
   drift into owning retry/backoff behavior (the same risk Phase 1.3 named for its own seam's retry
   loop), this document states directly that a concrete adapter never re-attempts a call internally
   before raising `LLMTransientError`; the decision of whether, and how many times, to call `invoke()`
   again belongs exclusively to Stage 13's own frozen Retry Policy. An adapter that swallowed a
   transient failure and quietly retried internally would defeat Stage 13's own `attempt_count`
   accounting and its own backoff schedule, silently.

5. **`RawLLMResult`'s six fields each receive individually stated ownership, rather than one blanket
   "the adapter maps the response" statement.** Two of the six fields — `finish_reason` and the
   token-count trio — carry a real normalization requirement Stage 8's own `embed_batch()` return
   shape never needed (a vector list has no comparable per-field ambiguity across providers). Stating
   each field's ownership individually, including the explicit prohibition on ever exposing a
   provider's native finish-reason vocabulary outside the adapter, closes a class of implementation
   mistakes (a leaked native enum value reaching Stage 13's own orchestration) before any concrete
   implementation is written.

6. **`model_version_reported`'s lifecycle is stated explicitly, including the cases where it never
   populates.** Given the field is documented only as "informational," a future implementer could
   reasonably wonder whether Stage 13 depends on it somewhere non-obvious. Stating plainly that Stage
   13 never depends on it for correctness, and that a provider exposing no version metadata is fully
   contract-compliant, removes that ambiguity before it becomes a false assumption baked into a
   concrete implementation.

7. **Model pinning is Phase 1.2's own added recommendation, explicitly labeled as such, never
   attributed to Stage 13.** Unlike Phase 1.3, where Stage 8's contract already states a pinning rule
   this document could faithfully reinforce, Stage 13 states no such rule. Citing one as though Stage
   13 already required it would be a fabricated citation; recommending it as this document's own
   addition, while naming the fact that it is an addition, preserves both the operational value of the
   recommendation and the citation accuracy this document's own review standard requires.

8. **SDK client ownership follows Phase 1.3's own established shape without modification**, since
   nothing about Stage 13's contract changes the underlying reasoning: the client is this document's
   own to construct and dispose of; it never escapes the adapter instance; neither Phase 1.1 nor Stage
   13 ever holds it.

## Constants

```python
# This document defines no numeric threshold, ceiling, or default of its own — DEFAULT_TIMEOUT_SECONDS,
# MAX_OUTPUT_TOKENS_CEILING, MAX_RETRY_ATTEMPTS_CEILING, RETRY_BACKOFF_BASE_SECONDS,
# RETRY_BACKOFF_MULTIPLIER, and FINISH_REASONS all remain Stage 13's own constants, exactly as already
# frozen. SDK-level timeout, SDK-level connection retry count, and any per-provider ceiling are
# ProviderSettings.extra values a concrete implementation interprets for itself (Provider
# Configuration). Provider-neutrality (Design Decisions #1) means this document names no closed set of
# provider identifiers or model names — that set is open-ended by design.

LLM_PROVIDER_SEAM_NAME = "LLM_PROVIDER"  # already Phase 1.1's own constant, restated here only to
                                          # name which seam this document concerns; not a new constant
                                          # this document introduces or owns.
```

No numeric threshold, ceiling, or default belonging to Stage 13 or Phase 1.1 is duplicated here — every
one of them already lives, exactly once, in the document that owns it.

## Complexity

- **Construction (factory invocation, Prompt Lifecycle step [2])** — O(1) from this document's own
  perspective; the actual cost of a specific SDK client's own construction is that SDK's own concern.
- **`invoke(system_prompt, user_prompt, config)`** — O(1) from this document's own perspective (one
  network call, one response mapping); the actual cost of that one call — including its size-dependent
  latency — is entirely that provider's own concern, never something this document estimates on a
  specific SDK's behalf.
- **`RawLLMResult` field mapping, per call** — O(1), a fixed, small number of field reads and at most
  one derived computation (`total_tokens` when only prompt/completion counts are available).
- **Adapter identity / `model_version_reported` access** — O(1), a direct property read.

## Known Limitations

- **No cross-provider abstraction beyond `LLMAdapter` itself.** This document does not define a shared
  internal base class, mixin, or helper library that concrete implementations must use — each is free
  to structure its own internals however it needs to, as long as the outward `LLMAdapter` contract is
  satisfied.
- **No credential rotation support**, mirroring Phase 1.1's and Phase 1.3's own named limitation: a
  credential consumed once at construction time is used for the constructed SDK client's entire
  lifetime; live rotation, if a provider requires it, is that concrete implementation's own concern.
- **No multi-region, multi-endpoint, or provider-side failover architecture.** A concrete adapter
  targets exactly one endpoint for its entire lifetime; routing across multiple endpoints for the same
  logical provider is a future, separate design pass, never assumed here.
- **No response caching of any kind.** This document defines no cache in front of `invoke()` — Stage
  13's own Known Limitations already name this as a Stage 14+ concern; this document does not
  reintroduce it as its own.
- **`model_version_reported`'s usefulness is entirely provider-dependent.** A provider exposing no
  version metadata leaves this field permanently uninformative; this document accepts that as a known,
  named gap rather than inventing a substitute value.
- **Streaming SDKs must still resolve to one materialized `RawLLMResult` per call.** Stage 13's own
  Scope already states it "never streams a partial response to any caller, even if an adapter's own
  SDK uses a streaming transport internally to assemble it." A concrete adapter wrapping a
  streaming-only SDK must fully consume that stream internally before returning `RawLLMResult`; this
  document names the requirement without prescribing how any specific SDK's own streaming interface
  should be consumed to produce it.

## Future Phase Boundaries

This document defines the architecture for a concrete LLM provider implementation. Two categories of
excluded work follow, kept explicitly separate because they differ in kind, not just in content —
mirroring Phase 1.3's own corrected boundary: Category A is deferred to a future actor; Category B has
no actor, ever.

**Category A — deferred composition-root and future-phase responsibilities.** Each item below is real
future work, explicitly reserved for the application composition root Phase 1.1 already names, or for
an explicitly separate future phase already named in Phase 1.1's own Future Phase Boundaries — it will
eventually be done, just not by this document:

- **Editing `ProviderRegistry` and performing dependency wiring of any kind.** This document defines
  the shape of a `ProviderRegistration` a concrete implementation supplies; it does not itself call
  `build_provider_registry()` or `wire_dependencies()` — assembling the full list of registrations and
  performing the wiring call remains the composition root's own job.
- **Implementing the planner.** Phase 1.4 — Concrete planner provider (registered under seam
  `PLANNER_LLM_PROVIDER`), already named in Phase 1.1's own Future Phase Boundaries — is a separate,
  future phase; it "may share underlying client plumbing with Phase 1.2's own implementation without
  sharing its public contract" (Phase 1.1's own words), but this document does not design, extend, or
  imply that sharing.
- **Implementing a Streamlit UI or any other network-facing API or UI.** An application-layer concern,
  described only as a future consumer of `LLMResponse`, never designed here.
- **Implementing the application composition root itself.** The layer that actually calls
  `load_raw_settings → validate_settings → build_provider_registry → wire_dependencies`, holds the
  resulting `WiringResult`, and assembles `PipelineDependencies.llm_adapter` — not designed here.
- **Implementing RAG orchestration** (retrieval, context assembly, response caching, evaluation, or
  any other Stage 14+ concern) — each already reserved, by Stage 13's own Future Stage Boundaries, for
  a later, separate design.
- **Introducing streaming.** Streaming token generation, incremental responses, server-sent events,
  chunked response delivery, or partial-completion callbacks would each require expanding Stage 13's
  own frozen `invoke()` contract — a new design pass against Stage 13 itself, never something this
  document or any concrete implementation architected under it may introduce unilaterally. This is
  real future work a later architecture phase could take on; it is not performed here (Prompt
  Lifecycle — streaming boundary, Adapter Contract).
- **Introducing conversation state.** Conversation history, chat session management, persistent
  conversations, provider-managed sessions, conversational memory, or dialogue state of any kind would
  require a future architecture phase, not an extension of Phase 1.2 — each `invoke()` call
  architected under this document is independent; no state from one call is read, stored, or
  referenced by a later call.

**Category B — permanent frozen-stage prohibitions, not composition-root or future-phase work.** Each
item below is never performed by any actor, at any future point, by anyone — this is not deferred work
waiting on a future phase; it is a permanent boundary that exists because Stage 12 and Stage 13 are
frozen:

- **Modifying Stage 13's own orchestration, Retry Policy, Timeout Policy, or Validation.** Untouched
  and unduplicated by this document or by any concrete implementation architected under it,
  permanently — not a task any future actor ever takes on.
- **Defining prompt engineering, prompt templates, prompt construction, or prompt budgeting.** These
  remain Stage 12's own frozen responsibility, permanently — this document's own adapters only ever
  receive already-assembled `system_prompt`/`user_prompt` strings via `invoke()`'s own parameters, and
  interpret them no further than Stage 13 itself does.

Every stage from Stage 0 through Stage 21, Phase 1.1 in full, and Phase 1.3 in full, remain exactly as
independently usable, and exactly as frozen, as they already are today. Phase 1.2 adds a way to
*build* what the `LLM_PROVIDER` seam already knows how to receive — it adds nothing Stage 12, Stage 13,
or Phase 1.1 must call differently, and nothing they must change to receive it.
