import unittest
import tempfile
import hashlib
from pathlib import Path
import sys

# Adjust path to import from src and scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from src.ingestion_types import ManifestRecord, DocumentStatus
from scripts.stage0_register import compute_sha256, register_document

class TestStage0Manifest(unittest.TestCase):
    
    def test_compute_sha256(self):
        """Test SHA-256 generation."""
        content = b"fake pdf content"
        expected_hash = hashlib.sha256(content).hexdigest()
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
            
        try:
            actual_hash = compute_sha256(tmp_path)
            self.assertEqual(expected_hash, actual_hash)
        finally:
            tmp_path.unlink()

    def test_category_detection(self):
        """Test that category is correctly derived from the parent folder."""
        manifest = {}
        content = b"content for category test"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock raw directory structure
            base_dir = Path(tmpdir)
            category_dir = base_dir / "climate"
            category_dir.mkdir()
            mock_pdf = category_dir / "test.pdf"
            mock_pdf.write_bytes(content)
            
            # Run the registration logic on a single document
            register_document(mock_pdf, manifest)
            
            self.assertEqual(len(manifest), 1)
            record = list(manifest.values())[0]
            self.assertEqual(record.category, "climate")
            self.assertEqual(record.status, DocumentStatus.REGISTERED)

    def test_duplicate_detection(self):
        """Test that duplicate documents are skipped."""
        manifest = {}
        content = b"content for duplicate test"
        file_hash = hashlib.sha256(content).hexdigest()
        doc_id = f"doc_{file_hash}"
        
        # Pre-populate manifest to simulate a duplicate
        manifest[doc_id] = ManifestRecord(
            doc_id=doc_id,
            category="health",
            status=DocumentStatus.READY_FOR_CHUNKING
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            category_dir = base_dir / "water"
            category_dir.mkdir()
            mock_pdf = category_dir / "test2.pdf"
            mock_pdf.write_bytes(content)
            
            register_document(mock_pdf, manifest)
            
            # The manifest should still have exactly 1 record, and it should remain the original one
            self.assertEqual(len(manifest), 1)
            self.assertEqual(manifest[doc_id].category, "health")
            self.assertEqual(manifest[doc_id].status, DocumentStatus.READY_FOR_CHUNKING)

    def test_manifest_serialization_round_trip(self):
        """Test ManifestRecord serialization round-trip to dict."""
        record = ManifestRecord(
            doc_id="doc_12345",
            category="biodiversity",
            status=DocumentStatus.REGISTERED,
            doc_type="RRP",
            started_at="2026-07-18T10:04:00Z",
            artifact_paths={"clean_text": "path/to/clean.json"}
        )
        
        # Serialize
        record_dict = record.to_dict()
        self.assertEqual(record_dict["doc_id"], "doc_12345")
        self.assertEqual(record_dict["category"], "biodiversity")
        self.assertEqual(record_dict["doc_type"], "RRP")
        self.assertEqual(record_dict["artifact_paths"], {"clean_text": "path/to/clean.json"})
        
        # Deserialize
        rehydrated = ManifestRecord.from_dict(record_dict)
        self.assertEqual(rehydrated.doc_id, record.doc_id)
        self.assertEqual(rehydrated.category, record.category)
        self.assertEqual(rehydrated.status, record.status)
        self.assertEqual(rehydrated.doc_type, record.doc_type)
        self.assertEqual(rehydrated.started_at, record.started_at)
        self.assertEqual(rehydrated.artifact_paths, record.artifact_paths)
        
if __name__ == "__main__":
    unittest.main()


class TestMovedDocuments(unittest.TestCase):
    """The category comes from the folder, so a document moved between folders must be re-categorised."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.old = self.root / "raw" / "climate" / "doc.pdf"
        self.new = self.root / "raw" / "biodiversity" / "doc.pdf"
        for d in (self.old.parent, self.new.parent):
            d.mkdir(parents=True)
        self.old.write_bytes(b"same bytes")

    def _registered(self):
        manifest = {}
        self.assertTrue(register_document(self.old, manifest))
        (doc_id,) = manifest
        return manifest, doc_id

    def test_moved_file_updates_category_and_source_path_but_keeps_the_record(self):
        manifest, doc_id = self._registered()
        manifest[doc_id].status = DocumentStatus.READY_FOR_CHUNKING
        self.old.rename(self.new)

        self.assertTrue(register_document(self.new, manifest))

        self.assertEqual(list(manifest), [doc_id])                       # same doc_id, no second record
        self.assertEqual(manifest[doc_id].category, "biodiversity")
        self.assertEqual(manifest[doc_id].source_path, str(self.new).replace("\\", "/"))
        self.assertEqual(manifest[doc_id].status, DocumentStatus.READY_FOR_CHUNKING)  # progress is kept

    def test_second_copy_while_the_original_still_exists_is_a_duplicate_not_a_move(self):
        manifest, doc_id = self._registered()
        self.new.write_bytes(b"same bytes")                              # copy, original still in place

        register_document(self.new, manifest)

        self.assertEqual(manifest[doc_id].category, "climate")           # first registration wins
        self.assertEqual(manifest[doc_id].source_path, str(self.old).replace("\\", "/"))

    def test_re_registering_an_unmoved_file_changes_nothing(self):
        manifest, doc_id = self._registered()
        before = (manifest[doc_id].category, manifest[doc_id].source_path)
        register_document(self.old, manifest)
        self.assertEqual((manifest[doc_id].category, manifest[doc_id].source_path), before)

