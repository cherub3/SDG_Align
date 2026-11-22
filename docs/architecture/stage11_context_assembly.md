# Stage 11 — Context Assembly

Stages 0–10 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 11 turns Stage 10's `RetrievalResult` into a `ContextPackage`: a deterministic, budget-aware
assembly of ranked chunks ready to hand to a future prompt-construction stage. It performs no
retrieval, no ranking, no generation — it is a pure, in-memory transformation of already-final
retrieval output into a bounded, well-provenanced package. `assemble_context(retrieval_result,
context_budget_tokens)` is the sole public entrypoint.

## Scope

Stage 11 answers exactly one question — given a `RetrievalResult`, what ordered, budget-bounded set
of context blocks should a caller build a prompt from — and stops there. It never generates an
answer, never constructs a prompt or system message, never invokes an LLM, never reranks or
re-scores, never summarizes or modifies a chunk's own text, never evaluates retrieval quality. Those
boundaries are restated in Future Stage Boundaries.

## Responsibilities

Stage 11 shall: receive a `RetrievalResult`; structurally validate it before use; preserve Stage 10's
own retrieval ordering exactly (never re-rank, never re-score); preserve chunk boundaries (never
split, merge, or partially include a chunk's text); preserve document, section, and page provenance
on every block, verbatim; enforce a configurable token budget; estimate token usage via a fixed,
deterministic transform; and assemble a `ContextPackage` whose own internal invariants are
self-checked before it is ever returned.

## Inputs

Exactly one required input, entirely in-memory:

- `RetrievalResult` (Stage 10's own output schema, unchanged) — the sole source of every chunk, its
  text, its score, and its full provenance.

No other input is read. Although `manifest.json`, `chunks.json`, and `metadata.json` are in
principle available read-only, Stage 11 does not open any of them in its ordinary path — every field
a `ContextBlock` needs (`text`, `heading_path`, `section_ids`, page range, `category`/`doc_type`/
`title`) already exists on each `RetrievedChunk`, verbatim (see Design Decisions #1). No PDF is ever
reopened; no chunk is ever regenerated; no embedding or vector search is ever performed here.

## Outputs

None persisted. Stage 11 produces zero artifacts and writes to no file — the second fully read-only
stage in this pipeline, and the first that performs zero disk reads of its own at all (Stage 10 still
reads `manifest.json` and each contributing `chunks.json`; Stage 11 reads nothing from disk — its
only input is already an in-memory Python object). Its sole output is an in-memory `ContextPackage`
(see Schema) returned directly to the caller.

## Pipeline

```
RetrievalResult { status, results[], findings[], ... }
      │
      ▼
[1] validate_retrieval_result(retrieval_result)   — Stage 11's own structural input check: required
      keys present, correctly typed. Malformed input raises ContextAssemblyInputError immediately —
      this should never happen under correct operation, since Stage 10 already self-validates its own
      output before returning it (see Validation). Distinct from, and never calling, Stage 10's own
      identically-named internal function.
      │
      ▼
[2] retrieval_result["status"] == "FAIL"?
      ├─yes──▶ ContextPackage{status="FAIL", context_blocks=[], ...}, done, nothing else runs
      │no
      ▼
[3] build_context_blocks(retrieval_result["results"])   — one ContextBlock per RetrievedChunk, in
      the exact rank order Stage 10 already computed; pure field copy-through (Provenance
      Guarantees); never splits, merges, reorders, or drops a chunk here
      │
      ▼
[4] estimate_tokens(block.text) per block   — fixed character-ratio estimate (Token Estimation
      Strategy); computed once, stored on the block, never recomputed
      │
      ▼
[5] enforce_budget(blocks, context_budget_tokens)   — prefix truncation in rank order (Context
      Budget Policy): the first block that would exceed the budget, and every block after it in rank
      order, are excluded; included blocks are always a contiguous prefix of the ranked list
      │
      ▼
[6] assemble_context_package(retrieval_result, included_blocks, excluded_blocks,
      context_budget_tokens)   — wraps included blocks + token stats + inherited status/findings into
      the final ContextPackage
      │
      ▼
[7] validate_context_package(package)   — internal invariant self-check on the assembled output;
      raises ContextAssemblyInternalError on violation
      │
      ▼
ContextPackage { status, context_blocks[], findings[], token stats, ... }
```

## Context Assembly Pipeline Diagram

```
                    ┌──────────────────────┐
                    │   RetrievalResult     │
                    └──────────┬────────────┘
                               │
                    validate_retrieval_result()
                               │
                     status == "FAIL"? ──yes──▶ ContextPackage(FAIL, [])
                               │ no
                     build_context_blocks()
                               │
                    ┌──────────▼────────────┐
                    │  ContextBlock[] (all)  │
                    └──────────┬────────────┘
                               │
                    estimate_tokens() per block
                               │
                      enforce_budget(budget_tokens)
                               │
                 ┌─────────────┴─────────────┐
                 ▼                            ▼
        included_blocks[]            excluded_blocks[]
      (contiguous rank prefix)      (budget-truncated tail)
                 │
        assemble_context_package()
                 │
        validate_context_package()
                 │
                 ▼
          ContextPackage
```

## Context Block Schema

`ContextBlock` — one per surviving `RetrievedChunk`, an in-memory structure, no file format:

```jsonc
{
  "context_block_id": "pkg_...__doc_..._2.1.1_0",  // deterministic: {context_package_id}_{chunk_id}
  "rank": 0,                                 // copied verbatim from RetrievedChunk.rank — this
                                              // package's one frozen positional index (0-indexed,
                                              // contiguous); see Ordering Guarantees
  "score": 0.8421,                           // copied verbatim, never recomputed
  "index_fingerprint": "a3f9...",
  "embedding_id": "doc_..._2.1.1_0__prov__mod__v1",
  "chunk_id": "doc_..._2.1.1_0",
  "doc_id": "doc_9f3a2b1c8e4d",
  "text": "...",                             // verbatim, byte-for-byte, never truncated/modified
  "heading_path": ["2. Project Background", "2.1 Climate Rationale"],
  "section_ids": ["2.1.1"],
  "page_start": 34, "page_end": 35,
  "category": "climate", "doc_type": "RRP", "title": "Climate Resilience...",
  "estimated_tokens": 355                    // the one content field this stage computes and adds
}
```

Every field except `context_block_id` and `estimated_tokens` is a direct, unmodified copy of the
matching field on the source `RetrievedChunk` — Stage 11 never re-derives `score`, `rank`, or any
provenance field from anything other than Stage 10's own already-final record. `context_block_id`
and `rank` are this stage's only two block-identity fields, and both are frozen by this contract: no
separate `block_index` concept is introduced, since `rank` already is the block's 0-indexed,
contiguous positional index within the package (Ordering Guarantees) — a second, near-duplicate id
field would only invite drift between the two. A future stage must reference a specific block by
`context_block_id` (globally unique, package-scoped) or by `rank` (positional within one package),
never by inventing a third scheme of its own.

## ContextPackage Schema

```jsonc
{
  "context_package_id": "...",               // deterministic identity, see Determinism Guarantees
  "context_pipeline_version": "1.0.0",       // this stage's own independent version constant,
                                              // matching Stage 10's retrieval_pipeline_version and
                                              // Stage 9's index_pipeline_version convention exactly
  "assembled_at": "2026-07-20T12:00:00Z",    // timestamp, excluded from every determinism comparison
  "query": "climate adaptation financing mechanisms",   // copied verbatim from RetrievalResult.query
  "status": "PASS",                          // PASS | PARTIAL | FAIL — inherited from RetrievalResult
  "is_empty": false,                         // true iff context_blocks == []
  "context_budget_tokens": 4000,             // the budget this package was assembled against
  "total_estimated_tokens": 3820,            // sum of estimated_tokens across INCLUDED blocks only
  "included_block_count": 9,
  "excluded_block_count": 1,                 // excluded by budget truncation only — never any other filter
  "excluded_estimated_tokens": 410,          // sum of estimated_tokens across EXCLUDED blocks only —
                                              // together with total_estimated_tokens, accounts for
                                              // every token estimate computed in Pipeline [4]
  "budget_utilization": 0.955,               // total_estimated_tokens / context_budget_tokens;
                                              // always in [0.0, 1.0] — see Context Budget Policy
  "context_blocks": [ /* ContextBlock, ..., len == included_block_count */ ],
  "excluded_context_blocks": [ /* ContextBlock, ..., len == excluded_block_count — the exact
                                   budget-truncated tail, kept (not discarded) for debugging
                                   visibility into what was cut and why */ ],
  "retrieval_findings": [ /* RetrievalResult.findings[], copied verbatim — full upstream provenance */ ],
  "findings": [ /* this stage's own new findings: {severity, code, message} */ ],
  "requested_index_fingerprints": [ /* copied verbatim from RetrievalResult */ ],
  "searched_index_fingerprints": [ /* copied verbatim from RetrievalResult */ ]
}
```

## Token Estimation Strategy

A fixed, named, deterministic character-ratio transform — never a real tokenizer call, since no
tokenizer or model is named anywhere in this project (the same honest gap Stage 7 Decision 7 already
accepted for its own character-based chunk-size thresholds, now inherited one stage further
downstream):

```python
estimate_tokens(text) = ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)
```

Only a block's own `text` field is counted — `heading_path`, `title`, and other metadata fields a
future prompt template might also inject are deliberately excluded from the estimate (Known
Limitations): Stage 11 has no visibility into any such template, so it honestly estimates only what
it itself controls. `estimate_tokens` is a pure function of its `text` argument alone — no state, no
caller context, no randomness.

## Context Budget Policy

`context_budget_tokens` is per-request configuration (mirrors Stage 10's own `top_k` convention):
supplied by the caller, clamped to `[1, MAX_CONTEXT_BUDGET_TOKENS]`, defaulting to
`DEFAULT_CONTEXT_BUDGET_TOKENS` when omitted — never read from any global or environment state.

Enforcement is **prefix truncation in rank order, never bin-packing**: iterate `context_blocks` in
their existing rank order, accumulating `estimated_tokens`; the first block whose inclusion would
push the running total over `context_budget_tokens`, and every block after it, are excluded. Included
blocks are therefore always a contiguous prefix of the ranked list — never a block "skipped over" in
favor of a smaller one further down the ranking. A chunk is never split to partially fit a budget,
under any circumstance — a chunk is the smallest unit this entire pipeline ever assembles, moves, or
truncates (the same atomicity guarantee Stage 7 established for chunk identity, preserved unbroken
through Stage 11). If even the highest-ranked block's own `estimated_tokens` exceeds
`context_budget_tokens`, zero blocks are included.

Truncation is never silent: `enforce_budget`'s excluded tail is never discarded, only separated. It
is carried into the final package as `excluded_context_blocks` (the exact excluded `ContextBlock`
records, in their original rank order), `excluded_estimated_tokens` (the sum of their
`estimated_tokens`), and `budget_utilization` (`total_estimated_tokens / context_budget_tokens`,
always in `[0.0, 1.0]`) — alongside the `CONTEXT_BUDGET_EXCEEDED` finding (Validation), giving a
caller or debugger full visibility into exactly what was cut, how much token budget it would have
cost, and how tightly the included set fills the budget it was given.

## Ordering Guarantees

`context_blocks` strictly preserves `RetrievalResult.results`'s own rank order — Stage 11 never
independently sorts, re-scores, or re-ranks anything. Budget enforcement only ever removes a
contiguous trailing suffix of the ranked list; it never reorders and never removes from the middle.
A direct consequence: because Stage 10 already assigns contiguous 0-indexed `rank` values and Stage
11 only ever truncates a trailing suffix, the surviving blocks' `rank` values are automatically
already contiguous `0..included_block_count-1` — Stage 11 never re-assigns `rank`.

## Provenance Guarantees

Every `ContextBlock` carries its own `doc_id`, `chunk_id`, `index_fingerprint`, page range, and full
section hierarchy, copied verbatim from its source `RetrievedChunk` — nothing recomputed, nothing
inferred, nothing re-read from any artifact. No two chunks are ever merged into one block, even when
adjacent in rank order and from the same document — chunk atomicity is preserved unbroken. Document
boundaries are therefore preserved implicitly: because each block is tagged with its own `doc_id` and
never combined with another block's text, a downstream consumer can always tell, block by block,
exactly which document and location any piece of context text came from.

## Metadata Preservation

`category`, `doc_type`, `title`, `heading_path`, `section_ids`, `page_start`, `page_end` are copied
verbatim from each `RetrievedChunk` in their original order and form — never re-sorted, never
re-derived, never re-read from `chunks.json` or `metadata.json` directly (see Design Decisions #1).
Stage 11 trusts Stage 10's own already-assembled record completely, avoiding a redundant re-join —
the same avoid-redundant-read principle Stage 10's own Design Decision 6 already established one
level upstream.

## Design Decisions

1. **`RetrievalResult` alone is sufficient input; `manifest.json`/`chunks.json`/`metadata.json` are
   never actually opened.** Every field a `ContextBlock` needs already exists, verbatim, on each
   `RetrievedChunk` — re-reading any upstream artifact would only duplicate a join Stage 10 already
   performed, for no gain (Stage 10 Design Decision 6 made the identical call one stage upstream).
2. **Chunks are never split, ever.** A chunk is this pipeline's smallest addressable unit, fixed at
   Stage 7 and never revisited since — budget enforcement operates only at whole-block granularity.
3. **Budget enforcement is prefix truncation, not bin-packing.** A block that doesn't fit, and every
   lower-ranked block after it, are excluded together — never skipped individually in search of a
   smaller later block that might fit. Simpler, fully predictable, and keeps "what got included" a
   pure function of "how far down the ranked list the budget reached" — no gaps in the included set.
4. **Token estimation is a fixed character-ratio heuristic, never a real tokenizer.** Consistent with
   Principle 5 (deterministic before probabilistic) and Stage 7's own precedent: no tokenizer or
   model is named anywhere in this project, so introducing one here would be premature coupling.
5. **`status` is a pure passthrough of `RetrievalResult.status`.** Stage 11 introduces no new FAIL or
   PARTIAL condition of its own beyond relaying what Stage 10 already determined — its own local
   findings (`CONTEXT_BUDGET_EXCEEDED`, `CONTEXT_EMPTY`) are always WARNING-severity and never alter
   `status`, mirroring Stage 10's own "WARNING never downgrades status" rule exactly.
6. **Stage 11 defines its own `validate_retrieval_result()`, deliberately reusing Stage 10's function
   name.** Different module, different responsibility: this one structurally validates a *received*
   `RetrievalResult` as Stage 11's own input gate, never Stage 10's own internal pre-return
   self-check. The name is intentionally symmetric with Stage 10's contract, not accidental — Stage
   11 never imports or calls Stage 10's version.
7. **A malformed `RetrievalResult` raises, rather than returning a degraded `ContextPackage`.** Since
   Stage 10 already self-validates its own output via its own `validate_retrieval_result()` before
   ever returning it, a malformed `RetrievalResult` reaching Stage 11 indicates a caller error or a
   genuine upstream bug, not a normal degraded-but-expected outcome — the same fail-loud posture
   Stage 10 reserves for its own internal invariant violations, applied here at the input boundary
   instead of the output boundary.
8. **`context_package_id` is a deterministic hash, never a UUID or timestamp.** Computed from exactly
   `query`, `requested_index_fingerprints`, `searched_index_fingerprints`, the ordered list of
   surviving `chunk_id`s, and `context_budget_tokens` — the same sha256-over-canonical-json pattern
   Stage 9's `index_fingerprint` already established.
9. **Block identity is exactly two frozen fields, never three.** `context_block_id` (globally
   unique, deterministic, package-scoped) and `rank` (positionally frozen, 0-indexed, contiguous
   within one package) are the only sanctioned ways to reference a specific `ContextBlock`. No
   separate `block_index` field is introduced alongside `rank` — they would mean the same thing,
   and a future stage picking one over the other inconsistently is exactly the drift this decision
   forecloses by only ever defining one.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md`
§4's Critical/Recoverable document-quarantine model, since Stage 11 has no document to quarantine and
no persisted artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10 already
gave for its own Validation section). Every code below is closed-vocabulary and named, matching the
table-of-codes style Stage 9 and Stage 10 both use, split by what actually happens when it fires:

**1. Input validation codes** — raised, never returned as part of any `ContextPackage`:

| Code | Raised as | Trigger |
|---|---|---|
| `RETRIEVAL_RESULT_MALFORMED` | `ContextAssemblyInputError` | the received `RetrievalResult` is missing a required key or has a wrong-typed value (Pipeline [1]); no `ContextPackage` is produced at all |

A `RetrievedChunk.text` that isn't a string is caught here too, at input validation, before
`estimate_tokens` is ever called on it — `estimate_tokens` itself has no distinct "failed" state,
since by the time it runs its input type is already guaranteed correct (see Public Function
Contracts).

**2. Package-level findings** — recorded in `ContextPackage.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `RETRIEVAL_STATUS_FAIL` | FAIL | package | passthrough of `RetrievalResult.status == "FAIL"`; `context_blocks=[]`, no budget enforcement attempted |
| `CONTEXT_BUDGET_EXCEEDED` | WARNING | package | at least one available block was excluded by budget truncation; never downgrades `status`; always paired with populated `excluded_context_blocks`/`excluded_estimated_tokens` |
| `CONTEXT_EMPTY` | WARNING | package | `context_blocks == []` after assembly, for any reason; never downgrades `status` |

`status` truth table (pure passthrough, no additional Stage 11 condition):

| Condition | `status` |
|---|---|
| `RetrievalResult.status == "FAIL"` | `FAIL` |
| `RetrievalResult.status == "PARTIAL"` | `PARTIAL` |
| `RetrievalResult.status == "PASS"` | `PASS` |

**3. Internal invariant codes** — raised by `validate_context_package()`, run unconditionally on the
assembled package before it is ever returned; never returned as part of any `ContextPackage`:

| Code | Trigger |
|---|---|
| `DUPLICATE_CONTEXT_BLOCK` | the same `chunk_id` appears more than once in `context_blocks` |
| `RANK_NOT_CONTIGUOUS` | `rank` values on `context_blocks` are not exactly `0..included_block_count-1` |
| `TOKEN_ESTIMATE_SUM_MISMATCH` | `sum(block.estimated_tokens for block in context_blocks) != total_estimated_tokens` |
| `BUDGET_INVARIANT_VIOLATED` | `total_estimated_tokens > context_budget_tokens` |
| `EXCLUDED_COUNT_MISMATCH` | `included_block_count + excluded_block_count != len(retrieval_result["results"])` |

Any of these five raises `ContextAssemblyInternalError` rather than being returned as a malformed
`ContextPackage` — the same fail-loud posture as Stage 10's own `RetrievalInternalError`, and never
expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage11_context_assembly"`, `doc_id: null` always —
entries are package-scoped, not document-scoped). New codes this stage adds:
`WARNING_CONTEXT_BUDGET_EXCEEDED`, `WARNING_CONTEXT_EMPTY`. No new `FATAL_*` code — Stage 11 never
sets a manifest `error_code`, since it never touches the manifest at all (see Manifest Interaction).

## Manifest Interaction

None. Stage 11 never opens, reads, or writes `manifest.json` — the first stage in this pipeline with
zero manifest interaction of any kind (Stage 10 at least reads it twice per query; Stage 11 needs it
for nothing, since every field it needs already arrived on `RetrievalResult`).

## Artifact Interaction

None. Stage 11 performs zero file reads and zero file writes. Its only input is an in-memory
`RetrievalResult`; its only output is an in-memory `ContextPackage`. No atomicity concern exists
because there is nothing to persist and nothing to read from disk at all.

## Directory Structure

None added. Stage 11 introduces no new artifact directory — there is no artifact.

## Determinism Guarantees

- **Stable ordering.** `context_blocks` order is entirely inherited from `RetrievalResult.results`;
  never independently sorted.
- **Stable `context_block_id`.** Deterministic function of `context_package_id` + `chunk_id`; no
  timestamp/UUID/random input.
- **Stable overflow metadata.** `excluded_context_blocks`, `excluded_estimated_tokens`, and
  `budget_utilization` are all pure functions of the same deterministic `(RetrievalResult,
  context_budget_tokens)` input as everything else — identical input always yields identical values.
- **Stable `context_package_id`.** Deterministic sha256 over exactly `query`,
  `requested_index_fingerprints`, `searched_index_fingerprints`, ordered surviving `chunk_id`s, and
  `context_budget_tokens`.
- **Stable token estimation.** `estimate_tokens` is a pure function of `text` alone, using a fixed
  constant ratio — identical text always yields an identical estimate.
- **Stable metadata ordering.** `heading_path`/`section_ids` arrays are copied in their original
  order, never re-sorted.
- **Stable output.** Identical `(RetrievalResult, context_budget_tokens)` produces a byte-identical
  `ContextPackage` (`assembled_at` excluded), across repeated calls and process restarts.

## Failure Handling

- **A malformed `RetrievalResult`** (missing/wrong-typed required key) — `ContextAssemblyInputError`
  (`RETRIEVAL_RESULT_MALFORMED`) raised immediately; no `ContextPackage` returned.
- **`RetrievalResult.status == "FAIL"`** — graceful, well-formed `ContextPackage{status="FAIL",
  context_blocks=[]}`; no budget enforcement attempted; `RETRIEVAL_STATUS_FAIL` finding recorded.
- **`RetrievalResult.status == "PARTIAL"`** — context assembled normally from whatever `results`
  Stage 10 provided; `ContextPackage.status` stays `PARTIAL`; Stage 10's own `findings[]` carried
  forward verbatim into `retrieval_findings`.
- **`RetrievalResult.results == []`** (Stage 10's own `zero_results`) — `build_context_blocks`
  naturally produces zero blocks; `CONTEXT_EMPTY` WARNING; `status` stays whatever
  `RetrievalResult.status` already was.
- **The highest-ranked block's own `estimated_tokens` alone exceeds `context_budget_tokens`** — zero
  blocks included; `excluded_context_blocks` holds every available block, `budget_utilization ==
  0.0`; both `CONTEXT_BUDGET_EXCEEDED` and `CONTEXT_EMPTY` fire; `status` unaffected.
- **`context_budget_tokens` omitted, zero, or negative** — clamped to
  `[1, MAX_CONTEXT_BUDGET_TOKENS]`, defaulting to `DEFAULT_CONTEXT_BUDGET_TOKENS` when omitted
  (mirrors Stage 10's own `top_k` clamping).
- **A genuine Stage 11 bug** (one of the five named internal invariant codes in Validation §3) —
  `ContextAssemblyInternalError` raised, not returned as a malformed `ContextPackage`.

## Configuration

`context_budget_tokens` is per-request configuration, never defaulted from any global or environment
state except via the named `DEFAULT_CONTEXT_BUDGET_TOKENS` constant when the caller omits it
entirely — the same per-request convention Stage 10 already established for `top_k`. Stage 11
consumes no adapter factories of any kind; it never touches `ProviderAdapter` or `IndexAdapter`.

## Concurrency

Fully safe under concurrent calls. Stage 11 performs zero writes and holds no shared mutable state —
`assemble_context()` is a pure function of its own arguments; any number of calls, including against
identical input, may run simultaneously with no locking and no race condition.

## Security Considerations

- Chunk `text` is opaque data — never interpolated into a file path, shell command, or `eval`.
- No artifact path is ever constructed from any field of `RetrievalResult` — Stage 11 opens no files
  at all.
- No write capability anywhere in this design — eliminates an entire class of injection/corruption
  risk by construction, not by runtime validation.

## Public Function Contracts

- `validate_retrieval_result(result: RetrievalResult) -> None` — Stage 11's own structural input
  check; raises `ContextAssemblyInputError` (code `RETRIEVAL_RESULT_MALFORMED`) on a missing/
  wrong-typed required key, including a non-string `text` field on any `RetrievedChunk`. Distinct
  from, and never calling, Stage 10's own function of the same name (Design Decision 6).
- `estimate_tokens(text: str) -> int` — fixed character-ratio transform (Token Estimation Strategy);
  pure function of `text` alone; total (always succeeds once its input type is already guaranteed by
  `validate_retrieval_result`).
- `build_context_blocks(results: List[RetrievedChunk]) -> List[ContextBlock]` — one block per
  `RetrievedChunk`, in the same order, pure field copy-through plus `estimated_tokens`; never splits,
  merges, or reorders.
- `enforce_budget(blocks: List[ContextBlock], context_budget_tokens: int) -> Tuple[List[ContextBlock],
  List[ContextBlock]]` — returns `(included, excluded)`; prefix truncation in rank order (Context
  Budget Policy); the `excluded` list is never discarded by the caller — it flows directly into
  `ContextPackage.excluded_context_blocks`.
- `assemble_context_package(retrieval_result: RetrievalResult, included: List[ContextBlock], excluded:
  List[ContextBlock], context_budget_tokens: int) -> ContextPackage` — wraps included blocks +
  excluded blocks + token/budget stats (`total_estimated_tokens`, `excluded_estimated_tokens`,
  `budget_utilization`) + inherited `status`/`findings` into the final package.
- `validate_context_package(package: ContextPackage) -> None` — internal invariant self-check; raises
  `ContextAssemblyInternalError` (one of the five named codes in Validation §3) on violation.
- `assemble_context(retrieval_result: RetrievalResult, context_budget_tokens: Optional[int] = None) ->
  ContextPackage` — the sole public entrypoint; orchestrates Pipeline [1]–[7]; never reads or writes
  any artifact or the manifest.

## Constants

```python
CONTEXT_PIPELINE_VERSION = "1.0.0"
DEFAULT_CONTEXT_BUDGET_TOKENS = 4000
MAX_CONTEXT_BUDGET_TOKENS = 50000    # hard ceiling — guards a pathological request, never silently raised
CHARS_PER_TOKEN_ESTIMATE = 4.0       # fixed, documented English-text approximation; no tokenizer
                                      # named anywhere in this project (mirrors Stage 7 Decision 7)
```

## Known Limitations

- The token estimate is a fixed char-ratio approximation, not a real tokenizer count — can
  meaningfully over/under-estimate actual usage for any specific downstream model; revisit once a
  model/tokenizer is actually selected (the same gap Stage 7 already flagged for its own chunk-size
  thresholds, now inherited one stage further downstream).
- `estimate_tokens` only counts a block's own `text` — `heading_path`/`title`/other metadata a future
  prompt template might also inject are not counted, a deliberate, honest undercount, since Stage 11
  has no visibility into any prompt template (out of scope).
- Prefix-truncation budget enforcement can leave real remaining budget unused if a later, smaller
  block would have fit entirely — no bin-packing or reordering is attempted, by design.
- No chunk is ever split to fit a budget — a document whose single most relevant chunk alone exceeds
  the entire budget contributes zero blocks, even if a smaller, lower-rank chunk from a different
  document would have fit completely.
- Any cross-index score-comparability limitation already accepted by Stage 10 (mixing `cosine`/`l2`
  in one request) passes through unchanged into `ContextPackage`'s block ordering; Stage 11 makes no
  attempt to re-normalize or correct it.

## Accepted Tradeoffs

- **No persisted output artifact.** `ContextPackage` is entirely in-memory, extending Stage 10's own
  precedent one stage further — no audit trail exists unless a caller persists it independently.
- **Fixed char-ratio token estimation, not a real tokenizer dependency.** Avoids introducing a new
  dependency and a model-specific coupling before any model is actually chosen; accepts estimation
  error as the cost.
- **Prefix-truncation budget enforcement, not adaptive bin-packing.** Bounded, predictable, easy to
  reason about and test; accepts leaving some budget unused in exchange.
- **`validate_retrieval_result()` deliberately reuses Stage 10's function name.** Kept symmetric with
  Stage 10's own contract naming rather than inventing an artificially different name — accepted as
  an intentional, documented naming collision across two different modules, never a shared
  implementation.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not this
document.

- A malformed `RetrievalResult` is rejected deterministically, every time, without producing any
  `ContextPackage`.
- `RetrievalResult.status == "FAIL"` always produces `ContextPackage.status == "FAIL"` with
  `context_blocks == []`, without ever calling `build_context_blocks` or `enforce_budget`.
- `context_blocks` ordering is always identical to the surviving subsequence of
  `RetrievalResult.results`' own rank order — never independently sorted.
- No chunk is ever split; every `ContextBlock.text` is byte-identical to its source
  `RetrievedChunk.text`.
- Budget enforcement always yields a contiguous rank-order prefix as `included`, and the exact
  remaining suffix as `excluded` — `included_block_count + excluded_block_count ==
  len(retrieval_result["results"])` always, and `excluded_context_blocks` is always exactly that
  `excluded` list, never discarded or summarized away.
- `sum(block.estimated_tokens for block in context_blocks) == total_estimated_tokens` always, and
  `total_estimated_tokens <= context_budget_tokens` always; `excluded_estimated_tokens` always equals
  `sum(block.estimated_tokens for block in excluded_context_blocks)`; `budget_utilization` always
  equals `total_estimated_tokens / context_budget_tokens` and always falls in `[0.0, 1.0]`.
- `rank` values on `context_blocks` are always exactly `0..included_block_count-1`, contiguous, with
  no re-assignment performed by Stage 11; `context_block_id` is always exactly
  `f"{context_package_id}_{chunk_id}"`, and no `block_index` field is ever introduced alongside it.
- Every one of the five internal invariant codes (`DUPLICATE_CONTEXT_BLOCK`, `RANK_NOT_CONTIGUOUS`,
  `TOKEN_ESTIMATE_SUM_MISMATCH`, `BUDGET_INVARIANT_VIOLATED`, `EXCLUDED_COUNT_MISMATCH`) fires under
  its documented condition and only that condition.
- A zero-block outcome produces `is_empty=True`, `context_blocks=[]`, one `CONTEXT_EMPTY` WARNING —
  never conflated with `status="FAIL"` unless `RetrievalResult.status` was itself already `"FAIL"`.
- Determinism: identical `(RetrievalResult, context_budget_tokens)` produces a byte-identical
  `ContextPackage` (`assembled_at` excluded), across repeated calls and process restarts.
- Immutability: the input `RetrievalResult` object is never mutated by any Stage 11 function.

## Real Corpus Verification

Against the real, current corpus (via a real `RetrievalResult` produced by Stage 10 against the live
`vector_index/`): a representative multi-result query's `ContextPackage.context_blocks` preserve
exactly Stage 10's own rank order; a deliberately small `context_budget_tokens` (smaller than the
combined estimated tokens of all results) produces a correctly-truncated contiguous prefix, with
`excluded_block_count > 0`, a non-empty `excluded_context_blocks` matching it exactly,
`excluded_estimated_tokens > 0`, `budget_utilization` correctly computed and `<= 1.0`, and a
`CONTEXT_BUDGET_EXCEEDED` finding; a generously large budget includes every result with
`excluded_block_count == 0` and `excluded_context_blocks == []`; every included block's `text` is
confirmed byte-identical to its source `RetrievedChunk.text`.

**Determinism, explicitly:** two identical `RetrievalResult`s, run through `assemble_context()` with
the same `context_budget_tokens`, produce two byte-identical `ContextPackage`s (`assembled_at`
excluded) — checked directly, not only implied, including `context_package_id`, every
`context_block_id`, and every overflow-metadata field (`excluded_context_blocks`,
`excluded_estimated_tokens`, `budget_utilization`).

Immutability: the input `RetrievalResult` object and every real upstream artifact (`manifest.json`,
every `chunks.json`, `embeddings.parquet`, `metadata.json`, everything under `vector_index/`) are
confirmed byte-identical before and after the call.

## Future Stage Boundaries

Stage 12+ (not designed here) owns everything Stage 11 deliberately excludes: prompt construction,
system prompts, LLM invocation, answer generation, citation formatting, reasoning, retrieval-quality
evaluation, conversation memory, streaming, and any network-facing API or UI. Stage 11 hands a
`ContextPackage` back in memory; how a caller turns it into an actual prompt, invokes a model, or
formats an answer is entirely out of this design's scope.
