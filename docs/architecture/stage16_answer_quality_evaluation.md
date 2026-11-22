# Stage 16 — Answer Quality Evaluation

Stages 0–15 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 16 turns Stage 15's `GroundednessReport` into an `AnswerQualityReport`: a deterministic,
explainable set of response-level quality metrics — lexical, structural, citation-coverage, and
groundedness-derived — culminating in one composite `answer_quality_score`. It performs no semantic
judgment, no fact-checking, no second LLM call, and no re-verification of any individual citation
(that remains exclusively Stage 15's own, frozen job); it is a pure, in-memory aggregation and scoring
transform over already-final upstream output. `evaluate_answer_quality(groundedness_report)` is the
sole public entrypoint.

## Scope

Stage 16 answers exactly one question — given a `GroundednessReport`, how good is the completed answer,
by a fixed set of deterministic, mathematically-defined, non-semantic metrics — and stops there. It
never re-verifies a citation's own grounding (Stage 15's job); never re-extracts or re-attaches a
citation (Stage 14's job); never judges factual correctness, truthfulness, coherence, fluency, or
relevance to the original query (structurally impossible in any case — `query` is not present anywhere
on `GroundednessReport`, Stage 16's sole input); never invokes an LLM or computes an embedding; never
rewrites, corrects, or regenerates any part of the answer; never decides what to do about a low-scoring
result. Those boundaries are restated in Non-Responsibilities and Future Stage Boundaries.

## Responsibilities

Stage 16 shall: receive a `GroundednessReport`; structurally validate it before use (schema
well-formedness only — inspecting exactly the fields Stage 16 reads, never groundedness correctness or
answer truthfulness, both already Stage 15's own settled concern); compute a fixed set of deterministic
lexical and structural metrics from `response_text` and `span_count`; compute `citation_presence_ratio`
from `span_count`/`unsupported_span_count`; compute one composite `answer_quality_score` from
`groundedness_score` and `citation_presence_ratio` under fixed, named weights; classify the result
against fixed, named advisory thresholds; preserve `status` as a pure passthrough; and assemble an
`AnswerQualityReport` whose own internal invariants are self-checked before it is ever returned.

## Non-Responsibilities

Stage 16 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: semantic verification, factual verification, contradiction detection, or hallucination
detection of any kind (all require a model-based or embedding-based judgment, categorically forbidden
by Principle 5); computing or calling any embedding, vector search, or reranking mechanism; any LLM
call, for evaluation, explanation, or scoring; rewriting, correcting, or regenerating `response_text` or
any part of the answer; constructing a prompt of any kind (Stage 12's frozen job); extracting or
re-attaching a citation (Stage 14's frozen job); re-verifying an individual citation's own groundedness
(Stage 15's frozen job, and the exact boundary Design Decisions #8 restates); response caching or
deduplication; any network call, of any kind; serving a network-facing API; conversation memory or
multi-turn orchestration; agent planning; tool or function calling. Every one of these remains reserved
for a later, separate design, or is permanently out of this pipeline's scope under Principle 5 (Future
Stage Boundaries).

## Inputs

Exactly one required input, entirely in-memory:

- `GroundednessReport` (Stage 15's own output schema, unchanged) — the sole source of every field Stage
  16 needs: `response_text` (lexical/structural metrics), `span_count` and `unsupported_span_count`
  (citation-coverage and unsupported-span statistics), `groundedness_score` (groundedness statistics,
  read but never re-derived — see Design Decisions #6), `status` (passthrough), `findings` (carried
  forward as `groundedness_findings`), and the full identity chain (`groundedness_report_id`,
  `cited_response_id`, `llm_response_id`, `prompt_package_id`, `context_package_id`).

No other input is read. `CitedResponse`, `ContextPackage`, `PromptPackage`, `LLMResponse`,
`RetrievalResult`, `manifest.json`, `chunks.json`, `metadata.json`, vector indexes, and embeddings are
never opened — every field a response-level quality metric needs already exists, verbatim or as an
already-computed aggregate, on `GroundednessReport` (Design Decisions #1). No PDF is ever reopened; no
chunk is ever regenerated; no vector search, embedding call, or LLM call is ever performed here.

## Outputs

None persisted. Stage 16 produces zero artifacts and writes to no file — the seventh consecutive fully
read-only, zero-manifest-interaction stage in this pipeline's query-time path, extending the posture
Stage 10 through Stage 15 each already established. Its sole output is an in-memory `AnswerQualityReport`
(see Schemas) returned directly to the caller.

## Schemas

All in-memory Python structures — none persisted, no file format to version.

**`AnswerQualityReport`**
```jsonc
{
  "answer_quality_report_id": "...",           // deterministic identity, see Design Decisions #10
  "answer_quality_pipeline_version": "1.0.0",
  "evaluated_at": "2026-07-21T12:00:00Z",      // timestamp, excluded from every determinism comparison
  "groundedness_report_id": "...",             // identity reference back to the input GroundednessReport
                                                // — the sole link a caller needs to re-read
                                                // groundedness_score, per-span detail, or the threshold
                                                // that report was assembled against
  "cited_response_id": "...",                  // copied verbatim, full provenance
  "llm_response_id": "...",                    // copied verbatim, full provenance
  "prompt_package_id": "...",                  // copied verbatim, full provenance
  "context_package_id": "...",                 // copied verbatim, full provenance
  "status": "PASS",                            // SKIPPED | FAIL | PARTIAL | PASS — pure passthrough of
                                                // GroundednessReport.status (Design Decisions #9)
  "response_length_chars": 1523,               // len(response_text)
  "response_length_words": 240,                // word count per the frozen word-extraction rule
                                                // (Evaluation Algorithm) — NFC-normalized internal
                                                // copy, split on maximal Unicode-whitespace runs
  "lexical_diversity_ratio": 0.62,             // unique case-folded words / total words; 0.0 when
                                                // response_length_words == 0
  "span_count": 6,                             // copied verbatim — the necessary denominator for
                                                // average_span_length_chars (Design Decisions #6)
  "average_span_length_chars": 253.83,         // response_length_chars / span_count; 0.0 when
                                                // span_count == 0 — EXACT, not approximate, by Stage
                                                // 14's own Response Segmentation guarantee (see Context)
  "citation_presence_ratio": 0.833,            // (span_count - unsupported_span_count) / span_count;
                                                // 1.0 when span_count == 0 (vacuous, mirrors
                                                // GroundednessReport's own groundedness_score
                                                // convention)
  "answer_quality_score": 0.786,               // GROUNDEDNESS_WEIGHT * groundedness_score +
                                                // CITATION_PRESENCE_WEIGHT * citation_presence_ratio;
                                                // always in [0.0, 1.0] since both components are
  "findings": [ /* this stage's own findings: {severity, code, message} */ ],
  "groundedness_findings": [ /* GroundednessReport.findings[], copied verbatim — full upstream
                                 provenance, one level only, matching every prior stage's own
                                 *_findings convention */ ]
}
```

## Evaluation Algorithm

A fixed set of named, deterministic, mathematically-defined transforms — never a second LLM call, never
an embedding similarity computation, never any form of subjective or learned scoring (Design Decisions
#2). The specification below is exhaustive: two independent implementations following it produce
identical metric values from identical input.

**Lexical metrics.** `compute_lexical_metrics(response_text)`:
- `response_length_chars = len(response_text)` — always computed against the raw, unmodified
  `response_text`; never against any normalized or folded copy (word extraction below normalizes only
  its own internal, throwaway copy, never this one).
- **Word extraction — frozen, exhaustive rule.** An internal copy of `response_text` is first
  normalized to Unicode NFC (mirroring Stage 14/15's own `fold()` first step, applied here only to this
  throwaway internal copy — never to the stored `response_text` or `response_length_chars`). Word
  boundaries are then located by treating every maximal run of one or more Unicode whitespace
  characters (space, tab, newline, carriage return, and any other Unicode-whitespace code point) as a
  single delimiter; the text strictly between two consecutive delimiters, or between a delimiter and
  the start/end of the string, is one word. A leading or trailing whitespace run produces no empty
  word. No punctuation is stripped, inserted, or otherwise altered by this step: apostrophes and
  hyphens are ordinary characters, never treated as separators or removed — `"isn't"` is one word,
  `"well-known"` is one word, `"end."` (with its trailing period) is one word, exactly as written. This
  is the complete, frozen tokenization rule; two independent implementations following it produce an
  identical word list from identical input. `words` denotes this list; `response_length_words =
  len(words)`.
- `lexical_diversity_ratio`: each element of `words` is additionally folded via a locale-independent,
  simple lowercase mapping only (`.lower()`, never a locale-sensitive casing rule, matching Stage
  14/15's own `fold()` casing step exactly) — no further normalization or whitespace handling applies
  at this step, since `words` are already frozen tokens from word extraction above.
  `lexical_diversity_ratio = len({w.lower() for w in words}) / len(words)` when `words` is non-empty,
  else exactly `0.0`, by definition, never a division by zero. The result depends only on the
  cardinality of the case-folded set, never on set iteration or hash ordering — no implementation may
  treat iteration order as significant.
- **Fully empty input, stated explicitly.** When `response_text == ""` (which Stage 14/15's own
  guarantees mean always co-occurs with `span_count == 0`): `response_length_chars = 0`, `words = []`,
  `response_length_words = 0`, `lexical_diversity_ratio = 0.0` — every value forced by the formulas
  above, never a distinct special case.

**Structural metrics.** `compute_structural_metrics(response_length_chars, span_count)`:
- `average_span_length_chars = response_length_chars / span_count` when `span_count > 0`, else exactly
  `0.0`. This is not an approximation: Stage 14's own Response Segmentation guarantees every character
  of `response_text` belongs to exactly one span with no gaps or overlaps
  (`sum(len(span.text) for span in spans) == len(response_text)`, inherited unbroken through Stage 15),
  so `response_length_chars / span_count` equals the true mean per-span character length exactly,
  without Stage 16 ever needing to read an individual span's own text.

**Citation presence.** `compute_citation_presence_ratio(span_count, unsupported_span_count)`:
- `citation_presence_ratio = (span_count - unsupported_span_count) / span_count` when `span_count > 0`,
  else exactly `1.0` (vacuously fully "present" — no spans exist to lack a citation), mirroring
  `GroundednessReport.groundedness_score`'s own identical vacuous-`1.0`-on-`span_count == 0` convention
  one stage upstream. This is Stage 16's own new metric — a coarser, whole-response-level count derived
  purely from `GroundednessReport`'s own aggregate fields, never a re-derivation of Stage 14's own
  `citation_coverage` computation (which Stage 16 never reads, since it never opens `CitedResponse` —
  Design Decisions #1).

**Composite score — the exact, frozen equation, stated numerically as well as symbolically.**
`compute_answer_quality_score(groundedness_score, citation_presence_ratio)`:
```
answer_quality_score = (groundedness_score        * GROUNDEDNESS_WEIGHT)
                      + (citation_presence_ratio   * CITATION_PRESENCE_WEIGHT)
                      = (groundedness_score        * 0.7)
                      + (citation_presence_ratio   * 0.3)
```
`GROUNDEDNESS_WEIGHT = 0.7` and `CITATION_PRESENCE_WEIGHT = 0.3` (Constants) are frozen numeric
literals, never symbolic placeholders a future implementer could legally choose differently. Since
`GROUNDEDNESS_WEIGHT + CITATION_PRESENCE_WEIGHT == 1.0` exactly, and both `groundedness_score` and
`citation_presence_ratio` are always in `[0.0, 1.0]`, `answer_quality_score` is always in
`[0.0, 1.0]` by construction — no clamping is ever needed or applied. **Fully empty input, stated
explicitly:** when `span_count == 0`, `citation_presence_ratio == 1.0` (vacuous, per above) and
`groundedness_score` is whatever vacuous value the input `GroundednessReport` itself already carries
in that case (typically `1.0`, per Stage 15's own identical vacuous-on-`span_count == 0` convention) —
`groundedness_score` is the one component of `answer_quality_score` not structurally forced to a
specific value by Stage 16 itself, since Stage 16 only ever reads it, never computes it (Design
Decisions #6).

**Empty-input behavior — the complete, consolidated definition.** When the input `GroundednessReport`
carries `response_text == ""` (always co-occurring with `span_count == 0`, per Stage 14/15's own
guarantees), every metric on `AnswerQualityReport` is fully determined below — never a distinct,
implementation-dependent code path for any of the six:

| Field | Value on empty input |
|---|---|
| `response_length_chars` | `0` |
| `response_length_words` | `0` |
| `lexical_diversity_ratio` | `0.0` |
| `average_span_length_chars` | `0.0` |
| `citation_presence_ratio` | `1.0` (vacuous) |
| `answer_quality_score` | `(groundedness_score * 0.7) + (1.0 * 0.3)` — determined by whatever vacuous `groundedness_score` the input `GroundednessReport` itself already carries (typically `1.0`); the only field in this table not forced to one fixed literal by Stage 16 alone |

## Design Decisions

1. **A single input, `GroundednessReport`, is sufficient; no other upstream artifact is ever opened.**
   Every metric named in scope — answer completeness, citation coverage statistics, groundedness
   statistics, unsupported span statistics, lexical quality metrics, structural quality metrics,
   deterministic scoring — is computable from fields `GroundednessReport` already carries or already
   guarantees by construction (`response_text`, `span_count`, `unsupported_span_count`,
   `groundedness_score`, `status`, and the full identity chain). Re-reading `CitedResponse`,
   `ContextPackage`, `PromptPackage`, or `LLMResponse` would only duplicate work Stages 10–15 already
   did, for no gain — the identical call every one of those stages already made one stage upstream, for
   the identical reason, taken here to its logical minimum: one input, not two.
2. **Every metric is deterministic, mathematically defined, and non-semantic — Principle 5 applies
   here exactly as it has since Stage 7.** No LLM call, no embedding, no NLI/entailment model, no
   learned or statistically-fit scoring function, anywhere in this design. This is a restatement of an
   already-established, non-negotiable project-wide constraint, not a new rule invented for this stage.
3. **No fact-checking, hallucination detection, or contradiction detection is attempted, ever.** These
   require exactly the kind of semantic/model-based judgment Principle 5 forbids project-wide; Stage 16
   only ever aggregates counts and ratios that Stage 14 and Stage 15 already computed via their own
   deterministic lexical methods — it adds arithmetic over already-settled classifications, never a new
   judgment about meaning.
4. **`answer_quality_score` combines only the two `[0,1]`-scaled, quality-bearing signals
   (`groundedness_score`, `citation_presence_ratio`); purely descriptive statistics are reported but
   never composited.** `response_length_chars`, `response_length_words`, `lexical_diversity_ratio`,
   `span_count`, and `average_span_length_chars` all carry useful triage information but have no
   inherent "higher is better" direction that would justify folding them into one score — a very long
   answer is not thereby a better one, nor is high lexical diversity — and doing so would embed exactly
   the kind of subjective value judgment the Evaluation Strategy's "avoid subjective metrics"
   instruction warns against. They are reported for auditability and triage, never composited.
5. **Fixed, named composite weights — `GROUNDEDNESS_WEIGHT = 0.7`, `CITATION_PRESENCE_WEIGHT = 0.3`
   (Constants) — never learned, tuned, or fit by any statistical or ML process.** Groundedness (whether
   an attached citation structurally holds up under Stage 15's own stricter longest-common-substring
   check) is weighted more heavily than mere citation presence (whether a span got cited at all,
   regardless of how strongly) because the former is strictly stronger evidence of a well-supported
   answer — a deliberate, arbitrary-but-fixed and explicitly documented choice, the same "a heuristic is
   permitted only when it is a fixed, named, documented rule" posture Principle 5 requires everywhere
   else in this project.
6. **`groundedness_score` is read but never re-stated on the output schema; `span_count` is
   duplicated.** A caller already holds `GroundednessReport` (linked back via `groundedness_report_id`)
   and can read `groundedness_score` there directly — restating it on `AnswerQualityReport` would be
   exactly the "unnecessary duplication of upstream payloads" the Outputs design instruction warns
   against. `span_count`, by contrast, is duplicated deliberately: without it, `average_span_length_chars`
   is uninterpretable without a forced cross-reference back to `GroundednessReport`, and Outputs
   explicitly permits including a field "only if justified" — `span_count` is the one upstream count
   that is. More generally: `GroundednessReport` itself is never duplicated into the output in any
   form — its `span_groundedness` list, `groundedness_threshold`, `groundedness_pipeline_version`,
   `validated_at`, and every field besides the two duplicated above are never copied or embedded into
   `AnswerQualityReport`; `groundedness_report_id` is the sole, deliberate link back to it.
7. **Stage 16 never modifies anything it reads, and has no lever to correct a low-quality answer.**
   `GroundednessReport`, and by extension every earlier-stage object or artifact it was built from, is
   read-only input; Stage 16 cannot regenerate a response, re-attach a citation, or adjust a
   groundedness label. This mirrors the exact "validate-and-flag-only, never corrective" posture Stage
   12 already established for its own prompt-budget overflow — deciding what to *do* about a
   low-scoring answer (regenerate, reject, surface a warning) is explicitly a Stage 17+ decision, never
   Stage 16's.
8. **Stage 16 is separate from Stage 15, not folded into it, because the two stages answer different
   questions at different units of analysis.** Stage 15 asks "is *this one citation*, taken alone,
   structurally supported by its cited passage" — a per-span, per-citation lexical check, already
   frozen. Stage 16 asks "how good is *the completed answer*, as a whole" — a response-level
   aggregate/composite judgment that only makes sense once every span's own classification already
   exists. Reopening Stage 15 to add response-level aggregation it was never designed to own would
   violate the single-responsibility boundary the Stage 14 Roadmap Definition Pass already established
   for this entire 14–21 sequence.
9. **`status` is a pure passthrough of `GroundednessReport.status`, never an independently-computed
   value.** Stage 16 performs no external call of any kind and can only ever classify data that already
   exists — the same "can only ever lose information relative to upstream, never independently fail on
   its own terms" situation Stage 10, 11, 12, 14, and 15 were each already in (never Stage 13's own
   situation, which genuinely can fail on its own terms via a live network call). Its own findings
   (Validation §2) are therefore always WARNING-severity and never alter `status`.
10. **`answer_quality_report_id` hashes only `groundedness_report_id` — the sole identity-determining
    input, since Stage 16 accepts no per-request configuration of any kind.** Matching Stage 9/11/12/14/
    15's own "hash the identity-determining inputs, not the derived payload" pattern, taken here to its
    logical minimum:
    ```python
    hash_input = {"groundedness_report_id": groundedness_report["groundedness_report_id"]}
    answer_quality_report_id = sha256(canonical_json(hash_input)).hexdigest()
    ```
    Every metric on `AnswerQualityReport` is fully determined by `groundedness_report_id` alone (given
    the frozen algorithm and fixed constants) — hashing any derived field would be redundant, not
    additionally identity-bearing.
11. **Every threshold and weight is a fixed constant; Stage 16 accepts no per-request configuration of
    any kind.** Unlike Stage 15's own `groundedness_threshold` (which gates a per-span classification a
    caller may reasonably want to tune), every Stage 16 threshold gates only an advisory
    WARNING-severity finding, and the composite weights define the very meaning of
    `answer_quality_score` itself — making either caller-configurable would mean an identical
    `GroundednessReport` could yield a different `answer_quality_score` under two different callers,
    undermining "identical input always yields identical output" as an externally-visible guarantee,
    not merely an internal implementation detail.
12. **Stage 16 never iterates `span_groundedness`, and never re-derives a per-span-level count from
    scratch.** Every span-level aggregate it needs (`span_count`, `unsupported_span_count`) is already
    computed and stored on `GroundednessReport` by Stage 15; Stage 16 only ever reads these two integers
    and performs O(1) arithmetic on them. This keeps Stage 16's own algorithm O(n) in `response_text`
    length alone (Complexity), and is a direct consequence of, and further argument for, the
    single-input minimality already established in Design Decisions #1.
13. **No `status == "FAIL"`-style short-circuit branch, unlike Stage 11's own Pipeline [2].** A
    `GroundednessReport` with `status` in `{SKIPPED, FAIL}` already guarantees `span_count == 0` and
    `response_text == ""` (inherited unbroken from Stage 13 through Stage 15); every metric computed by
    the ordinary path already handles that case correctly and vacuously (`response_length_chars == 0`,
    `lexical_diversity_ratio == 0.0`, `citation_presence_ratio == 1.0`, `average_span_length_chars ==
    0.0`) with no special case required — the same "one uniform pipeline handles every status
    alike" posture Stage 12 already established for its own uniform, no-short-circuit pipeline.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md` §4's
Critical/Recoverable document-quarantine model, since Stage 16 has no document to quarantine and no
persisted artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10 through Stage 15
each already gave for their own Validation sections).

**1. Input validation codes** — raised, never returned as part of any `AnswerQualityReport`:

| Code | Raised as | Trigger |
|---|---|---|
| `GROUNDEDNESS_REPORT_MALFORMED` | `AnswerQualityEvaluationInputError` | the received `GroundednessReport` is missing a required key or has a wrong-typed value — inspecting exactly `groundedness_report_id`, `cited_response_id`, `llm_response_id`, `prompt_package_id`, `context_package_id`, `status`, `response_text`, `span_count`, `unsupported_span_count`, `groundedness_score`, and `findings`; no other `GroundednessReport` field is inspected (mirrors Stage 14/15's own "validate only the fields actually read" convention); no `AnswerQualityReport` is produced at all |

**2. Package-level findings** — recorded in `AnswerQualityReport.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `RESPONSE_EMPTY` | WARNING | package | `response_length_chars == 0` (span_count == 0, e.g. an upstream `SKIPPED`/`FAIL` status); never alters `status` |
| `ANSWER_BELOW_MIN_LENGTH` | WARNING | package | `0 < response_length_chars < MIN_ANSWER_LENGTH_CHARS`; never alters `status` — advisory only, see Known Limitations |
| `ZERO_ANSWER_QUALITY_SCORE` | WARNING | package | `span_count > 0` and `answer_quality_score == 0.0`; never alters `status` |
| `LOW_ANSWER_QUALITY_SCORE` | WARNING | package | `0.0 < answer_quality_score < LOW_ANSWER_QUALITY_THRESHOLD`; never alters `status` |
| `LOW_CITATION_PRESENCE` | WARNING | package | `0.0 < citation_presence_ratio < LOW_CITATION_PRESENCE_THRESHOLD`; never alters `status` |

`status` truth table (pure passthrough, no additional Stage 16 condition):

| Condition | `status` |
|---|---|
| `GroundednessReport.status == "SKIPPED"` | `SKIPPED` |
| `GroundednessReport.status == "FAIL"` | `FAIL` |
| `GroundednessReport.status == "PARTIAL"` | `PARTIAL` |
| `GroundednessReport.status == "PASS"` | `PASS` |

**3. Internal invariant codes** — raised by `validate_evaluation_report()`, run unconditionally on the
assembled report before it is ever returned; never returned as part of any `AnswerQualityReport`:

| Code | Trigger |
|---|---|
| `RESPONSE_LENGTH_CHARS_MISMATCH` | `response_length_chars != len(response_text)` |
| `RESPONSE_LENGTH_WORDS_MISMATCH` | `response_length_words` does not equal the word count produced by the frozen word-extraction rule (Evaluation Algorithm) applied to `response_text` |
| `LEXICAL_DIVERSITY_MISMATCH` | `lexical_diversity_ratio` does not equal `len({w.lower() for w in words}) / len(words)` (or `0.0` when `words == []`) |
| `AVERAGE_SPAN_LENGTH_MISMATCH` | `average_span_length_chars` does not equal `response_length_chars / span_count` (or `0.0` when `span_count == 0`) |
| `CITATION_PRESENCE_COMPUTATION_MISMATCH` | `citation_presence_ratio` does not equal `(span_count - unsupported_span_count) / span_count` (or `1.0` when `span_count == 0`) |
| `ANSWER_QUALITY_SCORE_COMPUTATION_MISMATCH` | `answer_quality_score` does not equal `(groundedness_score * GROUNDEDNESS_WEIGHT) + (citation_presence_ratio * CITATION_PRESENCE_WEIGHT)` (checked against the input `GroundednessReport`'s own `groundedness_score`, never a re-stated copy — see Design Decisions #6), or falls outside `[0.0, 1.0]` |
| `GROUNDEDNESS_REPORT_ID_MISMATCH` | `report["groundedness_report_id"] != input GroundednessReport["groundedness_report_id"]`, or any of `cited_response_id`/`llm_response_id`/`prompt_package_id`/`context_package_id` disagrees with the input |

Every metric Stage 16 computes — `response_length_chars`, `response_length_words`,
`lexical_diversity_ratio`, `average_span_length_chars`, `citation_presence_ratio`, and
`answer_quality_score` — has its own dedicated invariant above: `validate_evaluation_report`
recomputes each one fresh from the input `GroundednessReport`'s own fields (`response_text`,
`span_count`, `unsupported_span_count`, `groundedness_score`) using the exact formula given in
Evaluation Algorithm, and compares the freshly-recomputed value against what is actually stored on the
assembled `AnswerQualityReport` — none is checked only implicitly as a side effect of another. Any of
these seven raises
`AnswerQualityEvaluationInternalError` rather than being returned as a malformed `AnswerQualityReport`
— the same fail-loud posture as Stage 10 through Stage 15's own internal-invariant exceptions, and
never expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage16_answer_quality_evaluation"`, `doc_id: null`
always — entries are request-scoped, not document-scoped). New codes this stage adds:
`WARNING_RESPONSE_EMPTY`, `WARNING_ANSWER_BELOW_MIN_LENGTH`, `WARNING_ZERO_ANSWER_QUALITY_SCORE`,
`WARNING_LOW_ANSWER_QUALITY_SCORE`, `WARNING_LOW_CITATION_PRESENCE`. No new `FATAL_*` code — Stage 16
never sets a manifest `error_code`, since it never touches the manifest at all (see Manifest
Interaction).

## Manifest Interaction

None. Stage 16 never opens, reads, or writes `manifest.json` — the sixth stage in this pipeline with
zero manifest interaction of any kind, extending Stage 11 through Stage 15's own posture: every field
it needs already arrived on its single in-memory input.

## Artifact Interaction

None. Stage 16 performs zero file reads and zero file writes. Its only input is an in-memory
`GroundednessReport`; its only output is an in-memory `AnswerQualityReport`. No atomicity concern exists
because there is nothing to persist and nothing to read from disk at all — the same posture Stage 15
already established.

## Directory Structure

None added. Stage 16 introduces no new artifact directory — there is no artifact.

## Determinism

- **Deterministic (guaranteed).** Every computation this stage performs — `compute_lexical_metrics`,
  `compute_structural_metrics`, `compute_citation_presence_ratio`, `compute_answer_quality_score`,
  `answer_quality_report_id`, `status` passthrough, and `validate_evaluation_report`'s own outcome — is
  a pure function of the single `GroundednessReport` input, with no external call, no randomness, and no
  per-request configuration to vary (Design Decisions #11). Stated exhaustively, not merely implied:
  - **Byte-identical output.** Identical `GroundednessReport` input always produces a byte-identical
    `AnswerQualityReport` output, field for field, across repeated calls and process restarts.
  - **Timestamps excluded.** `evaluated_at` is the sole field excluded from every determinism
    comparison — a wall-clock timestamp, the same treatment every prior stage already gives its own
    timestamp field.
  - **No randomness.** No sampling, UUID, random seed, or any other non-reproducible value feeds into
    any computed field other than `evaluated_at` itself.
  - **No hidden state.** No global variable, environment variable, configuration file, or cache is read
    or consulted anywhere in this stage — `evaluate_answer_quality()`'s only input is its own single
    argument.
  - **No dependence on dictionary/set ordering.** `lexical_diversity_ratio` depends only on the
    cardinality of a set (`len(...)`), never on the order its elements were inserted or iterated; no
    other computation in this stage constructs a set or dict whose iteration order could affect any
    output field.
- **Inherited (not re-verified).** `groundedness_score`'s own correctness is Stage 15's guarantee, not
  re-derived or re-checked by Stage 16 — it is trusted as an opaque, already-validated input value, the
  same "does not re-verify an upstream stage's own settled computation" posture every stage in this
  chain extends from its predecessor.
- **Intentionally not evaluated.** Semantic quality, factual correctness, coherence, fluency, and
  relevance to the original query are never computed, attempted, or approximated — the query-relevance
  gap in particular is structural, not a deferred feature (Known Limitations).

## Read-Only Guarantees

Stage 16 never modifies `manifest.json`, any `GroundednessReport`, `CitedResponse`, `ContextPackage`,
`PromptPackage`, `LLMResponse`, `RetrievalResult`, any chunk, any metadata, any vector index, or any
embedding. No upstream artifact or in-memory object is ever mutated; no write capability, and no network
call of any kind, exists anywhere in this design.

## Failure Handling

- **A malformed `GroundednessReport`** (missing/wrong-typed required key) —
  `AnswerQualityEvaluationInputError` (`GROUNDEDNESS_REPORT_MALFORMED`) raised immediately; no
  `AnswerQualityReport` returned.
- **`GroundednessReport.status` in `{SKIPPED, FAIL}`** — `response_text == ""` and `span_count == 0`
  are already guaranteed by the inherited upstream chain; every metric computes normally and vacuously
  through the ordinary path (no special-cased branch — Design Decisions #13);
  `AnswerQualityReport.status` passes through as `SKIPPED`/`FAIL`; `RESPONSE_EMPTY` WARNING recorded.
  Because `citation_presence_ratio` and (typically) `groundedness_score` are both vacuously `1.0` in
  this case, `answer_quality_score` can itself be `1.0` despite the upstream failure — a caller must
  always inspect `status` before interpreting any score field, exactly the same caveat
  `GroundednessReport.groundedness_score` already carries one stage upstream (Known Limitations).
- **`GroundednessReport.status == "PARTIAL"`** — every metric computed normally from whatever
  `response_text`/counts Stage 15 provided; `AnswerQualityReport.status` stays `PARTIAL`;
  `GroundednessReport.findings[]` carried forward verbatim into `groundedness_findings`.
- **`0 < response_length_chars < MIN_ANSWER_LENGTH_CHARS`** — `ANSWER_BELOW_MIN_LENGTH` WARNING; not an
  error; a deterministic length heuristic only, never a claim of semantic incompleteness (Known
  Limitations).
- **`answer_quality_score == 0.0`** (both component scores are `0.0`) — `ZERO_ANSWER_QUALITY_SCORE`
  WARNING; not an error; a legitimate, informative outcome.
- **`0.0 < answer_quality_score < LOW_ANSWER_QUALITY_THRESHOLD`** — `LOW_ANSWER_QUALITY_SCORE` WARNING;
  not an error.
- **`0.0 < citation_presence_ratio < LOW_CITATION_PRESENCE_THRESHOLD`** — `LOW_CITATION_PRESENCE`
  WARNING; not an error; may co-occur with `LOW_ANSWER_QUALITY_SCORE`.
- **A genuine Stage 16 bug** (one of the seven named internal invariant codes in Validation §3) —
  `AnswerQualityEvaluationInternalError` raised, not returned as a malformed `AnswerQualityReport`.

## Configuration

None. Stage 16 accepts no per-request configuration of any kind — every threshold
(`MIN_ANSWER_LENGTH_CHARS`, `LOW_ANSWER_QUALITY_THRESHOLD`, `LOW_CITATION_PRESENCE_THRESHOLD`) and
composite weight (`GROUNDEDNESS_WEIGHT`, `CITATION_PRESENCE_WEIGHT`) is a fixed constant (Design
Decisions #11, Constants). Stage 16 consumes no adapter factories of any kind; it never touches
`ProviderAdapter`, `IndexAdapter`, or `LLMAdapter`.

## Concurrency

Fully safe under concurrent calls. Stage 16 performs zero writes, holds no shared mutable state, and
makes no network or file-system call of any kind — `evaluate_answer_quality()` is a pure function of its
own single argument; any number of calls, including against identical input, may run simultaneously with
no locking and no race condition.

## Security Considerations

- **Untrusted model output, inherited.** `response_text` (read via `GroundednessReport`) remains opaque,
  model-generated content; Stage 16 performs no interpretation or execution of it — only length
  measurement and whitespace-delimited word splitting. The same "`response_text` is potentially
  adversarial input to whatever consumes it next" risk Stage 13 first accepted (Stage 13's own Design
  Decisions #11) and Stage 14/15 already passed through unchanged.
- **No new I/O surface.** Stage 16 opens no file, calls no network endpoint, and touches no credential
  of any kind.
- **No write capability anywhere in this design** — eliminates an entire class of injection/corruption
  risk against this pipeline's own artifacts and in-memory objects by construction, not by runtime
  validation.

## Public Function Contracts

- `validate_groundedness_report(report: GroundednessReport) -> None` — Stage 16's own structural input
  check; inspects exactly `groundedness_report_id`, `cited_response_id`, `llm_response_id`,
  `prompt_package_id`, `context_package_id`, `status`, `response_text`, `span_count`,
  `unsupported_span_count`, `groundedness_score`, and `findings` — no other `GroundednessReport` field is
  inspected. Raises `AnswerQualityEvaluationInputError` (code `GROUNDEDNESS_REPORT_MALFORMED`) on
  violation. Distinct from, and never calling, Stage 15's own internal function of the same name.
- `compute_lexical_metrics(response_text: str) -> Dict[str, Any]` — returns
  `{response_length_chars, response_length_words, lexical_diversity_ratio}` (Evaluation Algorithm); pure
  function of `response_text` alone; total (always succeeds, including on an empty string).
- `compute_structural_metrics(response_length_chars: int, span_count: int) -> Dict[str, Any]` — returns
  `{average_span_length_chars}`; pure function of its two arguments; total.
- `compute_citation_presence_ratio(span_count: int, unsupported_span_count: int) -> float` — fixed
  formula (Evaluation Algorithm); pure function of its two arguments; total.
- `compute_answer_quality_score(groundedness_score: float, citation_presence_ratio: float) -> float` —
  fixed weighted formula (Evaluation Algorithm); pure function of its two arguments; total; always
  returns a value in `[0.0, 1.0]`.
- `build_evaluation_report(groundedness_report: GroundednessReport, lexical_metrics: Dict,
  structural_metrics: Dict, citation_presence_ratio: float, answer_quality_score: float) ->
  AnswerQualityReport` — wraps every computed metric + inherited `status`/identity chain +
  this stage's own findings into the final report; computes `answer_quality_report_id`.
- `validate_evaluation_report(report: AnswerQualityReport, groundedness_report: GroundednessReport) ->
  None` — internal invariant self-check; recomputes every metric from `groundedness_report`'s own
  fields and compares against `report`; raises `AnswerQualityEvaluationInternalError` (one of the seven
  named codes in Validation §3) on violation.
- `evaluate_answer_quality(groundedness_report: GroundednessReport) -> AnswerQualityReport` — the sole
  public entrypoint; orchestrates validation, every metric computation, report assembly, and the
  internal self-check in sequence; never reads or writes any artifact, the manifest, or any network
  endpoint.

## Constants

```python
ANSWER_QUALITY_PIPELINE_VERSION = "1.0.0"
GROUNDEDNESS_WEIGHT = 0.7             # weight of groundedness_score in the composite formula — weighted
                                       # higher than citation presence since it is strictly stronger
                                       # evidence of a well-supported answer (Design Decisions #5)
CITATION_PRESENCE_WEIGHT = 0.3        # GROUNDEDNESS_WEIGHT + CITATION_PRESENCE_WEIGHT == 1.0 exactly,
                                       # guaranteeing answer_quality_score in [0.0, 1.0] by construction
MIN_ANSWER_LENGTH_CHARS = 20          # below this (and above 0), ANSWER_BELOW_MIN_LENGTH fires — a
                                       # conservative floor chosen low enough that almost no legitimate
                                       # complete answer falls under it, while still catching an
                                       # obviously truncated or degenerate response; advisory only,
                                       # never authoritative evidence of incompleteness (Known Limitations)
LOW_ANSWER_QUALITY_THRESHOLD = 0.5    # below this (and above 0.0), LOW_ANSWER_QUALITY_SCORE fires —
                                       # the [0,1] midpoint, consistent with Stage 14/15's own
                                       # LOW_*_THRESHOLD = 0.5 precedent
LOW_CITATION_PRESENCE_THRESHOLD = 0.5 # below this (and above 0.0), LOW_CITATION_PRESENCE fires — the
                                       # same [0,1]-midpoint convention, applied to this stage's own
                                       # new metric
```

## Threshold Ownership

Stated explicitly, mirroring the identical clarification Stage 15's own document already makes for its
own thresholds relative to Stage 14's: `MIN_ANSWER_LENGTH_CHARS`, `LOW_ANSWER_QUALITY_THRESHOLD`, and
`LOW_CITATION_PRESENCE_THRESHOLD` belong exclusively to Stage 16's own advisory, WARNING-severity
findings. None of the three is ever read by, passed to, or in any way permitted to influence Stage 15's
own `groundedness_threshold`/`LOW_GROUNDEDNESS_THRESHOLD`, or Stage 14's own
`citation_match_threshold`/`LOW_CITATION_COVERAGE_THRESHOLD` — three stages' thresholds live in three
separate, frozen modules, and no future change to one may ever be justified by tuning another.
Symmetrically: Stage 16 never writes back to, or in any way modifies, the input `GroundednessReport` or
any object it was built from (Read-Only Guarantees) — a threshold crossing here produces a new finding
on `AnswerQualityReport.findings[]` only, never a mutation of anything upstream. Stated as one summary
sentence: Stage 16's advisory thresholds never influence Stage 15, never modify any upstream report, and
never automatically reject, regenerate, or hide an answer — every consequence of crossing one stops at a
WARNING-severity finding on this stage's own output (Future Stage Boundaries).

## Known Limitations

- **No query-relevance assessment of any kind — a structural impossibility, not a deferred feature.**
  `query` is not present anywhere on `GroundednessReport`, Stage 16's sole input; Stage 16 cannot judge,
  even heuristically, whether the answer actually addresses what was asked. A future revision wishing to
  add this would need to thread `query` through as a second input — a real, named architectural change,
  not an oversight in this design.
- **`answer_quality_score` is not a semantic quality judgment.** It is a fixed, named composite of two
  lexical/structural signals under fixed weights — never fact-checking, never entailment, never a
  judgment of whether the answer is actually correct, helpful, or well-written. A high score means "well
  cited and well grounded by Stage 15's own lexical standard," nothing more.
- **Vacuous scoring on an empty or failed upstream response.** When `GroundednessReport.status` is
  `SKIPPED` or `FAIL`, `span_count == 0` drives both `citation_presence_ratio` and (typically)
  `groundedness_score` to their vacuous `1.0` values, which can make `answer_quality_score` itself equal
  `1.0` despite the upstream failure. A caller must always check `status` before trusting any score field
  in isolation — restated from Failure Handling since it is easy to miss.
- **`ANSWER_BELOW_MIN_LENGTH` is a length heuristic only.** A short but complete and correct answer
  (e.g. "No such provision exists in this document.") will trigger it exactly as a genuinely truncated
  response would; it is advisory triage information, never evidence of actual incompleteness.
- **`lexical_diversity_ratio` is a raw type-token ratio, not corrected for response length.** Type-token
  ratio is well known to trend downward as text length grows for purely combinatorial reasons (a longer
  text has more chances to repeat a common word); Stage 16 does not apply any length-correction
  transform (e.g. MTLD, a moving-average TTR) — doing so would introduce a second, more complex
  algorithm this project has no independent need to validate, and no such method is named anywhere in
  this project's own constants (mirrors the precedent every stage's own token/length approximation has
  already accepted, e.g. Stage 11/12's fixed `CHARS_PER_TOKEN_ESTIMATE`).
- **A degenerate weight/threshold combination is not cross-validated.** Nothing structurally prevents a
  future edit to `GROUNDEDNESS_WEIGHT`/`CITATION_PRESENCE_WEIGHT` from drifting apart from
  `LOW_ANSWER_QUALITY_THRESHOLD`'s own assumed midpoint framing; both are independently fixed constants,
  documented, not mechanically cross-checked against each other.

## Accepted Tradeoffs

- **One composite score under fixed, non-tunable weights, rather than per-caller-configurable
  weighting.** Simpler, and preserves "identical input always yields identical output" as an
  externally-visible guarantee (Design Decisions #11); accepts that a caller who genuinely wants a
  different balance between groundedness and citation presence must read the individual component
  metrics and recombine them outside this stage.
- **No query-awareness.** A deliberate scope limit stemming directly from the single-input design
  (Design Decisions #1); accepted because adding `query` as a second input would break the "one input is
  sufficient" minimality this design achieves, for a capability (query-relevance scoring) that itself
  would likely require probabilistic judgment to do well, conflicting with Principle 5 regardless.
- **No persisted `AnswerQualityReport` artifact.** Matches Stage 10 through Stage 15's own precedent —
  no audit trail exists unless a caller persists it independently.
- **A raw, uncorrected type-token ratio for lexical diversity**, accepting known length-sensitivity
  rather than adopting a more robust but more complex corrected metric this project has no independent
  need to validate.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not this
document.

- A malformed `GroundednessReport` is rejected deterministically, every time, without producing any
  `AnswerQualityReport`.
- `response_length_chars` always equals `len(response_text)` exactly; `response_length_words` always
  equals `len(response_text.split())` exactly.
- `lexical_diversity_ratio` always equals `len({w.lower() for w in words}) / len(words)` when
  `words` is non-empty, and exactly `0.0` when `response_length_words == 0` — never a division by zero.
- `average_span_length_chars` always equals `response_length_chars / span_count` exactly when
  `span_count > 0`, and exactly `0.0` when `span_count == 0`.
- `citation_presence_ratio` always equals `(span_count - unsupported_span_count) / span_count` exactly
  when `span_count > 0`, and exactly `1.0` when `span_count == 0`.
- `answer_quality_score` always equals `GROUNDEDNESS_WEIGHT * groundedness_score +
  CITATION_PRESENCE_WEIGHT * citation_presence_ratio` exactly, and always falls in `[0.0, 1.0]`.
- `GroundednessReport.status` always passes through unchanged to `AnswerQualityReport.status`, for each
  of `SKIPPED`, `FAIL`, `PARTIAL`, `PASS`.
- Every one of the seven internal invariant codes (`RESPONSE_LENGTH_CHARS_MISMATCH`,
  `RESPONSE_LENGTH_WORDS_MISMATCH`, `LEXICAL_DIVERSITY_MISMATCH`, `AVERAGE_SPAN_LENGTH_MISMATCH`,
  `CITATION_PRESENCE_COMPUTATION_MISMATCH`, `ANSWER_QUALITY_SCORE_COMPUTATION_MISMATCH`,
  `GROUNDEDNESS_REPORT_ID_MISMATCH`) fires under its documented condition and only that condition.
- Every one of the five package-level findings (`RESPONSE_EMPTY`, `ANSWER_BELOW_MIN_LENGTH`,
  `ZERO_ANSWER_QUALITY_SCORE`, `LOW_ANSWER_QUALITY_SCORE`, `LOW_CITATION_PRESENCE`) fires under its
  documented condition and only that condition, and none ever alters `status`.
- Determinism: identical `GroundednessReport` input produces a byte-identical `AnswerQualityReport`
  (`evaluated_at` excluded), across repeated calls and process restarts.
- Immutability: the input `GroundednessReport` object is never mutated by any Stage 16 function,
  regardless of outcome.
- No file is ever read or written, and no network call is ever made, by any Stage 16 function, under
  any input or outcome.

## Real Corpus Verification

Against a real `GroundednessReport` produced by the live Stage 10 → 11 → 12 → 13 → 14 → 15 chain: a
representative real report with a mix of `GROUNDED`/`WEAKLY_GROUNDED`/`UNSUPPORTED` spans produces
`response_length_chars`/`response_length_words` matching a manual count of the real `response_text`;
`average_span_length_chars` cross-checked against `response_length_chars / span_count` by hand;
`citation_presence_ratio` cross-checked against `(span_count - unsupported_span_count) / span_count` by
hand; `answer_quality_score` cross-checked against the fixed weighted formula using the real report's
own `groundedness_score`; two identical runs of `evaluate_answer_quality()` over the same real report
produce byte-identical `AnswerQualityReport`s (`evaluated_at` excluded).

**Determinism, explicitly:** like Stage 14 and Stage 15, this section states the ordinary, full
byte-identical guarantee without qualification — Stage 16 performs no live call of its own, so two calls
sharing an identical input are guaranteed to produce byte-identical output when replayed.

Immutability: the input `GroundednessReport` object, and every real upstream artifact (`manifest.json`,
every `chunks.json`, `embeddings.parquet`, `metadata.json`, everything under `vector_index/`, every
on-disk prompt template file), are confirmed byte-identical before and after the call — Stage 16 opens
none of them directly.

## Future Stage Boundaries

**Stage 16 produces advisory metrics only and never determines whether an answer should be accepted,
rejected, regenerated, or hidden — that responsibility belongs downstream, to Stage 17+.**

Stage 17+ (not designed here) owns everything Stage 16 deliberately excludes: response caching or
deduplication, any network-facing API or response serving, response streaming to a caller or UI,
conversation memory or multi-turn orchestration, tool/function calling, agent planning, and — critically
— any decision about what to *do* with a low `answer_quality_score` or a poorly-grounded answer
(regenerate, reject, surface a warning to an end user, escalate to a human reviewer). Stage 16 hands an
`AnswerQualityReport` back in memory; deciding how to act on it is entirely out of this design's scope.
Should a future stage ever need query-relevance scoring, that requires a new, explicitly-approved design
threading `query` through as a second input (Known Limitations) — never assumed or implied here.

## Verification (of this plan)

This is a design-only task — no code is written. Verification is a read-through against the user's
original 24-section request and its explicit scope/exclusion lists:

- Every one of the 19 explicitly-named sections (Overview, Inputs, Outputs, Responsibilities,
  Non-Responsibilities, Pipeline Ordering, Processing Algorithm, Design Decisions, Data Schemas,
  Constants, Configuration, Validation, Failure Handling, Public Function Contracts, Determinism,
  Complexity, Known Limitations, Validation Requirements, Future Stage Boundaries) is present above,
  mapped onto this project's own established naming where the two differ (`Pipeline Ordering` → folded
  into the Pipeline enumeration inside Public Function Contracts' call order plus Design Decisions #13;
  `Processing Algorithm` → `## Evaluation Algorithm`, matching Stage 15's own "Groundedness Verification
  Strategy" naming pattern; `Data Schemas` → `## Schemas`, matching every prior stage's own heading).
  Every additional section present in Stage 9 through Stage 15's own docs (Scope, Schemas, Logging,
  Manifest/Artifact Interaction, Directory Structure, Read-Only Guarantees, Security Considerations,
  Concurrency, Accepted Tradeoffs, Real Corpus Verification) is also present, per the explicit
  Consistency Requirement to match Stages 11–15's own style exactly.
- The in-scope evaluation categories (answer completeness — `ANSWER_BELOW_MIN_LENGTH`/
  `response_length_chars`/`response_length_words`; citation coverage statistics —
  `citation_presence_ratio`; groundedness statistics — `groundedness_score` read into
  `answer_quality_score`; unsupported span statistics — `unsupported_span_count` consumed via
  `citation_presence_ratio`; lexical quality metrics — `lexical_diversity_ratio`; structural quality
  metrics — `average_span_length_chars`, `span_count`; deterministic scoring — `answer_quality_score`)
  are each implemented and named explicitly.
- Every excluded item (semantic verification, factual verification, contradiction detection,
  hallucination detection, embeddings, vector search, reranking, LLM evaluation, answer rewriting,
  answer generation, prompt generation, citation extraction, groundedness validation, caching,
  networking, APIs, serving, orchestration, conversation memory, tool calling) is confirmed absent and
  explicitly named as excluded (Non-Responsibilities, Scope, Future Stage Boundaries).
- Inputs are minimal and every field justified (Inputs, Design Decisions #1); no field obtainable
  indirectly through `GroundednessReport` was introduced as a redundant separate input.
- The output schema is new, contains only evaluation results, and does not unnecessarily duplicate
  upstream payloads — the one deliberate exception (`span_count`) is individually justified (Design
  Decisions #6).
- Every metric is reproducible, deterministic, explainable, computed without any LLM or embedding, and
  mathematically defined with an exact formula (Evaluation Algorithm, Public Function Contracts).
- The three-level validation pattern (input validation, package-level findings, internal invariants)
  matches Stage 11–15's own convention exactly, with every code carrying a unique identifier, an exact
  trigger, and deterministic behavior (Validation).
- Failure handling uses only deterministic findings, has no silent failures, raises no exception for any
  expected condition, and reserves exceptions exclusively for the seven named internal invariant
  violations (Failure Handling, Validation §3).
- A full Design Decisions section is present, explicitly justifying why deterministic metrics were
  chosen (#2), why no LLM is involved (#2, #3), why no semantic evaluation is attempted (#3), why Stage
  16 never modifies any upstream artifact (#7), and why Stage 16 is separate from Stage 15 (#8).
- Known Limitations explicitly states what Stage 16 does not evaluate, without overclaiming capability,
  most prominently the structural query-relevance gap.
- Future Stage Boundaries names Stage 17 through Stage 21's own responsibilities as excluded here,
  consistent with the Stage 14 Roadmap Definition Pass's own dependency ordering.
- Document style (headings, prose density, no implementation notes, no review diary, no narrative
  history) matches Stage 9–15 precedent throughout.
