# Phase 2.2 — Runtime Orchestration

Stages 0–21, Phase 1.1 (Configuration Layer), Phase 1.2 (LLM Provider Architecture), Phase 1.3
(Embedding Provider Architecture), Phase 1.4 (Planner Provider Architecture), Phase 1.5 (Composition
Root Architecture), and Phase 2.1 (Application Bootstrap Architecture) remain completely frozen;
nothing below proposes any change to existing code or shipped docs. Phase 2.2 defines the architecture
for the **runtime orchestration layer** — how one bootstrapped application instance executes one
complete request using the already-composed dependency graph Phase 2.1's own bootstrap layer already
holds.

**Framing principle, stated once, governing this entire document:** Phase 2.2 describes runtime
orchestration as invoking **the application's frozen public request-processing contract** — the contract
that accepts one request and one set of already-wired dependencies and returns one request result,
never redefined here. At the time this document was written, that contract is realized by Stage 21's
public entrypoint; this document depends only on the existence of the public contract, not on a
particular function name. This document does not name, describe, or depend on any current script's
specific function signature as though this document itself froze it; it builds against the frozen
public request-processing contract exactly as that contract already exists, the same citation discipline
every prior phase already applies to the layer beneath it.

**Provider-neutrality and stage-neutrality, stated once, governing this entire document:** nothing below
depends on which providers are registered, how many seams are configured, or which concrete adapters a
deployment supplies (inherited from Phase 2.1's own posture); nor does anything below depend on what
Stage 21's own internal planning loop decides to do for any particular request. Runtime orchestration's
own architecture is identical regardless of the bootstrapped instance's own composition and regardless
of any one request's own content — it treats both as opaque.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Phase 2.1's own Application Model defines an application instance as the dependency-object set produced
by exactly one successful bootstrap call, held for the lifetime of the process holding it. Phase 2.1
deliberately stops there: it defines what is held, but not what happens when that held instance is
actually used to do work. Holding a dependency graph and executing a request against it are different
concerns, and nothing in Phase 1.1 through Phase 2.1 defines how one request is actually carried out
against an already-bootstrapped instance, in what order the frozen stages beneath it are invoked, or
what a request's own boundaries are. That is the narrow gap Phase 2.2 closes.

Phase 2.2 does not implement anything. It defines: (1) the architecture of the runtime that holds one
bootstrapped application instance across however many requests a process serves; (2) the architecture of
one complete request's own execution lifecycle, from request boundary to request boundary, using that
already-composed dependency graph; and (3) the boundary between runtime orchestration and everything
above it — a process entrypoint, a deployment surface, a hosting framework — none of which this document
designs.

## Scope

Phase 2.2 answers exactly one question — given one already-bootstrapped application instance and one
incoming request, what is the architecture of the execution sequence that turns "an application instance
is ready" into "one request has been completely executed" — and stops there.

It never redesigns dependency injection, composition, or bootstrap — Phase 1.1's own configuration
machinery, Phase 1.5's own composition root, and Phase 2.1's own bootstrap layer are used exactly as
already frozen; runtime orchestration receives the already-bootstrapped application instance as a
finished, opaque object and never re-invokes, re-composes, or re-validates any part of how it came to
exist. It never redesigns any provider — Phase 1.2/1.3/1.4's own adapter architectures are untouched. It
never redesigns any stage's own orchestration — Stage 8, Stage 13, and Stage 21 each remain exclusively
responsible for their own internal sequencing, retry policy, and validation; this document invokes their
already-frozen public contracts and never re-implements what happens inside one. It never designs a
process entrypoint, a command-line interface, a REST or other network-facing API, a hosting framework, a
scheduler, a background worker, or a deployment/container/cloud concern of any kind — each is named only
as deferred future work (Future Phase Boundaries), never designed here.

## Responsibilities

Phase 2.2 shall: define the application runtime lifecycle as the span across which one bootstrapped
application instance is held and made available to however many requests a process executes (Runtime
Model); define the request execution lifecycle as a strictly linear, one-time sequence from request
boundary to request boundary (Request Lifecycle); define runtime's interaction with the bootstrapped
dependency graph as read-only, opaque use — the runtime holds the same instance Phase 2.1's own bootstrap
layer already produced and forwards it into exactly one frozen stage invocation per request, never
inspecting or modifying any of its fields (Runtime Model, Request Lifecycle); define stage invocation
order as invoking exactly one already-frozen, outermost stage entrypoint per request, with every further
stage invocation already sequenced internally by that entrypoint's own frozen contract (Request
Lifecycle, Public Function Contracts); define runtime ownership — what the runtime holds across requests
versus what belongs to one request alone (Runtime Model); define request boundaries — where one request
begins and ends, and that no request shares mutable state with any other (Request Lifecycle); define
runtime determinism inherited from, and never exceeding, what the invoked stage's own Determinism
section already guarantees (Determinism); define runtime failure propagation as propagate-unmodified,
never swallow-and-continue or degrade-and-proceed (Failure Handling); define runtime completion as the
point at which one request's own execution sequence ends, whether by success or by a propagated failure
(Request Lifecycle).

## Non-Responsibilities

Phase 2.2 explicitly does **not** perform, and no future patch to it may silently add without a new
design pass:

- **Composing dependencies.** Assembling the wired dependency-object set is entirely Phase 1.5's own
  composition-root call, invoked once by Phase 2.1's own bootstrap layer (`phase1_5_composition_root.md`
  §Composition Lifecycle; `phase2_1_application_bootstrap.md` §Bootstrap Lifecycle step [2]); runtime
  orchestration never calls the composition root itself, directly or indirectly.
- **Loading configuration.** `load_raw_settings()` and `validate_settings()` are entirely Phase 1.1's own
  frozen functions, invoked only from inside the composition root's own call
  (`phase1_1_configuration_layer.md` §Public Function Contracts); runtime orchestration never reads
  `os.environ`, opens a `.env` file, or constructs an `ApplicationSettings` instance of its own.
- **Registering providers.** Assembling `ProviderRegistration` objects and calling
  `build_provider_registry()` remain entirely inside the composition root's own call
  (`phase1_5_composition_root.md` §Provider Registration); runtime orchestration never supplies, inspects,
  or modifies a registration.
- **Wiring dependencies.** `wire_dependencies()` and `validate_wiring_result()` remain entirely Phase
  1.1's own frozen functions, invoked only from inside the composition root's own call
  (`phase1_1_configuration_layer.md` §Public Function Contracts); runtime orchestration never calls
  either directly.
- **Constructing adapters.** Every concrete adapter (embedding, LLM, planner) is constructed by its own
  provider module's own factory, invoked once by `wire_dependencies()`
  (`phase1_2_llm_provider.md`/`phase1_3_embedding_provider.md`/`phase1_4_planner_provider.md`); runtime
  orchestration never constructs, inspects, or replaces an adapter — it forwards the already-held
  dependency-object set into a frozen stage entrypoint exactly as bootstrap already produced it.
- **Redesigning Stage 8.** Stage 8's own batching, checkpointing, and retry orchestration
  (`scripts/stage8_embedding_generation.py`) is untouched; runtime orchestration never re-implements or
  bypasses it.
- **Redesigning Stage 13.** Stage 13's own retry policy, timeout policy, and validation
  (`scripts/stage13_llm_execution.py`) are untouched; runtime orchestration never re-implements or
  bypasses them.
- **Redesigning Stage 21.** Stage 21's own `PlannerState` machine and public entrypoint
  (`scripts/stage21_agent_planning.py`) are untouched as the current realization of the frozen public
  request-processing contract; runtime orchestration never re-implements, re-sequences, or duplicates
  any part of that contract's own internal sequencing.
- **Redesigning bootstrap.** Phase 2.1's own Bootstrap Lifecycle, Application Model, and readiness
  decision are untouched; runtime orchestration receives one already-bootstrapped application instance as
  a finished input and never re-invokes bootstrap for an instance that already exists.

Phase 2.2 additionally does not: introduce a process entrypoint, a command-line interface, a REST or
other network-facing API, a hosting framework, or any deployment/container/cloud concern (Future Phase
Boundaries); introduce networking of any kind — no socket, no HTTP client, no HTTP server; introduce
scheduling of any kind — no cron, no timer, no queue consumer; introduce background workers of any kind —
no thread pool, no async task, no worker process; introduce batching, streaming, retries beyond what an
invoked stage's own frozen contract already defines, cancellation, or shutdown (Request Lifecycle,
Runtime Model); hold any request-scoped mutable state beyond the span of the one request that created it;
move a responsibility from any frozen phase or stage into this document, or from this document into any
of them.

## Inputs

Two inputs, and nothing else:

- **One already-bootstrapped application instance** — the same held dependency-object set Phase 2.1's
  own bootstrap layer already produces (`phase2_1_application_bootstrap.md` §Outputs, §Application
  Model), received by the runtime as a finished, opaque object. Runtime orchestration never bootstraps
  one itself; it is handed exactly one, already ready, by whatever process-level caller invoked bootstrap
  before invoking runtime.
- **One request, per request-lifecycle invocation** — whatever shape the frozen public
  request-processing contract requires as its own input (as currently realized by Stage 21's own
  contract, this is an `agent_request`-shaped mapping whose structure is validated by that contract's
  own frozen input validation). Runtime orchestration does not itself define, validate, or reshape this
  input beyond forwarding it — the contract's own frozen input validation is the entire extent of
  validation this layer relies on.

No other input exists. No corpus artifact, manifest, vector index, embedding, prompt template, or
cache-store entry is ever read directly by this layer — none of them bears on runtime orchestration
itself, only on whatever the invoked stage's own frozen contract does internally.

## Outputs

- **One request result, per request-lifecycle invocation** — whatever the frozen public
  request-processing contract returns on success (as currently realized by Stage 21's own contract,
  this is an `agent_result`-shaped mapping), forwarded onward unmodified to whatever called runtime
  orchestration for that request. Runtime orchestration introduces no new result shape, no new field,
  and no new wrapper beyond what the contract already returns.
- **A completion outcome** — either the request completed (the invoked stage's own entrypoint returned)
  or the request failed (the invoked stage's own entrypoint raised) — never a third outcome, mirroring
  Phase 2.1's own binary readiness outcome one layer further out.

No file is written by the runtime orchestration layer itself. No new artifact directory is introduced.
There is no manifest interaction of any kind at this layer — the same zero-artifact posture every prior
phase already established, extended here to the layer that executes requests against an already-composed
graph.

## Runtime Model

**One runtime holds one application instance across however many requests a process executes.** The
runtime does not construct, re-construct, or partially replace the held application instance for any
request — it is the same single instance Phase 2.1's own bootstrap layer produced once, forwarded
unmodified into every request the runtime executes for the life of the process, mirroring Phase 2.1's own
"held as a single unit, never partially replaced" posture one layer further out.

**What the runtime owns across requests.** The runtime owns exactly one thing across requests: a
reference to the held application instance. It owns nothing else across requests — no accumulated
state, no request history, no cache, no counter — because nothing in the frozen sources this document
inherits from defines any such cross-request state, and inventing one here would introduce exactly the
kind of undesigned persistence this document's own Non-Responsibilities excludes.

**What belongs to one request alone.** Everything produced or consumed during one request's own
execution — the request input, whatever the invoked stage's own internal call sequence produces, and the
request result — belongs exclusively to that one request. No request shares mutable state with any other
request; each request-lifecycle invocation is independent of every other, using the same held application
instance only as a read-only, opaque input.

**Interaction with the bootstrapped dependency graph.** The runtime never inspects, modifies, or
re-maps any field of the held application instance. It forwards the instance as a whole into exactly one
frozen stage invocation per request (Request Lifecycle), exactly mirroring how Phase 2.1's own bootstrap
layer treats the composition root's own returned dependency-object set as opaque
(`phase2_1_application_bootstrap.md` §Security Considerations, §Read-Only Guarantees) — this document
extends that same opacity discipline one layer further out, from bootstrap-holds-it-opaquely to
runtime-uses-it-opaquely.

**The application boundary, restated one layer further out.** Runtime orchestration is the layer
immediately above bootstrap. Below it is bootstrap (Phase 2.1), which in turn sits above the composition
root (Phase 1.5), Phase 1.1's configuration machinery, and every provider implementation. Above runtime
orchestration is whatever actually receives requests and calls into this layer — a process entrypoint, a
CLI, a hosting framework — none of which is architected by this document or by any prior phase (Future
Phase Boundaries).

## Request Lifecycle

A strictly linear call sequence per request, never a stored, mutable state machine spanning multiple
requests — mirroring Phase 2.1's own Bootstrap Lifecycle reasoning and Phase 1.5's own Composition
Lifecycle, extended here to the request level: nothing in runtime orchestration branches on an external,
non-deterministic decision across requests the way the frozen public request-processing contract's own
internal sequencing does within one request.

```
[1] Request boundary begins   — one request arrives; the runtime holds the already-bootstrapped
      application instance, ready to be forwarded
      │
      ▼
[2] Contract invocation         — the runtime invokes the frozen public request-processing contract
      exactly once, supplying the request input and the held application instance's own relevant
      dependencies (currently realized by Stage 21's own public entrypoint)
      │
      ▼
[3] Completion decision        — if the call returns successfully, its own return value becomes the
      request result, and the request has completed (Outputs); if the call raises, no request result
      exists, and the request has failed — there is no third outcome
      │
      ▼
[4a] Request completed          — the request result is forwarded onward to whatever called runtime
      orchestration for this request                    [4b] Request failed — the raised exception
      │                                                   propagates unmodified
      ▼
[5] Request boundary ends      — the request's own execution ends here; no state from this request
      persists into any later request beyond the runtime's own unchanged reference to the held
      application instance
```

Steps [2]–[4] run at most once per request — the same "at most once, always-forward" posture Phase 1.1's
own Configuration Lifecycle, Phase 1.5's own Composition Lifecycle, and Phase 2.1's own Bootstrap
Lifecycle already state for their own steps, extended here to the request level. Nothing in this
document defines what happens inside step [2] beyond the one call boundary itself — everything the
frozen public request-processing contract does internally (its own further stage invocations, its own
internal sequencing, its own retries) is entirely that contract's own already-frozen responsibility,
never re-described or re-sequenced here. A request that must be executed again is a new request, running this sequence again
from step [1], never resuming or partially reusing a prior request's own state.

## Runtime Validation

Runtime-level validation at this layer is binary and introduces no new tier. Phase 1.1 already defines
three validation tiers (input, wiring-level, internal-invariant); Phase 1.5's own Design Decision #3 and
Phase 2.1's own Startup Validation each already state that no fourth or fifth tier is introduced by the
layers beneath this one. Runtime orchestration introduces no sixth: it observes only whether the one
contract-invocation call (which itself triggers whatever input and invariant validation the frozen public
request-processing contract already performs internally) returned successfully or raised.

There is no partially-completed request state this layer recognizes. Either the stage invocation
succeeded — in which case every validation tier the invoked stage's own contract already performs has
already passed — or it raised, in which case runtime orchestration performs no further validation of its
own and no request result exists. Runtime orchestration does not re-check, sample, or spot-verify
anything about the returned request result; trusting the invoked stage's own already-frozen guarantee is
the entire extent of this layer's own validation posture, mirroring exactly how Phase 2.1's own Startup
Validation trusts the composition root's own already-frozen guarantee one layer down.

## Public Function Contracts

The runtime layer's own entrypoint is described here only by shape — inputs, outputs, ordering,
ownership — never by a mandated, frozen name, exactly mirroring how Phase 2.1 itself treats its own
bootstrap entrypoint and how Phase 1.5 treats its own composition entrypoint. No script in the current
repository defines a runtime-orchestration entrypoint of any kind; any function name that might
illustrate this section is illustrative only, and this document does not mandate one.

- **The illustrative runtime entrypoint** — takes, per invocation, the held application instance and one
  request's own input (Inputs); internally invokes the outermost already-frozen stage entrypoint exactly
  once (Request Lifecycle step [2]); on success, returns that entrypoint's own return value as the
  request result (Outputs); on failure, allows whatever exception the invoked stage's own contract raised
  to propagate unmodified (Failure Handling) — never catching, wrapping, or reinterpreting it.
- **The outermost frozen stage entrypoint** — restated here only to name runtime orchestration's own
  obligation against it: call it exactly once per request, after assembling whatever inputs its own
  already-frozen contract requires, and treat its return value opaquely — runtime orchestration never
  inspects the internal shape of the returned result beyond forwarding it as a whole.

No function architected under this document ever imports a provider SDK directly, ever reads
`os.environ` or opens a `.env` file directly (those remain exclusively inside the composition root's own
call, inherited unchanged through bootstrap), ever opens a network socket itself, or ever calls a Stage
8, Stage 13, or any other stage's own entrypoint other than the single outermost one this layer is
architected to invoke.

## Determinism

**Deterministic (guaranteed, given identical input):**

- **Whether a request completes or fails**, given an identical request input and an identical held
  application instance — a pure consequence of whatever the invoked stage's own Determinism guarantees
  already state for its own entrypoint, inherited unchanged one layer up.
- **The completion decision itself** — a fixed, binary function of whether the one stage-invocation call
  raised or returned: given an identical outcome from that call, runtime orchestration's own completion
  decision is identical every time.

**Explicitly NOT deterministic (inherent to the sources this layer invokes; never assumed, never
hidden):**

- **Whatever the frozen public request-processing contract does internally** — planner-adapter
  invocations, tool executions, and any non-determinism Phase 1.2/1.3/1.4's own Determinism sections
  already name for the adapters the contract internally calls — is entirely inherited, never introduced
  or hidden by this layer. Runtime orchestration treats the contract's own invocation as an opaque unit
  and inherits whatever non-determinism already exists inside it.
- **Ordering across independent requests.** This document defines the lifecycle of one request; it makes
  no guarantee about the relative ordering, interleaving, or timing of independent requests against the
  same held application instance — that is a property of whatever future actor invokes this layer
  (Future Phase Boundaries), never guaranteed here.

## Read-Only Guarantees

- The runtime orchestration layer never modifies `manifest.json`, any corpus artifact, any vector index,
  any embedding, any prompt template, or any cache store entry directly — it has no relationship to any
  of them at all; only whatever the invoked stage's own frozen contract does internally may touch any of
  these, exactly as that stage's own architecture already governs.
- The runtime orchestration layer never modifies the held application instance for any request — it
  forwards the same reference, unchanged, into every request's own stage invocation, never mutating any
  field of it independently.
- The runtime orchestration layer holds no module-level mutable state of its own beyond the one held
  reference to the application instance, mirroring Phase 1.1's, Phase 1.5's, and Phase 2.1's own Design
  Decision #1 posture — every request result it produces is returned to whatever caller invoked runtime
  orchestration for that request, which is solely responsible for whatever it does with that result.
- The only external side effects the runtime orchestration layer's own call sequence performs are exactly
  the ones the invoked stage's own contract already performs (inherited); runtime orchestration
  introduces no additional side effect of its own.

## Failure Handling

**Request-level failures only — the runtime orchestration layer introduces no retry logic of its own
beyond whatever an invoked stage's own frozen contract already defines internally.**

- **Any exception the frozen public request-processing contract raises** — whether a typed exception
  defined by that contract's own layer (as currently realized, Stage 21's own
  `AgentPlanningInputError`/`AgentPlanningInternalError`/`PlannerInvocationError`), or any exception
  originating further down through whatever the contract internally invokes — propagates through the
  runtime orchestration layer to its own caller, completely unmodified. Runtime orchestration never
  catches, wraps, reinterprets, or logs-and-suppresses any of these.
- **No request result exists on failure.** There is no partially-completed, degraded, or fallback
  request outcome — either exactly one request result now exists, or none does.
- **No retry, no fallback stage, no degraded execution mode, introduced by this layer.** A request
  failure at any tier beneath runtime orchestration is always a hard stop with a named, actionable error,
  propagated to whatever caller invoked runtime orchestration for that request — never a silent
  substitution of some other stage, never a second attempt at the same request, and never a retry loop
  around the invoked stage's own entrypoint. Any retry that does occur (for example, Stage 13's own
  frozen retry policy around a transient LLM error) is entirely internal to the invoked stage's own
  already-frozen contract, never duplicated or re-triggered by this layer.
- **One failed request never affects any other request.** Because no request shares mutable state with
  any other (Runtime Model), a failure in one request's own execution has no bearing on the held
  application instance itself or on any other request executed against it.

## Security Considerations

- **No direct environment or credential access.** The runtime orchestration layer never reads
  `os.environ` or opens a `.env` file itself, and never receives a raw credential value as an argument or
  return value anywhere in its own call sequence — only the composition root's own call, inherited
  through bootstrap, does that, exactly as Phase 1.1's, Phase 1.5's, and Phase 2.1's own Security
  Considerations already establish.
- **No credential holding.** The runtime orchestration layer holds a reference to the same
  dependency-object set bootstrap already holds, but none of those objects carries a raw credential in
  any field a caller could read directly — the same guarantee every prior phase already establishes,
  inherited unchanged two layers up.
- **The held application instance and every request result remain opaque to this layer**, in the same
  way the returned dependency graph is opaque to bootstrap's own caller (Phase 2.1's own Application
  Model) — runtime orchestration inspects nothing about the internal shape of any wired adapter, any
  `AgentDependencies` field, or any request result beyond forwarding each as a whole.
- **No new credential-handling surface of any kind.** The runtime orchestration layer neither logs,
  prints, serializes, nor persists any value derived from the held application instance or from any
  request's own input or output, matching every prior phase's own "no secret logging"/"no secret
  serialization"/"no secret persistence" guarantees exactly, since this layer never possesses a raw secret
  value to begin with.
- **No new network-facing surface.** This document introduces no socket, no listener, and no
  network-facing entrypoint of any kind (Scope, Non-Responsibilities); nothing about request handling at
  this layer expands the security surface established by any frozen phase beneath it.

## Logging Vocabulary

This section defines the vocabulary available to a runtime-orchestration implementation **if** it emits
logs; exactly like every prior phase's own Logging Vocabulary section, it does not mandate that logging
occur.

This document introduces no new `stage` identifier and no new closed-vocabulary log codes. A runtime
implementation calls the outermost already-frozen stage entrypoint, which in turn owns its own already-
established logging vocabulary (and, beneath it, whatever Phase 1.1 and Phase 1.5's own vocabularies
already define) — extending any of those vocabularies is that layer's own revision path, never this
document's.

A runtime implementation that wishes to emit its own internal diagnostic information (for example,
"request completed" or "request failed") may do so at DEBUG severity or below, subject to the same hard
constraint stated in Security Considerations: it may never include a resolved raw credential, any raw
configuration value, any raw request content beyond what a prior phase's own Security Considerations
already permits, or any value a prior phase's own Security Considerations already prohibits from being
logged.

## Concurrency

**Request concurrency only.** The runtime holds one application instance across however many requests a
process executes (Runtime Model); this document defines the architecture of one request's own execution
lifecycle, and states no guarantee about whether multiple requests may execute concurrently against the
same held instance — that determination depends entirely on whether the held instance's own wired
adapters and SDK clients are themselves thread-safe (Phase 1.2/1.3/1.4's own Concurrency sections,
inherited unchanged, exactly as Phase 2.1's own Concurrency section already states for concurrent reads
of the held instance).

The runtime orchestration layer introduces no locking, no mutex, and no coordination of its own beyond
invoking, per request, the outermost already-frozen stage entrypoint. It asserts no concurrency guarantee
beyond what the frozen sources beneath it already state, and it is ownership-only: the runtime is the one
place that forwards an already-existing, already-ready application instance into however many concurrent
or sequential request invocations a future actor makes; it does not itself introduce any synchronization
primitive, and it defines no scheduling, batching, or background-execution behavior of any kind (Scope,
Non-Responsibilities).

## Design Decisions

1. **Runtime orchestration is a separate layer from bootstrap, not an extension of it.** Phase 2.1's own
   bootstrap layer has a single responsibility — decide whether a composed graph means the application is
   ready, and hold it. Runtime orchestration has a different single responsibility — use that already-held
   graph to execute requests. Collapsing the two into one layer would blur "becoming ready once" and
   "executing many times" into a single concern, exactly the kind of scope creep every prior phase's own
   Non-Responsibilities section is designed to prevent one layer down.

2. **Exactly one frozen public request-processing contract is invoked per request, never several
   independently sequenced calls.** The frozen public request-processing contract already internally
   sequences every further call that request execution needs — inventing a second, parallel invocation
   order at the runtime-orchestration layer would duplicate ownership the contract already holds
   exclusively. Stage 21 is the current realization of that contract, and its own internal sequencing
   (into `handle_request`, `select_memory`, `append_turn`, `execute_tool`, and the planner adapter)
   already demonstrates this ownership. This mirrors exactly how Phase 2.1's own bootstrap layer invokes
   the composition root's own single public contract rather than re-invoking Phase 1.1's own four
   functions itself.

3. **No shutdown, cancellation, retry, batching, or streaming contract is invented at this layer,
   because no frozen source defines one and the user's own constraints explicitly exclude each.** Given
   how naturally a "request execution" document could drift into defining a cancellation token, a retry
   wrapper, or a streaming response shape, this document states directly, in Scope and Non-
   Responsibilities, that none of these exist here — exactly one request lifecycle is defined, matching
   Phase 2.1's own "no shutdown contract is invented" discipline one layer further out.

4. **Runtime ownership is deliberately minimal — a single held reference, nothing more.** A runtime layer
   could plausibly accumulate request history, metrics, or caches across requests; this document
   deliberately does not, because no frozen source this document inherits from defines any such
   cross-request state, and inventing one here would introduce exactly the kind of undesigned persistence
   Phase 1.1's and Phase 1.5's own Design Decision #1 already warn against one layer down.

5. **Future Phase Boundaries names two categories, not an enumerated list of individually excluded
   surfaces**, exactly mirroring Phase 2.1's own Design Decision #5 — because each deferred concern (a
   CLI, a REST API, a scheduler, a background worker, a deployment target) shares the identical
   relationship to this document: each is something that would eventually call the runtime-orchestration
   layer this document already defines, never something this document itself designs.

## Constants

```python
# This document defines no numeric threshold, ceiling, or default of its own. Every constant governing
# configuration, provider behavior, or stage orchestration (including Stage 13's own retry/timeout
# ceilings and Stage 21's own DEFAULT_MAX_PLAN_STEPS/MAX_PLAN_STEPS) remains exactly where Phase 1.1
# through 2.1 and Stage 8/13/21 already own it — none of it is duplicated here.
```

No numeric threshold, ceiling, or default belonging to any frozen phase or stage is duplicated here —
every one of them already lives, exactly once, in the document or script that owns it.

## Complexity

- **Contract invocation (Request Lifecycle step [2])** — O(1) from this document's own perspective:
  exactly one call. The actual cost of that call is entirely whatever the frozen public
  request-processing contract's own Complexity already accounts for (bounded by whatever ceiling that
  contract defines internally), inherited unchanged, never re-estimated here.
- **Completion decision (step [3])** — O(1), a single success/failure branch.
- **Runtime holding cost across requests** — O(1) per request: the runtime forwards the same held
  reference into every request without copying, re-composing, or re-validating the application instance.

## Known Limitations

- **No cancellation.** A request, once its stage invocation begins, runs to completion or to a raised
  exception; this document defines no mechanism to cancel a request already in progress — inherited as an
  explicit omission from this document's own Scope, never assumed to exist.
- **No streaming.** A request result is returned only once the invoked stage's own entrypoint has fully
  returned; this document defines no partial or incremental result delivery.
- **No batching.** Each request-lifecycle invocation executes exactly one request; this document defines
  no mechanism for submitting or executing multiple requests as a single unit.
- **No cross-request state beyond the held application instance.** No request history, metrics, or cache
  persists across requests at this layer (Runtime Model, Design Decisions #4) — a future phase that needs
  any of these must design it separately, never assumed here.
- **No concurrency guarantee beyond what the held instance's own wired adapters already provide.** This
  document asserts no additional thread-safety or isolation guarantee of its own (Concurrency).
- **No health-check, readiness, or liveness surface.** Exactly as Phase 2.1's own Known Limitations
  already states for bootstrap-level readiness, this document defines no externally observable signal for
  runtime-level health — a deployment needing one must build that surface as a future, separate phase
  (Future Phase Boundaries).

## Future Phase Boundaries

**Runtime orchestration is the layer immediately above bootstrap.** Everything above runtime
orchestration itself — how a process actually receives requests, how it is deployed, and how anything
outside this document's own scope invokes the runtime layer — is reserved, in exactly two categories:

**Category A — deferred to a future actor (future runtime capabilities).** Streaming execution, request
cancellation, background execution, scheduling, concurrent-request coordination beyond what the held
instance's own adapters already provide, observability, metrics, and tracing are each real future work,
explicitly reserved for a later, separate phase. Each would extend or wrap the request-lifecycle
architecture this document already defines; none is designed, named, or implied here.

**Category B — outside runtime orchestration entirely.** A command-line interface, a REST API, FastAPI,
gRPC, deployment, Docker, Kubernetes, or cloud hosting of any kind is never designed by this document, at
any future point, by anyone reading it as though it were — each is a separate, future concern that would
eventually call the runtime-orchestration entrypoint this document already describes by shape, never
something this document itself becomes.

Every stage from Stage 0 through Stage 21, Phase 1.1 through Phase 1.5 in full, and Phase 2.1 in full,
remain exactly as independently usable, and exactly as frozen, as they already are today. Phase 2.2 adds
the one layer that decides how a held application instance is used to execute one request — it adds
nothing any of them must call differently, and nothing they must change to receive it.
