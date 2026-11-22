# Stage 21 — Agent Planning

Stages 0–20 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 21 is the highest orchestration layer in this pipeline — the planning and decision layer that
sits above every existing stage and coordinates their use to answer a user's request. Given an
`AgentRequest`, it decides whether the request can be answered directly via the existing query
pipeline (Stages 10–18), whether conversation memory should be consulted (Stage 19), whether one or
more tools should be invoked (Stage 20), in what order those operations should execute, and when
planning is complete and the final result should be returned to the caller.

Stage 21 **never executes work itself**. It plans work. Every act of retrieval, context assembly,
prompt construction, LLM execution, citation extraction, groundedness validation, answer quality
evaluation, response caching, API serving, conversation memory management, and tool execution remains
exactly what its own frozen stage already computed, untouched. Stage 21 only decides *what* to call,
*when* to call it, and *whether* the result is sufficient — then delegates the actual execution to
the stage that owns it.

`plan_and_execute(agent_request, agent_dependencies)` is the sole public entrypoint.

Stage 21 mirrors the adapter-based abstraction pattern established by every prior stage — defining
abstract contracts for its own dependencies without selecting, importing, or depending on any
concrete implementation, SDK, or external service. The dependencies it coordinates (Stage 18's
`handle_request`, Stage 19's conversation functions, Stage 20's `execute_tool`, and an LLM for
planning decisions) are all supplied by the caller as pre-configured contracts.

## Scope

Stage 21 answers exactly one question — given an agent request describing a user's intent and the
available capabilities (query pipeline, conversation memory, tools), what is the complete, correct
execution plan to produce the best possible response — and stops there. It never performs retrieval
(Stage 10's frozen job); never assembles context (Stage 11's frozen job); never constructs a prompt
(Stage 12's frozen job); never invokes an LLM for answer generation (Stage 13's frozen job, via
Stage 17/18); never extracts citations (Stage 14's frozen job); never validates groundedness
(Stage 15's frozen job); never evaluates answer quality (Stage 16's frozen job); never makes caching
decisions (Stage 17's frozen job); never serves an API (Stage 18's frozen job); never stores
conversation turns (Stage 19's frozen job); never invokes a tool (Stage 20's frozen job). It only
coordinates those stages.

### Stage 18 Ownership Boundary

Stage 21 is the top-level orchestration entrypoint; Stage 18 is a subordinate execution stage.
- **Invocation direction:** Stage 21 invokes Stage 18 (via `handle_request()`). Stage 18 never invokes Stage 21.
- **Lifecycle boundary:** Stage 18's lifecycle begins when Stage 21 calls it and ends when it returns an `APIResponse` to Stage 21. Stage 18 has no awareness of the agent planner, tools, or conversation memory.
- **No overlapping responsibilities:** Stage 21 plans and delegates; it never generates answers. Stage 18 generates answers (by orchestrating Stages 10–17); it never plans, manages memory, or invokes tools.

### Tool Invocation Boundary

Stage 21 decides *whether* a tool should be invoked and determines the invocation order. Stage 21 never invokes tools directly. It delegates every tool execution entirely to Stage 20 via `execute_tool()`.

## Responsibilities

Stage 21 shall: receive an `AgentRequest` and an `AgentDependencies` bundle; structurally validate
the request before use; assess the request to determine which capabilities are needed; generate a
deterministic `AgentPlan` describing the ordered sequence of `PlanStep`s to execute; execute each
plan step by delegating to the appropriate frozen stage; evaluate each step's result to determine
whether the plan is complete, needs additional steps, or has failed; track planner state through a
deterministic state machine; accumulate planner findings throughout the planning lifecycle; validate
every returned `AgentResult`'s internal invariants before returning; and return an immutable
`AgentResult` containing the final answer, all intermediate results, the complete executed plan, and
all findings.

## Non-Responsibilities

Stage 21 explicitly does **not** perform, and no future patch to this stage may silently add without
a new design pass: retrieval, embedding, reranking, or any change to how a document is found (Stage
10's frozen job); context assembly or budget enforcement (Stage 11's frozen job); prompt construction
or template rendering (Stage 12's frozen job); direct LLM invocation for answer generation — every
generation call is made exclusively through Stage 18's own `handle_request()`, itself calling the
frozen pipeline chain (Stages 10–17); cache-worthiness or freshness decisions (Stage 17's frozen
job); citation extraction, matching, or re-attachment (Stage 14's frozen job); groundedness
re-verification (Stage 15's frozen job); answer-quality re-scoring (Stage 16's frozen job);
conversation storage or turn management (Stage 19's frozen job — Stage 21 calls `select_memory()` to
read and `append_turn()` to write, but never manages the store itself); tool execution (Stage 20's
frozen job — Stage 21 constructs `ToolRequest`s and delegates to `execute_tool()`); choosing,
importing, or depending on any concrete tool implementation, SDK, or external service; retrying a
failed downstream stage invocation beyond what that stage's own frozen retry policy already provides
(Stage 13 owns LLM retries; no other stage retries); timeout enforcement (each stage owns its own
timeout boundary); sanitizing, interpreting, or semantically validating tool output (Stage 20's
structural-only validation boundary is inherited); streaming partial results of any kind.

## Inputs

Two required inputs, both supplied by the caller:

- **`AgentRequest`** (this stage's own new schema, see Schemas) — per-call, the sole source of the
  user's query, conversation context, tool preferences, and planning configuration.
- **`AgentDependencies`** (this stage's own new schema, see Configuration) — per-deployment, supplied
  once at wiring time: pre-configured entrypoints to Stage 18 (`handle_request`), Stage 19
  (conversation functions), Stage 20 (`execute_tool`, `ToolRegistry`, `ToolAdapter`), and a
  `PlannerLLMAdapter` for planning decisions.

No other input is read. `manifest.json`, `chunks.json`, `metadata.json`, vector indexes, embeddings,
prompt templates, cache stores, and every earlier-stage artifact are never opened — Stage 21 operates
exclusively on its own `AgentRequest` input and the pre-configured dependencies it coordinates. No
PDF is ever reopened; no corpus artifact is ever read.

## Outputs

`AgentResult` (see Schemas) is Stage 21's sole return value — never persisted by Stage 21 itself as a
distinct artifact, matching the zero-artifact posture every prior query-time stage (Stage 10 onward)
already established for their own in-memory return values. Whether and how a caller persists, logs, or
surfaces an `AgentResult` is explicitly that caller's own concern, never Stage 21's.

## Planning Model

### Planning Decisions

Stage 21 makes exactly three categories of decisions:

1. **Capability selection** — given the user's query and available context, which capabilities
   (query pipeline, conversation memory, tools) should be invoked, and in what order?
2. **Sufficiency evaluation** — given the results of executed steps, is the plan complete, or are
   additional steps needed?
3. **Termination** — has a stop condition been reached (success, failure, or step limit)?

These decisions are made by a `PlannerLLMAdapter` — a planning-specific LLM invocation that receives
a structured planning prompt and returns a structured planning decision. Stage 21 constructs the
planning prompt deterministically from the current planner state; the LLM's decision is the one
non-deterministic element (see Determinism).

### Plan

An `AgentPlan` is an ordered sequence of `PlanStep`s, built incrementally. Stage 21 does not
generate the entire plan upfront — it generates one step at a time, executes it, evaluates the
result, and then decides the next step. This is a deliberate, incremental planning model:

- **Step 0** is always the initial assessment: examine the request and decide the first action.
- **Steps 1–N** are generated one at a time, each informed by the results of all preceding steps.
- **The plan is complete** when a stop condition is met (see Stop Conditions).

### PlanStep

A `PlanStep` represents one atomic action the planner has decided to take:

```jsonc
{
  "step_index": 0,                              // 0-indexed, monotonically increasing, contiguous
  "step_type": "QUERY_PIPELINE",                // closed vocabulary — see Step Types
  "step_rationale": "User query requires...",   // the planner's stated reason for this step;
                                                // informational only, never interpreted by Stage 21
  "step_input": { ... },                        // step-type-specific input; see Step Types
  "step_result": { ... },                       // populated after execution; null before
  "step_status": "PENDING",                     // PENDING | EXECUTING | COMPLETED | FAILED
  "step_findings": [],                          // findings from this step's execution
  "started_at": null,                           // wall-clock; excluded from determinism
  "completed_at": null                          // wall-clock; excluded from determinism
}
```

### Step Types

Stage 21 defines a closed vocabulary of step types — one per frozen stage it coordinates:

| Step type | Delegates to | Input constructed from | Result captured as |
|---|---|---|---|
| `QUERY_PIPELINE` | Stage 18 `handle_request()` | `AgentRequest.query`, planner-selected options | `APIResponse` |
| `CONVERSATION_MEMORY` | Stage 19 `select_memory()` | `AgentRequest.conversation_id`, selection config | `ConversationMemoryPackage` |
| `CONVERSATION_APPEND` | Stage 19 `append_turn()` | Completed turn (user query + assistant response) | `ConversationState` |
| `TOOL_INVOCATION` | Stage 20 `execute_tool()` | Planner-constructed `ToolRequest` | `ToolExecutionRecord` |

No other step type exists. Stage 21 never invokes a frozen stage through any mechanism other than
the step types listed above — there is no "raw" stage call, no "custom" step type, and no escape
hatch that bypasses the plan.

**Conversation Append Guarantees:**
- Conversation append occurs **only** when represented as an explicit `CONVERSATION_APPEND` plan step.
- It never occurs implicitly.
- It never occurs automatically after a successful execution of any other step.

### Planner State Machine

The planner progresses through a deterministic state machine:

```
INITIALIZING → PLANNING → EXECUTING → EVALUATING → [PLANNING | COMPLETED | FAILED]
```

| State | Meaning | Valid Transitions To | Invalid Transitions |
|---|---|---|---|
| `INITIALIZING` | Validating the `AgentRequest` and preparing planner context | `PLANNING`, `FAILED` | Any other state |
| `PLANNING` | Deciding the next step via the `PlannerLLMAdapter` | `EXECUTING`, `COMPLETED`, `FAILED` | `INITIALIZING`, `EVALUATING` |
| `EXECUTING` | Delegating the current step to its frozen stage | `EVALUATING` | Any other state |
| `EVALUATING` | Assessing the step's result to decide next action | `PLANNING`, `COMPLETED`, `FAILED` | `INITIALIZING`, `EXECUTING` |
| `COMPLETED` | A stop condition has been met successfully | Terminal | Any transition out |
| `FAILED` | An unrecoverable failure has occurred | Terminal | Any transition out |

The state machine is deterministic given identical planner decisions — the same sequence of LLM
planning responses produces the same state transitions. The planner never skips a state, never
transitions backwards (except the `EVALUATING → PLANNING` loop for multi-step plans), and never
enters a state without having completed the preceding one.

### Stop Conditions

The planner terminates when any of these conditions is met. These are the **only** terminal outcomes:

1. **COMPLETE: Success.** The planner's sufficiency evaluation determines that the executed steps have produced
   a satisfactory result. This is the normal completion path.
2. **STEP_LIMIT_REACHED: Step limit reached.** The total number of executed steps reaches `MAX_PLAN_STEPS`. This prevents
   unbounded planning loops. The result is returned with a `PLAN_STEP_LIMIT_REACHED` WARNING finding
   and whatever partial results have been accumulated.
3. **FAIL: All steps failed.** Every executed step has `step_status == "FAILED"` and the planner determines
   no further action is possible. The result is returned with `status == "FAIL"`.
4. **FAIL: Planner failure.** The `PlannerLLMAdapter` itself fails (raises an exception) and cannot produce
   a planning decision. The result is returned with `status == "FAIL"` and a
   `PLANNER_INVOCATION_FAILED` finding.
5. **FAIL: Invalid plan step.** The planner produces a step that fails structural validation (unknown step
   type, malformed step input). The result is returned with `status == "FAIL"` and a
   `PLAN_STEP_INVALID` finding.
6. **FAIL: Unrecoverable invariant failure.** An internal invariant is violated (e.g., mismatching indices or unsupported planner state). `AgentPlanningInternalError` is raised.

### Execution Graph

Stage 21's execution graph is a **linear sequence**, not a DAG or tree. Steps execute one at a time,
in order, with each step's result available to inform the next step's planning decision. This matches
Stage 20's own single-invocation model (one tool call at a time) and is a deliberate simplification:

- **Execution strictly follows plan order.** No hidden insertion, no hidden removal, and no implicit reordering of steps.
- **No undeclared steps.** Stage 21 never executes a step that was not explicitly produced by the planner.
- **No parallel execution** within a single plan.
- **No branching (if/else)** within a plan.
- **No fan-out/fan-in** within a plan.
- The planner can achieve conditional behavior by evaluating step results and choosing different next
  steps — but the execution model itself is always sequential.

Multi-step parallelism, branching, and fan-out are explicitly excluded from Stage 21's scope and
would require a new design pass to introduce.

### Plan Immutability

- **Completed steps never change.** Once a step is executed, its `step_result` and `step_status` are permanently captured.
- **Completed history remains immutable.** Future planning iterations may append new steps, but previous executed steps are never rewritten, removed, or modified.

## Schemas

All in-memory Python structures — none persisted, no file format to version.

### AgentRequest

```jsonc
{
  "query": "What are the SDG financing gaps?",  // required, non-empty string — the user's question
  "conversation_id": null,                       // optional; if present, conversation memory is consulted
  "tool_preferences": {                          // optional; governs tool availability for this request
    "enabled": true,                             // whether tools may be invoked at all; default true
    "allowed_tools": null                        // null = all registered tools; list = explicit allow-list
  },
  "planning_config": {                           // optional; governs planner behavior
    "max_plan_steps": null,                      // null = DEFAULT_MAX_PLAN_STEPS
    "planner_model_name": null,                  // null = default planner model from AgentDependencies
    "planner_temperature": null                  // null = DEFAULT_PLANNER_TEMPERATURE
  },
  "pipeline_options": {                          // optional; forwarded verbatim to Stage 18's APIRequest
    "top_k": null,
    "context_budget_tokens": null,
    "template_version": null,
    "prompt_budget_tokens": null,
    "model_name": null,
    "temperature": null,
    "max_output_tokens": null,
    "timeout_seconds": null,
    "max_retry_attempts": null,
    "cache_ttl_seconds": null,
    "citation_match_threshold": null,
    "groundedness_threshold": null
  }
}
```

**Field justification:**
- `query`: the user's question; required for every plan.
- `conversation_id`: enables conversation-aware planning; if present, Stage 19 is consulted for
  memory before the first query pipeline invocation.
- `tool_preferences`: governs whether and which tools the planner may consider; structural guard,
  never a semantic evaluation.
- `planning_config`: tunes the planner's own behavior; every field has a documented default.
- `pipeline_options`: forwarded verbatim to Stage 18 without interpretation; Stage 21 never
  re-implements or duplicates any clamp, default, or ceiling any frozen stage already enforces.

### PlannerContext

```jsonc
{
  "query": "What are the SDG financing gaps?",
  "conversation_memory": null,                   // ConversationMemoryPackage, if available
  "available_tools": [],                         // list of ToolDefinition from the registry, filtered
                                                 // by tool_preferences.allowed_tools
  "executed_steps": [],                          // PlanStep[], completed so far
  "planner_state": "PLANNING",                   // current state machine state
  "step_count": 0                                // number of steps executed so far
}
```

The `PlannerContext` is assembled by Stage 21 from the current planning state and passed to the
`PlannerLLMAdapter` as input for each planning decision. It is a read-only snapshot — the planner
never mutates it.

### PlannerDecision

```jsonc
{
  "decision": "EXECUTE_STEP",                    // EXECUTE_STEP | COMPLETE | FAIL
  "next_step": {                                 // present only when decision == "EXECUTE_STEP"
    "step_type": "QUERY_PIPELINE",
    "step_rationale": "...",
    "step_input": { ... }
  },
  "final_answer_step_index": null,               // present only when decision == "COMPLETE";
                                                 // identifies which step's result is the final answer
  "decision_rationale": "..."                    // informational; never interpreted by Stage 21
}
```

Returned by the `PlannerLLMAdapter`. Stage 21 structurally validates this before acting on it — if
the decision is malformed or contains an unknown `decision` value or `step_type`, it is treated as a
planner failure (`PLAN_STEP_INVALID`).

### AgentPlan

```jsonc
{
  "agent_plan_id": "ap_...",                     // deterministic hash of plan-identity inputs
  "agent_planning_version": "1.0.0",
  "steps": [],                                   // PlanStep[], in execution order
  "plan_status": "COMPLETED",                    // COMPLETED | FAILED | STEP_LIMIT_REACHED
  "total_step_count": 3,
  "completed_step_count": 2,
  "failed_step_count": 1
}
```

### AgentResult

```jsonc
{
  "agent_result_id": "ar_...",                    // deterministic hash of result-identity inputs
  "agent_planning_version": "1.0.0",
  "planned_at": "2026-07-22T12:00:00Z",          // timestamp; excluded from determinism
  "query": "What are the SDG financing gaps?",
  "conversation_id": null,
  "status": "PASS",                               // PASS | PARTIAL | FAIL — see Validation
  "plan": { ... },                                // the complete AgentPlan
  "final_response": { ... },                      // the APIResponse from the terminal QUERY_PIPELINE step,
                                                  // or null if no successful query pipeline step completed
  "tool_results": [],                             // all ToolExecutionRecords from TOOL_INVOCATION steps
  "conversation_memory_used": null,               // the ConversationMemoryPackage, if conversation memory
                                                  // was consulted; null otherwise
  "findings": [],                                 // Stage 21's own findings: {severity, code, message}
  "upstream_findings": []                         // all findings from all downstream stages, collected
}
```

**Field justification & Ownership:**
- `agent_result_id`: deterministic identity for this planning execution; enables audit trail
  correlation.
- `agent_planning_version`: schema version traceability.
- `planned_at`: timestamp; excluded from determinism.
- `query`: copied verbatim from `AgentRequest.query`.
- `conversation_id`: copied verbatim from `AgentRequest.conversation_id`.
- `status`: computed from plan outcome (see Validation).
- `plan`: the complete executed plan; enables debugging and audit. Stage 21 owns this.
- `final_response`: embedded copy of the `APIResponse`. Immutably captured. May be `null` if planning failed before producing one.
- `tool_results`: embedded copies of all `ToolExecutionRecord`s. Immutably captured.
- `conversation_memory_used`: embedded copy of the `ConversationMemoryPackage`, if consulted. Immutably captured.
- `findings`: Stage 21's own structural and planning findings. Stage 21 generates and owns these exclusively.
- `upstream_findings`: all findings from all stages invoked during plan execution. These are downstream artifacts propagated unchanged. **Stage 21 merely aggregates them; it never rewrites, filters, or modifies downstream findings.**

*Note:* Downstream artifacts (`final_response`, `tool_results`, `conversation_memory_used`) are **embedded copies**, not mere references. Once embedded, they are completely immutable within the `AgentResult`.

### PlannerFinding

Planner findings follow the same `{severity, code, message}` shape every prior stage already uses.
They are recorded in `AgentResult.findings[]`.

### AgentResult Identity

```
agent_result_id = "ar_" + sha256(canonical_content).hexdigest()[:16]
```

Where `canonical_content` is the canonical JSON serialization of `{query, conversation_id,
agent_plan_id}` (sorted keys, no whitespace). This makes the id deterministic and request-
addressable — identical planning executions producing identical plans always produce the identical
id, matching the `*_id` convention every prior stage already established for its own packages.

### AgentPlan Identity

```
agent_plan_id = "ap_" + sha256(canonical_content).hexdigest()[:16]
```

Where `canonical_content` is the canonical JSON serialization of `{query, step_types, step_count}`
where `step_types` is the ordered list of `step_type` values from the executed steps.

- **What it identifies:** The structural sequence of operations planned (the intent), not their outcomes.
- **When it changes:** It changes incrementally every time a new step is appended to the plan.
- **Why it is independent from execution results:** This separates the identity of *what was attempted* from *what happened*. Identical plans executed twice (yielding different outcomes due to downstream non-determinism) share the same plan identity, ensuring deterministic tracking of the planner's decisions.

## Planning Lifecycle

The one and only valid execution sequence:

```
AgentRequest { query, conversation_id, tool_preferences, planning_config, pipeline_options }
      │
      ▼
[1] validate_agent_request(agent_request)   — structural shape only: required keys present,
      correctly typed. Malformed input raises AgentPlanningInputError immediately; nothing
      downstream is ever touched.
      │
      ▼
[2] resolve_planning_config(agent_request.planning_config, agent_dependencies)   — resolve
      planner model, max steps, temperature; clamp to documented limits.
      │
      ▼
[3] build_initial_context(agent_request, agent_dependencies)   — assemble the PlannerContext:
      load available tools from the registry (filtered by tool_preferences), load conversation
      memory if conversation_id is present, set planner_state to PLANNING.
      │
      ▼
[4] PLANNING LOOP:
      │
      ├──▶ [4a] build_planner_prompt(planner_context)   — deterministic construction of a
      │         structured planning prompt from the current PlannerContext
      │
      ├──▶ [4b] planner_decision = planner_llm_adapter.plan(planner_prompt)   — the sole
      │         non-deterministic element; returns a PlannerDecision
      │
      ├──▶ [4c] validate_planner_decision(planner_decision)   — structural validation of
      │         the decision; PLAN_STEP_INVALID on violation
      │
      ├──▶ [4d] decision == "COMPLETE"?
      │         ├─yes──▶ transition to COMPLETED, exit loop
      │         │
      │         decision == "FAIL"?
      │         ├─yes──▶ transition to FAILED, exit loop
      │         │
      │         decision == "EXECUTE_STEP"?
      │         └─yes──▶ continue to [4e]
      │
      ├──▶ [4e] validate_plan_step(next_step)   — structural validation of the step
      │
      ├──▶ [4f] execute_plan_step(next_step, agent_dependencies)   — delegate to the
      │         appropriate frozen stage; capture result and findings
      │
      ├──▶ [4g] update_planner_context(planner_context, executed_step)   — add the completed
      │         step to executed_steps, increment step_count
      │
      ├──▶ [4h] check_stop_conditions(planner_context)   — step limit check
      │         ├─step_limit──▶ STEP_LIMIT_REACHED, exit loop
      │         └─continue──▶ loop back to [4a]
      │
      └──▶ [end of loop]
      │
      ▼
[5] build_agent_result(agent_request, planner_context, plan)   — compute agent_result_id,
      status, collect all findings
      │
      ▼
[6] validate_agent_result(result)   — internal invariant self-check; raises
      AgentPlanningInternalError on violation
      │
      ▼
AgentResult { status, plan, final_response, tool_results, findings, ... }
```

No hidden execution paths. No reordered operations. Every step in the planning loop executes exactly
once per iteration. The loop always terminates (bounded by `MAX_PLAN_STEPS`).

## PlannerLLMAdapter

Stage 21 defines a `PlannerLLMAdapter` contract — a planning-specific LLM interface, distinct from
Stage 13's own `LLMAdapter`:

```python
class PlannerLLMAdapter(ABC):
    @abstractmethod
    def plan(self, planner_prompt: str, config: PlannerConfig) -> PlannerDecision:
        """Invokes a planning-capable LLM with the given prompt. Returns a structured
        PlannerDecision. On failure, raises PlannerInvocationError."""
```

### PlannerLLMAdapter Guarantees

- **No concrete implementation chosen.** A `PlannerLLMAdapter` may wrap the same LLM provider as
  Stage 13's own `LLMAdapter`, a different model, or a local planning heuristic — Stage 21 neither
  knows nor constrains which.
- **No import of model-specific libraries.** Stage 21 never imports any LLM SDK, client library,
  or provider module. All model-specific logic is the adapter's responsibility.
- **Single invocation model.** `plan()` makes exactly one call per planning iteration and returns
  one `PlannerDecision`. No streaming, no batching, no internal retry — matching Stage 13's own
  `LLMAdapter.invoke()` convention and Stage 20's `ToolAdapter.invoke()` convention.
- **Planning decisions only.** Generates planning decisions only. It never generates user-facing responses directly.
- **Never replaces Stage 13.** It never replaces Stage 13 LLM execution for answer generation.
- **Never bypasses Stage 18.** It never bypasses Stage 18 to return a direct answer to the user.
- **Closed exception vocabulary.** On failure, the adapter raises exactly
  `PlannerInvocationError` — a single exception type carrying a structured error code. Stage 21
  never catches raw provider exceptions.
- **Exception normalization guarantee.** Every planner exception is normalized by Stage 21 into a
  deterministic failure outcome: an `AgentResult` with `status = "FAIL"` and a
  `PLANNER_INVOCATION_FAILED` finding. No raw adapter exception ever propagates outside
  `plan_and_execute()`.

## Configuration

Stage 21 explicitly distinguishes three tiers of configuration ownership:

1. **Deployment-level configuration:** Supplied via `AgentDependencies` at wiring time. Defines the available adapters, tool registry, default planner model, and downstream Stage 18 dependencies. Owned by the system/deployment.
2. **Planner defaults:** Defined internally by Stage 21 (e.g., `DEFAULT_MAX_PLAN_STEPS`, `DEFAULT_PLANNER_TEMPERATURE`). Owned by the Stage 21 architecture.
3. **Request-level overrides:** Supplied via `AgentRequest.planning_config`. Allows the caller to override specific planner defaults for a single request. Owned by the caller.

### AgentDependencies

```python
class AgentDependencies:
    handle_request: Callable  # Stage 18's handle_request(api_request, pipeline_deps) -> APIResponse
    select_memory: Callable   # Stage 19's select_memory(conversation_id, selection_config) ->
                              #   ConversationMemoryPackage
    append_turn: Callable     # Stage 19's append_turn(conversation_id, turn) -> ConversationState
    get_conversation: Callable  # Stage 19's get_conversation(conversation_id) -> ConversationState
    execute_tool: Callable    # Stage 20's execute_tool(tool_request, registry, adapter) ->
                              #   ToolExecutionRecord
    tool_registry: ToolRegistry   # Stage 20's ToolRegistry
    tool_adapter: ToolAdapter     # Stage 20's ToolAdapter
    planner_llm_adapter: PlannerLLMAdapter  # Stage 21's own planning LLM
    pipeline_deps: Any        # Stage 18's own PipelineDependencies — forwarded verbatim, never
                              # inspected or modified by Stage 21
    default_planner_model_name: str  # default model for planning decisions
```

All dependencies are supplied at wiring time, never hard-coded. Stage 21 never imports or calls any
stage's internal functions — it only calls their public entrypoints through these pre-configured
references.

### PlannerConfig

```jsonc
{
  "model_name": "...",              // planner model; from planning_config or default
  "temperature": 0.0,              // planner temperature; default DEFAULT_PLANNER_TEMPERATURE
  "max_plan_steps": 10             // step limit; clamped to [1, MAX_PLAN_STEPS]
}
```

## Validation

Three distinct, clearly-scoped groups of named codes — the same three-layer pattern Stages 13, 17,
18, 19, and 20 already established.

### Validation Boundary

Stage 21's validation is exclusively **structural** — it verifies shapes, types, required fields,
step-type membership, and internal invariant consistency. Stage 21 explicitly does **not** validate:

- **Factual correctness** — whether a planning decision or tool result is factually true.
- **Semantic correctness** — whether a planning decision meaningfully advances the user's goal.
- **Business correctness** — whether a planning decision satisfies domain-specific business rules.
- **Plan optimality** — whether the plan is the best possible sequence of steps.

All semantic, factual, and optimality evaluation is the exclusive responsibility of the
`PlannerLLMAdapter`'s own reasoning and whatever consumes the `AgentResult` downstream.

### 1. Input validation codes — raised, never returned as part of any `AgentResult`:

| Code | Raised as | Trigger |
|---|---|---|
| `AGENT_REQUEST_MALFORMED` | `AgentPlanningInputError` | the received `AgentRequest` is missing a required key or has a wrong-typed value |
| `CONVERSATION_NOT_FOUND` | `AgentPlanningInputError` | `conversation_id` is present but no matching conversation exists in the store |
| `CONVERSATION_CLOSED` | `AgentPlanningInputError` | `conversation_id` references a `CLOSED` conversation that cannot accept new turns |

### 2. Package-level findings — recorded in `AgentResult.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `PLANNER_INVOCATION_FAILED` | FAIL | package | The `PlannerLLMAdapter` raised `PlannerInvocationError`; `status = "FAIL"` |
| `PLAN_STEP_INVALID` | FAIL | package | The planner produced a structurally invalid step; `status = "FAIL"` |
| `PLAN_STEP_EXECUTION_FAILED` | WARNING | per-step | A step's delegated stage returned a FAIL status; captured in step_findings |
| `PLAN_STEP_LIMIT_REACHED` | WARNING | package | The step limit was reached before the planner completed; partial results returned |
| `TOOL_NOT_AVAILABLE` | WARNING | per-step | A tool requested by the planner is not in the allowed tools list |
| `CONVERSATION_MEMORY_UNAVAILABLE` | WARNING | package | Conversation memory was requested but `select_memory()` failed |

### 3. Internal invariant codes — raised by `validate_agent_result()`, never returned:

| Code | Trigger |
|---|---|
| `RESULT_STEP_COUNT_MISMATCH` | `plan.total_step_count` does not match `len(plan.steps)` |
| `RESULT_STEP_INDEX_NOT_CONTIGUOUS` | step indices are not exactly `0..total_step_count - 1` |
| `RESULT_STATUS_RESPONSE_MISMATCH` | `status == "PASS"` but `final_response` is `null`, or `status == "FAIL"` for all steps but `final_response` is not `null` |
| `RESULT_PLAN_ID_MISMATCH` | `agent_plan_id` does not match a freshly recomputed hash |
| `RESULT_ID_MISMATCH` | `agent_result_id` does not match a freshly recomputed hash |
| `RESULT_TOOL_RESULTS_MISMATCH` | `tool_results` list does not match the `TOOL_INVOCATION` steps in the plan |

Any of these raises `AgentPlanningInternalError` — the same fail-loud posture every prior stage's
own internal-invariant exceptions already establish.

`status` is computed once, from this truth table (evaluated top-to-bottom, first matching row wins):

| Condition | `status` |
|---|---|
| Planner invocation failed | `FAIL` |
| Plan step invalid | `FAIL` |
| All executed steps failed | `FAIL` |
| Plan completed, final `APIResponse.status` maps to `PIPELINE_FAILURE` | `FAIL` |
| Plan completed, final `APIResponse.status` maps to `PARTIAL_SUCCESS` | `PARTIAL` |
| Step limit reached with at least one successful step | `PARTIAL` |
| Plan completed, final `APIResponse.status` maps to `SUCCESS` | `PASS` |

A WARNING-severity finding (`PLAN_STEP_LIMIT_REACHED`, `PLAN_STEP_EXECUTION_FAILED`,
`TOOL_NOT_AVAILABLE`, `CONVERSATION_MEMORY_UNAVAILABLE`) never by itself changes `status` away from
whatever the terminal step's own outcome determined — exactly the same "WARNING is informational,
never a status driver on its own" posture every prior stage established.

## Public Function Contracts

- `validate_agent_request(agent_request: AgentRequest) -> None` — structural input check; raises
  `AgentPlanningInputError` (code `AGENT_REQUEST_MALFORMED`) on a missing/wrong-typed required key.

- `resolve_planning_config(planning_config: Optional[Dict], agent_dependencies: AgentDependencies)
  -> PlannerConfig` — resolves planner model, max steps, and temperature from request config or
  deployment defaults; clamps to documented limits.

- `build_initial_context(agent_request: AgentRequest, agent_dependencies: AgentDependencies)
  -> PlannerContext` — assembles the initial `PlannerContext` from the request and dependencies;
  loads available tools from the registry (filtered by `tool_preferences`), loads conversation
  memory if `conversation_id` is present.

- `build_planner_prompt(planner_context: PlannerContext) -> str` — deterministic construction of
  a structured planning prompt from the current `PlannerContext`; pure function, no side effects.

- `validate_planner_decision(decision: PlannerDecision) -> None` — structural validation of the
  planner's decision; raises `AgentPlanningInputError` (code `PLAN_STEP_INVALID`) on an unknown
  decision type or malformed step.

- `validate_plan_step(step: PlanStep) -> None` — structural validation of a plan step before
  execution; raises `AgentPlanningInputError` (code `PLAN_STEP_INVALID`) on an unknown step type
  or malformed step input.

- `execute_plan_step(step: PlanStep, agent_dependencies: AgentDependencies) -> PlanStep` —
  delegates the step to the appropriate frozen stage's public entrypoint; captures the result,
  status, and findings on the step; returns the updated step.

- `build_agent_result(agent_request: AgentRequest, plan: AgentPlan,
  final_response: Optional[APIResponse], tool_results: List[ToolExecutionRecord],
  memory_used: Optional[ConversationMemoryPackage],
  package_findings: List[PlannerFinding]) -> AgentResult` — computes `agent_result_id`, `status`,
  and this stage's own findings; collects all upstream findings. The terminal `final_response`, the
  embedded `tool_results` and `memory_used` copies, and the accumulated `package_findings` are
  captured by `plan_and_execute` during the planning loop and passed in explicitly (they are not
  recoverable from `plan` or a `PlannerContext` alone).

- `validate_agent_result(result: AgentResult) -> None` — internal invariant self-check; raises
  `AgentPlanningInternalError` (one of the six named codes in Validation §3) on violation.

- `plan_and_execute(agent_request: AgentRequest, agent_dependencies: AgentDependencies)
  -> AgentResult` — the sole public entrypoint; orchestrates the Planning Lifecycle [1]–[6];
  never reads or writes any local artifact and never touches the manifest; the only I/O it performs
  is via the delegated stage calls and the `PlannerLLMAdapter`.

## Serialization

### AgentResult Serialization

- **Deterministic ordering.** All dict fields in `plan`, `findings`, `tool_results`, and
  `upstream_findings` are serialized with `sort_keys=True` wherever canonical JSON is computed
  (identity hashing, logging). Display-order for human-readable output is document-declaration order.
- **UTF-8.** All text is UTF-8. Stage 21 never re-encodes text into any other encoding.
- **Unicode NFC preserved.** Stage 21 never applies its own NFC/NFKC normalization pass to any
  text — the same byte-for-byte preservation rule every prior stage already applies.
- **Immutable output.** Once an `AgentResult` is assembled and validated, it is never modified —
  the same documented (not language-enforced) contract every prior stage's own returned package
  already carries.
- **Omission rules.** Every field named in the `AgentResult` schema is always present — never
  conditionally omitted based on content. `final_response` is `null` when no successful query
  pipeline step completed. `conversation_memory_used` is `null` when no conversation memory was
  consulted.
- **Null handling.** `final_response` is `null` on FAIL. `conversation_memory_used` is `null`
  when not applicable. Every other field is always present and non-null.

## Failure Handling

- **Malformed `AgentRequest`** (missing/wrong-typed required key) — `AgentPlanningInputError`
  (`AGENT_REQUEST_MALFORMED`) raised immediately; no `AgentResult` returned; no downstream stage
  called.
- **Conversation not found** — `AgentPlanningInputError` (`CONVERSATION_NOT_FOUND`) raised
  immediately; no `AgentResult` returned; no downstream stage called.
- **Conversation closed** — `AgentPlanningInputError` (`CONVERSATION_CLOSED`) raised immediately;
  no `AgentResult` returned; no downstream stage called.
- **Planner invocation failure** (`PlannerInvocationError` raised during planning) —
  `AgentResult{status="FAIL"}` returned with a `PLANNER_INVOCATION_FAILED` finding; the error is
  captured structurally, never swallowed, never re-raised as an unstructured exception.
- **Invalid plan step** — `AgentResult{status="FAIL"}` returned with a `PLAN_STEP_INVALID` finding.
- **Step execution failure** (delegated stage returns FAIL status) — step marked
  `step_status="FAILED"`, `PLAN_STEP_EXECUTION_FAILED` WARNING finding recorded; planner continues
  to the next planning decision (the planner may decide to retry with a different approach, invoke
  a different tool, or give up).
- **Step limit reached** — `AgentResult` returned with `PLAN_STEP_LIMIT_REACHED` WARNING finding
  and whatever partial results have been accumulated; `plan_status = "STEP_LIMIT_REACHED"`.
- **Tool not available** — `TOOL_NOT_AVAILABLE` WARNING finding; the planner is informed and may
  choose a different tool or approach.
- **Conversation memory failure** — `CONVERSATION_MEMORY_UNAVAILABLE` WARNING finding; planning
  continues without conversation context.
- **No retry logic.** Stage 21 performs no retries of any downstream stage invocation. If a step
  fails, the planner decides what to do next. Stage 21 never wraps a stage call in a retry loop.
- **No timeout ownership.** Stage 21 owns no timeout logic of its own. Each downstream stage owns
  its own timeout boundary.
- **No hidden recovery behavior.** No fallback mode, no degraded planning, no silent substitution.

## Determinism

Stage 21 draws the same explicit line between deterministic and non-deterministic as Stages 13, 17,
18, 19, and 20 — with a distinction specific to agent planning: Stage 21's own orchestration logic
is fully deterministic, but the `PlannerLLMAdapter`'s decisions are non-deterministic.

**Deterministic (guaranteed, byte-identical across runs, given identical planner decisions):**

- **Request validation.** Given an identical `AgentRequest`, the validation outcome is byte-identical
  every time.
- **Planning config resolution.** Given identical `(planning_config, agent_dependencies)`, resolution
  produces identical `PlannerConfig` every time.
- **Initial context construction.** Given identical `(agent_request, agent_dependencies)` and
  identical tool registry and conversation store state, `build_initial_context` produces an
  identical `PlannerContext` every time.
- **Planner prompt construction.** Given an identical `PlannerContext`, `build_planner_prompt`
  produces an identical prompt string every time.
- **Step validation.** Given an identical step, validation produces identical results every time.
- **Step delegation.** Given an identical step and identical downstream stage state, `execute_plan_step`
  calls the same stage with the same arguments every time.
- **`agent_result_id` and `agent_plan_id`.** Deterministic content-hashes — identical planning
  executions (same query, same steps) always produce identical ids.
- **Status computation.** Given an identical plan outcome, `status` is determined identically.
- **Finding codes.** A given condition always produces the same finding code.
- **No hidden state.** Stage 21 holds no module-level mutable state; all state is in the
  `PlannerContext` being assembled.
- **No randomness.** No `uuid4()`, no random selection — every identifier Stage 21 produces is a
  deterministic content-hash.

**Explicitly NOT deterministic (inherent to external dependencies; never assumed, never hidden):**

- **Planner decisions.** The `PlannerLLMAdapter`'s planning output; may differ across two calls with
  identical prompts. This is the sole source of non-determinism in Stage 21.
- **Downstream stage output.** `APIResponse`, `ToolExecutionRecord`, `ConversationMemoryPackage` —
  each may contain non-deterministic content (`response_text`, tool output, timestamps).
- **`planned_at`, `started_at`, `completed_at`.** Wall-clock timestamps; excluded from every
  determinism comparison.

## Read-Only Guarantees

- Stage 21 never modifies `manifest.json`, any corpus artifact, any vector index, any embedding, any
  prompt template, any cache store entry directly.
- Stage 21 never modifies a `ToolDefinition` resolved from the registry.
- Stage 21 never modifies a `ToolExecutionRecord` after capture.
- Stage 21 never modifies a `ConversationMemoryPackage` after capture.
- Stage 21 never modifies a `PromptPackage`, `LLMResponse`, `CitedResponse`, `GroundednessReport`,
  `AnswerQualityReport`, or `CachedExecutionResult`.
- Stage 21 never modifies an `APIResponse` after capture.
- Stage 21 never modifies a `RetrievalResult` or `ContextPackage`.
- Stage 21 never modifies an `AgentResult` after validation.
- Stage 21 holds no module-level mutable state. No global registries, no singletons, no thread-local
  storage.
- The only external side effects Stage 21 triggers are:
  - Stage 18's `handle_request()` → which itself triggers Stage 17's cache writes (if any).
  - Stage 19's `append_turn()` → which writes to the conversation store.
  - Stage 20's `execute_tool()` → which invokes a tool via the adapter.
  - `PlannerLLMAdapter.plan()` → which invokes the planning LLM.
  These are all delegated to their owning stages; Stage 21 never performs the write/invocation itself.

## Concurrency

### Ownership

Stage 21 itself is single-threaded and deterministic — it makes no concurrency guarantees of its own,
performs no locking, and holds no mutex or semaphore. Planning is inherently sequential: one step
at a time, one planning decision at a time.

### Downstream Concurrency

Each downstream stage's own concurrency posture applies when it is invoked:
- Stage 18 is safe under concurrent calls (per its own architecture).
- Stage 19's conversation operations may have store-level concurrency constraints.
- Stage 20 holds no shared mutable state and is safe under concurrent calls.

Stage 21 never coordinates parallel execution of downstream stages. If a future design requires
parallel tool invocations or parallel query pipeline calls, that is a new design pass — Stage 21's
current planning model is strictly sequential.

### Timeout Ownership

Stage 21 owns no timeout logic of its own. Each downstream stage owns its own timeout boundary
(Stage 13 owns LLM invocation timeouts; Stage 20 delegates tool timeouts to the adapter). The
planning loop is bounded by `MAX_PLAN_STEPS`, not by wall-clock time.

## Security Considerations

- **Untrusted query.** `agent_request.query` may contain adversarial input. Stage 21 validates it
  structurally but performs no content-level sanitization — that defense, if needed, is the
  downstream stage's own responsibility (Stage 12's prompt template boundary, Stage 13's LLM
  adapter boundary).

- **Untrusted planner output.** The `PlannerLLMAdapter`'s decision is treated as untrusted —
  structurally validated before any step is executed. An adversarial or malformed planning decision
  is caught by `validate_planner_decision()` and `validate_plan_step()`, producing a `PLAN_STEP_INVALID`
  failure rather than executing an invalid step.

- **No credential handling.** All credentials (LLM API keys, tool adapter tokens, conversation store
  credentials) are owned by their respective adapters, supplied by the caller to the adapter, never
  passed through, logged, or included in any `AgentResult`, `findings`, or log entry Stage 21 emits.

- **No code execution.** Stage 21 never evaluates, compiles, or executes code from any source —
  planner output, tool output, or user input. It only constructs structured step descriptors and
  delegates them to frozen stages.

- **No direct tool invocation.** Stage 21 never calls a tool directly — it constructs a
  `ToolRequest` and delegates to Stage 20's own `execute_tool()`, which owns all structural
  validation and exception normalization for tool invocations.

- **No prompt injection mitigation beyond structural planning boundaries.** Stage 21 does not
  implement prompt injection detection or prevention. Its defense is structural: the planner
  prompt is constructed deterministically from the `PlannerContext` by `build_planner_prompt()`,
  and the planner's output is structurally validated before execution. Content-level prompt
  injection defense, if needed, is a deployment-level concern or a future security layer.

- **Step limit as a safety bound.** `MAX_PLAN_STEPS` prevents an adversarial or confused planner
  from entering an infinite loop. This is a structural safety bound, not a timeout.

## Constants

```python
AGENT_PLANNING_VERSION = "1.0.0"

# Planning limits
DEFAULT_MAX_PLAN_STEPS = 10        # default step limit per plan
MAX_PLAN_STEPS = 25                # hard ceiling on total steps; guards unbounded planning
DEFAULT_PLANNER_TEMPERATURE = 0.0  # deterministic planning by default
MAX_PLANNER_TEMPERATURE = 1.0      # hard ceiling on planner temperature
```

No numeric threshold, ceiling, or default from any prior stage is duplicated here — every one Stage
21 defines is its own, governing agent planning only.

## Complexity

- `validate_agent_request()` — O(1): structural key/type checks.
- `resolve_planning_config()` — O(1): resolution and clamping.
- `build_initial_context()` — O(T) where T is the number of available tools (registry enumeration +
  filtering).
- `build_planner_prompt()` — O(S) where S is the number of executed steps (serialization of step
  history for the planner).
- `execute_plan_step()` — dominated by the delegated stage's own execution time.
- `plan_and_execute()` overall — O(N × (P + E)) where N is the number of planning iterations, P is
  the planner invocation cost, and E is the average step execution cost.
- `validate_agent_result()` — O(S): verification of step indices and hash recomputation.

## Logging

Per the shared Logging Specification (`stage: "stage21_agent_planning"`, `doc_id: null` always —
entries are request-scoped, not document-scoped). New codes this stage adds:

- `INFO_PLANNING_START` — a planning request has been received.
- `INFO_PLANNING_STEP_START` — a plan step is about to be executed.
- `INFO_PLANNING_STEP_COMPLETE` — a plan step has completed.
- `INFO_PLANNING_COMPLETE` — planning has completed successfully.
- `WARNING_PLAN_STEP_EXECUTION_FAILED` — a step's delegated stage returned FAIL status.
- `WARNING_PLAN_STEP_LIMIT_REACHED` — the step limit was reached.
- `WARNING_TOOL_NOT_AVAILABLE` — a planner-requested tool is not available.
- `WARNING_CONVERSATION_MEMORY_UNAVAILABLE` — conversation memory could not be loaded.
- `FATAL_PLANNER_INVOCATION_FAILED` — the planning LLM failed.
- `FATAL_PLAN_STEP_INVALID` — the planner produced a structurally invalid step.

No new `FATAL_*` code beyond those two — Stage 21 never sets a manifest `error_code`, since it
never touches the manifest at all.

## Design Decisions

1. **Incremental planning, not upfront plan generation.** Stage 21 generates one step at a time,
   informed by the results of all preceding steps. This allows the planner to adapt to unexpected
   results (a failed tool call, an unsatisfactory answer) without requiring the entire plan to be
   known in advance. A future design could introduce upfront multi-step planning as an optimization,
   but the current model is the simplest correct approach.

2. **Linear execution, not parallel.** Steps execute one at a time, in order. This matches Stage
   20's own single-invocation model and avoids the complexity of managing concurrent downstream
   stage calls, dependency ordering between parallel steps, and partial-failure recovery in a
   parallel execution graph. A future design could introduce parallelism as a separate concern.

3. **PlannerLLMAdapter is distinct from Stage 13's LLMAdapter.** The planning LLM serves a
   different purpose (structured decision-making about what to do next) than the answer-generation
   LLM (producing a natural-language response to a user query). They may use the same underlying
   model, but their contracts, prompt formats, and output schemas are different. Keeping them
   separate preserves the adapter boundary and allows independent evolution.

4. **Stage 21 never retries a downstream stage.** Each stage owns its own retry policy (Stage 13
   retries LLM invocations; no other stage retries). Stage 21's response to a step failure is to
   inform the planner, which can then decide to try a different approach — not to retry the same
   step. This preserves the separation of concerns between execution (downstream stages) and
   planning (Stage 21).

5. **Conversation memory is read via `select_memory()`, not raw history.** Stage 21 calls
   Stage 19's `select_memory()` to obtain a bounded, deterministic memory window — it never
   accesses the full conversation history directly. This respects Stage 19's window policy and
   budget enforcement.

6. **Tool availability is filtered at planning time, not execution time.** The `PlannerContext`
   contains only the tools that are available (per `tool_preferences.allowed_tools`), so the
   planner never sees or considers tools it cannot invoke. If the planner somehow produces a
   `TOOL_INVOCATION` step for an unavailable tool, Stage 21 catches this with a `TOOL_NOT_AVAILABLE`
   finding before delegation.

7. **`pipeline_options` are forwarded verbatim to Stage 18.** Stage 21 never re-implements or
   duplicates any clamp, default, or ceiling any frozen stage already enforces. Every
   `pipeline_options` field is Stage 18's own concern, forwarded transparently.

8. **The planner's rationale is informational only.** `step_rationale` and `decision_rationale` are
   stored for debugging and audit but never parsed, interpreted, or used to make any decision by
   Stage 21 itself. This prevents adversarial or nonsensical rationales from affecting execution.

9. **Conversation turn appending is a plan step, not an implicit side effect.** When conversation
   memory is active, the planner must explicitly include a `CONVERSATION_APPEND` step in the plan
   to record the completed turn. This makes conversation writes visible in the plan, auditable,
   and controllable — never a hidden side effect of completing a query.

10. **Stage 21 is the final stage.** There is no Stage 22. Stage 21 is the highest orchestration
    layer in this pipeline. All lower stages (0–20) remain independently usable without Stage 21 —
    a caller can invoke Stage 18 directly for a single query, Stage 19 directly for conversation
    management, or Stage 20 directly for tool execution, without ever involving Stage 21.

## Known Limitations

- **No parallel tool execution.** Stage 21 executes one tool per step. A planner that wants
  multiple tool results must plan them as sequential steps. A future design could introduce
  parallel execution as a new step type.

- **No plan caching.** Stage 21 does not cache plans. Two identical `AgentRequest`s each trigger
  a fresh planning cycle. A future caching layer could be introduced as a separate concern.

- **Planner decision quality is not evaluated.** Stage 21 structurally validates planner decisions
  but never evaluates whether they are *good* decisions. A planner that makes poor choices (e.g.,
  invoking irrelevant tools, ignoring available context) will produce a valid but suboptimal
  `AgentResult`.

- **No plan repair or backtracking.** If a step fails, the planner can choose a different next
  step, but Stage 21 cannot "undo" an already-executed step. Side effects from Stage 19
  (`append_turn`) and Stage 20 (tool execution) cannot be reversed.

- **Linear step limit, not a cost budget.** `MAX_PLAN_STEPS` counts steps regardless of their
  cost. A plan with 5 expensive LLM calls and a plan with 5 cheap tool lookups both count as 5
  steps. A future design could introduce a cost-based budget.

- **Schema validation of planner output is structural only.** Stage 21 checks that the planner
  produces a well-formed `PlannerDecision` with a valid step type, but never evaluates whether the
  step's arguments are semantically appropriate for the current context.

- **No streaming.** The complete `AgentResult` is fully materialized before being returned.

## Future Stage Boundaries

There is **no Stage 22**. Stage 21 is the highest orchestration layer in this pipeline's design
roadmap. All future enhancements to planning, tool use, or agent behavior are revisions to Stage 21
itself, not new stages.

All lower stages (0–20) remain independently usable without Stage 21:

- **Stage 18** (`handle_request`) can be called directly by any caller for a single-turn query
  without involving Stage 21. Stage 18's own pipeline chain (10→11→12→17→14→15→16) remains fully
  self-contained.

- **Stage 19** (`start_conversation`, `append_turn`, `select_memory`, etc.) can be called directly
  for conversation management without involving Stage 21.

- **Stage 20** (`execute_tool`) can be called directly for tool execution without involving
  Stage 21.

Stage 21 adds a planning and coordination layer *on top of* these independently-usable stages; it
does not modify, extend, or replace any of them. A deployment that does not need agent planning can
omit Stage 21 entirely and use Stages 0–20 directly.
