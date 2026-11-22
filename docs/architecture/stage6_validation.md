# Stage 6 — Validation & Metadata Assembly

See `docs/pipeline_principles.md` for shared conventions.

## Scope

Stage 6 validates each document's Stage 0–5 outputs and assembles `metadata.json` for documents
that pass. Input is `clean_text.json` + `raw_extraction.json` (read-only, already-existing
`artifact_paths`) plus the `manifest.json` record itself — no PDF is ever reopened (Design
Philosophy). Output is exactly three artifacts: `metadata.json` (only on PASS/WARNING),
`validation_reports/<doc_id>_validation.json` (always, every outcome), and
`quarantine/<doc_id>/reason.json` (only on FAIL), plus the corresponding `manifest.json` updates.
Per the architecture doc's own numbering this covers its Stage 6 (Validation) and Stage 7 (Metadata
Assembly); this project builds them as one implementation unit, labeled 6A/6B below, per the "Stage
N" Numbering Convention. Out of scope, not designed here: chunking, embeddings, retrieval, ranking,
annotation, evaluation, batch summary, and Stage 8's `ready_for_chunking` manifest promotion.

## Pipeline

One pass per document, entirely in memory except for the three output writes. No fail-fast: every
validator that can run, always runs, to completion, regardless of what an earlier validator found —
`validation_report.json` always shows every reachable check's outcome in one pass. The one
exception is a hard data precondition, not a stylistic short-circuit: `validate_pages`,
`validate_offsets`, and `validate_sections` operate on the parsed `clean_text` dict, so they are
skipped (not failed) when `validate_artifacts` finds `clean_text.json` itself unreadable. This
covers the two genuinely different concerns "can the JSON artifacts be read" and "is the manifest
record itself complete" as separate functions with separate inputs and severities.

```
validate_artifacts(record, clean_text, raw_extraction)
        │  ARTIFACTS_READABLE / CLEAN_TEXT_SCHEMA_VALID / CLEAN_TEXT_PATH_VALID / RAW_EXTRACTION_PATH_VALID
        ▼
validate_manifest(record)   — always runs; needs only the ManifestRecord, not parsed JSON
        │  DOC_ID_CONSISTENT* / CATEGORY_PRESENT / SOURCE_PATH_EXISTS / PIPELINE_VERSION_PRESENT
        │  (*DOC_ID_CONSISTENT needs clean_text — omitted, not failed, if it never parsed)
        ▼
   clean_text parsed successfully? ──no──┐
        │yes                             │
        ▼                                │
validate_pages(clean_text, record)       │
        ▼                                │
validate_offsets(clean_text)             │
        ▼                                │
validate_sections(clean_text)            │
        ▼                                │
resolve_metadata_fields(clean_text, original_filename)   │  (computes + returns title/doc_type
        │                                │                 result alongside its findings)
        └────────────────────────────────┘
        ▼
compute overall_status + findings summary (pass/warning/fail counts)
        ▼
write_validation_report()   — always runs here, before the branch below, regardless of
        │                     overall_status, including the total-artifact-failure case
        ▼
   any Critical/FAIL finding? ──yes──▶ write_quarantine_reason() ──▶ update_manifest() [QUARANTINED]
        │no (PASS or WARNING only)
        ▼
assemble_metadata(...) → write_metadata(metadata) → update_manifest(...) [status stays REGISTERED —
                                                       the only function that mutates `record`]
```

## Design Decisions

1. **Stage grouping.** Stage 6 (Validation) and Stage 7 (Metadata Assembly), per the architecture's
   numbering, are built as one implementation unit — labeled 6A/6B below — keeping the
   architecture's pass/fail gate between them exactly.
2. **`ready_for_chunking`** is not set by this stage — expressed instead via `metadata.json`'s own
   `validation.status`; manifest `status` stays `REGISTERED` on PASS/WARNING, `QUARANTINED` only on
   FAIL. *Why:* that transition is Stage 8's job.
3. **Title extraction skips the PDF-metadata step**, starting directly at a regex match on
   `clean_text.json` pages 1–3; `none_found` is a valid outcome. *Why:* no PDF reopening past
   Stage 2 (Design Philosophy), and no prior stage cached a PDF-native title.
4. **`table_regions[].approx_rows` is always `null`.** *Why:* Stage 2 never captured per-table row
   counts; a pipe-line count was rejected as false precision (separator/wrapped rows make it
   meaningless).
5. **`doc_type` resolution is implemented here**, via the architecture's §4a precedence, written to
   both `manifest.json.doc_type` and `metadata.json.classification`. *Why:* never implemented
   upstream — impossible before Stage 2's text extraction exists.
6. **`original_filename` = `Path(source_path).name`.** *Why:* matches the real, frozen Stage 0
   implementation, not the architecture doc's illustrative `doc_id__`-prefixed example.
7. **`quarantine/<doc_id>/reason.json` is written on every FAIL outcome** — an existing, documented
   artifact from the architecture's own artifact table.
8. **`provenance.ingested_at`** is populated from this stage's own `started_at` stamp. *Why:*
   Stage 0's original timestamp isn't retained anywhere by the time this stage runs.
9. **`validation.status` keeps the field name `status`** (matching the architecture's literal
   schema), values restricted to `"PASS"`/`"WARNING"` — never `"ready_for_chunking"`. *Why:* avoids
   overlap with Stage 8's terminology without deviating from the documented field name.
10. **Validators are split by concern** — `validate_artifacts` (JSON-artifact usability) vs.
    `validate_manifest` (manifest-record completeness): different inputs, failure modes, severities.
11. **`resolve_metadata_fields`** computes the title/doc-type precedence and returns two Recoverable
    findings (`DOC_TYPE_UNRESOLVED`, `TITLE_EXTRACTION_FALLBACK_USED`) alongside its result, so
    resolution joins the same full-validation pass as every other check; `assemble_metadata` reuses
    this computed result rather than recomputing it.
12. **Validators are pure functions** — findings only, no mutation. `validate_document` is the sole
    function that mutates `ManifestRecord`, and only once, after every reachable validator finishes.
13. **Severity model:** two tiers per the Validation Severity Tiers convention; this stage's own
    code-to-severity assignment (below) is stage-specific and kept in full.
14. **No `NO_APPENDIX_DETECTED`-style check added.** *Why:* most legitimate documents lack an
    appendix — an always-firing check on the common case would be fabricated, not real, signal.

## Validation Report Schema

```jsonc
{
  "doc_id": "doc_...",
  "generated_at": "2026-07-19T12:00:00Z",
  "overall_status": "PASS",              // PASS | WARNING | FAIL — FAIL iff any finding is Critical
  "summary": {                           // rollup computed directly from findings[] below
    "pass": 18,
    "warning": 3,
    "fail": 0
  },
  "findings": [
    {
      "code": "PAGE_COUNT_MATCH",
      "description": "clean_text.json page count (148) matches manifest page_count (148)",
      "severity": "PASS",
      "doc_id": "doc_..."                 // per-finding doc_id — makes each finding self-contained
                                           // if ever read out of file context
    }
  ]
}
```

Written unconditionally, for every document this stage processes, in every outcome — including the
extreme case where `validate_artifacts` finds `clean_text.json` completely unreadable, every
content-dependent validator is skipped, and the report shows only `ARTIFACTS_READABLE: FAIL` plus
whatever `validate_manifest` returned (`summary.fail >= 1`). There is no code path where a processed
document ends up with no validation report.

Closed finding-code vocabulary: every validator emits exactly one finding per its codes, every run
(mixed PASS/WARNING/FAIL in one report is a complete audit trail, not a sparse problems-only list).
Implemented as one frozen constant, `VALIDATION_CODES: FrozenSet[str]`, defined once in the Stage 6
module and imported everywhere a finding is constructed — a finding whose `code` isn't in that set
is a bug in the validator that produced it, not a legitimate new signal.

The table below is the single canonical source of truth for code → severity → quarantine behavior:

| Code | Validator | Severity | Quarantine? |
|---|---|---|---|
| `ARTIFACTS_READABLE` | validate_artifacts | FAIL | Yes |
| `CLEAN_TEXT_SCHEMA_VALID` | validate_artifacts | FAIL | Yes |
| `CLEAN_TEXT_PATH_VALID` | validate_artifacts | FAIL | Yes |
| `RAW_EXTRACTION_PATH_VALID` | validate_artifacts | WARNING | No |
| `DOC_ID_CONSISTENT` | validate_manifest | WARNING | No |
| `CATEGORY_PRESENT` | validate_manifest | WARNING | No |
| `SOURCE_PATH_EXISTS` | validate_manifest | WARNING | No |
| `PIPELINE_VERSION_PRESENT` | validate_manifest | WARNING | No |
| `PAGE_COUNT_MATCH` | validate_pages | WARNING | No |
| `PAGE_NUMBERING_MONOTONIC` | validate_pages | FAIL | Yes |
| `EXCLUDED_PAGES_VALID` | validate_pages | FAIL | Yes |
| `OFFSET_ORDERING_VALID` | validate_offsets | FAIL | Yes |
| `OFFSET_CONTIGUOUS` | validate_offsets | FAIL | Yes |
| `OFFSET_NO_OVERLAP` | validate_offsets | FAIL | Yes |
| `FULL_TEXT_CHAR_COUNT_CONSISTENT` | validate_offsets | WARNING | No |
| `SECTION_IDS_UNIQUE` | validate_sections | WARNING | No |
| `SECTION_PARENT_EXISTS` | validate_sections | WARNING | No |
| `SECTION_NO_CYCLES` | validate_sections | WARNING | No |
| `SECTION_HEADING_ANCHORS_VALID` | validate_sections | WARNING | No |
| `DOC_TYPE_UNRESOLVED` | resolve_metadata_fields | WARNING | No (emitted only when `doc_type_confidence == "unresolved"`) |
| `TITLE_EXTRACTION_FALLBACK_USED` | resolve_metadata_fields | WARNING | No (emitted only when `title_extraction_method != "regex_title_field"`) |

**Assignment test:** would this violation make downstream chunking unsafe/impossible, or only
reduce metadata completeness/precision? Artifact-readability and page/offset-integrity checks are
Critical because they protect the page-anchored `char_start`/`char_end` citation-grounding
guarantee chunking depends on. Everything else — manifest completeness, `raw_extraction`'s path,
the `doc_id` cross-check, the entire `section_tree` hierarchy layer, doc_type/title resolution — is
enrichment a chunker can operate safely without, so it's Recoverable.
`FULL_TEXT_CHAR_COUNT_CONSISTENT` is Recoverable despite being offset-adjacent because it's a
derived whole-document summary stat, never itself used as a citation anchor (citations are always
`page_number` + that page's own `char_start`/`char_end`).

`quarantine/<doc_id>/reason.json` — written only when `overall_status == FAIL`:

```jsonc
{
  "doc_id": "doc_...",
  "quarantined_at": "2026-07-19T12:00:00Z",
  "error_code": "FATAL_VALIDATION_FAILED",
  "failing_checks": ["OFFSET_CONTIGUOUS", "PAGE_NUMBERING_MONOTONIC"],
  "validation_report_path": "data/proposals/validation_reports/<doc_id>_validation.json"
}
```

New manifest-level `error_code`: `FATAL_VALIDATION_FAILED` — "one or more Critical structural/
offset invariants failed" (distinct from `FATAL_UNREADABLE`, which means the PDF/JSON won't open at
all). A closed, enumerated addition, matching the existing code table's granularity — specific
failing checks live in `reason.json`/`validation_report.json`, not the manifest itself. Per the
QUARANTINED-Reuse Convention, this stage's use of `QUARANTINED` means only "Stage 6 specifically
could not complete for this document" — upstream artifacts remain valid.

## Metadata Schema

Exactly the architecture's §4 schema — no invented fields. Fields uncomputable under this stage's
constraints are present with honestly-scoped values, never fabricated:

```jsonc
{
  "doc_id": "doc_...",
  "title": "...",                          // regex-extracted or largest-heading; see Design Decisions
  "title_extraction_method": "regex_title_field",  // pdf_metadata (unreachable) | regex_title_field |
                                                     // largest_heading | manual_override | none_found
  "provenance": {
    "original_filename": "...",            // Path(source_path).name
    "sha256": "...",                       // doc_id with the "doc_" prefix stripped
    "source_path": "...",                  // record.source_path, verbatim
    "ingested_at": "...",                  // this stage's own started_at
    "ingestion_pipeline_version": "..."    // record.pipeline_version
  },
  "classification": {
    "category": "...",                     // record.category, verbatim (folder-derived, Stage 0)
    "doc_type": "RRP",                     // resolved here, per §4a
    "doc_type_confidence": "title_page_match"  // title_page_match | filename_pattern | unresolved
  },
  "structure": {
    "page_count": 148,                     // record.page_count (Stage 1's PyMuPDF count, cached)
    "extracted_page_count": 148,           // len(clean_text["pages"])
    "excluded_pages": [112, 113],          // [p.page_number for p in pages if p.is_excluded]
    "has_tables_detected": true,           // any page's raw_extraction table_bboxes non-empty
    "table_regions": [{"page": 34, "approx_rows": null}],  // always null
    "sections_flagged": [
      {"type": "appendix", "start_page": 130},
      {"type": "references", "start_page": 145}
    ]
  },
  "validation": {
    "status": "PASS",                      // PASS | WARNING — never "ready_for_chunking" or "FAIL"
    "validation_report_path": "data/proposals/validation_reports/<doc_id>_validation.json"
  },
  "future_compatibility": {
    "language": "en",                      // fixed default — no language detection designed here
    "ocr_applied": false,                  // fixed default — no OCR anywhere in this pipeline
    "schema_version": "1.0"
  }
}
```

- `title`: regex step first (`Project Title:`, `Title:`, `Name of Project:` on pages 1–3), then
  largest-heading fallback (lowest `section_level`, ties broken by lowest `start_page`), then
  `none_found`.
- `sections_flagged`: re-applies Stage 5's own `APPENDIX_RE`/`REFERENCES_RE` against
  `section_tree[].title` rather than trusting a persisted flag.

### Manifest Update Rules

Per the Manifest Update Convention, only existing `DocumentStatus` values are used (`REGISTERED`,
`QUARANTINED`) — `READY_FOR_CHUNKING` and `FAILED` are never set by this stage. Stage-specific
detail:

- On success (PASS or WARNING): `record.artifact_paths["metadata"]` and
  `record.artifact_paths["validation_report"]` are set; `record.doc_type` is set from the §4a
  precedence result; `record.status` stays `REGISTERED`; `record.error_code` stays `None`.
- On failure (FAIL): `record.artifact_paths["validation_report"]` is set (always written);
  `record.artifact_paths["metadata"]` is never set; `record.status = QUARANTINED`;
  `record.error_code = "FATAL_VALIDATION_FAILED"`.

## Functions

```python
def validate_artifacts(record: ManifestRecord, clean_text: Optional[Dict], raw_extraction: Optional[Dict]) -> List[Dict]:
    """JSON-artifact usability only. Runs first; a Critical finding here skips validate_pages/offsets/sections/resolve_metadata_fields. Pure."""

def validate_manifest(record: ManifestRecord) -> List[Dict]:
    """ManifestRecord fields only -- always runs regardless of artifact readability. Pure."""

def validate_pages(clean_text: Dict, record: ManifestRecord) -> List[Dict]:
    """Page-count/numbering/excluded-page invariant checks."""

def validate_offsets(clean_text: Dict) -> List[Dict]:
    """char_start/char_end ordering, contiguity, overlap, and full-text count consistency checks."""

def validate_sections(clean_text: Dict) -> List[Dict]:
    """Independently re-verifies section_tree's own invariants (ids, parents, cycles, heading anchors)."""

def resolve_doc_type(clean_text: Dict, original_filename: str) -> Tuple[str, str]:
    """§4a precedence: title-page phrase match on pages 1-3, then filename fallback, then ('unknown', 'unresolved'). Deterministic."""

def resolve_title(clean_text: Dict) -> Tuple[str, str]:
    """Regex field match on pages 1-3 ('regex_title_field'), then largest-heading fallback, then ('', 'none_found')."""

def resolve_metadata_fields(clean_text: Dict, original_filename: str) -> Tuple[List[Dict], Tuple[str, str], Tuple[str, str]]:
    """Calls resolve_title/resolve_doc_type; returns their results plus the two conditional Recoverable findings. Pure."""

def assemble_metadata(record: ManifestRecord, clean_text: Dict, raw_extraction: Dict, title_result: Tuple[str, str], doc_type_result: Tuple[str, str], validation_result: str, validation_report_path: str) -> Dict:
    """Builds metadata.json per the schema above, only when overall_status is PASS/WARNING. Reuses already-computed results; touches neither disk nor record."""

def write_metadata(metadata: Dict) -> Path:
    """Writes metadata.json to EXTRACTED_DIR/<doc_id>/metadata.json."""

def write_validation_report(record: ManifestRecord, findings: List[Dict], overall_status: str) -> Path:
    """Writes validation_reports/<doc_id>_validation.json unconditionally, including summary counts. Called before the quarantine branch."""

def write_quarantine_reason(record: ManifestRecord, findings: List[Dict], validation_report_path: str) -> Path:
    """Writes quarantine/<doc_id>/reason.json, only on FAIL. Structured (error_code + failing_checks), never free text."""

def validate_document(record: ManifestRecord) -> None:
    """Orchestrates one document per Pipeline above; the sole function that mutates `record`. Unexpected exception -> QUARANTINED, error_code='FATAL_UNREADABLE' (distinct from 'FATAL_VALIDATION_FAILED')."""

def run_stage6() -> None:
    """Loads manifest, processes every REGISTERED record with 'clean_text' in artifact_paths, saves manifest once at the end."""
```

## Self-Critique

1. **Can any validator produce nondeterministic output?** No — every check is a pure comparison
   over already-loaded JSON structures (counts, offsets, string equality, regex, graph-walk) or the
   fixed `future_compatibility` defaults. Only `generated_at`/`ingested_at` vary between runs, and
   both are explicitly excluded from the rerun-determinism tests.
2. **Could validation accidentally modify document content?** No — `clean_text.json` and
   `raw_extraction.json` are opened read-only and never written back; verified by tests 50 and 51.
3. **Can Stage 8 consume the outputs without reopening PDFs?** Yes — `metadata.json` carries
   `validation.status` (`PASS`/`WARNING`, never the ambiguous `ready_for_chunking` string), artifact
   paths via the manifest record, doc_type, and title. Stage 8's own job is purely a manifest-status
   flip needing no further PDF or content access.
4. **Are validation failures reproducible?** Yes — same fixture produces same findings, severities,
   and `overall_status` (tests 46–47); the 21-code vocabulary is closed and every reachable
   validator always emits every one of its codes, with the three conditionally-emitted codes
   (`DOC_ID_CONSISTENT`, `DOC_TYPE_UNRESOLVED`, `TITLE_EXTRACTION_FALLBACK_USED`) conditional on a
   fixed, deterministic precondition, never on anything nondeterministic.
5. **Did any retrieval logic enter Stage 6?** No — nothing ranks, scores, embeds, or retrieves;
   every function either checks an existing invariant or reshapes already-computed values into
   `metadata.json`'s documented fields.
6. **Is the full-validation, no-fail-fast philosophy actually preserved?** Yes — see Pipeline's
   precondition note; test 22 covers `validate_manifest` still running when `validate_artifacts`
   finds the JSON unreadable.
7. **Does downgrading most checks to Recoverable make the FAIL gate too weak to be useful?** No —
   the checks that remain Critical (`ARTIFACTS_READABLE`, `CLEAN_TEXT_SCHEMA_VALID`,
   `CLEAN_TEXT_PATH_VALID`, `PAGE_NUMBERING_MONOTONIC`, `EXCLUDED_PAGES_VALID`,
   `OFFSET_ORDERING_VALID`, `OFFSET_CONTIGUOUS`, `OFFSET_NO_OVERLAP`) are precisely the ones
   protecting page-anchored, offset-correct citation grounding plus basic readability. Every
   Recoverable check governs an enrichment layer a chunker can safely operate without.
8. **Is manifest mutation actually isolated to one function?** Yes, per Design Decision 12; test 45a
   is the regression guard, snapshotting the record before/after every validator call.
9. **Is the finding-code vocabulary actually closed, or just documented as closed?** Enforced via a
   single frozen constant (`VALIDATION_CODES`), not just prose — test 40a makes constructing a
   finding with an unrecognized code an immediate, loud test failure rather than silent drift.

No open weaknesses requiring redesign.

## Test Plan

`unittest`, no `fitz`, no PDF fixtures — hand-built `clean_text.json`/`raw_extraction.json`-shaped
dicts and `ManifestRecord` instances matching real Stage 0–5 output shapes.

**Page validation**
- `test_validate_pages_count_match_pass` — page counts match → PASS
- `test_validate_pages_count_mismatch_warning` — counts differ → WARNING, not FAIL
- `test_validate_pages_numbering_gap_fails` — numbering gap → `PAGE_NUMBERING_MONOTONIC` FAIL
- `test_validate_pages_excluded_page_invalid_offsets_fails` — excluded page, `char_start != char_end` → `EXCLUDED_PAGES_VALID` FAIL

**Offset validation**
- `test_validate_offsets_valid_pass` — well-formed fixture → all four offset checks PASS
- `test_validate_offsets_overlap_fails` — overlapping page ranges → `OFFSET_NO_OVERLAP` FAIL
- `test_validate_offsets_gap_fails` — gap between pages → `OFFSET_CONTIGUOUS` FAIL
- `test_validate_offsets_char_count_mismatch_warning` — `full_text_char_count` mismatch → WARNING, not FAIL

**Hierarchy validation**
- `test_validate_sections_valid_hierarchy_pass` — well-formed 3-level tree → all four PASS
- `test_validate_sections_duplicate_ids_warning` — duplicate `section_id` → WARNING
- `test_validate_sections_missing_parent_warning` — dangling `parent_section` reference → WARNING
- `test_validate_sections_cycle_detected_warning` — cyclic parent references → WARNING
- `test_validate_sections_invalid_heading_anchor_warning` — heading references unknown/mismatched section → WARNING
- `test_validate_sections_hierarchy_issue_does_not_block_metadata` — lone `SECTION_NO_CYCLES` violation still yields `metadata.json`

**Artifact validation**
- `test_validate_artifacts_unreadable_json_fails` — invalid `clean_text.json` → `ARTIFACTS_READABLE` FAIL, content validators not called
- `test_validate_artifacts_precondition_not_fail_fast` — `validate_manifest` still runs/reports despite the unreadable artifact
- `test_validate_artifacts_missing_schema_fails` — valid JSON missing `pages` key → `CLEAN_TEXT_SCHEMA_VALID` FAIL
- `test_validate_artifacts_clean_text_path_missing_fails` — nonexistent clean_text path → `CLEAN_TEXT_PATH_VALID` FAIL
- `test_validate_artifacts_raw_extraction_path_missing_warning` — nonexistent raw_extraction path → WARNING, metadata still assembled

**Manifest validation**
- `test_validate_manifest_all_present_pass` — complete record → all four checks PASS
- `test_validate_manifest_category_missing_warning` — empty category → WARNING
- `test_validate_manifest_source_path_missing_warning` — nonexistent source_path → WARNING (filesystem check only, no PDF open)
- `test_validate_manifest_doc_id_mismatch_warning` — doc_id mismatch → WARNING
- `test_validate_manifest_runs_even_when_artifacts_unreadable` — manifest checks still appear when clean_text fails to parse
- `test_validate_manifest_doc_id_consistent_omitted_when_unparseable` — `DOC_ID_CONSISTENT` absent entirely when unparseable

**Metadata field resolution**
- `test_resolve_metadata_fields_doc_type_unresolved_warning` — no match → `DOC_TYPE_UNRESOLVED` WARNING
- `test_resolve_metadata_fields_doc_type_resolved_no_warning` — title-page match found → no warning emitted
- `test_resolve_metadata_fields_title_fallback_warning` — `largest_heading` method → `TITLE_EXTRACTION_FALLBACK_USED` WARNING
- `test_resolve_metadata_fields_title_regex_no_warning` — `regex_title_field` method → no warning emitted

**Metadata schema**
- `test_assemble_metadata_produces_all_required_sections` — exactly the documented top-level keys, no extras
- `test_resolve_title_regex_match` — regex match → method `regex_title_field`
- `test_resolve_title_falls_back_to_largest_heading` — no regex match, level-1 heading exists → method `largest_heading`
- `test_resolve_title_none_found` — no match, empty section_tree → `''`, `none_found`
- `test_resolve_doc_type_title_page_match` — title-page phrase match → `PAD`, `title_page_match`
- `test_resolve_doc_type_filename_fallback` — filename contains `RRP` → `RRP`, `filename_pattern`
- `test_resolve_doc_type_unresolved` — no match → `unknown`, `unresolved`
- `test_metadata_not_written_on_critical_failure` — Critical finding → `metadata.json` never created
- `test_metadata_written_on_warning_only` — Recoverable-only findings → `metadata.json` created, `validation.status == "WARNING"`
- `test_metadata_validation_status_never_ready_for_chunking` — status always `PASS`/`WARNING`, never `ready_for_chunking`

**Validation report schema**
- `test_validation_report_always_written` — written for both a passing and a failing fixture
- `test_validation_report_written_even_when_artifacts_unreadable` — still produced when `clean_text.json` is invalid JSON
- `test_validation_report_mixed_severities` — one fixture producing PASS + WARNING + FAIL findings together
- `test_validation_report_summary_counts_match_findings` — summary counts are a pure rollup of `findings[]`
- `test_validation_report_every_reachable_check_always_present` — every code appears at most once; unconditional codes exactly once
- `test_finding_code_rejected_if_not_in_frozen_vocabulary` — unknown `code` fails loudly at construction time

**Manifest update**
- `test_manifest_status_stays_registered_on_pass` — status unchanged after a clean PASS run
- `test_manifest_status_stays_registered_on_warning_only` — status unchanged after a WARNING-only run
- `test_manifest_quarantined_on_critical_fail` — status `QUARANTINED`, error_code `FATAL_VALIDATION_FAILED`
- `test_manifest_artifact_paths_updated_on_pass_or_warning` — `metadata` and `validation_report` keys added
- `test_manifest_metadata_path_absent_on_fail` — `metadata` key never added when quarantined
- `test_validators_do_not_mutate_record` — every validator leaves `ManifestRecord` unchanged; only `validate_document` mutates it

**Determinism / reruns**
- `test_rerun_produces_identical_metadata` — two runs produce byte-identical `metadata.json` (timestamps excluded)
- `test_rerun_produces_identical_findings` — two runs produce the same findings (codes, order, severities)

**Corrupt artifacts**
- `test_corrupt_clean_text_json_fails_gracefully` — invalid JSON → `ARTIFACTS_READABLE` FAIL, quarantined, no exception propagates
- `test_missing_clean_text_file_fails_gracefully` — missing file → same graceful FAIL path

**Immutability**
- `test_clean_text_not_mutated` — `clean_text.json` byte-identical before/after
- `test_raw_extraction_not_mutated` — `raw_extraction.json` byte-identical before/after
