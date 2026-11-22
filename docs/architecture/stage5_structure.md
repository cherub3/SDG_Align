# Stage 5 — Structural Tagging

See `docs/pipeline_principles.md` for shared conventions (Design Philosophy, Logging Specification,
Stage-N numbering, severity tiers, QUARANTINED-reuse, manifest updates).

## Scope

Stage 5 reads `clean_text.json` (Stage 4's output) and, for a font-emphasis signal only,
`raw_extraction.json`'s `font_info`; it extends `clean_text.json` in place with exactly two new
fields — top-level `section_tree` and per-page `headings` — matching the architecture's documented,
closed schema. It never changes `text`/`char_start`/`char_end`/`is_excluded`/`page_number`, never
re-opens a PDF, never mutates `raw_extraction.json`, never writes a new artifact file, and does no
appendix/references field-writing, chunking, embeddings, retrieval, or metadata extraction — those
are out of scope (appendix/reference detection is logged only, not persisted; see Design Decisions).

**Corpus reality check:** only 6 of 13 real corpus documents have a `clean_text.json` (the other 7
were quarantined at Stage 3 as scanned/image-only) — Stage 5's test plan accounts for this.

## Pipeline

```
detect_headings(clean_text, font_info_by_page)
        ↓  (flat, page-ordered list of raw heading detections)
assign_heading_levels(headings)
        ↓  (each entry now has section_level)
generate_section_ids(headings)
        ↓  (each entry now has section_id + parent_section)
build_section_tree(headings)
        ↓  (final [{section_id, section_level, parent_section, title, start_page}, ...])
detect_appendices(section_tree)   ─┐
detect_reference_sections(section_tree) ─┘  (logging only — no field written)
        ↓
update_clean_text(clean_text, section_tree)
        ↓  (adds section_tree + per-page headings, returns updated dict)
write back to the same clean_text.json path
```

`generate_section_ids` internally performs the same parent-tracking walk `build_section_tree` needs
(synthetic-id generation requires knowing the parent first); `build_section_tree` does final assembly
and validation rather than re-deriving parentage from scratch.

`raw_extraction.json` is opened read-only, once per document, solely to build a page-indexed lookup
of `font_info`. If missing or unreadable, Stage 5 logs a `WARNING` and proceeds without the
font-emphasis tier rather than failing the document — font-emphasis is one signal among several, not
a hard dependency.

## Design Decisions

1. Uses `font_info`'s real field names (`text`, `max_font_size`, `bold_if_any`, `bbox`) as produced
   by `stage2_extraction.py:_extract_line_font_info`, not the architecture doc's illustrative
   `{text, size, bold, bbox}` example. Why: current implementation is source of truth over
   illustrative examples where they disagree.
2. No `is_appendix`/`is_references`/`heading_level` fields anywhere on `section_tree` or page
   `headings`. Why: the doc's `clean_text.json` schema is closed and shows exactly five
   `section_tree` fields and two `headings` fields; a machine-readable appendix/references flag
   belongs to Stage 7's `metadata.json.structure.sections_flagged`, not here. `detect_appendices`/
   `detect_reference_sections` remain real, independently tested functions — their result surfaces
   via `WARNING`-level logging (e.g. "3 sections flagged as appendix/references starting at page
   130") so a future Stage 7 can reuse the same trigger regex.
3. `title` is always numbering-stripped descriptive text, in both `section_tree` and page `headings`
   (e.g. `"Climate Rationale"`, not `"2.1 Climate Rationale"`). Why: avoids storing the number
   redundantly in both `section_id` and `title`.
4. Page-level `headings` carries only `{section_id, title}`, no `section_level`. Why: avoids
   duplicating hierarchy data on every page — a reader looks up the level in `section_tree` by
   `section_id`.
5. `update_clean_text` replaces `section_tree` wholesale on each run, never appends. Why: per Design
   Philosophy #4 (idempotent reruns, no accumulation).
6. A missing/unreadable `raw_extraction.json` degrades Stage 5 gracefully (font-emphasis tier
   skipped) rather than quarantining the document. Why: font-emphasis is optional, lowest-priority
   signal; nothing downstream depends on it firing.

## Schema

Additions to `clean_text.json` (real field names, nothing invented beyond the doc's schema):

```jsonc
{
  "doc_id": "...",
  "full_text_char_count": 98031,
  "section_tree": [                          // NEW — top-level, added by Stage 5
    {
      "section_id": "2.1",                   // native numbering token, or synthetic "s2"/"s2a"
      "section_level": 2,
      "parent_section": "2",                 // or null for a root node
      "title": "Climate Rationale",          // numbering-stripped descriptive text only
      "start_page": 13
    }
  ],
  "pages": [
    {
      "page_number": 1,
      "text": "...",                         // untouched, from Stage 4
      "char_start": 0,                       // untouched, from Stage 4
      "char_end": 1893,                      // untouched, from Stage 4
      "is_excluded": false,                  // untouched, from Stage 4
      "headings": [                          // NEW — per-page, added by Stage 5
        {"section_id": "1", "title": "Executive Summary"}
      ]
    }
  ]
}
```

## Functions

```python
def detect_headings(clean_text: Dict, font_info_by_page: Dict[int, List[Dict]]) -> List[Dict]:
    """Scans every non-excluded page's text, line by line, in page order;
    classifies each line by first-match-wins precedence, appending
    {line_text, title, numbering, style, page_number} per match. Body text
    produces no entry. Detection only — no section_level/section_id yet.

    Precedence: (1) markdown ATX header (^#{1,6}\\s+.+) (2) numeric dotted
    numbering (3) roman numeral (4) alphabetic (5) font-emphasis fallback —
    normalized-text lookup in font_info_by_page; heading if max_font_size >=
    FONT_EMPHASIS_SIZE_RATIO * modal body size, or bold_if_any; no match ->
    falls through (6) all-caps unnumbered fallback (CAPS_HEADING_MIN/MAX_LENGTH,
    no trailing period). Guards at every tier: HEADING_MAX_LENGTH cutoff,
    bullet/list markers excluded. title is always numbering-stripped."""

def assign_heading_levels(headings: List[Dict]) -> List[Dict]:
    """Adds section_level per style: markdown -> '#' count; numeric -> dot-
    segment count; roman -> 1; alpha -> 2; font_emphasis/caps_unnumbered -> 1."""

def generate_section_ids(headings: List[Dict]) -> List[Dict]:
    """Walks the leveled, page-ordered list with a level-indexed stack (pop
    entries >= current level; new top is the parent). Adds section_id +
    parent_section: native numbering uses its own token, dot-joined to the
    parent's id for cross-branch uniqueness; no native numbering -> synthetic
    's{n}' at top level or '{parent_id}{letter}' as a child. Purely
    positional, no hashing."""

def build_section_tree(headings: List[Dict]) -> List[Dict]:
    """Final assembly + validation: maps to the closed 5-field shape
    {section_id, section_level, parent_section, title, start_page}; asserts
    every non-null parent_section refers to an earlier section_id (an
    internal consistency check, not a data-quality heuristic)."""

def detect_appendices(section_tree: List[Dict]) -> List[str]:
    """Returns section_ids whose title matches APPENDIX_RE — titles only,
    never body text. Does not mutate section_tree; caller logs the result."""

def detect_reference_sections(section_tree: List[Dict]) -> List[str]:
    """Same mechanism as detect_appendices, against REFERENCES_RE."""

def update_clean_text(clean_text: Dict, section_tree: List[Dict]) -> Dict:
    """Sets clean_text['section_tree'] (replacing wholesale, not appending).
    Per page, sets headings = [{section_id, title}] for every section_tree
    entry whose start_page matches. Never touches text/char_start/char_end/
    is_excluded/page_number. Returns the dict."""
```

Orchestration (mirrors Stage 2–4 shape):

```python
def load_font_info_by_page(record: ManifestRecord) -> Dict[int, List[Dict]]:
    """Reads artifact_paths['raw_extraction'] read-only, returns
    {page_number: font_info_list}. Missing/unreadable -> logs WARNING,
    returns {}."""

def tag_document(record: ManifestRecord) -> None:
    """Reads clean_text.json, calls load_font_info_by_page, then
    detect_headings -> assign_heading_levels -> generate_section_ids ->
    build_section_tree -> detect_appendices/detect_reference_sections
    (logged) -> update_clean_text, writes back to the same path. Stamps
    started_at/completed_at/pipeline_version. Failure -> QUARANTINED,
    FATAL_UNREADABLE. Success leaves status at REGISTERED."""

def run_stage5() -> None:
    """Processes every REGISTERED record with 'clean_text' in
    artifact_paths, saves manifest once at the end."""
```

**Named constants** (documented, testable, analogous to Stage 3/4's thresholds — the architecture
doc names the heuristic kind but gives no numbers or trigger words):

```python
HEADING_MAX_LENGTH = 120          # a heading candidate line longer than this is body text
CAPS_HEADING_MIN_LENGTH = 3
CAPS_HEADING_MAX_LENGTH = 80
FONT_EMPHASIS_SIZE_RATIO = 1.15   # candidate font size must be >= 1.15x the document's modal body size
APPENDIX_RE = re.compile(r'^(APPENDIX|ANNEX)(ES)?\b', re.IGNORECASE)
REFERENCES_RE = re.compile(r'^(REFERENCES|BIBLIOGRAPHY|WORKS CITED|LITERATURE)\b', re.IGNORECASE)
```

Modal body font size is computed once per document: the most frequent `max_font_size` value (rounded
to the nearest 0.5pt to absorb float noise) across all `font_info` entries on all non-excluded pages
— a pure arithmetic/statistical computation, not semantic interpretation.

### Font-Correlation Limitation

`detect_headings`' font-emphasis tier (tier 5) correlates a cleaned line of `clean_text.json` text
back to its `font_info` entry by normalized-text match (strip + collapse whitespace, then equality).
This correlation can fail: Stage 4's cleaning (dehyphenation, header/footer stripping, encoding
repair) runs between the two artifacts, so a line altered enough — a rejoined hyphenated word, a
stripped repeated header — no longer has an exact match in `font_info_by_page`.

This is accepted, not a bug: `font_info` is captured pre-cleaning, `clean_text` post-cleaning.
Guaranteeing perfect correlation would require either tracking a char-offset mapping through every
Stage 4 transform, or reopening the PDF against cleaned text (forbidden per Design Philosophy #3) —
neither in scope. A missed correlation is a precision loss on one optional, lowest-priority detection
tier; nothing downstream depends on it firing. When correlation fails, detection falls through to the
caps-unnumbered fallback (tier 6) exactly as if the tier didn't exist for that line; a line failing
every tier is classified as body text — the honest default per Design Philosophy #5.

No fuzzy matching is introduced as a fix: an approximate match (edit distance, substring,
token-overlap) risks correlating the wrong line's font info to a given text line — a false
correlation is strictly worse than a missed one, since it would silently misclassify a line based on
unrelated font data. Exact match or honest non-match is preferred, per Design Philosophy #5.

Test 7 (`test_detect_headings_font_emphasis_requires_correlation`) exercises this directly.

## Self-Critique

1. **Can a body paragraph be falsely detected as a heading?** Mitigated by `HEADING_MAX_LENGTH`, the
   bullet-marker exclusion at every tier, and requiring the all-caps fallback to have no trailing
   period within a narrow length band. Residual, accepted risk: a short, unpunctuated all-caps body
   sentence, or a bolded/oversized pull-quote, could still false-positive — same accepted-heuristic-
   risk category as Stage 3/4's own thresholds. Not eliminated; documented.
2. **Can different numbering systems create ambiguity?** Yes in principle (contrived input could
   satisfy both numeric and alphabetic patterns) — resolved by the fixed, first-match-wins precedence
   order, covered by test 11.
3. **Are synthetic ids deterministic?** Yes — generated purely from a heading's own text/numbering
   and position in a deterministic top-to-bottom, page-ordered scan; no hashing, no randomness, no
   run-order dependency. Verified by tests 15 and 24.
4. **Can Stage 6 consume this output without reopening the PDF?** Yes — `section_tree` gives explicit
   hierarchy with `start_page` anchors, per-page `headings` give per-page anchors, and Stage 4 already
   populated `char_start`/`char_end`. Sufficient for a future chunker to align boundaries to structure
   without re-deriving anything.
5. **Is any semantic reasoning accidentally introduced?** No. Every signal is a typographic or
   textual pattern already present in the data — markdown syntax, numbering tokens, capitalization, a
   measured font-size ratio, fixed keyword regex. The modal-body-font-size computation is arithmetic
   (a mode over already-captured numbers), not interpretation. No relevance/importance judgment, no
   summarization, no SDG classification anywhere in Stage 5.

## Test Plan

`unittest`, no `fitz` — hand-built `clean_text.json`/`raw_extraction.json`-shaped dicts.

**Pure-function unit tests:**
1. `test_detect_headings_numeric` — `"2.1 Climate Rationale"` → numeric style, numbering `"2.1"`, title `"Climate Rationale"`
2. `test_detect_headings_roman` — `"I. THE PROPOSAL"` → roman style
3. `test_detect_headings_alpha` — `"A. Background"` → alpha style
4. `test_detect_headings_markdown` — `"## Executive Summary"` → markdown style, level 2
5. `test_detect_headings_mixed_styles_in_one_document` — markdown, numeric, roman headings all classified correctly, none miscategorized
6. `test_detect_headings_font_emphasis_fallback` — no textual pattern, but correlated font size well above modal → detected via font-emphasis
7. `test_detect_headings_font_emphasis_requires_correlation` — large font size but no normalized-text match → not detected via font-emphasis, falls through
8. `test_detect_headings_caps_unnumbered` — `"EXECUTIVE SUMMARY"` → caps_unnumbered style
9. `test_detect_headings_rejects_long_body_line` — 200-char sentence never a heading, even with number-like prefix
10. `test_detect_headings_rejects_bullet_line` — `"- 2.1 not a heading, a list item"` not classified as heading
11. `test_precedence_markdown_over_numeric` — `"# 2.1 Title"` classified by markdown rule, not numeric
12. `test_generate_section_ids_uses_native_numbering` — `"2.1.1"` → `section_id == "2.1.1"`
13. `test_generate_section_ids_synthesizes_when_unnumbered` — first unnumbered top-level heading → `"s1"`, second → `"s2"`
14. `test_generate_section_ids_synthesizes_child` — unnumbered heading nested under `"s2"` → `"s2a"`
15. `test_generate_section_ids_deterministic_across_runs` — running twice on the same detected list produces identical ids and order
16. `test_detect_appendices_matches_annex_a` — `"ANNEX A"` and `"APPENDIX B"` both returned
17. `test_detect_reference_sections_matches_bibliography` — `"BIBLIOGRAPHY"` and `"REFERENCES"` both returned
18. `test_detect_appendices_ignores_body_text_mentions` — a section titled `"Overview"` with "appendix" in body text is not flagged — title-only matching

**Integration tests** (fixture `clean_text.json` + `raw_extraction.json` in a temp dir, minimal
`ManifestRecord`, call `tag_document(record)`, reload `clean_text.json`):
19. `test_section_tree_created`
20. `test_parent_child_hierarchy` — 3-level fixture (`"1"` → `"1.1"` → `"1.1.1"`) produces correct `parent_section` chains
21. `test_page_headings_populated` — each page's `headings` contains only headings whose `start_page` matches, exactly `{section_id, title}`
22. `test_no_page_text_modified` — every page's `text`/`char_start`/`char_end`/`is_excluded` byte-identical before/after
23. `test_raw_extraction_not_mutated` — fixture byte-identical on disk before/after
24. `test_rerun_produces_identical_output` — calling `tag_document()` twice produces identical `section_tree` and per-page `headings`, no accumulation
25. `test_missing_raw_extraction_degrades_gracefully` — missing/absent `raw_extraction` artifact path still succeeds using non-font-emphasis tiers, no quarantine
