# Stage 19 — Conversation Memory

Stages 0–18 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 19 manages multi-turn conversation state: it creates, extends, retrieves, closes, and selects
which portion of a conversation's history should be supplied alongside the current turn's query to a
future downstream consumer. It performs no retrieval, no prompt construction, no LLM invocation, no
citation extraction, no groundedness validation, no answer quality evaluation, no response caching,
and no API response serving of its own; every one of those remains exactly what its own frozen stage
already computed, untouched. Stage 19 sits *above* Stage 18 in the call hierarchy: a conversation-
aware caller invokes Stage 19 to prepare the conversational context, then passes the current turn's
query (potentially enriched with selected conversation history) into Stage 18's own unmodified
`handle_request()`. Stage 19 never modifies Stage 18 or any stage below it.

`start_conversation(config)`, `append_turn(conversation_id, turn)`,
`select_memory(conversation_id, selection_config)`, `get_conversation(conversation_id)`,
`close_conversation(conversation_id)`, and `validate_conversation(conversation_state)` are the
public entrypoints.

## Scope

Stage 19 answers exactly one question — given a conversation's accumulated history, what ordered,
bounded, deterministic slice of that history should accompany the current turn's query to whatever
downstream consumer needs it — and stops there. It never builds a prompt from that history (Stage
12's frozen job, extended by a future integration layer); never invokes an LLM to summarize, rephrase,
or compress the history; never performs retrieval, embedding, or reranking of conversation turns; never
evaluates answer quality or groundedness; never caches responses; never serves an API; never calls a
tool or function; never plans multi-step actions. Those boundaries are restated in Non-Responsibilities
and Future Stage Boundaries.

## Responsibilities

Stage 19 shall: create new conversations with a unique, stable `conversation_id` that never changes
for the conversation's lifetime; accept new turns (user message, assistant message) and append them
immutably to the conversation's ordered history without any hard ceiling on total conversation length;
structurally validate every turn before appending (individual message integrity only, never total
conversation size); maintain a deterministic, monotonically increasing `turn_index` within each
conversation; select a bounded, ordered window of past turns for downstream consumption, governed by
a fixed, deterministic window policy and a configurable character budget; serialize the selected memory
window into a deterministic, transport-agnostic `ConversationMemoryPackage`; track conversation
lifecycle state (`ACTIVE`, `CLOSED`); self-check every returned `ConversationMemoryPackage`'s internal
invariants before it is ever returned; and provide read-only access to a conversation's full history
for auditing and debugging purposes.

## Non-Responsibilities

Stage 19 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: prompt construction or template rendering of any kind (Stage 12's frozen job —
conversation history is *selected and serialized* by Stage 19, but how it is injected into a prompt
template is a separate integration concern, not Stage 19's own); LLM invocation for summarization,
compression, rephrasing, or any other transformation of conversation history (Principle 5 — see Design
Decisions #1); semantic similarity, embedding-based retrieval, or relevance ranking of conversation
turns (Principle 5 — see Design Decisions #2); any modification to Stage 18's `handle_request()` or
any stage below it; retrieval, context assembly, citation extraction, groundedness validation, answer
quality evaluation, or response caching; tool or function calling (Stage 20's future scope); agent
planning (Stage 21's future scope); user authentication, session management beyond conversation
lifecycle, or rate limiting; streaming of any kind; choosing, importing, or depending on any concrete
storage framework, transport framework, or database library.

## Inputs

Two required inputs per operation, at two different scopes:

- **Per-operation:** the operation's own arguments (e.g., `turn` for `append_turn()`,
  `selection_config` for `select_memory()`).
- **`ConversationStore`** (this stage's own new contract, see Conversation Storage Abstraction) —
  per-deployment, supplied once at wiring time: a pre-configured store providing `get()`, `put()`,
  and `delete()` operations over conversation state. The store is the sole mechanism through which
  Stage 19 reads and writes conversation state — Stage 19 never directly opens, reads, or writes
  any file, database, or external service itself. `ConversationStore` mirrors the `CacheAdapter`
  pattern Stage 17 already established: Stage 19 defines the abstract contract; a concrete
  implementation lives entirely outside this design (see Conversation Storage Abstraction).

No other input is read. `manifest.json`, `chunks.json`, `metadata.json`, vector indexes, embeddings,
prompt templates, and every earlier-stage artifact are never opened — Stage 19 operates exclusively on
its own conversation state objects, never on corpus artifacts.

## Outputs

`ConversationMemoryPackage` (see Schemas) is Stage 19's primary return value from `select_memory()`.
`ConversationState` (see Schemas) is returned by `get_conversation()` and `start_conversation()`.
Neither is persisted as a distinct file artifact by Stage 19 itself — the sole persisted state is
whatever the caller-supplied `ConversationStore` writes internally, an artifact Stage 19 owns through
the `ConversationStore` contract but whose format, location, and backend are entirely undefined by this
architecture.

## Pipeline Ordering

Stage 19 sits **above** Stage 18, never inside it. A conversation-aware orchestration layer calls
Stage 19 to select memory, then passes the enriched request into Stage 18's own unmodified
`handle_request()`. Stage 19 never calls Stage 18, and Stage 18 never calls Stage 19. The two stages
share no internal state — their interaction is mediated entirely by the caller that coordinates them:

```
External caller or future orchestrator
      │
      ├──▶ [1] Stage 19: start_conversation / get_conversation
      │
      ├──▶ [2] Stage 19: select_memory(conversation_id, selection_config)
      │         → ConversationMemoryPackage
      │
      ├──▶ [3] Caller constructs the enriched APIRequest (adding conversation context to query
      │         or pipeline_options — integration detail, outside both Stage 18 and Stage 19's scope)
      │
      ├──▶ [4] Stage 18: handle_request(enriched_request, deps) → APIResponse
      │
      ├──▶ [5] Stage 19: append_turn(conversation_id, turn)
      │
      └──▶ [repeat from step 2 for each subsequent turn]
```

Stage 19's own design sequence number (19) does *not* imply it executes after Stage 18 within the
single-request pipeline — it operates at a different layer entirely: the conversation layer, which
wraps the per-turn pipeline (Stages 10–18) rather than extending it.

## Conversation Model

### Conversation

A `Conversation` is an ordered sequence of turns between a user and the system, bounded by a creation
event and an optional close event. Every conversation has:

- A unique, stable `conversation_id` that never changes for the conversation's lifetime.
- An immutable creation timestamp.
- A monotonically increasing turn sequence.
- A lifecycle state (`ACTIVE` or `CLOSED`).
- Immutable metadata established at creation time.

A conversation's history grows without bound — Stage 19 imposes no hard ceiling on the number of
turns or total character count of a conversation's stored history. The `select_memory()` window
mechanism governs what subset of that history is presented downstream; the full history is always
preserved for audit and debugging, regardless of how large it grows. Resource-level constraints
(storage capacity, memory pressure) are the `ConversationStore` implementation's concern, never
Stage 19's own in-memory logic.

### Turn

A `Turn` is one exchange within a conversation: a user message followed by an assistant response.
Turns are ordered by `turn_index` (0-indexed, monotonically increasing, contiguous, never reordered
or renumbered after creation). Each turn is immutable once appended — its content, metadata, and
provenance are never modified.

### Messages

A turn contains exactly two messages:

- **User message** (`speaker: "user"`) — the user's query text for this turn, captured verbatim,
  byte-for-byte.
- **Assistant message** (`speaker: "assistant"`) — the system's response text for this turn, copied
  verbatim from the `APIResponse.answer.response_text` that Stage 18 produced for this turn. Never
  rewritten, summarized, or reformatted by Stage 19.

### System Messages — Excluded by Design

Stage 19 does **not** model system messages. This is a deliberate ownership boundary, not an
oversight:

- **Ownership.** System prompts are exclusively Stage 12's concern — loaded from versioned, static
  template files (`config/prompt_templates/<version>/system_prompt.txt`), never from conversation
  history. Stage 12 owns the system prompt's content, format, and lifecycle. Stage 19 owns
  conversation history (user/assistant exchanges). Neither stage crosses into the other's domain.

- **Rationale.** Storing system prompts in conversation history would duplicate content already
  managed by Stage 12, introduce a second source of truth for system-prompt text, and blur the
  ownership boundary between "what instructions govern the model's behavior" (Stage 12) and "what
  prior exchanges provide conversational context" (Stage 19). A system prompt is not part of the
  conversation — it is part of the prompt template.

- **Future-stage boundary.** If a future design requires injecting conversation-specific system
  instructions (e.g., "you are helping this user with topic X, based on prior exchanges"), that
  injection belongs to a future integration layer between Stage 19 and Stage 12, or to a new prompt
  template version that defines a `{{conversation_context}}` placeholder — never to Stage 19 storing
  system messages alongside user/assistant turns. Stage 19's `serialized_memory` output is consumed
  by whatever downstream integration exists; Stage 19 itself never decides where in a prompt that
  memory appears.

### Ownership

Stage 19 owns the conversation, its turns, and their messages. It does not own, and never reads or
writes, any upstream pipeline artifact (`RetrievalResult`, `ContextPackage`, `PromptPackage`,
`LLMResponse`, `CitedResponse`, `GroundednessReport`, `AnswerQualityReport`, `CachedExecutionResult`,
`APIResponse`). The assistant message's `response_text` is copied into the turn at append time;
after that copy, Stage 19 holds no reference to, and never consults, the `APIResponse` it came from.

## Conversation Identity Model

Stage 19 distinguishes three levels of identity, each with a distinct stability guarantee:

### 1. `conversation_id` — Stable for the conversation's lifetime

```
conversation_id = "conv_" + sha256(session_seed_bytes).hexdigest()[:16]
```

Where `session_seed_bytes` is the UTF-8 encoding of the caller-supplied `session_seed` string
(required, non-empty). The `conversation_id` is computed exactly once, at creation time, and never
recomputed — it remains byte-identical from the conversation's first turn to its last, regardless of
how many turns are appended, how many memory selections are performed, or whether the conversation is
closed.

**Why stable:** A `conversation_id` is an external reference — callers store it, pass it between
systems, use it for correlation. If the id changed when state evolved, every external reference would
become stale, and the caller would lose the ability to address the conversation. Stability is a hard
requirement for any identifier that crosses a system boundary.

**Why deterministic:** Identical `session_seed` always produces the identical `conversation_id`. This
makes conversation creation reproducible in tests and auditable in production — a caller that knows
the seed can predict the id without calling `start_conversation()`.

### 2. `conversation_state_version` — Changes whenever conversation state changes

```
conversation_state_version = turn_count
```

A monotonically increasing integer, equal to `turn_count`, incremented on every `append_turn()`.
Not a hash, not a content address — simply the sequence number of the most recent mutation. This is
not a separate field in the schema; `turn_count` already serves this purpose exactly. A caller that
needs to detect whether a conversation has changed since it last read it compares `turn_count`.

**Why mutable:** Conversation state evolves with every appended turn. A fixed identifier for evolving
state would either become stale (misleading) or require hashing the entire entry list on every read
(expensive and unnecessary when a monotonic counter already exists).

### 3. `conversation_memory_package_id` — Derived from the selected memory window

```
conversation_memory_package_id = "cmp_" + sha256(canonical_content).hexdigest()[:16]
```

Where `canonical_content` is the canonical JSON serialization of `{conversation_id,
window_start_turn_index, window_end_turn_index, serialized_memory}`. This makes the package id
deterministic and content-addressable — identical selected content always produces the identical
package id, matching the `*_id` convention every prior stage already established for its own packages.

**Why content-derived:** A `ConversationMemoryPackage` is a snapshot of a selection — it captures
a specific window of a specific conversation at a specific point in its history. Two selections of
the same window from the same conversation must produce the same id (determinism). A selection of a
different window, or from a different conversation state (new turns appended), must produce a
different id (content-addressability).

### Identity Stability Summary

| Identifier | Scope | Stability | Changes when |
|---|---|---|---|
| `conversation_id` | Conversation | Permanent | Never — assigned at creation, immutable |
| `turn_count` | Conversation state | Monotonic | Every `append_turn()` |
| `conversation_memory_package_id` | Memory selection | Content-derived | Selected window content changes |

## Schemas

All in-memory Python structures — none persisted in a format Stage 19 itself defines (the
`ConversationStore` owns its own persistence format, opaque to this design).

### MemoryEntry

```jsonc
{
  "conversation_id": "conv_a1b2c3d4e5f6",       // stable, see Conversation Identity Model
  "turn_index": 0,                                // 0-indexed, monotonically increasing, contiguous
  "speaker": "user",                              // "user" | "assistant" — closed vocabulary, no other value
  "content": "What are the SDG financing gaps?",  // verbatim message text; never null, never empty
  "created_at": "2026-07-22T07:00:00Z",           // wall-clock when this entry was appended; excluded from
                                                   // determinism comparisons (same treatment as every prior
                                                   // stage's own timestamp)
  "provenance": {
    "request_id": "...",                           // Stage 18's own request_id for this turn (user message: the
                                                   // request_id of the APIRequest that carried this query;
                                                   // assistant message: the request_id of the APIResponse that
                                                   // produced this answer); establishes a traceable link back to
                                                   // the per-turn pipeline execution without Stage 19 needing
                                                   // to know anything about what that pipeline computed
    "api_pipeline_version": "1.0.0"                // copied verbatim from APIResponse.api_pipeline_version;
                                                   // provides version traceability for the pipeline that
                                                   // produced this turn's answer
  }
}
```

**Field justification:**
- `conversation_id`: groups entries into one conversation; required for retrieval and lifecycle.
- `turn_index`: orders entries deterministically within a conversation; required for window selection.
- `speaker`: identifies message origin; required for rendering user/assistant pairs.
- `content`: the actual message text; the reason this entry exists.
- `created_at`: audit trail; explicitly excluded from determinism.
- `provenance.request_id`: links this turn to its Stage 18 execution; required for debugging and audit.
- `provenance.api_pipeline_version`: version traceability; ensures history entries can be attributed
  to the pipeline version that produced them.

### ConversationState

```jsonc
{
  "conversation_id": "conv_a1b2c3d4e5f6",         // stable — never changes after creation
  "conversation_memory_version": "1.0.0",          // this schema's own version
  "status": "ACTIVE",                               // "ACTIVE" | "CLOSED" — see Conversation Lifecycle
  "created_at": "2026-07-22T07:00:00Z",             // wall-clock; excluded from determinism
  "closed_at": null,                                 // null while ACTIVE; set on close; excluded from determinism
  "turn_count": 3,                                   // current number of complete turns (each = user + assistant);
                                                     // also serves as conversation_state_version (see Identity Model)
  "entries": [                                       // ordered list of MemoryEntry objects; append-only; unbounded
    // ... MemoryEntry objects, alternating user/assistant, in turn_index order
  ],
  "metadata": {
    "title": null,                                   // optional, caller-supplied at creation; never auto-generated
    "tags": []                                        // optional, caller-supplied at creation; never auto-generated
  },
  "findings": []                                     // Stage 19's own findings: {severity, code, message}
}
```

**Lifecycle states:**

| Status | Meaning | Allowed operations |
|---|---|---|
| `ACTIVE` | Conversation is open; new turns may be appended | `append_turn`, `select_memory`, `get_conversation`, `close_conversation` |
| `CLOSED` | Conversation is permanently closed; history is read-only | `select_memory`, `get_conversation` |

There is no `ARCHIVED` state distinct from `CLOSED`. Archival, if ever desired (e.g., moving cold
conversations to cheaper storage), is a `ConversationStore` implementation concern, never a
conversation lifecycle state Stage 19 itself defines.

**Conversation versioning:** `ConversationState` carries `conversation_memory_version` (the schema
version), not a content version or edit counter. Since entries are append-only and never modified,
`turn_count` serves as the state version — a monotonically increasing integer that changes on every
`append_turn()` and is always available for staleness detection.

### ConversationMemoryPackage

```jsonc
{
  "conversation_memory_package_id": "cmp_...",     // deterministic hash of selected content (see Identity Model)
  "conversation_id": "conv_a1b2c3d4e5f6",          // stable reference to the source conversation
  "conversation_memory_version": "1.0.0",
  "selected_turn_count": 5,                        // number of complete turns in the selected window
  "total_turn_count": 12,                           // total turns in the full conversation at selection time
  "window_start_turn_index": 7,                     // inclusive; the earliest turn_index in the window
  "window_end_turn_index": 11,                      // inclusive; the latest turn_index in the window
  "total_selected_characters": 8432,                // total character count across all selected entries
  "serialized_memory": "User: What are...\nAssistant: The SDG...\n...",
                                                    // deterministic, UTF-8, NFC-preserved rendering of the
                                                    // selected window; see Memory Serialization
  "status": "PASS",                                 // PASS | WARNING — see Validation §2
  "entries": [                                      // the selected MemoryEntry objects, in turn_index order
    // ... selected MemoryEntry subset
  ],
  "findings": [],                                   // Stage 19's own findings for this selection
  "selected_at": "2026-07-22T07:01:00Z"             // wall-clock; excluded from determinism
}
```

### SelectionConfig

```jsonc
{
  "max_turns": 10,                                  // maximum number of complete turns to include; optional,
                                                    // defaults to DEFAULT_SELECTION_MAX_TURNS
  "max_characters": 50000,                          // character budget for serialized memory; optional,
                                                    // defaults to DEFAULT_SELECTION_MAX_CHARACTERS
  "exclude_current_turn": true                      // if true, omit the most recent turn (the one being
                                                    // responded to now); typically true since the current
                                                    // query is already in the APIRequest
}
```

## Memory Selection Strategy

Selection is purely structural and fully deterministic. No semantic ranking, no embedding-based
similarity, no relevance scoring — Principle 5 explicitly forbids any such probabilistic judgment.

### Algorithm

Given a `conversation_id` and a `SelectionConfig`:

```
[1] Retrieve ConversationState from store
      │
      ▼
[2] Determine the effective window boundaries:
      a. effective_max_turns = min(selection_config.max_turns, MAX_SELECTION_TURNS_CEILING)
      b. If exclude_current_turn, the candidate pool is entries[0 .. last_complete_turn].
         Otherwise, entries[0 .. end].
      c. Take the most recent effective_max_turns complete turns (recency-first; see Design
         Decisions #3).
      │
      ▼
[3] Apply character budget:
      Starting from the most recent turn backward, accumulate entries. If adding the next turn's
      total characters (user + assistant) would exceed max_characters, stop. No partial-turn
      inclusion — a turn is either fully included or fully excluded (Design Decisions #4).
      │
      ▼
[4] The surviving entries, in their original turn_index order (ascending — oldest first), form
      the selected window. See Memory Window Guarantees.
      │
      ▼
[5] Serialize the selected window (Memory Serialization).
      │
      ▼
[6] Compute conversation_memory_package_id from the serialized content.
      │
      ▼
[7] Assemble ConversationMemoryPackage.
      │
      ▼
[8] validate_memory_package(package) — internal invariant self-check.
      │
      ▼
Return ConversationMemoryPackage
```

### Selection Guarantee

Given identical `(ConversationState, SelectionConfig)`, `select_memory()` always produces a
byte-identical `ConversationMemoryPackage` (excluding `selected_at`). This is guaranteed because:
- The entry list is append-only and immutable.
- Selection uses only structural criteria (turn_index, character count).
- Serialization is deterministic.
- The package id is a deterministic hash of the selected content.

## Memory Window Policy

The window policy is fixed and deterministic.

### Window Guarantees

The following invariants hold for every `ConversationMemoryPackage` produced by `select_memory()`:

1. **Contiguous turns only.** The selected window is always a contiguous range of `turn_index`
   values — `[window_start_turn_index, window_end_turn_index]` with no gaps. Stage 19 never
   cherry-picks non-adjacent turns.

2. **No skipped turns.** Within the selected window, every turn between `window_start_turn_index`
   and `window_end_turn_index` (inclusive) is present. There are no holes.

3. **No reordering.** The selected entries are always in strictly ascending `turn_index` order,
   matching the original conversation chronology. Stage 19 never reorders turns based on content,
   score, or any other criterion.

4. **Deterministic selection.** Given identical `(ConversationState, SelectionConfig)`, the same
   window is always selected — same `window_start_turn_index`, same `window_end_turn_index`, same
   entries, same serialization, same `conversation_memory_package_id`.

5. **Stable ordering.** The ordering of entries within a `ConversationMemoryPackage` is always
   ascending `turn_index` — oldest selected turn first, newest selected turn last. This matches the
   natural conversation chronology and is the order used for serialization (see Memory Serialization).

### Window Selection Rules

1. **Recency-first.** The most recent turns are always preferred. Older turns are dropped first when
   the window is constrained — the same prefix-truncation-in-reverse strategy every prior budget-
   enforcement stage already uses (Stage 11's own context budget drops the lowest-ranked blocks
   first; Stage 19 drops the oldest turns first, for the analogous reason: the most recent turns
   are most likely to be relevant to the current query).

2. **Complete turns only.** A turn is the atomic unit of inclusion. If both the user message and the
   assistant message cannot fit within the remaining budget, the entire turn is excluded — no
   partial-turn rendering, no orphaned user messages without their assistant responses.

3. **No gap.** The selected window is always a contiguous range of turn_indexes. Stage 19 never
   cherry-picks non-adjacent turns — this would require a relevance judgment forbidden by
   Principle 5.

4. **Conversation history is never discarded.** The full conversation history (all appended turns)
   is always preserved in the `ConversationState`, regardless of how large it grows. The active
   memory window is a *view* into that history, selected deterministically by `select_memory()` —
   not a replacement for it. A conversation with 200 turns still stores all 200 turns; a selection
   with `max_turns=10` simply returns the most recent 10 that fit within the character budget.

## Token / Character Budget Strategy

Stage 19 uses a **character-based budget**, not a token-based one.

**Rationale (Design Decisions #5):** Token counting requires a tokenizer, which is model-specific and
introduces a dependency on a particular LLM provider's tokenization library. Stage 19 has no
visibility into which model Stage 13 will ultimately use (that is resolved at Stage 18's own
`resolve_execution_config_for_api()`, or at deployment time via `deps.default_model_name`). Using a
character budget keeps Stage 19 fully model-independent and deterministic without approximation. If a
downstream consumer needs a token-budget conversion, it can apply its own `chars_per_token_estimate`
(the same fixed ratio Stage 11 already uses for its own context budget) to Stage 19's reported
`total_selected_characters`.

Budget enforcement is deterministic:
- Each entry's character count is `len(entry["content"])` — no approximation, no model-specific logic.
- A turn's total character cost is `len(user_entry["content"]) + len(assistant_entry["content"])`.
- Budget is consumed most-recent-turn-first, backward through the conversation.
- The budget check is strictly `accumulated + turn_cost <= max_characters` — no overshoot.

The character budget governs *selection* only — it determines how many turns fit in the downstream
memory window. It does not limit how many turns a conversation may store. A conversation may store
arbitrarily many turns; `select_memory()` simply selects the most recent window that fits the budget.

## Memory Serialization

### Format

```
User: <user message text>\nAssistant: <assistant message text>\n
```

Repeated for each selected turn, in ascending `turn_index` order (oldest selected turn first, newest
selected turn last), separated by a single newline (`TURN_SEPARATOR = "\n"`). The final entry is
followed by a trailing newline.

### Serialization Order

Serialization order is explicitly **ascending `turn_index`** — oldest selected turn first, newest
selected turn last:

```
Turn with lowest turn_index in window   (oldest)
      ↓
Turn with next turn_index
      ↓
...
      ↓
Turn with highest turn_index in window  (newest)
```

This matches the natural conversation chronology: when the serialized text is consumed by a
downstream prompt, the earliest context appears first and the most recent exchange appears last,
immediately before the current query. This ordering is fixed and non-configurable.

### Guarantees

- **Deterministic ordering.** Entries are serialized in ascending turn_index order — the same order
  they were appended. No content-dependent reordering.
- **UTF-8.** All text is UTF-8. Stage 19 never re-encodes text into any other encoding.
- **Unicode NFC preserved.** Stage 19 never applies its own NFC/NFKC normalization pass to message
  content — the same byte-for-byte preservation rule every prior stage already applies to text it
  passes through. Content is stored and serialized exactly as received.
- **Immutable output.** Once `serialized_memory` is computed and attached to a
  `ConversationMemoryPackage`, it is never modified — the same documented (not language-enforced)
  contract every prior stage's own returned package already carries.
- **Omission rules.** Every field named in the `ConversationMemoryPackage` schema is always present —
  never conditionally omitted based on content (matching Stage 18's own omission rule). An empty
  selection produces `serialized_memory = ""` and `entries = []`, both present, never missing keys.
- **Null handling.** Stage 19 introduces no new null-vs-omitted convention. `closed_at` is `null`
  while a conversation is `ACTIVE`. `metadata.title` is `null` when not caller-supplied. Every other
  field is always present and non-null.

## Conversation Lifecycle

### Create Conversation

`start_conversation(config: ConversationConfig) -> ConversationState`

Creates a new `ACTIVE` conversation with an empty entry list, a stable `conversation_id` derived from
`config.session_seed`, and the immutable metadata supplied by the caller. The conversation is
persisted via the `ConversationStore`. No hidden state transitions.

### Append Turn

`append_turn(conversation_id: str, turn: TurnInput) -> ConversationState`

Appends exactly two new `MemoryEntry` objects (user, then assistant) to the conversation's entry list.
The conversation must be `ACTIVE` — appending to a `CLOSED` conversation raises
`ConversationMemoryInputError("CONVERSATION_CLOSED")`. The `turn_index` is assigned automatically as
`conversation.turn_count` (the next sequential value). `turn_count` is incremented by 1.

There is no hard ceiling on the number of turns or total characters a conversation may store.
Conversations grow without bound. The `select_memory()` window mechanism governs what subset of that
history is presented downstream; the full history is always preserved for audit and debugging.

Individual message validation (non-empty string content, well-formed provenance) is enforced per turn
at append time. Stage 19 validates the *integrity of each individual turn* — it never rejects a turn
based on the conversation's total accumulated size.

### Close Conversation

`close_conversation(conversation_id: str) -> ConversationState`

Sets `status = "CLOSED"` and `closed_at` to the current wall-clock time.

**Reopening is permanently prohibited.** A closed conversation cannot be reopened — there is no
`reopen_conversation()` function, no `ACTIVE` transition from `CLOSED`, and no mechanism to reverse a
close. This is a deliberate, permanent constraint:

- Reopening would break the monotonic lifecycle guarantee (`ACTIVE → CLOSED` is a one-way transition).
- It would require re-validating the entire conversation state to ensure it is still consistent after
  an arbitrary time period — a complexity Stage 19 does not introduce.
- A caller that needs to continue a line of inquiry after closing a conversation should start a new
  conversation, optionally seeding it with relevant context from the closed one (outside Stage 19's
  scope).

Closing an already-closed conversation is idempotent (returns the existing state without modification,
no error raised).

### Retrieve Conversation

`get_conversation(conversation_id: str) -> ConversationState`

Returns the full `ConversationState` for the given conversation, including all entries. Read-only —
never modifies the stored state. A nonexistent `conversation_id` raises
`ConversationMemoryInputError("CONVERSATION_NOT_FOUND")`.

### Conversation Deletion

Stage 19 itself **never deletes conversations**. The `ConversationStore` contract exposes a `delete()`
method, but Stage 19's own code never calls it. Deletion semantics are as follows:

- **Stage 19's scope:** Conversations are created (`start_conversation`) and closed
  (`close_conversation`). Stage 19 performs no deletion of any kind — logical or physical.

- **Administrative deletion:** The `ConversationStore.delete()` method exists exclusively for
  administrative tooling, compliance workflows (e.g., GDPR right-to-erasure), or operational
  maintenance outside Stage 19's own scope. Whether `delete()` performs a logical soft-delete
  (marking a record as deleted) or a physical hard-delete (removing bytes from storage) is entirely
  the `ConversationStore` implementation's decision — Stage 19 does not specify, constrain, or
  depend on either behavior.

- **No cascading effects within Stage 19.** Since Stage 19 never calls `delete()`, there are no
  cascading effects to design. A deleted conversation simply ceases to be retrievable via `get()`;
  any subsequent call to `get_conversation()`, `append_turn()`, `select_memory()`, or
  `close_conversation()` for that `conversation_id` will encounter a `None` from `store.get()` and
  raise `ConversationMemoryInputError("CONVERSATION_NOT_FOUND")`.

### Memory Pruning

Stage 19 does **not** perform automatic pruning, summarization, or compression of conversation
history. This is a deliberate architectural choice (Design Decisions #6):

- Conversations grow without bound. There is no `max_turns` or `max_total_characters` ceiling on
  the stored history.
- The *selection* step (`select_memory()`) already provides a windowed view — a caller need not
  consume the full history. The full history is always preserved for audit and debugging.
- Summarization (collapsing older turns into a shorter representation) would require an LLM call,
  violating Principle 5. Stage 19 will never summarize.

If a deployment requires turn eviction or compaction, that behavior belongs to the
`ConversationStore` implementation itself (a TTL, a background archival job, etc.) — never to
Stage 19's own in-memory logic.

## Conversation Storage Abstraction

Stage 19 defines a `ConversationStore` contract — a minimal abstract interface for persisting and
retrieving `ConversationState` objects — matching the adapter pattern Stage 9 (`IndexAdapter`),
Stage 13 (`LLMAdapter`), and Stage 17 (`CacheAdapter`) already established:

```python
class ConversationStore(ABC):
    @abstractmethod
    def get(self, conversation_id: str) -> Optional[ConversationState]:
        """Returns the ConversationState for the given id, or None if not found."""

    @abstractmethod
    def put(self, conversation_state: ConversationState) -> None:
        """Stores (creates or replaces) a ConversationState."""

    @abstractmethod
    def delete(self, conversation_id: str) -> None:
        """Removes a conversation from the store. Idempotent.
        Stage 19 itself never calls this method — it exists for
        administrative tooling outside Stage 19's scope."""
```

### Abstraction Guarantees

The `ConversationStore` contract is an **adapter-only** abstraction. This architecture:

- **Selects no concrete backend.** No storage technology — filesystem, relational database, document
  database, key-value store, object store, or any other — is chosen, recommended, or assumed by this
  design. The choice of backend is a deployment decision, entirely outside Stage 19's scope.

- **Makes no filesystem assumption.** Stage 19 never assumes that conversations are stored as files,
  in directories, on local disk, or in any path-addressable structure. It calls `get()`, `put()`,
  and `delete()` — nothing more.

- **Makes no database assumption.** Stage 19 never assumes that conversations are stored in tables,
  rows, collections, documents, or any schema-specific structure. It has no knowledge of SQL, NoSQL,
  indexes, migrations, connection pooling, or query languages.

- **Makes no cloud assumption.** Stage 19 never assumes that conversations are stored in any cloud
  service (S3, DynamoDB, Cosmos DB, Firestore, Redis, etc.). It has no knowledge of regions,
  partitions, consistency models, or cloud-specific APIs.

- **Imports no storage library.** Stage 19 never imports, depends on, or references any concrete
  storage library, ORM, driver, or SDK. The abstract `ConversationStore` class is the sole
  dependency boundary.

A concrete implementation — an in-memory `dict`, a JSON file, a SQLite database, a Redis instance,
a DynamoDB table, or any other backend — lives entirely outside this design. Stage 19 defines only
the three-method abstract contract and relies on it exclusively.

## Validation

Three distinct, clearly-scoped groups of named codes — the same three-layer pattern Stage 18 already
established for its own Validation, and for the same reason: Stage 19 has no document to quarantine
and no persisted-per-document artifact to mark `FAIL`/`PASS`/`WARNING` against.

### 1. Input validation codes — raised, never returned as part of any package:

| Code | Raised as | Trigger |
|---|---|---|
| `CONVERSATION_NOT_FOUND` | `ConversationMemoryInputError` | `conversation_id` does not exist in the store |
| `CONVERSATION_CLOSED` | `ConversationMemoryInputError` | `append_turn()` called on a `CLOSED` conversation |
| `TURN_CONTENT_MISSING_OR_INVALID` | `ConversationMemoryInputError` | `turn.user_content` or `turn.assistant_content` is absent, not a string, or empty |
| `TURN_PROVENANCE_MISSING` | `ConversationMemoryInputError` | `turn.provenance` is absent or malformed (missing `request_id`) |
| `SELECTION_CONFIG_MALFORMED` | `ConversationMemoryInputError` | `selection_config` contains wrong-typed or out-of-range values |
| `SESSION_SEED_MISSING` | `ConversationMemoryInputError` | `config.session_seed` is absent, not a string, or empty |

### 2. Package-level findings — recorded in `ConversationMemoryPackage.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `WINDOW_TRUNCATED_BY_BUDGET` | INFO | package | Character budget caused fewer turns to be selected than `max_turns` would have allowed |
| `WINDOW_TRUNCATED_BY_MAX_TURNS` | INFO | package | `max_turns` limit caused older turns to be excluded |
| `EMPTY_CONVERSATION` | WARNING | package | Conversation has zero turns; `serialized_memory = ""` |
| `CONVERSATION_CLOSED_AT_SELECTION` | INFO | package | Memory was selected from a `CLOSED` conversation |

### 3. Internal invariant codes — raised by `validate_memory_package()`, never returned:

| Code | Trigger |
|---|---|
| `SELECTED_TURN_COUNT_MISMATCH` | `selected_turn_count` does not match the actual number of complete turns in `entries` |
| `WINDOW_RANGE_INCONSISTENT` | `window_start_turn_index > window_end_turn_index`, or window indexes do not match the actual entry range |
| `SERIALIZED_MEMORY_MISMATCH` | `serialized_memory` does not match a freshly re-serialized version of the selected `entries` |
| `CHARACTER_COUNT_MISMATCH` | `total_selected_characters` does not match `sum(len(e["content"]) for e in entries)` |
| `PACKAGE_ID_MISMATCH` | `conversation_memory_package_id` does not match a freshly recomputed hash of the selected content |
| `ENTRY_ORDER_VIOLATED` | Entries are not in strictly ascending `turn_index` order |

Any of these raises `ConversationMemoryInternalError` — the same fail-loud posture every prior
stage's own internal-invariant exceptions already establish.

## Public Function Contracts

- `start_conversation(config: ConversationConfig) -> ConversationState` — creates a new `ACTIVE`
  conversation with a stable `conversation_id` derived from `config.session_seed`. Validates `config`
  structurally; raises `ConversationMemoryInputError` on violation. Persists the new state via
  `ConversationStore.put()`. Returns the newly created state.

- `append_turn(conversation_id: str, turn: TurnInput) -> ConversationState` — appends one complete
  turn (user + assistant) to an existing `ACTIVE` conversation. Validates the turn structurally;
  validates lifecycle constraints (not closed). Assigns `turn_index` automatically. Persists the
  updated state via `ConversationStore.put()`. Returns the updated state.

- `select_memory(conversation_id: str, selection_config: SelectionConfig) -> ConversationMemoryPackage`
  — selects a bounded, ordered window of past turns from the conversation, serializes them, and
  returns a self-validated `ConversationMemoryPackage`. Does not modify the conversation state.
  Read-only.

- `get_conversation(conversation_id: str) -> ConversationState` — returns the full conversation state.
  Read-only. Raises `ConversationMemoryInputError("CONVERSATION_NOT_FOUND")` if the id does not exist.

- `close_conversation(conversation_id: str) -> ConversationState` — transitions a conversation to
  `CLOSED`. Permanent and irreversible. Idempotent on an already-closed conversation. Raises
  `ConversationMemoryInputError("CONVERSATION_NOT_FOUND")` if the id does not exist.

- `validate_conversation(conversation_state: ConversationState) -> None` — structural validation of a
  `ConversationState` object: entry ordering, turn_count consistency, status validity, turn_index
  contiguity. Raises `ConversationMemoryInternalError` on violation. Called internally before
  returning from `start_conversation()` and `append_turn()`.

- `validate_memory_package(package: ConversationMemoryPackage) -> None` — internal invariant self-check
  of an assembled `ConversationMemoryPackage`. Raises `ConversationMemoryInternalError` (one of the
  six named codes in Validation §3) on violation. Called internally before returning from
  `select_memory()`.

- `serialize_memory_window(entries: List[MemoryEntry]) -> str` — deterministic serialization of
  selected entries into the fixed text format, in ascending `turn_index` order (oldest first). Pure
  function of its argument. Used internally by `select_memory()` and by `validate_memory_package()`
  for re-serialization checks.

## Determinism

Stage 19 draws the same explicit line between deterministic and non-deterministic as Stages 13, 17,
and 18 — but for a simpler reason: all non-determinism is confined to wall-clock timestamps.

**Deterministic (guaranteed, byte-identical across runs, given identical input):**

- **Memory selection.** Given identical `(ConversationState, SelectionConfig)`, `select_memory()`
  always produces byte-identical `entries`, `serialized_memory`, `selected_turn_count`,
  `total_selected_characters`, `window_start_turn_index`, `window_end_turn_index`, `status`,
  `findings`, and `conversation_memory_package_id`.
- **Serialization.** `serialize_memory_window()` is a pure function; identical entries always produce
  byte-identical serialized output.
- **`conversation_memory_package_id`.** Deterministic content-hash of selected content; identical
  selections always produce identical ids.
- **`conversation_id`.** Deterministic hash of `session_seed`; stable for the conversation's lifetime.
- **Turn ordering.** `turn_index` assignment is deterministic and monotonic.
- **Validation outcomes.** Identical state always produces identical validation results.
- **No hidden state.** Stage 19 holds no module-level mutable state; all state is in
  `ConversationState` objects managed through the `ConversationStore`.
- **No randomness.** No `uuid4()`, no random selection — unlike Stage 18's own `request_id`, every
  identifier Stage 19 produces is a deterministic content-hash or monotonic counter.

**Explicitly NOT deterministic (wall-clock only, excluded from every determinism comparison):**

- `created_at` on `MemoryEntry` and `ConversationState`.
- `closed_at` on `ConversationState`.
- `selected_at` on `ConversationMemoryPackage`.

## Read-Only Guarantees

- Stage 19 never modifies `manifest.json`, any corpus artifact, any vector index, any embedding, any
  prompt template, any cache store, or any `APIResponse`.
- `select_memory()` never modifies the `ConversationState` it reads from.
- `get_conversation()` never modifies the `ConversationState` it returns.
- `MemoryEntry` objects are immutable once appended — Stage 19 never modifies an existing entry's
  content, speaker, provenance, or timestamp.
- Stage 19 never calls Stage 18's `handle_request()` or any stage below it.
- The only mutation Stage 19 performs is appending entries to `ConversationState.entries` via
  `append_turn()` (its own owned state), and updating `status`/`closed_at` via `close_conversation()`
  (its own owned state) — never any upstream artifact.

## Failure Handling

- **Nonexistent conversation** — `CONVERSATION_NOT_FOUND` raised immediately; no state is created
  or modified.
- **Closed conversation** — `CONVERSATION_CLOSED` raised on `append_turn()`; the conversation state
  is never modified.
- **Malformed turn content** — `TURN_CONTENT_MISSING_OR_INVALID` raised; no entry is appended.
- **Malformed provenance** — `TURN_PROVENANCE_MISSING` raised; no entry is appended.
- **Malformed selection config** — `SELECTION_CONFIG_MALFORMED` raised; no selection is performed.
- **Empty conversation selection** — not an error; returns a valid `ConversationMemoryPackage` with
  `serialized_memory = ""`, `entries = []`, `status = "WARNING"`, and `EMPTY_CONVERSATION` finding.
- **`ConversationStore` failure** (store.get() or store.put() raises unexpectedly) — propagated
  unchanged, wrapped in `ConversationMemoryInternalError` with the original exception, never
  silently swallowed. Same fail-loud posture as Stage 18's own `PipelineOrchestrationError`.
- **No retry logic.** Stage 19 performs no retries of any operation.
- **No timeout ownership.** Stage 19 owns no timeout logic of its own.

## Design Decisions

1. **No LLM-based summarization of conversation history.** Principle 5 states: "No fuzzy matching,
   no scoring/ranking judgment, no AI/LLM call anywhere in this pipeline." Summarizing older turns
   to fit more history into a prompt budget would require an LLM call, making conversation memory
   non-deterministic, non-reproducible, and potentially unfaithful to the original exchange. Stage
   19 uses only structural selection (recency + character budget) — simpler, fully deterministic,
   and auditable. If a future extension requires summarization, it would be a new stage or a
   revision of this one's frozen contract, never a silent addition.

2. **No semantic or embedding-based retrieval of relevant turns.** Selecting "the most relevant"
   past turns would require computing similarity between the current query and past turns — an
   embedding call or an LLM call, both forbidden by Principle 5. Recency-based windowing is the
   only selection strategy this stage implements, and it is fully deterministic. Semantic memory
   retrieval, if ever desired, is a future extension requiring its own design pass.

3. **Recency-first window selection, not earliest-first.** In typical multi-turn conversations, the
   most recent exchanges are most relevant to the current query — a widely-observed empirical
   pattern in conversational AI. Earliest-first selection would prioritize the opening turns, which
   are less likely to be directly relevant. This is a fixed, structural heuristic (a selection
   *rule*, not a *ranking judgment*), consistent with Principle 5.

4. **Complete turns only — no partial-turn inclusion.** Including a user message without its
   assistant response (or vice versa) would produce incoherent, misleading context. The turn is the
   atomic unit of conversation, and the atomic unit of memory selection. A half-turn is never more
   useful than no turn at all.

5. **Character budget, not token budget.** Token counting is model-specific — it requires knowing
   which tokenizer the downstream LLM will use, information Stage 19 does not have (model selection
   happens at Stage 18's own `resolve_execution_config_for_api()` or deployment-level
   `default_model_name`). Character counting is model-independent, deterministic, and
   approximation-free. A downstream consumer that needs a token estimate can apply the same fixed
   `chars_per_token_estimate` ratio Stage 11 already uses, converting Stage 19's
   `total_selected_characters` — but that conversion is their responsibility, not Stage 19's.

6. **Unbounded history, windowed selection.** Conversation history grows without bound — Stage 19
   imposes no hard ceiling on the number of turns or total characters stored. This separates two
   concerns that the original "hard rejection" design conflated:
   - **Storage** (how much history is *preserved*) — unbounded, limited only by the
     `ConversationStore` backend's own capacity, never by Stage 19's in-memory logic.
   - **Selection** (how much history is *presented downstream*) — bounded by `select_memory()`'s
     own `max_turns` and `max_characters` configuration, applied deterministically at selection time.

   A conversation with 500 turns stores all 500 turns. A `select_memory()` call with
   `max_turns=10` returns the most recent 10 that fit within the character budget. The remaining
   490 turns are preserved for audit/debugging, but never sent downstream. This design eliminates
   the artificial failure mode of rejecting legitimate new turns solely because the total
   conversation exceeds a serving budget — a distinction between "how much to store" and "how much
   to serve" that the selection mechanism already provides.

7. **Stage 19 sits above Stage 18, never inside it.** Stage 18's `handle_request()` is fully
   stateless and per-call — it has no knowledge of prior turns. Making it conversation-aware would
   violate its own frozen contract and single responsibility. Instead, Stage 19 prepares
   conversation context separately, and a future orchestration layer (or an existing external caller)
   coordinates the two — passing Stage 19's `serialized_memory` alongside the current query into
   Stage 18's own unmodified `APIRequest`. This preserves Stage 18's frozen contract completely.

8. **Immutable entries, not editable messages.** Once a `MemoryEntry` is appended, it is never
   modified. This guarantees that `conversation_memory_package_id` is truly content-addressable
   (the same selected window always produces the same id), simplifies concurrency (no read-modify-
   write races on individual entries), and provides a faithful audit trail. If a deployment needs
   to "edit" a message, it should close the current conversation and start a new one with corrected
   content — never mutate history in place.

9. **No system messages in conversation history.** System prompts are Stage 12's concern (loaded
   from versioned templates, static, and context-free). Storing them in conversation history would
   duplicate content already managed by Stage 12, and mixing system instructions with user/assistant
   exchanges would blur the ownership boundary between Stage 12 (prompt construction) and Stage 19
   (conversation memory). See System Messages — Excluded by Design for the full rationale.

10. **Stable conversation identity, evolving state version.** `conversation_id` is permanent and
    never changes — it is an external reference used for correlation across systems. `turn_count`
    serves as a monotonic state version — it changes on every `append_turn()` and allows staleness
    detection. `conversation_memory_package_id` is content-derived — it changes when the selected
    window's content changes, providing deterministic, content-addressable identification for each
    distinct memory selection. See Conversation Identity Model for the full rationale.

## Constants

```python
CONVERSATION_MEMORY_VERSION = "1.0.0"

# Selection defaults (for SelectionConfig)
DEFAULT_SELECTION_MAX_TURNS = 10                # default window size
DEFAULT_SELECTION_MAX_CHARACTERS = 50_000       # default character budget for selected memory
MAX_SELECTION_TURNS_CEILING = 50                # selection can never exceed this, even if asked
MAX_SELECTION_CHARACTERS_CEILING = 200_000      # selection character budget ceiling

# Serialization
TURN_SEPARATOR = "\n"                           # separator between turns in serialized_memory
USER_PREFIX = "User: "                          # prefix for user messages in serialization
ASSISTANT_PREFIX = "Assistant: "                # prefix for assistant messages in serialization
```

No numeric threshold, ceiling, or default from any prior stage is duplicated here — every one Stage
19 defines is its own, governing conversation memory only.

Note: the constants `MAX_TURNS_CEILING`, `MAX_TOTAL_CHARACTERS_CEILING`, `DEFAULT_MAX_TURNS`, and
`DEFAULT_MAX_TOTAL_CHARACTERS` (which governed hard ceilings on conversation storage size) have been
removed. Conversation history is now unbounded; only the *selection* window has configurable limits,
governed by `DEFAULT_SELECTION_MAX_TURNS`, `DEFAULT_SELECTION_MAX_CHARACTERS`,
`MAX_SELECTION_TURNS_CEILING`, and `MAX_SELECTION_CHARACTERS_CEILING`.

## Complexity

- `start_conversation()` — O(1): hash computation, store put.
- `append_turn()` — O(1): validation, append two entries, increment count, store put.
- `get_conversation()` — O(1): store get.
- `close_conversation()` — O(1): state update, store put.
- `select_memory()` — O(T) where T is `selected_turn_count`: iterate over the selected window,
  serialize, hash. Never O(N) in total conversation length for the serialization step — only the
  window is serialized, not the full history.
- `validate_memory_package()` — O(T): re-serialization and re-hashing of the selected window.

## Logging

Per the shared Logging Specification (`stage: "stage19_conversation_memory"`, `doc_id: null` always —
entries are conversation-scoped, not document-scoped). New codes this stage adds:

- `INFO_CONVERSATION_CREATED` — a new conversation was created.
- `INFO_TURN_APPENDED` — a new turn was appended.
- `INFO_CONVERSATION_CLOSED` — a conversation was closed.
- `INFO_MEMORY_SELECTED` — a memory window was selected.
- `WARNING_WINDOW_TRUNCATED` — the selected window was truncated by budget or turn limit.

No new `FATAL_*` code — Stage 19 never sets a manifest `error_code`, since it never touches the
manifest at all.

## Concurrency

### Ownership

Concurrency coordination is **owned entirely by the `ConversationStore` implementation**, not by
Stage 19's own in-memory logic. Stage 19 itself is single-threaded and deterministic — it makes no
concurrency guarantees of its own, performs no locking, and holds no mutex or semaphore.

### Read operations

`select_memory()` and `get_conversation()` are read-only and safe under concurrent execution. They
never modify the `ConversationState` they read from, and they hold no locks.

### Write operations

`append_turn()` and `close_conversation()` mutate `ConversationState` — performing a read-modify-write
cycle (`store.get()` → modify in memory → `store.put()`). Concurrent writes to the same conversation
require the `ConversationStore` implementation to provide its own serialization guarantees. Examples of
valid strategies a `ConversationStore` might employ (none chosen or recommended by this design):

- Optimistic locking (compare-and-swap on `turn_count`)
- Pessimistic locking (mutex per `conversation_id`)
- Serialized write queues
- Database-level transactions

### Conflict resolution

If two concurrent `append_turn()` calls race on the same conversation, the `ConversationStore` is
responsible for ensuring that exactly one succeeds and the other either retries or fails. Stage 19
does not define a conflict resolution policy — it delegates that entirely to the storage adapter.
This is the same posture Stage 17 already established for its own `CacheAdapter` (where two concurrent
misses may both write, accepted as a documented limitation).

### Guarantee summary

| Operation | Reads state? | Mutates state? | Concurrency-safe without store coordination? |
|---|---|---|---|
| `get_conversation` | Yes | No | Yes |
| `select_memory` | Yes | No | Yes |
| `append_turn` | Yes | Yes | No — requires `ConversationStore` coordination |
| `close_conversation` | Yes | Yes | No — requires `ConversationStore` coordination |
| `start_conversation` | No | Yes (put) | Yes — no read-modify-write; put of a new key |

## Security Considerations

- **Untrusted user message content.** `turn.user_content` originates from an external caller and may
  contain adversarial input. Stage 19 stores it verbatim and serializes it verbatim into
  `serialized_memory`. Any defense against prompt injection via conversation history (output
  encoding, content-security policies, injection detection) is the responsibility of whoever
  consumes `serialized_memory` downstream — not Stage 19's concern. This mirrors Stage 10's own
  posture toward query text and Stage 13's own posture toward model output.
- **Model output in assistant messages.** `turn.assistant_content` contains LLM-generated text (from
  `APIResponse.answer.response_text`), which is itself potentially adversarial. Stage 19 applies no
  sanitization — the same posture Stage 18 already established for surfacing model output to
  external callers.
- **No credential handling.** `ConversationStore` (and whatever storage backend it wraps) is a
  deployment-level dependency; credentials are never exposed in `ConversationState`, `MemoryEntry`,
  or `ConversationMemoryPackage`.
- **Conversation isolation.** Every operation requires an explicit `conversation_id`. Stage 19
  provides no mechanism to list all conversations or iterate across conversations — those are
  administrative operations outside this design's scope. A caller can only access a conversation
  they already know the id of.

## Known Limitations

- **No summarization, compression, or abstractive memory.** Stage 19 can only select a contiguous
  recency-based window of verbatim past turns. It cannot condense a 50-turn conversation into a
  shorter representation. This is an explicit, deliberate limitation of Principle 5's "no LLM call"
  constraint.
- **No semantic retrieval of relevant turns.** A user asking about a topic discussed 30 turns ago
  will not have that turn included in the selected window unless the window is large enough to
  reach it by recency alone. Semantic memory retrieval would require embeddings or an LLM call,
  both forbidden.
- **No cross-conversation memory.** Stage 19 manages conversations independently. A user's history
  from one conversation is never accessible from another. Cross-conversation memory would require
  a user-identity concept and a global memory store, both outside this design's scope.
- **Unbounded storage growth.** Conversation history grows without bound; Stage 19 imposes no
  ceiling on the number of turns or total characters stored. Storage capacity management (eviction,
  archival, compaction) is the `ConversationStore` implementation's concern.
- **No edit, delete, or undo for individual turns.** Entries are immutable once appended. A
  deployment needing to correct a past entry must close the conversation and start a new one.
- **`serialized_memory` format is fixed and simple.** The `"User: ...\nAssistant: ...\n"` format
  is not configurable. A downstream consumer needing a different format must perform its own
  transformation.
- **No integration with Stage 12's prompt templates.** How `serialized_memory` is injected into a
  prompt is an integration concern outside both Stage 12 and Stage 19's scope. A future integration
  layer or a new prompt template version would need to define a `{{conversation_history}}`
  placeholder — but neither stage owns that integration.
- **Closed conversations cannot be reopened.** This is permanent and by design — see Conversation
  Lifecycle.

## Future Stage Boundaries

Stage 20+ (not designed here) owns everything Stage 19 deliberately excludes:

- **Stage 20 — Tool / Function Calling** owns extending the LLM invocation model to call external
  tools — entirely orthogonal to conversation memory. Stage 19 stores tool-call results only if
  they appear as part of `APIResponse.answer.response_text` (already captured as the assistant
  message); it has no knowledge of tool calls as a distinct concept.
- **Stage 21 — Agent Planning** owns multi-step autonomous reasoning. An agent planner might consume
  `ConversationMemoryPackage` as input to its planning logic, but Stage 19 performs no planning
  itself.
- **Prompt template integration** — defining how `serialized_memory` is injected into Stage 12's
  prompt templates is an integration concern, potentially handled by a new prompt template version
  or a thin integration layer between Stage 19 and Stage 18. This integration layer is not designed
  here.
- **Semantic memory retrieval** — selecting turns by semantic relevance rather than recency would
  require embedding-based retrieval, a new design pass, and potentially a new stage.
- **Conversation summarization** — compressing history via LLM calls would require reopening
  Principle 5's constraint, a new design pass, and potentially a new stage.

Stage 19 prepares conversation context and makes it available; how that context reaches the LLM (via
Stage 12's prompt templates, via Stage 18's pipeline options, or via a new integration mechanism) is
a separate concern this design deliberately leaves open.
