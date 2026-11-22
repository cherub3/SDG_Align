# Phase 2.1 — Application Bootstrap: Implementation Plan

This is a planning document only. It contains no implementation code, no pseudocode, and no test
code. It describes how the frozen architecture at
`docs/architecture/phase2_1_application_bootstrap.md` would be implemented, so that the implementation
itself can be reviewed and approved before any code is written.

## 1. Executive Summary

**Objective.** Implement the bootstrap layer Phase 2.1 already architects: a thin, one-call layer that
invokes the composition root's public contract exactly once, makes a binary readiness decision, holds
the returned dependency-object set for the lifetime of one application instance, and propagates any
startup failure unmodified.

**Scope.** One new module providing (a) a way to represent and hold "one application instance" as a
single unit, and (b) a bootstrap entrypoint function that performs the one composition-root call, the
readiness decision, and the failure-propagation behavior Phase 2.1 defines. Nothing else. No provider
work, no configuration work, no composition-root work, no Stage work.

**Architectural assumptions.**
- The current repository's composition-root implementation is used without modification. Re-reading
  `scripts/composition_root.py` for this plan confirms `compose_application(registrations, env=None,
  dotenv_path=None)` already accepts a deployment-supplied `registrations` sequence, already returns
  the dependency-object set Phase 1.5 describes, and already raises Phase 1.1's three configuration
  exception types unmodified on failure. This implementation plan builds the bootstrap layer directly
  against this existing function, calling it exactly as it exists today.
- Phase 1.1's three exception types (`ConfigurationInputError`, `ConfigurationWiringError`,
  `ConfigurationInternalError`) and the dependency-object shapes Phase 1.5 already defines
  (`AgentDependencies`, the wired adapters, the retrieval closures) are used exactly as frozen — the
  bootstrap layer neither redefines nor wraps any of them.
- **This phase implements already-frozen architecture without redesigning any of it.** Every decision
  in this plan is a direct translation of a statement already made in
  `docs/architecture/phase2_1_application_bootstrap.md`; where this plan makes an implementation
  choice the architecture leaves open (e.g., a concrete module/file name), that choice is stated as
  illustrative, matching the architecture's own discipline for its entrypoint's name.

## 2. Planned Module Structure

**Files to create:**
- `scripts/application_bootstrap.py` — the bootstrap module: the application-instance representation
  and the bootstrap entrypoint. The name is illustrative, matching Phase 2.1's own "no frozen name"
  treatment of its entrypoint (Public Function Contracts) — no architectural document mandates this
  exact file or function name.
- `tests/test_application_bootstrap.py` — the test module covering the cases listed in Section 5.

**Files to modify:** none. No file under `scripts/`, `tests/`, or `docs/` is modified by this
implementation. **No existing bootstrap-like module is replaced** — this is a net-new addition; no
prior startup mechanism exists in the repository for it to supersede.

**Files intentionally left untouched:**
- Every Stage script (Stage 0 through Stage 21), including `stage8_embedding_generation.py`,
  `stage13_llm_execution.py`, and `stage21_agent_planning.py` — their own orchestration, contracts, and
  entrypoints are called through the held dependency-object set, never modified.
- `scripts/phase1_1_configuration_layer.py` — called only indirectly, through the one
  `compose_application()` invocation; never called directly by the bootstrap module.
- `scripts/embedding_provider_gemini.py`, `scripts/llm_provider_gemini.py`,
  `scripts/planner_provider_gemini.py` — each provider's own factory and registration function are
  invoked only inside `compose_application()`'s own call chain; the bootstrap module never touches them.
- `scripts/composition_root.py` — called as-is, exactly once per bootstrap invocation, never edited.
- Every existing test file, including `tests/test_composition_root.py`.
- Every file under `docs/architecture/`.

**Ownership boundaries**, restated from Phase 2.1's own Non-Responsibilities, and preserved
unmodified by this plan:
- The bootstrap module never assembles a `ProviderRegistration` list itself — whatever list is needed
  is passed into the bootstrap entrypoint by its own caller, and forwarded to `compose_application()`
  unchanged.
- The bootstrap module never calls `load_raw_settings()`, `validate_settings()`,
  `build_provider_registry()`, `wire_dependencies()`, or `validate_wiring_result()` directly — its only
  interaction with Phase 1.1's machinery is indirect, through the one `compose_application()` call.
- The bootstrap module never constructs an adapter, never touches an SDK client, and never resolves a
  credential — every one of those remains entirely inside `compose_application()`'s own call.
- The bootstrap module never mutates the dependency-object set `compose_application()` returns.

## 3. Implementation Order

The sequence below follows Phase 2.1's own Bootstrap Lifecycle (Overview through step [6]) directly.
Each step is described narratively; no code or pseudocode is included.

**(a) Application-instance representation.** Define a way to hold the dependency-object set
`compose_application()` returns as a single, cohesive unit — the same set Phase 1.5's Outputs section
names (the wired adapters, `AgentDependencies`, the retrieval closures). This representation is built
once, from the successful result of one composition-root call, and is never partially replaced or
partially reconstructed afterward, matching Application Model's "owned as a single unit" statement.

**(b) Bootstrap entrypoint.** Define one function that accepts whatever `compose_application()` itself
requires as input (the registrations sequence, and optionally an environment mapping or `.env` path),
and internally invokes `compose_application()` exactly once. This mirrors Bootstrap Lifecycle step [2]
precisely — the entrypoint performs no provider registration, no wiring, and no adapter construction
itself; it only makes the one call and reacts to its outcome.

**(c) Readiness decision.** Immediately after the one call, the entrypoint observes whether it returned
or raised. This is a binary observation, not a computed judgment — Startup Validation states plainly
that no new validation tier exists at this layer, so the entrypoint does not re-inspect, sample, or
re-validate anything about the returned dependency-object set. On a successful return, the
application-instance representation from step (a) is constructed around the returned set, and the
instance is considered ready. On a raised exception, no instance is constructed.

**(d) Failure propagation.** Whatever exception `compose_application()` raises — any of Phase 1.1's
three configuration exception types, or an exception a provider factory raised through
`wire_dependencies()` — propagates out of the bootstrap entrypoint completely unmodified. The
entrypoint contains no `try`/`except` block that changes, wraps, logs-and-suppresses, or reinterprets
the exception; per Failure Handling, this is a hard stop, never a retry, never a fallback, and never a
degraded/partial instance.

**(e) Shutdown handling.** Exactly as Bootstrap Lifecycle step [6] and Design Decision #2 state: no
disposal method, no teardown callback, no `close()`/`shutdown()` function, and no lifecycle hook of any
kind is added to the bootstrap module, to the application-instance representation, or to anything the
bootstrap entrypoint returns. Process exit is ordinary object lifetime. This is a deliberate omission,
not an oversight — implementing any such method would add behavior the frozen architecture explicitly
states does not exist anywhere in the repository.

No other step is added. The implementation order above starts and ends with exactly the six lifecycle
steps Bootstrap Lifecycle names (startup, composition-root invocation, readiness decision, ready/failed
branch, application lifetime, shutdown-absence) — steps (a) through (e) above map onto them directly,
with "application lifetime" (Bootstrap Lifecycle step [5]) requiring no separate implementation step of
its own, since it describes the instance persisting unchanged for as long as the holding process is
alive — a property of not writing any mutation or replacement logic, not a step to implement.

## 4. Validation Strategy

Implementation compliance is checked as a review pass against each frozen source, run after the module
described in Section 2 exists and before it is considered complete:

**Against Phase 2.1** (`docs/architecture/phase2_1_application_bootstrap.md`):
- Every item in Responsibilities and Non-Responsibilities is checked against the implemented module:
  does the bootstrap entrypoint call the composition root's contract exactly once (Responsibilities
  item 1)? Does it introduce no new validation tier (Startup Validation)? Does readiness remain an
  internal concept, with no health-check route, CLI flag, or network-facing surface added anywhere
  (Application Model, Design Decisions #3)? Is there no disposal, teardown, or shutdown method anywhere
  in the module (Bootstrap Lifecycle step [6])? Is the bootstrap entrypoint's own name treated as
  illustrative rather than asserted as frozen (Public Function Contracts)?
- The Application Model's three defining questions are checked directly: does the implementation
  produce exactly one held dependency-object set per successful call; is that set held/exposed as a
  single unit, never partially replaced; does the instance's own lifetime tie to nothing but the
  holding process's own lifetime?

**Against Phase 1.5** (`docs/architecture/phase1_5_composition_root.md`):
- Confirm the bootstrap module never calls `build_provider_registry()`, `wire_dependencies()`, or
  `validate_wiring_result()` directly — only `compose_application()` is called, and only once per
  bootstrap invocation.
- Confirm the bootstrap module treats the returned dependency-object set opaquely, per Phase 1.5's own
  Composition Model and Security Considerations — no field is inspected, extracted, or serialized
  beyond holding and forwarding the set as a whole.

**Against Phase 1.1** (`docs/architecture/phase1_1_configuration_layer.md`):
- Confirm the bootstrap module never reads `os.environ` directly, never opens a `.env` file itself, and
  never resolves a `credential_ref` — every one of these remains exclusively inside
  `compose_application()`'s own call chain.
- Confirm no raw credential value is ever received, held, logged, or forwarded by the bootstrap module.

This validation pass is a manual review checklist run against the finished module's source, not new
automated tooling — the same posture every prior phase's own implementation-compliance review in this
project has used.

## 5. Testing Strategy

The tests below are described in one sentence each. No test code or assertions are written here.

1. **Successful bootstrap** — verifies that a bootstrap call with valid inputs results in a held
   dependency-object set containing every member `compose_application()` itself returns (the wired
   adapters, `AgentDependencies`, the retrieval closures).
2. **Startup failure propagation** — verifies that each of Phase 1.1's three exception types
   (`ConfigurationInputError`, `ConfigurationWiringError`, `ConfigurationInternalError`), when raised by
   the underlying composition-root call, propagates out of the bootstrap entrypoint unmodified.
3. **Readiness transitions** — verifies that no application instance exists before the bootstrap call
   is made, that exactly one instance exists and is marked ready after a successful call, that no
   instance exists after a failed call, and that no third outcome is ever observed.
4. **Lifetime ownership** — verifies that the object reference held after a successful bootstrap call
   is never reconstructed, replaced, or partially reassigned by any later operation on the bootstrap
   module.
5. **Deterministic startup** — verifies that, given a composition-root call mocked to return a fixed
   outcome, the bootstrap entrypoint's own readiness decision is identical on every invocation.
6. **Composition-root invocation count** — verifies that `compose_application()` is called exactly once
   per bootstrap invocation, never twice, and never retried after a failure.
7. **No modification of the dependency graph after bootstrap** — verifies that the held
   dependency-object set's own fields/entries are unchanged across repeated reads after a successful
   bootstrap call.
8. **Binary startup result** — verifies that success and failure are mutually exclusive and exhaustive
   outcomes of a single bootstrap call — never both, never neither.
9. **Repeated successful bootstrap invocations create independent application instances** — verifies
   that calling the bootstrap entrypoint twice, each time successfully, produces two distinct held
   dependency-object sets with no shared mutable state between them, confirming the "one instance per
   call" lifetime model stated in Application Model.
10. **Shutdown behavior exactly matching the architecture** — verifies the absence of any
    dispose/close/teardown method anywhere on the bootstrap module or on the application-instance
    representation it returns; this test asserts that no such method exists, not that one behaves a
    particular way.

## 6. Acceptance Criteria

Implementation of Phase 2.1 is complete when all of the following hold:

- All repository tests pass, including the existing `tests/test_composition_root.py` suite, run
  unmodified.
- No Stage 0–21 script is modified.
- No provider module (`embedding_provider_gemini.py`, `llm_provider_gemini.py`,
  `planner_provider_gemini.py`) is modified.
- `scripts/phase1_1_configuration_layer.py` is not redesigned — no new function, field, or validation
  tier is added to it.
- `scripts/composition_root.py` is not redesigned — it is called exactly as it exists today, with no
  modification.
- **Bootstrap performs exactly one composition-root invocation per bootstrap call**, verified directly
  by Testing Strategy item 6.
- Every checklist item in Validation Strategy (Section 4) is satisfied against Phase 2.1, Phase 1.5,
  and Phase 1.1.
- Deterministic behavior is confirmed by Testing Strategy item 5 — identical inputs to the mocked
  composition-root call always produce an identical readiness outcome.
- Zero regressions: a full run of the existing test suite shows identical pass/fail results before and
  after the new module's addition.

Implementation has not yet begun. This document is a plan only.

---

# Phase 2.2 — Runtime Orchestration: Implementation Plan

This is a planning document only. It contains no implementation code, no pseudocode, and no test
code. It describes how the frozen architecture at
`docs/architecture/phase2_2_runtime_orchestration.md` would be implemented, so that the implementation
itself can be reviewed and approved before any code is written.

## 1. Executive Summary

**Objective.** Implement the runtime-orchestration layer Phase 2.2 already architects: a thin,
one-call-per-request layer that receives an already-bootstrapped application instance, invokes the
frozen public request-processing contract exactly once per request, forwards the returned result
unmodified, and propagates any request failure unmodified.

**Architectural scope.** One new module providing a single runtime entrypoint function that accepts the
already-bootstrapped application instance and one request's own input, and performs the one
contract-invocation call, the completion decision, and the failure-propagation behavior Phase 2.2
defines. Nothing else. No bootstrap work, no composition-root work, no configuration work, no provider
work, no redesign of any Stage.

**Relationship to Phase 2.1.** The runtime receives the already-bootstrapped application instance
(`ApplicationInstance`, the same held dependency-object set `bootstrap_application()` already produces)
as a finished, opaque input. The runtime never calls `bootstrap_application()` itself, never
re-composes the instance, and never inspects its internal fields beyond forwarding it as a whole into
the one contract invocation.

**Relationship to the composition root.** The runtime never calls `compose_application()`, directly or
indirectly — its only relationship to the composition root is transitive, through the already-held
application instance bootstrap already produced.

**Relationship to the frozen public request-processing contract.** This is the one call the runtime
makes per request. At the time this plan is written, that contract is realized by Stage 21's own public
entrypoint (`scripts/stage21_agent_planning.py`), taking an `agent_request`-shaped mapping and an
`AgentDependencies` instance and returning an `agent_result`-shaped mapping, or raising one of Stage
21's own typed exceptions. This plan depends only on the existence of that contract, not on its
particular function name — Stage 21 is named here only as its current realization, never as the
runtime's permanent architectural identity, matching the discipline Phase 2.2's own architecture
document already establishes.

**This implementation realizes the frozen architecture only.** Every decision in this plan is a direct
translation of a statement already made in `docs/architecture/phase2_2_runtime_orchestration.md`; it
redesigns no existing layer — not runtime's own responsibilities, not bootstrap, not the composition
root, not Stage 21.

## 2. Planned Module Structure

**Files to create:**
- `scripts/runtime_orchestration.py` — the runtime module: one entrypoint function that invokes the
  frozen public request-processing contract exactly once per request. The name is illustrative, matching
  Phase 2.2's own "no frozen name" treatment of its entrypoint (Public Function Contracts) — no
  architectural document mandates this exact file or function name.
- `tests/test_runtime_orchestration.py` — the test module covering the cases listed in Section 5.

**Files to modify:** none. No file under `scripts/`, `tests/`, or `docs/` is modified by this
implementation. No existing runtime-like module is replaced — this is a net-new addition alongside
bootstrap, not a redesign of it.

**Ownership**, restated from Phase 2.2's own Non-Responsibilities, and preserved unmodified by this
plan:
- The runtime module never assembles a `ProviderRegistration` list, never calls `compose_application()`,
  and never calls `bootstrap_application()` — it receives an already-bootstrapped application instance
  as input, supplied by its own caller.
- The runtime module never imports a provider SDK directly, never reads `os.environ` or opens a `.env`
  file, and never resolves a credential.
- The runtime module never calls Stage 8's or Stage 13's own entrypoints directly — only the one
  outermost frozen public request-processing contract call (currently realized by Stage 21's own
  entrypoint) is invoked; every further stage invocation that contract needs is entirely that contract's
  own internal responsibility.

**Lifetime.** The runtime entrypoint holds no state of its own across calls beyond what its own caller
passes in per invocation — no module-level mutable state, no accumulated request history, no cache, no
counter, matching Phase 2.2's own Read-Only Guarantees and Runtime Model.

**Files intentionally left untouched:**
- `scripts/application_bootstrap.py` and its own `bootstrap_application()` entrypoint — called as-is by
  whatever process-level caller invokes the runtime, never modified or re-invoked by the runtime module
  itself.
- `scripts/composition_root.py`, `scripts/phase1_1_configuration_layer.py`, the three provider Gemini
  modules — never called by the runtime module, only transitively inherited through the already-held
  application instance.
- `scripts/stage8_embedding_generation.py`, `scripts/stage13_llm_execution.py`,
  `scripts/stage21_agent_planning.py` — none redesigned; Stage 21's own public entrypoint is invoked
  as-is, exactly once per request, as the current realization of the frozen contract.
- Every existing test file, including `tests/test_application_bootstrap.py` and
  `tests/test_composition_root.py`.
- Every file under `docs/architecture/`.

## 3. Implementation Order

Described as required behavior, matching Phase 2.2's own Request Lifecycle without prescribing internal
code organization. No code or pseudocode is included.

The runtime entrypoint must: accept the already-bootstrapped application instance and one request's own
input without validating or reshaping that input itself; invoke the frozen public request-processing
contract exactly once per request, supplying the request input and the relevant held dependencies
(currently realized by Stage 21's own public entrypoint, named illustratively); on success, return the
contract's own return value unmodified as the request result; on failure, allow the raised exception to
propagate through the entrypoint completely unmodified, never caught or wrapped; and end the request's
own execution there — no further step, matching Phase 2.2's own Request Lifecycle boundary-to-boundary
span in full.

## 4. Validation Strategy

Implementation compliance is checked as a review pass against each frozen source, run after the module
described in Section 2 exists and before it is considered complete. Each check below is distinct from
Section 7's post-implementation Verification checklist — this section defines what "compliant" means;
Verification confirms the finished plan document itself satisfies its own requirements.

**Against Phase 2.2** (`docs/architecture/phase2_2_runtime_orchestration.md`):
- Lifecycle validation: does the implemented entrypoint represent all five Request Lifecycle steps
  (request boundary begins, contract invocation, completion decision, completed/failed, request
  boundary ends) with none skipped and none added?
- Ownership validation: does the runtime hold nothing across requests beyond a reference to the
  application instance passed into it — no accumulated state, no cache, no counter?
- Determinism validation: given an identical request input and an identical held instance, is the
  completion decision identical every time?
- Failure propagation validation: does every exception the contract raises reach the runtime's own
  caller completely unmodified — no catch, no wrap, no log-and-suppress?

**Against Phase 2.1** (`docs/architecture/phase2_1_application_bootstrap.md`):
- Confirm the runtime module never calls `bootstrap_application()` — the application instance is
  received as a finished, opaque input, never re-composed or re-validated by the runtime itself.

**Against Phase 1.5** (`docs/architecture/phase1_5_composition_root.md`):
- Confirm the runtime module never calls `compose_application()`, `build_provider_registry()`,
  `wire_dependencies()`, or `validate_wiring_result()` directly — its relationship to each is entirely
  transitive, through the already-bootstrapped instance.

This validation pass is a manual review checklist run against the finished module's source, not new
automated tooling — the same posture the Phase 2.1 implementation plan already establishes.

## 5. Testing Strategy

The tests below are described in one sentence each. No test code or assertions are written here.

1. **Successful request execution** — verifies that, given a mocked contract call that returns, the
   runtime entrypoint returns that same result unmodified as the request result.
2. **Runtime failure propagation** — verifies that, given a mocked contract call that raises, the same
   exception propagates through the runtime entrypoint unmodified.
3. **Exactly one request-processing contract invocation** — verifies that the contract is called exactly
   once per runtime call, never zero, never twice, with no retry on failure.
4. **Deterministic execution** — verifies that, given a mocked contract call with a fixed outcome, the
   completion decision is identical across repeated invocations.
5. **Request ownership** — verifies that one request's own input and result are never attributed to, or
   leaked into, any other request.
6. **Request isolation** — verifies that two sequential requests against the same held application
   instance produce independent results with no shared mutable state between them.
7. **Repeated request execution** — verifies that invoking the runtime entrypoint multiple times against
   the same held instance produces one independent result per call, with the held instance itself
   unchanged across calls.
8. **Binary completion** — verifies that every invocation ends in exactly one of "completed" or "failed"
   — never a third outcome, never both, never neither.
9. **No retries** — verifies that the runtime itself never re-invokes the contract after a failure, by
   asserting the contract mock's own call count remains one even when it raises.
10. **No background execution** — verifies that the runtime entrypoint's own call is synchronous and
    blocking, with no thread, async task, or deferred execution introduced.
11. **No hidden lifecycle** — verifies that the runtime introduces no step beyond the five Phase 2.2
    Request Lifecycle already names — no implicit setup, teardown, or state transition the architecture
    does not define.

## 6. Acceptance Criteria

Implementation of Phase 2.2 is complete when all of the following hold:

- **The frozen public request-processing contract is invoked exactly once per runtime call**, verified
  directly by Testing Strategy item 3.
- **Deterministic execution** is confirmed by Testing Strategy item 4 — identical inputs to the mocked
  contract call always produce an identical completion decision.
- **Request lifecycle complete** — all five Phase 2.2 Request Lifecycle steps are represented, with no
  step skipped or added.
- **Binary success/failure** — every request ends in exactly one of two outcomes, verified by Testing
  Strategy item 8.
- No Stage 8, Stage 13, or Stage 21 script is modified or redesigned — each is called only through its
  own already-frozen public contract.
- `scripts/application_bootstrap.py` is not modified or redesigned — called as-is by whatever invokes
  the runtime, never by the runtime module itself.
- `scripts/composition_root.py` is not modified or redesigned — never called by the runtime module.
- All repository tests pass, including every existing test file (`tests/test_application_bootstrap.py`,
  `tests/test_composition_root.py`) run unmodified.
- Zero regressions: a full run of the existing test suite shows identical pass/fail results before and
  after the new module's addition.

Implementation has not yet begun. This document is a plan only.

---

# Phase 2.3 — Request Observability: Implementation Plan

This is a planning document only. It contains no implementation code, no pseudocode, and no test code.
It describes how the frozen architecture at `docs/architecture/phase2_3_request_observability.md` would
be implemented, so that the implementation itself can be reviewed and approved before any code is
written.

## 1. Executive Summary

Phase 2.3's objective is to implement the frozen request-observability layer that watches one request's
own execution — already fully defined by Phase 2.2's own Request Lifecycle — without altering how that
request executes. Architectural scope: one new module holding an observer entrypoint that wraps a call
to the existing runtime-orchestration entrypoint exactly once per request, generates a per-request
correlation identity, and produces one immutable observation record on either outcome — nothing else.

Relationship to Phase 2.2: the observer receives the same inputs Phase 2.2's own runtime entrypoint
already receives (the bootstrapped application instance and one request), and calls that entrypoint
exactly once, with its inputs and behavior completely unmodified — the observer never wraps the call in
a try/except of its own, never alters the call count, and never changes what the caller ultimately
receives (the underlying result on success, the underlying exception on failure).

Relationship to Phase 2.1 and the composition root: inherited transitively and unchanged — the observer
never bootstraps, never composes, and never re-invokes either.

Relationship to the frozen public request-processing contract: unchanged — the observer never calls it
directly; it only ever calls the existing runtime-orchestration entrypoint, which alone invokes the
contract.

This implementation realizes the frozen Phase 2.3 architecture only — no redesign of Phase 2.2's Request
Lifecycle, Failure Handling, or Runtime Model; no error-isolation mechanism invented; no emission target
(logging, exporting, buffering) implemented.

## 2. Planned Module Structure

New module: `scripts/request_observability.py` (illustrative name, matching the "no frozen name"
discipline every prior phase applies to its own entrypoint), holding one observer entrypoint function
and whatever minimal correlation-identity generation and record-shape definition it needs internally.

New test module: `tests/test_request_observability.py`.

Ownership boundaries: the observer module never calls `bootstrap_application()`, never calls the
composition root, never imports a provider SDK, never calls Stage 8, Stage 13, or Stage 21 directly, and
never calls the frozen public request-processing contract directly — it calls only the existing
runtime-orchestration entrypoint (`scripts/runtime_orchestration.py`'s own `execute_request`, or
equivalent), exactly once per invocation, with its inputs unmodified.

Explicit non-goal: the observer never wraps the runtime-orchestration entrypoint's own call to the
frozen contract in a try/except of its own. Per the corrected Failure Handling posture in the Phase 2.3
architecture, this implementation does not attempt to isolate an observation failure from request
execution — no frozen source defines that mechanism, and none is introduced here.

Lifetime: the observer holds no state across calls beyond whatever mechanism it uses to generate a
fresh correlation identity per invocation — no module-level mutable state, no accumulated record
history, no cache.

Files intentionally left untouched: `scripts/runtime_orchestration.py`, `scripts/application_
bootstrap.py`, `scripts/composition_root.py`, `scripts/phase1_1_configuration_layer.py`, all three
provider Gemini modules, `scripts/stage8_embedding_generation.py`, `scripts/stage13_llm_execution.py`,
`scripts/stage21_agent_planning.py`, every existing test file, every existing architecture document.

## 3. Implementation Order

Described as required behavior, matching the Phase 2.3 architecture's own Observation Lifecycle,
without prescribing internal code organization:

Observation starts at request boundary begin, generating a fresh per-request correlation identity. The
existing runtime-orchestration entrypoint is then invoked exactly once, with the request and the
already-bootstrapped application instance forwarded unmodified — this call is not wrapped in any
exception handling of the observer's own. On that call's own return, an immutable observation record is
produced carrying the correlation identity, a "completed" outcome, and a duration; the underlying result
is returned to the observer's own caller completely unchanged. On that call's own raised exception, an
immutable observation record is produced carrying the correlation identity, a "failed" outcome, and a
duration (whether a record can be produced at all in every such case is a matter for the implementation,
but no exception handling exists purely to force one — see Planned Module Structure's explicit
non-goal); the underlying exception continues to propagate to the observer's own caller completely
unmodified. The observer's own responsibility ends at record production — what happens to the record
afterward is out of scope. No code or pseudocode for any step — narrative description only.

## 4. Validation Strategy

Review checklist to run post-implementation, not new automated tooling:

Against Phase 2.3 (every Responsibility/Non-Responsibility satisfied; correlation identity is generated
by the observer itself, never assumed to come from elsewhere; the observation record is immutable and
never retained or read back by runtime orchestration or bootstrap; no error-isolation mechanism is
introduced; no emission target is implemented).

Against Phase 2.2 (the runtime-orchestration entrypoint's own behavior, call count, and exception
identity are provably unchanged before and after being wrapped by the observer; the observer introduces
no exception handling around the wrapped call; existing Phase 2.2 tests continue to pass unmodified).

Against Phase 2.1 (the observer never re-invokes bootstrap; the held application instance continues to
be treated as a finished, opaque input, forwarded unmodified).

Sub-checks: record-content validation (no request or result payload, no credential, appears in any
produced record — only correlation identity, outcome, and duration); ownership validation (the observer
holds no state across calls beyond fresh-per-call correlation-identity generation); determinism
validation (record structure and lifecycle ordering are identical across repeated calls; only the
duration value itself varies, as expected).

## 5. Testing Strategy

One sentence per planned test, no test code:

Successful request execution produces an observation record with a valid correlation identity and a
"completed" outcome, while the underlying result returned to the caller is identical to what the
wrapped runtime entrypoint itself returned.

Failure propagation — given a wrapped call that raises, the original exception propagates through the
observer to its own caller completely unmodified, with the same type and identity it was raised with.

Exactly one wrapped-call invocation per observer call — the underlying runtime entrypoint is invoked
exactly once, never zero, never twice, no retry introduced by the observer.

No exception handling introduced by the observer around the wrapped call — inspecting the observer's
own source confirms no try/except surrounds the call to the runtime-orchestration entrypoint.

No content leakage — a produced observation record never contains the raw request or raw result content
under any of its own fields.

Deterministic record structure and lifecycle ordering — repeated calls with a mocked, fixed-outcome
wrapped call always produce a record with the same field set and the same relative step ordering.

Per-request correlation-identity independence — two sequential calls never produce the same correlation
identity as each other.

No mutable state retained across calls — the observer holds nothing between two sequential invocations
beyond generating a fresh correlation identity each time.

## 6. Acceptance Criteria

Measurable completion criteria:

- The wrapped runtime-orchestration entrypoint's own behavior, call count, and exception identity are
  unchanged before and after being wrapped by the observer, verified by Testing Strategy items 1–3.
- The observer introduces no exception handling of its own around the wrapped call, verified by Testing
  Strategy item 4 (source inspection).
- No content leakage in any produced record, verified by Testing Strategy item 5.
- Deterministic record structure and lifecycle ordering, verified by Testing Strategy item 6.
- Per-request correlation-identity independence, verified by Testing Strategy item 7.
- No mutable state retained across calls, verified by Testing Strategy item 8.
- No redesign of Phase 2.2's Request Lifecycle, Failure Handling, or Runtime Model — each remains
  exactly as frozen.
- No redesign of Phase 2.1's bootstrap layer or Phase 1.5's composition root — neither is called by the
  observer.
- All repository tests pass, including every existing test file (`tests/test_runtime_orchestration.py`,
  `tests/test_application_bootstrap.py`, `tests/test_composition_root.py`) run unmodified.
- Zero regressions: a full run of the existing test suite shows identical pass/fail results before and
  after the new module's addition.

Implementation has not yet begun. This document is a plan only.
