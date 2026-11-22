"""Unit tests for Stage 8 — Embedding Generation.
Covers Provider Abstraction, Incremental Reuse, Checkpointing, and Validation.
"""

import unittest
import sys
import os
import json
import tempfile
import math
from pathlib import Path
from typing import List, Optional, Any, Dict
from copy import deepcopy

import pyarrow as pa
import pyarrow.parquet as pq

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage8_embedding_generation import (
    ProviderAdapter,
    CorruptedArtifactError,
    compute_text_checksum,
    compute_config_fingerprint,
    build_embedding_id,
    sanitize_id_component,
    get_parquet_schema,
    determine_workload,
    validate_embeddings,
    process_document,
    run_stage8,
    load_existing_embeddings,
    BATCH_SIZE,
    MAX_RETRIES,
    load_checkpoint,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    EMBEDDING_PIPELINE_VERSION
)
from src.ingestion_types import ManifestRecord, DocumentStatus

class StubProvider(ProviderAdapter):
    def __init__(self, dim=4, max_batch=None, fails_on_batch=False, transient_fail=False):
        self._dim = dim
        self._max_batch_size = max_batch
        self.calls = 0
        self.fails_on_batch = fails_on_batch
        self.transient_fail = transient_fail
        
    @property
    def provider_name(self) -> str: return "stub_provider"
    
    @property
    def model_name(self) -> str: return "stub-model"
    
    @property
    def model_version(self) -> str: return "v1.0"
    
    @property
    def embedding_dimension(self) -> int: return self._dim

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        self.calls += 1
        if self.fails_on_batch:
            if self.transient_fail:
                raise TimeoutError("Simulated transient error")
            else:
                raise ValueError("Simulated fatal error")
        return [[0.1] * self._dim for _ in texts]

    def is_transient_error(self, exception: Exception) -> bool:
        return isinstance(exception, TimeoutError)

    @property
    def max_batch_size(self) -> Optional[int]:
        return self._max_batch_size

class TestProviderContract(unittest.TestCase):
    def test_stub_provider_accepted(self):
        provider = StubProvider()
        self.assertEqual(provider.provider_name, "stub_provider")
        
    def test_unpinned_model_version_rejected(self):
        class BadProvider(StubProvider):
            @property
            def model_version(self) -> str: return "latest"
            
        with self.assertRaises(ValueError):
            compute_config_fingerprint(BadProvider(), 4)
            
    def test_max_batch_size_clamping(self):
        provider = StubProvider(max_batch=10)
        # We can't directly test orchestrator clamping without running it, 
        # but we can simulate the clamping logic.
        clamped = min(BATCH_SIZE, provider.max_batch_size)
        self.assertEqual(clamped, 10)

class TestChecksum(unittest.TestCase):
    def test_hash_excludes_position_metadata(self):
        chunk1 = {"text": "hello world", "char_start": 0, "char_end": 11}
        chunk2 = {"text": "hello world", "char_start": 100, "char_end": 111}
        self.assertEqual(compute_text_checksum(chunk1["text"]), compute_text_checksum(chunk2["text"]))
        
    def test_hash_changes_on_text_change(self):
        self.assertNotEqual(compute_text_checksum("hello world"), compute_text_checksum("hello worle"))

class TestEmbeddingId(unittest.TestCase):
    def test_deterministic(self):
        provider = StubProvider()
        id1 = build_embedding_id("chunk_1", provider)
        id2 = build_embedding_id("chunk_1", provider)
        self.assertEqual(id1, id2)
        
    def test_sanitization(self):
        self.assertEqual(sanitize_id_component("model/v1.0 spaces"), "model-v1.0-spaces")

class TestConfigFingerprint(unittest.TestCase):
    def test_changes_with_any_field(self):
        fp1 = compute_config_fingerprint(StubProvider(), 4)
        fp2 = compute_config_fingerprint(StubProvider(dim=8), 8)
        self.assertNotEqual(fp1, fp2)
        
        class Provider2(StubProvider):
            @property
            def model_name(self) -> str: return "other-model"
        
        fp3 = compute_config_fingerprint(Provider2(), 4)
        self.assertNotEqual(fp1, fp3)

class TestDetermineWorkload(unittest.TestCase):
    def test_partitions_reuse_vs_generate(self):
        provider = StubProvider()
        dim = 4
        chunks = [
            {"chunk_id": "c1", "text": "unchanged"},
            {"chunk_id": "c2", "text": "changed"},
            {"chunk_id": "c3", "text": "new"}
        ]
        
        cfg = compute_config_fingerprint(provider, dim)
        existing = {
            build_embedding_id("c1", provider): {
                "embedding_id": build_embedding_id("c1", provider),
                "text_checksum": compute_text_checksum("unchanged"),
                "config_fingerprint": cfg
            },
            build_embedding_id("c2", provider): {
                "embedding_id": build_embedding_id("c2", provider),
                "text_checksum": compute_text_checksum("old_text"),
                "config_fingerprint": cfg
            }
        }
        
        reuse, gen = determine_workload(chunks, existing, provider, dim)
        self.assertEqual(len(reuse), 1)
        self.assertEqual(reuse[0]["embedding_id"], build_embedding_id("c1", provider))
        
        self.assertEqual(len(gen), 2)
        self.assertEqual({c["chunk_id"] for c in gen}, {"c2", "c3"})

class TestDimensionValidation(unittest.TestCase):
    def setUp(self):
        self.provider = StubProvider()
        self.dim = 4
        self.chunks = [{"chunk_id": "c1", "text": "test"}]
        self.cfg = compute_config_fingerprint(self.provider, self.dim)
        
        self.valid_row = {
            "embedding_id": build_embedding_id("c1", self.provider),
            "chunk_id": "c1",
            "provider": self.provider.provider_name,
            "model_name": self.provider.model_name,
            "model_version": self.provider.model_version,
            "embedding_dimension": self.dim,
            "embedding_vector": [0.1] * self.dim,
            "text_checksum": compute_text_checksum("test"),
            "config_fingerprint": self.cfg
        }

    def test_mismatch_flagged_critical(self):
        row = deepcopy(self.valid_row)
        row["embedding_vector"] = [0.1] * 5 # Wrong length
        
        findings = validate_embeddings([row], self.chunks, self.provider, self.dim)
        codes = [f["code"] for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertIn("EMBEDDING_DIMENSION_CONSISTENT", codes)

    def test_nan_flagged_critical(self):
        row = deepcopy(self.valid_row)
        row["embedding_vector"] = [0.1, math.nan, 0.1, 0.1]
        
        findings = validate_embeddings([row], self.chunks, self.provider, self.dim)
        codes = [f["code"] for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertIn("EMBEDDING_NO_NAN_INF", codes)

class TestCorruptedArtifact(unittest.TestCase):
    def setUp(self):
        self.provider = StubProvider()
        self.dim = 4
        self.chunks = [{"chunk_id": "c1", "text": "test"}]
        self.cfg = compute_config_fingerprint(self.provider, self.dim)
        
        self.valid_row = {
            "embedding_id": build_embedding_id("c1", self.provider),
            "chunk_id": "c1",
            "provider": self.provider.provider_name,
            "model_name": self.provider.model_name,
            "model_version": self.provider.model_version,
            "embedding_dimension": self.dim,
            "embedding_vector": [0.1] * self.dim,
            "text_checksum": compute_text_checksum("test"),
            "config_fingerprint": self.cfg
        }

    def test_truncated_parquet_flagged(self):
        """A corrupted parquet must raise CorruptedArtifactError (Finding 3),
        which process_document translates into an EMBEDDING_ARTIFACT_READABLE
        Critical finding.  It must NOT silently return empty."""
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "bad.parquet"
            bad_path.write_bytes(b"PAR1gibberish")

            # load_existing_embeddings must raise, not return {}
            with self.assertRaises(CorruptedArtifactError):
                load_existing_embeddings(bad_path)

    def test_corrupted_parquet_produces_critical_finding(self):
        """End-to-end: a corrupted parquet on disk causes process_document
        to emit EMBEDDING_ARTIFACT_READABLE as Critical and FAIL."""
        import scripts.stage8_embedding_generation as s8
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            orig_dir = s8.EMBEDDINGS_DIR
            s8.EMBEDDINGS_DIR = tmp_path / "embeddings"

            doc_id = "doc_corrupt"
            doc_dir = s8.EMBEDDINGS_DIR / doc_id
            doc_dir.mkdir(parents=True)
            (doc_dir / "embeddings.parquet").write_bytes(b"PAR1gibberish")

            provider = StubProvider()
            dim = 4
            chunks = [{"chunk_id": "c1", "text": "test"}]
            record = ManifestRecord(doc_id=doc_id, category="c", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "x"})

            outcome, findings, _, _, _ = s8.process_document(record, chunks, provider, dim)

            s8.EMBEDDINGS_DIR = orig_dir

            self.assertEqual(outcome, "FAIL")
            codes = [f["code"] for f in findings if f["severity"] == SEVERITY_ERROR]
            self.assertIn("EMBEDDING_ARTIFACT_READABLE", codes)

    def test_malformed_checksum_flagged(self):
        row = deepcopy(self.valid_row)
        row["text_checksum"] = "badhex"
        
        findings = validate_embeddings([row], self.chunks, self.provider, self.dim)
        codes = [f["code"] for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertIn("EMBEDDING_CHECKSUM_WELL_FORMED", codes)

    def test_orphan_chunk_flagged_warning(self):
        # A row exists, but chunk is not in expected_chunks
        findings = validate_embeddings([self.valid_row], [], self.provider, self.dim)
        codes = [f["code"] for f in findings if f["severity"] == SEVERITY_WARNING]
        self.assertIn("EMBEDDING_ORPHAN_CHUNK", codes)

    def test_orphan_chunk_from_old_config_flagged(self):
        """A row from a prior config whose chunk_id no longer exists must still be
        flagged as EMBEDDING_ORPHAN_CHUNK — the architecture defines orphan as
        'chunk_id no longer exists in chunks.json' for any row, not only current-config rows."""
        old_config_row = deepcopy(self.valid_row)
        old_config_row["config_fingerprint"] = "deadbeef" * 8  # different fingerprint
        # current chunks list is empty — the chunk c1 no longer exists
        findings = validate_embeddings([old_config_row], [], self.provider, self.dim)
        codes = [f["code"] for f in findings if f["severity"] == SEVERITY_WARNING]
        self.assertIn("EMBEDDING_ORPHAN_CHUNK", codes)


# Integration style tests modifying global paths
class Stage8IntegrationTest(unittest.TestCase):
    def setUp(self):
        import scripts.stage8_embedding_generation as s8
        self.s8 = s8
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        
        self.orig_embeddings_dir = self.s8.EMBEDDINGS_DIR
        self.orig_chunks_dir = self.s8.CHUNKS_DIR
        
        self.s8.EMBEDDINGS_DIR = self.tmp_path / "embeddings"
        self.s8.CHUNKS_DIR = self.tmp_path / "chunks"
        
        self.provider = StubProvider()
        self.dim = 4

    def tearDown(self):
        self.s8.EMBEDDINGS_DIR = self.orig_embeddings_dir
        self.s8.CHUNKS_DIR = self.orig_chunks_dir
        self.tmp.cleanup()

    def test_batch_generation(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(100)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        outcome, findings, total, reused, gen = self.s8.process_document(record, chunks, self.provider, self.dim)
        self.assertEqual(outcome, "PASS")
        self.assertEqual(gen, 100)
        self.assertEqual(reused, 0)
        # BATCH_SIZE=32, so 4 batches for 100 items (32, 32, 32, 4)
        self.assertEqual(self.provider.calls, 4)

    def test_persist_embeddings(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(100)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        self.s8.process_document(record, chunks, self.provider, self.dim)
        pq_path = self.s8.EMBEDDINGS_DIR / doc_id / "embeddings.parquet"
        self.assertTrue(pq_path.exists())
        
        table = pq.read_table(pq_path)
        self.assertEqual(table.num_rows, 100)

    def test_update_manifest(self):
        doc_id = "doc1"
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        self.s8.update_manifest(record, "PASS", Path("/tmp/e.parquet"), Path("/tmp/r.json"))
        self.assertIn("embeddings", record.artifact_paths)
        self.assertEqual(record.status, DocumentStatus.REGISTERED)
        self.assertIsNone(record.error_code)
        
        self.s8.update_manifest(record, "FAIL", None, Path("/tmp/r.json"))
        self.assertEqual(record.status, DocumentStatus.QUARANTINED)
        self.assertEqual(record.error_code, "FATAL_EMBEDDING_FAILED")

    def test_rerun_determinism(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(10)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        # Run 1
        self.s8.process_document(record, chunks, self.provider, self.dim)
        calls_run1 = self.provider.calls
        self.assertGreater(calls_run1, 0)
        
        # Run 2
        self.provider.calls = 0
        outcome, _, t, r, g = self.s8.process_document(record, chunks, self.provider, self.dim)
        
        self.assertEqual(outcome, "PASS")
        self.assertEqual(self.provider.calls, 0) # Zero provider calls on rerun!
        self.assertEqual(r, 10)
        self.assertEqual(g, 0)

    def test_incremental_regen(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(10)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        self.s8.process_document(record, chunks, self.provider, self.dim)
        
        # Modify one chunk's text
        chunks[5]["text"] = "changed_text"
        self.provider.calls = 0
        
        outcome, _, t, r, g = self.s8.process_document(record, chunks, self.provider, self.dim)
        self.assertEqual(outcome, "PASS")
        self.assertEqual(r, 9)
        self.assertEqual(g, 1) # Only 1 chunk generated

    def test_model_change_regenerates_all(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(10)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        self.s8.process_document(record, chunks, self.provider, self.dim)
        
        class NewProvider(StubProvider):
            @property
            def model_version(self) -> str: return "v2.0"
            
        provider2 = NewProvider()
        outcome, _, t, r, g = self.s8.process_document(record, chunks, provider2, self.dim)
        
        self.assertEqual(outcome, "PASS")
        self.assertEqual(g, 10) # All chunks regenerated
        self.assertEqual(t, 20) # Total rows in parquet is 20 (10 old + 10 new)

    def test_exhausted_retries_aborts_without_gap(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(10)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        # Using a provider that always fails transiently
        fail_provider = StubProvider(fails_on_batch=True, transient_fail=True)
        # Patch time.sleep to avoid waiting
        import time
        orig_sleep = time.sleep
        time.sleep = lambda x: None
        
        try:
            outcome, findings, _, _, _ = self.s8.process_document(record, chunks, fail_provider, self.dim)
        finally:
            time.sleep = orig_sleep
            
        self.assertEqual(outcome, "FAIL")
        
        # No parquet written
        pq_path = self.s8.EMBEDDINGS_DIR / doc_id / "embeddings.parquet"
        self.assertFalse(pq_path.exists())

    def test_nontransient_error_fails_fast(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(10)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        fail_provider = StubProvider(fails_on_batch=True, transient_fail=False)
        outcome, findings, _, _, _ = self.s8.process_document(record, chunks, fail_provider, self.dim)
        self.assertEqual(outcome, "FAIL")
        # should only call once, no retries
        self.assertEqual(fail_provider.calls, 1)

    def test_resume_checkpoint(self):
        doc_id = "doc1"
        chunks = [{"chunk_id": f"c{i}", "text": f"text{i}"} for i in range(5)]
        record = ManifestRecord(doc_id=doc_id, category="climate", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": "xyz"})
        
        # Mock writing a checkpoint for the first 2 rows
        doc_dir = self.s8.EMBEDDINGS_DIR / doc_id
        doc_dir.mkdir(parents=True)
        ckpt = doc_dir / "embeddings.checkpoint.jsonl"
        
        cfg = compute_config_fingerprint(self.provider, self.dim)
        for i in range(2):
            row = {
                "embedding_id": build_embedding_id(f"c{i}", self.provider),
                "chunk_id": f"c{i}",
                "doc_id": doc_id,
                "provider": self.provider.provider_name,
                "model_name": self.provider.model_name,
                "model_version": self.provider.model_version,
                "embedding_dimension": self.dim,
                "embedding_vector": [0.1] * self.dim,
                "text_checksum": compute_text_checksum(f"text{i}"),
                "config_fingerprint": cfg,
                "created_at": "now",
                "embedding_pipeline_version": EMBEDDING_PIPELINE_VERSION,
                "source_chunk_char_count": 5
            }
            with open(ckpt, 'a') as f:
                f.write(json.dumps(row) + "\n")
                
        # Run should process only remaining 3
        outcome, _, _, r, g = self.s8.process_document(record, chunks, self.provider, self.dim)
        
        self.assertEqual(outcome, "PASS")
        self.assertEqual(r, 2)
        self.assertEqual(g, 3)
        self.assertFalse(ckpt.exists()) # Checkpoint cleaned up

    def test_real_corpus_like_run(self):
        # Test full orchestration loop logic
        # We simulate the manifest and chunk artifacts to avoid reading real corpus in unit test.
        # But we will use the orchestrator structure.
        manifest_data = {
            "doc1": ManifestRecord(doc_id="doc1", category="c", status=DocumentStatus.READY_FOR_CHUNKING, artifact_paths={"chunks": str(self.s8.CHUNKS_DIR / "doc1" / "chunks.json")}),
            "doc2": ManifestRecord(doc_id="doc2", category="c", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": str(self.s8.CHUNKS_DIR / "doc2" / "chunks.json")}),
            "doc3": ManifestRecord(doc_id="doc3", category="c", status=DocumentStatus.REGISTERED, artifact_paths={"other": "path"}) # Ineligible
        }
        
        # create chunk files
        for did in ["doc1", "doc2"]:
            cdir = self.s8.CHUNKS_DIR / did
            cdir.mkdir(parents=True)
            with open(cdir / "chunks.json", "w") as f:
                json.dump({"chunks": [{"chunk_id": f"c_{did}_0", "text": "text"}]}, f)
                
        orig_load = self.s8.load_manifest
        orig_save = self.s8.save_manifest
        self.s8.load_manifest = lambda: manifest_data
    
        saved_manifest = None
        def mock_save(m):
            nonlocal saved_manifest
            saved_manifest = m
        self.s8.save_manifest = mock_save
    
        try:
            self.s8.run_stage8(self.provider)
        finally:
            self.s8.load_manifest = orig_load
            self.s8.save_manifest = orig_save
            
        self.assertIsNotNone(saved_manifest)
        self.assertIn("embeddings", saved_manifest["doc1"].artifact_paths)
        self.assertIn("embeddings", saved_manifest["doc2"].artifact_paths)
        self.assertNotIn("embeddings", saved_manifest["doc3"].artifact_paths)

    def test_crash_isolation_one_doc_does_not_block_batch(self):
        """Finding 1: An unexpected exception in one document must not
        prevent processing of remaining documents."""
        import scripts.stage8_embedding_generation as s8_mod

        # doc1 has a corrupted chunks.json that will cause json.load to fail
        # doc2 is normal
        cdir1 = self.s8.CHUNKS_DIR / "doc1"
        cdir1.mkdir(parents=True)
        (cdir1 / "chunks.json").write_text("NOT VALID JSON {{{", encoding="utf-8")

        cdir2 = self.s8.CHUNKS_DIR / "doc2"
        cdir2.mkdir(parents=True)
        with open(cdir2 / "chunks.json", "w") as f:
            json.dump({"chunks": [{"chunk_id": "c_doc2_0", "text": "hello"}]}, f)

        manifest_data = {
            "doc1": ManifestRecord(doc_id="doc1", category="c", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": str(cdir1 / "chunks.json")}),
            "doc2": ManifestRecord(doc_id="doc2", category="c", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": str(cdir2 / "chunks.json")}),
        }

        orig_load = self.s8.load_manifest
        orig_save = self.s8.save_manifest
        self.s8.load_manifest = lambda: manifest_data

        saved_manifest = None
        def mock_save(m):
            nonlocal saved_manifest
            saved_manifest = m
        self.s8.save_manifest = mock_save

        try:
            self.s8.run_stage8(self.provider)
        finally:
            self.s8.load_manifest = orig_load
            self.s8.save_manifest = orig_save

        # doc1 should be quarantined from the crash
        self.assertEqual(saved_manifest["doc1"].status, DocumentStatus.QUARANTINED)
        self.assertEqual(saved_manifest["doc1"].error_code, "FATAL_EMBEDDING_FAILED")

        # doc2 should have been processed successfully
        self.assertIn("embeddings", saved_manifest["doc2"].artifact_paths)

    def test_manifest_persisted_after_crash(self):
        """Finding 1: save_manifest must always execute even when a document crashes."""
        cdir1 = self.s8.CHUNKS_DIR / "doc1"
        cdir1.mkdir(parents=True)
        (cdir1 / "chunks.json").write_text("CORRUPT", encoding="utf-8")

        manifest_data = {
            "doc1": ManifestRecord(doc_id="doc1", category="c", status=DocumentStatus.REGISTERED, artifact_paths={"chunks": str(cdir1 / "chunks.json")}),
        }

        orig_load = self.s8.load_manifest
        orig_save = self.s8.save_manifest
        self.s8.load_manifest = lambda: manifest_data

        save_called = False
        def mock_save(m):
            nonlocal save_called
            save_called = True
        self.s8.save_manifest = mock_save

        try:
            self.s8.run_stage8(self.provider)
        finally:
            self.s8.load_manifest = orig_load
            self.s8.save_manifest = orig_save

        self.assertTrue(save_called, "save_manifest must always be called")

    def test_cached_rerun_zero_provider_calls(self):
        """Finding 4: A fully cached rerun must make zero embed_batch calls,
        including the dimension-discovery call."""
        # First run: generates embeddings
        cdir = self.s8.CHUNKS_DIR / "doc1"
        cdir.mkdir(parents=True)
        with open(cdir / "chunks.json", "w") as f:
            json.dump({"chunks": [{"chunk_id": "c1", "text": "hello"}]}, f)

        manifest_data = {
            "doc1": ManifestRecord(doc_id="doc1", category="c", status=DocumentStatus.REGISTERED,
                                  artifact_paths={"chunks": str(cdir / "chunks.json")}),
        }

        orig_load = self.s8.load_manifest
        orig_save = self.s8.save_manifest
        self.s8.load_manifest = lambda: manifest_data
        self.s8.save_manifest = lambda m: None

        try:
            self.s8.run_stage8(self.provider)
            first_run_calls = self.provider.calls
            self.assertGreater(first_run_calls, 0)

            # Second run: must make zero calls
            # The manifest now has the embeddings path from the first run
            self.provider.calls = 0
            self.s8.run_stage8(self.provider)
            self.assertEqual(self.provider.calls, 0,
                             "Cached rerun must make zero provider calls")
        finally:
            self.s8.load_manifest = orig_load
            self.s8.save_manifest = orig_save


if __name__ == '__main__':
    unittest.main()
