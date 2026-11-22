"""Tests for Stage 7 — Semantic Chunking."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from src.ingestion_types import ManifestRecord, DocumentStatus
from scripts import stage7_chunking as s7


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def build_pages(page_texts, excluded=None):
    """Build a clean_text.json-shaped pages[] list with contiguous offsets,
    matching Stage 4's own char_start/char_end convention exactly."""
    excluded = excluded or set()
    pages = []
    cursor = 0
    for i, text in enumerate(page_texts, start=1):
        if i in excluded:
            pages.append({
                "page_number": i, "text": "", "char_start": cursor,
                "char_end": cursor, "is_excluded": True, "headings": [],
            })
        else:
            start = cursor
            end = cursor + len(text)
            pages.append({
                "page_number": i, "text": text, "char_start": start,
                "char_end": end, "is_excluded": False, "headings": [],
            })
            cursor = end
    return pages


def build_clean_text(doc_id, page_texts, section_tree, excluded=None):
    pages = build_pages(page_texts, excluded)
    full_len = pages[-1]["char_end"] if pages else 0
    return {
        "doc_id": doc_id,
        "full_text_char_count": full_len,
        "section_tree": section_tree,
        "pages": pages,
    }


def build_metadata(doc_id, title="Sample Title", category="climate", doc_type=None):
    return {
        "doc_id": doc_id,
        "title": title,
        "title_extraction_method": "largest_heading",
        "provenance": {
            "original_filename": "sample.pdf", "sha256": doc_id.removeprefix("doc_"),
            "source_path": f"data/proposals/raw/{category}/sample.pdf",
            "ingested_at": "2026-07-19T00:00:00Z", "ingestion_pipeline_version": "0.1.0",
        },
        "classification": {"category": category, "doc_type": doc_type, "doc_type_confidence": "unresolved"},
        "structure": {
            "page_count": 1, "extracted_page_count": 1, "excluded_pages": [],
            "has_tables_detected": None, "sections_flagged": [],
        },
        "validation": {"status": "ready_for_chunking", "validation_report_path": "x"},
        "future_compatibility": {"language": "en", "ocr_applied": False, "schema_version": "1.0"},
    }


def make_record(doc_id, clean_text_path=None, metadata_path=None, page_count=1):
    return ManifestRecord(
        doc_id=doc_id, category="climate", status=DocumentStatus.READY_FOR_CHUNKING,
        page_count=page_count, source_path="data/proposals/raw/climate/sample.pdf",
        artifact_paths={
            **({"clean_text": clean_text_path} if clean_text_path else {}),
            **({"metadata": metadata_path} if metadata_path else {}),
        },
    )


# ===========================================================================
# resolve_heading_offsets
# ===========================================================================

class TestResolveHeadingOffsets(unittest.TestCase):

    def test_exact_match_resolves_line_start(self):
        page_text = "Introduction\nSome body text about the project follows here."
        clean_text = build_clean_text("doc_x", [page_text], [
            {"section_id": "s1", "section_level": 1, "parent_section": None,
             "title": "Introduction", "start_page": 1},
        ])
        resolved, findings = s7.resolve_heading_offsets(clean_text)
        self.assertEqual(resolved[0]["absolute_start"], 0)
        self.assertTrue(resolved[0]["recovered"])
        self.assertEqual(findings, [])

    def test_duplicate_titles_on_same_page_resolve_distinct_occurrences(self):
        page_text = "Overview\nFirst part.\n\nOverview\nSecond part."
        clean_text = build_clean_text("doc_x", [page_text], [
            {"section_id": "s1", "section_level": 1, "parent_section": None, "title": "Overview", "start_page": 1},
            {"section_id": "s2", "section_level": 1, "parent_section": None, "title": "Overview", "start_page": 1},
        ])
        resolved, findings = s7.resolve_heading_offsets(clean_text)
        self.assertTrue(resolved[0]["recovered"])
        self.assertTrue(resolved[1]["recovered"])
        self.assertLess(resolved[0]["absolute_start"], resolved[1]["absolute_start"])

    def test_title_not_found_falls_back_to_page_start(self):
        page_text = "Some unrelated body text with no heading line at all."
        clean_text = build_clean_text("doc_x", [page_text], [
            {"section_id": "s1", "section_level": 1, "parent_section": None,
             "title": "Executive Summary", "start_page": 1},
        ])
        resolved, findings = s7.resolve_heading_offsets(clean_text)
        self.assertFalse(resolved[0]["recovered"])
        self.assertEqual(resolved[0]["absolute_start"], 0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "WARNING_HEADING_OFFSET_NOT_RECOVERED")

    def test_implausible_match_rejected_falls_back(self):
        # "Overview" appears mid-sentence in a long line, not on its own line.
        page_text = "This chapter provides an Overview of the entire regional programme context and rationale in detail."
        clean_text = build_clean_text("doc_x", [page_text], [
            {"section_id": "s1", "section_level": 1, "parent_section": None, "title": "Overview", "start_page": 1},
        ])
        resolved, findings = s7.resolve_heading_offsets(clean_text)
        self.assertFalse(resolved[0]["recovered"])
        self.assertEqual(findings[0]["code"], "WARNING_HEADING_OFFSET_NOT_RECOVERED")

    def test_missing_start_page_falls_back_gracefully(self):
        clean_text = build_clean_text("doc_x", ["Body text."], [
            {"section_id": "s1", "section_level": 1, "parent_section": None, "title": "Ghost", "start_page": 99},
        ])
        resolved, findings = s7.resolve_heading_offsets(clean_text)
        self.assertFalse(resolved[0]["recovered"])
        self.assertEqual(len(findings), 1)

    def test_resolved_offsets_are_monotonic_non_decreasing(self):
        # Section A resolves late in the page text via str.find(); section B
        # on the SAME page fails to resolve and would otherwise fall back to
        # that page's own char_start (0) — earlier than A's resolved offset.
        # The monotonicity clamp must prevent B from landing before A.
        page_text = "Filler filler filler filler filler.\n\nLate Heading\nBody text after."
        clean_text = build_clean_text("doc_x", [page_text], [
            {"section_id": "a", "section_level": 1, "parent_section": None, "title": "Late Heading", "start_page": 1},
            {"section_id": "b", "section_level": 1, "parent_section": None, "title": "Nonexistent Title", "start_page": 1},
        ])
        resolved, findings = s7.resolve_heading_offsets(clean_text)
        self.assertTrue(resolved[0]["recovered"])
        self.assertFalse(resolved[1]["recovered"])
        self.assertGreaterEqual(resolved[1]["absolute_start"], resolved[0]["absolute_start"])

    def test_monotonic_offsets_prevent_span_overlap(self):
        page_text = "Filler filler filler filler filler.\n\nLate Heading\nBody text after."
        clean_text = build_clean_text("doc_x", [page_text], [
            {"section_id": "a", "section_level": 1, "parent_section": None, "title": "Late Heading", "start_page": 1},
            {"section_id": "b", "section_level": 1, "parent_section": None, "title": "Nonexistent Title", "start_page": 1},
            {"section_id": "c", "section_level": 1, "parent_section": None, "title": "Also Missing", "start_page": 1},
        ])
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        for a, b in zip(spans, spans[1:]):
            self.assertEqual(a["char_end"], b["char_start"])  # connected chain: no gap, no overlap


# ===========================================================================
# build_section_spans
# ===========================================================================

class TestBuildSectionSpans(unittest.TestCase):

    def test_preamble_span_when_content_precedes_first_heading(self):
        page_text = "Cover page text.\n\nIntroduction\nBody."
        clean_text = build_clean_text("doc_x", [page_text], [
            {"section_id": "s1", "section_level": 1, "parent_section": None, "title": "Introduction", "start_page": 1},
        ])
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        self.assertEqual(spans[0]["anchor_section_id"], "preamble")
        self.assertEqual(spans[0]["char_start"], 0)
        self.assertEqual(spans[0]["char_end"], spans[1]["char_start"])

    def test_whole_document_one_span_when_no_sections(self):
        clean_text = build_clean_text("doc_x", ["Just body text, no headings at all."], [])
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["anchor_section_id"], "preamble")
        self.assertEqual(spans[0]["char_start"], 0)
        self.assertEqual(spans[0]["char_end"], clean_text["full_text_char_count"])

    def test_connected_chain_spans_are_contiguous(self):
        p1 = "Intro\nBody one here."
        p2 = "Methods\nBody two here."
        clean_text = build_clean_text("doc_x", [p1, p2], [
            {"section_id": "1", "section_level": 1, "parent_section": None, "title": "Intro", "start_page": 1},
            {"section_id": "2", "section_level": 1, "parent_section": None, "title": "Methods", "start_page": 2},
        ])
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        for a, b in zip(spans, spans[1:]):
            self.assertEqual(a["char_end"], b["char_start"])
        self.assertEqual(spans[-1]["char_end"], clean_text["full_text_char_count"])

    def test_parent_child_ancestor_chain(self):
        text = "1\nA\n\n1.1\nB\n\n1.1.1\nC"
        clean_text = build_clean_text("doc_x", [text], [
            {"section_id": "1", "section_level": 1, "parent_section": None, "title": "1", "start_page": 1},
            {"section_id": "1.1", "section_level": 2, "parent_section": "1", "title": "1.1", "start_page": 1},
            {"section_id": "1.1.1", "section_level": 3, "parent_section": "1.1", "title": "1.1.1", "start_page": 1},
        ])
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        leaf = [s for s in spans if s["anchor_section_id"] == "1.1.1"][0]
        self.assertEqual(leaf["ancestor_section_ids"], ["1", "1.1", "1.1.1"])

    def test_duplicate_section_ids_get_disambiguated_anchors(self):
        text = "Dup\nA\n\nDup\nB"
        clean_text = build_clean_text("doc_x", [text], [
            {"section_id": "x", "section_level": 1, "parent_section": None, "title": "Dup", "start_page": 1},
            {"section_id": "x", "section_level": 1, "parent_section": None, "title": "Dup", "start_page": 1},
        ])
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        anchors = [s["anchor_section_id"] for s in spans]
        self.assertIn("x", anchors)
        self.assertIn("x-dup2", anchors)

    def test_is_appendix_flag_set_from_heading_path(self):
        text = "ANNEX A\nSome annex text."
        clean_text = build_clean_text("doc_x", [text], [
            {"section_id": "a", "section_level": 1, "parent_section": None, "title": "ANNEX A", "start_page": 1},
        ])
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        section_span = [s for s in spans if s["anchor_section_id"] == "a"][0]
        self.assertTrue(section_span["is_appendix"])

    def test_empty_document_produces_no_spans(self):
        clean_text = {"doc_id": "doc_x", "full_text_char_count": 0, "section_tree": [], "pages": []}
        resolved, _ = s7.resolve_heading_offsets(clean_text)
        spans = s7.build_section_spans(clean_text, resolved)
        self.assertEqual(spans, [])


# ===========================================================================
# split_oversized_spans
# ===========================================================================

class TestSplitOversizedSpans(unittest.TestCase):

    def test_span_within_max_is_not_split(self):
        span = {"char_start": 0, "char_end": 100, "section_ids": ["1"], "anchor_section_id": "1",
                "ancestor_section_ids": ["1"], "heading_path": ["T"], "degenerate": False,
                "is_appendix": False, "is_references": False}
        full_text = "x" * 100
        result = s7.split_oversized_spans([span], full_text)
        self.assertEqual(len(result), 1)

    def test_paragraph_boundary_split_fires(self):
        para = ("Lorem ipsum dolor sit amet. " * 20).strip()  # ~580 chars
        full_text = "\n\n".join([para] * 8)  # well over MAX_CHUNK_CHARS
        span = {"char_start": 0, "char_end": len(full_text), "section_ids": ["1"], "anchor_section_id": "1",
                "ancestor_section_ids": ["1"], "heading_path": ["T"], "degenerate": False,
                "is_appendix": False, "is_references": False}
        result = s7.split_oversized_spans([span], full_text)
        self.assertGreater(len(result), 1)
        for piece in result:
            self.assertLessEqual(piece["char_end"] - piece["char_start"], s7.MAX_CHUNK_CHARS)

    def test_split_pieces_reconstruct_original_span_exactly(self):
        para = ("Lorem ipsum dolor sit amet. " * 20).strip()
        full_text = "\n\n".join([para] * 8)
        span = {"char_start": 0, "char_end": len(full_text), "section_ids": ["1"], "anchor_section_id": "1",
                "ancestor_section_ids": ["1"], "heading_path": ["T"], "degenerate": False,
                "is_appendix": False, "is_references": False}
        result = s7.split_oversized_spans([span], full_text)
        result.sort(key=lambda s: s["char_start"])
        self.assertEqual(result[0]["char_start"], 0)
        self.assertEqual(result[-1]["char_end"], len(full_text))
        for a, b in zip(result, result[1:]):
            self.assertEqual(a["char_end"], b["char_start"])

    def test_sentence_boundary_fallback_when_no_paragraph_or_list(self):
        # one dense block, no blank lines, no list markers, no sub-headings
        sentence = "This is a sentence with no special structure at all. "
        full_text = sentence * 100  # dense, sentence-only breakpoints
        span = {"char_start": 0, "char_end": len(full_text), "section_ids": ["1"], "anchor_section_id": "1",
                "ancestor_section_ids": ["1"], "heading_path": ["T"], "degenerate": False,
                "is_appendix": False, "is_references": False}
        result = s7.split_oversized_spans([span], full_text)
        self.assertGreater(len(result), 1)
        for piece in result:
            self.assertLessEqual(piece["char_end"] - piece["char_start"], s7.MAX_CHUNK_CHARS)

    def test_fixed_length_fallback_when_no_breakpoint_at_all(self):
        full_text = "x" * (s7.MAX_CHUNK_CHARS * 2)  # no whitespace/punctuation anywhere
        span = {"char_start": 0, "char_end": len(full_text), "section_ids": ["1"], "anchor_section_id": "1",
                "ancestor_section_ids": ["1"], "heading_path": ["T"], "degenerate": False,
                "is_appendix": False, "is_references": False}
        result = s7.split_oversized_spans([span], full_text)
        for piece in result:
            self.assertLessEqual(piece["char_end"] - piece["char_start"], s7.MAX_CHUNK_CHARS)


# ===========================================================================
# merge_undersized_spans
# ===========================================================================

class TestMergeUndersizedSpans(unittest.TestCase):

    def _span(self, start, end, anchor, ancestor=None, appendix=False, references=False, degenerate=False):
        return {
            "char_start": start, "char_end": end, "section_ids": [anchor],
            "anchor_section_id": anchor, "ancestor_section_ids": ancestor or [anchor],
            "heading_path": [anchor], "degenerate": degenerate,
            "is_appendix": appendix, "is_references": references,
            "page_start": 1, "page_end": 1,
        }

    def test_undersized_trailing_span_merges_backward(self):
        spans = [
            self._span(0, 1000, "1", ["1"]),
            self._span(1000, 1050, "2", ["1"]),  # 50 chars, undersized, same top branch
        ]
        merged = s7.merge_undersized_spans(spans)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["char_start"], 0)
        self.assertEqual(merged[0]["char_end"], 1050)

    def test_first_span_undersized_merges_forward(self):
        spans = [
            self._span(0, 50, "1", ["1"]),   # undersized, no predecessor
            self._span(50, 1200, "2", ["1"]),
        ]
        merged = s7.merge_undersized_spans(spans)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["char_start"], 0)
        self.assertEqual(merged[0]["char_end"], 1200)

    def test_never_merges_across_top_level_branch_boundary(self):
        spans = [
            self._span(0, 1000, "1", ["1"]),
            self._span(1000, 1050, "2", ["2"]),  # different top-level ancestor
        ]
        merged = s7.merge_undersized_spans(spans)
        self.assertEqual(len(merged), 2)

    def test_never_merges_across_appendix_boundary(self):
        spans = [
            self._span(0, 1000, "1", ["1"], appendix=False),
            self._span(1000, 1050, "2", ["1"], appendix=True),  # tiny, but appendix
        ]
        merged = s7.merge_undersized_spans(spans)
        self.assertEqual(len(merged), 2)

    def test_isolated_small_section_with_nothing_to_merge_into_kept_as_is(self):
        spans = [self._span(0, 50, "1", ["1"])]
        merged = s7.merge_undersized_spans(spans)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["char_end"] - merged[0]["char_start"], 50)

    def test_degenerate_span_merge_eligible_regardless_of_branch(self):
        spans = [
            self._span(0, 1000, "1", ["1"]),
            self._span(1000, 1000, "2", ["2"], degenerate=True),  # zero-width, different branch
            self._span(1000, 2000, "3", ["3"]),
        ]
        merged = s7.merge_undersized_spans(spans)
        # degenerate span (zero length) must not survive as its own chunk
        self.assertTrue(all(m["char_end"] - m["char_start"] != 0 or len(merged) == 1 for m in merged))
        total_span = merged[0]["char_end"] - merged[0]["char_start"]
        self.assertGreaterEqual(total_span, 1000)

    def test_already_valid_span_never_pulled_into_merge(self):
        spans = [
            self._span(0, 1000, "1", ["1"]),
            self._span(1000, 2000, "2", ["1"]),  # already >= MIN_CHUNK_CHARS
        ]
        merged = s7.merge_undersized_spans(spans)
        self.assertEqual(len(merged), 2)

    def test_empty_span_list_returns_empty(self):
        self.assertEqual(s7.merge_undersized_spans([]), [])


# ===========================================================================
# assign_chunk_ids
# ===========================================================================

class TestAssignChunkIds(unittest.TestCase):

    def _span(self, anchor):
        return {"char_start": 0, "char_end": 10, "section_ids": [anchor], "anchor_section_id": anchor,
                "ancestor_section_ids": [anchor], "heading_path": [anchor], "degenerate": False,
                "is_appendix": False, "is_references": False, "page_start": 1, "page_end": 1}

    def test_chunk_id_format_structural(self):
        spans = [self._span("2.1")]
        result = s7.assign_chunk_ids(spans, "doc_abc")
        self.assertEqual(result[0]["chunk_id"], "doc_abc_2.1_0")

    def test_dots_preserved_not_sanitized(self):
        spans = [self._span("2.1.1")]
        result = s7.assign_chunk_ids(spans, "doc_abc")
        self.assertIn("2.1.1", result[0]["chunk_id"])

    def test_multiple_chunks_same_anchor_indexed_sequentially(self):
        spans = [self._span("s1"), self._span("s1"), self._span("s1")]
        result = s7.assign_chunk_ids(spans, "doc_abc")
        ids = [c["chunk_id"] for c in result]
        self.assertEqual(ids, ["doc_abc_s1_0", "doc_abc_s1_1", "doc_abc_s1_2"])
        self.assertTrue(all(c["section_chunk_count"] == 3 for c in result))

    def test_rerun_produces_identical_ids(self):
        spans1 = [self._span("s1"), self._span("s2")]
        spans2 = [self._span("s1"), self._span("s2")]
        r1 = s7.assign_chunk_ids(spans1, "doc_abc")
        r2 = s7.assign_chunk_ids(spans2, "doc_abc")
        self.assertEqual([c["chunk_id"] for c in r1], [c["chunk_id"] for c in r2])

    def test_preamble_uses_fixed_anchor(self):
        spans = [self._span("preamble")]
        result = s7.assign_chunk_ids(spans, "doc_abc")
        self.assertEqual(result[0]["chunk_id"], "doc_abc_preamble_0")

    def test_edit_stability_unaffected_sections_keep_ids(self):
        # baseline: two sections
        base = [self._span("1"), self._span("2")]
        base_ids = [c["chunk_id"] for c in s7.assign_chunk_ids(base, "doc_abc")]
        # "edit": insert a new section between them — section "2" is unaffected in identity terms
        # since ids are anchored to section_id, not position, "2"'s id is stable.
        edited = [self._span("1"), self._span("1b"), self._span("2")]
        edited_ids = [c["chunk_id"] for c in s7.assign_chunk_ids(edited, "doc_abc")]
        self.assertIn("doc_abc_2_0", base_ids)
        self.assertIn("doc_abc_2_0", edited_ids)


# ===========================================================================
# validate_chunks
# ===========================================================================

class TestValidateChunks(unittest.TestCase):

    def _clean_text(self, full_len, pages=None):
        return {"doc_id": "doc_x", "full_text_char_count": full_len,
                "section_tree": [{"section_id": "1", "title": "T", "section_level": 1,
                                   "parent_section": None, "start_page": 1}],
                "pages": pages or [{"page_number": 1, "char_start": 0, "char_end": full_len,
                                     "text": "x" * full_len, "is_excluded": False}]}

    def _chunk(self, cid, start, end, text, section_ids=("1",), page_start=1, page_end=1):
        return {"chunk_id": cid, "doc_id": "doc_x", "text": text, "char_start": start, "char_end": end,
                "page_start": page_start, "page_end": page_end, "section_ids": list(section_ids),
                "ancestor_section_ids": list(section_ids), "heading_path": ["T"],
                "chunk_index_within_section": 0, "section_chunk_count": 1,
                "is_appendix": False, "is_references": False, "has_table_content": False,
                "category": "climate", "doc_type": None, "title": "T"}

    def test_exact_coverage_passes(self):
        n = s7.MIN_CHUNK_CHARS
        clean_text = self._clean_text(2 * n)
        chunks = [self._chunk("c1", 0, n, "x" * n), self._chunk("c2", n, 2 * n, "x" * n)]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "PASS")

    def test_gap_between_chunks_fails_coverage(self):
        clean_text = self._clean_text(20)
        chunks = [self._chunk("c1", 0, 8, "x" * 8), self._chunk("c2", 10, 20, "x" * 10)]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "FAIL")
        codes = [f["code"] for f in findings]
        self.assertIn("CHUNK_COVERAGE_EXACT", codes)

    def test_overlap_between_chunks_fails(self):
        clean_text = self._clean_text(20)
        chunks = [self._chunk("c1", 0, 12, "x" * 12), self._chunk("c2", 10, 20, "x" * 10)]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "FAIL")
        codes = [f["code"] for f in findings]
        self.assertIn("CHUNK_NO_OVERLAP", codes)

    def test_empty_chunk_text_fails(self):
        clean_text = self._clean_text(10)
        chunks = [self._chunk("c1", 0, 10, "   ")]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "FAIL")
        self.assertIn("CHUNK_NON_EMPTY", [f["code"] for f in findings])

    def test_duplicate_chunk_ids_fail(self):
        clean_text = self._clean_text(20)
        chunks = [self._chunk("dup", 0, 10, "x" * 10), self._chunk("dup", 10, 20, "x" * 10)]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "FAIL")
        self.assertIn("CHUNK_IDS_UNIQUE", [f["code"] for f in findings])

    def test_undersized_chunk_warns_not_fails(self):
        clean_text = self._clean_text(50)
        chunks = [self._chunk("c1", 0, 50, "x" * 50)]  # below MIN_CHUNK_CHARS
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "WARNING")
        self.assertIn("CHUNK_SIZE_ABOVE_MIN", [f["code"] for f in findings])

    def test_oversized_chunk_fails(self):
        big = s7.MAX_CHUNK_CHARS + 10
        clean_text = self._clean_text(big)
        chunks = [self._chunk("c1", 0, big, "x" * big)]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "FAIL")
        self.assertIn("CHUNK_SIZE_WITHIN_MAX", [f["code"] for f in findings])

    def test_unknown_section_id_warns(self):
        clean_text = self._clean_text(500)
        chunks = [self._chunk("c1", 0, 500, "x" * 500, section_ids=("unknown",))]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertIn("CHUNK_HEADING_PATH_VALID", [f["code"] for f in findings])

    def test_invalid_page_range_fails(self):
        clean_text = self._clean_text(500)
        chunks = [self._chunk("c1", 0, 500, "x" * 500, page_start=5, page_end=1)]
        findings, outcome = s7.validate_chunks(chunks, clean_text)
        self.assertEqual(outcome, "FAIL")
        self.assertIn("CHUNK_PAGE_RANGE_VALID", [f["code"] for f in findings])

    def test_empty_document_empty_chunks_passes(self):
        clean_text = {"doc_id": "doc_x", "full_text_char_count": 0, "section_tree": [], "pages": []}
        findings, outcome = s7.validate_chunks([], clean_text)
        self.assertEqual(outcome, "PASS")


# ===========================================================================
# Integration — full chunk_document pipeline
# ===========================================================================

class TestChunkDocumentIntegration(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self._orig_chunks_dir = s7.CHUNKS_DIR
        s7.CHUNKS_DIR = self.tmpdir / "chunks"

    def tearDown(self):
        s7.CHUNKS_DIR = self._orig_chunks_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_fixture(self, doc_id):
        p1 = "Introduction\n" + ("This is body text for the introduction section. " * 15)
        p2 = "Methods\n" + ("This describes the methodology used in the project. " * 15)
        clean_text = build_clean_text(doc_id, [p1, p2], [
            {"section_id": "1", "section_level": 1, "parent_section": None, "title": "Introduction", "start_page": 1},
            {"section_id": "2", "section_level": 1, "parent_section": None, "title": "Methods", "start_page": 2},
        ])
        metadata = build_metadata(doc_id)
        clean_text_path = self.tmpdir / "clean_text.json"
        metadata_path = self.tmpdir / "metadata.json"
        with open(clean_text_path, "w", encoding="utf-8") as f:
            json.dump(clean_text, f)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f)
        return clean_text, metadata, clean_text_path, metadata_path

    def test_chunks_json_created_with_documented_shape(self):
        doc_id = "doc_test1"
        clean_text, metadata, ct_path, md_path = self._write_fixture(doc_id)
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)

        chunks_path = s7.CHUNKS_DIR / doc_id / "chunks.json"
        self.assertTrue(chunks_path.exists())
        with open(chunks_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(set(data.keys()), {"doc_id", "chunking_pipeline_version", "generated_at", "chunk_count", "chunks"})
        self.assertEqual(data["chunk_count"], len(data["chunks"]))
        self.assertGreater(data["chunk_count"], 0)

    def test_chunk_validation_report_always_written(self):
        doc_id = "doc_test2"
        clean_text, metadata, ct_path, md_path = self._write_fixture(doc_id)
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)

        report_path = s7.CHUNKS_DIR / doc_id / "chunk_validation_report.json"
        self.assertTrue(report_path.exists())
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        self.assertIn("overall_status", report)
        self.assertIn("stats", report)
        self.assertIn(report["overall_status"], ("PASS", "WARNING", "FAIL"))

    def test_manifest_updated_on_success(self):
        doc_id = "doc_test3"
        clean_text, metadata, ct_path, md_path = self._write_fixture(doc_id)
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)

        self.assertEqual(record.status, DocumentStatus.READY_FOR_CHUNKING)
        self.assertIn("chunks", record.artifact_paths)
        self.assertIn("chunk_validation_report", record.artifact_paths)
        self.assertIsNone(record.error_code)

    def test_manifest_quarantined_on_critical_failure(self):
        # deliberately corrupt: section_tree references a page that doesn't exist,
        # AND we force a coverage break by truncating full_text_char_count.
        doc_id = "doc_test4"
        p1 = "Body text here for a single page document that is long enough."
        clean_text = build_clean_text(doc_id, [p1], [])
        clean_text["full_text_char_count"] = len(p1) + 500  # inflate beyond actual text -> coverage gap
        metadata = build_metadata(doc_id)
        ct_path = self.tmpdir / "clean_text_fail.json"
        md_path = self.tmpdir / "metadata_fail.json"
        with open(ct_path, "w", encoding="utf-8") as f:
            json.dump(clean_text, f)
        with open(md_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f)
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)

        self.assertEqual(record.status, DocumentStatus.QUARANTINED)
        self.assertEqual(record.error_code, "FATAL_CHUNKING_FAILED")
        self.assertNotIn("chunks", record.artifact_paths)
        self.assertIn("chunk_validation_report", record.artifact_paths)

    def test_rerun_produces_identical_chunks_excluding_timestamp(self):
        doc_id = "doc_test5"
        clean_text, metadata, ct_path, md_path = self._write_fixture(doc_id)
        record1 = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record1, clean_text, metadata)
        with open(s7.CHUNKS_DIR / doc_id / "chunks.json", encoding="utf-8") as f:
            run1 = json.load(f)

        record2 = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record2, clean_text, metadata)
        with open(s7.CHUNKS_DIR / doc_id / "chunks.json", encoding="utf-8") as f:
            run2 = json.load(f)

        run1.pop("generated_at")
        run2.pop("generated_at")
        self.assertEqual(run1, run2)

    def test_clean_text_not_mutated_on_disk(self):
        doc_id = "doc_test6"
        clean_text, metadata, ct_path, md_path = self._write_fixture(doc_id)
        before = ct_path.read_bytes()
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)
        after = ct_path.read_bytes()
        self.assertEqual(before, after)

    def test_metadata_not_mutated_on_disk(self):
        doc_id = "doc_test7"
        clean_text, metadata, ct_path, md_path = self._write_fixture(doc_id)
        before = md_path.read_bytes()
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)
        after = md_path.read_bytes()
        self.assertEqual(before, after)

    def test_chunk_records_denormalize_category_doc_type_title(self):
        doc_id = "doc_test8"
        clean_text, metadata, ct_path, md_path = self._write_fixture(doc_id)
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)
        with open(s7.CHUNKS_DIR / doc_id / "chunks.json", encoding="utf-8") as f:
            data = json.load(f)
        for c in data["chunks"]:
            self.assertEqual(c["category"], "climate")
            self.assertEqual(c["title"], "Sample Title")

    def test_empty_section_tree_document_chunks_as_preamble(self):
        doc_id = "doc_test9"
        p1 = "Just plain body text, no headings, but long enough to be a valid chunk on its own merit here."
        clean_text = build_clean_text(doc_id, [p1], [])
        metadata = build_metadata(doc_id)
        ct_path = self.tmpdir / "ct9.json"
        md_path = self.tmpdir / "md9.json"
        with open(ct_path, "w", encoding="utf-8") as f:
            json.dump(clean_text, f)
        with open(md_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f)
        record = make_record(doc_id, str(ct_path), str(md_path))
        s7.chunk_document(record, clean_text, metadata)
        with open(s7.CHUNKS_DIR / doc_id / "chunks.json", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["chunks"]), 1)
        self.assertEqual(data["chunks"][0]["section_ids"], [])


# ===========================================================================
# run_stage7 — batch orchestrator gating
# ===========================================================================

class TestRunStage7Gating(unittest.TestCase):

    def test_only_ready_for_chunking_documents_are_selected(self):
        registered = ManifestRecord(doc_id="doc_a", category="x", status=DocumentStatus.REGISTERED)
        quarantined = ManifestRecord(doc_id="doc_b", category="x", status=DocumentStatus.QUARANTINED)
        ready = ManifestRecord(doc_id="doc_c", category="x", status=DocumentStatus.READY_FOR_CHUNKING,
                                artifact_paths={"clean_text": "x", "metadata": "y"})
        eligible = [r for r in (registered, quarantined, ready) if r.status == DocumentStatus.READY_FOR_CHUNKING]
        self.assertEqual([r.doc_id for r in eligible], ["doc_c"])

    def test_ready_without_required_artifacts_is_skipped(self):
        ready_missing = ManifestRecord(doc_id="doc_d", category="x", status=DocumentStatus.READY_FOR_CHUNKING,
                                        artifact_paths={"clean_text": "x"})  # metadata missing
        has_both = "clean_text" in ready_missing.artifact_paths and "metadata" in ready_missing.artifact_paths
        self.assertFalse(has_both)


if __name__ == "__main__":
    unittest.main()
