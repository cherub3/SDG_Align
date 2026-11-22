# Stage 7 — Semantic Chunking

See `docs/pipeline_principles.md` for shared conventions.

## Scope

Stage 7 turns each document's already-validated `clean_text.json` + `metadata.json` (from Stage 4/5
and this project's own "Stage 6") into `chunks.json` — a deterministic, structure-first segmentation
of already-extracted text into retrieval-sized chunks — plus an always-written
`chunk_validation_report.json`. It is purely deterministic string/offset computation: no AI, no
embeddings, no vector database, no retrieval, no ranking, no annotation; it never reopens the PDF,
never reads `raw_extraction.json`, and never mutates either input artifact. No Stage 8 functionality
(manifest finalization / `ready_for_chunking` promotion) is designed here.

## Pipeline

```
select eligible documents: "metadata" in record.artifact_paths
        ↓                   (NOT record.status == ready_for_chunking — nothing sets that; see Design Decisions #1)
load clean_text.json + metadata.json   (read-only, never mutated)
        ↓
resolve_heading_offsets(clean_text)          — deterministic intra-page offset recovery
        ↓
build_section_spans(clean_text, offsets)     — one span per section_tree entry, connected chain
        ↓
split_oversized_spans(spans)                 — structure-first fallback order; never crosses a section boundary
        ↓
merge_undersized_spans(spans)                — adjacent, same-branch, backward-only (one exception)
        ↓
assign_chunk_ids(spans, doc_id)              — structural, not positional; stable under document edits
        ↓
assemble_chunk_records(spans, clean_text, metadata)
        ↓
validate_chunks(chunks, clean_text)          — full-validation, no-fail-fast (Validation Severity Tiers)
        ↓
compute overall_status + summary (pass/warning/fail counts)
        ↓
write_chunk_validation_report()              — ALWAYS runs here, before the branch below
        ↓
   any Critical/FAIL finding? ──yes──▶ update_manifest() [QUARANTINED, error_code=FATAL_CHUNKING_FAILED]
        │no (PASS or WARNING only)
        ▼
write_chunks(chunks)
        ↓
update_manifest(record, chunks_path, chunk_validation_report_path)   [status stays REGISTERED]
```

Corpus reality check: only documents with `"metadata" in record.artifact_paths` are eligible —
currently up to 6 real corpus documents that pass Stage 4→5→"Stage 6" cleanly.

## Design Decisions

1. **Document selection.** Gate on `"metadata" in record.artifact_paths`, never on `record.status`.
   Why: nothing in the codebase sets `ready_for_chunking`; that promotion remains exclusively Stage
   8's job.
2. **`chunking_pipeline_version`.** An independent constant, stored only in `chunks.json`'s own
   header, never added to `ManifestRecord` — per the Manifest Update Convention.
3. **Chunk artifact directory.** `data/proposals/chunks/` added, sibling to existing artifact
   directories, none of which are touched.
4. **Table row/cell data.** `table_regions[].approx_rows` is always `null` (inherited from "Stage
   6"). Chunking uses only page-level table anchors and the already-embedded markdown table text;
   no attempt to recover row counts.
5. **`sections_flagged` reuse.** Re-applies Stage 5's own `APPENDIX_RE`/`REFERENCES_RE` directly
   against each chunk's `heading_path`, rather than trusting the persisted flag. Why: the flag is
   keyed by `start_page`, ambiguous when two sections share a page.
6. **Chunk boundary strategy — sections as the primary unit, with deterministic offset recovery.**
   Every span starts life as exactly one `section_tree` entry's content region.
   - New constant: `HEADING_LINE_PREFIX_TOLERANCE = 20` — chars of slack beyond `len(title)` for a
     matched line to still plausibly be the heading line itself (numbering/markdown prefix); beyond
     this, the match is treated as a false positive.
   - `resolve_heading_offsets`: for each `section_tree` entry, in document order, using a per-page
     search cursor (advances past each resolved match so two same-titled headings on one page each
     resolve to their own occurrence): `idx = page_text.find(title, cursor)` — first exact
     occurrence, pure `str.find()`, no fuzzy matching, no case-folding. Not found → resolution fails,
     logs `WARNING_HEADING_OFFSET_NOT_RECOVERED`, falls back to the page's own `char_start`. Found →
     walk backward to the enclosing line's start; if that line's length exceeds
     `len(title) + HEADING_LINE_PREFIX_TOLERANCE`, the match is implausible (likely a body-text
     mention of the title) and this design falls back to the same page-level snap instead. On
     success, offset = `char_start(start_page) + line_start`.
     Why: recovers real intra-page precision — `clean_text.json`'s per-page `headings[]` carries no
     offset field — using only already-produced text, no PDF, no Stage 5 change.
   - `build_section_spans`: a **connected chain** — `span[i].char_end` is defined as exactly
     `span[i+1].char_start`, so no gap is constructible by design (this is what makes
     `CHUNK_COVERAGE_EXACT` provable, not just probable). Content before the first heading becomes a
     synthetic **preamble span** (`section_id: null`, `heading_path: []`); an empty `section_tree`
     makes the whole document one preamble span.
   - Same-page collisions are now a **residual** case only: occurs when offset recovery fails for one
     or more entries sharing a `start_page`, producing a degenerate (near-zero-width) span — always
     merge-eligible regardless of section branch.
   - Excluded pages need no special handling — inherited zero-width and never-a-heading-anchor
     guarantees from Stage 4/5, not re-verified here.
   - Tables get no dedicated split boundary (no row/cell data exists). `has_table_content` is a
     page-level signal only — true if `[page_start, page_end]` intersects
     `metadata.json.structure.table_regions[].page`.
   - Appendices/references are chunked under identical rules to any other section (no exclusion, no
     truncation); tagged `is_appendix`/`is_references` by re-applying the shared regexes against
     `heading_path`; never merged across that boundary into/out of the main body.
7. **Chunk size policy — characters, not tokens.**
   Why: no tokenizer or embedding model is named anywhere in this project (embeddings are out of
   scope); `clean_text.json`'s own offsets are already character-based, avoiding a new dependency.
   ```python
   MIN_CHUNK_CHARS = 300      # below this, likely a bare heading + one sentence — too little
                               # standalone context to be a useful retrieval unit
   TARGET_CHUNK_CHARS = 1500  # ~250-300 words; a single-topic paragraph-cluster
   MAX_CHUNK_CHARS = 3000     # hard ceiling, 2x target; forces a split even mid-section
   ```
   Working defaults, not derived from measurement (only ~6 corpus documents exist today) — flagged
   in Self-Critique for revisit once an embedding model is actually selected.
8. **Chunk merging strategy.** Runs *after* oversized-splitting (deliberate ordering, see
   Self-Critique). Merge when, all of: the later span is `< MIN_CHUNK_CHARS`; it merges only into the
   *immediately preceding* span; the combined size stays `<= MAX_CHUNK_CHARS`; both spans share the
   same immediate `parent_section` — **or** the later span is a degenerate collision span (always
   eligible). One exception: the very first span in a document, if undersized, merges *forward*
   instead (nothing precedes it) — the only forward-merge case. Never merges across a top-level
   (`section_level == 1`) branch boundary, an appendix/references boundary, or into an
   already-`>= MIN_CHUNK_CHARS` span. If nothing is left to merge into, the span is kept as-is,
   flagged `CHUNK_SIZE_ABOVE_MIN` WARNING, never dropped or force-merged.
   Why: preserves topic coherence over rigid size compliance.
9. **Oversized section splitting — five-tier deterministic fallback, recursive, never crosses a
   `section_tree` boundary.**
   1. Paragraph boundary (`\n\n`) — greedy, cut at the last boundary before `TARGET_CHUNK_CHARS`.
   2. Sub-heading boundary — a markdown ATX line (`^#{1,6}\s+.+`, Stage 5's own highest-confidence
      detection tier, reused verbatim) is a strong break signal, used before list/sentence tiers.
      Why only this one Stage 5 tier: it's the least false-positive-prone signal, and the only one
      reusable without re-running Stage 5's font-emphasis logic (needs `raw_extraction.json`, out of
      scope). The split is text-level only — a sub-heading found this way is never promoted to its
      own `section_id`.
   3. List-item boundary (`- `, `* `, digit + `.`) — used only when a single paragraph itself
      exceeds `MAX_CHUNK_CHARS` with no sub-heading inside it.
   4. Sentence boundary (`[.!?]\s+`, plain regex) — used only when no earlier tier finds a
      breakpoint.
   5. Fixed-length cut at exactly `MAX_CHUNK_CHARS` — absolute last resort; logs
      `WARNING_FIXED_LENGTH_SPLIT_FALLBACK`, the one case where the boundary is genuinely arbitrary.

   Recursive: each split piece is re-evaluated until `<= MAX_CHUNK_CHARS`. Pieces from one section
   are tagged `chunk_index_within_section`/`section_chunk_count`.
10. **Chunk identity — structural, not positional.**
    `chunk_id = f"{doc_id}_{anchor_id}_{index_within_section}"` (e.g. `doc_xxx_2.1.1_0`).
    - `anchor_id` — the originating `section_tree` entry's `section_id`, used **verbatim** (no
      sanitization — `chunk_id` is never used as a filename/path segment). The preamble span uses
      the fixed literal `"preamble"`. A span formed by merging a degenerate collision span into a
      real neighbor uses the earliest (document-order) `section_id` among its `section_ids`.
    - `index_within_section` — 0-indexed, not zero-padded; the same value stored on the chunk record
      as `chunk_index_within_section` — one field, one source of truth.
    - Collision handling: `SECTION_IDS_UNIQUE` is WARNING-tier not FAIL (from "Stage 6"), so a
      document with a genuine duplicate `section_id` can reach this stage. Anchor resolution tracks
      how many prior entries already used that `section_id` and appends a disambiguating suffix
      (`-dup2`, `-dup3`, ...). `CHUNK_IDS_UNIQUE` remains the final safety net regardless.
    Why: a positional id (`doc_xxx_c0042`) renumbers every later chunk when one heading is inserted,
    invalidating every embedding/cache/eval-snapshot keyed by the old id; a structural id only
    changes for the section actually edited. A `CHUNKING_PIPELINE_VERSION` bump is still allowed to
    change assignments (no migration path designed) — but routine content edits no longer force a
    version-wide id churn.
11. **Validation suite.** New, chunk-set-level (not source-document-level — already validated by
    "Stage 6"). Reuses the Validation Severity Tiers convention. See finding-code table below.
    `CHUNK_COVERAGE_EXACT` validates an invariant the connected-chain construction already
    guarantees by design — a regression safety net, not a legitimate-gap tolerance (the earlier
    `GAP_TOLERANCE_CHARS` fudge-factor is removed for this reason: exact equality is provable, so no
    tolerance is needed). `CHUNK_NO_OVERLAP` stays a separate check since it pinpoints which pair of
    chunks disagrees, which the aggregate coverage check alone would not.
12. **Directory structure.**
    ```
    data/proposals/chunks/<doc_id>/chunks.json
    data/proposals/chunks/<doc_id>/chunk_validation_report.json     # always written
    ```
    Sibling to the existing `extracted/`, `quarantine/`, `validation_reports/`, `logs/`.
13. **Manifest updates.** Per the Manifest Update Convention and QUARANTINED-Reuse Convention: on
    success, `artifact_paths["chunks"]` + `["chunk_validation_report"]` are set, `status` stays
    `REGISTERED` (promotion to `ready_for_chunking` remains Stage 8's job). On FAIL, only
    `chunk_validation_report` is set, `status = QUARANTINED`, `error_code = "FATAL_CHUNKING_FAILED"`
    — meaning specifically "chunking could not complete for this document," not that
    `clean_text.json`/`metadata.json` are invalid.
14. **Logging.** Per the Logging Specification, this stage's own closed-vocabulary additions:
    `WARNING_CHUNK_BELOW_MINIMUM`, `WARNING_FIXED_LENGTH_SPLIT_FALLBACK`,
    `WARNING_SAME_PAGE_SECTION_COLLISION`, `WARNING_HEADING_OFFSET_NOT_RECOVERED`; ERROR code
    `FATAL_CHUNKING_FAILED`.
15. **Error handling.** Per-document `try`/`except`, one document's failure never blocks the batch.
    An unexpected exception → `QUARANTINED`, `FATAL_CHUNKING_FAILED` (the same code as a clean
    validation-FAIL, since both equally mean "chunking did not succeed" — unlike "Stage 6," which
    draws a two-code distinction because an unreadable artifact is a meaningfully different failure
    mode there). No retries (deterministic, local). Idempotent reruns skip any document where
    `"chunks" in record.artifact_paths` already, pending a future `--force` flag (not designed).

## Schema

`chunks.json` — one file per document, matching every prior stage's per-doc-directory convention:

```jsonc
{
  "doc_id": "doc_9f3a2b1c8e4d",
  "chunking_pipeline_version": "1.0.0",      // independent of the shared manifest pipeline_version
  "generated_at": "2026-07-19T12:00:00Z",
  "chunk_count": 87,
  "chunks": [
    {
      "chunk_id": "doc_9f3a2b1c8e4d_2.1.1_0", // structural: {doc_id}_{anchor section_id, verbatim}_{index_within_section}
      "doc_id": "doc_9f3a2b1c8e4d",           // redundant with the file's own path; self-contained record
      "text": "...",                          // exact substring [char_start, char_end) of the cumulative
                                               // document text, reconstructed from clean_text.json's pages
      "char_start": 40213,                    // same cumulative offset space clean_text.json already defines;
      "char_end": 41680,                      // adjacent chunks are exactly contiguous by construction
      "page_start": 34,                       // first/last page_number this char range touches;
      "page_end": 35,                         // equal unless the chunk spans a page boundary
      "section_ids": ["2.1.1"],               // list, not scalar — a same-page-collision merge can span >1 section
      "ancestor_section_ids": ["2", "2.1", "2.1.1"],  // root-to-leaf section_id chain, parallel to heading_path
                                               // but ids not titles — lets a consumer filter/aggregate structurally
      "heading_path": [                       // full ancestor chain, root to most specific, numbering-stripped
        "2. Project Background",              // titles only (Stage 5's own convention) — breadcrumb context
        "2.1 Climate Rationale",               // with no second section_tree lookup needed
        "2.1.1 Regional Impacts"
      ],
      "chunk_index_within_section": 0,        // 0-indexed; identical to the value embedded in chunk_id.
      "section_chunk_count": 3,               // A section never split is 0/1; increments only when
                                               // oversized-splitting multiplies one section into several pieces
      "is_appendix": false,                   // re-derived from heading_path via APPENDIX_RE
      "is_references": false,                 // re-derived from heading_path via REFERENCES_RE — never
                                               // trusts a persisted flag
      "has_table_content": true,              // page-level signal only — [page_start, page_end] intersects
                                               // metadata.json's structure.table_regions[].page
      "category": "climate",                  // denormalized from metadata.json.classification —
      "doc_type": "RRP",                      // avoids a second file read for "which document did this
      "title": "Climate Resilience..."        // chunk come from" (chunk_id -> doc_id -> page_number chain)
    }
  ]
}
```

`chunk_validation_report.json` — same shape as "Stage 6"'s own report (`overall_status`, `summary`
counts, `findings[]`), plus a `stats` block, purely for human debugging convenience (no new signal,
nothing gated on it):

```jsonc
"stats": {
  "coverage_percent": 100.0,             // always 100.0 when CHUNK_COVERAGE_EXACT passes; kept as an
                                          // explicit, human-scannable field anyway
  "avg_chunk_chars": 1423.5,
  "largest_chunk_chars": 2998,
  "smallest_chunk_chars": 312,
  "chunks_per_section": {"2.1.1": 3, "2.1.2": 1}   // keyed by anchor section_id — a quick way to spot
                                          // a section that split unexpectedly wide
}
```

**Finding codes** (Validation Severity Tiers convention):

| Code | Severity | Quarantine? | Meaning |
|---|---|---|---|
| `CHUNK_NON_EMPTY` | FAIL | Yes | every chunk's `text`, stripped, is non-empty |
| `CHUNK_OFFSETS_VALID` | FAIL | Yes | `char_start < char_end`, both within `[0, full_text_char_count]` |
| `CHUNK_NO_OVERLAP` | FAIL | Yes | no two chunks' `[char_start, char_end)` ranges overlap anywhere |
| `CHUNK_COVERAGE_EXACT` | FAIL | Yes | sorted chunk ranges union to exactly `[0, full_text_char_count)`, zero gap/overlap at every boundary |
| `CHUNK_IDS_UNIQUE` | FAIL | Yes | no duplicate `chunk_id` in the set |
| `CHUNK_PAGE_RANGE_VALID` | FAIL | Yes | `page_start <= page_end`, both correspond to real, non-excluded pages |
| `CHUNK_SIZE_WITHIN_MAX` | FAIL | Yes | every chunk `<= MAX_CHUNK_CHARS` (safety net — should be impossible by construction) |
| `CHUNK_SIZE_ABOVE_MIN` | WARNING | No | flags any chunk `< MIN_CHUNK_CHARS` that survived merging |
| `CHUNK_HEADING_PATH_VALID` | WARNING | No | every `section_id` in a chunk's `section_ids`/`ancestor_section_ids` exists in `section_tree` |

## Functions / Contracts

- `resolve_heading_offsets(clean_text) -> dict[section_id, offset]` — deterministic `str.find()`-based
  intra-page offset recovery per `section_tree` entry, with page-level fallback.
- `build_section_spans(clean_text, resolved_offsets) -> list[Span]` — one connected-chain span per
  `section_tree` entry, plus preamble handling.
- `split_oversized_spans(spans) -> list[Span]` — recursive, five-tier structure-first splitting of
  any span `> MAX_CHUNK_CHARS`.
- `merge_undersized_spans(spans) -> list[Span]` — adjacent, same-branch, backward-only merging of
  spans `< MIN_CHUNK_CHARS` (forward exception for the first span).
- `assign_chunk_ids(spans, doc_id) -> list[Span]` — assigns structural `chunk_id`s, with duplicate-
  anchor disambiguation.
- `assemble_chunk_records(spans, clean_text, metadata) -> list[dict]` — builds the full chunk schema
  per span, including denormalized doc fields and appendix/references/table tags.
- `validate_chunks(chunks, clean_text) -> ValidationReport` — runs the full finding-code suite,
  no-fail-fast.
- `write_chunk_validation_report(report, path)` — unconditional write, before the quarantine branch.
- `write_chunks(chunks, path)` — writes `chunks.json`, only reached on PASS/WARNING.
- `update_manifest(record, chunks_path, chunk_validation_report_path)` — sets `artifact_paths`,
  timestamps, and (on FAIL only) `status`/`error_code`.

## Self-Critique

1. Section-boundary precision is substantially improved but not perfect — any path through
   `resolve_heading_offsets` that fails (title altered by cleaning, or rejected by the plausibility
   guard) still falls back to the page-level snap.
2. Heading-detection quality is inherited wholesale from Stage 5, uncorrected — any Stage 5 false
   positive/negative propagates directly into a wrong chunk boundary here.
3. Residual false-positive risk in offset recovery: a body-text sentence mentioning a heading's exact
   title, positioned before the real heading, whose line happens to pass the length guard, is not
   fully eliminated (no dedicated test — constructing such a fixture is itself contrived). Two
   distinct sections sharing a generic title on different pages resolve correctly and independently
   (tested).
4. The narrower same-page-collision mechanism still cannot distinguish a genuine short sub-heading
   from an accidental Stage-5 over-detection when offset recovery fails for both — both are silently
   absorbed via forced merge.
5. Table handling is coarse — `has_table_content` is a page-level boolean; a chunk can mix
   low-information table rows with narrative prose with no separation, which would measurably hurt
   embedding quality once a downstream system embeds it. No row/cell data exists upstream to fix
   this here.
6. The sentence-boundary regex fallback (`[.!?]\s+`) is naive — misfires on abbreviations ("U.S.",
   "e.g.") and decimals ("2.5 million"); mitigated by being tier 4 of 5, not eliminated.
7. The sub-heading splitting tier only reuses Stage 5's single highest-confidence rule (markdown
   ATX), deliberately not its weaker tiers — a section whose embedded sub-structure is marked only by
   ALL-CAPS or numeric lines gets no benefit and falls through to weaker tiers. Precision-over-recall,
   not an oversight.
8. Structural chunk_ids improve edit-stability but introduce a new failure surface the old sequential
   scheme never had: duplicate-`section_id` collision handling (the `-dup2`/`-dup3` suffix) is new
   logic, tested, but a genuine complexity cost.
9. A `CHUNKING_PIPELINE_VERSION` bump still intentionally invalidates prior chunk_ids for any section
   whose split/merge assignment shifts, with no migration path — narrower blast radius than a
   positional scheme, but the tradeoff itself is unchanged.
10. Reusing `QUARANTINED` for a chunking-stage failure is a genuine semantic overload, even though
    documented — a reader who skips the caveat could misinterpret it as "this document's extraction
    is bad" and deprioritize an otherwise valid document. Mitigation is documentation only.
11. Split-before-merge ordering is deliberate but not proven-safe by construction — a tiny section
    followed by one needing its own split could behave differently under the reverse order; fixed
    order keeps behavior well-defined, backed by dedicated edge-case tests rather than a correctness
    proof.
12. `CHUNK_COVERAGE_EXACT` is only a *consistency* check on this design's own construction, not an
    independent proof of correctness against the source PDF — an internally-consistent but
    wrongly-anchored bug in offset resolution would still pass it.
13. No automated measure of chunk semantic coherence exists or can exist under a purely deterministic
    design — the only quality gate is the manual spot-check in Test Plan item 49, not an automated
    test.
14. Denormalized `category`/`doc_type`/`title` fields go stale with no versioning tie-back — if
    `metadata.json` is later corrected and this stage re-run for one document, existing chunks for
    that document become silently outdated until re-chunked.
15. Chunk size thresholds are explicitly not tied to any embedding model, because none has been
    chosen anywhere in this project — a deliberate, honest gap. Should be revisited against a real
    tokenizer/context window once a model is selected.

No finding above requires an architectural redesign — every one is an accepted, bounded limitation.

## Test Plan

`unittest`, no `fitz`, hand-built `clean_text.json`/`metadata.json`-shaped fixtures.

**Heading offset recovery:**
1. Exact `title` match on its `start_page` resolves to the enclosing line's start, converted to a
   document-level offset.
2. Two same-titled headings on one page resolve to distinct occurrences (cursor advances).
3. Title not found verbatim → falls back to the page-level snap, logs
   `WARNING_HEADING_OFFSET_NOT_RECOVERED`.
4. A match rejected by the plausibility guard also falls back — proves the false-positive guard
   fires, not just exists in prose.

**Boundary/span computation:**
5. Span derivation from a well-formed `section_tree` (3+ sections) confirms the connected-chain
   construction (`char_end` exactly equals the next span's `char_start`).
6. Preamble span when content precedes the first heading.
7. Whole-document-as-one-span when `section_tree` is empty.
8. Same-page collision produces a degenerate span only when offset recovery fails for one of the
   colliding entries.
9. Degenerate span is merge-eligible regardless of section branch.

**Size policy / splitting:**
10. Paragraph-boundary split lands at the last `\n\n` before `TARGET_CHUNK_CHARS`.
11. Sub-heading-boundary split fires on an embedded markdown ATX line before falling to list/sentence
    tiers.
12. List-item-boundary split fires only when a single paragraph exceeds `MAX_CHUNK_CHARS` with no
    embedded sub-heading.
13. Sentence-boundary split fires only when no paragraph/sub-heading/list markers exist in-window.
14. Fixed-length last-resort split fires only when no earlier tier finds a breakpoint, and logs
    `WARNING_FIXED_LENGTH_SPLIT_FALLBACK`.
15. Recursive re-splitting: a still-oversized split piece splits again.
16. A split never crosses a `section_tree` boundary, including at the sub-heading tier.
17. `chunk_index_within_section`/`section_chunk_count` correctly assigned across a 3-way split.

**Merging:**
18. An undersized trailing span merges backward into its immediate predecessor.
19. The first span in a document, if undersized, merges forward into the following large section.
20. Merge across a top-level branch boundary never happens, even when the neighbor is tiny.
21. Merge across an appendix/references boundary never happens.
22. An already-`>= MIN_CHUNK_CHARS` span is never pulled into a merge.
23. A document with one small, isolated section keeps it as-is, flagged `CHUNK_SIZE_ABOVE_MIN`
    WARNING, not dropped.

**Chunk identity:**
24. `chunk_id` format matches `{doc_id}_{anchor_id}_{index_within_section}` exactly, `anchor_id`
    used verbatim (dots preserved).
25. Rerun on identical input + identical `CHUNKING_PIPELINE_VERSION` → byte-identical chunk_ids.
26. Edit-stability: inserting a new heading near the start of a fixture leaves every chunk_id for
    unaffected later sections byte-identical; only affected section(s) change.
27. Duplicate `section_id`s produce disambiguated, non-colliding anchors (`-dup2`, `-dup3`, ...).
28. The preamble span's chunk_id uses the fixed literal anchor `"preamble"`.

**Appendix/references/table tagging:**
29. `is_appendix`/`is_references` correctly re-derived from `heading_path` via the shared regexes.
30. `has_table_content` true only when the chunk's page range intersects a flagged table page.
31. `ancestor_section_ids` correctly walks the `parent_section` chain root-to-leaf.

**Integration** (fixture `clean_text.json` + `metadata.json`, minimal `ManifestRecord`, call the
orchestrator, reload outputs):
32. `chunks.json` created with the documented top-level shape.
33. `chunk_validation_report.json` always written, for both a passing and a Critical-failing fixture,
    including the `stats` block.
34. Manifest updated correctly on success (`artifact_paths` set, `status` stays `REGISTERED`).
35. Manifest updated correctly on Critical failure (`QUARANTINED`, `FATAL_CHUNKING_FAILED`, `chunks`
    absent, `chunk_validation_report` present).

**Determinism / reruns:**
36. Full pipeline rerun on the same fixture → byte-identical `chunks.json` (excluding `generated_at`).
37. A `CHUNKING_PIPELINE_VERSION` bump is permitted to change chunk_ids (documents the expectation,
    not equivalence).

**Edge cases:**
38. Empty `section_tree` → single preamble span, flows through splitting normally.
39. Every section oversized → all get split, none skipped.
40. Every section undersized → merges collapse them where legal, remainder kept.
41. A section spans an excluded-then-resumed page run (zero contribution from the excluded page).
42. An appendix section immediately follows the main body with no gap — both tagged, never merged.
43. A table-containing page produces a chunk flagged `has_table_content: true`, table text intact.
44. Two identically-titled headings on different pages each resolve independently and correctly.

**Validation report:**
45. Mixed-severity fixture produces at least one FAIL, one WARNING; confirms `chunks.json` is NOT
    written when any FAIL is present.
46. `summary.pass + summary.warning + summary.fail == len(findings)`.
46a. `CHUNK_COVERAGE_EXACT` fails (Critical) on a fixture with a deliberately introduced gap or
    overlap — the negative-case test for the strict coverage check.

**Immutability:**
47. `clean_text.json` byte-identical on disk before/after the stage runs.
48. `metadata.json` byte-identical on disk before/after the stage runs.

**Real corpus verification (once implemented):**
49. Run against the up-to-6 real documents — spot-check chunk count plausibility per page count,
    `CHUNK_COVERAGE_EXACT` passes with `coverage_percent == 100.0`, real appendix/references
    correctly tagged, and a handful of resolved heading offsets spot-checked by eye.

## Phase 1 additions (2026-11-23)

* Merge: a heading-only span merges forward into the content it introduces (even across a top-level branch); other undersized
  spans merge forward within their branch.
* Split: cuts are made at sentence ends where possible, a piece is at least `MIN_CHUNK_CHARS`, and a line-break tier keeps table rows whole.
* `drop_duplicate_spans`: a span whose whitespace-normalised text equals an earlier span of the same document is dropped (first copy kept).
* `drop_heading_only_spans`: a span under `MIN_CHUNK_CHARS` whose every non-empty line is a Markdown heading is dropped.
* Both drops record their `(start, end)` ranges in the chunk validation report (`dropped_duplicate_ranges`), and `CHUNK_COVERAGE_EXACT`
  accepts a gap only if it is a recorded range, so coverage of the document is still proved.
* Known effect: merging a heading into the next chunk can lower that chunk's retrieval score for questions the passage answers
  (`reports/evidence/judging/rank1_investigation.txt`).
