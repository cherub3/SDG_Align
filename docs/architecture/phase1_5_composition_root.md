# Phase 1.5 — Composition Root Architecture

Stages 0–21, Phase 1.1 (Configuration Layer), Phase 1.2 (LLM Provider Architecture), Phase 1.3
(Embedding Provider Architecture), and Phase 1.4 (Planner Provider Architecture) remain completely
frozen; nothing below proposes any change to existing code or shipped docs. Phase 1.5 defines the
architecture for the **composition root** — the final assembly layer that Phase 1.1's own Future Phase
Boundaries section already names and reserves: "the layer that actually calls
`load_raw_settings → validate_settings → build_provider_registry → wire_dependencies`, holds the
resulting `WiringResult`, and performs the final, mechanical assembly into `PipelineDependencies` and
`AgentDependencies` per the Dependency Wiring Model's own mapping table."

**Source-fidelity rule, stated once, governing this entire document, matching Phase 1.4's own
discipline:** every architectural statement below is derived directly from
`scripts/phase1_1_configuration_layer.py`, `docs/architecture/phase1_1_configuration_layer.md`,
`docs/architecture/phase1_2_llm_provider.md`, `docs/architecture/phase1_3_embedding_provider.md`,
`docs/architecture/phase1_4_planner_provider.md`, `scripts/embedding_provider_gemini.py`,
`scripts/llm_provider_gemini.py`, `scripts/planner_provider_gemini.py`,
`scripts/stage8_embedding_generation.py`, `scripts/stage13_llm_execution.py`, and
`scripts/stage21_agent_planning.py`. Where a prior phase leaves something undefined or deferred —
most notably, no script in this repository defines a `PipelineDependencies` dataclass, and no script
defines any composition-root entrypoint by any name — this document states that absence explicitly
rather than inventing a concrete type or a frozen function name the repository does not contain. No
new dependency-injection mechanism, provider contract, or stage orchestration is introduced; the
composition root only assembles what Phase 1.1 through Phase 1.4 already know how to produce and
receive.

**Provider-neutrality, stated once, governing this entire document, exactly as Phase 1.2/1.3/1.4
already establish for their own seams:** provider-specific terminology and module names may appear
only as illustrative examples of the current deployment. Normative behavior — registration assembly,
the composition lifecycle, dependency ownership — must never depend on any specific vendor's
semantics or on any specific, named provider module.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Every prior phase's own Future Phase Boundaries section reserves the same, single remaining gap.
Phase 1.1: "A future application composition root (not designed here) — the layer that actually calls
`load_raw_settings → validate_settings → build_provider_registry → wire_dependencies`, holds the
resulting `WiringResult`, and performs the final, mechanical assembly into `PipelineDependencies` and
`AgentDependencies`." Phase 1.2, Phase 1.3, and Phase 1.4 each repeat, for their own seam, that
"editing `ProviderRegistry` and performing dependency wiring of any kind" and "implementing the
application composition root itself" are deferred, composition-root-only work, never performed by any
of those documents or by any concrete provider implementation architected under them.

That gap is what Phase 1.5 closes, and only that gap. Three concrete provider implementations already
exist in the current deployment — an embedding provider, an LLM provider, and a planner provider, each
supplying its own `get_provider_registration() -> ProviderRegistration` function
(`scripts/embedding_provider_gemini.py`, `scripts/llm_provider_gemini.py`,
`scripts/planner_provider_gemini.py`) — and Phase 1.1's own four-function pipeline
(`load_raw_settings`, `validate_settings`, `build_provider_registry`, `wire_dependencies`) is fully
implemented in `scripts/phase1_1_configuration_layer.py`. Nothing in the repository yet calls that
pipeline, assembles a set of registrations to feed it, or maps its output onto the dependency objects
Stage 8, Stage 13, and Stage 21 actually consume. Phase 1.5 defines the architecture of that one
missing layer.

Phase 1.5 does not implement anything. It defines: (1) how the composition root assembles the set of
`ProviderRegistration` objects supplied by the current deployment before invoking
`build_provider_registry()`; (2) the exact sequence in which Phase 1.1's own four functions are
invoked; (3) how the resulting `WiringResult.wired` dict is mapped onto the dependency objects Stage 8,
Stage 13, and Stage 21 actually declare — which, per the repository as it exists today, means a bare
`ProviderAdapter`/`LLMAdapter` argument for Stage 8/Stage 13 and a concrete `AgentDependencies`
instance for Stage 21; (4) how retrieval closures are assembled from the wired embedding adapter,
exactly where Phase 1.1's own Dependency Wiring Model already reserves that step; and (5) the ownership
boundary that keeps every one of these responsibilities out of Phase 1.1 and out of every provider
implementation.

**A repository fact this document states precisely, because two prior-phase documents refer to a
target that does not yet exist as a concrete type:** Phase 1.1's own Dependency Wiring Model table
names `PipelineDependencies.llm_adapter` and `PipelineDependencies.cache_adapter` as mapping targets,
and Phase 1.2's own Future Phase Boundaries repeats "assembles `PipelineDependencies.llm_adapter`" as
composition-root work. Reading `scripts/stage8_embedding_generation.py` and
`scripts/stage13_llm_execution.py` in full confirms that **neither script defines a
`PipelineDependencies` dataclass.** Stage 8's own entrypoint is `run_stage8(provider: ProviderAdapter)
-> None`; Stage 13's own entrypoint is `execute_prompt(prompt_package, llm_adapter: LLMAdapter,
execution_config=None)`. Each takes a bare adapter as a direct positional argument. `AgentDependencies`
is the only dependency-container dataclass that actually exists in the repository today
(`scripts/stage21_agent_planning.py:49-60`). This document therefore states, once, the rule that
governs every later section referring to this pairing: **where a `PipelineDependencies` abstraction
exists in a deployment, the composition root maps wired adapters into it; in the current repository
only `AgentDependencies` is concretely defined, and Stage 8/Stage 13 are supplied their adapters as
direct call arguments instead.** This document neither invents a `PipelineDependencies` class nor
removes the mapping target Phase 1.1/1.2 already name — it states plainly which of the two is real
today.

## Scope

Phase 1.5 answers exactly one question — given the current deployment's set of `ProviderRegistration`
objects and Phase 1.1's own frozen four-function configuration pipeline, what is the architecture of
the one process-startup sequence that produces a fully wired set of dependency objects for Stage 8,
Stage 13, and Stage 21 — and stops there.

It never redesigns dependency injection — Phase 1.1's own `ApplicationSettings`/`ProviderSettings`/
`ProviderRegistration`/`wire_dependencies()` contracts are used exactly as already frozen. It never
redesigns any provider — the embedding, LLM, and planner adapters' own internal architecture (Phase
1.2, 1.3, 1.4) is used exactly as already frozen, and their own factory functions are invoked, never
reimplemented. It never redesigns any stage's own orchestration — Stage 8's batching/retry loop,
Stage 13's retry policy, and Stage 21's planning loop are each untouched; the composition root supplies
each stage's own already-declared entrypoint with the object that entrypoint already expects, and does
nothing else. It never selects which provider is active for a seam beyond what
`ApplicationSettings.providers` already encodes (Phase 1.1's own job). It never constructs a prompt,
executes an embedding call, invokes an LLM, or runs a planning loop.

## Responsibilities

Phase 1.5 shall: assemble the set of `ProviderRegistration` objects supplied by the current deployment
— today, the three registrations returned by the embedding, LLM, and planner provider modules' own
`get_provider_registration()` functions — into the one list `build_provider_registry()` expects
(Provider Registration); invoke `load_raw_settings()`, `validate_settings()`,
`build_provider_registry()`, and `wire_dependencies()`, in that exact order, exactly as Phase 1.1's own
Configuration Lifecycle already specifies (Composition Lifecycle); map each entry of the resulting
`WiringResult.wired` dict onto the constructor argument or dependency-object field the owning stage
actually declares — a direct positional argument for Stage 8/Stage 13, a field on `AgentDependencies`
for Stage 21 (Dependency Graph); construct the retrieval closure(s) Stage 10's own frozen Configuration
section describes as "an implementation detail entirely internal to Stage 10, opaque to Stage 18,"
from the wired `EMBEDDING_PROVIDER` adapter, exactly where Phase 1.1's own Dependency Wiring Model
already reserves this step (Composition Model); supply the deployment-level scalar fields
`AgentDependencies` also carries that are not seam outputs at all (`default_planner_model_name`) from
`ApplicationSettings`/`RuntimeConfig` or an equivalent deployment-level source, never inventing new
values for them (Dependency Graph); return the fully wired set of dependency objects to whatever
process-level caller starts the application (Outputs).

## Non-Responsibilities

Phase 1.5 explicitly does **not** own, and no future patch to it may silently add without a new design
pass:

- **Embedding generation.** Stage 8's own batching, retry, checkpointing, and manifest-writing
  orchestration (`scripts/stage8_embedding_generation.py`) is untouched; the composition root supplies
  `run_stage8()` with a constructed `ProviderAdapter` and does nothing else.
- **LLM execution.** Stage 13's own `execute_prompt()`, `invoke_with_retry()`, and response-validation
  logic (`scripts/stage13_llm_execution.py`) is untouched; the composition root supplies a constructed
  `LLMAdapter` and does nothing else.
- **Planner execution.** Stage 21's own `plan_and_execute()`, `PlannerState` machine, and validation
  functions (`scripts/stage21_agent_planning.py`) are untouched; the composition root supplies a
  constructed `PlannerLLMAdapter` inside `AgentDependencies` and does nothing else.
- **Retry policies.** Stage 8's own retry loop around `is_transient_error()`, Stage 13's own
  `invoke_with_retry()`, and Stage 21's own "no retry" behavior on `PlannerInvocationError` are each
  untouched. The composition root introduces no retry logic of its own, at startup or at runtime.
- **Provider SDK behavior.** Whatever a concrete adapter's own SDK client does internally (Phase 1.2,
  1.3, 1.4's own Security/Determinism sections) is untouched and unobserved by the composition root.
- **Provider implementations.** The embedding, LLM, and planner adapters' own internal construction,
  identity, exception translation, and result-ownership rules (Phase 1.2, 1.3, 1.4) are untouched; the
  composition root calls each provider module's own factory and registration function exactly as
  supplied, never reimplementing either.
- **Configuration validation.** `validate_settings()`, `validate_wiring_result()`, and every named
  validation code in Phase 1.1's own Configuration Validation section are untouched; the composition
  root triggers them by calling Phase 1.1's own functions and does not duplicate, relax, or extend any
  of them.
- **`ProviderRegistration` schema.** The shape of `ProviderRegistration` (`seam`, `provider_name`,
  `network_dependent`, `factory`) is exactly Phase 1.1's own frozen `TypedDict`
  (`scripts/phase1_1_configuration_layer.py:70-74`); the composition root supplies instances of it,
  never redefines its fields.
- **Stage orchestration.** Stage 8, Stage 13, and Stage 21's own internal control flow, state
  machines, and validation are each untouched, exactly as stated above.

Phase 1.5 additionally does not: introduce a new dependency-injection mechanism distinct from Phase
1.1's own `ProviderRegistry`/`wire_dependencies()` pair; introduce a new provider contract distinct
from `ProviderAdapter`/`LLMAdapter`/`PlannerLLMAdapter`; hold any global mutable state, mirroring Phase
1.1's own Design Decision #1; introduce a new logging namespace or closed log-code vocabulary distinct
from Phase 1.1's own; move a responsibility from any frozen phase or stage into this document, or from
this document into any of them; define a `PipelineDependencies` dataclass that does not exist in the
repository today (Overview); mandate a specific, frozen name for its own composition entrypoint
(Public Function Contracts).

## Inputs

Two inputs, and nothing else:

- **The process environment / an optional `.env` file** — read indirectly, only through
  `load_raw_settings()`, exactly as Phase 1.1's own Public Function Contracts already describe. The
  composition root never reads `os.environ` or opens a `.env` file itself; it only calls the function
  that already does.
- **The deployment-supplied `ProviderRegistration` objects** — never a closed, named list of
  registration functions this document enumerates. The current deployment happens to supply exactly
  three, one per provider module already named in Overview; a future deployment could supply more,
  fewer, or differently-sourced registrations (a plugin scan, a config-driven list) without this
  document changing, because the composition root's own contract is "assemble whatever
  `ProviderRegistration` objects the deployment provides," never "call these three named functions."

No corpus artifact, manifest, vector index, embedding, prompt template, or cache-store entry is ever
read by this layer — none of them bears on composition.

## Outputs

- **One set of wired dependency objects**, mapped per Dependency Graph below: a constructed
  `ProviderAdapter` and `LLMAdapter` supplied as direct arguments wherever Stage 8/Stage 13's own
  entrypoints expect them, and one constructed `AgentDependencies` instance supplied wherever Stage
  21's own `plan_and_execute()` expects it. Where a deployment defines its own `PipelineDependencies`
  abstraction, the composition root maps the wired adapters into it in the same way; the repository as
  it exists today defines no such class, so this document names the direct-argument mapping as what
  actually happens now.
- **The retrieval closure(s)** Stage 10's own frozen Configuration section names as its own
  implementation detail, constructed from the wired `EMBEDDING_PROVIDER` adapter (Composition Model).

No file is written by the composition root. No new artifact directory is introduced. There is no
manifest interaction of any kind — the same zero-artifact posture every prior phase already
established, extended here to the assembly layer.

## Composition Model

**`ProviderRegistry` assembly.** The composition root collects the deployment-supplied
`ProviderRegistration` objects (Inputs) into one list and passes that list, once, to
`build_provider_registry(registrations: Sequence[ProviderRegistration]) -> ProviderRegistry` — exactly
Phase 1.1's own frozen, pure function. `build_provider_registry()` itself is never modified or
reimplemented; the composition root's own contribution is assembling the list it is called with.

**The dependency graph.** A strictly linear chain of transformations, each producing one immutable
object consumed by the next step:

```
ProviderRegistration[] (deployment-supplied)
        │
        ▼  build_provider_registry()
ProviderRegistry
        │
        ▼  wire_dependencies(settings, registry)
WiringResult { wired: Dict[seam_name, instance] }
        │
        ▼  composition-root-only mapping step (this document's own architecture)
        ├─► AgentDependencies (Stage 21) — a real, concretely-defined dataclass
        ├─► Stage 8's run_stage8(provider) — bare adapter argument, no dependency-container class
        ├─► Stage 13's execute_prompt(..., llm_adapter, ...) — bare adapter argument, no
        │     dependency-container class
        └─► retrieval closure(s) (Stage 10) — built from the wired EMBEDDING_PROVIDER adapter
```

`ApplicationSettings` is produced in parallel by `load_raw_settings()`/`validate_settings()`, before
`wire_dependencies()` is called; it is the second argument `wire_dependencies()` requires alongside the
`ProviderRegistry` above.

**Application object graph.** The composition root's own final output is not one object but a small
set of already-frozen dependency shapes, each populated from the same `WiringResult`: one
`AgentDependencies` instance (Stage 21), and, for Stage 8 and Stage 13, the wired adapter instances
themselves, ready to be passed as call arguments — never assembled into a `PipelineDependencies`
instance, since no such class exists in the repository today (Overview).

**Runtime ownership.** `ApplicationSettings`, `ProviderRegistry`, and `WiringResult` are each immutable
from the moment their constructing function returns (Phase 1.1's own Configuration Immutability,
inherited unchanged). The composition root holds all of them for exactly as long as the process that
called it is alive; it introduces no additional mutation, no additional persistence, and no additional
lifecycle beyond holding references and passing them, or values derived from them, to whatever calls
Stage 8, Stage 13, and Stage 21.

## Composition Lifecycle

A strictly linear call sequence, never a stored, mutable state machine — mirroring Phase 1.1's own
Design Decision #3 reasoning: nothing in composition branches on an external, non-deterministic
decision the way Stage 21's planning loop does.

```
[1] Startup                — the process begins; nothing has been read or constructed yet
      │
      ▼
[2] Configuration          — load_raw_settings() reads the process environment / an optional .env
      file; validate_settings() structurally and range-validates the result, producing an immutable
      ApplicationSettings (Phase 1.1's own Configuration Lifecycle steps [1]-[2], invoked here, never
      reimplemented)
      │
      ▼
[3] Provider registration  — the composition root assembles the deployment-supplied
      ProviderRegistration objects into one list and calls build_provider_registry(), producing an
      immutable ProviderRegistry (Composition Model)
      │
      ▼
[4] Dependency wiring       — wire_dependencies(settings, registry) is called once, producing an
      immutable WiringResult; validate_wiring_result() is called immediately after, per Phase 1.1's
      own Configuration Lifecycle step [5] (Validation)
      │
      ▼
[5] Application assembly   — the composition-root-only mapping step: WiringResult.wired entries are
      mapped onto AgentDependencies' own fields and onto the direct-argument shape Stage 8/Stage 13
      expect; retrieval closures are constructed from the wired EMBEDDING_PROVIDER adapter
      (Dependency Graph)
      │
      ▼
[6] Application ready       — the assembled dependency objects are returned to whatever process-level
      caller started the composition root; Stage 8, Stage 13, and Stage 21 may now be invoked with
      them
      │
      ▼
[7] Shutdown                — no shutdown contract is defined anywhere in the frozen repository. No
      phase document (1.1 through 1.4) defines an explicit disposal method for a wired adapter, for
      WiringResult, or for AgentDependencies; Phase 1.4's own Planner Invocation Lifecycle states
      disposal for its own adapter is "ordinary object lifetime... since Stage 21's own frozen
      contract calls none." This document states the same, once, for every wired object: process exit
      is ordinary object lifetime; there is no teardown callback, no explicit close() method, and no
      lifecycle hook this document introduces or assumes exists.
```

Each of steps [2]–[5] runs at most once for a given `ApplicationSettings`/`ProviderRegistry` pair, at
process start (or explicitly, in a test harness, per test) — the same "at most once, always-forward"
posture Phase 1.1's own Configuration Lifecycle already states for its own four steps, extended here to
the one additional step (application assembly) this document adds.

## Dependency Graph

An explicit ownership table for every major runtime object this document names. Each row states who
constructs it, who owns/holds it, what it is exposed to, what it is hidden from, and its lifetime.

| Object | Constructed by | Owned by | Exposed to | Hidden from | Lifetime |
|---|---|---|---|---|---|
| `ApplicationSettings` | Phase 1.1's `validate_settings()`, called by the composition root | The composition root, for the duration of process startup and thereafter as needed | The composition root; any deployment-level code that needs `RuntimeConfig`/deployment scalars | Stage 8, Stage 13, Stage 21 (none of them ever receives this object directly) | Immutable once constructed; held for the process's own lifetime, never reconstructed except by running the sequence again (Composition Lifecycle) |
| `ProviderRegistry` | Phase 1.1's `build_provider_registry()`, called by the composition root over the deployment-supplied registration list | The composition root, transiently — consumed by the very next call (`wire_dependencies()`) | `wire_dependencies()` only | Stage 8, Stage 13, Stage 21; any object returned from the composition root | Immutable once constructed; typically not retained past step [4] of Composition Lifecycle, though nothing prohibits holding it for a later re-wiring call |
| `WiringResult` | Phase 1.1's `wire_dependencies()`, called by the composition root | The composition root, transiently — consumed by the application-assembly step | The composition root's own mapping step (step [5]) | Stage 8, Stage 13, Stage 21; every wired adapter is unwrapped from `WiringResult.wired` before reaching a stage | Immutable once constructed; consumed once by the mapping step, not retained by any stage |
| The wired embedding adapter (`ProviderAdapter`) | The embedding provider module's own factory (Phase 1.3), invoked by `wire_dependencies()` | The composition root, until handed to Stage 8's own entrypoint (and to the retrieval-closure construction step) | Stage 8's `run_stage8(provider)` (direct argument); the retrieval closure this document constructs | Phase 1.1's own functions after construction; the composition root never inspects the adapter's own SDK client | Constructed once at wiring time; held for the process's own lifetime, passed by reference wherever Stage 8 or the retrieval closure needs it |
| The wired LLM adapter (`LLMAdapter`) | The LLM provider module's own factory (Phase 1.2), invoked by `wire_dependencies()` | The composition root, until handed to Stage 13's own entrypoint | Stage 13's `execute_prompt(..., llm_adapter, ...)` (direct argument) | Everything else | Constructed once at wiring time; held for the process's own lifetime |
| The wired planner adapter (`PlannerLLMAdapter`) | The planner provider module's own factory (Phase 1.4), invoked by `wire_dependencies()` | The composition root, until placed on `AgentDependencies.planner_llm_adapter` | `AgentDependencies` (as a field); Stage 21's own `plan_and_execute()` through that field | Everything else | Constructed once at wiring time; held for the process's own lifetime, as a field on the constructed `AgentDependencies` |
| Retrieval closure(s) | The composition root's own assembly step, from the wired embedding adapter (and, if configured, an `INDEX_BACKEND` adapter) | The composition root, until handed to whatever calls Stage 10 | Stage 10's own `retrieve`/`embed_query` entrypoints, exactly as Stage 10's own frozen Configuration section already describes them as "opaque to Stage 18" | The embedding/index adapters' own internal SDK clients (the closure wraps them; nothing outside the closure ever sees the adapter directly through this path) | Constructed once at application-assembly time; held for the process's own lifetime |
| `AgentDependencies` | The composition root's own assembly step, populating each field per Stage 21's own frozen dataclass (`scripts/stage21_agent_planning.py:49-60`) | The composition root, until handed to whatever calls Stage 21's `plan_and_execute()` | Stage 21's own orchestration, exactly as its own frozen contract already receives it | Nothing — this is the one object this document constructs that a frozen stage directly consumes as a whole | Constructed once at application-assembly time; held for the process's own lifetime |
| Stage 8 / Stage 13's dependency shape | Not a constructed object at all — a bare positional argument passed at each call site | Whatever code calls `run_stage8()`/`execute_prompt()`, typically the composition root's own caller | Stage 8/Stage 13's own entrypoints, directly | N/A — there is no container object to hide anything from | Passed per call; the underlying adapter instance itself has the lifetime stated above |

## Provider Registration

**Registration ownership.** Each provider module owns writing its own `get_provider_registration() ->
ProviderRegistration` function (Phase 1.2/1.3/1.4's own Factory/Public Function Contracts sections);
the composition root owns calling every such function the current deployment supplies and assembling
their return values into one list. The composition root never writes a `ProviderRegistration` itself
— it only collects ones already supplied.

**Seam ownership.** The closed set of seam names (`SUPPORTED_SEAMS`, Phase 1.1's own frozen constant)
is untouched; the composition root never introduces a new seam name, and never registers a provider
under a seam absent from that tuple.

**Factory ownership.** Each provider module's own factory function (`gemini_factory`,
`gemini_llm_factory`, `gemini_planner_factory` in the current deployment) is untouched; the composition
root never constructs an adapter itself — it only supplies the assembled `ProviderRegistry` to
`wire_dependencies()`, which is the sole caller of any factory.

**Registration ordering.** `build_provider_registry()`'s own implementation
(`scripts/phase1_1_configuration_layer.py:242-257`) keys its resulting dict by `seam` and then by
`provider_name`; the order in which registrations appear in the list the composition root assembles has
no effect on the resulting `ProviderRegistry`'s own contents. The composition root therefore has no
ordering requirement to satisfy beyond including every registration the deployment supplies exactly
once.

**Duplicate registration behavior.** Two registrations sharing an identical `(seam, provider_name)`
pair raise `PROVIDER_ALREADY_REGISTERED` (`ConfigurationWiringError`), exactly as Phase 1.1's own
Configuration Validation §2 already states, restated here by citation and never redefined. The
composition root's own responsibility is limited to not assembling a list that contains such a
duplicate; it introduces no additional deduplication logic of its own, since `build_provider_registry()`
already enforces uniqueness.

## Validation

Three tiers, mapped exactly onto Phase 1.1's own three tiers — the composition root introduces no
fourth tier of its own:

1. **Input validation** — triggered by calling `validate_settings()`; raises `ConfigurationInputError`
   on any of Phase 1.1's own named codes (`REQUIRED_FIELD_MISSING`, `FIELD_TYPE_INVALID`,
   `UNKNOWN_SEAM`, `CREDENTIAL_REF_MALFORMED`). The composition root triggers this tier by calling the
   function; it never re-validates, relaxes, or duplicates any of these checks itself.
2. **Wiring-level validation** — triggered by calling `build_provider_registry()` and
   `wire_dependencies()`; raises `ConfigurationWiringError` on `PROVIDER_ALREADY_REGISTERED`,
   `PROVIDER_NOT_REGISTERED`, `SEAM_NOT_CONFIGURED`, or `NETWORK_CALLS_DISABLED`, exactly as Phase 1.1
   already freezes them.
3. **Internal invariant validation** — triggered by calling `validate_wiring_result()`; raises
   `ConfigurationInternalError` on `WIRING_SETTINGS_FINGERPRINT_MISMATCH`,
   `WIRING_SEAM_COUNT_MISMATCH`, or `WIRING_UNKNOWN_SEAM_PRESENT`.

The composition root triggers each of these three tiers by calling Phase 1.1's own functions, in the
order Composition Lifecycle already states; it defines no fourth, composition-level validation tier of
its own. In particular, `validate_wiring_result()`'s own stated limitation — it "does not verify that
each constructed adapter instance is a subclass of its seam's declared abstract base class" (Phase
1.1's own Configuration Validation §3) — is inherited unchanged. An application composition root that
wishes to enforce type conformance beyond what Python's own ABC machinery already provides may do so
by checking each `WiringResult.wired` value against its expected abstract base class before the
application-assembly step (step [5]); Phase 1.1's own document already names this as a composition-root
option, never a Phase 1.1 invariant — this document does not mandate that such a check occur, only
notes that it is available.

## Public Function Contracts

The composition root's own entrypoint is described here only by shape — inputs, outputs, ordering,
ownership — never by a mandated, frozen name. **No script in the current repository defines a
composition-root entrypoint of any kind; any function name used in this section (for illustration
only, e.g. `compose_application(...)`) is illustrative, not frozen, and this document does not mandate
that exact name.** A future implementation is free to name, split, or structure its own
composition-root entrypoint(s) however it needs to, as long as the ordering and ownership stated below
hold.

- **The illustrative composition entrypoint** — takes, at minimum, the deployment-supplied list of
  `ProviderRegistration` objects (Inputs) and whatever `load_raw_settings()` itself accepts
  (`env`, `dotenv_path` — both optional); internally calls, in order, `load_raw_settings()`,
  `validate_settings()`, `build_provider_registry()`, `wire_dependencies()`, `validate_wiring_result()`
  (Composition Lifecycle); performs the application-assembly step (Dependency Graph); returns the
  resulting set of dependency objects (Outputs). Raises whatever `ConfigurationInputError`/
  `ConfigurationWiringError`/`ConfigurationInternalError` any of Phase 1.1's own called functions
  raises, unmodified and unwrapped, exactly as Phase 1.1's own functions already raise them (Failure
  Handling).
- **`build_provider_registry(registrations: Sequence[ProviderRegistration]) -> ProviderRegistry`** —
  Phase 1.1's own frozen function, restated here only to name the composition root's own obligation
  against it: supply the deployment's full set of registrations, assembled once, in one list, before
  the call (Provider Registration).
- **`wire_dependencies(settings: ApplicationSettings, registry: ProviderRegistry) -> WiringResult`** —
  Phase 1.1's own frozen function, restated here only to name the composition root's own obligation
  against it: call it exactly once per `(settings, registry)` pair, after both have been produced by
  the two functions preceding it in Composition Lifecycle.

No function architected under this document ever imports a provider SDK directly, ever reads
`os.environ` directly (Phase 1.1's own `load_raw_settings()`/`wire_dependencies()` are the only
functions in the entire dependency graph that do), or ever opens a network socket itself (every network
call belongs to a concrete adapter's own SDK client, constructed by `wire_dependencies()`'s own factory
calls, never by the composition root directly).

## Determinism

**Deterministic (guaranteed, given identical input):**

- **Which seams wire successfully and which raise a wiring-level error**, given identical
  `(ApplicationSettings, ProviderRegistry)` — a pure function of those two inputs alone, exactly as
  Phase 1.1's own Determinism section already states, inherited unchanged.
- **The composition-root's own application-assembly mapping** (step [5]) — a fixed, structural mapping
  from `WiringResult.wired` keys onto `AgentDependencies`' own fields and onto Stage 8/Stage 13's own
  call-argument positions; given an identical `WiringResult`, the mapping produces an identical
  assembled object graph.
- **Whether a given deployment's registration list contains a duplicate `(seam, provider_name)` pair**
  — a pure, structural check.

**Explicitly NOT deterministic (inherent to the sources this layer composes; never assumed, never
hidden):**

- **Whatever each provider factory does when invoked** — SDK client construction, any connection setup
  or credential validation a specific SDK performs at construction time — is entirely inherited from
  Phase 1.2/1.3/1.4's own Determinism sections; the composition root's own `wire_dependencies()` call
  treats each factory's return value opaquely and inherits, never introduces, any non-determinism in
  that construction.
- **The actual values read from `os.environ`/`.env` at load time** — inherited unchanged from Phase
  1.1's own Determinism section.

## Read-Only Guarantees

- The composition root never modifies `manifest.json`, any corpus artifact, any vector index, any
  embedding, any prompt template, or any cache store entry — it has no relationship to any of them at
  all.
- The composition root never modifies `ApplicationSettings`, `ProviderRegistry`, or `WiringResult`
  after the function that constructed each one returns — inherited unchanged from Phase 1.1's own
  Read-Only Guarantees.
- The composition root never mutates a wired adapter instance's own internal state, and never mutates
  `AgentDependencies` after constructing it — assembly is a one-time, forward-only step (Composition
  Lifecycle), never a later in-place update.
- The composition root holds no module-level mutable state of its own, mirroring Phase 1.1's own Design
  Decision #1 — every object it produces is returned to whatever process-level caller started it, which
  is solely responsible for holding onto it and threading it into Stage 8/Stage 13/Stage 21.
- The only external side effects the composition root's own call sequence performs are exactly the ones
  Phase 1.1's own functions already name (one optional `.env` read, process-environment reads at load
  and wiring time) plus whatever each provider factory's own SDK client construction does on its own
  behalf (Phase 1.2/1.3/1.4, inherited) — the composition root introduces no additional side effect of
  its own.

## Failure Handling

**Startup failures only — the composition root introduces no runtime retry logic of any kind.**

- **A malformed configuration value** — `ConfigurationInputError`, raised from `validate_settings()`,
  propagates unmodified through the composition root to its own caller; no `ApplicationSettings` is
  produced; no registration, wiring, or assembly step is ever attempted.
- **A duplicate `(seam, provider_name)` registration in the deployment-supplied list** —
  `ConfigurationWiringError` (`PROVIDER_ALREADY_REGISTERED`), raised from `build_provider_registry()`,
  propagates unmodified; no `ProviderRegistry` is produced.
- **A configured seam with no matching registered factory, or a network-dependent factory when network
  calls are disabled** — `ConfigurationWiringError` (`PROVIDER_NOT_REGISTERED` or
  `NETWORK_CALLS_DISABLED`), raised from `wire_dependencies()`, propagates unmodified; wiring halts for
  the whole call, exactly as Phase 1.1's own Failure Handling already states ("either every configured
  seam resolves, or the call raises").
- **A genuine Phase 1.1 internal-invariant violation** — `ConfigurationInternalError`, raised from
  `validate_wiring_result()`, propagates unmodified.
- **A construction-time failure inside a specific provider factory** (Phase 1.2/1.3/1.4's own
  Construction-time validation) — whatever exception that factory raises propagates through
  `wire_dependencies()` unmodified, exactly as Phase 1.1's own `wire_dependencies()` contract already
  treats a factory's exceptions opaquely; the composition root does not catch, wrap, or reinterpret it.
- **No retry, no fallback provider, no degraded application state.** A composition failure at any of
  the four tiers above is always a hard stop with a named, actionable error, propagated to whatever
  process-level caller started the composition root — never a silent substitution of some other
  provider, never a partially-assembled `AgentDependencies`, and never a retry loop around any of Phase
  1.1's own functions. This mirrors exactly Phase 1.1's own Failure Handling posture ("No retry, no
  fallback provider, no degraded configuration mode"), extended here to the one additional
  assembly step this document adds.

## Security Considerations

- **Credential ownership, inherited unchanged.** Phase 1.1's own complete credential lifecycle
  (`load_raw_settings()` reads raw environment values into `RawSettings`; `validate_settings()` never
  carries a raw secret into `ApplicationSettings`; `wire_dependencies()` resolves a credential
  transiently, once per seam, and hands it to that seam's factory) governs every credential this
  composition root ever causes to be read. The composition root itself never reads `os.environ`
  directly, never resolves a `credential_ref`, and never receives a raw credential value as an
  argument or return value anywhere in its own call sequence — only `load_raw_settings()` and
  `wire_dependencies()` do that, and both are Phase 1.1's own functions, called by the composition root
  but never reimplemented by it.
- **SDK ownership, inherited unchanged.** Each concrete adapter's own SDK client is constructed inside
  that adapter's own factory, during the `wire_dependencies()` call; the composition root never
  constructs an SDK client itself, never receives one directly (only the fully constructed adapter
  instance, via `WiringResult.wired`), and never holds a reference to one independent of holding the
  adapter instance itself — exactly the ownership boundary Phase 1.2/1.3/1.4 already state for Phase 1.1
  itself, extended here to the composition root.
- **Dependency ownership.** The composition root holds the final, assembled object graph
  (`AgentDependencies`, the wired Stage 8/Stage 13 adapters, the retrieval closures) for the life of
  the process; none of these objects carries a raw credential in any field a caller could read
  directly — the only object anywhere in this chain that ever touches a credential's origin is
  `ProviderSettings.credential_ref`, and it is, by Phase 1.1's own contract, a reference string, never
  a value.
- **Composition-root-specific guarantee.** The composition root introduces no new credential-handling
  surface of its own — it neither logs, prints, serializes, nor persists any value derived from
  `ApplicationSettings`/`ProviderSettings`/a resolved credential, matching Phase 1.1's own "No secret
  logging"/"No secret serialization"/"No secret persistence" guarantees exactly, since the composition
  root never possesses a raw secret value to begin with.

## Logging Vocabulary

This section defines the vocabulary available to a composition-root implementation **if** it emits
logs; exactly like every prior phase's own Logging Vocabulary section, it does not mandate that logging
occur.

This document introduces no new `stage` identifier and no new closed-vocabulary log codes. A
composition-root implementation calls Phase 1.1's own functions, each of which already owns its own
logging vocabulary (`INFO_CONFIGURATION_LOADED`, `INFO_CONFIGURATION_VALIDATED`,
`INFO_PROVIDER_REGISTRY_BUILT`, `INFO_DEPENDENCIES_WIRED`, and the rest of Phase 1.1's own Logging
Vocabulary section) — extending that vocabulary is Phase 1.1's own revision path, never this document's.

A composition-root implementation that wishes to emit its own internal diagnostic information (for
example, "application assembly completed" or "retrieval closure constructed") may do so at DEBUG
severity or below, subject to the same hard constraint stated in Security Considerations: it may never
include a resolved raw credential, any raw configuration value from `REDACTED_FIELD_NAMES`, or any
value Phase 1.1's own Security Considerations already prohibits from being logged.

## Concurrency

**Startup concurrency only.** Composition happens once per process lifetime (or once per explicit,
isolated call in a test harness), mirroring Phase 1.1's own Concurrency section exactly: "Configuration
loading, validation, and wiring happen once per process lifetime... producing immutable objects." The
composition root introduces no locking, no mutex, and no coordination of its own beyond calling Phase
1.1's own functions in the fixed order Composition Lifecycle states.

Concurrent reads of an already-assembled `AgentDependencies` instance, or of an already-wired adapter,
by multiple threads are inherently safe only to the extent the underlying SDK client each adapter wraps
is itself thread-safe (Phase 1.2/1.3/1.4's own Concurrency sections, inherited unchanged) — this
document asserts no concurrency guarantee beyond what those documents already state for their own
adapters, and it is ownership-only: the composition root is the one place that decides, once, which
adapter instance is shared across whatever later concurrent calls a process makes; it does not itself
introduce any synchronization primitive.

## Design Decisions

1. **Registration-list assembly is the composition root's own job, never Phase 1.1's, and never a
   fixed, named list of functions this document enumerates.** Phase 1.1's own Design Decision #7
   already rejects an import-time side-effect registration mechanism ("a decorator that mutates a
   module-level dict... reintroduces exactly the global-mutable-state and hidden-side-effect patterns
   Design Decision #1 forbids") in favor of an explicit, caller-assembled list. This document extends
   that same reasoning one step further: not only must assembly be explicit rather than a side effect,
   it must be described as "whatever the deployment supplies," never as "these three named functions,"
   so that a future deployment can add, remove, or resource a registration differently (a config file,
   a plugin discovery mechanism) without requiring a revision to this architecture.

2. **Retrieval-closure construction lives in the composition root, not in Phase 1.1 or in the embedding
   provider itself.** Phase 1.1's own Dependency Wiring Model already states that producing Stage 10's
   own `retrieve`/`embed_query` closure from the wired `EMBEDDING_PROVIDER` (and `INDEX_BACKEND`)
   adapters is "application-composition-root work, described here only as a mapping target, never
   implemented in this document." Phase 1.3's own Future Phase Boundaries repeats the same reservation.
   This document is where that already-reserved work is finally given an explicit home, never a new
   responsibility invented here.

3. **No fourth validation tier is introduced.** Phase 1.1's own Design Decision #4 already explains why
   its own validation model has exactly three tiers and no "package findings" tier; adding a
   composition-level fourth tier would repeat the same "partially successful configuration" mistake
   Phase 1.1's own document already rejects for its own object lifecycle. The composition root's own
   correctness is binary — either every step succeeds and assembly proceeds, or a step raises and
   assembly never happens — mirroring Phase 1.1's own "either every configured seam wires, or the call
   raises" posture exactly.

4. **The composition entrypoint's own name is stated as illustrative, never frozen.** Unlike Phase
   1.1/1.2/1.3/1.4, each of which restates a real, already-shipped function signature by citation, no
   script in the current repository defines a composition-root entrypoint at all. Naming one function
   name as though it were already established (`compose_application`, or any other) would misrepresent
   the repository's own current state; stating explicitly that any name used here is illustrative
   avoids a future reader mistaking an illustration for a frozen contract this document does not
   actually establish.

5. **No shutdown contract is invented.** Given how naturally an "application assembly" document could
   drift into defining teardown callbacks, disposal methods, or a shutdown hook, this document states
   directly that no such contract exists anywhere in the frozen repository — Phase 1.4's own Planner
   Invocation Lifecycle already treats disposal as "ordinary object lifetime," and no other phase states
   anything stronger. Inventing a shutdown method here would add behavior none of Phase 1.1 through 1.4
   asked for, exactly the kind of unrequested addition every prior phase's own Design Decisions section
   already warns against.

6. **`PipelineDependencies` is named as an undefined, deferred mapping target, never as an existing
   class.** Phase 1.1 and Phase 1.2 each refer to `PipelineDependencies.llm_adapter`/
   `PipelineDependencies.cache_adapter` as mapping targets, but neither Stage 8 nor Stage 13's own
   script defines any such dataclass. Stating this precisely — rather than silently assuming the class
   exists, or silently inventing one — keeps this document's own claims falsifiable against the actual
   shipped code, the same discipline Phase 1.4 already applied when stating `PlannerLLMAdapter`
   declares no identity property.

## Constants

```python
# This document defines no numeric threshold, ceiling, or default of its own. Every constant governing
# configuration, provider behavior, or stage orchestration remains exactly where Phase 1.1 through 1.4
# and Stage 8/13/21 already own it — none of it is duplicated here.

# This document names no closed list of provider registration functions. If it names anything, it is
# only the current deployment's own provider registrations, illustrative only, never a closed contract
# this document or Phase 1.1 enforces:
#   - the embedding provider module's get_provider_registration() (Phase 1.3's concrete implementation)
#   - the LLM provider module's get_provider_registration() (Phase 1.2's concrete implementation)
#   - the planner provider module's get_provider_registration() (Phase 1.4's concrete implementation)
# A future deployment may supply more, fewer, or differently-sourced registrations without this
# document changing (Design Decisions #1).
```

No numeric threshold, ceiling, or default belonging to any frozen phase or stage
(`CONFIGURATION_LAYER_VERSION`, `MAX_PLAN_STEPS`, `BATCH_SIZE`, or any other) is duplicated here — every
one of them already lives, exactly once, in the document or script that owns it.

## Complexity

- **Configuration (steps [2] of Composition Lifecycle)** — inherited unchanged from Phase 1.1's own
  Complexity section: O(E) for `load_raw_settings()`, O(F) for `validate_settings()`.
- **Provider registration (step [3])** — O(R), where R is the number of `ProviderRegistration` objects
  the deployment supplies — a small, fixed number in the current deployment (three), never assumed
  fixed at that number by this document.
- **Dependency wiring (step [4])** — inherited unchanged from Phase 1.1's own Complexity section: O(S),
  bounded above by `len(SUPPORTED_SEAMS)` (eight).
- **Application assembly (step [5])** — O(S), a fixed, small number of dict-key reads and field
  assignments per wired seam; the actual cost of constructing a retrieval closure or any other assembled
  object is O(1) from this document's own perspective, since it is a fixed reference-holding operation,
  never a computation over data.

## Known Limitations

- **No hot-reload, no dynamic re-registration**, inherited unchanged from Phase 1.1's own Known
  Limitations: a running process's configuration and wiring are fixed for its lifetime once assembled;
  a genuine reconfiguration means running the whole sequence again from step [2], producing an entirely
  new object graph.
- **No per-tenant or per-caller provider selection**, inherited unchanged from Phase 1.1's own Known
  Limitations: `ApplicationSettings` names exactly one provider per seam for the whole process; the
  composition root assembles exactly one application object graph per invocation of its own sequence.
- **The current deployment supplies exactly three registrations**, one per seam with a concrete Gemini
  implementation today (`EMBEDDING_PROVIDER`, `LLM_PROVIDER`, `PLANNER_LLM_PROVIDER`); the remaining
  seams named in Phase 1.1's own `SUPPORTED_SEAMS` (`INDEX_BACKEND`, `CACHE_BACKEND`,
  `CONVERSATION_STORE`, `TOOL_REGISTRY`, `TOOL_ADAPTER`) have no concrete registration supplied by this
  document — a future deployment adding one does not require any change to this architecture (Design
  Decisions #1).
- **No composition-root-level disposal, teardown, or shutdown mechanism**, stated as its own limitation
  rather than left as an unstated gap (Composition Lifecycle step [7], Design Decisions #5).
- **No enforcement of adapter-to-ABC conformance beyond what Python's own ABC machinery already
  provides**, inherited unchanged from Phase 1.1's own Configuration Validation §3 — an application
  wishing stronger guarantees may add its own check, but this document does not require or standardize
  one (Validation).

## Future Phase Boundaries

**The composition root is the final assembly layer.** Every gap named as "composition-root work" by
Phase 1.1's own Future Phase Boundaries, and repeated by Phase 1.2/1.3/1.4's own Future Phase
Boundaries sections, is closed by this document's own architecture. No further phase is reserved by
this document for assembling `ApplicationSettings`, `ProviderRegistry`, or `WiringResult` into
dependency objects — that work is what Phase 1.5 itself defines.

**Future phases may extend providers.** A new concrete provider implementation for any seam Phase 1.1
already names (`INDEX_BACKEND`, `CACHE_BACKEND`, `CONVERSATION_STORE`, `TOOL_REGISTRY`,
`TOOL_ADAPTER`, or an additional provider for a seam that already has one) supplies its own
`ProviderRegistration` and its own factory, exactly as Phase 1.2/1.3/1.4's own concrete implementations
already do — the composition root's own architecture requires no change to accept it, per Design
Decisions #1's own deployment-supplied framing.

**Future phases may extend applications.** A deployment introducing a genuinely different application
shape — a different UI, a different set of stages wired together, a `PipelineDependencies` class that
does not exist today — may do so by supplying its own application-assembly mapping step (Dependency
Graph), consuming the same `WiringResult` this document's architecture already produces.

**They do not redesign dependency injection.** No future provider or application extension modifies
Phase 1.1's own `ApplicationSettings`/`ProviderSettings`/`ProviderRegistration`/`wire_dependencies()`
contracts — those remain exactly as Phase 1.1 already froze them, for every future extension, without
exception.

**They do not redesign the composition root.** No future provider or application extension modifies
this document's own architecture — the registration-assembly step, the four-function invocation order,
the mapping discipline, and the ownership boundaries stated above remain exactly as this document
states them, for every future extension.

**They do not redesign provider contracts.** No future extension modifies `ProviderAdapter`,
`LLMAdapter`, or `PlannerLLMAdapter` (Stage 8/13/21's own frozen contracts) — a new provider
implements one of these three existing contracts, never a new one.

**They do not redesign stage orchestration.** No future extension modifies Stage 8's batching/retry
loop, Stage 13's retry policy, or Stage 21's planning loop — a new provider or application shape is
supplied to these stages' own existing entrypoints, exactly as this document's own Dependency Graph
already states, never by altering what those entrypoints do internally.

Every stage from Stage 0 through Stage 21, Phase 1.1 in full, Phase 1.2 in full, Phase 1.3 in full, and
Phase 1.4 in full, remain exactly as independently usable, and exactly as frozen, as they already are
today. Phase 1.5 adds the one remaining layer that assembles what all of them already know how to
produce and receive — it adds nothing any of them must call differently, and nothing they must change
to receive it.
