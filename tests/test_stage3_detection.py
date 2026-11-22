import unittest
import tempfile
import json
from pathlib import Path
import sys

# Adjust path to import from src and scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from src.ingestion_types import ManifestRecord, DocumentStatus
from scripts.stage3_detection import process_document, MIN_CHARS_PER_PAGE

class TestStage3Detection(unittest.TestCase):
    
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmpdir.name)
        
        import scripts.stage3_detection
        self.old_extracted_dir = scripts.stage3_detection.EXTRACTED_DIR
        scripts.stage3_detection.EXTRACTED_DIR = self.base_dir
        
    def tearDown(self):
        import scripts.stage3_detection
        scripts.stage3_detection.EXTRACTED_DIR = self.old_extracted_dir
        self.tmpdir.cleanup()

    def test_evaluate_pages(self):
        """Test evaluation of empty, low density, and normal pages."""
        doc_id = "doc_test_123"
        doc_dir = self.base_dir / doc_id
        doc_dir.mkdir()
        
        raw_extraction_path = doc_dir / "raw_extraction.json"
        
        # Create raw extraction content
        content = {
            "doc_id": doc_id,
            "pages": [
                {"page_number": 1, "raw_text": "   \n\t  "},
                {"page_number": 2, "raw_text": "Short text"},
                {"page_number": 3, "raw_text": "A" * MIN_CHARS_PER_PAGE}
            ]
        }
        
        with open(raw_extraction_path, "w", encoding="utf-8") as f:
            json.dump(content, f)
            
        record = ManifestRecord(
            doc_id=doc_id,
            category="climate",
            status=DocumentStatus.REGISTERED,
            artifact_paths={"raw_extraction": str(raw_extraction_path)}
        )
        
        process_document(record)
        
        # Ensure status didn't fail (ISSUE 2: remains REGISTERED on success)
        self.assertEqual(record.status, DocumentStatus.REGISTERED)
        
        # Read it back and verify
        with open(raw_extraction_path, "r", encoding="utf-8") as f:
            result = json.load(f)
            
        pages = result["pages"]
        self.assertEqual(len(pages), 3)
        
        # 1. Empty page
        self.assertTrue(pages[0]["excluded"])
        self.assertEqual(pages[0]["exclusion_reason"], "EMPTY_PAGE")
        self.assertEqual(pages[0]["character_count"], 0)
        
        # 2. Low density page
        self.assertTrue(pages[1]["excluded"])
        self.assertEqual(pages[1]["exclusion_reason"], "LOW_CHARACTER_DENSITY")
        self.assertEqual(pages[1]["character_count"], len("Short text"))
        
        # 3. Normal page
        self.assertFalse(pages[2]["excluded"])
        self.assertIsNone(pages[2]["exclusion_reason"])
        self.assertEqual(pages[2]["character_count"], MIN_CHARS_PER_PAGE)

    def test_batch_continues_after_failure(self):
        """Test that if a document has missing artifact, it fails cleanly but won't throw."""
        # Issue 3: No fallback. If artifact_paths is empty or file missing, use QUARANTINED
        record = ManifestRecord(
            doc_id="doc_missing",
            category="climate",
            status=DocumentStatus.REGISTERED
        )
        
        process_document(record)
        
        # Issue 2: Uses existing DocumentStatus enum, no FAILED
        self.assertEqual(record.status, DocumentStatus.QUARANTINED)
        self.assertEqual(record.error_code, "FATAL_UNREADABLE")
        self.assertIsNotNone(record.completed_at)

if __name__ == "__main__":
    unittest.main()
