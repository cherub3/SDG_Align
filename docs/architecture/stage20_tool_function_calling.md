# Stage 20 — Tool / Function Calling

Stages 0–19 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 20 manages the structured invocation of external tools on behalf of an LLM-driven workflow: it
validates a tool request, resolves the requested tool's definition from an abstract registry, verifies
that the request satisfies the tool's declared execution policy, invokes the tool through a
caller-supplied adapter, validates the result, and packages the complete execution record into an
immutable `ToolExecutionRecord`. It performs no generation, no retrieval, no prompt construction, no
LLM invocation, no citation extraction, no groundedness validation, no answer quality evaluation, no
response caching, no API serving, no conversation memory management, and — critically — no reasoning
about *which* tool should be called, *when* it should be called, or *why* one tool is preferable to
another. Those decisions belong exclusively to Stage 21 (Agent Planning); Stage 20 is a pure
execution-and-capture layer that carries out one tool invocation at a time, deterministically
orchestrated, and returns a structured result.

`execute_tool(tool_request, tool_registry, tool_adapter)` is the sole public entrypoint.

Stage 20 mirrors the adapter-based abstraction pattern established by Stage 9 (`IndexAdapter`),
Stage 13 (`LLMAdapter`), Stage 17 (`CacheAdapter`), and Stage 19 (`ConversationStore`) — defining
abstract contracts for tool resolution and tool execution without selecting, importing, or depending on
any concrete tool implementation, SDK, or external service.

## Scope

Stage 20 answers exactly one question — given a structured tool request naming a specific tool and
supplying arguments, what is the validated, structured result of executing that tool — and stops there.
It never decides which tool should be called (Stage 21's future scope); never reasons about a sequence
of tool calls (Stage 21); never constructs a prompt from a tool result (Stage 12's frozen job); never
invokes an LLM (Stage 13's frozen job); never manages conversation state (Stage 19's frozen job);
never serves an API (Stage 18's frozen job); never caches a tool result (a future concern, outside
this design); never streams partial results; never interprets a tool result's semantic meaning. Those
boundaries are restated in Non-Responsibilities and Future Stage Boundaries.

## Responsibilities

Stage 20 shall: receive a `ToolRequest`; structurally validate it before use; resolve the named tool's
`ToolDefinition` from a caller-supplied `ToolRegistry`; verify the request's arguments against the
tool's declared parameter schema; verify the tool's execution policy permits invocation; invoke the
tool through a caller-supplied `ToolAdapter`; capture the tool's output, execution metadata (latency,
status), and any error; validate the result against the tool's declared output schema; compute a
deterministic `tool_execution_record_id`; and assemble a `ToolExecutionRecord` whose own internal
invariants are self-checked before it is ever returned.

## Non-Responsibilities

Stage 20 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: deciding which tool to call, when to call it, or whether a tool call is appropriate
(Stage 21 — Agent Planning); sequencing multiple tool calls or orchestrating a multi-step tool-use
plan (Stage 21); constructing or modifying any prompt from a tool result (Stage 12's frozen job,
extended by a future integration layer); invoking an LLM to interpret, summarize, or reason about a
tool result (Stage 13's frozen job); retrying a failed tool invocation (see Failure Handling — no
retry logic); caching tool results; managing conversation memory (Stage 19's frozen job); performing
retrieval, embedding, reranking, or vector search of any kind; citation extraction, groundedness
validation, or answer quality evaluation; serving a network-facing API; streaming partial tool
results; choosing, importing, or depending on any concrete tool implementation, SDK, API client, or
external service library.

## Inputs

Three required inputs, all supplied by the caller:

- **`ToolRequest`** (this stage's own new schema, see Schemas) — per-call, the sole source of the
  tool name, arguments, and request metadata. This is what a caller (typically Stage 21's future
  agent planner, or a manual test harness) supplies to request one tool invocation.
- **`ToolRegistry`** (this stage's own new abstract contract, see Tool Registry) — per-deployment,
  supplied once at wiring time: an abstract registry providing tool definition lookup by name. The
  registry is the sole mechanism through which Stage 20 resolves tool metadata — Stage 20 never
  hard-codes, discovers, or auto-registers tools itself.
- **`ToolAdapter`** (this stage's own new abstract contract, see Tool Adapter) — per-deployment,
  supplied once at wiring time: an abstract adapter providing the actual tool execution capability.
  The adapter is the sole mechanism through which Stage 20 invokes a tool — Stage 20 never directly
  calls any external service, SDK, or function itself.

No other input is read. `manifest.json`, `chunks.json`, `metadata.json`, vector indexes, embeddings,
prompt templates, cache stores, conversation stores, and every earlier-stage artifact are never opened
— Stage 20 operates exclusively on its own `ToolRequest` input and the two abstract contracts it
defines. No PDF is ever reopened; no corpus artifact is ever read.

## Outputs

`ToolExecutionRecord` (see Schemas) is Stage 20's sole return value — never persisted by Stage 20
itself as a distinct artifact, matching the zero-artifact posture Stage 10 through Stage 19 each
already established for their own in-memory return values. Whether and how a caller persists, caches,
logs, or surfaces a `ToolExecutionRecord` is explicitly that caller's own concern, never Stage 20's.

## Tool Model

### Tool

A `Tool` is a named, versioned, externally-implemented capability that Stage 20 can invoke on behalf
of a caller. Every tool has:

- A unique, stable `tool_name` that identifies it within the registry.
- An immutable `ToolDefinition` that declares its parameters, output schema, and execution policy.
- A concrete implementation that lives entirely outside Stage 20, behind the `ToolAdapter` contract.

Stage 20 has no knowledge of what a tool *does* — it knows only the tool's declared interface
(parameters, output shape, execution constraints) and delegates actual execution to the adapter.

### Tool Invocation

A single tool invocation is the atomic unit of Stage 20's work: one `ToolRequest` → one tool lookup →
one execution → one `ToolExecutionRecord`. Stage 20 never batches, pipelines, or parallelizes
multiple tool calls within a single `execute_tool()` invocation. Multi-tool orchestration is
Stage 21's exclusive responsibility.

## Tool Registry

Stage 20 defines a `ToolRegistry` contract — a minimal abstract interface for resolving tool
definitions by name — matching the adapter pattern Stage 9 (`IndexAdapter`), Stage 13 (`LLMAdapter`),
Stage 17 (`CacheAdapter`), and Stage 19 (`ConversationStore`) already established:

```python
class ToolRegistry(ABC):
    @abstractmethod
    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """Returns the ToolDefinition for the given name, or None if not registered."""

    @abstractmethod
    def list_tools(self) -> List[ToolDefinition]:
        """Returns all registered ToolDefinitions. Order is deterministic (alphabetical by
        tool_name). Used only for introspection — Stage 20's own execute_tool() never calls
        this method; it exists for callers that need to enumerate available tools (e.g.,
        Stage 21's future agent planner, or a configuration UI)."""
```

### Registry Guarantees

- **Abstraction only.** No storage technology — in-memory dict, configuration file, database, or
  service discovery mechanism — is chosen, recommended, or assumed by this design. The choice of
  backend is a deployment decision, entirely outside Stage 20's scope.
- **Deterministic lookup.** Given the same `tool_name`, `get_tool()` always returns the same
  `ToolDefinition` (or `None`) for the lifetime of that registry instance. A registry must not
  silently modify, add, or remove tool definitions while Stage 20 is using it.
- **Single lookup path.** `get_tool()` performs exactly one deterministic lookup per call. There is
  no fallback lookup, no fuzzy matching, no prefix matching, no alias resolution, no retry on a
  failed lookup, and no secondary registry consultation. An unknown `tool_name` produces exactly one
  outcome: `None`, which Stage 20 maps to `TOOL_NOT_FOUND` immediately.
- **Immutable tool definitions.** A `ToolDefinition` returned by the registry is never modified by
  Stage 20. It is treated as a read-only specification.
- **No auto-discovery.** Stage 20 never discovers, scans for, or auto-registers tools. Every tool
  must be explicitly registered in the registry by whatever deployment mechanism configures it.
- **No import of tool implementations.** The registry provides definitions (metadata, schemas); the
  `ToolAdapter` provides execution. The registry never imports, references, or contains executable
  tool code.

### Registry Ownership

Stage 20 consumes an existing `ToolRegistry` — it never creates one, never modifies one, never
registers tools into one, and never unregisters or removes tools from one. Registry lifecycle —
creation, population, configuration, and teardown — is entirely owned by the deployment layer or
caller that supplies the registry to `execute_tool()`. Stage 20 treats the registry as a read-only,
pre-populated dependency for the duration of each invocation.

## Tool Adapter

Stage 20 defines a `ToolAdapter` contract — the sole mechanism through which a tool is actually
invoked:

```python
class ToolAdapter(ABC):
    @abstractmethod
    def invoke(self, tool_name: str, arguments: Dict[str, Any],
               tool_definition: ToolDefinition) -> RawToolResult:
        """Invokes the named tool with the given arguments. Returns a RawToolResult
        containing the tool's output and execution metadata. On failure, raises
        ToolExecutionError (see Failure Handling)."""
```

### Adapter Guarantees

- **No concrete implementation chosen.** A `ToolAdapter` may wrap an HTTP API call, a local function
  call, a subprocess, an SDK client, or any other execution mechanism — Stage 20 neither knows nor
  constrains which.
- **No import of tool-specific libraries.** Stage 20 never imports any tool's own SDK, client
  library, or implementation module. All tool-specific logic is the adapter's responsibility.
- **Single invocation model.** `invoke()` makes exactly one call per invocation and returns one
  `RawToolResult`. No streaming, no batching, no internal retry — matching Stage 13's own
  `LLMAdapter.invoke()` convention for its own single-call model.
- **Closed exception vocabulary.** On failure, the adapter raises exactly `ToolExecutionError` — a
  single exception type carrying a structured error code (see Failure Handling). Stage 20 never
  catches raw provider exceptions, HTTP errors, or SDK-specific exception types.
- **Exception normalization guarantee.** Every adapter exception is normalized by Stage 20 into a
  deterministic failure object: a `ToolExecutionRecord` with `status = "FAIL"`, `output = null`,
  and a `TOOL_INVOCATION_FAILED` finding carrying the structured error code from the
  `ToolExecutionError`. No raw adapter exception, provider-specific exception, HTTP error, or
  SDK-specific exception type ever propagates outside `execute_tool()` — the same exception-
  normalization posture Stage 13 established for its own `LLMAdapter` error mapping.

## Schemas

All in-memory Python structures — none persisted, no file format to version.

### ToolDefinition

```jsonc
{
  "tool_name": "search_documents",                  // unique identifier within the registry
  "tool_version": "1.0.0",                          // version of this tool's interface
  "description": "Searches the document corpus...", // human-readable description; informational only,
                                                    // never interpreted by Stage 20
  "parameter_schema": {                             // JSON-Schema-like declaration of accepted arguments;
    "type": "object",                               // used by Stage 20 for structural argument validation
    "properties": {
      "query": {"type": "string"},
      "max_results": {"type": "integer", "minimum": 1, "maximum": 100}
    },
    "required": ["query"]
  },
  "output_schema": {                                // JSON-Schema-like declaration of the expected output
    "type": "object",                               // shape; used by Stage 20 for result validation
    "properties": {
      "results": {"type": "array"},
      "total_count": {"type": "integer"}
    }
  },
  "execution_policy": {                             // fixed, declarative constraints on invocation
    "max_timeout_seconds": 30,                      // hard ceiling on adapter invocation time;
                                                    // Stage 20 itself owns no timeout logic (see Concurrency);
                                                    // this value is passed to the adapter for its own use
    "idempotent": true,                             // informational — whether repeated identical invocations
                                                    // are safe; Stage 20 records it but never acts on it
                                                    // (retries are forbidden); Stage 21 may use it for
                                                    // planning decisions
    "side_effects": false                           // informational — whether the tool modifies external state;
                                                    // Stage 20 records it but never acts on it; Stage 21 may
                                                    // use it for planning decisions
  }
}
```

**Field justification:**
- `tool_name`: identifies the tool; required for lookup and correlation.
- `tool_version`: version traceability; ensures invocation records can be attributed to the interface
  version that governed them.
- `description`: human-readable documentation; never parsed or interpreted programmatically.
- `parameter_schema`: enables structural validation of arguments before invocation; prevents malformed
  requests from reaching the adapter.
- `output_schema`: enables structural validation of results after invocation; detects adapter
  implementation bugs or contract violations.
- `execution_policy.max_timeout_seconds`: communicates the tool's time budget to the adapter; Stage 20
  itself owns no timeout enforcement (see Concurrency).
- `execution_policy.idempotent`: metadata for upstream consumers (Stage 21); Stage 20 never retries.
- `execution_policy.side_effects`: metadata for upstream consumers (Stage 21); Stage 20 never reasons
  about side-effect safety.

### ToolRequest

```jsonc
{
  "tool_name": "search_documents",                  // must match a registered ToolDefinition
  "arguments": {                                    // must conform to the tool's parameter_schema
    "query": "SDG financing gaps",
    "max_results": 10
  },
  "request_context": {                              // optional, caller-supplied metadata for traceability
    "request_id": "req_...",                        // Stage 18's own request_id, if applicable
    "conversation_id": "conv_...",                  // Stage 19's own conversation_id, if applicable
    "planning_step_id": null                        // Stage 21's own step id, when Stage 21 exists
  }
}
```

**Field justification:**
- `tool_name`: identifies which tool to invoke; required for registry lookup.
- `arguments`: the tool's input; validated against `parameter_schema` before invocation.
- `request_context`: optional provenance linking this invocation to the broader pipeline; never
  interpreted by Stage 20, only carried through into the `ToolExecutionRecord`.

### RawToolResult

```jsonc
{
  "output": { ... },                                // the tool's actual output; shape governed by the
                                                    // tool's output_schema
  "execution_metadata": {
    "latency_ms": 245,                              // wall-clock duration of the adapter invocation
    "adapter_status": "success"                     // "success" | "error" — closed vocabulary
  }
}
```

Returned by `ToolAdapter.invoke()`. Stage 20 validates this structure and transforms it into the
final `ToolExecutionRecord`.

### ToolExecutionRecord

```jsonc
{
  "tool_execution_record_id": "ter_...",            // deterministic hash of request-identity inputs
  "tool_execution_version": "1.0.0",                // this schema's own version
  "tool_name": "search_documents",                  // copied from ToolRequest
  "tool_version": "1.0.0",                          // copied from ToolDefinition
  "arguments": {                                    // copied from ToolRequest, after validation
    "query": "SDG financing gaps",
    "max_results": 10
  },
  "output": { ... },                                // tool output; null on failure
  "status": "PASS",                                 // PASS | FAIL — see Validation
  "latency_ms": 245,                                // wall-clock; excluded from determinism comparisons
  "request_context": { ... },                       // copied verbatim from ToolRequest
  "executed_at": "2026-07-22T12:00:00Z",            // wall-clock; excluded from determinism comparisons
  "findings": [],                                   // Stage 20's own findings: {severity, code, message}
  "tool_findings": []                               // ToolDefinition's own execution_policy metadata,
                                                    // carried through for upstream consumers
}
```

**Field justification:**
- `tool_execution_record_id`: deterministic identity for this execution request; enables deduplication
  detection and audit trail correlation.
- `tool_execution_version`: schema version traceability.
- `tool_name`, `tool_version`: identify what was invoked and which interface version governed it.
- `arguments`: the validated arguments that were actually sent to the adapter; preserved for audit.
- `output`: the tool's validated output; `null` when `status == "FAIL"`.
- `status`: computed from the invocation outcome (see Validation).
- `latency_ms`: wall-clock duration; excluded from determinism comparisons.
- `request_context`: provenance linkage; never interpreted by Stage 20.
- `executed_at`: timestamp; excluded from determinism comparisons.
- `findings`: Stage 20's own structural and execution findings.
- `tool_findings`: declarative tool metadata (idempotency, side-effects) from `execution_policy`,
  carried through for Stage 21 or other upstream consumers.

### ToolExecutionRecord Identity

```
tool_execution_record_id = "ter_" + sha256(canonical_content).hexdigest()[:16]
```

Where `canonical_content` is the canonical JSON serialization of `{tool_name, tool_version,
arguments}` (sorted keys, no whitespace). This makes the id deterministic and request-addressable —
identical tool requests always produce the identical id, matching the `*_id` convention every prior
stage already established for its own packages.

### Execution Identity vs. Execution Result

Stage 20 deliberately separates two independent concepts:

- **Execution identity** (`tool_execution_record_id`) identifies *which tool invocation was
  requested* — a deterministic function of the request inputs (`tool_name`, `tool_version`,
  `arguments`) alone. Two calls with identical request inputs always produce the identical
  `tool_execution_record_id`, regardless of what the tool actually returned.

- **Execution result** (`output`, `status`, `latency_ms`, `executed_at`) captures *what the tool
  actually produced* — inherently non-deterministic for any tool that depends on external state,
  time, network conditions, or other non-reproducible factors.

These two concepts are deliberately independent: an identical execution identity does not imply an
identical execution result, and two different execution results may share the same execution identity.
This is the same deliberate reframing Stage 13 already established for `llm_response_id` (Design
Decisions #6 in Stage 13's own frozen architecture) — an id that identifies the *request*, never the
*response's own content*.

**Why this separation is correct:** The tool's own output may be non-deterministic (an external API
returning different results across calls, a time-dependent computation). Hashing the output into the
id would make the id itself non-deterministic, violating Principle 1 for every field that depends on
it. Hashing only the request inputs preserves determinism for the identity while honestly
acknowledging non-determinism in the result — never hidden, never assumed away.

## Tool Invocation Lifecycle

The one and only valid execution sequence:

```
ToolRequest { tool_name, arguments, request_context }
      │
      ▼
[1] validate_tool_request(tool_request)   — structural shape only: required keys present, correctly
      typed. Malformed input raises ToolInvocationInputError immediately; nothing downstream is ever
      touched.
      │
      ▼
[2] tool_definition = registry.get_tool(tool_request.tool_name)   — resolve the tool's definition;
      None → TOOL_NOT_FOUND, raises ToolInvocationInputError immediately
      │
      ▼
[3] validate_arguments(tool_request.arguments, tool_definition.parameter_schema)   — structural
      validation of the request's arguments against the tool's declared parameter schema;
      TOOL_ARGUMENTS_INVALID on violation, raises ToolInvocationInputError
      │
      ▼
[4] verify_execution_policy(tool_definition.execution_policy)   — verify the tool's declared
      execution policy permits invocation (currently a no-op expansion point — all registered tools
      are invocable; see Design Decisions #4)
      │
      ▼
[5] raw_result = adapter.invoke(tool_name, arguments, tool_definition)   — the sole external side
      effect; adapter raises ToolExecutionError on failure
      │
      ▼
[6] validate_tool_result(raw_result, tool_definition.output_schema)   — structural validation of
      the tool's output against its declared output schema; TOOL_OUTPUT_SCHEMA_VIOLATION as a finding
      (WARNING, not a failure — see Design Decisions #5)
      │
      ▼
[7] build_tool_execution_record(tool_request, tool_definition, raw_result_or_error, latency_ms)
      — computes tool_execution_record_id, status, and this stage's own findings
      │
      ▼
[8] validate_tool_execution_record(record)   — internal invariant self-check; raises
      ToolInvocationInternalError on violation
      │
      ▼
ToolExecutionRecord { status, output, findings, ... }
```

No hidden execution paths. No reordered operations. Every step executes exactly once per invocation.

## Tool Execution Policy

The `execution_policy` on a `ToolDefinition` declares static, immutable constraints about the tool.
Stage 20 reads and records these constraints but — with one exception — never acts on them itself:

- **`max_timeout_seconds`**: Passed to the `ToolAdapter` as part of the `tool_definition` argument;
  the adapter may use it to bound its own invocation time. Stage 20 itself owns no timeout
  enforcement (see Concurrency) — the same posture Stage 18 established for its own timeout handling
  (delegating entirely to Stage 13's own `timeout_seconds`).

- **`idempotent`**: Recorded in the `ToolExecutionRecord` for upstream consumers (Stage 21 may use
  it to decide whether a failed tool call is safe to retry). Stage 20 never retries a tool call,
  regardless of this flag.

- **`side_effects`**: Recorded in the `ToolExecutionRecord` for upstream consumers (Stage 21 may use
  it to reason about execution safety). Stage 20 never reasons about side-effect safety.

### Policy Scope

Stage 20 enforces only **deterministic structural execution policy** — verifying that the
`execution_policy` dict is well-formed (required keys present, correctly typed) and recording its
values for upstream consumers. Stage 20 explicitly does **not** enforce, evaluate, or participate in:

- **Authorization or permission systems** — deciding whether a caller is *allowed* to invoke a
  specific tool is a deployment-layer or caller-level concern, never Stage 20's.
- **Business-rule evaluation** — deciding whether a tool invocation is *appropriate* in a given
  business context is a caller-level or Stage 21-level concern.
- **Semantic approval** — deciding whether a tool invocation *makes sense* given a user's intent
  or a conversation's history is Stage 21's exclusive responsibility.
- **Planning or agent reasoning** — deciding whether a tool invocation advances a goal, should be
  retried, or should be replaced with a different tool is Stage 21's exclusive responsibility.
- **Workflow orchestration** — deciding where a tool invocation fits in a multi-step sequence is
  Stage 21's exclusive responsibility.

Every one of these is explicitly out of scope for Stage 20 and belongs to a future stage, the
deployment layer, or the caller.

### Policy Verification (Step [4])

`verify_execution_policy()` is currently a structural validation step that confirms the
`execution_policy` dict is well-formed (required keys present, correctly typed). It does not reject
any invocation based on policy values — every registered tool with a well-formed definition is
invocable. This step exists as an explicit expansion point: a future revision to this design could
introduce policy-based restrictions (e.g., "tools with `side_effects: true` require explicit caller
confirmation") without reorganizing the lifecycle.

## Serialization

### ToolExecutionRecord Serialization

- **Deterministic ordering.** All dict fields in `arguments`, `output`, `request_context`, and
  `findings` are serialized with `sort_keys=True` wherever canonical JSON is computed (identity
  hashing, logging). Display-order for human-readable output is document-declaration order.
- **UTF-8.** All text is UTF-8. Stage 20 never re-encodes text into any other encoding.
- **Unicode NFC preserved.** Stage 20 never applies its own NFC/NFKC normalization pass to any
  text — the same byte-for-byte preservation rule every prior stage already applies to text it
  passes through. Arguments and outputs are stored and serialized exactly as received.
- **Immutable output.** Once a `ToolExecutionRecord` is assembled and validated, it is never
  modified — the same documented (not language-enforced) contract every prior stage's own returned
  package already carries.
- **Identical serialization guarantee.** Two `ToolExecutionRecord`s with byte-identical content
  (excluding `executed_at` and `latency_ms`, which are excluded from all determinism comparisons)
  always produce byte-identical canonical JSON serialization. This follows from deterministic
  field ordering (`sort_keys=True`), UTF-8 encoding, and NFC preservation — no field's
  serialization depends on run-time state, platform, or locale.
- **Omission rules.** Every field named in the `ToolExecutionRecord` schema is always present —
  never conditionally omitted based on content (matching Stage 18's own omission rule). A failed
  invocation produces `output = null` and `status = "FAIL"`, both present, never missing keys.
- **Null handling.** `output` is `null` when `status == "FAIL"`. `request_context` fields are `null`
  when not caller-supplied. Every other field is always present and non-null.

## Validation

Three distinct, clearly-scoped groups of named codes — the same three-layer pattern Stage 13, 17, 18,
and 19 already established for their own Validation.

### Validation Boundary

Stage 20's validation is exclusively **structural** — it verifies shapes, types, required fields,
schema conformance, and internal invariant consistency. Stage 20 explicitly does **not** validate:

- **Factual correctness** — whether a tool's output is factually true or accurate.
- **Semantic correctness** — whether a tool's output meaningfully answers the question it was asked.
- **Business correctness** — whether a tool's output satisfies domain-specific business rules.
- **Domain correctness** — whether a tool's output is valid within a particular domain model.

All semantic, factual, business, and domain validation is the exclusive responsibility of whatever
consumes the `ToolExecutionRecord` downstream (Stage 21, a caller, or a deployment-level validator).

### 1. Input validation codes — raised, never returned as part of any `ToolExecutionRecord`:

| Code | Raised as | Trigger |
|---|---|---|
| `TOOL_REQUEST_MALFORMED` | `ToolInvocationInputError` | the received `ToolRequest` is missing a required key or has a wrong-typed value |
| `TOOL_NOT_FOUND` | `ToolInvocationInputError` | `tool_name` does not match any registered tool in the registry |
| `TOOL_ARGUMENTS_INVALID` | `ToolInvocationInputError` | `arguments` do not conform to the tool's declared `parameter_schema` |
| `TOOL_POLICY_MALFORMED` | `ToolInvocationInputError` | `execution_policy` on the resolved `ToolDefinition` is missing required keys or has wrong-typed values |

### 2. Package-level findings — recorded in `ToolExecutionRecord.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `TOOL_INVOCATION_FAILED` | FAIL | package | The adapter raised `ToolExecutionError`; `status = "FAIL"`, `output = null` |
| `TOOL_OUTPUT_SCHEMA_VIOLATION` | WARNING | package | The tool's output did not conform to its declared `output_schema`; output is still captured verbatim, `status` remains `PASS` |
| `TOOL_LATENCY_EXCEEDED` | WARNING | package | Execution latency exceeded `max_timeout_seconds` but the adapter still returned a result (informational) |

### 3. Internal invariant codes — raised by `validate_tool_execution_record()`, never returned:

| Code | Trigger |
|---|---|
| `RECORD_STATUS_OUTPUT_MISMATCH` | `status == "FAIL"` but `output` is not `null`, or `status == "PASS"` but `output` is `null` |
| `RECORD_TOOL_NAME_MISMATCH` | `record.tool_name != tool_request.tool_name` |
| `RECORD_TOOL_VERSION_MISMATCH` | `record.tool_version != tool_definition.tool_version` |
| `RECORD_ARGUMENTS_MISMATCH` | `record.arguments != tool_request.arguments` (after validation) |
| `RECORD_ID_MISMATCH` | `tool_execution_record_id` does not match a freshly recomputed hash |
| `RECORD_LATENCY_INVALID` | `latency_ms < 0`, or `latency_ms` is not `null` when `status == "PASS"` but is `null` |

Any of these raises `ToolInvocationInternalError` — the same fail-loud posture every prior stage's
own internal-invariant exceptions already establish.

`status` is computed once, from this truth table (evaluated top-to-bottom, first matching row wins):

| Condition | `status` |
|---|---|
| Adapter raised `ToolExecutionError` | `FAIL` |
| Adapter returned a `RawToolResult` successfully | `PASS` |

A WARNING-severity finding (`TOOL_OUTPUT_SCHEMA_VIOLATION`, `TOOL_LATENCY_EXCEEDED`) never by itself
changes `status` away from `PASS` — exactly the same "WARNING is informational, never a status driver
on its own" posture Stage 10/11/12/13 each established.

## Public Function Contracts

- `validate_tool_request(tool_request: ToolRequest) -> None` — structural input check; raises
  `ToolInvocationInputError` (code `TOOL_REQUEST_MALFORMED`) on a missing/wrong-typed required key.

- `resolve_tool(tool_name: str, registry: ToolRegistry) -> ToolDefinition` — looks up the tool by
  name; raises `ToolInvocationInputError` (code `TOOL_NOT_FOUND`) if not registered. Returns the
  immutable `ToolDefinition`.

- `validate_arguments(arguments: Dict[str, Any], parameter_schema: Dict[str, Any]) -> None` —
  validates the request's arguments against the tool's declared parameter schema; raises
  `ToolInvocationInputError` (code `TOOL_ARGUMENTS_INVALID`) on violation.

- `verify_execution_policy(execution_policy: Dict[str, Any]) -> None` — structural validation of
  the execution policy dict; raises `ToolInvocationInputError` (code `TOOL_POLICY_MALFORMED`) if
  malformed. Currently does not reject any invocation based on policy values.

- `build_tool_execution_record(tool_request: ToolRequest, tool_definition: ToolDefinition,
  raw_result: Optional[RawToolResult], error_code: Optional[str], latency_ms: int)
  -> ToolExecutionRecord` — computes `tool_execution_record_id`, `status`, and this stage's own
  `findings`; sets `tool_findings` from `tool_definition.execution_policy`.

- `validate_tool_execution_record(record: ToolExecutionRecord) -> None` — internal invariant
  self-check; raises `ToolInvocationInternalError` (one of the six named codes in Validation §3)
  on violation.

- `validate_tool_result(raw_result: RawToolResult, output_schema: Dict[str, Any]) -> List[Finding]`
  — validates the tool's output against its declared output schema; returns a list of findings
  (empty if valid, contains `TOOL_OUTPUT_SCHEMA_VIOLATION` if not). Never raises — schema violations
  are findings, not fatal errors (Design Decisions #5).

- `execute_tool(tool_request: ToolRequest, tool_registry: ToolRegistry,
  tool_adapter: ToolAdapter) -> ToolExecutionRecord` — the sole public entrypoint; orchestrates
  Lifecycle [1]–[8]; never reads or writes any local artifact and never touches the manifest; the
  only I/O it performs is via `tool_adapter.invoke()`.

## Failure Handling

- **Malformed `ToolRequest`** (missing/wrong-typed required key) — `ToolInvocationInputError`
  (`TOOL_REQUEST_MALFORMED`) raised immediately; no `ToolExecutionRecord` returned; adapter never
  called.
- **Unknown tool** (`tool_name` not in registry) — `ToolInvocationInputError` (`TOOL_NOT_FOUND`)
  raised immediately; no `ToolExecutionRecord` returned; adapter never called.
- **Invalid arguments** (don't match `parameter_schema`) — `ToolInvocationInputError`
  (`TOOL_ARGUMENTS_INVALID`) raised immediately; no `ToolExecutionRecord` returned; adapter never
  called.
- **Malformed execution policy** — `ToolInvocationInputError` (`TOOL_POLICY_MALFORMED`) raised
  immediately; no `ToolExecutionRecord` returned; adapter never called.
- **Adapter failure** (`ToolExecutionError` raised during invocation) —
  `ToolExecutionRecord{status="FAIL", output=null}` returned with a `TOOL_INVOCATION_FAILED` finding;
  the error is captured structurally, never swallowed, never re-raised as an unstructured exception.
- **Tool output schema violation** — `ToolExecutionRecord{status="PASS"}` returned with a
  `TOOL_OUTPUT_SCHEMA_VIOLATION` WARNING finding; the output is captured verbatim despite the schema
  mismatch (Design Decisions #5).
- **Registry failure** (`ToolRegistry.get_tool()` raises unexpectedly) — propagated unchanged,
  wrapped in `ToolInvocationInternalError` with the original exception, never silently swallowed.
  Same fail-loud posture as Stage 19's own `ConversationMemoryInternalError` for store failures.
- **No retry logic.** Stage 20 performs no retries of any tool invocation. A failed invocation
  produces a `FAIL`-status `ToolExecutionRecord` and is done. Whether a retry is warranted is
  Stage 21's decision, informed by the `execution_policy.idempotent` flag on the tool's definition.
- **No timeout ownership.** Stage 20 owns no timeout logic of its own. The
  `execution_policy.max_timeout_seconds` value is passed to the adapter as part of the
  `tool_definition`; whether and how the adapter enforces it is entirely the adapter's concern —
  the same posture Stage 18 established for its own timeout handling.
- **No hidden recovery behavior.** No fallback tool, no degraded mode, no silent substitution.

## Determinism

Stage 20 draws the same explicit line between deterministic and non-deterministic as Stages 13, 17,
18, and 19 — but with a distinction specific to tool invocation: Stage 20's own orchestration is
fully deterministic, but the external tool being invoked may itself be non-deterministic.

**Deterministic (guaranteed, byte-identical across runs, given identical input):**

- **Request validation.** Given an identical `ToolRequest`, the validation outcome is byte-identical
  every time.
- **Tool resolution.** Given an identical `(tool_name, ToolRegistry)`, `resolve_tool()` returns an
  identical `ToolDefinition` every time.
- **Argument validation.** Given identical `(arguments, parameter_schema)`, the validation outcome
  is byte-identical every time.
- **`tool_execution_record_id`.** A deterministic content-hash of `{tool_name, tool_version,
  arguments}` — identical requests always produce identical ids.
- **Status computation.** Given an identical adapter outcome (success vs. failure), `status` is
  determined identically every time.
- **Finding codes.** A given condition always produces the same finding code.
- **Validation outcomes.** `validate_tool_execution_record()` produces identical results for
  identical record content.
- **No hidden state.** Stage 20 holds no module-level mutable state; all state is in the
  `ToolExecutionRecord` being assembled.
- **No randomness.** No `uuid4()`, no random selection — every identifier Stage 20 produces is a
  deterministic content-hash.

**Explicitly NOT deterministic (inherent to external tool invocation; never assumed, never hidden):**

- **`output`.** The tool's own output; may differ across two calls with identical arguments (e.g., a
  search API returning updated results, a time-dependent computation). Never assumed byte-identical.
- **`latency_ms`.** Wall-clock by definition; excluded from every determinism comparison.
- **`executed_at`.** Timestamp; excluded from every determinism comparison.
- **`adapter_status`.** Depends on whether the external tool actually succeeded — not reproducible
  under real network/service conditions.

## Read-Only Guarantees

- Stage 20 never modifies `manifest.json`, any corpus artifact, any vector index, any embedding, any
  prompt template, any cache store, any conversation store, or any `APIResponse`.
- Stage 20 never modifies a `ToolDefinition` resolved from the registry.
- Stage 20 never modifies a `ToolRequest` after validation.
- Stage 20 never modifies a `RawToolResult` after capture.
- Stage 20 never modifies a `ToolExecutionRecord` after validation.
- Stage 20 never calls Stage 18's `handle_request()`, Stage 19's conversation functions, or any
  stage below Stage 18.
- The only external side effect Stage 20 performs is the outbound tool invocation via
  `tool_adapter.invoke()` — the same class of side effect Stage 13's own `llm_adapter.invoke()`
  already performs (a call to an external service), nothing new in kind, only in purpose (tool
  execution rather than LLM generation).
- Stage 20 holds no module-level mutable state. No global registries, no singletons, no thread-local
  storage.

## Design Decisions

1. **Registry abstraction, not hard-coded tool list.** Tools are resolved from an abstract
   `ToolRegistry`, never hard-coded in Stage 20's own source. This mirrors the adapter pattern
   every prior stage already established (`IndexAdapter`, `LLMAdapter`, `CacheAdapter`,
   `ConversationStore`) and serves the same purpose: Stage 20's own logic is independent of which
   concrete tools exist, how they are discovered, or where their implementations live.

2. **Immutable tool definitions.** A `ToolDefinition` is a static, declarative specification — it
   declares what a tool accepts, what it produces, and what constraints govern its use. It is never
   modified at runtime by Stage 20 or by a tool invocation. This guarantees that validation
   outcomes are deterministic and that the `tool_version` recorded in a `ToolExecutionRecord`
   faithfully identifies the interface that governed that execution.

3. **Deterministic orchestration, non-deterministic tool output.** Stage 20 guarantees that its
   *own* orchestration — request validation, tool resolution, argument validation, status
   computation, identity hashing — is fully deterministic. It explicitly does *not* claim that
   tool output is deterministic, because external tools may depend on time, network state, external
   databases, or other non-reproducible factors. This is the same line Stage 13 already drew
   between its own deterministic request construction and the LLM's non-deterministic response.

4. **Execution policy verification is an expansion point, not a gate.** Currently, every registered
   tool with a well-formed definition is invocable — `verify_execution_policy()` validates structure
   only, never rejects based on policy values. This is deliberate: Stage 20 has no knowledge of
   *why* a caller is requesting a tool invocation (that reasoning belongs to Stage 21), so it
   cannot meaningfully evaluate whether a given policy permits invocation in a given context. The
   step exists so a future revision can introduce policy-based restrictions without reorganizing the
   lifecycle.

5. **Schema-violating tool output is captured, not rejected.** A tool that returns output not
   conforming to its declared `output_schema` produces a `TOOL_OUTPUT_SCHEMA_VIOLATION` WARNING
   finding, not a `FAIL` status. Rationale: the tool *did* execute and *did* return something —
   rejecting that result would discard potentially useful information. The warning signals a
   contract violation (likely an adapter or tool implementation bug) without suppressing the actual
   output. A caller or Stage 21 can decide whether to trust a schema-violating result.

6. **No retry logic.** Stage 20 never retries a failed tool invocation. This is a deliberate
   separation of concerns:
   - Stage 20 owns *execution*: validate, invoke, capture, package.
   - Stage 21 owns *planning*: decide whether to retry, substitute a different tool, or abandon
     the tool call entirely.
   A tool that fails produces a `FAIL`-status `ToolExecutionRecord`. Stage 21 can inspect the
   `execution_policy.idempotent` flag and the failure finding to decide whether a retry is safe
   and warranted. Embedding retry logic in Stage 20 would blur this boundary and duplicate
   decision-making that belongs to the planning layer.

7. **Separation from conversation memory (Stage 19).** Stage 20 has no knowledge of conversations,
   turns, or conversation history. A tool invocation is a single, stateless operation. If a tool
   result needs to be recorded in conversation history, that is the caller's responsibility (using
   Stage 19's own `append_turn()` to store the result as part of an assistant message). Stage 20
   never calls Stage 19.

8. **Separation from API serving (Stage 18).** Stage 20 never calls Stage 18's `handle_request()`
   and Stage 18 never calls Stage 20's `execute_tool()`. The two stages operate at different layers:
   Stage 18 orchestrates the per-turn query pipeline (Stages 10–17); Stage 20 executes individual
   tool calls. A future orchestration layer (Stage 21 or a deployment-level coordinator) may call
   both, but neither calls the other directly.

9. **Tool selection is excluded.** Deciding *which* tool to call is a reasoning task that requires
   understanding the user's intent, the available tools' capabilities, and the current state of a
   multi-step plan. That is Stage 21's responsibility. Stage 20 receives a `ToolRequest` with an
   explicit `tool_name` and executes it — it never evaluates whether a different tool would be more
   appropriate, never ranks tools by relevance, and never suggests alternatives.

10. **Planning is excluded.** Orchestrating a sequence of tool calls — deciding whether a tool
    result necessitates another tool call, whether to try an alternative approach, or whether the
    overall goal has been achieved — is Stage 21's exclusive responsibility. Stage 20 executes one
    tool call at a time and returns the result. It has no concept of a "plan", a "goal", or a
    "step sequence".

## Constants

```python
TOOL_EXECUTION_VERSION = "1.0.0"

# Argument validation
MAX_ARGUMENT_DEPTH = 10                    # maximum nesting depth for argument validation
MAX_ARGUMENT_SIZE_BYTES = 1_000_000        # maximum serialized size of arguments (1 MB)

# Output validation
MAX_OUTPUT_SIZE_BYTES = 10_000_000         # maximum serialized size of tool output (10 MB)
```

No numeric threshold, ceiling, or default from any prior stage is duplicated here — every one Stage
20 defines is its own, governing tool invocation only.

## Complexity

- `validate_tool_request()` — O(1): structural key/type checks.
- `resolve_tool()` — O(1): registry lookup by name (assuming the registry itself provides O(1)
  lookup, which is a reasonable expectation for any concrete implementation).
- `validate_arguments()` — O(A) where A is the number of argument fields: iterate over properties,
  check types and constraints.
- `verify_execution_policy()` — O(1): structural key/type checks.
- `execute_tool()` overall — O(A + T) where A is argument validation cost and T is the tool's own
  execution time (dominated by the external invocation).
- `validate_tool_execution_record()` — O(A): re-hash of arguments for id verification.

## Logging

Per the shared Logging Specification (`stage: "stage20_tool_function_calling"`, `doc_id: null` always
— entries are request-scoped, not document-scoped). New codes this stage adds:

- `INFO_TOOL_INVOCATION_START` — a tool invocation has been requested.
- `INFO_TOOL_INVOCATION_COMPLETE` — a tool invocation completed successfully.
- `WARNING_TOOL_OUTPUT_SCHEMA_VIOLATION` — the tool's output did not conform to its declared schema.
- `WARNING_TOOL_LATENCY_EXCEEDED` — execution latency exceeded the declared timeout.
- `FATAL_TOOL_INVOCATION_FAILED` — the adapter raised `ToolExecutionError`.

No new `FATAL_*` code beyond `FATAL_TOOL_INVOCATION_FAILED` — Stage 20 never sets a manifest
`error_code`, since it never touches the manifest at all.

## Concurrency

### Ownership

Stage 20 itself is single-threaded and deterministic — it makes no concurrency guarantees of its own,
performs no locking, and holds no mutex or semaphore. Safe under concurrent calls because it holds no
shared mutable state of its own: any number of `execute_tool()` calls may run simultaneously with no
local race condition.

### External Tool Concurrency

The external tool being invoked may itself have concurrency constraints (rate limits, mutual exclusion
requirements). Those are entirely the `ToolAdapter`'s and the tool implementation's own concern —
Stage 20 never coordinates concurrent access to the same tool, the same external API, or the same
shared resource.

### Timeout Ownership

Stage 20 owns no timeout logic of its own. The `execution_policy.max_timeout_seconds` is communicated
to the `ToolAdapter` via the `tool_definition` argument — whether and how the adapter enforces it is
the adapter's own responsibility. This mirrors the posture Stage 18 established (no timeout of its
own, delegating to Stage 13's own `timeout_seconds`).

## Security Considerations

- **Untrusted tool arguments.** `tool_request.arguments` may originate from an LLM's generated
  output (via Stage 21's future agent planner) and may contain adversarial input. Stage 20
  validates arguments structurally against the `parameter_schema` but performs no content-level
  sanitization — that defense, if needed, is the `ToolAdapter`'s or the tool implementation's own
  responsibility. This mirrors Stage 13's own posture toward untrusted model output.

- **Untrusted tool output.** The tool's own output is treated as untrusted, opaque content — never
  interpreted, executed, or interpolated into a path/shell/eval by Stage 20. A tool can return
  adversarial content (injection payloads, misleading data); Stage 20 performs no sanitization.
  Whatever consumes the `ToolExecutionRecord` downstream is responsible for handling the content
  safely.

- **No credential handling.** Tool credentials (API keys, tokens, authentication headers) are
  `ToolAdapter`-level configuration, supplied by the caller to the adapter, never passed through,
  logged, or included in `ToolExecutionRecord`, `findings`, or any log entry Stage 20 itself emits.

- **Tool isolation.** Stage 20 has no mechanism to restrict what a tool *does* when invoked — the
  tool may read files, make network calls, modify external state, or perform any other operation
  its implementation supports. Constraining tool behavior is the `ToolAdapter`'s and the
  deployment's own concern. Stage 20 records the declared `side_effects` flag for upstream
  consumers but never enforces it.

- **Argument size limits.** `MAX_ARGUMENT_SIZE_BYTES` guards against pathologically large argument
  payloads that could exhaust memory during validation or serialization. `MAX_OUTPUT_SIZE_BYTES`
  provides the analogous guard for tool output.

## Known Limitations

- **No retry logic.** A failed tool invocation is never retried by Stage 20. Whether a retry is
  warranted is Stage 21's decision, not Stage 20's. This means a transiently-failing tool will
  produce a `FAIL`-status `ToolExecutionRecord` even if a second attempt might have succeeded.
  Accepted because embedding retry decisions in the execution layer would blur the
  execution/planning boundary.

- **No tool output caching.** Stage 20 does not cache tool results. Two identical `ToolRequest`s
  each trigger a fresh tool invocation. A future caching layer (analogous to Stage 17 for LLM
  responses) could be introduced as a separate concern.

- **No parallel tool execution.** Stage 20 executes one tool per `execute_tool()` call.
  Parallelizing multiple tool calls is a planning/orchestration concern belonging to Stage 21.

- **No streaming.** Tool results are fully materialized before being returned. A tool that produces
  large output incrementally still returns it as one complete `RawToolResult`.

- **No tool discovery or auto-registration.** Stage 20 cannot find tools on its own; every tool must
  be explicitly registered in the `ToolRegistry` by the deployment configuration.

- **Schema validation is structural only.** `validate_arguments()` and `validate_tool_result()`
  check types and required fields per the JSON-Schema-like declarations. They do not enforce
  semantic constraints (e.g., "this date must be in the future" or "this ID must reference a real
  entity").

- **No cross-tool state.** Each tool invocation is independent. Stage 20 has no mechanism for one
  tool to pass state to another tool or for a tool to access results from a previous invocation.
  Cross-tool coordination is Stage 21's responsibility.

- **`output_schema` violations are warnings, not failures.** A tool that returns malformed output
  produces a WARNING, not a FAIL. This means downstream consumers must handle potentially
  schema-violating output — accepted because discarding a real tool result is worse than flagging
  it as suspect.

## Future Stage Boundaries

Stage 21+ (not designed here) owns everything Stage 20 deliberately excludes:

- **Stage 21 — Agent Planning** owns deciding *which* tool to call, *when* to call it, *why* one
  tool is preferable to another, and *how* to sequence multiple tool calls into a coherent plan.
  It consumes `ToolExecutionRecord`s from Stage 20 and uses them to make planning decisions —
  including whether to retry a failed call, try an alternative tool, or abandon the tool-use
  approach entirely. Stage 20 executes; Stage 21 plans.

- **Tool result integration into conversation memory** — recording a tool result as part of an
  assistant message in Stage 19's conversation history is a coordination concern handled by
  whatever orchestration layer (Stage 21 or a deployment-level coordinator) calls both Stage 19
  and Stage 20. Stage 20 never calls Stage 19.

- **Tool result integration into prompts** — injecting a tool result into Stage 12's prompt
  templates is an integration concern handled by a future prompt template version or integration
  layer. Stage 20 never calls Stage 12.

- **Tool result caching** — caching tool results to avoid redundant invocations is a future concern,
  potentially analogous to Stage 17's response caching pattern. Not designed here.

- **Tool-aware LLM invocation** — modifying Stage 13's `LLMAdapter` contract to support tool-use
  modes (function calling APIs, tool-use prompts) is a future integration concern. Stage 20
  invokes tools independently of Stage 13; how tool results are fed back to the LLM is an
  integration concern this design deliberately leaves open.
