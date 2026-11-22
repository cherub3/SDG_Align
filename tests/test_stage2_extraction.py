import unittest
import tempfile
import json
from pathlib import Path
import sys
import fitz

# Adjust path to import from src and scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import register_document
from scripts.stage1_integrity import verify_document_integrity
from scripts.stage2_extraction import extract_document


class TestStage2Extraction(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmpdir.name)
        self.extracted_dir = self.base_dir / "extracted"

        # Patch RAW_DIR / EXTRACTED_DIR across all three stage modules
        import scripts.stage0_register
        import scripts.stage1_integrity
        import scripts.stage2_extraction
        self.old_raw_dir0 = scripts.stage0_register.RAW_DIR
        self.old_raw_dir1 = scripts.stage1_integrity.RAW_DIR
        self.old_extracted_dir = scripts.stage2_extraction.EXTRACTED_DIR
        scripts.stage0_register.RAW_DIR = self.base_dir
        scripts.stage1_integrity.RAW_DIR = self.base_dir
        scripts.stage2_extraction.EXTRACTED_DIR = self.extracted_dir

        self.category_dir = self.base_dir / "test_category"
        self.category_dir.mkdir()

        # Build a real 2-page PDF: page one has a heading + body text,
        # page two has body text only.
        self.pdf_path = self.category_dir / "sample.pdf"
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((72, 72), "1. Executive Summary", fontsize=18)
        p1.insert_text((72, 100), "This is body text on page one.", fontsize=10)
        p2 = doc.new_page()
        p2.insert_text((72, 72), "This is body text on page two.", fontsize=10)
        doc.save(self.pdf_path)
        doc.close()

        manifest = {}
        register_document(self.pdf_path, manifest)
        self.doc_id = list(manifest.keys())[0]
        verify_document_integrity(manifest[self.doc_id])
        self.manifest = manifest

    def tearDown(self):
        import scripts.stage0_register
        import scripts.stage1_integrity
        import scripts.stage2_extraction
        scripts.stage0_register.RAW_DIR = self.old_raw_dir0
        scripts.stage1_integrity.RAW_DIR = self.old_raw_dir1
        scripts.stage2_extraction.EXTRACTED_DIR = self.old_extracted_dir
        self.tmpdir.cleanup()

    def _run_and_load(self):
        record = self.manifest[self.doc_id]
        extract_document(record)
        out_path = Path(record.artifact_paths["raw_extraction"])
        return json.loads(out_path.read_text())

    def test_raw_extraction_json_created(self):
        record = self.manifest[self.doc_id]
        extract_document(record)
        out_path = self.extracted_dir / self.doc_id / "raw_extraction.json"
        self.assertTrue(out_path.exists())

    def test_page_count_matches_pdf(self):
        data = self._run_and_load()
        self.assertEqual(len(data["pages"]), 2)

    def test_every_page_has_page_number(self):
        data = self._run_and_load()
        for i, page in enumerate(data["pages"], start=1):
            self.assertEqual(page["page_number"], i)

    def test_layout_metadata_present(self):
        data = self._run_and_load()
        for page in data["pages"]:
            self.assertIn("layout_metadata", page)
            self.assertIsNotNone(page["layout_metadata"])

    def test_block_count_recorded(self):
        data = self._run_and_load()
        for page in data["pages"]:
            self.assertIsInstance(page["layout_metadata"]["block_count"], int)
            self.assertGreaterEqual(page["layout_metadata"]["block_count"], 0)

    def test_table_bboxes_field_exists(self):
        data = self._run_and_load()
        for page in data["pages"]:
            self.assertIn("table_bboxes", page["layout_metadata"])
            self.assertIsInstance(page["layout_metadata"]["table_bboxes"], list)

    def test_font_info_extracted(self):
        data = self._run_and_load()
        page_one_lines = data["pages"][0]["font_info"]
        self.assertTrue(len(page_one_lines) > 0)
        self.assertIn("max_font_size", page_one_lines[0])
        self.assertIn("bold_if_any", page_one_lines[0])


if __name__ == "__main__":
    unittest.main()
