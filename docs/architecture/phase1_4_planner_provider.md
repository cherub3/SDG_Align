# Phase 1.4 — Planner Provider Architecture

Stages 0–21, Phase 1.1 (Configuration Layer), Phase 1.2 (LLM Provider Architecture), and Phase 1.3
(Embedding Provider Architecture) remain completely frozen; nothing below proposes any change to
existing code or shipped docs. Phase 1.4 defines the architecture for a **concrete** implementation
of the abstract `PlannerLLMAdapter` contract Stage 21 already declares
(`scripts/stage21_agent_planning.py:41-46`), registered under the `PLANNER_LLM_PROVIDER` seam Phase
1.1 already recognizes (`SUPPORTED_SEAMS`, `docs/architecture/phase1_1_configuration_layer.md`
line 710), and already named as future work in Phase 1.1's own Future Phase Boundaries ("Phase 1.4 —
Concrete planner provider. A real `PlannerLLMAdapter` implementation, registered under seam
`PLANNER_LLM_PROVIDER`, which may share underlying client plumbing with Phase 1.2's own
implementation without sharing its public contract.").

**Source-fidelity rule, stated once, governing this entire document:** every architectural statement
below is derived directly from `scripts/stage21_agent_planning.py`, `phase1_1_configuration_layer.md`,
`phase1_2_llm_provider.md`, or `phase1_3_embedding_provider.md`. Where Stage 21's actual contract
leaves something undefined — most notably, `PlannerLLMAdapter` declares no identity property, no
result dataclass, and no retry policy of its own — this document states that absence explicitly
rather than inventing a Phase-1.2-shaped or Phase-1.3-shaped analog that Stage 21's own source does
not support. No new planner abstraction is introduced; the existing `PlannerLLMAdapter` contract is
built against exactly as declared.

**Provider-neutrality, stated once, governing this entire document, exactly as Phase 1.2 and Phase
1.3 already establish for their own seams:** provider-specific terminology, SDK behavior, and
configuration field names may appear only as illustrative examples. Normative behavior — the adapter
contract, the identity statement, the result-ownership rules, the exception boundary — must never
depend on any specific vendor's semantics.

See `docs/pipeline_principles.md` for shared conventions this document inherits rather than restates.

## Overview

Stage 21's own Schemas and Contracts section declares `PlannerLLMAdapter` in full:

```python
class PlannerLLMAdapter(ABC):
    @abstractmethod
    def plan(self, planner_prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes a planning-capable LLM with the given prompt.
        Returns a structured PlannerDecision. On failure, raises PlannerInvocationError."""
        pass
```

(`scripts/stage21_agent_planning.py:41-46`). `AgentDependencies.planner_llm_adapter:
PlannerLLMAdapter` (line 58) is the field a concrete instance is threaded through; Phase 1.1's own
Dependency Wiring Model already maps this seam onto that exact field
(`PLANNER_LLM_PROVIDER` → `AgentDependencies.planner_llm_adapter`, line 372). Neither Stage 21 nor
Phase 1.1 defines what a concrete adapter itself must do internally to be a correct, safe,
production-grade implementation of that contract. That is the entire, narrow gap Phase 1.4 closes —
the same kind of gap Phase 1.2 closed for `LLMAdapter` and Phase 1.3 closed for `ProviderAdapter`.

Phase 1.4 does not implement any adapter. It defines: (1) the architecture any concrete
`PlannerLLMAdapter` implementation must follow — construction ownership, and per-field ownership of
every value a concrete implementation must produce in the dict `plan()` returns; (2) the
`ProviderRegistration` contract a concrete implementation supplies to Phase 1.1's
`build_provider_registry()`; and (3) the exception-raising discipline a concrete implementation's
`plan()` must follow.

**Structural differences from Phase 1.2's `LLMAdapter` and Phase 1.3's `ProviderAdapter`, confirmed
directly against Stage 21's actual source, that this document states explicitly rather than silently
porting over either prior phase's shape:**

1. **`PlannerLLMAdapter` declares no identity property of any kind.** Unlike `LLMAdapter.
   provider_name`/`model_version_reported` (Stage 13) or the embedding provider's own identity triple
   (Stage 8), Stage 21's abstract class declares exactly one abstract method (`plan`) and nothing
   else — no `provider_name`, no `model_version_reported`, no analog. This document does not invent
   an identity property Stage 21 never asked for (Provider Identity).
2. **The return type is an untyped `Dict[str, Any]`, not a dataclass.** Stage 13's `RawLLMResult` and
   Stage 8's embedding return shape are typed contracts; `plan()`'s own docstring says only "Returns a
   structured PlannerDecision" and returns `Dict[str, Any]` — Stage 21 defines the dict's required
   shape through its own `validate_planner_decision()` function, not through a class (Planner Result
   Ownership).
3. **Exactly one exception type, carrying a `code` field, not a closed four-member (or boolean)
   vocabulary.** `PlannerInvocationError(message: str, code: str)` (line 31-35) is the only exception
   type `plan()`'s own docstring names. There is no `PlannerAuthError`, no
   `PlannerContentPolicyError`, no transient/non-retryable split analogous to Stage 13's four types
   (Exception Boundary).
4. **Stage 21 implements no retry of a failed planner invocation.** Reading `plan_and_execute()`'s own
   loop (lines 446-457): on `PlannerInvocationError`, the loop appends a `PLANNER_INVOCATION_FAILED`
   finding, sets `plan_status = "FAILED"`, transitions to `PlannerState.FAILED`, and `break`s — there
   is no retry attempt, no backoff, and no retry-related constant anywhere in Stage 21's own Constants
   section. This document does not attribute a Stage-13-style retry policy to Stage 21, because none
   exists in the source (Retry Ownership).
5. **`config` is resolved once per `plan_and_execute()` call, not fresh per `plan()` call.**
   `resolve_planning_config()` is called exactly once (line 411), before the planning loop begins;
   the same `config` dict is passed to every `plan()` call within that loop, unlike Stage 13's
   `LLMExecutionConfig`, which a caller supplies fresh on every `invoke()` call (Planner Invocation
   Lifecycle).

**Boundary rule, stated once, governing this entire document:** Stage 21's `PlannerLLMAdapter`/
`PlannerInvocationError`/`validate_planner_decision()` contract is frozen and is never re-defined,
extended, or altered here — it is quoted, cited, and built against. Phase 1.1's `ApplicationSettings`/
`ProviderSettings`/`ProviderRegistration`/`wire_dependencies()` contracts are equally frozen and are
never re-defined here. Phase 1.4 is the thing standing between them: it describes how a real,
concrete class satisfies the first contract while being correctly constructible by the second.

## Scope

Phase 1.4 answers exactly one question — given a `ProviderSettings` object and (if `credential_ref`
was present) a resolved raw credential string, supplied by Phase 1.1's `wire_dependencies()` exactly
as its own Public Function Contracts already describe, what is the architecture of a concrete class
that (a) satisfies Stage 21's frozen `PlannerLLMAdapter` contract, (b) owns exactly one SDK client (or
equivalent) for its own lifetime, and (c) can be supplied to `build_provider_registry()` as a
`ProviderRegistration` — and stops there.

It never redesigns `PlannerLLMAdapter`, `PlannerState`, or `plan_and_execute()`'s own state machine
(Stage 21's own frozen job). It never selects which provider is active for the
`PLANNER_LLM_PROVIDER` seam (Phase 1.1's own job, via `ApplicationSettings`). It never constructs the
`planner_prompt` string — `build_planner_prompt()` (`scripts/stage21_agent_planning.py:264-266`) is
Stage 21's own, and a concrete adapter receives that already-built string as `plan()`'s first
parameter, exactly as Stage 13's `LLMAdapter` receives already-assembled `system_prompt`/
`user_prompt` strings (Phase 1.2's own Non-Responsibilities, extended here by the same reasoning). It
never modifies Stage 21's own validation (`validate_planner_decision`, `validate_plan_step`,
`validate_agent_result`), its own `PlannerState` transitions, or the tool/conversation/pipeline
dependencies `AgentDependencies` also carries. It never implements a Streamlit UI, the application
composition root, or any dependency of `AgentDependencies` other than `planner_llm_adapter` itself.

## Responsibilities

Phase 1.4 shall: define the architecture of a concrete `PlannerLLMAdapter` subclass that fully and
exactly implements Stage 21's frozen abstract contract (Adapter Contract); define the ownership and
lifecycle of the one SDK client (or equivalent) a concrete adapter instance holds, from construction
through disposal, never escaping the adapter instance (Planner Invocation Lifecycle); define how a
concrete adapter's constructor consumes the `(ProviderSettings, Optional[str])` pair Phase 1.1's
`wire_dependencies()` already calls a registered factory with, and what it does with the resolved raw
credential (Planner Configuration, Security); state explicitly, per the source, that Stage 21's
`PlannerLLMAdapter` contract defines no adapter-identity property, and define what — if anything — a
concrete implementation may expose beyond that contract without it becoming visible to Stage 21's own
orchestration (Planner Provider Identity); define, per key, the ownership of every value a concrete
implementation must produce in the dict `plan()` returns, matched against Stage 21's own
`validate_planner_decision()` requirements (Planner Result Ownership); define the `ProviderRegistration`
a concrete implementation supplies to Phase 1.1's `build_provider_registry()`, including the correct
`network_dependent` declaration (Factory Contract); define the exception-raising discipline a concrete
adapter's `plan()` must follow to satisfy Stage 21's own single-exception-type contract (Planner
Exception Translation); state explicitly, per the source, that Stage 21 implements no retry of a
failed planner invocation, and that this document introduces none either (Retry Ownership).

## Non-Responsibilities

Phase 1.4 explicitly does **not** perform, and no future patch to it may silently add without a new
design pass: select, implement, or import any specific concrete planning-capable LLM provider SDK
(this document defines the architecture any provider-specific implementation must follow; the
implementation itself, for any named provider, is separate, future, per-provider work never designed
here); construct the `planner_prompt` string, assemble `planner_context`, or decide when
`build_planner_prompt()` is called — that remains `plan_and_execute()`'s own frozen job
(`scripts/stage21_agent_planning.py:264-266, 444`); this document only ever receives an
already-assembled `planner_prompt: str` via `plan()`'s own parameter, exactly as Stage 21 itself
produces it, and interprets it no further than Stage 21 already does; modify Stage 21's own
`PlannerState` machine, `_transition()`, `plan_and_execute()`'s own loop, or any of
`validate_agent_request`, `validate_planner_decision`, `validate_plan_step`, `validate_agent_result` —
every one of those is untouched and unduplicated here; implement retry, backoff, or timeout logic
around a planner invocation of any kind — Stage 21's own source implements none, and inventing one
here would add behavior neither Stage 21 nor Phase 1.1 asked for (Retry Ownership); construct a
retrieval closure, edit `ProviderRegistry`, or perform dependency wiring of any kind — every one of
those remains exclusively owned by Phase 1.1's own composition root, a deferred responsibility, not a
permanent prohibition; implement a Streamlit UI, the application composition root, or any of
`AgentDependencies`'s other fields (`handle_request`, `select_memory`, `append_turn`,
`get_conversation`, `execute_tool`, `tool_registry`, `tool_adapter`, `pipeline_deps`,
`default_planner_model_name`) — each is either an existing frozen stage's own contract or the
composition root's own concern, never this document's; choose which provider is active for the
`PLANNER_LLM_PROVIDER` seam (`ApplicationSettings`, Phase 1.1's own job, never this document's);
re-define, re-default, or re-clamp any tunable Stage 21's own `resolve_planning_config()` already owns
(`DEFAULT_MAX_PLAN_STEPS`, `MAX_PLAN_STEPS`, `DEFAULT_PLANNER_TEMPERATURE`,
`MAX_PLANNER_TEMPERATURE`); hold any global mutable state; introduce a new logging namespace, `stage`
identifier, or closed log-code vocabulary distinct from Stage 21's own (Logging Vocabulary); move a
responsibility from Stage 21 or Phase 1.1 into this document, or from this document into either of
them; invent an adapter-identity property, a typed result dataclass, or a multi-member exception
vocabulary that Stage 21's own source does not declare (Provider Identity, Planner Result Ownership,
Planner Exception Translation); introduce streaming, conversation memory, or session state on the
planner adapter itself — Stage 21's own `plan()` signature is synchronous request/response only, and
conversation state, where it exists at all in this pipeline, is owned by
`AgentDependencies.get_conversation`/`select_memory`/`append_turn`, never by
`planner_llm_adapter` (Future Phase Boundaries).

## Inputs

Two inputs, both supplied by Phase 1.1's `wire_dependencies()` exactly as its own Public Function
Contracts already describe — a concrete adapter's constructor (or the factory function that builds
it) never reads any other source:

- **`ProviderSettings`** — the seam's resolved configuration object (Phase 1.1's own schema): names
  the active `provider_name`, carries an `extra: Dict[str, Any]` passthrough this document is the
  first to interpret for the `PLANNER_LLM_PROVIDER` seam (Planner Configuration), and a
  `credential_ref` (an opaque reference, never a raw value).
- **An optional resolved raw credential (`Optional[str]`)** — the second positional argument Phase
  1.1's `wire_dependencies()` already passes to every registered factory, resolved from
  `credential_ref` immediately before the factory call, and `None` if the seam carries no
  `credential_ref`.

No environment variable, `.env` file, or secret store is ever read directly by a concrete adapter or
its factory — that reading is Phase 1.1's own exclusive responsibility, already performed before
either of the two inputs above reaches this layer.

At invocation time, a constructed adapter also receives, per call, exactly what Stage 21's own frozen
`plan()` signature already names: `planner_prompt: str` (produced by `build_planner_prompt()`, a
canonical-JSON serialization of `planner_context`) and `config: Dict[str, Any]` (produced once per
`plan_and_execute()` call by `resolve_planning_config()`, carrying `model_name`, `temperature`, and
`max_plan_steps`) — never anything this document adds to that signature.

## Outputs

- **One constructed instance conforming to Stage 21's frozen `PlannerLLMAdapter` contract** — returned
  by the factory function `wire_dependencies()` invokes; nothing else is returned to Phase 1.1.
- **Per invocation, one `Dict[str, Any]` satisfying Stage 21's own `validate_planner_decision()`
  requirements** (on success) **or a raised `PlannerInvocationError`** (on failure) — never anything
  else. Stage 21's own source names no other outward shape `plan()` may produce.

No file is written by any concrete adapter architected under this document. No new artifact directory
is introduced. There is no manifest interaction of any kind — the same zero-artifact posture Phase
1.1, Phase 1.2, and Phase 1.3 already established, extended here to the planner provider layer.

## Planner Provider Identity

Stage 21's own `PlannerLLMAdapter` abstract class, quoted in full above, declares exactly one member:
the abstract method `plan`. **It declares no `provider_name`, no `model_version_reported`, and no
identity property of any kind.** This is a real, confirmed structural difference from both Phase 1.2's
`LLMAdapter` (`provider_name`, `model_version_reported`) and Phase 1.3's embedding provider identity
triple — not an omission this document corrects, but a fact about Stage 21's own frozen contract this
document states plainly rather than papering over.

Consequences of this absence, each following directly from the source rather than from inference:

- **Stage 21's own orchestration never reads an identity property off `planner_llm_adapter`.**
  `AgentDependencies.planner_llm_adapter` is invoked only through `.plan(prompt, config)`
  (`scripts/stage21_agent_planning.py:447`); no other attribute access on it appears anywhere in
  `stage21_agent_planning.py`. A concrete implementation may add a `provider_name` attribute of its
  own for its own internal or diagnostic use, but doing so adds nothing Stage 21 will ever observe or
  depend on — it is invisible past the adapter boundary, exactly as any attribute not in the abstract
  contract would be.
- **No adapter-identity/request-identity split exists here, because neither concept is defined by
  Stage 21.** Phase 1.2 was required to split `LLMAdapter`'s identity into two concepts because Stage
  13's own `LLMExecutionConfig.model_name` is supplied fresh per call while `provider_name` is fixed
  per adapter. Stage 21's `config["model_name"]` is likewise per-call configuration (resolved once per
  `plan_and_execute()` invocation, per Overview point 5), but since `PlannerLLMAdapter` itself exposes
  no adapter-level identity property to hold the other half of a comparable split, there is nothing to
  split. This document does not manufacture a splitting exercise the source gives it no contract to
  split.
- **`model_name` is planner-request configuration, read from `config["model_name"]` by a concrete
  implementation's own `plan()` body — never a property Stage 21 places on the adapter.** A concrete
  implementation may use `config["model_name"]` however its own provider requires (as Phase 1.2's
  concrete `LLMAdapter` implementations do with the structurally identical key), but this document
  does not name this "request identity" as though it were a defined Stage 21 concept — the term
  belongs to Phase 1.2's own document, describing Stage 13's own contract, not Stage 21's.

**This document does not add an identity property to `PlannerLLMAdapter`.** Doing so would extend
Stage 21's frozen abstract contract, which is outside this document's authority (Adapter Contract,
Future Phase Boundaries — Category B).

## Planner Invocation Lifecycle

A strictly linear construction-to-disposal model, never a stored, mutable state machine — mirroring
Phase 1.2's own Prompt Lifecycle and Phase 1.3's own Embedding Lifecycle. The planning-loop state
machine (`PlannerState`) belongs entirely to Stage 21's own `plan_and_execute()`; nothing in a
concrete adapter's own lifecycle participates in or branches on that state machine.

```
[1] Factory invocation           — wire_dependencies() invokes the registered factory with
      (ProviderSettings, Optional[str]); the second argument is the resolved raw credential, or None
      │
      ▼
[2] SDK client construction      — the factory (or the adapter's own __init__) constructs exactly one
      SDK client (or equivalent), consuming the resolved raw credential exactly once; the client is
      stored only as a private attribute on the constructed adapter instance
      │
      ▼
[3] Adapter instance returned    — the fully constructed, PlannerLLMAdapter-conforming instance is
      returned to wire_dependencies(), which places it in WiringResult.wired[PLANNER_LLM_PROVIDER]
      │
      ▼
[4] Repeated plan() calls        — Stage 21's own plan_and_execute() loop calls
      plan(planner_prompt, config) zero or more times over one agent request's own planning loop
      (bounded by config["max_plan_steps"], itself resolved once before the loop begins), each call
      using the same SDK client constructed in step [2]; no reconstruction, no reconnection between
      calls; config is the same dict object across every call within one plan_and_execute() invocation
      (resolve_planning_config() is called exactly once, before the loop — Overview point 5);
      planner_prompt differs on each call, reflecting planner_context's own growing executed_steps
      history
      │
      ▼
[5] Result mapping               — on a successful call, the adapter returns a Dict[str, Any]
      satisfying Stage 21's own validate_planner_decision() requirements (Planner Result Ownership);
      on a failed call, the adapter raises PlannerInvocationError (Planner Exception Translation)
      │
      ▼
[6] Disposal                     — when the process holding the adapter instance ends (or, in a test
      harness, when the instance is explicitly discarded), the SDK client is released with it; this
      document defines no explicit disposal method beyond ordinary object lifetime, since Stage 21's
      own frozen contract calls none
```

**The retry boundary, stated explicitly, governing this entire document — and stated differently from
Phase 1.2's own retry boundary, because the source requires it.** One call to `plan()` corresponds to
exactly one provider invocation attempt; a concrete adapter performs exactly one network call (or
equivalent) per `plan()` invocation. Unlike Stage 13's own frozen Retry Policy, which Phase 1.2's
`LLMTransientError` feeds into, **Stage 21's own `plan_and_execute()` implements no retry of a failed
planner invocation at all.** On `PlannerInvocationError`, `plan_and_execute()`'s own loop
(`scripts/stage21_agent_planning.py:449-457`) appends a `PLANNER_INVOCATION_FAILED` finding, sets
`plan_status = "FAILED"`, transitions to `PlannerState.FAILED`, and breaks — there is no second
`plan()` call, no backoff, and no retry-related constant anywhere in Stage 21's own Constants section.
A concrete adapter therefore raises `PlannerInvocationError` exactly once per failed attempt, with the
understanding that Stage 21's own source treats that single failure as terminal for the current
`plan_and_execute()` invocation; this document defines no retry logic of its own, because none exists
in the contract it builds against (Planner Exception Translation, Design Decisions).

## Planner Configuration

### `ProviderSettings.extra` — interpreted here, for this seam only

Phase 1.1's own Configuration Model defines `ProviderSettings.extra: Dict[str, Any]` as a
"provider-specific, uninterpreted passthrough" that Phase 1.1 itself never interprets. Phase 1.4
interprets this field for the `PLANNER_LLM_PROVIDER` seam, exactly as Phase 1.2 already does for
`LLM_PROVIDER` and Phase 1.3 already does for `EMBEDDING_PROVIDER`. A concrete adapter's own factory
reads whichever of the following keys its own provider needs; no key is mandatory across every
concrete implementation, and a concrete implementation is free to define additional keys of its own:

```
extra = {
    "default_model_name":       "<deployment-level default model, if the deployment wants one>",
    "api_base_url":             "<optional endpoint override>",
    "request_timeout_seconds":  "<optional per-call SDK-level timeout>",
    "sdk_max_retries":          "<optional SDK-internal connection-level retry count>",
}
```

Nothing in Stage 21's own source names a closed set of `extra` keys for this seam — the set above is
illustrative, matching the same illustrative posture Phase 1.2 and Phase 1.3 already take for their
own `extra` interpretations.

### Provider-owned configuration vs. Stage 21's own planning configuration — the explicit line

| Concern | Owner |
|---|---|
| `model_name`, `temperature`, `max_plan_steps` for a given `plan_and_execute()` invocation | Stage 21's own `resolve_planning_config()`, exactly as already frozen (`scripts/stage21_agent_planning.py:197-218`) — clamped and defaulted there (`temperature` clamped to `[0.0, MAX_PLANNER_TEMPERATURE]`, `max_plan_steps` clamped to `[1, MAX_PLAN_STEPS]`), never re-defined, re-defaulted, or re-clamped here |
| `default_planner_model_name` | `AgentDependencies.default_planner_model_name: str` (line 60) — supplied by whatever assembles `AgentDependencies`, consumed by `resolve_planning_config()` as the fallback when `planning_config.get("planner_model_name")` is absent; not a `ProviderSettings.extra` concern this document interprets, since Stage 21's own source reads it from `AgentDependencies` directly, not from the adapter's own configuration |
| SDK client construction knobs (endpoint, SDK-level connection timeout, SDK-level connection retry count) | This document's own `extra` interpretation — provider-owned, never a Stage 21 concern, since `resolve_planning_config()` has no field for any of these |

**Model pinning.** Stage 21's own source states no model-pinning rule of any kind — no equivalent of
Stage 8's disallowed `"latest"` alias, and no statement on the subject anywhere in
`stage21_agent_planning.py`. This document therefore states neither a Stage-21-attributed rule nor an
independent recommendation of its own on this point; doing either without a source basis would be
either a fabricated citation or an unrequested addition beyond what the audit-replacement instruction
permits ("if the architecture is not explicitly supported by those files, do not invent it").

## Adapter Contract

Restated here by citation, not redefinition — Stage 21's own frozen `PlannerLLMAdapter`/
`PlannerInvocationError` contract (`scripts/stage21_agent_planning.py:31-46`):

```python
class PlannerInvocationError(Exception):
    """Raised by PlannerLLMAdapter on failure."""
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class PlannerLLMAdapter(ABC):
    @abstractmethod
    def plan(self, planner_prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes a planning-capable LLM with the given prompt.
        Returns a structured PlannerDecision. On failure, raises PlannerInvocationError."""
        pass
```

This document adds nothing to this contract's own public surface — no new abstract method, no new
required property, no changed signature. Everything Phase 1.4 defines (SDK client ownership, the
absence of an identity property, result-key ownership, `extra` interpretation, exception-raising
discipline) governs how a concrete subclass is built and configured; none of it is visible to Stage
21's own orchestration, which continues to see exactly the contract above and nothing more.

`plan()`'s signature above is synchronous request/response only, by Stage 21's own frozen design —
one call in, one `Dict[str, Any]` out, or one raised `PlannerInvocationError`. No concrete
implementation may widen this into a streaming, generator-based, or callback-based surface; doing so
would be a change to Stage 21's own frozen public contract, which is outside this document's authority
to make (Future Phase Boundaries).

## Validation

Two distinct, clearly-scoped groups, deliberately kept separate — mirroring the same discipline Phase
1.2 and Phase 1.3 already apply for their own seams:

**1. Construction-time validation** — a concrete adapter's own constructor (or factory) validates the
inputs it directly receives, before constructing its SDK client:

- `ProviderSettings.extra` carries whatever keys this specific provider requires — a missing required
  key is this concrete implementation's own error to raise, in whatever exception type is natural to
  it; this document mandates no closed vocabulary of construction-time error codes, since the set of
  possible concrete implementations, and their own required `extra` keys, is open-ended by design.
- If the provider requires a credential (`credential_ref` was present on `ProviderSettings`) and the
  resolved raw credential argument is `None` or empty, construction must fail — a concrete adapter
  never silently constructs an unauthenticated client when a credential was expected.

**2. Runtime validation** — remains exactly where Stage 21's own frozen contract already places it:
`validate_planner_decision()` (`scripts/stage21_agent_planning.py:129-145`) validates the dict returned
by `plan()` — checking `decision` is one of `("EXECUTE_STEP", "COMPLETE", "FAIL")`, and, for
`EXECUTE_STEP`, that `next_step` is a dict with a recognized `step_type` and a dict `step_input`. This
validation happens in `plan_and_execute()`, immediately after the `plan()` call
(`scripts/stage21_agent_planning.py:448`), and is not duplicated by this document. A concrete adapter's
own `plan()` is trusted to produce a dict Stage 21's own `validate_planner_decision()` can validate, or
to raise `PlannerInvocationError`; a dict that fails that validation raises `AgentPlanningInputError`
inside `plan_and_execute()` itself, caught there and mapped to the `PLAN_STEP_INVALID` finding
(`scripts/stage21_agent_planning.py:458-466`) — a failure mode this document does not intercept, own,
or duplicate.

There is no third, Phase-1.1-style "wiring-level" validation tier here — `build_provider_registry()`
and `wire_dependencies()` remain exactly as Phase 1.1 already froze them; this document supplies
inputs to that machinery (a `ProviderRegistration`) without adding a new validation tier of its own.

## Factory Contract

- **The factory function contract** — `Callable[[ProviderSettings, Optional[str]], PlannerLLMAdapter]`
  — exactly the signature Phase 1.1's own `ProviderRegistration.factory` field and
  `wire_dependencies()` contract already establish, structurally identical to Phase 1.2's own factory
  contract for `LLMAdapter`. A concrete implementation's factory: reads whatever keys it needs from
  `settings.extra`; performs Construction-time validation (above); constructs exactly one SDK client
  from the resolved raw credential (the second argument), if one was supplied; returns a fully
  constructed instance conforming to Stage 21's `PlannerLLMAdapter` contract; raises on any
  construction-time validation failure, in whatever exception type is natural to the concrete
  implementation — this document mandates no shared exception base class for construction failures,
  since Phase 1.1's own `wire_dependencies()` treats a factory's return value opaquely and propagates
  any exception a factory raises without inspecting its type.

- **The `ProviderRegistration` this document's implementations supply** — `seam="PLANNER_LLM_PROVIDER"`,
  a `provider_name` unique among registrations for that seam, `network_dependent` set truthfully by
  the concrete implementation (`True` for any adapter that opens a network socket during construction
  or during `plan()` — the expected case for essentially every real planning-capable LLM provider),
  and the factory described above. This document defines the shape of this registration; it does not
  itself call `build_provider_registry()` or assemble a list of registrations — that remains the
  application composition root's own job (Future Phase Boundaries).

- **`plan(self, planner_prompt: str, config: Dict[str, Any]) -> Dict[str, Any]`** — Stage 21's own
  frozen abstract method, restated here only to state a concrete implementation's own obligations
  against it: perform exactly one network call (or equivalent) to the provider (Planner Invocation
  Lifecycle's retry boundary); construct the provider's own native request from `planner_prompt` and
  the relevant fields of `config` (at minimum `model_name`, since `resolve_planning_config()` always
  supplies one); on success, return a dict satisfying Stage 21's own `validate_planner_decision()`
  requirements (Planner Result Ownership); on failure, raise `PlannerInvocationError` — Stage 21's own
  source names no other exception type `plan()` may raise.

No function architected under this document ever imports Phase 1.1's own internals, ever reads
`os.environ` directly (the resolved credential always arrives as an argument, never read from the
environment by this layer), or ever opens a network socket outside of what its own SDK client does on
its own provider's behalf.

## Planner Result Ownership

Stage 21's own `validate_planner_decision()` (`scripts/stage21_agent_planning.py:129-145`) is the
authoritative source for what a `plan()` return value must contain. This document states, per key, who
supplies it, whether the adapter copies or normalizes it, whether it is required or conditionally
required, and whether a missing value is acceptable — architecture only, no algorithm:

| Key | Supplied by | Copy or normalize? | Required/Conditional | Missing value acceptable? |
|---|---|---|---|---|
| `decision` | The provider's own planning output, **normalized by the adapter** into one of Stage 21's three closed strings | Normalized, never copied verbatim from an arbitrary provider vocabulary | Required — `validate_planner_decision()` raises `AgentPlanningInputError` if absent or not one of `("EXECUTE_STEP", "COMPLETE", "FAIL")` | No |
| `next_step` | The provider's own proposed next action, mapped by the adapter into Stage 21's own step shape (`step_type`, `step_input`, optionally `step_rationale`) | Normalized | Required only when `decision == "EXECUTE_STEP"`; absent or wrong-shaped otherwise raises `AgentPlanningInputError` (line 138-140) | Yes, when `decision != "EXECUTE_STEP"` |
| `next_step.step_type` | The adapter's own normalization of the provider's proposed action into one of Stage 21's four closed step types (`"QUERY_PIPELINE"`, `"CONVERSATION_MEMORY"`, `"CONVERSATION_APPEND"`, `"TOOL_INVOCATION"`) | Normalized, never a provider-native action name passed through verbatim | Required when `next_step` is present | No — `validate_planner_decision()` raises `AgentPlanningInputError` on an unrecognized value (line 143) |
| `next_step.step_input` | The adapter's own construction, from whatever arguments the provider's planning output specifies for the chosen step | Adapter-constructed | Required when `next_step` is present (must be a dict) | No (line 144-145) |
| `next_step.step_rationale` | The adapter's own optional annotation, if it chooses to supply one | Adapter-supplied, passed through by `execute_plan_step()` via `.get("step_rationale", "")` (line 501) | Optional | Yes — Stage 21 itself defaults to `""` when absent |
| `final_answer_step_index` | The adapter's own indication of which prior executed step's result should serve as the final answer, read via `.get("final_answer_step_index")` (line 471) | Adapter-supplied | Optional, meaningful only when `decision == "COMPLETE"` | Yes — `plan_and_execute()` treats a missing or out-of-range value as "no final response" (line 472) |

**Decision Normalization.** A provider's own native planning-output vocabulary (whatever labels or
structure that specific SDK or prompting scheme uses) is never exposed outside the adapter as `decision`
under any circumstance. The adapter alone owns normalizing the provider's own signal into exactly one
of Stage 21's three closed values — `EXECUTE_STEP`, `COMPLETE`, `FAIL` — before returning. Stage 21's
own orchestration only ever sees the normalized value; it never inspects a provider-native string
(mirroring the same discipline Phase 1.2's own Finish Reason Normalization applies one seam over).

**Step Type Normalization.** The same discipline applies to `next_step.step_type`: the adapter
normalizes whatever the provider's own planning output names as the next action into one of Stage
21's four closed step types. Stage 21's own `validate_planner_decision()` and `validate_plan_step()`
reject any other value outright.

**Structural Ownership.** Before returning from `plan()`, the adapter is responsible for ensuring the
dict it constructs satisfies Stage 21's own structural contract, per the table above. Stage 21's own
`validate_planner_decision()` validates the returned dict once received; this document assigns no new
validation tier of its own — the adapter owns constructing a structurally valid dict; Stage 21 owns
validating it. No validation algorithm is defined here.

**No dataclass, no `RawLLMResult` analog.** Unlike Stage 13's `RawLLMResult`, Stage 21's own source
defines no typed result class for a planner invocation's output. This document does not introduce one
— doing so would imply a Stage 21 contract that does not exist, and would itself be a new public API
this document is forbidden from inventing.

## Planner Exception Translation

**The exception boundary, stated explicitly.** Provider-native SDK exception types never cross the
adapter boundary, under any circumstance — Stage 21's own orchestration only ever sees
`PlannerInvocationError`, never a raw SDK-specific exception class. This mirrors the same discipline
Phase 1.2's own Failure Handling states for `LLMAdapter`, adapted to Stage 21's own, narrower,
single-exception-type contract:

- **`PlannerInvocationError(message: str, code: str)`** — the only exception type Stage 21's own
  `plan()` docstring names. A concrete adapter translates any provider-native SDK exception
  encountered during `plan()` into this single type, supplying whatever `message` and `code` values
  are meaningful for that concrete implementation's own diagnostics. Stage 21's own source defines no
  closed vocabulary for the `code` field's values — `plan_and_execute()` catches
  `PlannerInvocationError` as a single type (line 449) and never branches on `code` (the `code`
  attribute is read nowhere in `stage21_agent_planning.py` beyond the constructor that sets it); this
  document therefore does not mandate a closed set of `code` values, since Stage 21's own source
  neither defines nor consumes one.
- **No transient/non-retryable distinction exists in the source.** Unlike Stage 13's four-member
  vocabulary, which lets Stage 13's own Retry Policy distinguish retryable from non-retryable
  failures, `PlannerInvocationError` is Stage 21's only planner-adapter exception type, and
  `plan_and_execute()` treats every occurrence of it identically — as an immediate, terminal
  `PLANNER_INVOCATION_FAILED` finding (line 450-457), regardless of whatever underlying cause a
  concrete adapter's own `code` field might describe. This document does not invent a retryable
  category the source does not act on.
- **The retry boundary, restated here in full.** One `plan()` call is exactly one provider invocation
  attempt (Planner Invocation Lifecycle). A raised `PlannerInvocationError` is terminal for the current
  `plan_and_execute()` invocation — Stage 21's own source calls `plan()` no further times after that
  exception is caught. The adapter itself never re-attempts the call before raising, and never
  implements backoff, a retry count, or a retry ceiling of its own; doing so would not be filling a gap
  Stage 21 leaves for someone else to own, since Stage 21's own source defines no retry step for a
  concrete implementation, or anyone else, to defer to.
- **No fallback provider, no silent degradation.** If a concrete adapter's construction fails, or if
  `plan()` raises `PlannerInvocationError`, the failure propagates exactly as Stage 21's own
  `plan_and_execute()` already handles it — never a silent substitution of a different provider or a
  degraded, partially computed decision.

## Determinism

**Deterministic (guaranteed, given identical input):**

- Whether construction-time validation passes or fails, given identical `(ProviderSettings,
  Optional[str])` inputs.
- **Decision-vocabulary normalization outcome.** Whether a given provider-native planning signal maps
  to `EXECUTE_STEP`, `COMPLETE`, or `FAIL` is a fixed function of that concrete implementation's own
  normalization logic, applied consistently.

**Explicitly NOT deterministic (inherent to a real provider; never assumed, never hidden):**

- **The provider's own planning decision content** — `next_step.step_input`, `step_rationale`, which
  step type is chosen, and whether the provider decides to `COMPLETE`, `FAIL`, or continue — all
  reflect the model's own generated output, the same category of non-determinism Phase 1.2's own
  Determinism section already states for `response_text`, extended here to planning decisions.
- **Latency.** Wall-clock by definition, excluded from every determinism comparison.
- **SDK client construction side effects.** A real SDK client may perform its own connection setup or
  credential validation against a live endpoint at construction time; this document makes no claim
  about what a specific SDK does internally during Planner Invocation Lifecycle step [2].

**No `config_fingerprint_fields` analog exists in this document, because Stage 21's own source defines
none.** `stage21_agent_planning.py` has no persisted artifact tied to a planner invocation and no
config-fingerprint concept of any kind on `PlannerLLMAdapter`. Introducing one here would be inventing
a contract Stage 21's own frozen source does not support.

## Read-Only Guarantees

- Phase 1.4 never modifies `manifest.json`, any corpus artifact, any vector index, any embedding, any
  prompt template, or any cache store entry — it has no relationship to any of them at all.
- A concrete adapter never modifies `ProviderSettings` after receiving it — it reads from `extra` and
  `credential_ref`/the resolved credential, never mutates either.
- A concrete adapter never modifies the `planner_prompt` or `config` it receives on `plan()` — it
  reads from them to construct its own native request, never mutating the caller's own objects. In
  particular, since `config` is the same dict object across every `plan()` call within one
  `plan_and_execute()` invocation (Planner Invocation Lifecycle), a concrete adapter must never mutate
  it — doing so would corrupt every subsequent `plan()` call within that same planning loop.
- A concrete adapter holds no module-level mutable state of its own; every piece of state it needs
  (its SDK client) lives on the constructed instance itself, never in a module-level variable shared
  across instances.
- The only external side effects an SDK client may perform are whatever its own provider's SDK does on
  its own behalf (a network call) — this document defines no additional side effect of its own beyond
  what Planner Invocation Lifecycle step [2] and step [4] already name.

## Security Considerations

- **Credential consumption.** A concrete adapter's factory receives the resolved raw credential as its
  second positional argument, exactly as Phase 1.1's `wire_dependencies()` contract already supplies
  it. The factory consumes this value exactly once, at construction time, to build its SDK client; it
  retains no separate copy of the raw string after construction — the SDK client itself becomes the
  credential's sole holder, matching Phase 1.1's own Security Considerations and Phase 1.2's/Phase
  1.3's own corrected shape.
- **SDK client as sole credential holder.** After construction, only the SDK client instance held by
  the adapter carries the credential. No field on the adapter instance itself, and no field on any
  object this document defines, stores the raw credential as a plain, independently-readable value.
- **No credential serialization.** The resolved raw credential is never converted to JSON, a dict, or
  any other serializable form by this document's own architecture, for logging, caching, or transport.
- **No credential persistence.** Nothing this document architects writes the resolved raw credential
  to disk, to a cache store, to the manifest, or to any artifact of any kind.
- **No credential logging.** A concrete adapter never logs, prints, or serializes the resolved raw
  credential argument, at any severity, under any circumstance.
- **`planner_prompt` content, inherited.** `planner_prompt` is a canonical-JSON serialization of
  `planner_context` (`build_planner_prompt()`, line 264-266), which itself embeds the original
  `agent_request["query"]`, conversation memory (if any), and prior executed-step results — any of
  which may already carry adversarial content from upstream corpus injection or user input, the same
  accepted, documented risk Stage 13's own Security Considerations already state for `system_prompt`/
  `user_prompt`. A concrete adapter performs no additional sanitization on the outbound request; that
  risk passes through unchanged.
- **Untrusted planning output, inherited.** The dict returned by `plan()` is opaque, model-generated
  content that Stage 21's own `execute_plan_step()` subsequently acts on (dispatching tool invocations,
  pipeline queries, and conversation operations named by `next_step`). A concrete adapter's own `plan()`
  implementation never interprets, executes, or acts on this content itself beyond returning it
  verbatim — whatever downstream trust decisions Stage 21 makes about executing a planner-named step
  are Stage 21's own, entirely outside this document's authority to change.
- **No network isolation guarantee.** A concrete adapter architected under this document opens a real
  network socket to its provider's own endpoint for essentially every real implementation. This
  document makes no claim that such an adapter is network-isolated; it only guarantees that the
  *credential* reaching that socket is handled exactly as described above.

## Logging Vocabulary

This section defines the vocabulary available to a concrete adapter **if** it emits logs; exactly like
Phase 1.1's, Phase 1.2's, and Phase 1.3's own Logging Vocabulary sections, it does not mandate that
logging occur.

This document introduces no new `stage` identifier and no new closed-vocabulary log codes. A concrete
adapter operates inside Stage 21's own runtime; whatever closed logging vocabulary Stage 21's own
document defines for a planner-invocation outcome (including `PLANNER_INVOCATION_FAILED`, the finding
code `plan_and_execute()` itself appends on a caught `PlannerInvocationError`, line 450-454) remains
Stage 21's own to own and extend, never this document's.

A concrete adapter that wishes to emit its own internal diagnostic information may do so at DEBUG
severity or below, subject to the same hard constraint stated in Security Considerations: it may never
include the resolved raw credential, any raw `planner_prompt` content, or any raw planning-decision
content beyond what Stage 21's own logging discipline already permits.

## Concurrency

Stage 21's own source gives no explicit statement, in `stage21_agent_planning.py`, about whether
`plan_and_execute()` itself is safe to call concurrently, or whether a single `AgentDependencies`
(and the `planner_llm_adapter` it carries) is shared across concurrent `plan_and_execute()`
invocations. This document does not assert a concurrency guarantee Stage 21's own source does not
state.

A concrete adapter instance is constructed exactly once (Planner Invocation Lifecycle step [2]) and
its `plan()` method may be called repeatedly over its lifetime (step [4]), including, if a caller
shares one adapter instance across multiple `plan_and_execute()` invocations, concurrently — but
whether that is safe is a property of the specific SDK client a concrete implementation wraps, never
something this architecture can guarantee on that SDK's behalf. A concrete implementation that wraps a
thread-safe SDK client inherits that safety; one that wraps a non-thread-safe client does not.

Phase 1.4 defines no locking, no mutex, and no coordination of its own beyond what Planner Invocation
Lifecycle already describes.

## Design Decisions

1. **This architecture is provider-neutral by construction, not by convention.** Every section above
   is written to hold for any concrete `PlannerLLMAdapter` implementation — any vendor — because the
   set of planning-capable providers this repository may eventually support is open-ended. Naming a
   provider anywhere in this document is illustrative only, never load-bearing.

2. **No adapter-identity property is introduced, because Stage 21's own contract declares none.**
   Phase 1.2 and Phase 1.3 each define an identity concept because their own frozen contracts
   (`LLMAdapter.provider_name`, the embedding provider's identity triple) require one. `PlannerLLMAdapter`
   requires nothing of the kind. Inventing one here — even one modeled on Phase 1.2's adapter-identity/
   request-identity split — would state a Stage 21 contract that does not exist, misleading a future
   implementer into believing Stage 21's own orchestration reads or depends on it.

3. **No typed result dataclass is introduced, because Stage 21's own contract returns an untyped
   `Dict[str, Any]`, validated externally.** Stage 13's `RawLLMResult` and Stage 8's own return shape
   are each typed by their own frozen contracts; Stage 21's is not. Matching the source's own looser
   typing here, rather than imposing a `PlannerInvocationResult`-style dataclass this document would
   have to invent, keeps this document's claims falsifiable against the actual shipped code.

4. **No multi-member exception vocabulary or transient/non-retryable split is introduced, because
   `PlannerInvocationError` is Stage 21's only planner-adapter exception type and
   `plan_and_execute()` does not branch on its `code` field.** Introducing a Stage-13-style four-member
   vocabulary here would misrepresent Stage 21's actual, narrower failure-handling behavior — a single
   caught exception type, treated identically regardless of cause, terminal for the current
   `plan_and_execute()` invocation.

5. **No retry policy is introduced, because Stage 21's own source implements none.** Given how easily
   a "provider adapter" document could drift into inventing a retry story for symmetry with Phase 1.2,
   this document states directly, and confirms against the actual loop body
   (`scripts/stage21_agent_planning.py:446-457`), that a single `PlannerInvocationError` is terminal —
   there is no retry budget, no backoff schedule, and no second `plan()` call to defer ownership of to
   any future actor. Asserting one would misstate the source's own frozen behavior.

6. **No model-pinning recommendation is stated, because neither Stage 21 nor any prior phase's document
   supplies a source basis for one here.** Phase 1.2 was able to add its own operational recommendation
   because Stage 8's contract already established the underlying reasoning (a disallowed floating
   alias) for an analogous seam; no comparable statement exists anywhere for the planner seam. Adding
   one anyway would be an unrequested addition beyond what deriving architecture "only" from the named
   sources permits.

7. **No shared exception base class is mandated for construction-time failures**, for the same reason
   Phase 1.2 and Phase 1.3 already give for their own seams: Phase 1.1's own `wire_dependencies()`
   already treats a factory's exceptions opaquely, so mandating a hierarchy here would add a
   cross-cutting contract neither Stage 21 nor Phase 1.1 asked for.

8. **SDK client ownership follows Phase 1.2's and Phase 1.3's own established shape without
   modification**, since nothing about Stage 21's contract changes the underlying reasoning: the
   client is this document's own to construct and dispose of; it never escapes the adapter instance;
   neither Phase 1.1 nor Stage 21 ever holds it.

## Constants

```python
# This document defines no numeric threshold, ceiling, or default of its own — DEFAULT_MAX_PLAN_STEPS,
# MAX_PLAN_STEPS, DEFAULT_PLANNER_TEMPERATURE, and MAX_PLANNER_TEMPERATURE all remain Stage 21's own
# constants (scripts/stage21_agent_planning.py:14-17), exactly as already frozen. SDK-level timeout,
# SDK-level connection retry count, and any per-provider ceiling are ProviderSettings.extra values a
# concrete implementation interprets for itself (Planner Configuration). Provider-neutrality (Design
# Decisions #1) means this document names no closed set of provider identifiers or model names — that
# set is open-ended by design.

PLANNER_LLM_PROVIDER_SEAM_NAME = "PLANNER_LLM_PROVIDER"  # already Phase 1.1's own constant, restated
                                                          # here only to name which seam this document
                                                          # concerns; not a new constant this document
                                                          # introduces or owns.
```

No numeric threshold, ceiling, or default belonging to Stage 21 or Phase 1.1 is duplicated here — every
one of them already lives, exactly once, in the document that owns it.

## Complexity

- **Construction (factory invocation, Planner Invocation Lifecycle step [2])** — O(1) from this
  document's own perspective; the actual cost of a specific SDK client's own construction is that
  SDK's own concern.
- **`plan(planner_prompt, config)`** — O(1) from this document's own perspective (one network call,
  one result mapping); the actual cost of that one call — including its size-dependent latency, which
  grows with `planner_prompt`'s own size as `planner_context["executed_steps"]` accumulates across a
  planning loop — is entirely that provider's own concern, never something this document estimates on
  a specific SDK's behalf.
- **Result-dict construction, per call** — O(1), a fixed, small number of key reads and writes.

## Known Limitations

- **No cross-provider abstraction beyond `PlannerLLMAdapter` itself.** This document does not define a
  shared internal base class, mixin, or helper library that concrete implementations must use — each
  is free to structure its own internals however it needs to, as long as the outward
  `PlannerLLMAdapter` contract is satisfied.
- **No credential rotation support**, mirroring Phase 1.1's, Phase 1.2's, and Phase 1.3's own named
  limitation: a credential consumed once at construction time is used for the constructed SDK client's
  entire lifetime; live rotation, if a provider requires it, is that concrete implementation's own
  concern.
- **No retry, by design of the source this document builds against, not by omission.** Because Stage
  21's own `plan_and_execute()` implements no retry of a failed planner invocation, a single transient
  failure (a timeout, a rate limit) is architecturally indistinguishable, at the Stage 21 level, from a
  permanent one — both raise `PlannerInvocationError` and both are terminal for the current
  `plan_and_execute()` invocation. This document does not resolve that limitation, because doing so
  would require modifying Stage 21's own frozen orchestration, which is outside this document's
  authority.
- **No response caching of any kind.** This document defines no cache in front of `plan()`.
- **No adapter-level identity for diagnostics or multi-adapter disambiguation.** Since
  `PlannerLLMAdapter` declares no identity property, a caller holding multiple concrete instances (for
  example, across different `AgentDependencies` in a multi-tenant deployment) has no contract-level way
  to distinguish them beyond object identity itself, unless a concrete implementation adds its own
  attribute for that purpose — an addition this document permits but does not require or standardize.

## Future Phase Boundaries

This document defines the architecture for a concrete planner provider implementation. Two categories
of excluded work follow, kept explicitly separate because they differ in kind, not just in content —
mirroring Phase 1.2's and Phase 1.3's own corrected boundary: Category A is deferred to a future actor;
Category B has no actor, ever.

**Category A — deferred composition-root and future-phase responsibilities.** Each item below is real
future work, explicitly reserved for the application composition root Phase 1.1 already names — it
will eventually be done, just not by this document:

- **Editing `ProviderRegistry` and performing dependency wiring of any kind.** This document defines
  the shape of a `ProviderRegistration` a concrete implementation supplies; it does not itself call
  `build_provider_registry()` or `wire_dependencies()` — assembling the full list of registrations and
  performing the wiring call remains the composition root's own job.
- **Implementing a Streamlit UI or any other network-facing API or UI.** An application-layer concern,
  never designed here.
- **Implementing the application composition root itself.** The layer that actually calls
  `load_raw_settings → validate_settings → build_provider_registry → wire_dependencies`, holds the
  resulting `WiringResult`, and assembles `AgentDependencies.planner_llm_adapter` — not designed here.
- **Sharing underlying client plumbing with a Phase 1.2 concrete `LLMAdapter` implementation.** Phase
  1.1's own Future Phase Boundaries already anticipate this ("may share underlying client plumbing
  with Phase 1.2's own implementation without sharing its public contract") — this document does not
  design, extend, or require that sharing; it is a future implementation choice, not an architectural
  requirement stated here.
- **Introducing an identity property, a typed result dataclass, a multi-member exception vocabulary,
  or a retry policy onto `PlannerLLMAdapter` itself.** Each would require a new design pass against
  Stage 21's own frozen contract — expanding what `PlannerLLMAdapter` declares, not merely building a
  concrete implementation underneath it. This document explicitly declines to do so (Provider
  Identity, Planner Result Ownership, Planner Exception Translation, Retry Ownership), leaving that
  decision, if ever made, to a future revision of Stage 21 itself — never to this document or to any
  concrete implementation architected under it.
- **Introducing streaming or conversation state on the planner adapter itself.** Stage 21's own
  `plan()` signature is synchronous request/response only; conversation state, where it exists in this
  pipeline, is owned by `AgentDependencies.get_conversation`/`select_memory`/`append_turn`, never by
  `planner_llm_adapter`. Introducing either onto the planner adapter would require expanding Stage 21's
  own frozen contract.

**Category B — permanent frozen-stage prohibitions, not composition-root or future-phase work.** Each
item below is never performed by any actor, at any future point, by anyone — this is not deferred work
waiting on a future phase; it is a permanent boundary that exists because Stage 21 is frozen:

- **Modifying Stage 21's own `PlannerState` machine, `plan_and_execute()`'s own loop, or any of its own
  validation functions (`validate_agent_request`, `validate_planner_decision`, `validate_plan_step`,
  `validate_agent_result`).** Untouched and unduplicated by this document or by any concrete
  implementation architected under it, permanently — not a task any future actor ever takes on.
- **Constructing `planner_context` or `planner_prompt`.** `build_initial_context()` and
  `build_planner_prompt()` remain Stage 21's own frozen responsibility, permanently — this document's
  own adapters only ever receive an already-assembled `planner_prompt: str` via `plan()`'s own
  parameter, and interpret it no further than Stage 21 itself does.

Every stage from Stage 0 through Stage 21, Phase 1.1 in full, Phase 1.2 in full, and Phase 1.3 in full,
remain exactly as independently usable, and exactly as frozen, as they already are today. Phase 1.4
adds a way to *build* what the `PLANNER_LLM_PROVIDER` seam already knows how to receive — it adds
nothing Stage 21 or Phase 1.1 must call differently, and nothing they must change to receive it.
