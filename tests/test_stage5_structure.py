import unittest
import sys
import json
import copy
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import scripts.stage5_structure as stage5
from src.ingestion_types import ManifestRecord, DocumentStatus


def _single_line_clean_text(line: str, page_number: int = 1) -> dict:
    return {
        "doc_id": "doc_test",
        "full_text_char_count": len(line),
        "pages": [
            {"page_number": page_number, "text": line, "char_start": 0,
             "char_end": len(line), "is_excluded": False}
        ],
    }


class TestPureFunctions(unittest.TestCase):
    """Call detect_headings / assign_heading_levels / generate_section_ids /
    build_section_tree / detect_appendices / detect_reference_sections
    directly, no file I/O."""

    def test_detect_headings_numeric(self):
        ct = _single_line_clean_text("2.1 Climate Rationale")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["style"], "numeric")
        self.assertEqual(headings[0]["numbering"], "2.1")
        self.assertEqual(headings[0]["title"], "Climate Rationale")

    def test_detect_headings_roman(self):
        ct = _single_line_clean_text("I. THE PROPOSAL")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["style"], "roman")
        self.assertEqual(headings[0]["numbering"], "I")

    def test_detect_headings_alpha(self):
        ct = _single_line_clean_text("A. Background")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["style"], "alpha")
        self.assertEqual(headings[0]["numbering"], "A")

    def test_detect_headings_markdown(self):
        ct = _single_line_clean_text("## Executive Summary")
        headings = stage5.detect_headings(ct, {})
        headings = stage5.assign_heading_levels(headings)
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["style"], "markdown")
        self.assertEqual(headings[0]["section_level"], 2)

    def test_detect_headings_mixed_styles_in_one_document(self):
        text = "# Executive Summary\n2. Programme Description\nI. THE PROPOSAL"
        ct = _single_line_clean_text(text)
        headings = stage5.detect_headings(ct, {})
        styles = [h["style"] for h in headings]
        self.assertEqual(styles, ["markdown", "numeric", "roman"])

    def test_detect_headings_font_emphasis_fallback(self):
        text = "Body text at normal size.\nKey Findings\nMore body text here."
        ct = _single_line_clean_text(text)
        font_info = {1: [
            {"text": "Body text at normal size.", "max_font_size": 10.0, "bold_if_any": False, "bbox": [0, 0, 1, 1]},
            {"text": "Key Findings", "max_font_size": 18.0, "bold_if_any": False, "bbox": [0, 0, 1, 1]},
            {"text": "More body text here.", "max_font_size": 10.0, "bold_if_any": False, "bbox": [0, 0, 1, 1]},
        ]}
        headings = stage5.detect_headings(ct, font_info)
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["style"], "font_emphasis")
        self.assertEqual(headings[0]["title"], "Key Findings")

    def test_detect_headings_font_emphasis_requires_correlation(self):
        # The cleaned text at this position no longer matches the
        # font_info entry's text (simulates Stage 4 altering the line
        # beyond recognition) -- font-emphasis must not fire.
        text = "Body text.\nSomething totally different and unrelated.\nMore body text."
        ct = _single_line_clean_text(text)
        font_info = {1: [
            {"text": "Body text.", "max_font_size": 10.0, "bold_if_any": False, "bbox": [0, 0, 1, 1]},
            {"text": "Key Findings", "max_font_size": 18.0, "bold_if_any": False, "bbox": [0, 0, 1, 1]},
            {"text": "More body text.", "max_font_size": 10.0, "bold_if_any": False, "bbox": [0, 0, 1, 1]},
        ]}
        headings = stage5.detect_headings(ct, font_info)
        self.assertEqual(len(headings), 0)

    def test_detect_headings_rejects_table_row(self):
        # Regression test (found on the real corpus): a short, all-caps
        # table cell like a code column must not be misclassified as a
        # heading via the caps-unnumbered fallback -- pipe syntax marks it
        # as table content, per _is_table_row.
        ct = _single_line_clean_text("|WWF-US|G0061|")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 0)

    def test_detect_headings_caps_unnumbered(self):
        ct = _single_line_clean_text("EXECUTIVE SUMMARY")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["style"], "caps_unnumbered")

    def test_detect_headings_rejects_long_body_line(self):
        long_line = "This is a very long sentence that goes on and on " * 4
        ct = _single_line_clean_text(long_line.strip())
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 0)

    def test_detect_headings_rejects_bullet_line(self):
        ct = _single_line_clean_text("- 2.1 not a heading, a list item")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 0)

    def test_detect_headings_rejects_bare_quantity(self):
        # Regression test: "20 people attended..." must not be classified
        # as numeric heading numbering "20" -- see _try_numeric's guard.
        ct = _single_line_clean_text("20 people attended the workshop in Dhaka")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 0)

    def test_precedence_markdown_over_numeric(self):
        ct = _single_line_clean_text("# 2.1 Title")
        headings = stage5.detect_headings(ct, {})
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["style"], "markdown")

    def test_generate_section_ids_uses_native_numbering(self):
        ct = _single_line_clean_text("2.1.1 Baseline Vulnerability")
        headings = stage5.detect_headings(ct, {})
        headings = stage5.assign_heading_levels(headings)
        headings = stage5.generate_section_ids(headings)
        self.assertEqual(headings[0]["section_id"], "2.1.1")

    def test_generate_section_ids_synthesizes_when_unnumbered(self):
        text = "EXECUTIVE SUMMARY\nABOUT THIS DOCUMENT"
        ct = _single_line_clean_text(text)
        headings = stage5.detect_headings(ct, {})
        headings = stage5.assign_heading_levels(headings)
        headings = stage5.generate_section_ids(headings)
        self.assertEqual(headings[0]["section_id"], "s1")
        self.assertEqual(headings[1]["section_id"], "s2")

    def test_generate_section_ids_synthesizes_child(self):
        text = "# Overview\n## First Sub\n## Second Sub\n## Third Sub"
        ct = _single_line_clean_text(text)
        headings = stage5.detect_headings(ct, {})
        headings = stage5.assign_heading_levels(headings)
        headings = stage5.generate_section_ids(headings)
        self.assertEqual(headings[0]["section_id"], "s1")
        self.assertEqual(headings[1]["section_id"], "s1a")
        self.assertEqual(headings[2]["section_id"], "s1b")
        self.assertEqual(headings[3]["section_id"], "s1c")

    def test_generate_section_ids_deterministic_across_runs(self):
        text = "EXECUTIVE SUMMARY\n2. Programme Description\nABOUT THIS DOCUMENT"
        ct = _single_line_clean_text(text)
        base = stage5.assign_heading_levels(stage5.detect_headings(ct, {}))
        run1 = stage5.generate_section_ids(copy.deepcopy(base))
        run2 = stage5.generate_section_ids(copy.deepcopy(base))
        ids1 = [h["section_id"] for h in run1]
        ids2 = [h["section_id"] for h in run2]
        self.assertEqual(ids1, ids2)

    def test_detect_appendices_matches_annex_a(self):
        section_tree = [
            {"section_id": "s1", "section_level": 1, "parent_section": None, "title": "ANNEX A", "start_page": 10},
            {"section_id": "s2", "section_level": 1, "parent_section": None, "title": "APPENDIX B", "start_page": 12},
            {"section_id": "s3", "section_level": 1, "parent_section": None, "title": "Overview", "start_page": 1},
        ]
        result = stage5.detect_appendices(section_tree)
        self.assertEqual(set(result), {"s1", "s2"})

    def test_detect_reference_sections_matches_bibliography(self):
        section_tree = [
            {"section_id": "s1", "section_level": 1, "parent_section": None, "title": "BIBLIOGRAPHY", "start_page": 40},
            {"section_id": "s2", "section_level": 1, "parent_section": None, "title": "REFERENCES", "start_page": 42},
            {"section_id": "s3", "section_level": 1, "parent_section": None, "title": "Overview", "start_page": 1},
        ]
        result = stage5.detect_reference_sections(section_tree)
        self.assertEqual(set(result), {"s1", "s2"})

    def test_detect_appendices_ignores_body_text_mentions(self):
        section_tree = [
            {"section_id": "s1", "section_level": 1, "parent_section": None,
             "title": "Overview", "start_page": 1},
        ]
        # Body text mentioning "appendix" is never part of section_tree
        # titles in the first place -- this test documents that matching
        # is title-only by construction, using a title that itself is not
        # an appendix marker even though a body sentence might mention one.
        result = stage5.detect_appendices(section_tree)
        self.assertEqual(result, [])


class TestStage5Integration(unittest.TestCase):
    """Fixture-driven clean_text.json (+ raw_extraction.json) -> tagged
    clean_text.json via tag_document()."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp_dir.name)
        self.doc_id = "doc_teststage5"

        self.clean_text = {
            "doc_id": self.doc_id,
            "full_text_char_count": 0,
            "pages": [
                {
                    "page_number": 1,
                    "text": (
                        "# Executive Summary\n\n"
                        "This programme addresses climate vulnerability.\n\n"
                        "2. Programme Description\n\n"
                        "Some descriptive text.\n\n"
                        "2.1 Climate Rationale\n\n"
                        "More text about climate."
                    ),
                    "char_start": 0, "char_end": 100, "is_excluded": False,
                },
                {
                    "page_number": 2,
                    "text": (
                        "2.1.1 Baseline Vulnerability\n\n"
                        "Detail text about the baseline.\n\n"
                        "ANNEX A\n\n"
                        "Annex text goes here.\n\n"
                        "BIBLIOGRAPHY\n\n"
                        "Some citation text."
                    ),
                    "char_start": 100, "char_end": 200, "is_excluded": False,
                },
            ],
        }
        self.clean_text_path = self.base_dir / "clean_text.json"
        with open(self.clean_text_path, "w", encoding="utf-8") as f:
            json.dump(self.clean_text, f, indent=2)

        self.raw_extraction = {
            "doc_id": self.doc_id,
            "extractor": {"markdown": "pymupdf4llm", "layout": "PyMuPDF"},
            "pages": [
                {"page_number": 1, "raw_text": "...", "font_info": [], "layout_metadata": {}},
                {"page_number": 2, "raw_text": "...", "font_info": [], "layout_metadata": {}},
            ],
        }
        self.raw_extraction_path = self.base_dir / "raw_extraction.json"
        with open(self.raw_extraction_path, "w", encoding="utf-8") as f:
            json.dump(self.raw_extraction, f, indent=2)

        self.record = ManifestRecord(
            doc_id=self.doc_id,
            category="test_category",
            status=DocumentStatus.REGISTERED,
            artifact_paths={
                "clean_text": str(self.clean_text_path).replace("\\", "/"),
                "raw_extraction": str(self.raw_extraction_path).replace("\\", "/"),
            },
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _run_and_load(self):
        stage5.tag_document(self.record)
        return json.loads(self.clean_text_path.read_text(encoding="utf-8"))

    def test_section_tree_created(self):
        data = self._run_and_load()
        self.assertIn("section_tree", data)
        self.assertTrue(len(data["section_tree"]) > 0)

    def test_parent_child_hierarchy(self):
        data = self._run_and_load()
        by_id = {s["section_id"]: s for s in data["section_tree"]}
        self.assertIn("2", by_id)
        self.assertIn("2.1", by_id)
        self.assertIn("2.1.1", by_id)
        self.assertIsNone(by_id["2"]["parent_section"])
        self.assertEqual(by_id["2.1"]["parent_section"], "2")
        self.assertEqual(by_id["2.1.1"]["parent_section"], "2.1")
        self.assertEqual(by_id["2"]["section_level"], 1)
        self.assertEqual(by_id["2.1"]["section_level"], 2)
        self.assertEqual(by_id["2.1.1"]["section_level"], 3)

    def test_page_headings_populated(self):
        data = self._run_and_load()
        page1_headings = data["pages"][0]["headings"]
        page2_headings = data["pages"][1]["headings"]
        for h in page1_headings + page2_headings:
            self.assertEqual(set(h.keys()), {"section_id", "title"})
        page1_ids = {h["section_id"] for h in page1_headings}
        page2_ids = {h["section_id"] for h in page2_headings}
        self.assertTrue(page1_ids)
        self.assertTrue(page2_ids)
        self.assertNotIn("2.1.1", page1_ids)
        self.assertIn("2.1.1", page2_ids)

    def test_no_page_text_modified(self):
        before_pages = copy.deepcopy(self.clean_text["pages"])
        data = self._run_and_load()
        for before, after in zip(before_pages, data["pages"]):
            self.assertEqual(before["text"], after["text"])
            self.assertEqual(before["char_start"], after["char_start"])
            self.assertEqual(before["char_end"], after["char_end"])
            self.assertEqual(before["is_excluded"], after["is_excluded"])

    def test_raw_extraction_not_mutated(self):
        before = self.raw_extraction_path.read_bytes()
        stage5.tag_document(self.record)
        after = self.raw_extraction_path.read_bytes()
        self.assertEqual(before, after)

    def test_rerun_produces_identical_output(self):
        first = self._run_and_load()
        second = self._run_and_load()
        self.assertEqual(first["section_tree"], second["section_tree"])
        for p1, p2 in zip(first["pages"], second["pages"]):
            self.assertEqual(p1["headings"], p2["headings"])

    def test_missing_raw_extraction_degrades_gracefully(self):
        del self.record.artifact_paths["raw_extraction"]
        stage5.tag_document(self.record)
        self.assertEqual(self.record.status, DocumentStatus.REGISTERED)
        data = json.loads(self.clean_text_path.read_text(encoding="utf-8"))
        self.assertIn("section_tree", data)
        self.assertTrue(len(data["section_tree"]) > 0)

    def test_appendix_and_reference_sections_detected_end_to_end(self):
        data = self._run_and_load()
        titles = {s["section_id"]: s["title"] for s in data["section_tree"]}
        appendix_matches = [sid for sid, title in titles.items() if stage5.APPENDIX_RE.match(title)]
        reference_matches = [sid for sid, title in titles.items() if stage5.REFERENCES_RE.match(title)]
        self.assertTrue(appendix_matches)
        self.assertTrue(reference_matches)


if __name__ == "__main__":
    unittest.main()
