# Stage 4 — Cleaning & Normalization

See `docs/pipeline_principles.md` for shared conventions (Design Philosophy, Logging Specification,
Stage-N numbering, severity tiers, QUARANTINED-reuse, manifest updates).

## Scope

Stage 4 reads `raw_extraction.json` (written by Stage 2, mutated in place by Stage 3 with
`character_count`/`excluded`/`exclusion_reason` per page) and writes a new artifact,
`clean_text.json`, applying deterministic per-page text cleaning plus whole-document header/footer
stripping. It does not touch `raw_extraction.json`, does not detect headings or build
`section_tree` (Stage 5's job), and does not advance `record.status` past `REGISTERED` on success.

## Pipeline

```
normalize_whitespace → repair_dehyphenation → repair_encoding → remove_headers_footers → assemble_clean_text
```

`repair_encoding` runs before `remove_headers_footers` so header/footer candidate lines are compared
in encoding-normalized form (a ligature-encoded header on one page must string-match its ASCII twin
on another). `repair_dehyphenation` runs before `repair_encoding` safely — ligature codepoints aren't
`[a-zA-Z]`, so the two steps don't interact.

## Design Decisions

1. `clean_text.json` lands in the same per-doc directory as `raw_extraction.json` (`EXTRACTED_DIR`,
   imported from `stage2_extraction`, not redefined).
2. `raw_extraction.json` is never mutated by Stage 4, unlike Stage 3 → Stage 2. It stays intact as
   the undamaged fallback, and remains available for Stage 5's font-emphasis signal.
3. `clean_text.json` omits `section_tree` and per-page `headings` entirely at this stage — Stage 5
   adds them later, per Design Philosophy #2 (Stage 5 mutates its own artifact, extended, not
   another stage's).
4. Manifest timestamps (`started_at`/`completed_at`/`pipeline_version`) are stamped on every run,
   matching Stage 2/3. Per the Manifest Update Convention, these mean "last time the pipeline
   touched this record," not a per-stage audit trail.
5. `record.status` is left at `REGISTERED` on success; only ever set to `QUARANTINED` on failure,
   per the QUARANTINED-Reuse Convention.

## Schema

`clean_text.json` (Stage 4's own fields only — `section_tree`/page `headings` added later by Stage 5):

```jsonc
{
  "doc_id": "...",
  "full_text_char_count": 98031,
  "pages": [
    {
      "page_number": 1,
      "text": "...",
      "char_start": 0,
      "char_end": 1893,
      "is_excluded": false
    }
  ]
}
```

Excluded pages get `char_start == char_end` (zero-width) and do not advance the running counter.

## Functions

Pipeline functions (pure, independently unit-testable):

```python
def normalize_whitespace(text: str) -> str:
    """Collapse repeated horizontal whitespace, normalize line endings to \n,
    strip trailing spaces per line, cap 3+ consecutive blank lines to one
    (paragraph boundary preserved, not collapsed)."""

def repair_dehyphenation(text: str) -> str:
    """Join a word split by an end-of-line hyphen: letter-<newline>letter -> letters.
    Only fires when both characters adjacent to the hyphen are [a-zA-Z]. A hyphen
    followed by a space or another hyphen is untouched ('well-being' unaffected
    unless it genuinely wraps); an alphanumeric code broken across a line break
    ('COVID-' + newline + '19') is never merged, since the digit after the
    newline fails the alphabetic check."""

def repair_encoding(text: str) -> str:
    """Deterministic, narrow: normalize NBSP (\xa0) to a regular space, expand
    the standard PDF ligature codepoints (ff/fi/fl/ffi/ffl) to ASCII letter
    sequences. No smart-quote/dash rewriting — anything without a fixed 1:1
    mapping is left as-is."""

def remove_headers_footers(page_texts: List[str], excluded_flags: List[bool]) -> List[str]:
    """Whole-document heuristic. Candidate = first non-empty line and last
    non-empty line of each non-excluded page. A candidate is a repeated
    header/footer only if it occurs on >= HEADER_FOOTER_MIN_OCCURRENCES pages
    AND on >= HEADER_FOOTER_MIN_PAGE_RATIO of non-excluded pages. Matching
    lines are stripped only from the position found (first-line / last-line),
    never mid-page."""

def assemble_clean_text(doc_id: str, pages: List[Dict]) -> Dict:
    """Pure bookkeeping: assigns running char_start/char_end per page, sums
    full_text_char_count, returns the final clean_text.json dict. No
    section_tree, no headings."""
```

Constants: `HEADER_FOOTER_MIN_OCCURRENCES = 3`, `HEADER_FOOTER_MIN_PAGE_RATIO = 0.5` — the
architecture doc names the heuristic kind but no numeric threshold; these are the documented,
testable constants this implementation introduces (analogous to Stage 3's `MIN_CHARS_PER_PAGE = 50`).

Orchestration (mirrors Stage 2/3 shape):

```python
def build_clean_text(raw_extraction: Dict) -> Dict:
    """Runs the fixed pipeline per page, then remove_headers_footers across
    all pages, then assemble_clean_text. Returns the dict to write — no I/O."""

def write_clean_text(clean_text: Dict) -> Path:
    """Writes clean_text.json to EXTRACTED_DIR/<doc_id>/clean_text.json."""

def clean_document(record: ManifestRecord) -> None:
    """Reads record.artifact_paths['raw_extraction'], loads the JSON, calls
    build_clean_text + write_clean_text, sets
    record.artifact_paths['clean_text'], stamps started_at/completed_at/
    pipeline_version. On missing artifact path, missing file, or any
    exception: status = QUARANTINED, error_code = 'FATAL_UNREADABLE'
    (existing vocabulary, no new code). Success leaves status at REGISTERED."""

def run_stage4() -> None:
    """Loads manifest, processes every record where status == REGISTERED and
    'raw_extraction' in record.artifact_paths, skips everything else, saves
    manifest once at the end."""
```

## Self-Critique

1. **Semantic interpretation risk.** `remove_headers_footers` is the only step that looks at more
   than one page at a time, but it only compares literal string equality of first/last lines after
   whitespace normalization — no page-number stripping, no fuzzy matching. A footer like "Page 3 of
   42" that changes per page won't be caught — a known, accepted limitation, matching the
   architecture doc's own admission that this heuristic "can misfire."
2. **Regex over-removal risk.** `repair_dehyphenation` requires both characters adjacent to the
   hyphen to be alphabetic, distinguishing a soft line-wrap hyphen from an intentional one. This also
   means an alphanumeric identifier split across a line break (`"COVID-\n19"`) is intentionally not
   merged — the digit fails the check by construction, not by accident.
3. **Markdown structure risk.** None of the four transforms touch `-`, `*`, digit+`.`, or `|` —
   bullets, numbered lists, and table pipes pass through unchanged.
4. **Testability.** All five functions take/return plain strings or lists of strings/dicts, no hidden
   state, called directly in unit tests without file I/O.
5. **Idempotency.** `normalize_whitespace`, `repair_dehyphenation`, and `repair_encoding` each satisfy
   `f(f(x)) == f(x)` — a second run must not keep transforming already-cleaned text (e.g. the
   blank-line cap must not ratchet down further; ligature expansion must have no second-pass target).
   `remove_headers_footers` is naturally idempotent too — once a repeated line is stripped, it's no
   longer a candidate on the next pass.
6. **Stage 5 readiness.** `raw_extraction.json` is left untouched, so `font_info` remains available
   for Stage 5's font-size heading heuristic; `clean_text.json` carries `page_number` +
   `char_start`/`char_end` per page so Stage 5 can anchor `section_tree` entries without recomputing
   offsets.

## Test Plan

`unittest`, no `fitz` — fixtures are hand-built `raw_extraction.json`-shaped dicts.

**Pure-function unit tests:**
1. `test_normalize_whitespace_collapses_spaces`
2. `test_normalize_whitespace_preserves_paragraph_breaks` — blank line between paragraphs survives
3. `test_repair_dehyphenation_joins_split_word` — `"develop-\nment"` → `"development"`
4. `test_repair_dehyphenation_preserves_real_hyphen` — `"well-being"` unchanged
5. `test_repair_dehyphenation_preserves_alphanumeric_code` — `"COVID-\n19"` not merged
6. `test_remove_headers_footers_strips_repeated_line` — repeated first line on 4/5 pages stripped
7. `test_remove_headers_footers_keeps_unique_content` — page-local line never touched
8. `test_repair_encoding_expands_ligature` — ligature codepoint → ASCII
9. `test_repair_encoding_normalizes_nbsp` — `"\xa0"` → `" "`
10. `test_cleaning_functions_are_idempotent` — `f(f(x)) == f(x)` for each per-page transform

**Integration tests** (fixture `raw_extraction.json` in a temp `EXTRACTED_DIR`, minimal
`ManifestRecord`, call `clean_document(record)`, load `clean_text.json`):
11. `test_clean_text_json_created`
12. `test_page_count_preserved`
13. `test_page_numbers_not_renumbered`
14. `test_excluded_flag_carried_forward` — `excluded: True` → `is_excluded: True`
15. `test_markdown_bullets_preserved`
16. `test_numbered_list_preserved`
17. `test_table_text_preserved` — pipe-delimited markdown table text survives intact
18. `test_char_offsets_are_consistent` — `char_end - char_start == len(text)`, offsets chain correctly
19. `test_raw_extraction_not_mutated` — byte-identical on disk before/after
20. `test_pipeline_is_idempotent` — full pipeline settles to a fixed point on a second run

## Verification

1. `python -m unittest tests.test_stage4_cleaning -v` — all 20 tests pass.
2. Run `python scripts/stage4_cleaning.py` against the real corpus and spot-check one
   `clean_text.json`: page count matches `raw_extraction.json`, `full_text_char_count` equals the sum
   of per-page text lengths, no `section_tree`/`headings` keys present, excluded pages carry
   `is_excluded: true` with zero-width offsets.
3. Confirm `raw_extraction.json` for that same document is byte-identical to before the run.

## Phase 1 additions (2026-11-23)

Added after the original freeze, each with tests that fail on the old code: removal of `Page x of y` markers, HTML residue
(`<br>` to space, `<mark>`/`<u>` dropped, entities decoded), table-of-contents blocks (dot leaders, needs 3+ on a page), the GEF
template instruction text (explicit opener list), footers glued into sentences, and Markdown tables rewritten as
`Header: value; Header: value` row text. The rules were written by reading the same 5 GEF documents they are measured on, so the
automatic boilerplate metric is partly circular (see `reports/PHASE_1_REPORT.md`, section 7).
