import unittest
import sys
import json
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import scripts.stage4_cleaning as stage4
from src.ingestion_types import ManifestRecord, DocumentStatus


class TestPureFunctions(unittest.TestCase):
    """Call the five pipeline functions directly, no file I/O."""

    def test_normalize_whitespace_collapses_spaces(self):
        result = stage4.normalize_whitespace("hello    world")
        self.assertEqual(result, "hello world")

    def test_normalize_whitespace_preserves_paragraph_breaks(self):
        text = "Paragraph one.\n\nParagraph two."
        result = stage4.normalize_whitespace(text)
        self.assertIn("Paragraph one.", result)
        self.assertIn("Paragraph two.", result)
        self.assertIn("\n\n", result)

    def test_repair_dehyphenation_joins_split_word(self):
        result = stage4.repair_dehyphenation("develop-\nment")
        self.assertEqual(result, "development")

    def test_repair_dehyphenation_preserves_real_hyphen(self):
        result = stage4.repair_dehyphenation("well-being")
        self.assertEqual(result, "well-being")

    def test_repair_dehyphenation_preserves_alphanumeric_code(self):
        result = stage4.repair_dehyphenation("COVID-\n19")
        self.assertNotEqual(result, "COVID19")
        self.assertEqual(result, "COVID-\n19")

    def test_remove_headers_footers_strips_repeated_line(self):
        pages = [
            "Ministry of Finance\nBody text page 1",
            "Ministry of Finance\nBody text page 2",
            "Ministry of Finance\nBody text page 3",
            "Ministry of Finance\nBody text page 4",
            "Unique Header\nBody text page 5",
        ]
        excluded = [False] * 5
        result = stage4.remove_headers_footers(pages, excluded)
        for i in range(4):
            self.assertNotIn("Ministry of Finance", result[i])
        self.assertIn("Unique Header", result[4])

    def test_remove_headers_footers_keeps_unique_content(self):
        pages = [
            "Page-local heading A\nBody text 1",
            "Page-local heading B\nBody text 2",
            "Page-local heading C\nBody text 3",
        ]
        excluded = [False] * 3
        result = stage4.remove_headers_footers(pages, excluded)
        self.assertIn("Page-local heading A", result[0])
        self.assertIn("Page-local heading B", result[1])
        self.assertIn("Page-local heading C", result[2])

    def test_repair_encoding_expands_ligature(self):
        result = stage4.repair_encoding("ﬁle")
        self.assertEqual(result, "file")

    def test_repair_encoding_normalizes_nbsp(self):
        result = stage4.repair_encoding("hello\xa0world")
        self.assertEqual(result, "hello world")

    def test_cleaning_functions_are_idempotent(self):
        samples = [
            "hello    world\n\n\n\nmore text  ",
            "develop-\nment continues",
            "ﬁle with\xa0nbsp",
        ]
        for text in samples:
            ws1 = stage4.normalize_whitespace(text)
            ws2 = stage4.normalize_whitespace(ws1)
            self.assertEqual(ws1, ws2)

            dh1 = stage4.repair_dehyphenation(text)
            dh2 = stage4.repair_dehyphenation(dh1)
            self.assertEqual(dh1, dh2)

            enc1 = stage4.repair_encoding(text)
            enc2 = stage4.repair_encoding(enc1)
            self.assertEqual(enc1, enc2)


class TestStage4Integration(unittest.TestCase):
    """Fixture-driven raw_extraction.json -> clean_text.json via clean_document()."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.extracted_dir = Path(self.tmp_dir.name) / "extracted"
        self.extracted_dir.mkdir(parents=True)

        self._orig_extracted_dir = stage4.EXTRACTED_DIR
        stage4.EXTRACTED_DIR = self.extracted_dir

        self.doc_id = "doc_teststage4"
        self.raw_dir = self.extracted_dir / self.doc_id
        self.raw_dir.mkdir(parents=True)
        self.raw_path = self.raw_dir / "raw_extraction.json"

        self.raw_extraction = {
            "doc_id": self.doc_id,
            "extractor": {"markdown": "pymupdf4llm", "layout": "PyMuPDF"},
            "pages": [
                {
                    "page_number": 1,
                    "raw_text": (
                        "Ministry Report\n"
                        "# Executive Summary\n"
                        "- item one\n"
                        "- item two\n"
                        "1. First\n"
                        "2. Second\n"
                        "| A | B |\n"
                        "Page 1 of 3"
                    ),
                    "font_info": [],
                    "layout_metadata": {"table_bboxes": [], "block_count": 5},
                    "character_count": 100,
                    "excluded": False,
                    "exclusion_reason": None,
                },
                {
                    "page_number": 2,
                    "raw_text": (
                        "Ministry Report\n"
                        "More body text on page two.\n"
                        "Page 2 of 3"
                    ),
                    "font_info": [],
                    "layout_metadata": {"table_bboxes": [], "block_count": 2},
                    "character_count": 60,
                    "excluded": False,
                    "exclusion_reason": None,
                },
                {
                    "page_number": 3,
                    "raw_text": "",
                    "font_info": [],
                    "layout_metadata": {"table_bboxes": [], "block_count": 0},
                    "character_count": 0,
                    "excluded": True,
                    "exclusion_reason": "EMPTY_PAGE",
                },
            ],
        }
        with open(self.raw_path, "w", encoding="utf-8") as f:
            json.dump(self.raw_extraction, f, indent=2)

        self.record = ManifestRecord(
            doc_id=self.doc_id,
            category="test_category",
            status=DocumentStatus.REGISTERED,
            artifact_paths={"raw_extraction": str(self.raw_path).replace("\\", "/")},
        )

    def tearDown(self):
        stage4.EXTRACTED_DIR = self._orig_extracted_dir
        self.tmp_dir.cleanup()

    def _run_and_load(self):
        stage4.clean_document(self.record)
        out_path = Path(self.record.artifact_paths["clean_text"])
        return json.loads(out_path.read_text(encoding="utf-8"))

    def test_clean_text_json_created(self):
        stage4.clean_document(self.record)
        out_path = self.extracted_dir / self.doc_id / "clean_text.json"
        self.assertTrue(out_path.exists())

    def test_page_count_preserved(self):
        data = self._run_and_load()
        self.assertEqual(len(data["pages"]), 3)

    def test_page_numbers_not_renumbered(self):
        data = self._run_and_load()
        for i, page in enumerate(data["pages"], start=1):
            self.assertEqual(page["page_number"], i)

    def test_excluded_flag_carried_forward(self):
        data = self._run_and_load()
        self.assertFalse(data["pages"][0]["is_excluded"])
        self.assertFalse(data["pages"][1]["is_excluded"])
        self.assertTrue(data["pages"][2]["is_excluded"])

    def test_markdown_bullets_preserved(self):
        data = self._run_and_load()
        text = data["pages"][0]["text"]
        self.assertIn("- item one", text)
        self.assertIn("- item two", text)

    def test_numbered_list_preserved(self):
        data = self._run_and_load()
        text = data["pages"][0]["text"]
        self.assertIn("1. First", text)
        self.assertIn("2. Second", text)

    def test_table_text_preserved(self):
        data = self._run_and_load()
        text = data["pages"][0]["text"]
        self.assertIn("| A | B |", text)

    def test_char_offsets_are_consistent(self):
        data = self._run_and_load()
        prev_end = 0
        for page in data["pages"]:
            self.assertEqual(page["char_start"], prev_end)
            self.assertEqual(page["char_end"] - page["char_start"], len(page["text"]))
            prev_end = page["char_end"]

    def test_raw_extraction_not_mutated(self):
        before = self.raw_path.read_bytes()
        stage4.clean_document(self.record)
        after = self.raw_path.read_bytes()
        self.assertEqual(before, after)

    def test_pipeline_is_idempotent(self):
        first = stage4.build_clean_text(self.raw_extraction)
        # Feed the first run's output back through as if it were fresh raw_text.
        second_input = {
            "doc_id": self.doc_id,
            "pages": [
                {
                    "page_number": p["page_number"],
                    "raw_text": p["text"],
                    "excluded": p["is_excluded"],
                }
                for p in first["pages"]
            ],
        }
        second = stage4.build_clean_text(second_input)
        for p1, p2 in zip(first["pages"], second["pages"]):
            self.assertEqual(p1["text"], p2["text"])


if __name__ == "__main__":
    unittest.main()
