# Phase 1.1 — Configuration Layer

Stages 0–21 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. Phase 1.1 is a new, additive layer that sits outside the stage sequence — it is not Stage 22,
and no future patch to it may silently become one. Its only job is to load, validate, and wire
configuration so that every frozen stage's own already-declared dependency-injection seam receives a
concrete object conforming to that seam's own contract — nothing else.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Every frozen stage from Stage 8 onward already defines its own abstract backend contract
(`ProviderAdapter`, `IndexAdapter`, `LLMAdapter`, `CacheAdapter`, `ConversationStore`,
`ToolRegistry`/`ToolAdapter`, `PlannerLLMAdapter`) and states, explicitly, in its own Configuration
section, that a concrete instance of that contract is runtime configuration, supplied by the caller —
never hard-coded (Stage 13's own phrasing, echoed identically by Stage 8, 9, 10, 17, 18, 19, 20, and
21). None of those stages specifies *how* the caller decides which concrete instance to supply, from
where, or how a secret required by that instance reaches it safely. That is the entire, narrow gap
Phase 1.1 closes.

Phase 1.1 introduces exactly three things: (1) a closed configuration object model
(`ApplicationSettings`, `ProviderSettings`, `RuntimeConfig`) describing every deployment-level and
provider-level tunable a caller needs before it can construct any of the objects listed above; (2) a
configuration lifecycle — load, validate, wire — expressed as a linear function pipeline, never a
stored, mutable state machine; and (3) a provider registration model that lets a future phase supply
concrete factories for each seam without ever requiring this document, or any frozen stage, to
change.

Phase 1.1 constructs no concrete provider. It does not choose Gemini, does not choose an embedding
model, does not touch Stage 13, and does not decide what a real LLM call looks like. It defines the
machinery by which some later, separate design constructs those things and hands the result to the
stages that already know exactly how to receive it.

**Boundary rule, stated once, governing this entire document:** every frozen stage's own
Configuration section already establishes that it receives dependencies exclusively through
injection, never by reading ambient state. Phase 1.1 does not change this. Stage 13 never reads an
environment variable. Stage 18, 19, 20, and 21 never import `os`, never open a `.env` file, never see
a raw secret. Every stage's own frozen contract is honored exactly as written; Phase 1.1 is the thing
standing outside every stage that performs the one act none of them perform themselves: reading the
outside world.

## Scope

Phase 1.1 answers exactly one question — given the process environment, an optional local `.env`
file, and whatever the deployment's own secret store exposes as environment variables, what is the
one, fully validated, immutable configuration object graph from which every frozen stage's own
already-declared dependency can be constructed — and stops there.

It never selects a concrete embedding model, LLM provider, cache backend, conversation store, tool
implementation, or planner backend (Non-Responsibilities). It never constructs a prompt, retrieves a
document, plans a step, calls a network endpoint, or authenticates against anything (each already
the frozen job of some stage, or explicitly reserved for a future, separate provider-implementation
phase). It never introduces an orchestration framework, a new pluggable execution engine, or a
runtime scheduler. It never moves a responsibility from one stage to another, and it never
duplicates a default, clamp, or ceiling any frozen stage's own Configuration section already owns.

## Responsibilities

Phase 1.1 shall: define a closed, versioned configuration object model representing every
deployment-level and provider-level tunable this repository's frozen stages already declare as
caller-supplied (Configuration Schemas); load configuration values from a closed, ordered set of
sources without inventing a source no stage doc implies exists (Configuration Sources); structurally
and range-validate every loaded value before it is placed into any configuration object
(Configuration Validation); define a provider registration mechanism by which a future,
separately-designed concrete adapter factory can be associated with a named provider for a named
seam, without modifying this document or any frozen stage (Provider Registration Model); construct,
from a validated configuration object and a supplied provider registry, the concrete adapter
instances each seam's owning stage already expects (Dependency Wiring Model); own every secret value
from the moment it is read from its source until the moment it is handed, exactly once, to the one
factory function that consumes it to construct a concrete adapter — and retain no reference to that
raw value afterward (Security Considerations).

## Non-Responsibilities

Phase 1.1 explicitly does **not** perform, and no future patch to it may silently add without a new
design pass: select, implement, or import any concrete LLM provider, embedding provider, cache
backend, conversation-store backend, tool implementation, or planner backend — every one of those is
a separate, future provider-implementation phase (Future Phase Boundaries); implement retry, backoff,
or timeout logic of any kind (Stage 13's own frozen Retry Policy and Timeout Policy, and Stage 20's
own adapter-level timeout delegation, are untouched and unduplicated here); construct a prompt,
retrieve a document, assemble context, extract a citation, validate groundedness, score answer
quality, cache a response, plan a step, or execute a tool (every one already a frozen stage's own
job); perform authentication of any kind against any provider (an adapter's own concern once
constructed, never this layer's); expose an HTTP endpoint, CLI command, or UI of any kind (a future
application-layer concern, described only as a consumer of this layer's output — Future Phase
Boundaries); persist configuration to any datastore, file, or cache of its own beyond the one-time
read of an optional `.env` file (Configuration Lifecycle); introduce LangChain, LlamaIndex, CrewAI,
AutoGen, Haystack, Semantic Kernel, DSPy, or any other orchestration framework of any kind; hold any
global mutable state (Design Decisions #1); re-define, re-default, or re-clamp any tunable a frozen
stage's own Configuration section already owns (`temperature`, `max_output_tokens`, `top_k`,
`groundedness_threshold`, and every other field already named in Stage 10 through 21's own frozen
schemas remain forwarded, verbatim, never touched here); move a responsibility from any stage into
this layer, or from this layer into any stage.

## Inputs

Three sources, all read only by this layer, never by any stage:

- **Process environment** (`os.environ`), the canonical production source.
- **An optional `.env` file**, read once at load time and folded into the same key/value space the
  process environment occupies — never a second, separately-merged configuration channel
  (Configuration Sources).
- **An optional deployment-level secret store** (a cloud secret manager, a container orchestrator's
  mounted secret, a CI/CD injected variable) — never a new contract of its own; every such source is
  expected to already present itself as a process environment variable by the time this layer reads
  it (Design Decisions #5). Phase 1.1 defines no client, SDK, or network call to any secret-management
  service.

A fourth, optional input exists only at the call level, never the process level: a caller (typically a
test harness) may supply an explicit key/value mapping to `load_raw_settings()` in place of
`os.environ`, for fully deterministic, network-free testing (Determinism).

No other input is read. No corpus artifact, manifest, vector index, embedding, prompt template, or
cache-store entry is ever opened by this layer — none of them bears on configuration.

## Outputs

- **`ApplicationSettings`** — one immutable object per successful `load → validate` pass.
- **`ProviderRegistry`** — one immutable object per successful `build_provider_registry` call,
  supplied by whatever future phase owns concrete provider factories.
- **`WiringResult`** — one immutable object per successful `wire_dependencies` call, carrying one
  constructed adapter instance per configured seam.

No file is written by this layer under any circumstance. No new artifact directory is introduced.
There is no manifest interaction of any kind — the same zero-artifact posture every query-time stage
from Stage 10 onward already established, extended here to the layer that configures them.

## Configuration Model

Three tiers of ownership, mirroring Stage 21's own three-tier Configuration split (deployment-level /
stage defaults / request-level overrides) one layer above every stage:

1. **Deployment-level configuration** — read from the environment/`.env`/secret store by this layer.
   Owned by whoever deploys the process. Represented by `ApplicationSettings`.
2. **Phase 1.1's own operational defaults** — a small, closed set of constants this layer itself
   owns (which `.env` filename to look for, the closed list of recognized seam names, the closed
   list of field names that must never be logged). Never a business-level default belonging to any
   stage (Constants).
3. **Request/session-level overrides** — the `pipeline_options`, `planning_config`, and
   `execution_config` fields Stage 10 through 21 already define on their own request schemas. Phase
   1.1 never touches this tier at all; it flows, exactly as today, directly from an external caller
   into the stage that already owns its own defaults and clamps (Design Decisions #2).

### Object model

- **`ApplicationSettings`** — the top-level, immutable, one-per-process-lifetime object. Holds a
  `RuntimeConfig` and a mapping of `{seam_name: ProviderSettings}`, one entry per **configured**
  seam (a seam with no entry is simply not configured — see Configuration Validation,
  `SEAM_NOT_CONFIGURED`).
- **`ProviderSettings`** — one per seam. Names *which* provider is active for that seam
  (`provider_name`, an opaque string meaningless to this layer beyond registry lookup), an opaque
  `credential_ref` (never the raw secret — see Security Considerations), and an `extra: Dict[str,
  Any]` passthrough for provider-specific knobs this layer never interprets, validates the meaning
  of, or defaults.
- **`RuntimeConfig`** — the handful of non-secret, non-per-provider knobs this layer itself owns:
  which `.env` path (if any) was loaded, and whether outbound network calls are permitted in this
  process at all (a boolean gate a future test/CI environment can set to `False`, causing
  `wire_dependencies` to refuse to invoke any factory whose `ProviderRegistration` declares
  `network_dependent = True` — Failure Handling). `RuntimeConfig` never carries a timeout, retry count, or
  sampling parameter — every one of those remains exactly where Stage 13/20 already define it.

### Ownership table

| Concern | Owner |
|---|---|
| Reading `os.environ` / `.env` | Phase 1.1, exclusively — no stage ever does this |
| Holding a raw secret value beyond the one wiring call that consumes it | The constructed adapter instance itself; Phase 1.1 relinquishes its own reference immediately after the factory call returns (Security Considerations) |
| Choosing *which* provider is active for a seam | Deployment configuration, resolved by Phase 1.1 from `ApplicationSettings`, never hard-coded here |
| Implementing a factory for a given provider name | A future, separate provider-implementation phase (Future Phase Boundaries); Phase 1.1 defines only the registration mechanism |
| Assembling a wired adapter into a specific frozen stage's own `PipelineDependencies`/`AgentDependencies` | The application's own composition root, a future layer this document does not implement — described only as a mapping (Dependency Wiring Model) |
| Every per-call tunable already named in Stage 10–21's own frozen schemas | That stage, exactly as already frozen; never re-defined, re-defaulted, or re-clamped here |

## Configuration Lifecycle

A strictly linear call sequence, never a stored, mutable state machine — configuration has no
external, non-deterministic decision to branch on the way Stage 21's planning loop does, so a full
state-machine model would misrepresent this layer's actual complexity (Design Decisions #3):

```
[1] load_raw_settings(env, dotenv_path)     — read process env (or an explicit override mapping),
      fold in an optional .env file's contents; returns an unvalidated RawSettings
      │
      ▼
[2] validate_settings(raw)                  — structural + range validation (Configuration
      Validation); raises ConfigurationInputError immediately on any violation — nothing downstream
      is ever touched; returns an immutable ApplicationSettings
      │
      ▼
[3] build_provider_registry(registrations)  — pure function over a caller-supplied list of
      ProviderRegistration entries (each supplying seam, provider_name, network_dependent, and
      factory), owned entirely by whichever future phase supplies concrete factories; returns an
      immutable ProviderRegistry
      │
      ▼
[4] wire_dependencies(settings, registry)   — for each seam present in settings.providers: if
      ProviderSettings.credential_ref is present, reads the named environment variable from
      os.environ exactly once, producing a transient raw credential that exists only in local scope
      for the duration of the factory call and is discarded when the call returns (Security
      Considerations); checks network_dependent on the matched ProviderRegistration against
      runtime.network_calls_permitted; looks up the seam's provider_name in registry; invokes the
      matching factory exactly once with (ProviderSettings, Optional[str]) — the second argument is
      the resolved raw credential, or None if no credential_ref is present; and assembles a
      WiringResult; raises ConfigurationWiringError on any unresolved or disallowed seam
      │
      ▼
[5] validate_wiring_result(result, settings) — internal invariant self-check; raises
      ConfigurationInternalError on violation
      │
      ▼
WiringResult { seam_name -> concrete adapter instance }
```

Each of the five steps runs **at most once** for a given `ApplicationSettings`/`ProviderRegistry`
pair, at process start (or explicitly, in a test harness, per test). There is no reload, no hot-swap,
and no background refresh — a genuine reconfiguration means running the sequence again from step
[1], producing an entirely new object graph, never mutating an existing one (Read-Only Guarantees).

## Configuration Sources

A closed, ordered list — precedence high to low:

1. **Explicit programmatic mapping**, passed directly to `load_raw_settings(env=...)` — highest
   precedence, used exclusively by test harnesses to avoid any dependence on real process state
   (Determinism).
2. **Process environment variables** (`os.environ`) — the canonical production source. A deployment
   secret store is expected to have already injected its values here before this layer runs; Phase
   1.1 defines no client for any specific secret-management product.
3. **An optional `.env` file** — loaded at the start of `load_raw_settings()`, before the process
   environment is consulted, and folded into the identical key/value space. When the same key appears
   in both a `.env` entry and the process environment, the process environment value takes precedence;
   `.env` entries are the lower-precedence fallback that the process environment overrides. A `.env`
   entry behaves exactly like an exported environment variable for every key where the process
   environment has no matching entry, never a second, separately-precedented source (Design Decisions
   #6). Absence of the file is not an error.
4. **Phase 1.1's own named operational defaults** (Constants) — consulted only for `RuntimeConfig`
   tier fields that this layer itself owns; never used for a secret, and never used to default a
   `ProviderSettings.provider_name` (an unconfigured seam is `SEAM_NOT_CONFIGURED`, never silently
   defaulted to some provider — Configuration Validation).

No other source exists in this phase. A remote configuration service, a database-backed settings
table, or any file format other than `.env`/process env is explicitly a future phase boundary
(Future Phase Boundaries) — introducing one is a new design pass against this document, never a
silent extension of `load_raw_settings()`.

## Configuration Schemas

All in-memory Python structures — none persisted, no file format to version, matching every
query-time stage's own "no artifact" posture.

**`RawSettings`** (output of `load_raw_settings`, before validation)
```jsonc
{
  "values": { "GEMINI_API_KEY": "...", "LLM_PROVIDER": "gemini", ... },  // flat string->string map,
                                                                          // exactly as read from env/.env
  "dotenv_path_loaded": ".env"                                          // or null if none was found
}
```

**`ProviderSettings`**
```jsonc
{
  "seam": "LLM_PROVIDER",                 // one of the closed SUPPORTED_SEAMS (Constants)
  "provider_name": "gemini",              // opaque to this layer; meaningful only to the registry
  "credential_ref": "env:GEMINI_API_KEY", // opaque reference to WHERE the secret came from —
                                           // never the secret value itself (Security Considerations)
  "extra": { "model_name": "gemini-2.5-flash" }   // provider-specific, uninterpreted passthrough
}
```

**`RuntimeConfig`**
```jsonc
{
  "dotenv_path_loaded": ".env",           // or null
  "network_calls_permitted": true,        // false in a fully offline/CI context — see Failure Handling
  "configuration_layer_version": "1.0.0"
}
```

**`ApplicationSettings`**
```jsonc
{
  "settings_fingerprint": "cfg_...",      // deterministic identity — see Configuration Schemas,
                                           // Configuration Identity
  "runtime": { /* RuntimeConfig */ },
  "providers": {                          // one entry per CONFIGURED seam only; an absent key means
                                           // "not configured", never "configured with a default"
    "LLM_PROVIDER": { /* ProviderSettings */ },
    "EMBEDDING_PROVIDER": { /* ProviderSettings */ }
  }
}
```

**`ProviderRegistration`** (the input list to `build_provider_registry`)
```jsonc
{
  "seam": "LLM_PROVIDER",
  "provider_name": "gemini",
  "network_dependent": true,            // true if the factory opens a network socket during
                                        // construction; false for in-memory or purely local adapters.
                                        // wire_dependencies() refuses to invoke a network_dependent
                                        // factory when runtime.network_calls_permitted is False
                                        // (NETWORK_CALLS_DISABLED — see Configuration Validation §2).
  "factory": "<Callable[[ProviderSettings, Optional[str]], Any]>"
                                        // second argument is the resolved raw credential value, or
                                        // None if ProviderSettings carries no credential_ref.
                                        // The factory is the sole remaining holder of the raw
                                        // credential after wire_dependencies() returns (Security
                                        // Considerations).
}
```

**`WiringResult`**
```jsonc
{
  "settings_fingerprint": "cfg_...",      // copied verbatim from the ApplicationSettings that produced it
  "wired": {                              // one entry per seam that was both configured AND registered
    "LLM_PROVIDER": "<constructed LLMAdapter instance>",
    "EMBEDDING_PROVIDER": "<constructed ProviderAdapter instance>"
  }
}
```

### Configuration Identity

```
settings_fingerprint = "cfg_" + sha256(canonical_json(redacted_view(settings))).hexdigest()[:16]
```

Computed over the **redacted** view only (Security Considerations) — every field on
`REDACTED_FIELD_NAMES` (Constants) is stripped before hashing, so `settings_fingerprint` identifies
the *shape* of a configuration and never functions as a proof of possession of, or a lookup key
derived from, any secret value. Under the current architecture, `REDACTED_FIELD_NAMES` is empty
because no field on `ApplicationSettings` or `ProviderSettings` carries a raw secret value — raw
credentials exist only as transient local variables inside `wire_dependencies()` (Security
Considerations). `credential_ref` is **not** redacted: it holds only an opaque reference string (e.g.
`"env:GEMINI_API_KEY"`), contains no secret value, and is part of "the shape of a configuration"
this id exists to capture — two configurations referencing different environment variable names for
the same seam are distinguishable by their `settings_fingerprint`. Two deployments with identical
`credential_ref` values but different API keys stored under those names share an identical
`settings_fingerprint` — a deliberate property: this id answers "was the same configuration shape
active," never "was the same secret value active." This mirrors every frozen stage's own `*_id`
convention — a deterministic content-hash over exactly the fields that determine identity — while
excluding actual secret values from that hash input, for the reason stated in full under Design
Decisions #8.

### Configuration Immutability

`ApplicationSettings`, `ProviderSettings`, `RuntimeConfig`, `ProviderRegistry`, and `WiringResult` are
each immutable from the moment their constructing function returns. None of Phase 1.1's own functions
ever mutates a field on an object it did not itself just construct. A reconfiguration is always a
fresh call sequence (Configuration Lifecycle), never an in-place field update — the same documented
(not language-enforced) immutability contract every frozen stage's own returned package already
carries (e.g., Stage 21's `AgentResult`: "once assembled and validated... never modified").

## Dependency Wiring Model

`wire_dependencies()` produces one constructed adapter instance per seam — it does **not** assemble
those instances into a specific frozen stage's own `PipelineDependencies` or `AgentDependencies`
dataclass. That final assembly is a thin, mechanical mapping performed by the application's own
composition root — a future layer, not designed here — guided by this table:

| `WiringResult.wired` key | Feeds into | Frozen stage's own field |
|---|---|---|
| `EMBEDDING_PROVIDER` | Stage 8 / Stage 10 | the `ProviderAdapter` a `retrieve`/`embed_query` closure is built over |
| `INDEX_BACKEND` | Stage 9 / Stage 10 | the `IndexAdapter` a `retrieve` closure is built over |
| `LLM_PROVIDER` | Stage 13 (via Stage 17/18) | `PipelineDependencies.llm_adapter` |
| `CACHE_BACKEND` | Stage 17 (via Stage 18) | `PipelineDependencies.cache_adapter` |
| `CONVERSATION_STORE` | Stage 19 (via Stage 21) | the store backing `AgentDependencies.select_memory` / `.append_turn` / `.get_conversation` |
| `TOOL_REGISTRY` | Stage 20 (via Stage 21) | `AgentDependencies.tool_registry` |
| `TOOL_ADAPTER` | Stage 20 (via Stage 21) | `AgentDependencies.tool_adapter` |
| `PLANNER_LLM_PROVIDER` | Stage 21 | `AgentDependencies.planner_llm_adapter` |

Two entries in this table (`EMBEDDING_PROVIDER`, `INDEX_BACKEND`) do not map onto a single
constructor argument — Stage 10's own `retrieve` entrypoint is, per its own frozen Configuration
section, a pre-configured callable, "an implementation detail entirely internal to Stage 10, opaque
to Stage 18." Producing that specific closed-over callable from these two wired adapters is
application-composition-root work, described here only as a mapping target, never implemented in
this document (Non-Responsibilities).

Every field named on a frozen stage's own `PipelineDependencies`/`AgentDependencies` schema that this
table does not list (`default_model_name`, `handle_request`, `select_memory`, `append_turn`,
`get_conversation`, `execute_tool`, `pipeline_deps`) is either a plain reference to another frozen
stage's own already-existing public entrypoint (never something this layer constructs) or a
deployment-level scalar (`default_model_name`) that the application composition root supplies
directly from `ApplicationSettings.runtime` or an equivalent field — never a seam this layer wires.

## Provider Registration Model

A closed set of eight seams — the only seams Phase 1.1 recognizes, matching exactly the eight
abstract backend contracts the frozen stages already define:

```python
SUPPORTED_SEAMS = (
    "EMBEDDING_PROVIDER",    # Stage 8's ProviderAdapter
    "INDEX_BACKEND",         # Stage 9's IndexAdapter
    "LLM_PROVIDER",          # Stage 13's LLMAdapter
    "CACHE_BACKEND",         # Stage 17's CacheAdapter
    "CONVERSATION_STORE",    # Stage 19's ConversationStore
    "TOOL_REGISTRY",         # Stage 20's ToolRegistry
    "TOOL_ADAPTER",          # Stage 20's ToolAdapter
    "PLANNER_LLM_PROVIDER",  # Stage 21's PlannerLLMAdapter
)
```

`build_provider_registry(registrations: Sequence[ProviderRegistration]) -> ProviderRegistry` is a
**pure function**, not an incremental, ambient-mutation API. There is no `register_provider()`
function that mutates a module-level dict as a side effect of being imported — that shape is exactly
the global-mutable-state pattern this document is required to avoid (Design Decisions #1). Instead, a
future phase that implements a concrete adapter (e.g., a Gemini `LLMAdapter`) supplies its own
`ProviderRegistration` entry explicitly, and the application's composition root collects every such
entry from every provider module it has chosen to depend on, into one list, passed once to
`build_provider_registry()`.

- Two registrations sharing an identical `(seam, provider_name)` pair within one call raises
  `PROVIDER_ALREADY_REGISTERED` (Configuration Validation) — the registry itself has no notion of
  "last write wins."
- `wire_dependencies()` looks up `(seam, settings.providers[seam].provider_name)` in the registry; no
  match raises `PROVIDER_NOT_REGISTERED` — a named, explicit configuration error at wiring time,
  never a silent no-op, never a fallback to some other provider, and never a failure surfacing deep
  inside a frozen stage that has no idea configuration was ever involved.

**Illustrative note, not a registration performed by this document:** Stage 9 already ships a
concrete `FAISSAdapter`. A future application composition root is free to supply a
`ProviderRegistration` entry for `("INDEX_BACKEND", "faiss", <a factory constructing FAISSAdapter>)`
today, without waiting on any new provider-implementation phase, because the concrete implementation
already exists in this repository. This is stated only to illustrate that the registration mechanism
is provider-agnostic and already usable for the one seam with an existing concrete implementation; no
other seam has one yet (Known Limitations).

## Configuration Validation

Three distinct, clearly-scoped groups of named codes — a deliberate adaptation of the three-tier model
every frozen stage already uses, not a literal copy: Phase 1.1 has no per-request "package" the way a
query-time stage does (`ApplicationSettings` is a process-lifetime singleton object graph, not a
per-call artifact), so the middle tier below is scoped to *wiring*, not to a findings-bearing return
package (Design Decisions #4).

**1. Input validation codes** — raised by `validate_settings()`, never returned:

| Code | Raised as | Trigger |
|---|---|---|
| `REQUIRED_FIELD_MISSING` | `ConfigurationInputError` | a configured seam entry is present with no `provider_name` |
| `FIELD_TYPE_INVALID` | `ConfigurationInputError` | a recognized field is present with the wrong type (e.g. `network_calls_permitted` not a bool) |
| `UNKNOWN_SEAM` | `ConfigurationInputError` | a configured seam name is not one of `SUPPORTED_SEAMS` |
| `CREDENTIAL_REF_MALFORMED` | `ConfigurationInputError` | `credential_ref` does not match the closed `env:<VAR_NAME>` reference shape (Security Considerations) |

**2. Wiring-level codes** — raised by `build_provider_registry()`, `wire_dependencies()`, or
`resolve_provider_settings()`, never returned:

| Code | Raised as | Trigger |
|---|---|---|
| `PROVIDER_ALREADY_REGISTERED` | `ConfigurationWiringError` | two registrations share an identical `(seam, provider_name)` pair |
| `PROVIDER_NOT_REGISTERED` | `ConfigurationWiringError` | a configured seam's `provider_name` has no matching registry entry |
| `SEAM_NOT_CONFIGURED` | `ConfigurationWiringError` | a caller calls `resolve_provider_settings()` for a seam absent from `settings.providers` |
| `NETWORK_CALLS_DISABLED` | `ConfigurationWiringError` | `runtime.network_calls_permitted == False` and the matched `ProviderRegistration.network_dependent` is `True` |

**3. Internal invariant codes** — raised by `validate_wiring_result()`, never returned:

| Code | Trigger |
|---|---|
| `WIRING_SETTINGS_FINGERPRINT_MISMATCH` | `result.settings_fingerprint != settings.settings_fingerprint`, recomputed fresh |
| `WIRING_SEAM_COUNT_MISMATCH` | the number of keys in `result.wired` does not equal the number of seams `wire_dependencies()` itself successfully resolved |
| `WIRING_UNKNOWN_SEAM_PRESENT` | `result.wired` contains a key outside `SUPPORTED_SEAMS` |

Any of the tier-3 codes raises `ConfigurationInternalError` — the same fail-loud posture every frozen
stage's own internal-invariant exception already establishes, and never expected to fire under
correct operation.

`validate_wiring_result()` does not verify that each constructed adapter instance is a subclass of
its seam's declared abstract base class (e.g. that the `LLM_PROVIDER` factory returned an `LLMAdapter`
subclass). Type conformance is the concrete adapter factory's own responsibility: a factory that
correctly subclasses the seam's ABC causes Python's own ABC machinery to enforce abstract method
presence at instantiation time, before `wire_dependencies()` receives the return value. If a factory
returns an object that does not subclass the expected ABC, the failure surfaces inside the stage that
first attempts to invoke the seam's abstract method. An application composition root that wishes to
enforce type conformance beyond what the ABC machinery provides may do so by checking each
`WiringResult.wired` value against its expected abstract base class before assembling
`PipelineDependencies`/`AgentDependencies`; that check is a composition-root responsibility, not a
Phase 1.1 invariant.

There is no fourth, "package-level findings" tier here — Phase 1.1 has no notion of a WARNING that
allows an otherwise-degraded configuration object to be returned. Every violation at every tier is a
hard stop (Failure Handling); this is the one place this document's validation model departs in
substance, not merely in vocabulary, from a query-time stage's own three-tier convention, and the
departure is named and justified in full under Design Decisions #4.

## Public Function Contracts

- `load_raw_settings(env: Optional[Mapping[str, str]] = None, dotenv_path: Optional[str] = None) ->
  RawSettings` — reads the supplied mapping (or `os.environ` if omitted) and an optional `.env` file;
  pure given identical inputs; performs no validation of any kind.

- `validate_settings(raw: RawSettings) -> ApplicationSettings` — structural and range validation
  (Configuration Validation §1); computes `settings_fingerprint`; raises `ConfigurationInputError` on
  violation; returns an immutable `ApplicationSettings`.

- `build_provider_registry(registrations: Sequence[ProviderRegistration]) -> ProviderRegistry` — pure
  function over its one argument; raises `ConfigurationWiringError` (`PROVIDER_ALREADY_REGISTERED`) on
  a duplicate `(seam, provider_name)` pair; returns an immutable `ProviderRegistry`.

- `resolve_provider_settings(settings: ApplicationSettings, seam: str) -> ProviderSettings` — pure
  lookup; raises `ConfigurationWiringError` (`SEAM_NOT_CONFIGURED`) if `seam` has no entry in
  `settings.providers`.

- `wire_dependencies(settings: ApplicationSettings, registry: ProviderRegistry) -> WiringResult` —
  for each seam present in `settings.providers`: if `ProviderSettings.credential_ref` is present,
  reads the named environment variable from `os.environ` exactly once, producing a transient raw
  credential string held only in local scope for the duration of the factory call; checks the matched
  `ProviderRegistration.network_dependent` against `runtime.network_calls_permitted`; looks up the
  seam's `provider_name` in `registry`; and invokes the matching factory exactly once with
  `(ProviderSettings, Optional[str])` — the second argument is the resolved raw credential, or
  `None` if `credential_ref` is absent. After the factory call returns, the transient raw credential
  is discarded; the constructed adapter instance is the sole remaining holder of any credential it
  consumed. Collects all results into a `WiringResult`; raises `ConfigurationWiringError`
  (`PROVIDER_NOT_REGISTERED` or `NETWORK_CALLS_DISABLED`) on any unresolved or disallowed seam.
  Either every configured seam resolves, or the call raises — there is no partial `WiringResult`.
  This is the only function other than `load_raw_settings()` that reads `os.environ`; no other
  function in this contract reads the process environment.

- `validate_wiring_result(result: WiringResult, settings: ApplicationSettings) -> None` — internal
  invariant self-check (Configuration Validation §3); raises `ConfigurationInternalError` on
  violation. Does not verify that constructed adapter instances conform to their seam's expected
  abstract base class — that responsibility is stated in full under Configuration Validation §3.

- `redacted_view(settings: ApplicationSettings) -> Dict[str, Any]` — returns a plain dict
  representation of `settings` with every field named in `REDACTED_FIELD_NAMES` (Constants) replaced
  by a fixed sentinel (`"<redacted>"`); the only sanctioned way to log, print, or serialize anything
  derived from `ApplicationSettings` (Security Considerations).

No function in this contract list ever imports a provider SDK, opens a network socket, or reads any
file other than the one optional `.env` path passed to `load_raw_settings()`.

## Determinism

**Deterministic (guaranteed, byte-identical across runs, given identical input):**

- `load_raw_settings()` — given an identical `env` mapping (or an identical real process environment)
  and an identical `.env` file's contents, produces a byte-identical `RawSettings` every time.
- `validate_settings()` — given identical `RawSettings`, produces a byte-identical
  `ApplicationSettings`, including `settings_fingerprint`, every time.
- `build_provider_registry()` — given an identical `registrations` sequence, produces an identical
  `ProviderRegistry` every time (or an identical `ConfigurationWiringError` on a duplicate).
- `resolve_provider_settings()` — a pure, total lookup.
- `settings_fingerprint` — a pure content-hash over the redacted view alone (Configuration Identity).
- **Which** seams wire successfully and which raise `PROVIDER_NOT_REGISTERED` or
  `NETWORK_CALLS_DISABLED` is a pure function of `(settings, registry)` alone —
  `network_calls_permitted` is in `settings.runtime`, and `network_dependent` is in the
  `ProviderRegistration` carried by `registry`.

**Explicitly NOT deterministic (inherent to the sources this layer reads; never assumed, never
hidden):**

- **The actual values read from `os.environ`/`.env` at load time.** These reflect whatever the
  deployment environment happens to contain at the moment `load_raw_settings()` runs — Phase 1.1
  makes no claim that two different processes, or two different deployments, load identical values.
  Determinism here means "given the identical environment, the identical result" — never "the
  environment itself is predictable."
- **The raw credential values resolved by `wire_dependencies()` from `os.environ` at wiring time.**
  Phase 1.1 makes no claim that a credential resolved during `wire_dependencies()` equals the value
  that `load_raw_settings()` read for the same variable if the process environment has changed in
  between. This non-determinism is inherent to the environment source — the same qualifier already
  stated for `load_raw_settings()` above applies here.

- **Whatever a registered factory itself does when invoked.** Constructing a concrete adapter
  instance is entirely that factory's own concern (a future, separate design); Phase 1.1's own
  `wire_dependencies()` calls it exactly once and treats its return value opaquely — any
  non-determinism in a concrete adapter's own construction (e.g. an SDK client that pings a health
  endpoint at construction time) is inherited, never introduced, by this layer.

## Read-Only Guarantees

- Phase 1.1 never modifies `manifest.json`, any corpus artifact, any vector index, any embedding, any
  prompt template, or any cache store entry — it has no relationship to any of them at all.
- Phase 1.1 never modifies a `RawSettings`, `ApplicationSettings`, `ProviderSettings`,
  `ProviderRegistry`, or `WiringResult` object after the function that constructed it returns.
- Phase 1.1 never writes to `.env` or to the process environment — it only ever reads from both.
- **Phase 1.1 holds no module-level mutable state of any kind.** There is no stored "current
  settings" singleton and no ambiently-mutated provider registry (Design Decisions #1). Every object
  this layer produces is returned to its caller, which is solely responsible for holding onto it and
  threading it explicitly into whatever needs it next — exactly the discipline Stage 21 already
  states for its own `PlannerContext` ("Stage 21 holds no module-level mutable state; all state is in
  the `PlannerContext` being assembled"), applied here to configuration itself.
- The external side effects this layer performs are exactly: one read of an optional `.env` file
  (in `load_raw_settings()`), reads of the process environment at load time (`load_raw_settings()`)
  and per-seam at wiring time (`wire_dependencies()` — Security Considerations). No network call, no
  disk write, no subprocess.

## Failure Handling

- **A malformed configuration value** (wrong type, unknown seam, malformed `credential_ref`) —
  `ConfigurationInputError` raised immediately from `validate_settings()`, with the matching code; no
  `ApplicationSettings` is produced; no wiring is ever attempted.
- **A duplicate `(seam, provider_name)` registration** — `ConfigurationWiringError`
  (`PROVIDER_ALREADY_REGISTERED`) raised immediately from `build_provider_registry()`; no registry is
  produced.
- **A configured seam with no matching registered factory** — `ConfigurationWiringError`
  (`PROVIDER_NOT_REGISTERED`) raised from `wire_dependencies()`; wiring halts for the whole call —
  there is no partial `WiringResult` returned with some seams missing; either every configured seam
  resolves, or the call raises.
- **A configured seam whose matched `ProviderRegistration.network_dependent` is `True` and
  `runtime.network_calls_permitted` is `False`** — `ConfigurationWiringError`
  (`NETWORK_CALLS_DISABLED`) raised from `wire_dependencies()` before the factory is invoked; this
  exists specifically so a fully offline test/CI run fails fast and explicitly, rather than a factory
  silently attempting (and hanging on, or failing deep inside) a real network call it was never
  supposed to make.
- **A genuine Phase 1.1 bug** (one of the three named internal invariant codes, Configuration
  Validation §3) — `ConfigurationInternalError` raised, never returned as a superficially-valid but
  internally-inconsistent `WiringResult`.
- **No retry, no fallback provider, no degraded configuration mode.** A wiring failure is always a
  hard stop with a named, actionable error — never a silent substitution of some other provider or a
  partially-wired application state.

## Design Decisions

1. **No global mutable state, anywhere in this layer, under any circumstance.** Every object this
   layer produces (`RawSettings`, `ApplicationSettings`, `ProviderRegistry`, `WiringResult`) is
   returned to its caller and threaded explicitly from there — there is no module-level "current
   settings" variable and no ambient `register_provider()` mutation function. This is the one
   Absolute Rule most naturally tempting to violate in a configuration layer (a global settings
   object is the most common shape this kind of code takes), which is exactly why it is named here as
   a first-class, deliberate decision rather than left to be discovered as an omission.

2. **Request/session-level overrides are never touched by this layer.** Stage 10 through Stage 21
   each already define their own `pipeline_options`/`planning_config`/`execution_config` fields, with
   their own defaults and clamps, forwarded verbatim by every orchestrating stage above them (Stage
   18's own Design Decision: "Stage 18 never re-implements or duplicates any clamp, default, or
   ceiling any frozen stage already enforces"). Phase 1.1 extends this discipline one layer further
   out: it configures *which provider* answers a call, never *how* that call is tuned per request.

3. **Configuration Lifecycle is a linear function pipeline, not a stored state machine.** Stage 21's
   own `PlannerState` state machine exists because planning genuinely branches on a non-deterministic,
   external decision (the `PlannerLLMAdapter`'s own output) across a bounded loop. Nothing in
   configuration loading, validation, or wiring branches on an external decision at all — every step
   either succeeds deterministically or raises. Modeling this as a stored FSM would manufacture
   complexity this layer does not have; a five-step, always-forward pipeline (Configuration
   Lifecycle) is the honest shape.

4. **Configuration Validation's middle tier is scoped to wiring, not to a findings-bearing return
   package, and there is no fourth "package findings" tier at all.** Stage 10 through Stage 21 each
   use a `{severity, code, message}` findings list on a per-request, per-call return package, because
   a package-level WARNING can coexist with an otherwise-successful result. `ApplicationSettings`/
   `WiringResult` have no equivalent notion of a "partially successful configuration" — either every
   configured seam wires, or the call raises. The three-tier *shape* (input / intermediate /
   internal-invariant) is preserved for consistency with every frozen stage's own Validation section;
   its *content* is adapted, and the missing WARNING tier is named explicitly rather than left as an
   unstated gap, because this layer's own object lifecycle is genuinely different from a per-request
   package's: a caller cannot safely proceed on a "warned but wired" configuration the way a caller
   can proceed on a "warned but answered" `APIResponse`.

5. **A deployment secret store is never given its own client or contract.** Introducing a
   `SecretStoreAdapter` alongside `ProviderAdapter`/`LLMAdapter`/etc. would be a ninth backend
   contract for a concern that, in practice, every real secret-management product (cloud secret
   managers, container-orchestrator secret mounts, CI-injected variables) already solves by exposing
   itself as a process environment variable at the point this application actually runs. Reading
   `os.environ` is therefore sufficient and correct; a future phase needing a genuinely different
   secret-retrieval mechanism (e.g., a live per-call secret-rotation client) is an explicit, separate
   design pass against this document, never assumed here (Future Phase Boundaries).

6. **A `.env` file is folded into the same key/value space as the process environment, never a
   second source with its own precedence rules beyond "checked before the process environment."**
   This mirrors the universal convention already familiar from every other tool that supports
   `.env` files, and avoids inventing a bespoke merge algorithm this layer would then need to
   document and test on its own terms.

7. **The Provider Registration Model is a pure builder function, never an import-time side effect.**
   A tempting alternative — a decorator (`@register_provider("gemini")`) that mutates a module-level
   dict as a side effect of importing a provider module — was rejected because it reintroduces
   exactly the global-mutable-state and hidden-side-effect patterns Design Decision #1 forbids, and
   makes registration order (and therefore behavior) depend on unpredictable Python import ordering.
   `build_provider_registry(registrations)` requires every registration to be explicit, visible, and
   assembled once, by one caller, in one place — the application's own composition root.

8. **`settings_fingerprint` excludes every secret field from its hash input, by construction, not by
   convention.** Every frozen stage's own `*_id` convention hashes exactly the fields that fully
   determine identity. Including a secret in that hash would not aid identity — two configurations
   with the same provider selection but different API keys are still "the same configuration shape"
   for every purpose this id serves (audit, log correlation) — and would create an unnecessary,
   avoidable path by which a hash function's output could be scrutinized for information about a
   secret's value. Excluding secrets from the hash input entirely, rather than merely trusting
   `sha256` to be one-way, is the more conservative and more correct choice.

9. **`wire_dependencies()` is all-or-nothing per call, never partially successful.** A caller that
   configured five seams and registered factories for only four cannot receive a `WiringResult`
   covering the four that resolved — the whole call raises `PROVIDER_NOT_REGISTERED` naming the one
   that did not. This mirrors every frozen stage's own "no hidden recovery behavior; no degraded
   mode" posture (Stage 21's own Failure Handling: "No fallback mode, no degraded planning, no silent
   substitution"), applied here to wiring rather than planning.

10. **`ProviderRegistration.network_dependent` is a caller-supplied declaration, never a runtime
    probe.** Phase 1.1 does not attempt to detect whether a factory will open a network socket by
    inspecting or executing it ahead of time — doing so would require invoking the factory before the
    official wiring step, introducing hidden side effects and duplicated object construction. Instead,
    `network_dependent: bool` is a field on `ProviderRegistration` that the future phase supplying
    the factory sets at registration time. This places responsibility where knowledge actually lives:
    the author of a concrete adapter knows whether its construction requires network access; Phase 1.1
    knows only that a deployment has declared itself offline. Mismatching these two declarations (a
    factory that opens a network socket but declares `network_dependent = False`) is an error at the
    future phase's own responsibility level, not a Phase 1.1 invariant to enforce at runtime.

## Constants

```python
CONFIGURATION_LAYER_VERSION = "1.0.0"

DEFAULT_DOTENV_FILENAME = ".env"

SUPPORTED_SEAMS = (
    "EMBEDDING_PROVIDER", "INDEX_BACKEND", "LLM_PROVIDER", "CACHE_BACKEND",
    "CONVERSATION_STORE", "TOOL_REGISTRY", "TOOL_ADAPTER", "PLANNER_LLM_PROVIDER",
)

# Field names stripped by redacted_view() before any object derived from ApplicationSettings
# may be logged, printed, or serialized. Closed list — extending it requires a new design pass,
# never an ad hoc addition at a call site.
#
# Under the current architecture this tuple is empty: no field on ApplicationSettings or
# ProviderSettings carries a raw secret value. credential_ref is a reference string (e.g.
# "env:GEMINI_API_KEY"), not a value, and belongs in the fingerprint. Raw credentials exist
# only as transient locals inside wire_dependencies() and never appear as named object fields
# (Security Considerations). Any future schema revision that introduces a field carrying a raw
# secret must add that field name here before the revision is merged.
REDACTED_FIELD_NAMES = ()
```

No numeric threshold, ceiling, or default belonging to any frozen stage (`MAX_RETRY_ATTEMPTS_CEILING`,
`DEFAULT_TIMEOUT_SECONDS`, `MAX_PLAN_STEPS`, or any other) is duplicated here — every one of them
already lives, exactly once, in the stage that owns it.

## Complexity

- `load_raw_settings()` — O(E), where E is the number of environment variables scanned plus the
  `.env` file's own line count.
- `validate_settings()` — O(F), where F is the number of fields present across all configured
  `ProviderSettings` entries — a structural/type/range check per field, no nested search.
- `build_provider_registry()` — O(R), where R is the number of supplied registrations (a duplicate
  check per entry against previously seen `(seam, provider_name)` pairs).
- `resolve_provider_settings()` — O(1), a direct dict lookup.
- `wire_dependencies()` — O(S), where S is the number of configured seams — bounded above by 8
  (`len(SUPPORTED_SEAMS)`), so this is effectively O(1) in practice; the actual cost of any one
  factory invocation is entirely that factory's own concern, invisible to this layer's own
  complexity accounting.
- `validate_wiring_result()` — O(S), the same small, fixed bound.

## Logging Vocabulary

Per the shared Logging Specification (`stage: "phase1_1_configuration"`, `doc_id: null` always —
entries are process-scoped, not document-scoped). New codes this layer adds:

- `INFO_CONFIGURATION_LOADED` — `load_raw_settings()` completed.
- `INFO_CONFIGURATION_VALIDATED` — `validate_settings()` completed; logged alongside
  `settings_fingerprint`, never alongside any raw field value.
- `INFO_PROVIDER_REGISTRY_BUILT` — `build_provider_registry()` completed; logged with the count and
  the list of `(seam, provider_name)` pairs only — never a factory's own internals.
- `INFO_DEPENDENCIES_WIRED` — `wire_dependencies()` completed; logged with the list of seams wired,
  never the constructed instances themselves.
- `WARNING_DOTENV_FILE_NOT_FOUND` — the configured `dotenv_path` did not exist; not an error, since
  `.env` is always optional.
- `FATAL_CONFIGURATION_MALFORMED` — one of Configuration Validation §1's codes fired.
- `FATAL_PROVIDER_NOT_REGISTERED` — Configuration Validation §2's `PROVIDER_NOT_REGISTERED` fired.
- `FATAL_SEAM_NOT_CONFIGURED` — Configuration Validation §2's `SEAM_NOT_CONFIGURED` fired.

**Hard constraint, stated once and binding on every one of the codes above:** no log entry emitted by
this layer, at any severity, may include a value from `REDACTED_FIELD_NAMES`, a raw environment
variable value, or a raw `.env` line. Any function in this layer that logs anything derived from
`ApplicationSettings`/`ProviderSettings` must construct that log entry from `redacted_view()`'s
output, never from the object itself. This is an architectural constraint on this layer's own
implementation, not a coding-style suggestion — restated in full under Security Considerations.

None of the `FATAL_*` codes above sets a manifest `error_code` — this layer never touches the
manifest at all (Read-Only Guarantees).

## Concurrency

Configuration loading, validation, and wiring happen once per process lifetime (or once per
explicit, isolated call in a test), producing immutable objects (Configuration Immutability). There
is no mutation after construction, and therefore nothing for this layer to lock. Concurrent reads of
an already-constructed `ApplicationSettings`/`ProviderRegistry`/`WiringResult` by multiple threads are
inherently safe, by construction, not by any synchronization primitive this layer defines.

Phase 1.1 defines no locking, no mutex, and no coordination of its own — the same "safe because there
is nothing shared to protect" posture Stage 20/21 already state for their own stateless
orchestration functions. A future application layer that decides to reconfigure a running process
(Known Limitations — no hot-reload is designed here) would need to define its own coordination for
swapping one immutable object graph for another; that coordination is explicitly outside this
document's scope.

## Security Considerations

- **API key / secret ownership — complete credential lifecycle.** A raw credential value flows through
  this layer in three distinct steps, each with a bounded and documented lifetime:

  1. **`load_raw_settings()` reads the process environment** into `RawSettings.values` — a flat
     `string → string` map that includes all environment variables, including those that carry
     secrets. `RawSettings` is returned to the caller and is the caller's own responsibility to
     discard promptly after passing it to `validate_settings()`. Phase 1.1's own functions hold no
     reference to `RawSettings` after `validate_settings()` returns.

  2. **`validate_settings()` produces `ApplicationSettings`**, in which each seam's
     `ProviderSettings.credential_ref` carries an opaque reference string (e.g.
     `"env:GEMINI_API_KEY"`) — never the raw secret value. No object returned by `validate_settings()`
     or any later function in this layer carries a raw secret in any field.

  3. **`wire_dependencies()` resolves `credential_ref`** by reading the named environment variable
     from `os.environ` exactly once per seam, immediately before invoking that seam's factory. The
     resolved raw value exists only as a transient local variable in `wire_dependencies()`'s own
     scope for the duration of the factory call. When the factory call returns, that local variable
     goes out of scope; the constructed adapter instance is the sole remaining holder of the
     credential. Phase 1.1 retains no copy.

  `wire_dependencies()` is the only function other than `load_raw_settings()` in this layer that
  reads `os.environ`; this is the only mechanism by which a raw credential reaches a factory
  (Public Function Contracts). This is the same ownership model every frozen stage's own Security
  Considerations already state for their own credentials (Stage 13: "API keys or other provider
  credentials are `LLMAdapter`-level configuration, supplied by the caller to the adapter, never
  passed through, logged, or included in `LLMResponse`"); Phase 1.1 is the mechanism that gets the
  credential from its source to that adapter constructor.

- **Environment isolation.** Only this layer ever reads `os.environ` or opens a `.env` file, and
  within this layer exactly two functions do so: `load_raw_settings()` (the primary read, at load
  time) and `wire_dependencies()` (the per-seam credential resolution read, at wiring time — see API
  key / secret ownership above). No other function in this layer reads the process environment. No
  frozen stage (Stage 8 through Stage 21) imports `os`, calls `os.environ`, or opens any `.env` file
  under any circumstance — every one of them receives its adapter, already constructed, purely
  through dependency injection. This boundary is absolute: introducing an environment read inside any
  stage's own module would be a violation of that stage's own frozen Configuration section, never a
  Phase 1.1 concern to police at runtime, but a contract every stage's own doc already commits to.

- **No secret logging, under any circumstance.** Every log entry this layer emits (Logging
  Vocabulary) is required to be constructed from `redacted_view()`'s output. This is stated as a hard
  constraint on this layer's own future implementation, not a best-effort convention.

- **No secret serialization.** `ApplicationSettings`/`ProviderSettings` are never converted to JSON,
  a dict, or any other serializable form for logging, caching, or transport, except through
  `redacted_view()`, which strips every field in `REDACTED_FIELD_NAMES` first. There is no
  "debug dump" function in this contract that bypasses this.

- **No secret persistence.** Nothing in this layer writes a secret value to disk, to a cache store,
  to the manifest, or to any artifact of any kind. The only file this layer ever opens is an
  optional, caller-supplied `.env` path — for reading, never for writing.

- **No secret hashing.** `settings_fingerprint` (Configuration Identity) is computed exclusively over
  the redacted view — a secret value is never, under any circumstance, fed as input to any hash this
  layer computes, closing off even an indirect information-leakage path through a content-identity
  hash.

- **No secret exposure through any returned package.** `WiringResult`, `ApplicationSettings`, and
  every object this layer returns are constructed, by design (never merely by convention), to never
  carry a raw secret in any field a caller could read directly — the only field that ever touches a
  secret's origin is `credential_ref`, and it is defined, by contract, to hold a reference string,
  never a value.

## Known Limitations

- **No hot-reload.** A running process's configuration is fixed for its lifetime once wired; picking
  up a changed environment variable or `.env` file requires restarting the process (or, in a test
  harness, running the load→validate→wire sequence again explicitly). Introducing live reload is a
  future, separate design pass.
- **Single-process configuration only.** This layer has no notion of a distributed configuration
  service, no cross-process cache invalidation, and no cluster-wide consistency guarantee — each
  process independently loads and wires its own configuration from its own environment.
- **No per-tenant or per-caller provider selection.** `ApplicationSettings` names exactly one
  provider per seam for the whole process — mirroring Stage 18's own accepted, named limitation
  ("`default_model_name` is a single, global fallback — not per-caller or per-tenant configurable").
  A deployment needing different providers for different callers must resolve that above this layer.
- **The provider registry ships with zero concrete registrations from this document.** Phase 1.1
  defines the mechanism only; every concrete factory (a real Gemini `LLMAdapter`, a real embedding
  `ProviderAdapter`, etc.) is supplied by a later, separate phase. The one seam with an existing
  concrete implementation in this repository today (`INDEX_BACKEND` → `FAISSAdapter`) is not
  registered by this document either — only noted as illustrative (Provider Registration Model).
- **No secret rotation support.** A credential read once at wiring time is used for the life of the
  constructed adapter instance; a provider requiring live credential rotation must implement that
  entirely inside its own adapter, invisible to this layer.
- **No configuration versioning beyond `CONFIGURATION_LAYER_VERSION`.** This layer names its own
  schema version as a single constant, the same convention every frozen stage's own `*_VERSION`
  constant already establishes; it defines no migration mechanism between versions, since no prior
  version has ever existed until this document itself.

## Future Phase Boundaries

There is **no Stage 22**. Phase 1.1 is a configuration and wiring layer sitting alongside the frozen
0–21 stage sequence, not a new stage within it, and nothing in this document changes that.

Everything Phase 1.1 deliberately excludes is reserved for a later, separate phase — each phase
supplies a `ProviderRegistration` (or several) that plug into the mechanism this document already
defines, without requiring this document, or any frozen stage, to change:

- **Phase 1.2 — Concrete LLM provider.** A real `LLMAdapter` implementation (e.g., wrapping Gemini),
  registered under seam `LLM_PROVIDER`. Owns model invocation, error mapping into Stage 13's own
  closed exception vocabulary, and response mapping into Stage 13's own `RawLLMResult` shape.
- **Phase 1.3 — Concrete embedding provider.** A real `ProviderAdapter` implementation, registered
  under seam `EMBEDDING_PROVIDER`.
- **Phase 1.4 — Concrete planner provider.** A real `PlannerLLMAdapter` implementation, registered
  under seam `PLANNER_LLM_PROVIDER`, which may share underlying client plumbing with Phase 1.2's own
  implementation without sharing its public contract.
- **Phase 1.5 — Supporting adapters, as needed.** Concrete `CacheAdapter`, `ConversationStore`, and
  `ToolRegistry`/`ToolAdapter` implementations, registered under their respective seams, only when a
  concrete use case requires more than an in-memory default.
- **A future application composition root** (not designed here) — the layer that actually calls
  `load_raw_settings → validate_settings → build_provider_registry → wire_dependencies`, holds the
  resulting `WiringResult`, and performs the final, mechanical assembly into `PipelineDependencies`
  and `AgentDependencies` per the Dependency Wiring Model's own mapping table.
- **Any secret-rotation, distributed-configuration, or hot-reload capability** — each is a new design
  pass against this document, never a silent extension of the load-once, wire-once lifecycle defined
  here.

Every stage from Stage 0 through Stage 21 remains exactly as independently usable, and exactly as
frozen, as it already is today. Phase 1.1 adds a way to *supply* what those stages already ask for —
it adds nothing they can call, and nothing they must change to receive.
