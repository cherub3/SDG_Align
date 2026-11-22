import unittest
import tempfile
from pathlib import Path
import sys
import fitz

# Adjust path to import from src and scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from src.ingestion_types import ManifestRecord, DocumentStatus
from scripts.stage1_integrity import verify_document_integrity, get_now_iso
from scripts.stage0_register import register_document

class TestStage1Integrity(unittest.TestCase):
    
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmpdir.name)
        
        # Patch RAW_DIR in stage1_integrity and ingest_proposals
        import scripts.stage1_integrity
        import scripts.stage0_register
        self.old_raw_dir1 = scripts.stage1_integrity.RAW_DIR
        self.old_raw_dir2 = scripts.stage0_register.RAW_DIR
        scripts.stage1_integrity.RAW_DIR = self.base_dir
        scripts.stage0_register.RAW_DIR = self.base_dir
        
        # Create a category dir
        self.category_dir = self.base_dir / "test_category"
        self.category_dir.mkdir()

    def tearDown(self):
        import scripts.stage1_integrity
        import scripts.stage0_register
        scripts.stage1_integrity.RAW_DIR = self.old_raw_dir1
        scripts.stage0_register.RAW_DIR = self.old_raw_dir2
        self.tmpdir.cleanup()

    def test_valid_pdf_opens(self):
        """Test that a valid PDF opens successfully and page count is recorded."""
        # Create a real, valid tiny PDF using fitz
        pdf_path = self.category_dir / "valid.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()
        
        manifest = {}
        register_document(pdf_path, manifest)
        
        # Get the registered record
        doc_id = list(manifest.keys())[0]
        record = manifest[doc_id]
        
        verify_document_integrity(record)
        
        self.assertEqual(record.status, DocumentStatus.REGISTERED)
        self.assertEqual(record.page_count, 2)
        self.assertIsNone(record.error_code)

    def test_unreadable_pdf_quarantined(self):
        """Test that a corrupted PDF becomes QUARANTINED."""
        pdf_path = self.category_dir / "corrupted.pdf"
        pdf_path.write_bytes(b"Not a real PDF file")
        
        manifest = {}
        register_document(pdf_path, manifest)
        
        doc_id = list(manifest.keys())[0]
        record = manifest[doc_id]
        
        verify_document_integrity(record)
        
        self.assertEqual(record.status, DocumentStatus.QUARANTINED)
        self.assertEqual(record.error_code, "FATAL_UNREADABLE")
        self.assertIsNone(record.page_count)

if __name__ == "__main__":
    unittest.main()
