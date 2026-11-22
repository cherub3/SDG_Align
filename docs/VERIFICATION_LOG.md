# Verification Log

Chronological, real-corpus run summaries and bugs found/fixed as a direct result of running the
pipeline against real documents. Only ingestion stages with a distinct real-corpus verification
narrative are listed here (Stage 6 has none separate from its implementation). This is a historical
record of the ingestion-phase corpus runs; the query and agent stages (10–21) are library modules
verified by their own test suites rather than by corpus runs (see each stage's architecture doc).

## Stage 4 — Cleaning & Normalization
- Corpus run: 13 documents total. 7 are genuinely scanned/image-only PDFs (confirmed directly via
  `fitz`) and were correctly quarantined by Stage 3 (`FATAL_NO_TEXT`). The other 6 have real
  extractable text and flow cleanly through Stages 2->3->4.
- Bugs found:
  - `scripts/stage2_extraction.py`'s `_extract_table_bboxes` crashed on documents with real text —
    PyMuPDF's `find_tables()` can return a degenerate candidate with no cells, whose `.bbox`
    property raises `ValueError` (`min()` of an empty sequence) instead of a usable box. Fix: skip
    such a candidate rather than letting it crash extraction for the whole page (narrow,
    user-approved fix).

## Stage 5 — Structural Tagging
- Corpus run: only 6 of the 13 real corpus documents have a `clean_text.json` for Stage 5 to
  consume (the other 7 are quarantined at Stage 3, per Stage 4's run above).
- Bugs found:
  - A short, all-caps table cell (e.g. `"|WWF-US|G0061|"`) was misclassified as a heading via the
    caps-unnumbered fallback tier. Fix: `detect_headings` now rejects pipe-delimited table rows
    before the caps-unnumbered check (`_is_table_row`). Regression test:
    `test_detect_headings_rejects_table_row` (`tests/test_stage5_structure.py`).
  - A bare-quantity sentence (e.g. `"20 people attended the workshop in Dhaka"`) was misclassified
    as numeric heading numbering (matching on the leading `"20"`). Fix: added a guard in
    `_try_numeric` to reject this pattern. Regression test:
    `test_detect_headings_rejects_bare_quantity` (`tests/test_stage5_structure.py`).

## Stage 7 — Semantic Chunking
- Corpus run: 5 of the 13 registered documents successfully completed Stage 7 chunking; the other
  8 are quarantined at earlier stages.
- Bugs found:
  - **Monotonicity clamp for overlapping spans:** `resolve_heading_offsets` could produce
    non-monotonic (out-of-order) offsets — if an earlier heading resolved to a late position on a
    page and a later heading on the *same* page failed to resolve, it fell back to that page's own
    `char_start` (0), landing earlier than the prior resolved offset and producing an
    overlapping/invalid span in `build_section_spans`. Fix: each resolved offset is now clamped to
    be `>=` the previous resolved offset (`clamped = max(candidate, prev_start)`). Regression
    tests: `test_resolved_offsets_are_monotonic_non_decreasing`,
    `test_monotonic_offsets_prevent_span_overlap` (`tests/test_stage7_chunking.py`).
  - **Preamble-to-first-section merge:** the "first span merges forward" exception (for an
    undersized preamble/intro span with no predecessor to merge backward into) was gated by the
    same same-branch check used for ordinary backward merges, which could incorrectly block a
    preamble span from merging into the document's first real section. Fix:
    `merge_undersized_spans`'s first-span-forward exception is exempted from the `_same_branch`
    gate — a preamble span (no section of its own) merging into the first real section is not a
    branch crossing in any meaningful sense. Regression test:
    `test_first_span_undersized_merges_forward` (`tests/test_stage7_chunking.py`).
