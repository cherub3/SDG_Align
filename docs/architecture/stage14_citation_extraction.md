# Stage 14 — Citation Extraction

Stages 0–13 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 14 turns Stage 13's `LLMResponse` into a `CitedResponse`: it segments `response_text` into
ordered spans and, for each span, deterministically identifies which of Stage 11's `ContextBlock`s (if
any) the span's content overlaps with — attaching a citation reference to each grounded span and
leaving an ungrounded span uncited rather than guessing. It performs no generation, no second model
call, no factual judgment of whether a citation is *correct*, only whether the span's own text overlaps
the cited source's own text. `extract_citations(llm_response, prompt_package, context_package,
citation_match_threshold)` is the sole public entrypoint.

Stage 14 requires three inputs, not one — `LLMResponse`, `PromptPackage`, and `ContextPackage` — because
the structured, addressable source units it cites (`ContextBlock`s) exist only on `ContextPackage`;
`PromptPackage` carries only the already-flattened `context_text` string Stage 12 rendered from those
blocks (see Design Decisions #1).

## Scope

Stage 14 answers exactly one question — given an `LLMResponse`'s generated text and the `ContextBlock`s
it was generated from, which source(s), if any, does each part of the answer's text surface-overlap
with — and stops there. It never judges whether a citation is factually correct or whether an uncited
span constitutes a hallucination (that is Stage 15's job, working from Stage 14's own output); it never
invokes a second LLM call to explain or verify a citation; it never rewrites, summarizes, truncates, or
reformats `response_text` itself — every character of the original text is preserved, only annotated;
it never re-ranks, re-scores, or filters `ContextBlock`s (Stage 11's own ranking is untouched); it never
persists anything; it never streams; it never serves a citation to any external caller. Those
boundaries are restated in Future Stage Boundaries.

## Responsibilities

Stage 14 shall: receive an `LLMResponse`, a `PromptPackage`, and a `ContextPackage`; structurally
validate all three before use (schema well-formedness only — never groundedness, correctness, or
answer quality, all of which remain explicitly out of scope; see Non-Responsibilities); verify the
three inputs actually belong to the same request chain
(`llm_response.prompt_package_id == prompt_package.prompt_package_id` and
`prompt_package.context_package_id == context_package.context_package_id`); segment `response_text`
into an ordered, contiguous, exhaustive partition of spans using a fixed, deterministic rule; for each
span, score its lexical overlap against every `ContextBlock`'s own `text` using a fixed, deterministic
algorithm; attach a citation to a span for every block whose overlap score satisfies the Threshold comparison
rule (Citation Matching Strategy — the sole place that rule is stated, never repeated here); preserve
`response_text` byte-for-byte; and assemble a `CitedResponse` whose own internal
invariants are self-checked before it is ever returned.

## Non-Responsibilities

Stage 14 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: groundedness or hallucination validation (deciding whether a citation, once attached,
actually *supports* the cited claim — reserved for Stage 15); answer-quality or retrieval-quality
evaluation (Stage 16); any second LLM call, of any kind, for citation extraction, explanation, or
verification; semantic-embedding-based similarity matching (a new Stage 8 embedding call for span text
is explicitly rejected, see Design Decisions #2); rewriting, summarizing, or reformatting
`response_text`; rendering, formatting, or serializing a `Citation` into Markdown, HTML, footnote
markers, or any other UI-specific display representation — every `Citation` Stage 14 produces is a
plain structured record (Schemas), consumed by a later stage or caller, never pre-rendered text;
re-ranking or re-scoring `ContextBlock`s; response caching, streaming, conversation memory, tool
calling, agent planning, or any network-facing API or UI. Every one of these remains reserved for a
later, separate design (Future Stage Boundaries).

## Inputs

Three required inputs, all in-memory, all already held by whatever caller is orchestrating one query
through this pipeline's query-time chain:

- `LLMResponse` (Stage 13's own output schema, unchanged) — the sole source of `response_text`,
  `status`, and `prompt_package_id`.
- `PromptPackage` (Stage 12's own output schema, unchanged) — read only for `prompt_package_id` (to
  verify against `LLMResponse.prompt_package_id`) and `context_package_id` (to bridge to
  `ContextPackage`); `system_prompt`, `user_prompt`, `assembled_prompt`, and `context_text` are never
  read (see Design Decisions #1). No portion of this coupling can be removed: `LLMResponse` (Stage
  13's own frozen schema) carries no `context_package_id` of its own, so
  `PromptPackage.context_package_id` is the only mechanism available for connecting a given
  `LLMResponse` back to the `ContextPackage` it was produced from.
- `ContextPackage` (Stage 11's own output schema, unchanged) — the sole source of `context_blocks`,
  each carrying `chunk_id`, `doc_id`, `text`, and full provenance, used as the citable-source universe.

No other input is read. `manifest.json`, `chunks.json`, `metadata.json`, `RetrievalResult`, vector
indexes, and embeddings are never opened — every field Stage 14 needs already exists on one of its
three in-memory inputs (see Design Decisions #1). No PDF is ever reopened; no chunk is ever
regenerated; no vector search, embedding call, or LLM call is ever performed here.

## Outputs

None persisted. Stage 14 produces zero artifacts and writes to no file — the fifth consecutive fully
read-only, zero-manifest-interaction stage in this pipeline's query-time path, extending the posture
Stage 10 through Stage 13 each already established. Its sole output is an in-memory `CitedResponse`
(see Schemas) returned directly to the caller.

## Schemas

All in-memory Python structures — none persisted, no file format to version.

**`Citation`**
```jsonc
{
  "context_block_id": "...",     // copied verbatim from the cited ContextBlock
  "chunk_id": "...",
  "doc_id": "...",
  "match_score": 0.83            // overlap score, see Citation Matching Strategy; always in [0.0, 1.0]
}
```

**`ResponseSpan`**
```jsonc
{
  "span_index": 0,               // 0-indexed, contiguous within one CitedResponse
  "text": "...",                 // verbatim substring of response_text — never modified
  "start_offset": 0,             // character offsets into response_text; [start_offset, end_offset)
  "end_offset": 42,              // spans partition response_text exactly, in order, no gaps or overlaps
  "citations": [ /* Citation, ..., possibly empty — an uncited span is not an error */ ]
}
```

**`CitedResponse`**
```jsonc
{
  "cited_response_id": "...",              // deterministic identity, see Determinism
  "citation_pipeline_version": "1.0.0",
  "extracted_at": "2026-07-20T12:00:00Z",  // timestamp, excluded from every determinism comparison
  "llm_response_id": "...",                // copied verbatim from the input LLMResponse
  "prompt_package_id": "...",              // copied verbatim, already verified consistent
  "context_package_id": "...",             // copied verbatim, already verified consistent
  "status": "PASS",                        // SKIPPED | FAIL | PARTIAL | PASS — pure passthrough of
                                            // LLMResponse.status (Design Decisions #5)
  "response_text": "...",                  // verbatim copy from LLMResponse, never modified
  "spans": [ /* ResponseSpan, ..., in order; concatenating every span.text reconstitutes
                response_text exactly */ ],
  "span_count": 6,
  "cited_span_count": 5,                   // spans with at least one citation
  "uncited_span_count": 1,                 // spans with zero citations — not an error, see Design
                                            // Decisions #9
  "citation_coverage": 0.833,              // cited_span_count / span_count; 1.0 when span_count == 0
                                            // (vacuously fully covered — see Failure Handling)
  "citation_match_threshold": 0.6,         // the threshold this package was assembled against
  "findings": [ /* this stage's own findings: {severity, code, message} */ ],
  "llm_findings": [ /* LLMResponse.findings[], copied verbatim — full upstream provenance */ ]
}
```

## Response Segmentation

`segment_response_text(response_text)` partitions `response_text` into an ordered, contiguous,
gap-free sequence of `ResponseSpan`s using a fixed character-class algorithm — never a linguistic
sentence tokenizer, and never dependent on any abbreviation list, locale table, or other external
resource. The algorithm is fully specified below; two independent implementations following it
produce byte-identical spans for identical input.

**Definitions.** `SPAN_TERMINATORS = ('.', '!', '?')` (Constants) — characters that can begin a
boundary. `SPAN_TRAILING_CLOSERS = ('"', "'", ')', ']', '”', '’', '»')` (Constants) —
characters that may immediately extend an already-open boundary without ending it, but can never begin
one on their own.

**Step 1 — empty input.** If `response_text == ""`, `segment_response_text` returns `[]` immediately;
no further steps run.

**Step 2 — locate boundary runs.** Scan `response_text` left to right. A *boundary run* is a maximal
contiguous substring whose first character is a member of `SPAN_TERMINATORS` and every subsequent
character (if any) is a member of `SPAN_TERMINATORS ∪ SPAN_TRAILING_CLOSERS` — "maximal" meaning the
run is extended one character at a time for as long as this condition holds, then stops. A
`SPAN_TRAILING_CLOSERS` character can never start a run by itself. This single rule is what collapses
`"..."`, `"?!"`, `"!!!"`, and `'!"'` into exactly one boundary run apiece, rather than one run per
character.

**Step 3 — decide which boundary runs are active.** A boundary run is *active* (produces a span break)
if and only if at least one of the following holds:
  (a) it is immediately followed by one or more space or tab characters in `response_text`;
  (b) it is immediately followed by one or more newline characters;
  (c) it is the final characters of `response_text` (nothing follows it at all).
A boundary run satisfying none of these (immediately followed by a non-whitespace, non-end-of-string
character — e.g. the `.` inside `"3.14"`, immediately followed by `"1"`) is *not* active and produces
no break; the text flows through it into the same span uninterrupted. This is what makes ordinary
decimal numbers ("3.14") fall out correctly without any digit-specific special case, and what makes an
abbreviation like "Dr. Smith" deliberately *not* special-cased: `"Dr."` followed by a space *is* an
active boundary under rule (a) — "Dr." and "Smith" fall into two separate spans. This is a deliberate
application of Principle 5 (deterministic before probabilistic): a fixed, exact, fully-specified rule
is chosen over a probabilistic or list-driven abbreviation detector, even at the cost of this kind of
linguistic imprecision — documented, intended behavior of the fixed rule, never an oversight (see
Known Limitations).

**Step 4 — newline runs are always active, independent of Steps 2–3.** Separately from any boundary
run, every maximal run of one or more newline characters anywhere in `response_text` is *always* an
active boundary, whether or not it is adjacent to a `SPAN_TERMINATORS` character (a paragraph break is
a boundary on its own).

**Step 5 — merge adjacent/overlapping active boundaries.** Collect every active boundary from Steps
3–4 as a `(start, end)` character-offset range. If any two active boundaries are adjacent (one's `end`
equals the other's `start`) or overlapping, they are merged into a single boundary spanning their
union, repeated until no two remaining boundaries are adjacent or overlapping. This merge step is what
prevents an empty span from ever being produced between, for example, a terminator run immediately
followed by a paragraph break (`"done.\n\n"`).

**Step 6 — partition.** Walking `response_text` in order: the text of each active boundary (after
Step 5's merge) is appended in full to the end of the span currently being built — never dropped,
never split into a span of its own. A new span begins at the first character immediately after an
active boundary ends. A boundary that reaches the literal end of `response_text` (Step 3c) simply
closes the final span; it never creates an additional, empty span after itself.

**Guarantees, by construction:**
- Every character of `response_text` belongs to exactly one span — `sum(len(span.text) for span in
  spans) == len(response_text)` always, and concatenating every `span.text` in encounter order
  reconstitutes `response_text` exactly (`SPAN_TEXT_MISMATCH`, Validation §3).
- No span is ever zero-length: a new span is only ever opened when at least one non-boundary
  character follows, and the merge step (5) prevents two active boundaries from ever standing
  back-to-back with nothing between them.
- `span.text` is never whitespace-collapsed, case-folded, or otherwise altered — segmentation only
  ever decides *where* to cut, never rewrites what is on either side of the cut. (Normalization for
  matching purposes happens later, only inside `compute_ngram_overlap`'s own internal, throwaway
  copy — see Citation Matching Strategy — and never touches the stored `span.text`.)
- Spans are produced in one left-to-right pass and are therefore always already in increasing
  `start_offset` order, numbered `0..span_count-1` contiguously, with no re-sorting step required.
- `start_offset` and `end_offset` are character offsets into the **original, unmodified**
  `response_text` — never into any folded, normalized, or otherwise transformed copy (the folded copy
  used inside `compute_ngram_overlap` is fully internal and never influences offsets). This means a
  later stage (e.g. a future Stage 15 mapping a groundedness finding back to exact source text) can
  always recover a span's precise source position using `response_text[span.start_offset :
  span.end_offset]` alone, with no re-derivation — already true of the `ResponseSpan` schema
  (`start_offset`, `end_offset`, `text`) and restated here explicitly as a guarantee, not merely a
  field that happens to exist.

## Citation Matching Strategy

A fixed, named, deterministic lexical-overlap transform — never a second LLM call, never a semantic
embedding similarity search (Design Decisions #2), consistent with Principle 5 (deterministic before
probabilistic). The specification below is exhaustive: two independent implementations following it
produce identical `match_score` values and identical citation sets from identical input.

**Preprocessing (internal to `compute_ngram_overlap` only).** Given a string (either a `span.text` or a
`ContextBlock.text`), the folded copy used for comparison is produced by, in this exact order:
1. Unicode normalization to Normalization Form C (NFC).
2. Case-folding via a locale-independent, simple lowercase mapping (never a locale-sensitive casing
   rule — e.g. the Turkish dotless-i rule is never applied, regardless of runtime locale).
3. Whitespace normalization: every maximal run of one or more whitespace characters (space, tab,
   newline) is collapsed to exactly one space character, and the result is stripped of any leading or
   trailing space.
No punctuation is removed or altered at any step — every punctuation character survives folding and
participates in n-gram formation exactly like any other character. This folded copy exists solely
inside `compute_ngram_overlap`; it is never stored, returned, or reused anywhere else in this stage —
`response_text`, every `span.text`, and every `ContextBlock.text` are reported everywhere else in this
stage's output in their original, unmodified form (see Design Decisions #7 for why this does not
conflict with Stage 10's own "no lowercasing, ever" rule).

**N-gram extraction.** For a folded string `s` of length `L` (measured in Unicode code points, i.e.
Python string length/indexing — never grapheme clusters or bytes) and the fixed `NGRAM_SIZE = 5`
(Constants): if `L < NGRAM_SIZE`, the n-gram set is the empty set. Otherwise, the n-gram set is the set
of *unique* length-`NGRAM_SIZE` substrings `{s[i : i + NGRAM_SIZE] for i in range(0, L - NGRAM_SIZE +
1)}` — a set, not a multiset: an n-gram that occurs more than once in `s` still contributes exactly one
member to the set. `ngrams(s)` denotes this set throughout.

**Containment formula.** `compute_ngram_overlap(span_text, block_text)` folds both arguments as above,
then returns:
```
score = |ngrams(fold(span_text)) ∩ ngrams(fold(block_text))| / |ngrams(fold(span_text))|
```
computed as standard IEEE-754 double-precision division of two non-negative integers — no epsilon or
tolerance is applied anywhere in this comparison. If `ngrams(fold(span_text))` is empty (i.e.
`len(fold(span_text)) < NGRAM_SIZE`), `compute_ngram_overlap` returns exactly `0.0`, by definition,
never a division by zero. The formula is deliberately a **containment** ratio (normalized by the
span's own n-gram count, not a symmetric measure like Jaccard) since a span is typically far shorter
than the block it may be grounded in; a symmetric measure would systematically under-score a short,
fully-grounded span against a long block. This also makes the score explicitly input-order-sensitive:
`compute_ngram_overlap(a, b)` and `compute_ngram_overlap(b, a)` are not generally equal.

**Threshold comparison — the sole authoritative rule, stated nowhere else in this document.** A
`Citation` is attached for a given `(span, block)` pair **if and only if**
`compute_ngram_overlap(span.text, block.text) >= citation_match_threshold` — a closed, non-strict
comparison: a score exactly equal to the threshold counts as a match. Every other mention of "the
threshold" anywhere in this document refers back to this exact rule by name and never restates the
comparison operator itself, so there is exactly one place a future edit could ever introduce a
`>=`/`>` inconsistency, and this is that place.

**Matching, per span.** `match_span_to_blocks(span, context_blocks, citation_match_threshold)` computes
`compute_ngram_overlap` between `span.text` and every `ContextBlock.text` in `context_blocks`,
independently and without any cross-block interaction, and returns one `Citation` for every block
satisfying the Threshold comparison rule immediately above — this may be zero, one, or many; no
maximum-citations-per-span cap is imposed
by this design (Known Limitations, Accepted Tradeoffs). `context_blocks` is guaranteed by Stage 10's
own dedup-by-`chunk_id` invariant (carried forward unchanged through Stage 11) to contain no two
blocks sharing a `chunk_id` — Stage 14 relies on this inherited guarantee rather than re-implementing
its own block-level deduplication, and `validate_cited_response` re-checks it defensively as
`DUPLICATE_CITATION_IN_SPAN` (Validation §3) in case that upstream guarantee is ever violated.

**Deterministic ordering.** When more than one block qualifies for one span, its citations are ordered
by descending `match_score`; ties are broken by ascending `chunk_id`. Because `chunk_id` is guaranteed
unique across `context_blocks` (the same inherited guarantee above), this pair of keys is always a
strict total order — there is never a residual, unresolved tie. This is the same deterministic
tie-break convention Stage 10's own `merge_and_rank` already established.

A span scoring below threshold against every block is left with `citations == []` — an expected,
non-error outcome (Design Decisions #9), never itself an internal invariant violation.

## Design Decisions

1. **Three inputs are required, not one.** `LLMResponse` alone cannot supply what Stage 14 needs: the
   structured, addressable `ContextBlock`s it cites exist only on `ContextPackage`, since `PromptPackage`
   already flattened them into an opaque `context_text` string at Stage 12 (`PromptPackage` schema —
   `context_text` is rendered prose, not a block array). `PromptPackage` is still required as the
   id-bridge: `LLMResponse` carries only `prompt_package_id`, never `context_package_id` directly, so
   `PromptPackage.context_package_id` is the only link connecting an `LLMResponse` to the
   `ContextPackage` it was ultimately generated from. All three objects are already held by any caller
   orchestrating one query through Stages 10–13 in sequence, so requiring all three imposes no new
   burden — it only makes an existing implicit dependency explicit. This is the only way to establish
   the link at all: no alternative exists that keeps `PromptPackage` out of Stage 14's inputs, given
   `LLMResponse`'s own frozen schema.
2. **Citation matching is fixed lexical n-gram overlap, never a second LLM call or an embedding
   similarity search.** A second LLM call is barred outright by Non-Responsibilities and Principle 5. A
   fresh Stage-8-style embedding call for each span was considered and rejected: it would introduce a
   real network call, cost, and latency into what is meant to be a lightweight, fully local post-process,
   and "does this span's surface text resemble this block's surface text" (a lexical question, answerable
   deterministically) is a materially different, and appropriately narrower, question than "is this claim
   true" (a semantic/factual question, correctly deferred to Stage 15).
3. **Segmentation is a fixed punctuation-boundary rule, never an NLP sentence tokenizer** (the full,
   exact algorithm is specified in Response Segmentation). Consistent with the same "no tokenizer or
   model named anywhere in this project" precedent Stage 7, 11, and 12
   each already established for their own text-processing heuristics.
4. **No `SKIPPED`/`FAIL` short-circuit branch, mirroring Stage 12's own Pipeline, not Stage 11's.**
   Stage 13 already guarantees `status` in `{SKIPPED, FAIL}` implies `response_text == ""`; an empty
   string already segments to `spans == []` through the ordinary `segment_response_text` path with no
   special case needed — the identical "empty input flows naturally through the uniform pipeline" pattern
   Stage 12 established one stage upstream for its own `context_text` rendering.
5. **`status` is a pure passthrough of `LLMResponse.status` — Stage 14 reverts to the Stage 10–12
   convention, not Stage 13's own deliberate departure from it.** Stage 13 broke the passthrough
   convention because its own success genuinely depended on a live network operation it performed
   itself. Stage 14 performs no external call of any kind; it can only ever attach, or fail to attach, a
   citation to text that already exists — exactly the same "can only ever lose information relative to
   upstream, never independently fail on its own terms" situation Stage 10, 11, and 12 were each in. Its
   own findings (`LOW_CITATION_COVERAGE`, `ZERO_CITATIONS`) are therefore always WARNING-severity and
   never alter `status`, restoring the convention Stage 13 was the sole, explicitly-named exception to.
6. **`cited_response_id` is a deterministic hash over identity-determining inputs, never over
   `response_text` or any computed span/citation content.** Matching Stage 9/11/12's own "hash the
   identity-determining inputs, not the derived payload" pattern:
   ```python
   hash_input = {
       "llm_response_id": llm_response["llm_response_id"],
       "context_package_id": context_package["context_package_id"],
       "citation_match_threshold": citation_match_threshold,
       "ngram_size": NGRAM_SIZE
   }
   cited_response_id = sha256(canonical_json(hash_input)).hexdigest()
   ```
   `spans`/`citations` are deliberately **not** hashed: given the hashed inputs plus the frozen matching
   algorithm, they are fully determined — hashing them would be redundant, not additionally
   identity-bearing (`llm_response_id` already stands in for `response_text` itself, exactly as
   `context_package_id` already stands in for the full `context_blocks` array).
7. **Case-folding inside `compute_ngram_overlap` does not conflict with Stage 10's own "no lowercasing,
   ever" rule.** Stage 10 Design Decision #11 scopes that rule specifically to *query preprocessing*
   feeding an *embedding call* — semantic embeddings are largely case-invariant already, so lowercasing
   there would have been a needless, unprincipled deviation. Here, case-folding is an internal
   implementation detail of a specific, local, deterministic *lexical string-matching* algorithm, whose
   folded copy never escapes `compute_ngram_overlap` itself — every field this stage actually outputs
   (`response_text`, `span.text`, every citation's referenced block) preserves its original casing
   unconditionally. The two rules govern different mechanisms for different purposes and do not collide.
8. **`response_text` is preserved byte-for-byte; only annotated, never modified.** Direct extension of
   the "never truncate, modify, or re-normalize source text" guarantee every stage from Stage 10 onward
   (chunk `text`, then `context_text`, then `assembled_prompt`) has already carried forward.
9. **An uncited span is not an error, a WARNING, or evidence of anything by itself.** A generated answer
   legitimately contains connective, transitional, or synthesis text with no single source passage to
   point to — that is expected, ordinary output, not a defect. Only a *low or zero* overall
   `citation_coverage` across the whole response produces a package-level WARNING (Validation), and even
   that is informational, never a status driver — judging whether any specific uncited span constitutes
   a problem (e.g. a hallucinated claim) is explicitly Stage 15's job, working from this stage's own
   span/citation structure, never Stage 14's.
10. **Stage 14 defines its own `validate_llm_response()`, `validate_prompt_package()`, and
    `validate_context_package()`, deliberately reusing all three upstream stages' function names.**
    Different module, different responsibility in every case: each one structurally validates a
    *received* object as Stage 14's own input gate, never calling or duplicating the identically-named
    internal self-check each upstream stage already runs on its own output before returning it — the
    same naming-reuse pattern Stage 11 established for Stage 10's name, Stage 12 for Stage 11's, and
    Stage 13 for Stage 12's, now applied three times over since Stage 14 is the first stage with three
    upstream inputs to validate.
11. **A mismatched id chain across the three inputs raises, rather than silently proceeding.** If
    `llm_response.prompt_package_id != prompt_package.prompt_package_id`, or
    `prompt_package.context_package_id != context_package.context_package_id`, the three inputs do not
    actually describe one coherent request — this is a caller error (the caller assembled the wrong
    triad of objects), not a normal degraded-but-expected outcome, so it is raised at the input boundary
    (`ID_CHAIN_MISMATCH`) rather than surfaced as a package-level finding.
12. **`CitedResponse` is fully in-memory, never persisted, matching Stage 10–13's own posture exactly.**
    The fifth consecutive zero-artifact, zero-manifest-interaction stage in this pipeline's query-time
    path; a future Stage 15 is expected to consume the returned object directly in-process.
13. **Input validation checks only the fields Stage 14 actually reads, never full upstream-schema
    validation.** `validate_prompt_package` inspects exactly `prompt_package_id` and
    `context_package_id`; no other `PromptPackage` field (`system_prompt`, `user_prompt`,
    `context_text`, `assembled_prompt`, findings, budget stats) is inspected, referenced, or assumed
    present. `validate_context_package` inspects exactly `context_package_id` and `context_blocks`
    (each block's `context_block_id`/`chunk_id`/`doc_id`/`text`). `validate_llm_response` inspects
    exactly `llm_response_id`, `response_text`, `status`, `prompt_package_id`, and `findings`. This
    keeps the documented minimal coupling (Inputs, Design Decisions #1) honest at the validation layer
    too — a broader check would silently imply Stage 14 depends on fields it never actually reads.
14. **The no-duplicate-`chunk_id` guarantee on `context_blocks` is inherited, not re-derived, but is
    re-checked defensively — and "duplicate" is defined precisely as same `context_block_id`, never
    text equality or object identity.** Stage 10 already deduplicates search results by `chunk_id`
    before Stage 11 ever sees them, and Stage 11 never reintroduces a duplicate; Stage 14 relies on
    this rather than performing its own block-level dedup pass. `validate_cited_response`'s
    `DUPLICATE_CITATION_IN_SPAN` check (Validation §3) compares `Citation.context_block_id` — the
    cleanest available definition, since it is the literal foreign key a `Citation` carries, and is
    deterministically 1:1 with `chunk_id` by Stage 11's own `context_block_id` construction — never two
    blocks' `text` happening to match (irrelevant here — two *different* blocks with coincidentally
    identical text are not "duplicates" under this check, only two citations pointing at the *same*
    block are) and never comparing `Citation` objects themselves (which would be trivially always
    distinct instances). This exists purely as a defensive safety net against the upstream guarantee
    ever being silently violated — the same "does not blindly trust the upstream stage's report"
    posture Stage 9 already established for its own inputs.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md` §4's
Critical/Recoverable document-quarantine model, since Stage 14 has no document to quarantine and no
persisted artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10 through Stage 13
each already gave for their own Validation sections).

**1. Input validation codes** — raised, never returned as part of any `CitedResponse`:

| Code | Raised as | Trigger |
|---|---|---|
| `LLM_RESPONSE_MALFORMED` | `CitationExtractionInputError` | the received `LLMResponse` is missing a required key or has a wrong-typed value; no `CitedResponse` is produced at all |
| `PROMPT_PACKAGE_MALFORMED` | `CitationExtractionInputError` | the received `PromptPackage` is missing a required key or has a wrong-typed value; no `CitedResponse` is produced at all |
| `CONTEXT_PACKAGE_MALFORMED` | `CitationExtractionInputError` | the received `ContextPackage` is missing a required key or has a wrong-typed value; no `CitedResponse` is produced at all |
| `ID_CHAIN_MISMATCH` | `CitationExtractionInputError` | `llm_response.prompt_package_id != prompt_package.prompt_package_id`, or `prompt_package.context_package_id != context_package.context_package_id` (Design Decisions #11); no `CitedResponse` is produced at all |

**2. Package-level findings** — recorded in `CitedResponse.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `ZERO_CITATIONS` | WARNING | package | `span_count > 0` and `citation_coverage == 0.0`; never alters `status` |
| `LOW_CITATION_COVERAGE` | WARNING | package | `0.0 < citation_coverage < LOW_CITATION_COVERAGE_THRESHOLD`; never alters `status` |
| `RESPONSE_EMPTY` | WARNING | package | `span_count == 0` (an empty `response_text`, e.g. because `LLMResponse.status` was `SKIPPED`/`FAIL`, or a `PASS` response that itself carried `LLM_RESPONSE_EMPTY`); never alters `status` |

`status` truth table (pure passthrough, no additional Stage 14 condition):

| Condition | `status` |
|---|---|
| `LLMResponse.status == "SKIPPED"` | `SKIPPED` |
| `LLMResponse.status == "FAIL"` | `FAIL` |
| `LLMResponse.status == "PARTIAL"` | `PARTIAL` |
| `LLMResponse.status == "PASS"` | `PASS` |

**3. Internal invariant codes** — raised by `validate_cited_response()`, run unconditionally on the
assembled response before it is ever returned; never returned as part of any `CitedResponse`:

| Code | Trigger |
|---|---|
| `SPAN_TEXT_MISMATCH` | concatenating every `span.text` in order does not exactly equal `response_text` |
| `SPAN_OFFSET_DISCONTINUOUS` | `spans[i].end_offset != spans[i+1].start_offset` for any `i`, or `spans[0].start_offset != 0`, or the last span's `end_offset != len(response_text)` |
| `CITATION_REFERENCES_UNKNOWN_BLOCK` | a `Citation.context_block_id` does not correspond to any block in `context_package["context_blocks"]` |
| `DUPLICATE_CITATION_IN_SPAN` | two `Citation`s attached to the same `ResponseSpan` share the same `context_block_id` — the canonical duplicate-identity key, since `Citation.context_block_id` is the field actually compared (never text equality, and never the bare `Citation` object identity). `context_block_id` is deterministically derived from `chunk_id` (Stage 11's own `f"{context_package_id}_{chunk_id}"` scheme), so two Citations sharing a `context_block_id` always share a `chunk_id` too — the check is stated in terms of `context_block_id` because that is the literal field compared. |
| `COVERAGE_COMPUTATION_MISMATCH` | `citation_coverage != (cited_span_count / span_count if span_count > 0 else 1.0)`, or `cited_span_count + uncited_span_count != span_count` |
| `LLM_RESPONSE_ID_MISMATCH` | `response.llm_response_id != input LLMResponse.llm_response_id`, or `response.context_package_id != input ContextPackage.context_package_id` |

Any of these six raises `CitationExtractionInternalError` rather than being returned as a malformed
`CitedResponse` — the same fail-loud posture as Stage 10 through Stage 13's own internal-invariant
exceptions, and never expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage14_citation_extraction"`, `doc_id: null` always —
entries are request-scoped, not document-scoped). New codes this stage adds:
`WARNING_ZERO_CITATIONS`, `WARNING_LOW_CITATION_COVERAGE`, `WARNING_RESPONSE_EMPTY`. No new `FATAL_*`
code — Stage 14 never sets a manifest `error_code`, since it never touches the manifest at all (see
Manifest Interaction).

## Manifest Interaction

None. Stage 14 never opens, reads, or writes `manifest.json` — the fourth stage in this pipeline with
zero manifest interaction of any kind, extending Stage 11 through Stage 13's own posture: every field
it needs already arrived on its three in-memory inputs.

## Artifact Interaction

None. Stage 14 performs zero file reads and zero file writes. Its only inputs are in-memory
(`LLMResponse`, `PromptPackage`, `ContextPackage`); its only output is an in-memory `CitedResponse`. No
atomicity concern exists because there is nothing to persist and nothing to read from disk at all —
unlike Stage 13, Stage 14 performs no network call of any kind either.

## Directory Structure

None added. Stage 14 introduces no new artifact directory — there is no artifact.

## Determinism

Stage 14's own transform is fully deterministic — a pure function of its three inputs, with no external
call of any kind. This is a materially different situation from Stage 13's own explicit exception: Stage
13 could not promise reproducible *content* because it performed a live sampling call; Stage 14 performs
no such call and processes whatever `response_text` it is handed with total determinism, regardless of
whether that `response_text` itself varied between two upstream calls to Stage 13.

- **Stable segmentation.** `segment_response_text` is a pure function of `response_text` alone, using
  the fixed, fully-specified algorithm in Response Segmentation — identical text always yields
  identical spans.
- **Stable matching.** `compute_ngram_overlap` and `match_span_to_blocks` are pure functions of their own
  arguments and the fixed `NGRAM_SIZE`/`citation_match_threshold` — no randomness, no external state.
- **Stable tie-break.** Multiple qualifying citations on one span are always ordered identically:
  descending `match_score`, ascending `chunk_id` on ties.
- **Stable `cited_response_id`.** Deterministic sha256 over exactly `llm_response_id`,
  `context_package_id`, `citation_match_threshold`, and `NGRAM_SIZE` — no timestamp/UUID/random input.
- **Stable output.** Identical `(LLMResponse, PromptPackage, ContextPackage, citation_match_threshold)`
  produces a byte-identical `CitedResponse` (`extracted_at` excluded), across repeated calls and process
  restarts — including the case where the same `response_text` is replayed through Stage 14 twice, even
  though that same `response_text` might never recur from a live Stage 13 call.

## Read-Only Guarantees

Stage 14 never modifies `manifest.json`, any `LLMResponse`, `PromptPackage`, `ContextPackage`,
`RetrievalResult`, any chunk, any metadata, any vector index, or any embedding. No upstream artifact or
in-memory object is ever mutated; no write capability, and no network call of any kind, exists anywhere
in this design.

## Failure Handling

- **A malformed `LLMResponse`, `PromptPackage`, or `ContextPackage`** (missing/wrong-typed required key)
  — `CitationExtractionInputError` (`LLM_RESPONSE_MALFORMED` / `PROMPT_PACKAGE_MALFORMED` /
  `CONTEXT_PACKAGE_MALFORMED`) raised immediately; no `CitedResponse` returned.
- **A mismatched id chain across the three inputs** — `CitationExtractionInputError`
  (`ID_CHAIN_MISMATCH`) raised immediately; no `CitedResponse` returned.
- **`LLMResponse.status` in `{SKIPPED, FAIL}`** — `response_text == ""` is already guaranteed by Stage
  13's own contract; `segment_response_text` naturally produces `spans == []`; `CitedResponse.status`
  passes through as `SKIPPED`/`FAIL`; `RESPONSE_EMPTY` WARNING recorded; no special-cased branch is
  needed (Design Decisions #4).
- **`LLMResponse.status == "PARTIAL"`** — citation extraction proceeds normally over whatever
  (truncated) `response_text` is present; `CitedResponse.status` stays `PARTIAL`; `LLMResponse.findings`
  carried forward verbatim into `llm_findings`.
- **A successful, non-empty response with zero qualifying citations on every span** —
  `citation_coverage == 0.0`; `ZERO_CITATIONS` WARNING; `status` unaffected — this is a legitimate,
  informative outcome (e.g. a purely synthesized answer), never treated as an error.
- **A single span scores below threshold against every `ContextBlock`** — `citations == []` for that
  span alone. An empty citation list is a valid successful Stage 14 outcome and does not indicate
  failure: it simply means no evidence above threshold was found for that one span, not itself a
  WARNING (Design Decisions #9). This is distinct from the package-level case above: only the
  *aggregate* `citation_coverage` across the whole response can trigger
  `ZERO_CITATIONS`/`LOW_CITATION_COVERAGE` (Validation §2); a single uncited span among otherwise-cited
  spans triggers neither. Whether an empty or sparse citation list reflects a genuine problem with the
  answer is a judgment explicitly reserved for Stage 15, never decided here.
- **`citation_match_threshold` omitted, or below/above a sane range** — defaulted to
  `DEFAULT_CITATION_MATCH_THRESHOLD`, clamped to `[0.0, 1.0]` (mirrors the caller-supplied-with-default
  convention Stage 11/12/13 each already established for their own tunables).
- **A genuine Stage 14 bug** (one of the six named internal invariant codes in Validation §3) —
  `CitationExtractionInternalError` raised, not returned as a malformed `CitedResponse`.

## Configuration

`citation_match_threshold` is per-request configuration, never defaulted from any global or environment
state except via the named `DEFAULT_CITATION_MATCH_THRESHOLD` constant when the caller omits it
entirely — the same per-request convention Stage 11 (`context_budget_tokens`), Stage 12
(`prompt_budget_tokens`/`template_version`), and Stage 13 (`execution_config`) each already established
for their own tunables. `NGRAM_SIZE`, `SPAN_TERMINATORS`, and `SPAN_TRAILING_CLOSERS` are fixed constants, not per-request
configuration — varying the segmentation or matching *algorithm* itself per call would break the
"identical input always yields identical output" determinism guarantee across calls using different
settings, so only the pass/fail threshold on an otherwise-fixed algorithm is exposed. Stage 14 consumes
no adapter factories of any kind; it never touches `ProviderAdapter`, `IndexAdapter`, or `LLMAdapter`.

## Concurrency

Fully safe under concurrent calls. Stage 14 performs zero writes, holds no shared mutable state, and
makes no network or file-system call of any kind — `extract_citations()` is a pure function of its own
arguments; any number of calls, including against identical input, may run simultaneously with no
locking and no race condition.

## Security Considerations

- **Untrusted model output, inherited.** `response_text` remains opaque, model-generated content — Stage
  14 performs no interpretation, execution, or sanitization of it beyond segmenting and scoring its
  surface text; this is the same "response_text is potentially adversarial input to whatever consumes it
  next" risk Stage 13 already accepted (Stage 13's own Design Decisions #11 — distinct from Stage 14's
  own #11 above, which concerns `ID_CHAIN_MISMATCH`), passed through unchanged. Stage 14's
  citation matching operates purely on string content, never treating any part of `response_text` or any
  `ContextBlock.text` as executable or interpretable.
- **No new I/O surface.** Stage 14 opens no file, calls no network endpoint, and touches no credential of
  any kind — a strictly narrower surface than every stage from Stage 8 onward that performs a real
  external call.
- **No write capability anywhere in this design** — eliminates an entire class of injection/corruption
  risk against this pipeline's own artifacts and in-memory objects by construction, not by runtime
  validation.

## Public Function Contracts

- `validate_llm_response(response: LLMResponse) -> None` — Stage 14's own structural input check;
  inspects exactly `llm_response_id`, `response_text`, `status`, `prompt_package_id`, and `findings`
  for presence and correct type — no other `LLMResponse` field is inspected. Raises
  `CitationExtractionInputError` (code `LLM_RESPONSE_MALFORMED`) on violation. Distinct from, and never
  calling, Stage 13's own internal function of the same name.
- `validate_prompt_package(package: PromptPackage) -> None` — Stage 14's own structural input check;
  inspects exactly `prompt_package_id` and `context_package_id` — no other `PromptPackage` field is
  inspected (Design Decisions #13). Raises `CitationExtractionInputError` (code
  `PROMPT_PACKAGE_MALFORMED`). Distinct from, and never calling, Stage 12's own function of the same
  name.
- `validate_context_package(package: ContextPackage) -> None` — Stage 14's own structural input check;
  inspects exactly `context_package_id` and `context_blocks` (each block's `context_block_id`/
  `chunk_id`/`doc_id`/`text`). Raises `CitationExtractionInputError` (code `CONTEXT_PACKAGE_MALFORMED`).
  Distinct from, and never calling, Stage 11's own function of the same name.
- `verify_id_chain(llm_response: LLMResponse, prompt_package: PromptPackage, context_package:
  ContextPackage) -> None` — raises `CitationExtractionInputError` (code `ID_CHAIN_MISMATCH`) if the
  three objects' linking ids disagree (Design Decisions #11).
- `segment_response_text(response_text: str) -> List[ResponseSpan]` — fixed punctuation-boundary split
  (Response Segmentation); pure function of `response_text` alone; total (always succeeds, including
  on an empty string, which returns `[]`).
- `compute_ngram_overlap(span_text: str, block_text: str) -> float` — fixed character-n-gram containment
  score (Citation Matching Strategy); pure function of its two arguments and the fixed `NGRAM_SIZE`;
  returns `0.0` when `span_text` produces zero n-grams.
- `match_span_to_blocks(span: ResponseSpan, context_blocks: List[ContextBlock],
  citation_match_threshold: float) -> List[Citation]` — returns every qualifying citation for one span,
  ordered by descending `match_score` then ascending `chunk_id`; may return `[]`.
- `assemble_cited_response(llm_response: LLMResponse, prompt_package: PromptPackage, context_package:
  ContextPackage, spans: List[ResponseSpan], citation_match_threshold: float) -> CitedResponse` — wraps
  spans + coverage stats + inherited `status`/findings into the final package; computes
  `cited_response_id`.
- `validate_cited_response(response: CitedResponse, context_package: ContextPackage,
  llm_response: LLMResponse) -> None` — internal invariant self-check; raises
  `CitationExtractionInternalError` (one of the six named codes in Validation §3) on violation.
  The two additional parameters are required by the invariants themselves: `CITATION_REFERENCES_UNKNOWN_BLOCK`
  needs `context_package["context_blocks"]` to build the set of valid block ids (that set is not
  stored on `CitedResponse`), and `LLM_RESPONSE_ID_MISMATCH` needs the original
  `llm_response["llm_response_id"]` and `context_package["context_package_id"]` to compare against
  the copies carried on the assembled response. No alternative signature can implement both invariants
  from `CitedResponse` alone.
- `extract_citations(llm_response: LLMResponse, prompt_package: PromptPackage, context_package:
  ContextPackage, citation_match_threshold: Optional[float] = None) -> CitedResponse` — the sole public
  entrypoint; orchestrates the full pipeline; never reads or writes any artifact, the manifest, or any
  network endpoint.

## Constants

```python
CITATION_PIPELINE_VERSION = "1.0.0"
SPAN_TERMINATORS = ('.', '!', '?')                 # characters that can begin a boundary run
SPAN_TRAILING_CLOSERS = ('"', "'", ')', ']', '”', '’', '»')  # extend, never begin, a run
NGRAM_SIZE = 5                                     # character n-gram size for overlap matching
DEFAULT_CITATION_MATCH_THRESHOLD = 0.6             # containment-score cutoff for attaching a citation
LOW_CITATION_COVERAGE_THRESHOLD = 0.5              # below this (and above 0.0), LOW_CITATION_COVERAGE fires
```

## Known Limitations

- **Lexical overlap is a proxy for attribution, never a semantic entailment check.** A span can score
  above threshold against a block that happens to share surface vocabulary without actually being
  supported by it (a false-positive citation), and can score below threshold against a block that truly
  supports it but is phrased very differently (a false-negative, uncited span). Judging true semantic
  groundedness is explicitly Stage 15's job, not this stage's.
- **Segmentation is not linguistically aware — a deliberate application of Principle 5 (deterministic
  before probabilistic), not an oversight.** The fully-specified algorithm (Response Segmentation)
  treats every active boundary identically regardless of meaning — an abbreviation like "Dr. Smith" is
  split into two spans exactly as a genuine sentence end would be, since "Dr." followed by a space
  satisfies the same active-boundary rule; there is no abbreviation list, locale table, or exception
  mechanism of any kind. A probabilistic or list-driven abbreviation detector was deliberately rejected
  in favor of this fixed, exact, dependency-free rule, even at the cost of this kind of linguistic
  imprecision (Design Decisions #3).
- **A short span (under `NGRAM_SIZE` characters) can never be cited**, by construction — an honest
  consequence of a fixed n-gram floor, not a bug; revisit `NGRAM_SIZE` only via an explicit constant
  change, never a per-call override (Configuration).
- **Multiple qualifying citations on one span are all retained, uncapped** — a span overlapping several
  near-duplicate blocks (e.g. two indexes over the same corpus, per Stage 10's own accepted multi-index
  overlap limitation) can accumulate several citations; no maximum-citations-per-span cap is imposed in
  this design.
- **Case-folding inside `compute_ngram_overlap` is English/Unicode-general but not diacritic- or
  script-aware beyond NFC normalization** — a token differing only by a diacritic normalization form
  Unicode NFC doesn't collapse could under-match; accepted as a v1 scope limit.

## Accepted Tradeoffs

- **Deterministic lexical matching over a second LLM call or an embedding search.** Cheaper, fully local,
  fully auditable, and consistent with this project's "deterministic before probabilistic" principle —
  accepts a strictly narrower, surface-level notion of "citation" than a semantic-similarity or
  LLM-judged approach would offer.
- **Fixed, non-per-request `NGRAM_SIZE` and segmentation pattern.** Simpler to reason about and keeps the
  determinism guarantee airtight across calls; accepts that tuning match sensitivity requires an explicit
  constant/architecture change, not a runtime knob, beyond the one threshold that is exposed.
- **No cap on citations per span.** Simpler; accepts a span with several overlapping/duplicate source
  blocks reporting all of them rather than an arbitrary top-N.
- **`CitedResponse` is fully in-memory, no persisted artifact.** Matches Stage 10 through Stage 13's own
  precedent — no audit trail exists unless a caller persists it independently.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not this
document.

- A malformed `LLMResponse`, `PromptPackage`, or `ContextPackage` is rejected deterministically, every
  time, without producing any `CitedResponse`.
- A mismatched id chain across the three inputs is rejected deterministically, every time, without
  producing any `CitedResponse`.
- `LLMResponse.status` in `{SKIPPED, FAIL}` always produces `CitedResponse.status` matching exactly, with
  `spans == []`, `span_count == 0`, and `citation_coverage == 1.0` (vacuous), without any special-cased
  branch in the implementation.
- Concatenating every `span.text` in order always exactly equals `response_text`, for every non-empty
  input; span offsets are always contiguous, starting at `0` and ending at `len(response_text)`.
- `compute_ngram_overlap` is symmetric-input-order-sensitive by design (containment, not Jaccard) —
  verified by a case where swapping `span_text`/`block_text` changes the score.
- A span shorter than `NGRAM_SIZE` characters always produces zero citations, deterministically.
- Every citation attached to a span has `match_score >= citation_match_threshold`, and citations on one
  span are always ordered by descending `match_score`, ties broken by ascending `chunk_id`.
- `cited_span_count + uncited_span_count == span_count` always; `citation_coverage` always equals the
  documented formula exactly.
- No two `Citation`s attached to the same `ResponseSpan` ever reference the same `chunk_id` —
  guaranteed by the inherited upstream invariant (Design Decisions #14) and independently re-verified
  by `DUPLICATE_CITATION_IN_SPAN`.
- Every one of the six internal invariant codes (`SPAN_TEXT_MISMATCH`, `SPAN_OFFSET_DISCONTINUOUS`,
  `CITATION_REFERENCES_UNKNOWN_BLOCK`, `DUPLICATE_CITATION_IN_SPAN`, `COVERAGE_COMPUTATION_MISMATCH`,
  `LLM_RESPONSE_ID_MISMATCH`) fires under its documented condition and only that condition.
- Determinism: identical `(LLMResponse, PromptPackage, ContextPackage, citation_match_threshold)`
  produces a byte-identical `CitedResponse` (`extracted_at` excluded), across repeated calls and process
  restarts.
- Immutability: none of the three input objects is ever mutated by any Stage 14 function, regardless of
  outcome.
- No file is ever read or written, and no network call is ever made, by any Stage 14 function, under any
  input or outcome.

## Real Corpus Verification

Against a real `LLMResponse`/`PromptPackage`/`ContextPackage` triad produced by the live Stage 10 → 11 →
12 → 13 chain: a representative successful response segments into a plausible number of spans (spot-
checked by eye against `response_text`); at least one span is confirmed cited against the real
`ContextBlock` its content was visibly drawn from, with `match_score` reported and above the configured
threshold; a deliberately unrelated `response_text` (e.g. constructed by a stub adapter returning
generic filler text unrelated to the retrieved corpus) produces `citation_coverage == 0.0` and a
`ZERO_CITATIONS` finding, without raising; two identical runs of `extract_citations()` over the same real
triad and threshold produce byte-identical `CitedResponse`s (`extracted_at` excluded), including every
span's offsets and every citation's `match_score`; every returned citation's `context_block_id`/`chunk_id`
is confirmed to resolve back to a real block present in the source `ContextPackage.context_blocks`.

**Determinism, explicitly:** unlike Stage 13, this section states the ordinary, full byte-identical
guarantee without qualification — Stage 14 performs no live call of its own, so two calls sharing an
identical `response_text` (even if that `response_text` itself only arose once, non-reproducibly, from a
real Stage 13 invocation) are guaranteed to produce byte-identical citation output when replayed.

Immutability: the three input objects, and every real upstream artifact (`manifest.json`, every
`chunks.json`, `embeddings.parquet`, `metadata.json`, everything under `vector_index/`, every on-disk
prompt template file), are confirmed byte-identical before and after the call — Stage 14 opens none of
them directly.

## Future Stage Boundaries

Stage 15+ (not designed here) owns everything Stage 14 deliberately excludes: groundedness or
hallucination validation of cited (and uncited) spans, answer-quality or retrieval-quality evaluation,
response caching or deduplication, response streaming to a caller or UI, tool/function calling,
conversation memory or multi-turn orchestration, agent planning, and any network-facing API or UI serving
a response to an end user. Stage 14 hands a `CitedResponse` back in memory; how a caller judges the
truth of a citation, scores the answer's overall quality, formats citations for display, or builds a
multi-turn conversation on top of it is entirely out of this design's scope.

## Verification (of this plan)

This is a design-only task — no code is written. Verification is a read-through against this pipeline's
own established conventions and the Stage Dependency Map / Frozen Pipeline Boundary roadmap this design
pass was scoped from:

- Every section present in Stage 9 through Stage 13's own docs is present here (Overview through Future
  Stage Boundaries), matching their structure, prose density, and no-implementation-notes /
  no-review-diary style throughout.
- The Stage Dependency Map's own description of Stage 14 ("Maps spans in `LLMResponse.response_text`
  back to source `ContextBlock`s from Stage 12's `PromptPackage`") is refined here with the accurate
  detail that the structured blocks are actually sourced from `ContextPackage`, with `PromptPackage`
  serving only as the id-bridge — a correction made during design, not a deviation from the roadmap's own
  intent.
- Frozen Pipeline Boundary compliance: nothing in this document modifies any schema, public function
  contract, validation semantics, determinism guarantee, artifact format, or stated responsibility of any
  Stage 0–13 document; every field and function this design reads from `LLMResponse`, `PromptPackage`,
  and `ContextPackage` is read, never altered.
- Every function this document names is one of a complete, closed set (`validate_llm_response`,
  `validate_prompt_package`, `validate_context_package`, `verify_id_chain`, `segment_response_text`,
  `compute_ngram_overlap`, `match_span_to_blocks`, `assemble_cited_response`, `validate_cited_response`)
  plus the sole entrypoint `extract_citations`.
- Determinism is stated without qualification (unlike Stage 13), since Stage 14 performs no external
  call of its own — verified explicitly in both Determinism and Real Corpus Verification.
- No functionality reserved for Stage 15+ (groundedness validation, evaluation, caching, streaming,
  tools, memory, agent planning, API/UI) appears anywhere in this design's Responsibilities, Pipeline, or
  Public Function Contracts.

Once approved, this document is Stage 14's frozen architecture — matching Stage 9 through Stage 13's own
"approved, then saved verbatim" precedent for this file.
