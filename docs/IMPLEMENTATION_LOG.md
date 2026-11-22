# Implementation Log

Chronological, one entry per stage. Files/functions verified against the current repo state
(`scripts/`, `tests/`); revision history extracted from the design plan's own "Conflicts Found &
Resolved" / round 2 / round 3 narration. This log is a historical record of the ingestion-phase
build (Stages 4–7); per-stage counts below are each stage's own test file run in isolation. The
full current suite across all stages (0–21) is **481 passing tests** (`python -m pytest`).

## Stage 4 — Cleaning & Normalization
- Files: `scripts/stage4_cleaning.py` (created), `tests/test_stage4_cleaning.py` (created),
  `scripts/stage2_extraction.py` (modified — narrow bug fix)
- Functions added: normalize_whitespace, repair_dehyphenation, repair_encoding,
  remove_headers_footers, assemble_clean_text, build_clean_text, write_clean_text, clean_document,
  run_stage4
- Tests: 20/20 passing
- Manifest fields touched: `artifact_paths["clean_text"]`, `started_at`, `completed_at`,
  `pipeline_version`; `status`/`error_code` only on failure (`QUARANTINED`/`FATAL_UNREADABLE`)
- Revisions: cleaning pipeline order changed from the original draft — `repair_encoding` moved
  before `remove_headers_footers` (final order: normalize_whitespace -> repair_dehyphenation ->
  repair_encoding -> remove_headers_footers -> assemble_clean_text) so header/footer line
  comparison runs on encoding-normalized text; a ligature-encoded header on one page wouldn't
  otherwise string-match its ASCII twin on another.

## Stage 5 — Structural Tagging
- Files: `scripts/stage5_structure.py`, `tests/test_stage5_structure.py`
- Functions added: detect_headings, assign_heading_levels, generate_section_ids,
  build_section_tree, detect_appendices, detect_reference_sections, update_clean_text,
  load_font_info_by_page, tag_document, run_stage5
- Tests: 28/28 passing
- Manifest fields touched: none new — extends `clean_text.json` in place (adds `section_tree`,
  per-page `headings`); `started_at`/`completed_at`/`pipeline_version` stamped every run;
  `status`/`error_code` only on failure
- Revisions:
  - Reversed a prior draft's decision to avoid reading `raw_extraction.json` — the font-emphasis
    heading-detection tier requires `font_info`, which only exists there, so Stage 5 reads it
    read-only for that one signal.
  - Used `raw_extraction.json`'s real field names (`max_font_size`, `bold_if_any`) instead of the
    architecture doc's illustrative (`size`, `bold`) — the real, already-approved Stage 2 output
    takes precedence over the doc's example.
  - Dropped a prior draft's `is_appendix`/`is_references` fields on `section_tree` entries —
    `clean_text.json`'s schema is closed at 5 fields; appendix/reference detection is surfaced via
    logging instead of a new persisted field.
  - `title` convention fixed to always be numbering-stripped, resolving an inconsistency between
    the architecture doc's own two illustrative examples.

## Stage 6 — Validation & Metadata Assembly
- Files: `scripts/stage6_validation.py`, `tests/test_stage6_validation.py`
- Functions added: validate_artifacts, validate_manifest, validate_pages, validate_text_volume,
  validate_offsets, validate_sections, resolve_metadata, assemble_validation_report,
  gate_metadata_generation, write_validation_report, write_metadata, update_manifest,
  validate_document, run_stage6
- Tests: 75/75 passing
- Manifest fields touched: `artifact_paths["metadata"]`, `artifact_paths["validation_report"]`,
  `doc_type`, `started_at`/`completed_at`/`pipeline_version`; `status` stays `REGISTERED` on
  PASS/WARNING, `QUARANTINED` + `error_code="FATAL_VALIDATION_FAILED"` only on a Critical finding
- Revisions:
  - Severity model changed from an implicit near-all-FAIL default to an explicit two-tier
    Critical/Recoverable split (round 2) — a review's guiding principle ("only quarantine when
    downstream chunking would become unsafe or impossible") reclassified most checks
    (`RAW_EXTRACTION_PATH_VALID`, `DOC_ID_CONSISTENT`, `CATEGORY_PRESENT`, `SOURCE_PATH_EXISTS`,
    `PIPELINE_VERSION_PRESENT`, `FULL_TEXT_CHAR_COUNT_CONSISTENT`, all four `SECTION_*` checks)
    from FAIL to WARNING; only checks protecting offset/page-anchored citation grounding stayed
    Critical.
  - `validate_document_integrity` split into `validate_artifacts` (JSON readability) and
    `validate_manifest` (record completeness) (round 2) — two genuinely unrelated concerns with
    different failure modes had been merged into one function.
  - `validate_metadata_resolution` renamed to `resolve_metadata_fields` in the design (round 3,
    later settled as `resolve_metadata` in the shipped code) — the function *produces*
    title/doc_type fields rather than validating pre-existing ones, so the original name was
    misleading even though its behavior was already correct.
  - `validation.status` field name kept as `status` (a review asked for `validation_result` to
    avoid overlap with Stage 8's `ready_for_chunking`) — only the *values* changed, to
    `PASS`/`WARNING`, since the architecture doc's schema names the field `status` explicitly.
  - `summary` (pass/warning/fail counts) added to `validation_report.json` (round 3) — a pure
    rollup of `findings[]`, added for scannability.
  - Manifest mutation isolated to `validate_document` only (round 3) — every other validator is a
    pure function; enforced by a dedicated regression test.

## Stage 7 — Semantic Chunking
- Files: `scripts/stage7_chunking.py`, `tests/test_stage7_chunking.py`
- Functions added: resolve_heading_offsets, build_section_spans, split_oversized_spans,
  merge_undersized_spans, assign_chunk_ids, assemble_chunk_records, validate_chunks, write_chunks,
  write_chunk_validation_report, update_manifest, chunk_document, run_stage7
- Tests: 54/54 passing
- Manifest fields touched: `artifact_paths["chunks"]`, `artifact_paths["chunk_validation_report"]`,
  `started_at`/`completed_at`/`pipeline_version`; `status` stays `REGISTERED` on PASS/WARNING,
  `QUARANTINED` + `error_code="FATAL_CHUNKING_FAILED"` only on a Critical finding
- Revisions:
  - `chunk_id` format changed from sequential `f"{doc_id}_c{chunk_index:04d}"` to structural
    `f"{doc_id}_{anchor_section_id}_{index_within_section}"` (round 2) — a positional index is
    unstable under document edits (inserting one heading renumbers every later chunk); a
    structural id only changes when that specific section changes.
  - Added deterministic `resolve_heading_offsets()` (`str.find()`-based intra-page offset
    recovery) (round 2) — the original design accepted page-level granularity only; a review
    pushed back since sub-page precision is recoverable from already-produced text without
    touching Stage 5 or the PDF.
  - `CHUNK_COVERAGE_EXACT` strengthened from a tolerance-based check (`GAP_TOLERANCE_CHARS`) to a
    strict union-equals-document-span check (round 2) — span construction changed to a connected
    chain (`span[i].char_end == span[i+1].char_start`), making an exact-equality check possible.
  - Added a sub-heading (markdown ATX) splitting tier to oversized-section splitting, before
    list/sentence tiers (round 2) — addresses sections oversized because of embedded sub-structure
    that never became its own `section_tree` entry.
  - `fragment_index`/`fragment_count` renamed to `chunk_index_within_section`/`section_chunk_count`
    (round 2) — unified with the value embedded in the new structural `chunk_id`, one source of
    truth instead of two parallel counters.
  - Added `ancestor_section_ids` (round 2) — root-to-leaf `section_id` chain parallel to
    `heading_path`, for structural filtering without a title-string comparison.
  - Dropped dot-to-underscore sanitization of `anchor_id` in `chunk_id` (round 3) — `chunk_id` is
    never used as a filename/path segment, only stored/compared as an opaque string, so
    sanitization was unneeded complexity.
