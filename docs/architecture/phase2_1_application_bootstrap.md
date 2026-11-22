# Phase 2.1 — Application Bootstrap Architecture

Stages 0–21, Phase 1.1 (Configuration Layer), Phase 1.2 (LLM Provider Architecture), Phase 1.3
(Embedding Provider Architecture), Phase 1.4 (Planner Provider Architecture), and Phase 1.5
(Composition Root Architecture) remain completely frozen; nothing below proposes any change to
existing code or shipped docs. Phase 2.1 defines the architecture for the **application bootstrap
layer** — the one, one-time act of invoking the composition root's own public contract, deciding
whether the result means the application is ready, and stating what happens when it is not.

**Framing principle, stated once, governing this entire document:** Phase 2.1 describes the bootstrap
layer as invoking **the composition root's public contract** — described by Phase 1.5's own Public
Function Contracts section, which already states that its own entrypoint's concrete name is
illustrative, not frozen. This document does not name, describe, or depend on any current script's
specific function signature; it builds against Phase 1.5's own contract exactly as Phase 1.5 itself
states it, the same citation discipline every prior phase already applies to the layer beneath it.

**Provider-neutrality and DI-neutrality, stated once, governing this entire document:** nothing below
depends on which providers are registered, how many seams are configured, or which concrete adapters a
deployment supplies. Bootstrap's own architecture is identical regardless of the composition root's
own inputs — it treats the composition root as a single opaque call with a known success/failure shape.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Phase 1.5's own Composition Model defines a strictly linear chain that ends with an assembled
dependency-object set — `AgentDependencies`, the wired Stage 8/Stage 13 adapters, retrieval closures —
returned "to whatever process-level caller starts the application." Phase 1.5 deliberately stops there:
it composes the graph, but does not define what happens next. Composing a dependency graph and using
one are different concerns, and nothing in Phase 1.1 through 1.5 defines how a process actually starts,
how it decides the application is ready, how a startup failure reaches whatever started the process, or
what "application lifetime" means one layer above composition. That is the narrow gap Phase 2.1 closes.

Phase 2.1 does not implement anything. It defines: (1) the architecture of the one-time sequence that
invokes the composition root's own public contract and interprets its result as either "ready" or
"failed," with no third outcome; (2) what constitutes one application instance, what is held for that
instance's lifetime, and when that instance ceases to exist; and (3) the boundary between bootstrap and
everything above it — a process entrypoint, a deployment surface, a hosting framework — none of which
this document designs.

## Scope

Phase 2.1 answers exactly one question — given the composition root's own public contract and nothing
else, what is the architecture of the one-time startup sequence that turns "an assembled dependency
graph exists" into "the application is ready" — and stops there.

It never redesigns dependency injection — Phase 1.1's own `ApplicationSettings`/`ProviderSettings`/
`ProviderRegistration`/`wire_dependencies()` contracts are used exactly as already frozen, entirely
inside the composition root's own call, never touched directly by this layer. It never redesigns any
provider — Phase 1.2/1.3/1.4's own adapter architectures are untouched. It never redesigns the
composition root itself — Phase 1.5's own registration-assembly, wiring-invocation-order, and
application-assembly-mapping responsibilities are untouched; bootstrap calls the composition root's
public contract exactly as Phase 1.5 already defines it, never modifying what happens inside that call.
It never redesigns any stage's own orchestration — Stage 8, Stage 13, and Stage 21 are each untouched.
It never designs a process entrypoint, a command-line interface, a REST or other network-facing API, a
hosting framework, or a deployment/container/cloud concern of any kind — each is named only as deferred
future work (Future Phase Boundaries), never designed here.

## Responsibilities

Phase 2.1 shall: define the application bootstrap lifecycle as a strictly linear, one-time sequence
from process start through readiness (or failure) (Bootstrap Lifecycle); define the startup sequence
that invokes the composition root's own public contract exactly once (Bootstrap Lifecycle, Public
Function Contracts); define composition-root invocation as the one call bootstrap makes downward, and
nothing else (Application Model, Public Function Contracts); define startup validation at this layer as
binary — either the composition call succeeds and the application is ready, or it raises and the
application never becomes ready — introducing no new validation tier beyond what Phase 1.1 and Phase
1.5 already define (Startup Validation); define runtime readiness as an internal state concept, never a
network-facing probe (Application Model, Bootstrap Lifecycle); define graceful startup failure as
propagate-unmodified, never swallow-and-continue or degrade-and-proceed (Failure Handling); define
application lifetime as the lifetime of one application instance — one composition call, one held
dependency-object set, for the life of the process holding it (Application Model); state explicitly,
per the frozen sources, that no shutdown contract exists anywhere in the frozen repository, and that
this document introduces none either (Bootstrap Lifecycle); define the application boundary — nothing
above bootstrap is architected by any frozen document (Application Model, Future Phase Boundaries);
define dependency graph exposure as holding and forwarding the same object set Phase 1.5 already
outputs, inventing no new container type or field (Outputs, Application Model).

## Non-Responsibilities

Phase 2.1 explicitly does **not** perform, and no future patch to it may silently add without a new
design pass:

- **Provider registration.** Assembling the deployment-supplied `ProviderRegistration` objects and
  calling `build_provider_registry()` is entirely inside the composition root's own call
  (`phase1_5_composition_root.md` §Provider Registration, §Composition Lifecycle step [3]); bootstrap
  never assembles a registrations list itself — it supplies whatever the composition root's own public
  contract requires as an input and nothing more.
- **Dependency wiring.** `wire_dependencies()` and `validate_wiring_result()` are entirely Phase 1.1's
  own frozen functions, invoked from inside the composition root's own call
  (`phase1_1_configuration_layer.md` §Public Function Contracts; `phase1_5_composition_root.md`
  §Composition Lifecycle steps [4]); bootstrap never calls either directly.
- **Constructing adapters.** Every concrete adapter (embedding, LLM, planner) is constructed by its own
  provider module's own factory, invoked once by `wire_dependencies()`
  (`phase1_2_llm_provider.md`/`phase1_3_embedding_provider.md`/`phase1_4_planner_provider.md` §Prompt/
  Embedding/Planner Invocation Lifecycle); bootstrap never constructs, inspects, or holds a reference to
  an SDK client independent of holding the composition root's own returned object set.
- **Redesigning configuration.** `ApplicationSettings`, `ProviderSettings`, `RuntimeConfig`, and every
  Phase 1.1 validation tier are untouched (`phase1_1_configuration_layer.md` §Configuration Model,
  §Configuration Validation); bootstrap never re-validates, relaxes, or duplicates any of them.
- **Redesigning `ProviderRegistry`.** Its shape and construction (`build_provider_registry()`) remain
  exactly as Phase 1.1 already froze them; bootstrap never inspects or modifies a `ProviderRegistry`
  instance.
- **Redesigning `AgentDependencies`.** Its field shape remains exactly as Stage 21 already defines it
  (`scripts/stage21_agent_planning.py:49-60`) and exactly as the composition root already assembles it
  (`phase1_5_composition_root.md` §Dependency Graph); bootstrap holds the already-assembled instance,
  never reconstructing or re-mapping any of its fields.
- **Redesigning retrieval closures.** Their construction from the wired `EMBEDDING_PROVIDER` adapter is
  entirely the composition root's own assembly step (`phase1_5_composition_root.md` §Composition Model,
  §Design Decisions #2); bootstrap holds whatever closure(s) the composition root returns, never
  constructing or modifying one itself.
- **Redesigning Stage 8.** Stage 8's own batching/retry orchestration is untouched; bootstrap never
  calls Stage 8's own entrypoint or inspects its own internal state.
- **Redesigning Stage 13.** Stage 13's own retry policy, timeout policy, and validation are untouched;
  bootstrap never calls Stage 13's own entrypoint or inspects its own internal state.
- **Redesigning Stage 21.** Stage 21's own `PlannerState` machine and `plan_and_execute()` loop are
  untouched; bootstrap never calls Stage 21's own entrypoint or inspects its own internal state.

Phase 2.1 additionally does not: introduce a process entrypoint, a command-line interface, a REST or
other network-facing API, a hosting framework, or any deployment/container/cloud concern (Future Phase
Boundaries); introduce a health-check endpoint, readiness probe route, or any other network-facing
readiness surface (Application Model); introduce retry, backoff, or fallback logic around a failed
composition-root call (Failure Handling); introduce a shutdown, teardown, or disposal contract that no
frozen source defines (Bootstrap Lifecycle); hold any global mutable state of its own; move a
responsibility from any frozen phase or stage into this document, or from this document into any of
them.

## Inputs

One input, and nothing else:

- **The composition root's own public contract** — described by Phase 1.5's own Public Function
  Contracts section: an entrypoint that accepts, at minimum, the deployment-supplied set of
  `ProviderRegistration` objects and whatever `load_raw_settings()` itself accepts, and returns the
  wired dependency-object set described in Phase 1.5's own Outputs section, or raises one of Phase
  1.1's own three configuration exception types unmodified.

Bootstrap supplies to this one call whatever the composition root's own contract requires as its own
inputs (the registrations set, and optionally an environment mapping or `.env` path) — it does not
itself assemble a registrations list, read `os.environ`, or open a `.env` file; every one of those
remains exclusively inside the composition root's own call, exactly as Phase 1.5 already states.

No other input exists. No corpus artifact, manifest, vector index, embedding, prompt template, or
cache-store entry is ever read by this layer — none of them bears on bootstrap.

## Outputs

- **One held application instance** — the same wired dependency-object set Phase 1.5's own composition
  root already outputs (`AgentDependencies`, the wired Stage 8/Stage 13 adapters, retrieval closures),
  now held by the bootstrap layer for the duration of one application instance's own lifetime
  (Application Model), and exposed onward to whatever needs it. Bootstrap introduces no new container
  type, no new field, and no new shape beyond what Phase 1.5 already names.
- **A readiness outcome** — either the application instance is ready (the composition call returned
  successfully and the dependency-object set is now held), or startup failed (the composition call
  raised, and no application instance exists) — never a third outcome.

No file is written by the bootstrap layer. No new artifact directory is introduced. There is no
manifest interaction of any kind — the same zero-artifact posture every prior phase already
established, extended here to the layer above composition.

## Application Model

**One application instance** is the dependency-object set produced by exactly one successful
composition-root call, held by exactly one bootstrap invocation. There is no notion of a "partial"
instance — either the composition call succeeded and exactly one instance now exists, or it raised and
no instance exists at all, mirroring Phase 1.5's own "either every step succeeds ... or a step raises"
posture one layer further out.

**What is owned for that instance's lifetime.** The entire held dependency-object set is owned as a
single unit for the instance's own lifetime — never partially released, never partially replaced, never
partially re-wired. Bootstrap does not distinguish between "the LLM adapter's lifetime" and "the
planner adapter's lifetime" as separate spans; both are the same instance's own lifetime, because both
arrived from the same, single composition-root call.

**When an instance ceases to exist.** An application instance ceases to exist when the process holding
it ends. There is no other termination event this document defines — no explicit release call, no
partial teardown, no independent disposal of one held object ahead of another. This is a direct
consequence of the shutdown finding stated in full under Bootstrap Lifecycle: since no shutdown contract
exists anywhere in the frozen repository, an instance's own end is simply the end of ordinary object
lifetime, not a defined event this document could otherwise describe.

**Runtime readiness**, correspondingly, is an internal state concept only, describing whether an
application instance currently exists: never a network-facing probe, health-check endpoint, or CLI
flag. A caller holding a successfully-returned dependency-object set already has everything "readiness"
means at this layer; no separate readiness query, method, or endpoint is defined here, because
inventing one would introduce exactly the kind of network-facing surface this document's own Scope
excludes.

**The application boundary.** Bootstrap is the outermost layer any frozen document describes. Below it
is the composition root (Phase 1.5), which in turn sits above Phase 1.1's configuration machinery and
every provider implementation. Above bootstrap is whatever actually starts the process — a script's own
entrypoint, a CLI, a hosting framework — none of which is architected by this document or by any prior
phase (Future Phase Boundaries).

## Bootstrap Lifecycle

A strictly linear call sequence, never a stored, mutable state machine — mirroring Phase 1.1's own
Design Decision #3 reasoning and Phase 1.5's own Composition Lifecycle: nothing in bootstrap branches on
an external, non-deterministic decision the way Stage 21's planning loop does.

```
[1] Startup                — the process begins; no application instance exists yet
      │
      ▼
[2] Composition-root invocation — bootstrap calls the composition root's own public contract exactly
      once, supplying whatever inputs that contract requires (Inputs)
      │
      ▼
[3] Readiness decision     — if the call returns successfully, the returned dependency-object set
      becomes the one held application instance, and the application is ready (Application Model);
      if the call raises, no application instance is created, and startup has failed — there is no
      third outcome
      │
      ▼
[4a] Application ready      — the held dependency-object set is exposed onward to whatever needs it;
      the application instance's own lifetime begins
      │                                                         [4b] Startup failed — the raised
      ▼                                                          exception propagates unmodified
[5] Application lifetime    — the instance persists, unchanged, for as long as the process holding it
      is alive; no re-invocation of the composition root occurs for this instance, and no partial
      re-wiring of any one held object occurs independently of the others
      │
      ▼
[6] Shutdown                — no shutdown contract is defined anywhere in the frozen repository.
      Phase 1.5's own Composition Lifecycle step [7] and Design Decision #5 already state this for the
      composition root's own held objects; this document states the same conclusion, once, one layer
      up: process exit is ordinary object lifetime for the application instance as a whole. There is
      no teardown callback, no explicit close() method, and no lifecycle hook this document introduces
      or assumes exists.
```

Steps [2]–[4] run at most once per application instance — the same "at most once, always-forward"
posture Phase 1.1's own Configuration Lifecycle and Phase 1.5's own Composition Lifecycle already state
for their own steps, extended here one layer further out. A genuine restart means a new process running
this sequence again from step [1], producing an entirely new application instance, never resuming or
partially reusing a prior one.

## Startup Validation

Startup validation at this layer is binary and introduces no new tier. Phase 1.1 already defines three
validation tiers (input, wiring-level, internal-invariant); Phase 1.5's own Design Decision #3 already
states the composition root introduces no fourth. Bootstrap introduces no fifth: it observes only
whether the one composition-root call (which itself triggers all three of Phase 1.1's own tiers,
exactly as Phase 1.5 already describes) returned successfully or raised.

There is no partially-ready application state this layer recognizes. Either the composition call
succeeded — in which case every validation tier beneath it has already passed — or it raised, in which
case bootstrap performs no further validation of its own and no application instance is created.
Bootstrap does not re-check, sample, or spot-verify anything about the returned dependency-object set;
trusting the composition root's own already-frozen guarantee is the entire extent of this layer's own
validation posture.

## Public Function Contracts

The bootstrap layer's own entrypoint is described here only by shape — inputs, outputs, ordering,
ownership — never by a mandated, frozen name, exactly mirroring how Phase 1.5 itself treats its own
composition entrypoint. No script in the current repository defines a bootstrap entrypoint of any kind;
any function name that might illustrate this section is illustrative only, and this document does not
mandate one.

- **The illustrative bootstrap entrypoint** — takes, at minimum, whatever the composition root's own
  public contract itself requires as input (Inputs); internally invokes that contract exactly once
  (Bootstrap Lifecycle step [2]); on success, returns the held dependency-object set as the ready
  application instance (Outputs); on failure, allows whatever exception the composition root's own
  contract raised to propagate unmodified (Failure Handling) — never catching, wrapping, or
  reinterpreting it.
- **The composition root's own public contract** — restated here only to name bootstrap's own
  obligation against it: call it exactly once per application instance, after assembling whatever
  inputs it requires, and treat its return value opaquely — bootstrap never inspects the internal shape
  of the returned dependency-object set beyond holding and forwarding it as a whole.

No function architected under this document ever imports a provider SDK directly, ever reads
`os.environ` or opens a `.env` file directly (those remain exclusively inside the composition root's
own call, per Phase 1.1's own Security Considerations, inherited unchanged), or ever opens a network
socket itself.

## Determinism

**Deterministic (guaranteed, given identical input):**

- **Whether startup succeeds or fails**, given an identical set of inputs to the composition root's own
  public contract — a pure consequence of whatever the composition root's own Determinism section
  already guarantees for its own call, inherited unchanged one layer up.
- **The readiness decision itself** — a fixed, binary function of whether the one composition-root call
  raised or returned: given an identical outcome from that call, bootstrap's own readiness decision is
  identical every time.

**Explicitly NOT deterministic (inherent to the sources this layer invokes; never assumed, never
hidden):**

- **Whatever the composition root's own call does internally** — provider factory construction, SDK
  client setup, and any non-determinism Phase 1.2/1.3/1.4's own Determinism sections already name — is
  entirely inherited, never introduced or hidden by this layer. Bootstrap treats the composition root's
  own call as an opaque unit and inherits whatever non-determinism already exists inside it.

## Read-Only Guarantees

- The bootstrap layer never modifies `manifest.json`, any corpus artifact, any vector index, any
  embedding, any prompt template, or any cache store entry — it has no relationship to any of them at
  all.
- The bootstrap layer never modifies the dependency-object set returned by the composition root after
  that call returns — it holds and forwards the same objects, never mutating any one of them
  independently.
- The bootstrap layer holds no module-level mutable state of its own beyond the one held application
  instance itself, mirroring Phase 1.1's and Phase 1.5's own Design Decision #1 — every application
  instance it produces is returned to whatever process-level caller started bootstrap, which is solely
  responsible for holding onto it and threading it into whatever needs it.
- The only external side effects the bootstrap layer's own call sequence performs are exactly the ones
  the composition root's own call already performs (Phase 1.5, inherited) — bootstrap introduces no
  additional side effect of its own.

## Failure Handling

**Startup failures only — the bootstrap layer introduces no retry logic of any kind.**

- **Any exception the composition root's own public contract raises** — whether a `ConfigurationInputError`,
  `ConfigurationWiringError`, or `ConfigurationInternalError` from Phase 1.1's own three tiers, or
  whatever exception a provider factory itself raised through wiring (Phase 1.2/1.3/1.4's own
  Construction-time validation) — propagates through the bootstrap layer to its own caller, completely
  unmodified. Bootstrap never catches, wraps, reinterprets, or logs-and-suppresses any of these.
- **No application instance is created on failure.** There is no partially-ready, degraded, or
  fallback application state — either exactly one application instance now exists, or none does.
- **No retry, no fallback provider, no degraded startup mode.** A startup failure at any tier beneath
  bootstrap is always a hard stop with a named, actionable error, propagated to whatever process-level
  caller started bootstrap — never a silent substitution of some other configuration, never a second
  attempt at composition, and never a retry loop around the composition root's own call. This mirrors
  exactly Phase 1.5's own Failure Handling posture, extended here one layer further out.

## Security Considerations

- **No direct environment or credential access.** The bootstrap layer never reads `os.environ` or opens
  a `.env` file itself, and never receives a raw credential value as an argument or return value
  anywhere in its own call sequence — only the composition root's own call (and, beneath it, Phase
  1.1's own functions) does that, exactly as Phase 1.1's and Phase 1.5's own Security Considerations
  already establish.
- **No credential holding.** The bootstrap layer holds the composition root's own returned
  dependency-object set, but none of those objects carries a raw credential in any field a caller could
  read directly — the same guarantee Phase 1.1 and every provider phase already establish, inherited
  unchanged one layer up.
- **The returned dependency graph is opaque to bootstrap**, in the same way it is opaque to the
  composition root's own caller (Phase 1.5's own Composition Model) — bootstrap inspects nothing about
  the internal shape of any wired adapter or `AgentDependencies` field; it holds and forwards the set as
  a whole.
- **No new credential-handling surface of any kind.** The bootstrap layer neither logs, prints,
  serializes, nor persists any value derived from the composition root's own inputs or outputs, matching
  every prior phase's own "no secret logging"/"no secret serialization"/"no secret persistence"
  guarantees exactly, since the bootstrap layer never possesses a raw secret value to begin with.

## Logging Vocabulary

This section defines the vocabulary available to a bootstrap implementation **if** it emits logs;
exactly like every prior phase's own Logging Vocabulary section, it does not mandate that logging
occur.

This document introduces no new `stage` identifier and no new closed-vocabulary log codes. A bootstrap
implementation calls the composition root's own public contract, which in turn calls Phase 1.1's own
functions, each already owning its own logging vocabulary — extending that vocabulary is Phase 1.1's or
Phase 1.5's own revision path, never this document's.

A bootstrap implementation that wishes to emit its own internal diagnostic information (for example,
"application instance ready" or "startup failed") may do so at DEBUG severity or below, subject to the
same hard constraint stated in Security Considerations: it may never include a resolved raw credential,
any raw configuration value, or any value a prior phase's own Security Considerations already prohibits
from being logged.

## Concurrency

**Startup concurrency only.** Bootstrap happens once per application instance (Application Model),
mirroring Phase 1.1's and Phase 1.5's own "once per process lifetime" framing extended one layer up. The
bootstrap layer introduces no locking, no mutex, and no coordination of its own beyond invoking the
composition root's own public contract exactly once.

Concurrent reads of an already-held application instance's own dependency-object set, by multiple
threads, are inherently safe only to the extent the underlying wired adapters and SDK clients they wrap
are themselves thread-safe (Phase 1.2/1.3/1.4's own Concurrency sections, inherited unchanged) — this
document asserts no concurrency guarantee beyond what those documents already state, and it is
ownership-only: bootstrap is the one place that decides, once, that a given application instance now
exists and may be shared across whatever later concurrent callers a process makes; it does not itself
introduce any synchronization primitive.

## Design Decisions

1. **Bootstrap is a separate layer from composition, not an extension of it.** Phase 1.5's own
   composition root has a single responsibility — assemble a dependency graph. Bootstrap has a
   different single responsibility — decide whether that graph means the application is ready, and hold
   it for the instance's lifetime. Collapsing the two into one layer would blur "producing the graph"
   and "using the graph" into a single concern, exactly the kind of scope creep every prior phase's own
   Non-Responsibilities section is designed to prevent one layer down.

2. **No shutdown contract is invented, stated once, cross-referenced everywhere else.** Given how
   naturally an "application lifetime" document could drift into defining teardown callbacks, disposal
   methods, or a shutdown hook, this document states directly, in Bootstrap Lifecycle alone, that no
   such contract exists anywhere in the frozen repository — Phase 1.5's own Design Decision #5 already
   reaches the same conclusion for the composition root's own held objects. Every other section that
   touches application lifetime (Application Model, Known Limitations) refers back to that one
   statement rather than restating the finding, keeping the document from repeating itself into
   dominating its own structure.

3. **Readiness is defined as an internal concept, never a network probe, because the constraints
   governing this document explicitly exclude any API, CLI, or deployment surface.** A future phase
   that introduces a real process entrypoint or hosting framework may choose to expose readiness through
   a health-check route or similar mechanism, but that choice belongs entirely to that future phase
   (Future Phase Boundaries) — inventing one here would design a deployment concern this document is
   explicitly scoped to exclude.

4. **The bootstrap entrypoint's own name and signature are stated as illustrative, never frozen** — the
   same discipline Phase 1.5 already applies to its own composition entrypoint. No script in the current
   repository defines a bootstrap entrypoint at all; naming one as though it were already established
   would misrepresent the repository's own current state.

5. **Future Phase Boundaries names two categories, not an enumerated list of individually excluded
   surfaces.** Rather than separately reserving a CLI, a REST API, a container runtime, and a cloud
   deployment target as though each were a distinct kind of future work, this document groups every
   process entrypoint, deployment surface, and hosting framework into one deferred category — because
   each shares the identical relationship to this document: each is something that would eventually call
   the bootstrap layer this document already defines, never something this document itself designs.

## Constants

```python
# This document defines no numeric threshold, ceiling, or default of its own. Every constant governing
# configuration, provider behavior, or stage orchestration remains exactly where Phase 1.1 through 1.5
# and Stage 8/13/21 already own it — none of it is duplicated here.
```

No numeric threshold, ceiling, or default belonging to any frozen phase or stage is duplicated here —
every one of them already lives, exactly once, in the document or script that owns it.

## Complexity

- **Composition-root invocation (Bootstrap Lifecycle step [2])** — O(1) from this document's own
  perspective: exactly one call. The actual cost of that call is entirely whatever Phase 1.5's own
  Complexity section already accounts for (O(S) dependency wiring, bounded above by
  `len(SUPPORTED_SEAMS)`), inherited unchanged, never re-estimated here.
- **Readiness decision (step [3])** — O(1), a single success/failure branch.

## Known Limitations

- **No hot-reload, no re-bootstrap.** An application instance's dependency-object set is fixed for its
  own lifetime once composition succeeds; a genuine reconfiguration means starting an entirely new
  process and running this sequence again from step [1] (Bootstrap Lifecycle), producing an entirely new
  instance — inherited unchanged from Phase 1.1's and Phase 1.5's own "no hot-reload" limitation,
  extended here one layer up.
- **No health-check or readiness-probe surface.** Readiness is an internal concept only (Application
  Model); a deployment needing an externally observable readiness signal must build that surface as a
  future, separate phase (Future Phase Boundaries) — this document does not provide one.
- **No multi-instance bootstrap coordination.** This document defines the architecture of one
  application instance's own bootstrap; it says nothing about coordinating multiple instances within one
  process, across processes, or across a cluster — that is explicitly outside this document's scope,
  never assumed here.
- **No composition-root-level disposal, teardown, or shutdown mechanism**, stated as its own limitation
  rather than left as an unstated gap (Bootstrap Lifecycle step [6], Design Decisions #2).

## Future Phase Boundaries

**Bootstrap is the layer immediately above the composition root.** Everything above bootstrap itself —
how a process actually starts, how it is deployed, and how anything outside this document's own scope
invokes the bootstrap layer — is reserved, in exactly two categories:

**Category A — deferred to a future actor.** Every process entrypoint, deployment surface, or hosting
framework that might eventually invoke the bootstrap layer this document defines — a script's own
`__main__`, a command-line interface, a REST or other network-facing API framework, a containerized or
cloud deployment target — is real future work, explicitly reserved for a later, separate phase. Each
would call the bootstrap entrypoint this document already describes by shape; none is designed, named,
or implied here.

**Category B — permanent, frozen-stage prohibitions.** Modifying Stage 8's, Stage 13's, or Stage 21's
own orchestration; modifying Phase 1.1 through Phase 1.5's own contracts; or redesigning any provider's
own adapter contract — each is never performed by any actor, at any future point, by anyone, for the
same reason every prior phase already states: these stages and phases are frozen, permanently.

Every stage from Stage 0 through Stage 21, and Phase 1.1 through Phase 1.5 in full, remain exactly as
independently usable, and exactly as frozen, as they already are today. Phase 2.1 adds the one layer
that decides what the composition root's own output means for the application as a whole — it adds
nothing any of them must call differently, and nothing they must change to receive it.
