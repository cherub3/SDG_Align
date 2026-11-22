# Stage 15 — Groundedness Validation

Stages 0–14 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 15 turns Stage 14's `CitedResponse` into a `GroundednessReport`: for every `ResponseSpan` that
carries at least one `Citation`, it independently re-verifies that citation against the actual text of
the `ContextBlock` it references (read from Stage 11's `ContextPackage`), using a fixed, deterministic,
longest-common-substring-based structural test distinct from Stage 14's own n-gram containment score —
and classifies each span into one of three closed states: `GROUNDED`, `WEAKLY_GROUNDED`, or
`UNSUPPORTED`. It performs no second citation search, no generation, no second LLM call, and no
semantic or factual judgment of whether a claim is *true* — only whether the span's own text and its
cited block's own text share one long, coherent, contiguous run of matching content.
`validate_groundedness(cited_response, context_package, groundedness_threshold)` is the sole public
entrypoint.

Stage 15 requires two inputs, not one — `CitedResponse` and `ContextPackage` — because the block text
a citation must be verified against exists only on `ContextPackage`; `Citation` (Stage 14's own frozen
schema) carries only an id and a previously-computed score, never the cited block's own text (see
Design Decisions #1).

## Scope

Stage 15 answers exactly one question — given a `CitedResponse`'s already-attached citations, how
strongly, by a fixed lexical measure, does each cited block's own text actually support the span it was
attached to — and stops there. It never re-decides *whether* a citation should have been attached in
the first place (that is Stage 14's own, frozen job); it never searches `context_blocks` for a citation
an uncited span might deserve; it never judges factual correctness, truthfulness, or semantic
entailment of any claim (that would require a model, forbidden by Principle 5 — see Non-
Responsibilities and Known Limitations); it never invokes a second LLM call to explain, verify, or
critique a citation; it never rewrites, summarizes, truncates, or reformats `response_text`, any
`span.text`, or any `Citation`; it never re-ranks, re-scores, or filters `ContextBlock`s themselves (no
block is ever excluded or reordered — only individual citations already attached to spans are scored);
it never persists anything; it never streams; it never scores overall *answer* quality (that is Stage
16's job, working from Stage 15's own output). Those boundaries are restated in Future Stage
Boundaries.

## Responsibilities

Stage 15 shall: receive a `CitedResponse` and a `ContextPackage`; structurally validate both before use
(schema well-formedness only — never groundedness, correctness, truthfulness, or answer quality, all
of which remain explicitly out of scope; see Non-Responsibilities); verify the two inputs actually
belong to the same request chain (`cited_response.context_package_id ==
context_package.context_package_id`); for every `ResponseSpan`, classify its groundedness using a
fixed, deterministic rule (Groundedness Verification Strategy) — `UNSUPPORTED` when `citations == []`,
otherwise independently re-score every attached `Citation` against its referenced `ContextBlock.text`
and classify `GROUNDED`/`WEAKLY_GROUNDED` by comparing the strongest recomputed score against a
configurable threshold; preserve `response_text` and every span/citation record byte-for-byte,
unmodified; and assemble a `GroundednessReport` whose own internal invariants are self-checked before
it is ever returned.

## Non-Responsibilities

Stage 15 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: citation extraction, re-extraction, or re-attachment of any kind (searching
`context_blocks` for a citation an `UNSUPPORTED` span might deserve is explicitly Stage 14's own,
frozen job, never Stage 15's — see Design Decisions #5); semantic entailment checking, fact-checking,
or any judgment of whether a claim is actually *true* (this would require an LLM or NLI model,
categorically forbidden by Principle 5 — see Known Limitations); any second LLM call, of any kind, for
groundedness explanation, verification, or scoring; semantic-embedding-based similarity of any kind (a
fresh Stage-8-style embedding call is rejected on the identical grounds Stage 14's own Design Decision
#2 already gave); answer-quality or retrieval-quality evaluation (Stage 16); rewriting, summarizing, or
reformatting `response_text`, any `span.text`, or any `Citation`; rendering, formatting, or serializing
a `GroundednessReport` or any `SpanGroundedness` into Markdown, HTML, footnote markers, or any other
UI-specific display representation; re-ranking, re-scoring, or filtering `ContextBlock`s (only
already-attached citations are scored — no block is ever excluded or reordered); response caching,
streaming, conversation memory, tool calling, agent planning, or any network-facing API or UI. Every
one of these remains reserved for a later, separate design (Future Stage Boundaries).

## Inputs

Two required inputs, both in-memory, both already held by whatever caller is orchestrating one query
through this pipeline's query-time chain:

- `CitedResponse` (Stage 14's own output schema, unchanged) — the sole source of `response_text`,
  `status`, `spans` (each carrying `citations`), and the full identity chain
  (`cited_response_id`/`llm_response_id`/`prompt_package_id`/`context_package_id`).
- `ContextPackage` (Stage 11's own output schema, unchanged) — read only for `context_package_id` (to
  verify against `CitedResponse.context_package_id`) and `context_blocks` (each carrying
  `context_block_id`, `chunk_id`, and `text` — the one field no `Citation` itself carries). No other
  `ContextPackage` field (`query`, `status`, budget/token stats, `findings`, `excluded_context_blocks`)
  is read (Design Decisions #12). No portion of this coupling can be removed: `Citation` (Stage 14's
  own frozen schema) never carries the cited block's own `text`, so `ContextPackage.context_blocks` is
  the only mechanism available for reading the actual evidence a citation is supposed to support (Design
  Decisions #1).

No other input is read. `LLMResponse`, `PromptPackage`, `manifest.json`, `chunks.json`,
`metadata.json`, `RetrievalResult`, vector indexes, and embeddings are never opened — every field Stage
15 needs already exists on one of its two in-memory inputs. Unlike Stage 14, no id-bridge object
(`PromptPackage`) is required at all: `CitedResponse.context_package_id` already links directly to the
`ContextPackage` Stage 14 itself consumed (Design Decisions #1). No PDF is ever reopened; no chunk is
ever regenerated; no vector search, embedding call, or LLM call is ever performed here.

## Outputs

None persisted. Stage 15 produces zero artifacts and writes to no file — the sixth consecutive fully
read-only, zero-manifest-interaction stage in this pipeline's query-time path, extending the posture
Stage 10 through Stage 14 each already established. Its sole output is an in-memory `GroundednessReport`
(see Schemas) returned directly to the caller.

## Schemas

All in-memory Python structures — none persisted, no file format to version.

**`SpanGroundedness`**
```jsonc
{
  "span_index": 0,                    // copied verbatim from the source ResponseSpan.span_index
  "groundedness": "GROUNDED",         // GROUNDED | WEAKLY_GROUNDED | UNSUPPORTED — closed vocabulary
  "best_groundedness_score": 0.91,    // max(compute_groundedness_overlap(span.text, block.text) over
                                       // every block cited by this span), or null when citations == []
  "strongest_grounding": {            // the single Citation (copied verbatim from CitedResponse, not
                                       // recomputed) achieving best_groundedness_score under Stage 15's
                                       // own metric — may differ from citations[0], which is ranked by
                                       // Stage 14's own match_score, not this stage's LCS-coverage
                                       // score (Known Limitations); null when citations == []
    "context_block_id": "...", "chunk_id": "...", "doc_id": "...", "match_score": 0.83
  }
}
```

**`GroundednessReport`**
```jsonc
{
  "groundedness_report_id": "...",         // deterministic identity, see Determinism
  "groundedness_pipeline_version": "1.0.0",
  "validated_at": "2026-07-20T12:00:00Z",  // timestamp, excluded from every determinism comparison
  "cited_response_id": "...",              // copied verbatim from the input CitedResponse
  "llm_response_id": "...",                // copied verbatim, full provenance
  "prompt_package_id": "...",              // copied verbatim, full provenance
  "context_package_id": "...",             // copied verbatim, already verified consistent
  "status": "PASS",                        // SKIPPED | FAIL | PARTIAL | PASS — pure passthrough of
                                            // CitedResponse.status (Design Decisions #7)
  "response_text": "...",                  // verbatim copy from CitedResponse, never modified
  "span_groundedness": [ /* SpanGroundedness, ..., one per CitedResponse.spans element, in the exact
                            same order — span_groundedness[i].span_index ==
                            cited_response["spans"][i]["span_index"] always */ ],
  "span_count": 6,
  "grounded_span_count": 4,
  "weakly_grounded_span_count": 1,
  "unsupported_span_count": 1,             // spans with citations == [] — inherited directly from
                                            // Stage 14's own uncited_span_count, never recomputed
                                            // independently of it
  "groundedness_score": 0.667,             // grounded_span_count / span_count; 1.0 when span_count == 0
                                            // (vacuously fully grounded — see Failure Handling)
  "groundedness_threshold": 0.8,           // the threshold this report was assembled against
  "findings": [ /* this stage's own findings: {severity, code, message} */ ],
  "citation_findings": [ /* CitedResponse.findings[], copied verbatim — full upstream provenance */ ]
}
```

## Groundedness Verification Strategy

A fixed, named, deterministic longest-common-substring (LCS) coverage transform — never a second LLM
call, never a semantic embedding similarity search, never a symmetric (Jaccard) n-gram measure (Design
Decisions #2), consistent with Principle 5 (deterministic before probabilistic). The specification
below is exhaustive: two independent implementations following it produce identical
`best_groundedness_score` values and identical classifications from identical input.

**Preprocessing (internal to `compute_groundedness_overlap` only).** Given a string (either a
`span.text` or a `ContextBlock.text`), the folded copy used for comparison is produced by Stage 15's
own private copy of Stage 14's exact `fold()` procedure, in this exact order: (1) Unicode
normalization to NFC; (2) locale-independent, simple-lowercase case-folding (never a locale-sensitive
rule); (3) whitespace normalization — every maximal run of whitespace collapsed to one space,
leading/trailing space stripped. No punctuation is removed or altered at any step. This folded copy
exists solely inside `compute_groundedness_overlap`; it is never stored, returned, or reused
anywhere else in this stage — `response_text`, every `span.text`, and every `Citation` are reported
everywhere else in this stage's output in their original, unmodified form. Stage 15 defines its own
private copy of this procedure rather than importing Stage 14's — the same each-stage-owns-its-own-
copy convention Stage 12 already established for its own `CHARS_PER_TOKEN_ESTIMATE` (Design Decisions
#10).

**Why fold at all before computing LCS.** Unicode NFC normalization and case-folding exist so that a
purely incidental difference — the model generating "Climate Change" where the source block reads
"climate change," or two visually-identical characters with different Unicode representations — never
prevents a genuinely matching, contiguous run from being found. Without folding, the longest-common-
substring computation would be needlessly brittle to formatting differences that carry no meaning
difference at all, systematically under-counting real grounding. Whitespace normalization exists for
the same reason: a line-wrapped or multiply-spaced rendering of the same underlying text should not
break an otherwise-contiguous match into several shorter ones. This is the identical rationale Stage
14 already gives for its own `fold()` (Stage 14's Citation Matching Strategy) — Stage 15 folds for the
same reason, one stage further downstream.

**Threshold ownership — stated explicitly to reinforce stage independence.**
`LOW_GROUNDEDNESS_THRESHOLD` (Constants) belongs exclusively to Stage 15's own package-level
aggregate finding (Validation §2). It is never read by, passed to, or in any way permitted to
influence Stage 14's own citation-attachment decision (`citation_match_threshold`,
`LOW_CITATION_COVERAGE_THRESHOLD`) — the two stages' thresholds are entirely separate, frozen
constants living in two separate, frozen modules, and no future change to one may be justified by
tuning the other. This is a restatement, not a new rule: Design Decisions #4 already establishes the
two-tier threshold split; this sentence exists solely so a future reader does not have to infer
cross-stage independence from that decision alone.

**Longest common substring.** For two folded strings `a` and `b`, the longest common substring length
`lcs_len(a, b)` is the length of the longest string that is a contiguous substring of both `a` and
`b` — a standard, unambiguous quantity: for any two finite strings there is exactly one such maximal
length (even when more than one substring of that length exists, the *length* itself is unique and
implementation-independent, computable by the standard O(len(a) × len(b)) dynamic-programming
recurrence `dp[i][j] = dp[i-1][j-1] + 1` when `a[i-1] == b[j-1]` else `0`, with `lcs_len(a, b) =
max(dp[i][j])`). If either folded string is empty, `lcs_len(a, b) = 0`, by definition, never an error.

**Containment formula.** `compute_groundedness_overlap(span_text, block_text)` folds both arguments as
above, then returns:
```
score = lcs_len(fold(span_text), fold(block_text)) / len(fold(span_text))
```
computed as standard IEEE-754 double-precision division — no epsilon or tolerance applied anywhere in
this comparison. If `len(fold(span_text)) == 0`, `compute_groundedness_overlap` returns exactly `0.0`,
by definition, never a division by zero. The formula is deliberately normalized by the **span's own**
folded length, not the block's and not their union — a symmetric (Jaccard-style) measure was
considered and rejected: `context_blocks` are typically far longer than any single response span, so a
symmetric intersection-over-union score is structurally dominated by the block's own size and would
collapse toward zero for a short, genuinely well-grounded span purely as an artifact of block length,
independent of actual grounding strength. Normalizing by the span's own length instead keeps the score
meaningful regardless of how much longer the cited block is, and makes `1.0` mean exactly "the entire
folded span text appears somewhere in the block as one uninterrupted, contiguous run" — a strictly
stronger, structurally different claim than Stage 14's own n-gram-*set* containment score, which is
order- and contiguity-insensitive and can be satisfied by scattered, unrelated five-character windows
matching in any order (Known Limitations, Design Decisions #2).

**Per-span verification.** For a `ResponseSpan` with `citations == []`: `groundedness = "UNSUPPORTED"`,
`best_groundedness_score = null`, `strongest_grounding = null` — no computation is performed, and
`context_blocks` is never searched for a citation this span might otherwise deserve (Design Decisions
#5). For a `ResponseSpan` with one or more citations: `compute_groundedness_overlap(span.text,
block.text)` is computed independently for **every** attached `Citation` (looking up each cited
block's `text` from `context_package["context_blocks"]` by `context_block_id`), never only the
citation Stage 14 itself ranked first by `match_score` — because LCS-coverage ranking can legitimately
differ from `match_score` ranking (Known Limitations), only an independent re-score of every candidate
correctly identifies the strongest evidence under this stage's own metric.

**Deterministic tie-break — stated once, authoritatively, here.** The citation achieving the maximum
`compute_groundedness_overlap` score becomes `strongest_grounding`. When two or more citations on the
same span tie for that maximum score, the tie is broken by **ascending `chunk_id`** — the same
deterministic tie-break convention Stage 14's own `match_span_to_blocks` already established for its
own `match_score` ordering, applied here to a different underlying score. This is the single place the
rule is defined; `verify_span_groundedness`'s own contract (Public Function Contracts) restates it as
an implementation obligation, never as a second, independent definition.

**Threshold comparison — the sole authoritative rule for per-span classification, stated nowhere else
in this document.** Given `best_groundedness_score` (only ever computed when `citations != []`):
`groundedness = "GROUNDED"` **if and only if** `best_groundedness_score >= groundedness_threshold` — a
closed, non-strict comparison, mirroring Stage 14's own `>=` convention exactly; otherwise
`groundedness = "WEAKLY_GROUNDED"`. `groundedness_threshold` gates only per-span classification; the
separate `LOW_GROUNDEDNESS_THRESHOLD` constant (Constants) gates only the package-level
`groundedness_score` aggregate finding (Validation) and is never applied per-span.

## Design Decisions

1. **Two inputs are required, not one, and no id-bridge object is needed.** `CitedResponse` alone
   cannot supply what Stage 15 needs: `Citation` (Stage 14's own frozen schema) carries only
   `context_block_id`/`chunk_id`/`doc_id`/`match_score` — never the cited block's own `text` — so
   "supported by their cited evidence" is unanswerable without reading `ContextPackage.context_blocks`
   directly. Unlike Stage 14 (which needed `PromptPackage` purely as an id-bridge, since `LLMResponse`
   carries no `context_package_id` of its own), Stage 15 needs no such bridge:
   `CitedResponse.context_package_id` (already copied verbatim by Stage 14 from the very
   `ContextPackage` it consumed) links directly to the correct package. Both objects are already held
   by any caller orchestrating one query through Stages 10–14 in sequence, so requiring both imposes no
   new burden.
2. **Groundedness verification is longest-common-substring coverage — never a reuse of Stage 14's own
   `match_score`, and never a symmetric (Jaccard) n-gram measure.** Reusing `match_score` verbatim would
   reduce Stage 15 to a second threshold on an already-computed number, incapable of catching the exact
   false-positive pattern Stage 14's own Known Limitations names: n-gram-*set* containment is order-
   and contiguity-insensitive, so five scattered, unrelated matching five-character windows score
   identically to one long, coherent, verbatim passage. LCS coverage requires one contiguous run,
   directly targeting that gap. A Jaccard-style symmetric measure (intersection over union of n-gram
   sets) was considered and rejected on a separate, concrete ground: `context_blocks` are typically far
   longer than any single response span, so a symmetric score is dominated by the block's own size and
   collapses toward zero for a short, genuinely well-grounded span, independent of actual grounding
   strength — an artifact of block length, not a meaningful signal. Normalizing LCS length by the
   span's own folded length (never the block's, never their union) avoids this collapse entirely.
3. **Every attached citation is independently re-scored, never only Stage 14's own top-ranked one.**
   `Citation` ordering on `ResponseSpan.citations` reflects Stage 14's own `match_score`-based tie-break
   (descending `match_score`, ascending `chunk_id`); LCS-coverage can legitimately rank a *different*
   citation highest for the same span (Known Limitations) — checking only `citations[0]` could report
   the wrong citation as "strongest," or miss a genuinely stronger one entirely.
4. **A two-tier threshold model, scoped differently at each tier — `groundedness_threshold` per span,
   `LOW_GROUNDEDNESS_THRESHOLD` only at the package level.** Mirrors Stage 14's own
   `citation_match_threshold`/`LOW_CITATION_COVERAGE_THRESHOLD` split exactly: one caller-configurable
   threshold gates each individual classification decision; a second, fixed constant gates only the
   aggregate package-level finding, and is never applied per span.
5. **`UNSUPPORTED` spans receive zero computation and are never re-searched against `context_blocks`.**
   Searching for a citation an uncited span might deserve is Stage 14's own citation-attachment job,
   frozen and out of scope here (Non-Responsibilities) — re-implementing any part of it, even
   defensively, would duplicate a responsibility this stage does not own.
6. **`groundedness_score` counts `GROUNDED` spans only, never `WEAKLY_GROUNDED`.** Mirrors Stage 14's
   own strict `citation_coverage` semantics (`cited_span_count` only, never a partial-credit blend) —
   a consistent, strict definition of "how much of this response is well-supported" across both stages.
7. **`status` is a pure passthrough of `CitedResponse.status`.** Stage 15 performs no external call of
   any kind; it can only ever classify data that already exists, exactly the same "can only ever lose
   information relative to upstream, never independently fail on its own terms" situation Stage 10,
   11, 12, and 14 were each already in. Its own findings (`LOW_GROUNDEDNESS_SCORE`,
   `ZERO_GROUNDED_CLAIMS`) are therefore always WARNING-severity and never alter `status`.
8. **`groundedness_report_id` is a deterministic hash over identity-determining inputs only, never over
   `span_groundedness` content.** Matching Stage 9/11/12/14's own "hash the identity-determining
   inputs, not the derived payload" pattern:
   ```python
   hash_input = {
       "cited_response_id": cited_response["cited_response_id"],
       "groundedness_threshold": groundedness_threshold
   }
   groundedness_report_id = sha256(canonical_json(hash_input)).hexdigest()
   ```
   `span_groundedness` is deliberately **not** hashed: given the hashed inputs, `context_package`
   (already implied by `cited_response_id`, since `CitedResponse` was itself built from exactly one
   `ContextPackage`), and the frozen verification algorithm, it is fully determined — hashing it would
   be redundant, not additionally identity-bearing.
9. **A mismatched `context_package_id` between the two inputs raises, rather than silently
   proceeding.** If `cited_response["context_package_id"] != context_package["context_package_id"]`,
   the two inputs do not actually describe one coherent request — a caller error (the wrong package
   was passed), not a normal degraded-but-expected outcome — raised at the input boundary
   (`CONTEXT_PACKAGE_ID_MISMATCH`) rather than surfaced as a package-level finding. Once this check
   passes, every `Citation.context_block_id` on every span is guaranteed resolvable against
   `context_package["context_blocks"]` by Stage 14's own frozen `CITATION_REFERENCES_UNKNOWN_BLOCK`
   invariant (already enforced when `CitedResponse` was built) composed with this stage's own id match
   — an inherited guarantee, not re-derived, the same "does not blindly trust the upstream stage's
   report" posture Stage 14 itself already applied to Stage 10/11's own dedup guarantee.
10. **Stage 15 defines its own private copies of `fold()` and `NGRAM_SIZE`-adjacent constants, never
    importing Stage 14's.** The folding *procedure* is identical to Stage 14's own (NFC normalize,
    case-fold, whitespace-collapse) because it is the same well-defined normalization question asked
    twice, but Stage 15 does not call Stage 14's private `compute_ngram_overlap` or its internal
    folding helper — the same each-stage-owns-its-own-copy convention Stage 12 already established for
    its own `CHARS_PER_TOKEN_ESTIMATE`/`estimate_prompt_tokens` (a fresh copy of Stage 11's identical
    formula).
11. **Stage 15 does not achieve "true semantic groundedness," despite Stage 14's own Known Limitations
    naming that as "Stage 15's job."** This is a deliberate, explicit correction, not a silent
    deviation: Stage 15 remains bound by Principle 5 exactly like every other stage in this pipeline —
    no LLM call, no embedding, no NLI/entailment model, anywhere in this design. What Stage 15 actually
    delivers is a second, independent, *stricter lexical* verification (Groundedness Verification
    Strategy) — a real improvement over trusting Stage 14's own single containment score at face value,
    but never semantic entailment, fact-checking, or a truth judgment of any kind (Known Limitations).
    Stage 14's own doc is frozen and is not edited by this design pass; this correction lives here, in
    Stage 15's own document, where the actual behavior is defined.
12. **Input validation checks only the fields Stage 15 actually reads, never full upstream-schema
    validation.** `validate_cited_response` inspects exactly `cited_response_id`, `llm_response_id`,
    `prompt_package_id`, `context_package_id`, `status`, `response_text`, `spans` (each span's
    `span_index`, `text`, `citations` — each citation's `context_block_id`, `chunk_id`, `doc_id`,
    `match_score`), and `findings` — no other `CitedResponse` field (`citation_pipeline_version`,
    `extracted_at`, `span_count`, `cited_span_count`, `uncited_span_count`, `citation_coverage`,
    `citation_match_threshold`, `llm_findings`) is inspected, referenced, or assumed present.
    `validate_context_package` inspects exactly `context_package_id` and `context_blocks` (each
    block's `context_block_id`, `chunk_id`, `text`) — no other `ContextPackage` field is inspected.
    This keeps the documented minimal coupling (Inputs) honest at the validation layer too — the same
    discipline Stage 14's own Design Decision #13 already established one stage upstream.
13. **`unsupported_span_count` is read directly from spans with `citations == []`, never
    cross-derived from Stage 14's own `uncited_span_count`.** Although the two values are guaranteed
    equal under correct operation (both count exactly the spans with zero citations), Stage 15
    computes its own count independently from `cited_response["spans"]` rather than trusting
    `cited_response["uncited_span_count"]` at face value — the same "does not blindly trust the
    upstream stage's own report" posture Design Decision #9 already applies to the id-resolution
    guarantee.
14. **`GroundednessReport` is fully in-memory, never persisted, matching Stage 10–14's own posture
    exactly.** The sixth consecutive zero-artifact, zero-manifest-interaction stage in this pipeline's
    query-time path; a future Stage 16 is expected to consume the returned object directly in-process.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md` §4's
Critical/Recoverable document-quarantine model, since Stage 15 has no document to quarantine and no
persisted artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10 through Stage 14
each already gave for their own Validation sections).

**1. Input validation codes** — raised, never returned as part of any `GroundednessReport`:

| Code | Raised as | Trigger |
|---|---|---|
| `CITED_RESPONSE_MALFORMED` | `GroundednessValidationInputError` | the received `CitedResponse` is missing a required key or has a wrong-typed value; no `GroundednessReport` is produced at all |
| `CONTEXT_PACKAGE_MALFORMED` | `GroundednessValidationInputError` | the received `ContextPackage` is missing a required key or has a wrong-typed value; no `GroundednessReport` is produced at all |
| `CONTEXT_PACKAGE_ID_MISMATCH` | `GroundednessValidationInputError` | `cited_response["context_package_id"] != context_package["context_package_id"]` (Design Decisions #9); no `GroundednessReport` is produced at all |

**2. Package-level findings** — recorded in `GroundednessReport.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `ZERO_GROUNDED_CLAIMS` | WARNING | package | `span_count > 0` and `groundedness_score == 0.0`; never alters `status` |
| `LOW_GROUNDEDNESS_SCORE` | WARNING | package | `0.0 < groundedness_score < LOW_GROUNDEDNESS_THRESHOLD`; never alters `status` |
| `RESPONSE_EMPTY` | WARNING | package | `span_count == 0` (an empty `response_text` upstream, e.g. because `CitedResponse.status` was `SKIPPED`/`FAIL`); never alters `status` |

`status` truth table (pure passthrough, no additional Stage 15 condition):

| Condition | `status` |
|---|---|
| `CitedResponse.status == "SKIPPED"` | `SKIPPED` |
| `CitedResponse.status == "FAIL"` | `FAIL` |
| `CitedResponse.status == "PARTIAL"` | `PARTIAL` |
| `CitedResponse.status == "PASS"` | `PASS` |

**3. Internal invariant codes** — raised by `validate_groundedness_report()`, run unconditionally on
the assembled report before it is ever returned; never returned as part of any `GroundednessReport`:

| Code | Trigger |
|---|---|
| `SPAN_COUNT_MISMATCH` | `len(report["span_groundedness"]) != len(cited_response["spans"])`, or `report["span_count"] != len(cited_response["spans"])` |
| `SPAN_ALIGNMENT_MISMATCH` | for any `i`, `span_groundedness[i]["span_index"] != cited_response["spans"][i]["span_index"]` — the two lists must be in exact positional correspondence |
| `GROUNDEDNESS_LABEL_INVALID` | a span's `groundedness` is inconsistent with its own `citations`/`best_groundedness_score`: `citations == []` but `groundedness != "UNSUPPORTED"` or `best_groundedness_score is not None`; `citations != []` but `groundedness == "UNSUPPORTED"`; `groundedness == "GROUNDED"` but `best_groundedness_score < groundedness_threshold`; `groundedness == "WEAKLY_GROUNDED"` but `best_groundedness_score >= groundedness_threshold` |
| `STRONGEST_GROUNDING_MISMATCH` | `strongest_grounding` (when not `null`) is not the `Citation` on that span achieving the maximum recomputed `compute_groundedness_overlap` score (ties broken by ascending `chunk_id`) |
| `GROUNDEDNESS_COMPUTATION_MISMATCH` | `groundedness_score != (grounded_span_count / span_count if span_count > 0 else 1.0)`, or `grounded_span_count + weakly_grounded_span_count + unsupported_span_count != span_count` |
| `CITED_RESPONSE_ID_MISMATCH` | `report["cited_response_id"] != input CitedResponse["cited_response_id"]`, or `report["llm_response_id"] != input CitedResponse["llm_response_id"]`, or `report["context_package_id"] != input CitedResponse["context_package_id"]` |

Any of these six raises `GroundednessValidationInternalError` rather than being returned as a malformed
`GroundednessReport` — the same fail-loud posture as Stage 10 through Stage 14's own internal-invariant
exceptions, and never expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage15_groundedness_validation"`, `doc_id: null`
always — entries are request-scoped, not document-scoped). New codes this stage adds:
`WARNING_ZERO_GROUNDED_CLAIMS`, `WARNING_LOW_GROUNDEDNESS_SCORE`, `WARNING_RESPONSE_EMPTY`. No new
`FATAL_*` code — Stage 15 never sets a manifest `error_code`, since it never touches the manifest at
all (see Manifest Interaction).

## Manifest Interaction

None. Stage 15 never opens, reads, or writes `manifest.json` — the fifth stage in this pipeline with
zero manifest interaction of any kind, extending Stage 11 through Stage 14's own posture: every field
it needs already arrived on its two in-memory inputs.

## Artifact Interaction

None. Stage 15 performs zero file reads and zero file writes. Its only inputs are in-memory
(`CitedResponse`, `ContextPackage`); its only output is an in-memory `GroundednessReport`. No
atomicity concern exists because there is nothing to persist and nothing to read from disk at all — the
same posture Stage 14 already established.

## Directory Structure

None added. Stage 15 introduces no new artifact directory — there is no artifact.

## Determinism

Stage 15's own transform is fully deterministic — a pure function of its two inputs, with no external
call of any kind. The same materially different situation from Stage 13's own explicit exception that
Stage 14 already noted: Stage 15 performs no live call and processes whatever `CitedResponse` it is
handed with total determinism, regardless of whether that `CitedResponse`'s own `response_text`
(ultimately traceable to a Stage 13 sampling call) varied between two upstream runs.

- **Stable verification.** `compute_groundedness_overlap` is a pure function of its two string
  arguments alone, using the fixed, fully-specified LCS-coverage formula (Groundedness Verification
  Strategy) — identical `(span_text, block_text)` always yields an identical score.
- **Stable classification.** `groundedness_threshold` comparison is a fixed `>=` rule (Groundedness
  Verification Strategy) — no randomness, no external state.
- **Stable tie-break.** When more than one citation ties for the maximum recomputed score on one span,
  `strongest_grounding` is always the same one: ascending `chunk_id`.
- **Stable `groundedness_report_id`.** Deterministic sha256 over exactly `cited_response_id` and
  `groundedness_threshold` — no timestamp/UUID/random input.
- **Stable output.** Identical `(CitedResponse, ContextPackage, groundedness_threshold)` produces a
  byte-identical `GroundednessReport` (`validated_at` excluded), across repeated calls and process
  restarts — including the case where the same `CitedResponse` is replayed through Stage 15 twice, even
  though it might never recur from a live Stage 13/14 run.

## Read-Only Guarantees

Stage 15 never modifies `manifest.json`, any `CitedResponse`, `ContextPackage`, `PromptPackage`,
`LLMResponse`, `RetrievalResult`, any chunk, any metadata, any vector index, or any embedding. No
upstream artifact or in-memory object is ever mutated; no write capability, and no network call of any
kind, exists anywhere in this design.

## Failure Handling

- **A malformed `CitedResponse` or `ContextPackage`** (missing/wrong-typed required key) —
  `GroundednessValidationInputError` (`CITED_RESPONSE_MALFORMED` / `CONTEXT_PACKAGE_MALFORMED`) raised
  immediately; no `GroundednessReport` returned.
- **A mismatched `context_package_id` between the two inputs** — `GroundednessValidationInputError`
  (`CONTEXT_PACKAGE_ID_MISMATCH`) raised immediately; no `GroundednessReport` returned.
- **`CitedResponse.status` in `{SKIPPED, FAIL}`** — `spans == []` is already guaranteed by Stage 14's
  own contract; `span_groundedness` is naturally empty; `GroundednessReport.status` passes through as
  `SKIPPED`/`FAIL`; `RESPONSE_EMPTY` WARNING recorded; no special-cased branch is needed (mirrors Stage
  14's own Design Decision #4 for the identical situation one stage upstream).
- **`CitedResponse.status == "PARTIAL"`** — verification proceeds normally over whatever spans are
  present; `GroundednessReport.status` stays `PARTIAL`; `CitedResponse.findings` carried forward
  verbatim into `citation_findings`.
- **A span with `citations == []`** — `groundedness = "UNSUPPORTED"`; not an error, not a per-span
  WARNING; `context_blocks` is never searched for a citation this span might deserve (Design Decisions
  #5). This is a legitimate, expected outcome — the same "an uncited span is not itself evidence of
  anything" posture Stage 14's own Design Decision #9 already established one stage upstream, now
  extended into Stage 15's own classification vocabulary as `UNSUPPORTED` rather than left implicit.
- **A span whose strongest recomputed score falls below `groundedness_threshold`** —
  `groundedness = "WEAKLY_GROUNDED"`; not an error, not a per-span WARNING; the citation was
  legitimately attached by Stage 14 (its `match_score` already cleared Stage 14's own, looser
  threshold) but does not clear this stage's own, stricter contiguous-run bar.
- **A successful, non-empty response with `groundedness_score == 0.0`** (every span is `UNSUPPORTED`
  or `WEAKLY_GROUNDED`, none `GROUNDED`) — `ZERO_GROUNDED_CLAIMS` WARNING; `status` unaffected — a
  legitimate, informative outcome, never treated as an error.
- **`groundedness_threshold` omitted, or below/above `[0.0, 1.0]`** — defaulted to
  `DEFAULT_GROUNDEDNESS_THRESHOLD`, clamped to `[0.0, 1.0]` (mirrors the caller-supplied-with-default
  convention Stage 11 through Stage 14 each already established for their own tunables).
- **A genuine Stage 15 bug** (one of the six named internal invariant codes in Validation §3) —
  `GroundednessValidationInternalError` raised, not returned as a malformed `GroundednessReport`.

## Configuration

`groundedness_threshold` is per-request configuration, never defaulted from any global or environment
state except via the named `DEFAULT_GROUNDEDNESS_THRESHOLD` constant when the caller omits it entirely
— the same per-request convention Stage 11 through Stage 14 each already established for their own
tunables. `NGRAM_SIZE`-adjacent internals (there is no n-gram size in this stage's own algorithm; LCS
computation has no analogous tunable) and `LOW_GROUNDEDNESS_THRESHOLD` are fixed constants, not
per-request configuration — varying the verification *algorithm* itself per call would break the
"identical input always yields identical output" determinism guarantee across calls using different
settings, so only the pass/fail threshold on an otherwise-fixed algorithm is exposed (mirrors Stage
14's own Configuration section exactly). Stage 15 consumes no adapter factories of any kind; it never
touches `ProviderAdapter`, `IndexAdapter`, or `LLMAdapter`.

## Concurrency

Fully safe under concurrent calls. Stage 15 performs zero writes, holds no shared mutable state, and
makes no network or file-system call of any kind — `validate_groundedness()` is a pure function of its
own arguments; any number of calls, including against identical input, may run simultaneously with no
locking and no race condition.

## Security Considerations

- **Untrusted model output, inherited.** `response_text` and every `span.text` remain opaque,
  model-generated content — Stage 15 performs no interpretation, execution, or sanitization of it
  beyond computing longest-common-substring length against block text; this is the same
  "`response_text` is potentially adversarial input to whatever consumes it next" risk Stage 13 first
  accepted (Stage 13's own Design Decisions #11) and Stage 14 already passed through unchanged (Stage
  14's own Security Considerations).
- **No new I/O surface.** Stage 15 opens no file, calls no network endpoint, and touches no credential
  of any kind — the same strictly narrow surface Stage 14 already established.
- **No write capability anywhere in this design** — eliminates an entire class of injection/corruption
  risk against this pipeline's own artifacts and in-memory objects by construction, not by runtime
  validation.

## Public Function Contracts

- `validate_cited_response(response: CitedResponse) -> None` — Stage 15's own structural input check;
  inspects exactly `cited_response_id`, `llm_response_id`, `prompt_package_id`, `context_package_id`,
  `status`, `response_text`, `spans` (each span's `span_index`, `text`, `citations` — each citation's
  `context_block_id`, `chunk_id`, `doc_id`, `match_score`), and `findings` — no other `CitedResponse`
  field is inspected (Design Decisions #12). Raises `GroundednessValidationInputError` (code
  `CITED_RESPONSE_MALFORMED`) on violation. Distinct from, and never calling, Stage 14's own internal
  function of the same name.
- `validate_context_package(package: ContextPackage) -> None` — Stage 15's own structural input check;
  inspects exactly `context_package_id` and `context_blocks` (each block's `context_block_id`,
  `chunk_id`, `text`) — no other `ContextPackage` field is inspected (Design Decisions #12). Raises
  `GroundednessValidationInputError` (code `CONTEXT_PACKAGE_MALFORMED`). Distinct from, and never
  calling, Stage 11's or Stage 12's own functions of the same name.
- `verify_context_package_match(cited_response: CitedResponse, context_package: ContextPackage) ->
  None` — raises `GroundednessValidationInputError` (code `CONTEXT_PACKAGE_ID_MISMATCH`) if
  `cited_response["context_package_id"] != context_package["context_package_id"]` (Design Decisions
  #9).
- `compute_groundedness_overlap(span_text: str, block_text: str) -> float` — fixed
  longest-common-substring coverage score (Groundedness Verification Strategy); pure function of its
  two arguments; returns `0.0` when `fold(span_text)` is empty.
- `verify_span_groundedness(span: ResponseSpan, context_blocks_by_id: Dict[str, ContextBlock],
  groundedness_threshold: float) -> SpanGroundedness` — returns `UNSUPPORTED` immediately (no
  computation) when `span["citations"] == []`; otherwise computes `compute_groundedness_overlap`
  against every cited block and returns the classified result, ordered deterministically on ties by
  ascending `chunk_id` (Groundedness Verification Strategy).
- `build_groundedness_report(cited_response: CitedResponse, context_package: ContextPackage,
  span_groundedness_list: List[SpanGroundedness], groundedness_threshold: float) ->
  GroundednessReport` — wraps span groundedness + aggregate stats + inherited `status`/findings into
  the final report; computes `groundedness_report_id`.
- `validate_groundedness_report(report: GroundednessReport, cited_response: CitedResponse,
  context_package: ContextPackage) -> None` —
  internal invariant self-check; raises `GroundednessValidationInternalError` (one of the six named
  codes in Validation §3) on violation. `context_package` is required because the
  `STRONGEST_GROUNDING_MISMATCH` invariant must recompute `compute_groundedness_overlap` scores
  against actual block text from `ContextPackage.context_blocks` — information not available on
  either `GroundednessReport` or `CitedResponse` alone.
- `validate_groundedness(cited_response: CitedResponse, context_package: ContextPackage,
  groundedness_threshold: Optional[float] = None) -> GroundednessReport` — the sole public entrypoint;
  orchestrates the full pipeline; never reads or writes any artifact, the manifest, or any network
  endpoint.

## Constants

```python
GROUNDEDNESS_PIPELINE_VERSION = "1.0.0"
DEFAULT_GROUNDEDNESS_THRESHOLD = 0.8       # LCS-coverage cutoff for GROUNDED classification — stricter
                                            # than Stage 14's own DEFAULT_CITATION_MATCH_THRESHOLD (0.6),
                                            # deliberately, since this is a second, harder-to-satisfy bar
LOW_GROUNDEDNESS_THRESHOLD = 0.5           # below this (and above 0.0), LOW_GROUNDEDNESS_SCORE fires —
                                            # package-level only, never applied per span
```

## Known Limitations

- **This is not semantic groundedness, and does not achieve fact-checking or entailment.** A `GROUNDED`
  span can still be factually wrong if its cited passage is itself wrong, outdated, or — most
  importantly — misquoted in a meaning-reversing way that happens to preserve a long verbatim run (a
  negation flip: a span asserting "X is true" scoring `GROUNDED` against a block that actually reads
  "X is not true" would still find a long common substring covering "X is true"). This is the single
  most important limitation of this stage, and is not fixable within Principle 5's deterministic-
  before-probabilistic constraint — true semantic/factual verification is out of scope for this entire
  pipeline unless and until a future, explicitly-approved design introduces controlled LLM/NLI usage
  (Design Decisions #11).
- **`WEAKLY_GROUNDED` does not mean the claim is false.** It only means the strongest recomputed
  contiguous-overlap score against the span's own cited block(s) fell short of
  `groundedness_threshold` — a genuinely well-supported claim phrased very differently from its source
  passage (after folding) would also land here.
- **`UNSUPPORTED` does not mean "hallucinated" or "false."** It only means Stage 14 attached zero
  citations to that span; Stage 15 never re-searches `context_blocks` for a citation Stage 14 might
  have missed (Design Decisions #5) — that remains exclusively Stage 14's own, frozen job.
- **`strongest_grounding` can name a different `Citation` than `span.citations[0]`.** LCS-coverage
  ranking and Stage 14's own `match_score` ranking are two structurally different measures and can
  legitimately disagree on which citation is "strongest" for the same span — an intentional,
  documented consequence of independently re-scoring every candidate (Design Decisions #3), never a
  bug.
- **No cross-validation between `groundedness_threshold` and `CitedResponse.citation_match_threshold`.**
  A caller could configure a degenerate combination that collapses the `WEAKLY_GROUNDED` tier (e.g. a
  `groundedness_threshold` set at or below what a typical already-attached citation's LCS coverage
  tends to achieve); this is documented, not structurally prevented — mirrors the same kind of
  caller-responsibility limitation Stage 12's own Known Limitations already accepted for its own
  budget/template combination.
- **A short cited passage inside a much longer block is not penalized, nor rewarded, for the block's
  own length** — by design (Groundedness Verification Strategy), since the score is normalized only by
  the span's own length; this is the intended fix for the symmetric-measure collapse problem, restated
  here as a limitation in the other direction: a block's own overall relevance or focus is never
  assessed, only whether it happens to contain the cited span's own text as one contiguous run.

## Accepted Tradeoffs

- **A second, independent structural check (LCS coverage) over simply re-thresholding Stage 14's own
  `match_score`.** More expensive (one substring computation per citation per span, plus a second
  `ContextPackage` read) but catches a real, named class of false positives Stage 14's own metric
  cannot structurally rule out.
- **Two required inputs, not one.** Accepted because "supported by cited evidence" fundamentally
  requires reading the evidence's own text, which only `ContextPackage` carries; the coupling is judged
  minimal since no id-bridge object beyond what `CitedResponse` already carries is needed (Design
  Decisions #1).
- **No fact-checking, no semantic entailment, ever, within this stage.** Principle 5 compliance is
  non-negotiable in this project; accepted as a hard, permanent boundary for this design, not a gap
  deferred for a later patch to this same stage (Design Decisions #11).
- **`GroundednessReport` is fully in-memory, no persisted artifact.** Matches Stage 10 through Stage
  14's own precedent — no audit trail exists unless a caller persists it independently.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not this
document.

- A malformed `CitedResponse` or `ContextPackage` is rejected deterministically, every time, without
  producing any `GroundednessReport`.
- A mismatched `context_package_id` between the two inputs is rejected deterministically, every time,
  without producing any `GroundednessReport`.
- `CitedResponse.status` in `{SKIPPED, FAIL}` always produces `GroundednessReport.status` matching
  exactly, with `span_groundedness == []`, `span_count == 0`, and `groundedness_score == 1.0`
  (vacuous), without any special-cased branch in the implementation.
- A span with `citations == []` always produces `groundedness == "UNSUPPORTED"`,
  `best_groundedness_score is None`, and `strongest_grounding is None`, with zero calls to
  `compute_groundedness_overlap` for that span (verifiable via a call-count assertion).
- `compute_groundedness_overlap` is verified span-length-normalized, not block-length- or
  union-normalized — a case with a short span fully contained (as one contiguous run) inside a very
  long block still scores `1.0`, unlike a symmetric measure over the same input.
- Every span with `citations != []` has every one of its attached citations independently scored — a
  case where `span.citations[0]` (Stage 14's own top `match_score`) is *not* the citation with the
  highest recomputed `compute_groundedness_overlap` score is verified to still select the correct
  (different) citation as `strongest_grounding`.
- `groundedness == "GROUNDED"` if and only if `best_groundedness_score >= groundedness_threshold`;
  `groundedness == "WEAKLY_GROUNDED"` if and only if citations exist and `best_groundedness_score <
  groundedness_threshold`.
- `grounded_span_count + weakly_grounded_span_count + unsupported_span_count == span_count` always;
  `groundedness_score` always equals the documented formula exactly, counting `GROUNDED` only.
- `unsupported_span_count` always equals the number of spans with `citations == []`, verified
  independently of trusting `CitedResponse.uncited_span_count` at face value (Design Decisions #13).
- Every one of the six internal invariant codes (`SPAN_COUNT_MISMATCH`, `SPAN_ALIGNMENT_MISMATCH`,
  `GROUNDEDNESS_LABEL_INVALID`, `STRONGEST_GROUNDING_MISMATCH`, `GROUNDEDNESS_COMPUTATION_MISMATCH`,
  `CITED_RESPONSE_ID_MISMATCH`) fires under its documented condition and only that condition.
- Determinism: identical `(CitedResponse, ContextPackage, groundedness_threshold)` produces a
  byte-identical `GroundednessReport` (`validated_at` excluded), across repeated calls and process
  restarts.
- Immutability: neither input object is ever mutated by any Stage 15 function, regardless of outcome.
- No file is ever read or written, and no network call is ever made, by any Stage 15 function, under
  any input or outcome.

## Real Corpus Verification

Against a real `CitedResponse`/`ContextPackage` pair produced by the live Stage 10 → 11 → 12 → 13 → 14
chain: a representative `CitedResponse` with at least one genuinely well-grounded span (its cited
block's text visibly contains the span's own wording near-verbatim) classifies `GROUNDED`, with
`best_groundedness_score` reported and `>=` the configured `groundedness_threshold`; a span whose
citation was attached on scattered vocabulary overlap alone (constructed via a stub `CitedResponse`
with a `Citation` whose block text shares many isolated words with the span but no long contiguous
run) classifies `WEAKLY_GROUNDED` despite having passed Stage 14's own threshold, demonstrating the
false-positive case Stage 14's own Known Limitations named; an `UNSUPPORTED` span (an uncited span
already present in a real `CitedResponse`) classifies `UNSUPPORTED` with zero
`compute_groundedness_overlap` calls made for it; two identical runs of `validate_groundedness()` over
the same real pair and threshold produce byte-identical `GroundednessReport`s (`validated_at`
excluded), including every span's `best_groundedness_score` and `strongest_grounding`.

**Determinism, explicitly:** like Stage 14, this section states the ordinary, full byte-identical
guarantee without qualification — Stage 15 performs no live call of its own, so two calls sharing
identical inputs are guaranteed to produce byte-identical output when replayed.

Immutability: both input objects, and every real upstream artifact (`manifest.json`, every
`chunks.json`, `embeddings.parquet`, `metadata.json`, everything under `vector_index/`, every on-disk
prompt template file), are confirmed byte-identical before and after the call — Stage 15 opens none of
them directly.

## Future Stage Boundaries

Stage 16+ (not designed here) owns everything Stage 15 deliberately excludes: overall answer-quality or
retrieval-quality evaluation (scoring a completed, validated answer against ground truth or
heuristics), any semantic/factual entailment or fact-checking (were it ever introduced, via a future,
explicitly-approved design permitting controlled LLM/NLI usage — not assumed or implied here), response
caching or deduplication, response streaming to a caller or UI, tool/function calling, conversation
memory or multi-turn orchestration, agent planning, and any network-facing API or UI serving a response
to an end user. Stage 15 hands a `GroundednessReport` back in memory; how a caller scores the answer's
overall quality, decides whether to surface a `WEAKLY_GROUNDED`/`UNSUPPORTED` span differently to an
end user, or builds a multi-turn conversation on top of it is entirely out of this design's scope.
