# Phase 2.3 — Request Observability

Stages 0–21, Phase 1.1 (Configuration Layer), Phase 1.2 (LLM Provider Architecture), Phase 1.3
(Embedding Provider Architecture), Phase 1.4 (Planner Provider Architecture), Phase 1.5 (Composition
Root Architecture), Phase 2.1 (Application Bootstrap Architecture), and Phase 2.2 (Runtime Orchestration
Architecture) remain completely frozen; nothing below proposes any change to existing code or shipped
docs. Phase 2.3 defines the architecture for the **request observability layer** — how one request's own
execution, already fully defined by Phase 2.2's own Request Lifecycle, is *observed* (timing, outcome,
identity) without altering how it executes.

**Framing principle, stated once, governing this entire document:** Phase 2.3 describes observability as
a read-only observer of Phase 2.2's own per-request call boundary (`phase2_2_runtime_orchestration.md`
§Request Lifecycle steps [1]–[5]). The observer never participates in the completion decision, never
touches the request or result content, and never introduces a new validation, retry, or failure-handling
tier. It watches the boundary; it does not move it.

**Provider-neutrality and stage-neutrality, stated once, governing this entire document:** nothing below
depends on which providers are registered, which concrete adapters a deployment supplies, or what any
invoked stage's own internal planning loop decides for any particular request — inherited unchanged from
Phase 2.2's own posture.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Phase 2.2's own Request Lifecycle defines a strictly linear, one-time sequence per request — request
boundary begins, the frozen public request-processing contract is invoked exactly once, a completion
decision is made, and the request boundary ends. Phase 2.2 deliberately stops there: it defines how a
request executes, but not how that execution is observed by anything outside the request itself. Nothing
in Phase 1.1 through Phase 2.2 defines what it means to know, after the fact, that a request happened,
how long it took, or whether it succeeded or failed — without altering the request's own outcome. That is
the narrow gap Phase 2.3 closes.

Phase 2.3 does not implement anything. It defines: (1) what is observed about one request's own
execution (Responsibilities); (2) who owns the correlation identity and the resulting observation record
(Observability Model); and (3) the boundary between observing a request and participating in it — this
document never becomes a second decision-maker about whether a request succeeded or failed.

## Scope

Phase 2.3 answers exactly one question — given one request already executing under Phase 2.2's own
frozen Request Lifecycle, what is the architecture of observing that execution's timing, outcome, and
identity — and stops there.

It never redesigns Phase 2.2's own Request Lifecycle, Runtime Model, or Failure Handling — the runtime
orchestration layer's own entrypoint, call count, and exception-propagation behavior are used exactly as
already frozen; the observer wraps a call to that entrypoint and never alters what the entrypoint itself
does. It never redesigns any frozen phase or stage beneath Phase 2.2. It never defines an emission target,
transport, or backend for an observation record — no log sink, no metrics exporter, no tracing backend, no
dashboard — each is named only as deferred future work (Future Phase Boundaries), never designed here. It
never defines an error-isolation, exception-swallowing, fallback, or buffering mechanism between
observation and request execution — no frozen source defines one today, and this document does not
introduce one silently.

## Responsibilities

Phase 2.3 shall: define what is observed about one request's own execution — request start, request end,
completion outcome (completed or failed), duration, and a per-request correlation identity — and nothing
about the request's or result's own content (Outputs); define correlation-identity ownership explicitly
as the observer's own responsibility to generate, never left implicit (Observability Model); define
observation-record ownership explicitly — who constructs it, its immutability, and that neither runtime
orchestration nor bootstrap ever holds, mutates, or reads it back (Observability Model); define the
observation lifecycle as a strictly linear sequence aligned to Phase 2.2's own Request Lifecycle, never a
second, independent state machine (Observation Lifecycle); define observation as non-authoritative and
non-participatory in the request's own completion decision (Failure Handling); define record production,
as distinct from record delivery, as this document's own boundary — whether a produced record is logged,
exported, buffered, or discarded is explicitly out of scope (Observability Model, Future Phase
Boundaries).

## Non-Responsibilities

Phase 2.3 explicitly does **not** perform, and no future patch to it may silently add without a new
design pass:

- **Redesigning Phase 2.2's Request Lifecycle.** The runtime orchestration layer's own entrypoint, its
  exactly-once contract invocation, and its completion decision (`phase2_2_runtime_orchestration.md`
  §Request Lifecycle) are untouched; the observer wraps a call to that entrypoint and never alters its
  own behavior, call count, or exception identity.
- **Redesigning Phase 2.2's Failure Handling.** Every exception the frozen public request-processing
  contract raises continues to propagate through runtime orchestration completely unmodified
  (`phase2_2_runtime_orchestration.md` §Failure Handling); the observer never catches, wraps, suppresses,
  or reinterprets any exception on the wrapped call's behalf.
- **Introducing streaming or partial result delivery.** A request result remains returned only once,
  in full, exactly as Phase 2.2 already defines (Request Lifecycle); this document never redefines that
  into an incremental or streamed shape.
- **Introducing request cancellation.** A request, once its stage invocation begins, runs to completion
  or to a raised exception, exactly as Phase 2.2 already states (Known Limitations); this document
  introduces no mechanism to interrupt a request already in progress.
- **Introducing scheduling or background execution.** The observer's own call sequence is synchronous
  and blocking, exactly mirroring Phase 2.2's own posture; no thread, no async task, no deferred
  execution, no queue.
- **Introducing retry logic of any kind.** Neither around the wrapped runtime call nor around the
  observer's own record production.
- **Introducing an error-isolation, exception-swallowing, fallback, or buffering mechanism.** No frozen
  source anywhere in this repository defines a mechanism that isolates one component's own failure from
  another's; this document does not invent one for observation failures. What happens if the observer's
  own logic raises is explicitly undefined here (Failure Handling, Future Phase Boundaries).
- **Defining an emission target, transport, or backend.** Whether an observation record is logged,
  exported to a metrics system, sent to a tracing backend, or discarded is never decided by this
  document (Future Phase Boundaries).
- **Redesigning any frozen phase or stage.** Stage 8, Stage 13, Stage 21, Phase 1.1 through 1.5, and
  Phase 2.1 remain exactly as frozen as they already are; this document adds a layer that watches Phase
  2.2's own call boundary and touches nothing beneath it.

Phase 2.3 additionally does not: introduce a process entrypoint, a command-line interface, a REST or
other network-facing API, a hosting framework, or any deployment/container/cloud concern (Future Phase
Boundaries); introduce a health-check, metrics, or tracing network surface; hold any request-scoped
mutable state beyond the span of the one request that produced it; move a responsibility from any frozen
phase or stage into this document, or from this document into any of them.

## Inputs

The same two inputs Phase 2.2 already names, observed rather than consumed:

- **One already-bootstrapped application instance**, forwarded opaquely into the wrapped runtime call,
  exactly as Phase 2.2 already receives it. The observer never inspects any field of it.
- **One request, per request-lifecycle invocation**, forwarded opaquely into the wrapped runtime call.
  The observer never inspects, validates, or reshapes the request's own content — it observes only that a
  request began and, later, that it ended.

No other input exists. No corpus artifact, manifest, vector index, embedding, prompt template, or
cache-store entry is ever read by this layer.

## Outputs

- **One observation record, per request-lifecycle invocation** — shape only, illustrative: a correlation
  identity (per Observability Model), a completion outcome (completed or failed — never a third value,
  mirroring Phase 2.2's own binary outcome one layer further out), and a duration. The record never
  contains the request's own content, the result's own content, or any credential.
- **No modification to the request result or to any exception the wrapped call raises.** The observer
  never alters what its caller ultimately receives from the wrapped runtime call — the underlying result
  or exception passes through completely unchanged (Failure Handling).

No file is written by the request observability layer itself. No new artifact directory is introduced.
There is no manifest interaction of any kind — the same zero-artifact posture every prior phase already
established.

## Observability Model

**Correlation-identity ownership, stated explicitly, never left implicit.** The observer itself
generates the per-request correlation identity. Nothing in the frozen architecture beneath Phase 2.3 —
not the caller, not runtime orchestration, not bootstrap — currently produces or carries one; this
document does not silently assign that responsibility to any of them. A future phase may instead choose
to accept a caller-supplied identity, but that is a future phase's own design choice, not this document's
own posture.

**Observation-record ownership, stated explicitly.** The observer alone constructs the record, and it is
immutable once produced. The observer's own responsibility ends at the record's production; it does not
retain the record beyond producing it, and neither runtime orchestration nor bootstrap ever holds,
mutates, or reads it back — both remain exactly as frozen, unaware that observation occurred.

**Production, not delivery.** Phase 2.3 owns the production of observation records. Whether a produced
record is logged, exported, buffered, or ignored is a future phase's own decision (Future Phase
Boundaries), never this document's.

**What is owned across requests.** The observer owns nothing across requests beyond whatever mechanism it
uses to generate a fresh correlation identity per call — no accumulated history, no counter beyond that,
no cache — mirroring Phase 2.2's own "single held reference, nothing more" minimalism one layer further
out.

## Observation Lifecycle

A strictly linear sequence aligned to Phase 2.2's own Request Lifecycle, never a second, independent
state machine:

```
[1] Request boundary begins    — inherited unchanged from Phase 2.2's own step [1]
      │
      ▼
[2] Observation starts          — the observer generates a fresh correlation identity for this request
      │
      ▼
[3] Contract invocation          — Phase 2.2's own runtime entrypoint is invoked exactly once, completely
      unchanged; the observer neither wraps this call in a try/except of its own nor alters its inputs
      │
      ▼
[4] Completion decision          — inherited unchanged from Phase 2.2's own step [3]; the observer
      participates in no part of this decision
      │
      ▼
[5] Observation record produced  — an immutable record is produced, carrying the correlation identity,
      the completion outcome, and the duration; the underlying result or exception continues onward to
      the observer's own caller completely unmodified
      │
      ▼
[6] Request boundary ends        — inherited unchanged from Phase 2.2's own step [5]
```

Steps [2] and [5] are this document's own addition; steps [1], [3], [4], and [6] are Phase 2.2's own
steps, restated here only to show where observation attaches, never redefined.

## Runtime Validation

Validation at this layer is binary and introduces no new tier. Phase 1.1 through Phase 2.2 already
establish that no fourth, fifth, or sixth validation tier exists beneath this layer. Phase 2.3 introduces
no seventh: it observes only whether the wrapped call (step [3]) returned or raised — the same binary
observation Phase 2.2 itself already makes, watched rather than re-decided.

## Public Function Contracts

The observer's own entrypoint is described here only by shape — inputs, outputs, ordering, ownership —
never by a mandated, frozen name, exactly mirroring how every prior phase treats its own entrypoint. No
script in the current repository defines a request-observability entrypoint of any kind; any function
name that might illustrate this section is illustrative only, and this document does not mandate one.

- **The illustrative observer entrypoint** — takes, per invocation, the same inputs Phase 2.2's own
  runtime entrypoint takes (Inputs); internally invokes that entrypoint exactly once, unmodified
  (Observation Lifecycle step [3]); on either outcome, produces exactly one observation record
  (Observation Lifecycle step [5]); returns the underlying result, or allows the underlying exception to
  propagate, completely unchanged from what the wrapped call itself produced.
- **The wrapped runtime entrypoint** — restated here only to name Phase 2.3's own obligation against it:
  call it exactly once per request, with its inputs unmodified, and treat its return value and any raised
  exception as opaque and authoritative — the observer never overrides, reinterprets, or second-guesses
  either.

No function architected under this document ever imports a provider SDK directly, ever reads
`os.environ` or opens a `.env` file directly, ever opens a network socket itself, or ever calls a Stage 8,
Stage 13, or Stage 21 entrypoint directly — it calls only the single wrapped runtime entrypoint Phase 2.2
already defines.

## Determinism

Stated as three distinct claims, never collapsed into one:

- **Deterministic record structure.** The observation record's own shape and field set are fixed and
  identical for every request, regardless of that request's own content or outcome.
- **Deterministic lifecycle ordering.** The relative order of the six Observation Lifecycle steps is
  identical for every request — observation always starts before the wrapped call and always produces a
  record after it, never interleaved differently.
- **Non-deterministic measurements.** The timing *values* recorded (duration) vary by nature, exactly as
  wall-clock measurement always does; this is a property of measurement itself, not of this document's own
  architecture, and must not be read as meaning Phase 2.3 itself is non-deterministic. Whatever the wrapped
  call's own Determinism section already states (Phase 2.2, inherited) about the request's own outcome is
  unaffected by, and unrelated to, this distinction.

## Read-Only Guarantees

- The request observability layer never modifies `manifest.json`, any corpus artifact, any vector index,
  any embedding, any prompt template, or any cache store entry — it has no relationship to any of them.
- The request observability layer never modifies the held application instance, the request, or the
  request result — it observes the boundary around the wrapped call and produces a separate record; it
  never mutates anything the wrapped call itself touches.
- The request observability layer holds no module-level mutable state of its own beyond whatever
  mechanism generates a fresh correlation identity per call, mirroring every prior phase's own Design
  Decision #1 posture.
- The only external side effect this layer's own call sequence performs, beyond producing one observation
  record, is exactly whatever the wrapped runtime call itself already performs (inherited).

## Failure Handling

**Observation is non-authoritative and non-participatory in the request's own completion decision.**

- **The wrapped runtime call's own outcome is authoritative and unmodified.** Whatever the wrapped call
  returns or raises passes through this layer completely unchanged — the observer never catches, wraps,
  suppresses, retries, or reinterprets it.
- **What happens if the observer's own logic raises is explicitly undefined by this document.** No frozen
  source anywhere in this repository defines an error-isolation, exception-swallowing, fallback, or
  buffering mechanism today, and this document does not invent one. Stating "an observation failure never
  affects request execution" would require exactly such a mechanism to exist; since none does, this
  document makes no such claim. Any mechanism that isolates an observation failure from request execution
  is explicitly reserved for a later phase (Future Phase Boundaries).
- **No retry, no fallback record, no degraded observation mode.** If a record cannot be produced, no
  record exists for that request — there is no partial or reconstructed record.

## Security Considerations

- **No direct environment or credential access.** The request observability layer never reads
  `os.environ` or opens a `.env` file itself, and never receives a raw credential value anywhere in its
  own call sequence.
- **No credential holding.** The observer never inspects the held application instance's own fields; it
  forwards the instance opaquely into the wrapped call, exactly as Phase 2.2 itself does.
- **No request or result content in observation records.** An observation record carries only a
  correlation identity, a completion outcome, and a duration — never the request's own content, the
  result's own content, or any value derived from either.
- **No new credential-handling or content-handling surface of any kind.** The request observability layer
  neither logs, prints, serializes, nor persists any value derived from the request's or result's own
  content, matching every prior phase's own "no secret logging" guarantee exactly.

## Logging Vocabulary

This section defines the vocabulary available to a request-observability implementation **if** it emits
logs; exactly like every prior phase's own Logging Vocabulary section, it does not mandate that logging
occur.

This document introduces no new `stage` identifier and no new closed-vocabulary log codes beyond what an
observation record's own fields already name (correlation identity, outcome, duration). A request-
observability implementation that wishes to emit its own internal diagnostic information may do so at
DEBUG severity or below, subject to the same hard constraint stated in Security Considerations.

## Concurrency

**Request concurrency only, inherited unchanged from Phase 2.2.** Each observation is scoped to one
request; this document introduces no locking, no mutex, and no coordination of its own beyond generating
one correlation identity and producing one record per request. It asserts no concurrency guarantee beyond
what Phase 2.2's own Concurrency section already states for the wrapped call.

## Design Decisions

1. **Observability is additive, never a new validation or retry tier.** A request-observability document
   could plausibly drift into re-deciding whether a request succeeded, or into retrying a failed
   observation; this document deliberately does not, because doing either would duplicate ownership Phase
   2.2 already holds exclusively over the completion decision, or invent a retry tier no frozen source
   defines.

2. **Correlation-identity and observation-record ownership are assigned explicitly to the observer,
   never left implicit.** Every prior phase in this repository states ownership explicitly for every
   object it names; this document follows the same discipline rather than allowing "who generates the
   identity" or "who holds the record" to remain an assumption a future reader might resolve differently.

3. **No error-isolation mechanism is invented, because none exists in the frozen architecture today.**
   It would be tempting to state that an observation failure never affects request execution, but no
   frozen source defines any mechanism that would make that true. This document instead states
   observation as non-authoritative and non-participatory, and defers the question of isolating an
   observation failure to a later phase — preserving today's architecture rather than silently assuming a
   mechanism into existence.

4. **Record content excludes request/result payloads by design.** An observation record's purpose is to
   answer "did this request happen, and how did it go" — not to duplicate the request or result. Limiting
   record content to correlation identity, outcome, and duration keeps this layer's own security posture
   identical to every prior phase's "no secret, no payload" guarantee.

5. **Future Phase Boundaries names two categories, not an enumerated list of individually excluded
   surfaces**, exactly mirroring every prior phase's own convention.

## Constants

```python
# This document defines no numeric threshold, ceiling, or default of its own. Every constant governing
# configuration, provider behavior, or stage orchestration remains exactly where Phase 1.1 through 2.2
# and Stage 8/13/21 already own it — none of it is duplicated here.
```

No numeric threshold, ceiling, or default belonging to any frozen phase or stage is duplicated here.

## Complexity

- **Observation start (step [2])** — O(1): generating one correlation identity.
- **Contract invocation (step [3])** — O(1) from this document's own perspective, exactly one call; the
  actual cost is entirely whatever Phase 2.2's own Complexity section already accounts for, inherited
  unchanged.
- **Observation record production (step [5])** — O(1): constructing one fixed-shape record.

## Known Limitations

- **No metrics aggregation, exporter, or dashboard.** This document defines only the production of one
  record per request; what happens to that record afterward is explicitly out of scope.
- **No error-isolation mechanism between observation and request execution.** Named here as its own
  stated limitation rather than left as an unstated gap (Failure Handling, Design Decisions #3).
- **No tracing-backend integration.** Correlation identity is defined only as a per-request value this
  document produces; propagating it to any distributed-tracing system is a future phase's own concern.
- **No caller-supplied correlation identity.** This document defines observer-generated identity only; a
  future phase may choose to accept one from a caller instead, but that is not this document's own
  posture (Observability Model).

## Future Phase Boundaries

**Request observability is a layer that watches Phase 2.2's own call boundary, never a layer above it in
the same sense runtime orchestration sits above bootstrap.** Everything beyond producing one observation
record per request is reserved, in exactly two categories:

**Category A — deferred to a future actor (future observability capabilities).** Record aggregation,
metrics exporters, tracing-backend integration, dashboards, caller-supplied correlation identity, and any
mechanism that isolates an observation failure from request execution are each real future work,
explicitly reserved for a later, separate phase. Each would consume or extend the observation record this
document already defines by shape; none is designed, named, or implied here.

**Category B — outside request observability entirely.** A command-line interface, a REST API, FastAPI,
gRPC, deployment, Docker, Kubernetes, or cloud hosting of any kind is never designed by this document, at
any future point, by anyone reading it as though it were — each is a separate, future concern.

Every stage from Stage 0 through Stage 21, Phase 1.1 through Phase 1.5 in full, and Phase 2.1 and Phase
2.2 in full, remain exactly as independently usable, and exactly as frozen, as they already are today.
Phase 2.3 adds a layer that watches one request's own execution — it adds nothing any of them must call
differently, and nothing they must change to receive it.
