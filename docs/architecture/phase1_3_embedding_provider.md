# Phase 1.3 — Embedding Provider Architecture

Stages 0–21 and Phase 1.1 (Configuration Layer) remain completely frozen; nothing below proposes any
change to existing code or shipped docs. Phase 1.3 defines the architecture for a **concrete**
implementation of the abstract `ProviderAdapter` contract Stage 8 already declares
(`docs/architecture/stage8_embeddings.md`, `scripts/stage8_embedding_generation.py:52`), registered
under the `EMBEDDING_PROVIDER` seam Phase 1.1 already recognizes (`SUPPORTED_SEAMS`).

**Provider-neutrality, stated once, governing this entire document:** this architecture is
provider-agnostic. It defines the shape any concrete embedding provider must take to satisfy Stage
8's frozen contract and Phase 1.1's frozen wiring contract — it does not depend on, assume, or encode
the semantics of any specific vendor SDK. Where a provider is named for illustration (Gemini, OpenAI,
VoyageAI, Cohere, SentenceTransformers, or any other), the name is illustrative only, never a binding
design constraint. Nothing in this document requires a network call at all — a concrete adapter
wrapping a local model (e.g., a SentenceTransformers model loaded in-process) satisfies this
architecture exactly as a concrete adapter wrapping a hosted API does; the two differ only in whether
`network_dependent` (Phase 1.1's `ProviderRegistration` field) is `True` or `False`.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Stage 8's own Configuration section (` docs/architecture/stage8_embeddings.md`) states the
`ProviderAdapter` contract in full and explicitly declines to select or implement a default: "No
default provider is stubbed or selected — implementing the first concrete adapter is a separate,
later task." Phase 1.1 closes the *wiring* half of that gap — it defines how a concrete adapter,
once it exists, is supplied to Stage 8/Stage 10 as configuration (`EMBEDDING_PROVIDER` seam,
`ProviderSettings`, `wire_dependencies()`). Neither Stage 8 nor Phase 1.1 defines what a concrete
adapter itself must do internally to be a correct, safe, production-grade implementation of that
contract. That is the entire, narrow gap Phase 1.3 closes.

Phase 1.3 does not implement any adapter. It defines: (1) the architecture any concrete
`ProviderAdapter` implementation must follow — SDK client ownership and lifecycle, credential
consumption, provider identity, model pinning discipline, and internal request/response handling;
(2) the `ProviderRegistration` contract a concrete implementation supplies to Phase 1.1's
`build_provider_registry()`; and (3) the exception-classification discipline a concrete
implementation's `is_transient_error()` must follow, without ever implementing the retry loop that
consumes it.

**Boundary rule, stated once, governing this entire document:** Stage 8's `ProviderAdapter` contract
is frozen and is never re-defined, extended, or altered here — it is quoted, cited, and built against.
Phase 1.1's `ApplicationSettings`/`ProviderSettings`/`ProviderRegistration`/`wire_dependencies()`
contracts are equally frozen and are never re-defined here. Phase 1.3 is the thing standing between
them: it describes how a real, concrete class satisfies the first contract while being correctly
constructible by the second.

## Scope

Phase 1.3 answers exactly one question — given a `ProviderSettings` object and (if `credential_ref`
was present) a resolved raw credential string, supplied by Phase 1.1's `wire_dependencies()` exactly
as its own Public Function Contracts already describe, what is the architecture of a concrete class
that (a) satisfies Stage 8's frozen `ProviderAdapter` contract, (b) owns exactly one SDK client (or
in-process model handle) for its own lifetime, and (c) can be supplied to `build_provider_registry()`
as a `ProviderRegistration` — and stops there.

It never selects which provider is active for the `EMBEDDING_PROVIDER` seam (Phase 1.1's own job,
via `ApplicationSettings`). It never constructs a retrieval closure, never modifies Stage 8's own
batching/retry orchestration, never modifies Stage 10's `retrieve`/`embed_query` closures, never
edits `ProviderRegistry`, and never performs dependency wiring of any kind (Future Phase Boundaries).
It never introduces retrieval logic, FAISS logic, or vector-database logic of any kind — those remain
exactly where Stage 9/Stage 10 already own them. It never implements LLM functionality (a separate,
future Phase 1.2 concern) or query execution (Stage 10/18's own frozen job).

## Responsibilities

Phase 1.3 shall: define the architecture of a concrete `ProviderAdapter` subclass that fully and
exactly implements Stage 8's frozen abstract contract (Adapter Contract); define the ownership and
lifecycle of the one SDK client (or in-process model handle) a concrete adapter instance holds,
from construction through disposal, never escaping the adapter instance (Embedding Lifecycle); define
how a concrete adapter's constructor consumes the `(ProviderSettings, Optional[str])` pair Phase 1.1's
`wire_dependencies()` already calls a registered factory with, and what it does with the resolved raw
credential (Provider Configuration, Security Considerations); define provider identity as the stable
triple `(provider_name, model_name, model_version)` a concrete adapter exposes for the lifetime of its
instance (Provider Model); define the model-pinning discipline every concrete adapter must follow,
reinforcing — never redefining — Stage 8's own frozen requirement that `model_version` be an explicit,
non-floating value (Provider Configuration); define the `ProviderRegistration` a concrete
implementation supplies to Phase 1.1's `build_provider_registry()`, including the correct
`network_dependent` declaration (Public Function Contracts); define the exception-classification
discipline a concrete adapter's `is_transient_error()` implementation must follow (Failure Handling).

## Non-Responsibilities

Phase 1.3 explicitly does **not** perform, and no future patch to it may silently add without a new
design pass: select, implement, or import any specific concrete embedding provider SDK (this document
defines the architecture any provider-specific implementation must follow; the implementation itself,
for any named provider, is separate, future, per-provider work never designed here); construct a
retrieval closure, edit `ProviderRegistry`, or perform dependency wiring of any kind — every one of
those remains exclusively owned by Phase 1.1's own composition root, a deferred responsibility, not a
permanent prohibition (Future Phase Boundaries); modify Stage 8's own batching/retry orchestration or
modify Stage 10's own `retrieve`/`embed_query` closures — unlike the composition-root items above,
these are not deferred to any future actor at all; Stage 8 and Stage 10 are frozen, so no one, ever,
performs this modification (Future Phase Boundaries); choose which provider is active for the
`EMBEDDING_PROVIDER` seam (`ApplicationSettings`,
Phase 1.1's own job, never this document's); implement retry, backoff, or timeout *looping* logic of
any kind (Stage 8's own frozen orchestration already owns the retry loop that consumes
`is_transient_error()`; Phase 1.3 defines only the classifier a concrete adapter's
`is_transient_error()` must implement, never the loop — Failure Handling); implement retrieval,
chunking, indexing, or any FAISS/vector-database logic of any kind (Stage 9/10's own frozen job);
implement LLM functionality or query execution of any kind (a separate, future Phase 1.2 concern, and
Stage 10/18's own frozen job, respectively); re-define, re-default, or re-clamp any tunable Stage 8's
own Configuration already owns (`BATCH_SIZE`, or any other); hold any global mutable state; introduce
a new logging namespace, `stage` identifier, or closed log-code vocabulary distinct from Stage 8's own
(Logging Vocabulary); move a responsibility from Stage 8, Stage 10, or Phase 1.1 into this document,
or from this document into any of them.

## Inputs

Two inputs, both supplied by Phase 1.1's `wire_dependencies()` exactly as its own Public Function
Contracts already describe — a concrete adapter's constructor (or the factory function that builds
it) never reads any other source:

- **`ProviderSettings`** — the seam's resolved configuration object (Phase 1.1's own schema): names
  the active `provider_name`, carries an `extra: Dict[str, Any]` passthrough this document is the
  first to interpret for the `EMBEDDING_PROVIDER` seam (Provider Configuration), and a
  `credential_ref` (an opaque reference, never a raw value).
- **An optional resolved raw credential (`Optional[str]`)** — the second positional argument Phase
  1.1's `wire_dependencies()` already passes to every registered factory, resolved from
  `credential_ref` immediately before the factory call, and `None` if the seam carries no
  `credential_ref` (e.g., a purely local, in-process model with no API key).

No environment variable, `.env` file, or secret store is ever read directly by a concrete adapter or
its factory — that reading is Phase 1.1's own exclusive responsibility, already performed before
either of the two inputs above reaches this layer.

## Outputs

- **One constructed instance conforming to Stage 8's frozen `ProviderAdapter` contract** — returned
  by the factory function `wire_dependencies()` invokes; nothing else is returned to Phase 1.1.

No file is written by any concrete adapter architected under this document. No new artifact
directory is introduced. There is no manifest interaction of any kind — the same zero-artifact
posture Phase 1.1 itself already established, extended here to the concrete provider layer.

## Provider Model

### Provider identity

A concrete adapter's identity is the stable triple:

```
(provider_name, model_name, model_version)
```

exactly the three fields Stage 8's own frozen contract already exposes as properties. This triple is
fixed for the entire lifetime of a constructed adapter instance — none of the three values may change
after construction. It is the basis of the `config_fingerprint_fields` a concrete adapter contributes
(Stage 8's own frozen contract field), and — one layer up — a contributor to Phase 1.1's own
`settings_fingerprint` by way of the `provider_name` already present on `ProviderSettings`. A
deployment that changes any one of the three values is, by definition, running a different provider
identity — the same content-identity discipline every frozen stage's own `*_id`/`*_fingerprint`
convention already establishes, applied here to provider selection rather than document or
configuration content.

### Relationship to Stage 8's frozen contract

A concrete adapter is a plain subclass of Stage 8's `ProviderAdapter` base class
(`scripts/stage8_embedding_generation.py:52`) implementing every property and method that class
declares, with no additions to the class's own public surface visible to Stage 8's orchestration.
Stage 8 calls `embed_batch(texts) -> List[List[float]]` and nothing else on the hot path; a concrete
adapter's constructor and any private helper methods are invisible to, and never called directly by,
Stage 8's own orchestration code.

### Internal request/response shape — adapter-private, not a new public contract

A concrete adapter that wraps a hosted API necessarily constructs some request representation to
send to that API and parses some response representation it receives back. This document names the
minimum information such a representation must carry, illustratively, entirely internal to a
concrete adapter, and **never** a new public contract this document mandates verbatim or exposes past
the adapter boundary:

```
# Illustrative only — entirely private to a concrete adapter's own implementation.
# Never returned from embed_batch(), never seen by Stage 8, never a Phase 1.1 concern.
_RawEmbeddingRequest:  { model_name, model_version, texts: List[str] }
_RawEmbeddingResponse: { vectors: List[List[float]], usage_metadata: Optional[Dict] }
```

`embed_batch(texts: List[str]) -> List[List[float]]` remains, exactly as Stage 8 already froze it,
the only shape a concrete adapter exposes outward. Any internal representation a concrete
implementation uses to talk to its own SDK is that implementation's own private concern, never
standardized by this document beyond the illustrative shape above.

## Embedding Lifecycle

A strictly linear construction-to-disposal model, never a stored, mutable state machine — mirroring
Phase 1.1's own Design Decision #3 reasoning: nothing in a concrete adapter's own lifecycle branches
on an external, non-deterministic decision the way Stage 21's planning loop does.

```
[1] Factory invocation           — wire_dependencies() invokes the registered factory with
      (ProviderSettings, Optional[str]); the second argument is the resolved raw credential, or None
      │
      ▼
[2] SDK client construction      — the factory (or the adapter's own __init__) constructs exactly one
      SDK client (or, for a local model, loads exactly one in-process model handle), consuming the
      resolved raw credential exactly once; the client/handle is stored only as a private attribute
      on the constructed adapter instance
      │
      ▼
[3] Adapter instance returned    — the fully constructed, ProviderAdapter-conforming instance is
      returned to wire_dependencies(), which places it in WiringResult.wired[EMBEDDING_PROVIDER]
      │
      ▼
[4] Repeated embed_batch() calls — Stage 8's own orchestration calls embed_batch(texts) zero or more
      times over the adapter instance's lifetime, each call using the same SDK client/handle
      constructed in step [2]; no reconstruction, no reconnection between calls
      │
      ▼
[5] Disposal                     — when the process holding the adapter instance ends (or, in a test
      harness, when the instance is explicitly discarded), the SDK client/handle is released with it;
      this document defines no explicit disposal method beyond ordinary object lifetime, since no
      frozen stage's own contract calls one
```

### SDK client ownership — stated explicitly, governing this entire document

- **This document's own architecture owns SDK client construction.** Construction happens exactly
  once, at step [2] above, inside the factory or the adapter's own constructor — never lazily on
  first `embed_batch()` call, never re-constructed between calls.
- **This document's own architecture owns SDK client disposal.** Disposal is tied to the adapter
  instance's own object lifetime; no external caller is ever responsible for explicitly closing or
  releasing a concrete adapter's SDK client.
- **The SDK client never escapes the adapter instance.** It is never returned from any public method,
  never placed on `ProviderSettings`, `WiringResult`, or any object Phase 1.1 returns, and never
  passed to any frozen stage. Stage 8 and Stage 10 call `embed_batch()`/`embed_query()`; neither ever
  receives, holds, or references the SDK client itself.
- **Phase 1.1 never owns the SDK client.** Phase 1.1's `wire_dependencies()` invokes the factory
  exactly once and receives back the fully constructed adapter instance; it never receives the SDK
  client directly, never inspects it, and never holds a reference to it independent of holding the
  adapter instance itself.
- **Stage 8 never owns the SDK client.** Stage 8 receives the adapter instance via dependency
  injection (Phase 1.1's own Dependency Wiring Model) and calls only the methods Stage 8's own frozen
  contract already names. Stage 8's own module never imports a provider SDK, never constructs a
  client of any kind, and never holds a reference to one outside the adapter instance it was handed.

## Provider Configuration

### `ProviderSettings.extra` — interpreted here, for this seam only

Phase 1.1's own Configuration Model defines `ProviderSettings.extra: Dict[str, Any]` as a
"provider-specific, uninterpreted passthrough" that Phase 1.1 itself "never interprets, validates the
meaning of, or defaults." Phase 1.3 is the first, and only, document that interprets this field, and
only for the `EMBEDDING_PROVIDER` seam. A concrete adapter's own factory reads whichever of the
following keys its own provider needs; no key is mandatory across every concrete implementation, and
a concrete implementation is free to define additional keys of its own, since `extra`'s contents
remain that implementation's own concern, never a schema this document closes:

```
extra = {
    "model_name":            "<provider's own model identifier>",   # forwarded to model_name property
    "model_version":         "<pinned version/revision string>",    # forwarded to model_version property — see Model Pinning
    "api_base_url":          "<optional endpoint override>",
    "request_timeout_seconds": "<optional per-call timeout>",
    "sdk_max_retries":        "<optional SDK-internal connection-level retry count>",
    "max_batch_size_override": "<optional override of this adapter's own max_batch_size>",
}
```

`sdk_max_retries` above governs only an SDK client's own low-level connection retry behavior (e.g.,
retrying a dropped TCP connection) — it is not, and must never be conflated with, the semantic
retry loop Stage 8's own orchestration performs against `is_transient_error()` (Failure Handling).
Timeout and SDK-level retry count are this adapter's own configuration, exactly as Stage 13's
`LLMAdapter` already establishes for its own credentials and knobs — never a Phase 1.1 concern
(`RuntimeConfig` "never carries a timeout, retry count, or sampling parameter") and never a Stage 8
concern (Stage 8's own Configuration section defines no timeout or retry-count field of its own for
the provider layer).

### Supported embedding dimensions

A concrete adapter's `embedding_dimension` property (Stage 8's own frozen contract field) returns a
fixed integer for the pinned `(provider_name, model_name, model_version)` triple the adapter was
constructed with — e.g., a specific hosted model at a specific pinned revision, from a specific
provider, has exactly one dimension. This document
does not enumerate a global list of supported dimensions across all possible providers, since the set
of providers is open-ended by design (provider-neutrality). Stage 8's own frozen behavior of
discovering and verifying dimension against a real first returned vector at run start is unaffected
by, and not owned by, this document.

### Batching rules

Stage 8 already owns `BATCH_SIZE = 32` as its own module constant and already clamps its own batching
loop to `min(BATCH_SIZE, provider.max_batch_size)`. A concrete adapter's own `max_batch_size` property
(Stage 8's own frozen contract field, `Optional[int]`, default `None`) declares that provider's own
upper bound, if one exists; `extra["max_batch_size_override"]` (above) lets deployment configuration
narrow that bound further without a code change, but a concrete adapter's own factory — never this
document, never Stage 8 — decides whether to honor an override smaller than the provider's true
ceiling. This document never re-defines, re-defaults, or duplicates Stage 8's own `BATCH_SIZE`
constant.

### Model pinning

Stage 8's own frozen contract already states: `model_version` is "a **pinned** version/revision
string; `"latest"` or any unpinned alias is disallowed by contract." Phase 1.3 reinforces — never
redefines — this requirement, for every concrete adapter architected under this document:

- `model_version` must always be an explicit, pinned value — a specific revision, snapshot, or
  version identifier the provider itself exposes, never a floating alias.
- A value such as `"latest"`, `"stable"`, or any other alias whose target can change without a
  configuration change is prohibited, exactly as Stage 8's own contract already states.
- Changing which model version an adapter uses always requires an explicit configuration change —
  a new `extra["model_version"]` value, deployed deliberately — never a change in behavior triggered
  by the provider silently updating what an existing pinned identifier resolves to.
- A concrete adapter must never silently upgrade the model it uses. If a provider deprecates a pinned
  version, the correct response is a configuration change (a new pinned value) deployed deliberately,
  never an automatic fallback to a different version chosen by the adapter itself.

## Adapter Contract

Restated here by citation, not redefinition — Stage 8's own frozen `ProviderAdapter` contract
(`docs/architecture/stage8_embeddings.md`, `scripts/stage8_embedding_generation.py:52`):

```python
class ProviderAdapter:
    provider_name: str             # property — short, fixed string identifying the provider family
    model_name: str                # property — the provider's own model identifier, verbatim
    model_version: str             # property — pinned; "latest" or any unpinned alias disallowed
    embedding_dimension: int       # property — discovered from the provider's actual first
                                    #   returned vector at run start, not hardcoded per adapter
    def embed_batch(self, texts: List[str]) -> List[List[float]]: ...
    def is_transient_error(self, exception: Exception) -> bool: ...
    requests_per_minute: Optional[int]        # property, default None
    max_batch_size: Optional[int]             # property, default None
    config_fingerprint_fields: Dict[str, Any] # property, default {}
```

This document adds nothing to this contract's own public surface — no new abstract method, no new
required property, no changed signature. Everything Phase 1.3 defines (SDK client ownership, provider
identity stability, model pinning discipline, `extra` interpretation, exception-classification
discipline) governs how a concrete subclass is built and configured; none of it is visible to Stage
8's own orchestration, which continues to see exactly the contract above and nothing more.

## Validation

Two distinct, clearly-scoped groups, deliberately kept separate — mirroring the same discipline Phase
1.1 already applied when adapting the three-tier model to its own object lifecycle (Phase 1.1 Design
Decision #4):

**1. Construction-time validation** — a concrete adapter's own constructor (or factory) validates the
inputs it directly receives, before constructing its SDK client:

- `ProviderSettings.extra` carries whatever keys this specific provider requires (e.g., `model_name`,
  `model_version`) — a missing required key is this concrete implementation's own error to raise, in
  whatever exception type is natural to it; this document mandates no closed vocabulary of
  construction-time error codes, since the set of possible concrete implementations, and their own
  required `extra` keys, is open-ended by design.
- If the provider requires a credential (`credential_ref` was present on `ProviderSettings`) and the
  resolved raw credential argument is `None` or empty, construction must fail — a concrete adapter
  never silently constructs an unauthenticated client when a credential was expected.
- `model_version` must be a pinned value (Model Pinning) — a concrete adapter's own construction-time
  check, never delegated to Stage 8 or Phase 1.1.

**2. Runtime validation** — remains exactly where Stage 8's own frozen contract already places it:
Stage 8's own orchestration validates `embed_batch()`'s return value (one vector per input text, in
order) and discovers/verifies `embedding_dimension` against the first real returned vector. This
document neither duplicates nor relaxes any of Stage 8's own runtime validation.

There is no third, Phase-1.1-style "wiring-level" validation tier here — `build_provider_registry()`
and `wire_dependencies()` remain exactly as Phase 1.1 already froze them; this document supplies
inputs to that machinery (a `ProviderRegistration`) without adding a new validation tier of its own.

## Public Function Contracts

- **The factory function contract** — `Callable[[ProviderSettings, Optional[str]], ProviderAdapter]`
  — exactly the signature Phase 1.1's own `ProviderRegistration.factory` field and `wire_dependencies()`
  contract already establish. A concrete implementation's factory: reads whatever keys it needs from
  `settings.extra`; performs Construction-time validation (above); constructs exactly one SDK client
  (or model handle) from the resolved raw credential (the second argument), if one was supplied;
  returns a fully constructed instance conforming to Stage 8's `ProviderAdapter` contract; raises on
  any construction-time validation failure, in whatever exception type is natural to the concrete
  implementation — this document mandates no shared exception base class for construction failures,
  since Phase 1.1's own `wire_dependencies()` treats a factory's return value opaquely and propagates
  any exception a factory raises without inspecting its type.

- **The `ProviderRegistration` this document's implementations supply** — `seam="EMBEDDING_PROVIDER"`,
  a `provider_name` unique among registrations for that seam, `network_dependent` set truthfully by
  the concrete implementation (`True` for any adapter that opens a network socket during construction
  or during `embed_batch()`; `False` for a purely local, in-process model), and the factory described
  above. This document defines the shape of this registration; it does not itself call
  `build_provider_registry()` or assemble a list of registrations — that remains the application
  composition root's own job (Future Phase Boundaries).

No function architected under this document ever imports Phase 1.1's own internals, ever reads
`os.environ` directly (the resolved credential always arrives as an argument, never read from the
environment by this layer), or ever opens a network socket outside of what its own SDK client does on
its own provider's behalf.

## Determinism

**Deterministic (guaranteed, given identical input):**

- Which `(provider_name, model_name, model_version)` triple a concrete adapter exposes, given
  identical `ProviderSettings` — a pure function of the configuration it was constructed with.
- `config_fingerprint_fields`, given an identical constructed instance — a pure function of that
  instance's own identity, never of any live network state.
- Whether construction-time validation passes or fails, given identical `(ProviderSettings,
  Optional[str])` inputs.

**Explicitly NOT deterministic (inherent to a real provider; never assumed, never hidden):**

- **The actual embedding vectors `embed_batch()` returns**, for any adapter backed by a live model
  (hosted or local) — a real model's output is that model's own concern, never something this
  architecture claims byte-identical reproducibility for. The shared Design Philosophy
  (`docs/pipeline_principles.md` §1.5), which Stage 8 inherits rather than restates, already
  excludes "any AI/LLM call anywhere in this pipeline" from its own no-randomness guarantee at
  the pipeline level; an embedding provider, once one exists, is the one narrow place a probabilistic
  or provider-versioned computation legitimately enters this repository, and this document does not
  pretend otherwise.
- **SDK client construction side effects** — a real SDK client may perform its own connection setup,
  credential validation against a live endpoint, or similar work at construction time; this document
  makes no claim about what a specific SDK does internally during step [2] of the Embedding Lifecycle.
- **Whether a specific SDK exception classifies as transient** in a way that depends on live network
  conditions (a timeout that would not occur under different network conditions, for instance) — the
  classification rule itself (Failure Handling) is deterministic given an exception instance, but
  which exception a live call actually raises is not.

## Read-Only Guarantees

- Phase 1.3 never modifies `manifest.json`, any corpus artifact, any vector index, any chunk, any
  prompt template, or any cache store entry — it has no relationship to any of them at all.
- A concrete adapter never modifies `ProviderSettings` after receiving it — it reads from `extra` and
  `credential_ref`/the resolved credential, never mutates either.
- A concrete adapter holds no module-level mutable state of its own; every piece of state it needs
  (its SDK client, its own identity triple) lives on the constructed instance itself, never in a
  module-level variable shared across instances.
- The only external side effects an SDK client may perform are whatever its own provider's SDK does
  on its own behalf (a network call, a local model's own file/memory access) — this document defines
  no additional side effect of its own beyond what Embedding Lifecycle step [2] and step [4] already
  name.

## Failure Handling

- **A construction-time validation failure** (missing required `extra` key, missing credential when
  one was expected, an unpinned `model_version`) — the factory raises immediately, before any SDK
  client is constructed; `wire_dependencies()` propagates whatever exception the factory raised
  (Phase 1.1's own `wire_dependencies()` contract already treats a factory's exceptions opaquely).
- **An SDK-level exception raised from `embed_batch()`** — classified by the concrete adapter's own
  `is_transient_error(exception) -> bool` into exactly two categories, a closed conceptual taxonomy
  every concrete implementation's classifier must sort real exceptions into:
  - **Transient** — a failure a retry is expected to resolve: a rate limit, a timeout, a dropped
    connection, a transient server-side error. `is_transient_error()` returns `True`.
  - **Fatal** — a failure no retry will resolve: an authentication failure, a malformed request, a
    permanently exceeded quota, an unsupported input. `is_transient_error()` returns `False`.
- **The retry loop itself is never implemented here.** Stage 8's own frozen orchestration owns the
  loop that calls `embed_batch()`, catches an exception, consults `is_transient_error()`, and decides
  whether to retry or fail the batch. This document defines only the classifier a concrete adapter's
  `is_transient_error()` must implement — the boolean judgment — never the loop, the backoff schedule,
  or the retry-count ceiling that consumes that judgment. Duplicating any of that here would violate
  this document's own Non-Responsibilities.
- **No fallback provider, no silent degradation.** If a concrete adapter's construction fails, or if
  `embed_batch()` exhausts Stage 8's own retry budget, the failure propagates exactly as Stage 8's own
  Failure Handling already specifies (`FATAL_EMBEDDING_FAILED`, `FATAL_EMBEDDING_PROVIDER_UNAVAILABLE`)
  — never a silent substitution of a different provider or a degraded, partially-computed embedding.

## Security Considerations

- **Credential consumption.** A concrete adapter's factory receives the resolved raw credential as
  its second positional argument, exactly as Phase 1.1's `wire_dependencies()` contract already
  supplies it. The factory consumes this value exactly once, at construction time, to build its SDK
  client; it retains no separate copy of the raw string after construction — the SDK client itself
  becomes the credential's sole holder, matching Phase 1.1's own Security Considerations ("the
  constructed adapter instance is the sole remaining holder of the credential").
- **SDK client as sole credential holder.** After construction, only the SDK client instance held by
  the adapter carries the credential (in whatever form that SDK's own client object holds it — a
  header, a signed token, or similar). No field on the adapter instance itself, and no field on any
  object this document defines, stores the raw credential as a plain, independently-readable value.
- **No credential logging.** A concrete adapter never logs, prints, or serializes the resolved raw
  credential argument, at any severity, under any circumstance — the same hard constraint Phase 1.1
  already states for its own layer, extended here to the layer that actually receives the value.
- **No credential serialization.** The resolved raw credential is never converted to JSON, a dict, or
  any other serializable form by this document's own architecture, for logging, caching, or transport
  — mirroring Phase 1.1's own "No secret serialization" guarantee, extended here to the layer that
  actually receives the value. Whatever serialized form an SDK client constructs internally to
  authenticate its own requests (a signed header, a bearer token) is that SDK's own concern,
  inherited by a concrete adapter, never introduced by this document.
- **No credential persistence.** Nothing this document architects writes the resolved raw credential
  to disk, to a cache store, to the manifest, or to any artifact of any kind — mirroring Phase 1.1's
  own "No secret persistence" guarantee. If a specific SDK client persists its own token to a local
  cache as part of its normal operation, that is inherited SDK behavior, never something this
  document introduces or is responsible for.
- **No raw request/response payload logging beyond Stage 8's own Logging Specification.** Stage 8's
  own shared Logging Specification already states "No document content logged above DEBUG." A
  concrete adapter's own diagnostic logging, if any, follows the same discipline for the request/
  response payloads it exchanges with its own SDK — chunk text and returned vectors are content, not
  metadata, and are never logged above DEBUG by any adapter architected under this document.
- **No network isolation guarantee.** Unlike Phase 1.1, which reads only `os.environ` and an optional
  `.env` file, a concrete adapter architected under this document may open a real network socket to
  its provider's own endpoint. This document makes no claim that such an adapter is network-isolated;
  it only guarantees that the *credential* reaching that socket is handled exactly as described above.

## Logging Vocabulary

This section defines the vocabulary available to a concrete adapter **if** it emits logs; exactly
like Phase 1.1's own Logging Vocabulary section, it does not mandate that logging occur.

This document introduces no new `stage` identifier and no new closed-vocabulary log codes. A concrete
adapter operates inside Stage 8's own runtime; Stage 8's own shared Logging Specification already
owns the `stage: "stage8_embedding_generation"` identifier and the closed codes that apply when
`embed_batch()` ultimately fails after Stage 8's own retry budget is exhausted
(`FATAL_EMBEDDING_FAILED`, `FATAL_EMBEDDING_PROVIDER_UNAVAILABLE` — Stage 8's own Design Decisions).
Extending that vocabulary is Stage 8's own revision path, never this document's.

A concrete adapter that wishes to emit its own internal diagnostic information (for example, "SDK
client constructed" or "SDK client construction failed") may do so at DEBUG severity or below the
same floor Stage 8's own Logging Specification already establishes for document content — no new
INFO/WARNING/FATAL code is defined by this document for that purpose. Any such diagnostic log entry is
subject to the same hard constraint stated in Security Considerations: it may never include the
resolved raw credential, any raw request/response payload, or any value that would violate Stage 8's
own "No document content logged above DEBUG" rule.

## Concurrency

A concrete adapter instance is constructed exactly once (Embedding Lifecycle step [2]) and its
`embed_batch()` method may be called repeatedly over its lifetime (step [4]). This document does not
mandate that a concrete adapter's `embed_batch()` be safe to call concurrently from multiple threads —
that is a property of the specific SDK client a concrete implementation wraps, never something this
architecture can guarantee on that SDK's behalf. A concrete implementation that wraps a thread-safe
SDK client inherits that safety; one that wraps a non-thread-safe client does not, and Stage 8's own
orchestration (which this document does not modify) determines whether concurrent calls are ever
attempted.

Phase 1.3 defines no locking, no mutex, and no coordination of its own beyond what Embedding
Lifecycle already describes — the same "no coordination introduced beyond what the wrapped resource
itself requires" posture, stated explicitly rather than left as an unstated gap.

## Design Decisions

1. **This architecture is provider-neutral by construction, not by convention.** Every section above
   is written to hold for any concrete `ProviderAdapter` implementation — hosted or local, any vendor
   — because the set of embedding providers this repository may eventually support is open-ended, and
   a document that silently assumed one vendor's SDK semantics (e.g., a specific error class hierarchy,
   a specific batching ceiling) would need a new design pass for every additional provider. Naming a
   provider anywhere in this document is illustrative only, never load-bearing.

2. **SDK client ownership is stated as an explicit, first-class rule, not left implicit.** A
   configuration/wiring layer is the most natural place for a "who holds the client" question to be
   answered ambiguously, exactly the same risk Phase 1.1's own Design Decision #1 named for global
   mutable state. Stating explicitly that the SDK client never escapes the adapter instance — and
   that neither Phase 1.1 nor Stage 8 ever holds it — closes off an entire class of implementation
   mistakes (a client accidentally exposed on `ProviderSettings`, or serialized into a log) before any
   concrete implementation is written.

3. **Model pinning is reinforced here, not redefined.** Stage 8's own frozen contract already
   prohibits floating aliases like `"latest"`. Restating the rule here, with the operational
   consequence spelled out (a version change always requires a deliberate configuration change, never
   a silent provider-side upgrade), closes the gap between Stage 8's one-sentence contract statement
   and the operational discipline a real deployment needs to actually honor it.

4. **Provider identity is defined as a stable triple, matching every frozen stage's own `*_id`
   convention.** `(provider_name, model_name, model_version)` mirrors the same "identity is exactly
   the fields that determine it, fixed once assembled" discipline Phase 1.1's own
   `settings_fingerprint` and every frozen stage's own content-hash convention already establish,
   applied here to a live object instance rather than a hashed artifact.

5. **The retry loop is named as explicitly out of scope, not merely omitted.** Given how naturally a
   "provider adapter" document could drift into owning retry/backoff behavior, this document states
   the boundary directly: `is_transient_error()` is a classifier this document owns; the loop that
   consumes it is Stage 8's own frozen orchestration. Leaving this unstated would risk a future
   concrete implementation duplicating Stage 8's own retry logic inside the adapter itself.

6. **No shared exception base class is mandated for construction-time failures.** Phase 1.1's own
   `wire_dependencies()` already treats a factory's exceptions opaquely — it propagates whatever a
   factory raises without inspecting its type. Mandating a shared exception hierarchy here would add
   a cross-cutting contract neither Stage 8 nor Phase 1.1 asked for, for no benefit any consumer of
   this architecture actually needs.

7. **Composition-root responsibilities are named exhaustively in Future Phase Boundaries, not
   scattered across this document.** Rather than repeating "this is the composition root's job" at
   every section where the temptation to describe integration arises, this document states the full,
   closed list once, in one place, and cross-references it — the same discipline Phase 1.1 itself uses
   when citing its own Design Decisions and Non-Responsibilities by name rather than restating them.

## Constants

```python
# This document defines no numeric threshold, ceiling, or default of its own — BATCH_SIZE remains
# Stage 8's own constant; timeout, SDK-level retry count, and any per-provider ceiling are
# ProviderSettings.extra values a concrete implementation interprets for itself (Provider
# Configuration). Provider-neutrality (Design Decisions #1) means this document names no closed set
# of provider identifiers, model names, or dimensions — that set is open-ended by design.

EMBEDDING_PROVIDER_SEAM_NAME = "EMBEDDING_PROVIDER"  # already Phase 1.1's own constant, restated
                                                      # here only to name which seam this document
                                                      # concerns; not a new constant this document
                                                      # introduces or owns.
```

No numeric threshold, ceiling, or default belonging to Stage 8 or Phase 1.1 (`BATCH_SIZE`,
`CONFIGURATION_LAYER_VERSION`, or any other) is duplicated here — every one of them already lives,
exactly once, in the document that owns it.

## Complexity

- **Construction (factory invocation, Embedding Lifecycle step [2])** — O(1) from this document's own
  perspective; the actual cost of a specific SDK client's own construction (e.g., a TLS handshake) is
  that SDK's own concern, invisible to this architecture's own complexity accounting.
- **`embed_batch(texts)`** — bounded by Stage 8's own frozen batching discipline
  (`min(BATCH_SIZE, provider.max_batch_size)` texts per call); the cost of any one call is that
  provider's own concern, never something this document estimates on a specific SDK's behalf.
- **`is_transient_error(exception)`** — O(1), a direct classification of one exception instance
  against a small, closed conceptual taxonomy (Failure Handling).
- **Provider identity / `config_fingerprint_fields` access** — O(1), a direct property read of values
  fixed at construction time.

## Known Limitations

- **No cross-provider abstraction beyond `ProviderAdapter` itself.** This document does not define a
  shared internal base class, mixin, or helper library that concrete implementations must use — each
  concrete implementation is free to structure its own internals however it needs to, as long as the
  outward `ProviderAdapter` contract is satisfied. A future phase may find enough common structure
  across multiple concrete implementations to warrant a shared internal helper; that is a new design
  pass against this document, not assumed here.
- **No credential rotation support**, mirroring Phase 1.1's own named limitation: a credential
  consumed once at construction time is used for the constructed SDK client's entire lifetime; live
  rotation, if a provider requires it, is that concrete implementation's own concern, entirely inside
  its own SDK client, invisible to this architecture.
- **No multi-region, multi-endpoint, or provider-side failover architecture.** A concrete adapter
  targets exactly one endpoint (whatever `extra["api_base_url"]` or the SDK's own default resolves
  to) for its entire lifetime; routing across multiple endpoints for the same logical provider is a
  future, separate design pass, never assumed here.
- **No embedding-result caching of any kind.** This document defines no cache in front of
  `embed_batch()` — Stage 17's own `CacheAdapter` seam, if ever applied to embeddings rather than
  LLM responses, would be a separate, future design pass entirely outside this document's scope.
- **No batch-level partial-failure recovery beyond what Stage 8 already defines.** If a batch of texts
  partially succeeds at the SDK level (some vectors returned, some not), how that is represented is
  this document's own open question for any real, non-atomic SDK — Stage 8's own frozen contract
  assumes `embed_batch()` returns exactly one vector per input text or raises; a concrete
  implementation must resolve any partial-success SDK behavior into that all-or-nothing shape itself,
  and this document names the requirement without prescribing how any specific SDK's own partial-
  failure semantics should be reconciled with it.

## Future Phase Boundaries

This document defines the architecture for a concrete embedding provider implementation. Two
categories of excluded work follow, kept explicitly separate because they differ in kind, not just
in content: Category A is deferred to a future actor; Category B has no actor, ever.

**Category A — deferred composition-root responsibilities.** Each item below is real future work,
explicitly reserved for the application composition root Phase 1.1 already names (never a new phase
number invented here); it will eventually be done, just not by this document:

- **Constructing retrieval closures.** Producing the specific closed-over `retrieve`/`embed_query`
  callable Stage 10's own frozen Configuration section describes as "an implementation detail entirely
  internal to Stage 10, opaque to Stage 18" — building that closure from a wired `ProviderAdapter`
  instance is composition-root work, exactly as Phase 1.1's own Dependency Wiring Model already states.
- **Editing `ProviderRegistry`.** This document defines the shape of a `ProviderRegistration` a
  concrete implementation supplies; it does not itself call `build_provider_registry()`, and no
  concrete implementation architected under this document calls it either — assembling the full list
  of registrations from every provider module a deployment depends on remains the composition root's
  own job, exactly as Phase 1.1's own Provider Registration Model already states.
- **Performing dependency wiring of any kind.** `wire_dependencies()` remains exactly as Phase 1.1
  already froze it; this document supplies one of its possible inputs (a `ProviderRegistration`),
  never a modification to the function itself.

**Category B — permanent frozen-stage prohibitions, not composition-root work.** Each item below is
never performed by any actor, at any future point, by anyone — this is not deferred work waiting on
the composition root; it is a permanent boundary that exists because Stage 8 and Stage 10 are frozen:

- **Modifying Stage 8 orchestration.** Stage 8's own batching loop, retry loop, dimension discovery,
  and manifest interaction are untouched and unduplicated by this document or by any concrete
  implementation architected under it, permanently — not a task the composition root or any other
  future actor ever takes on.
- **Modifying Stage 10 retrieval.** Stage 10's own retrieval logic, ranking, and context assembly are
  untouched by this document, permanently, for the same reason.

Separately, and not to be confused with the composition-root work above: **Phase 1.2 — Concrete LLM
provider** (registered under seam `LLM_PROVIDER`) and **Phase 1.4 — Concrete planner provider**
(registered under seam `PLANNER_LLM_PROVIDER`) are each their own, separate, future phases, already
named in Phase 1.1's own Future Phase Boundaries section. Neither is designed, extended, or implied by
this document.

Every stage from Stage 0 through Stage 21, and Phase 1.1 in full, remain exactly as independently
usable, and exactly as frozen, as they already are today. Phase 1.3 adds the architecture for
*building* what the `EMBEDDING_PROVIDER` seam already knows how to receive — it adds nothing Stage 8,
Stage 10, or Phase 1.1 must call differently, and nothing they must change to receive it.
