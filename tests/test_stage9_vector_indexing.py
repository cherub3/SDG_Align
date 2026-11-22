import pytest
import json
import os
import shutil
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage9_vector_indexing import (
    IndexAdapter, FAISSAdapter, compute_adapter_internal_id, compute_index_fingerprint,
    normalize_vectors, load_eligible_documents, discover_config_fingerprints,
    load_rows_for_fingerprint, revalidate_rows, IndexWorkload, determine_index_workload,
    apply_workload_to_staging, validate_index, persist_index_atomic,
    write_index_validation_report, update_manifest_for_fingerprint, run_stage9,
    INDEX_DIR, STAGING_DIR_SUFFIX, INDEX_PIPELINE_VERSION, _rename_with_retry
)
from src.ingestion_types import ManifestRecord, DocumentStatus

class StubAdapter(IndexAdapter):
    def __init__(self, metric="cosine"):
        self._metric = metric
        self.internal_map = {}
        self.vectors = {}
        self.built = False
        self._dim = 0
        
    @property
    def backend_name(self): return "stub"
    @property
    def backend_version(self): return "1.0.0"
    @property
    def backend_detail(self): return "StubBackend"
    @property
    def metric(self): return self._metric
    @property
    def metric_implementation(self): return "stub_metric"
    @property
    def normalization(self): return "none"
    
    @property
    def dimension(self): return self._dim
    
    def reconstruct(self, internal_id: int):
        return self.vectors[internal_id]
    
    def build(self, dim): 
        self.built = True
        self._dim = dim
        
    def add(self, ids, vectors):
        for i, vec in zip(ids, vectors):
            self.internal_map[int(i)] = vec
            self.vectors[int(i)] = vec
            
    def remove(self, ids):
        for i in ids:
            if int(i) in self.internal_map:
                del self.internal_map[int(i)]
                del self.vectors[int(i)]
                
    def search(self, query, k):
        n = len(query)
        D = np.array([[1.0]] * n)
        I = np.zeros((n, 1), dtype=np.int64)
        for i, q in enumerate(query):
            found = False
            for k_id, v in self.vectors.items():
                if np.allclose(q, v):
                    I[i][0] = k_id
                    found = True
                    break
            if not found:
                I[i][0] = list(self.vectors.keys())[0] if self.vectors else -1
        return D, I
        
    def serialize(self, path):
        with open(path, 'w') as f:
            f.write("stub")
            
    def deserialize(self, path):
        self.built = True
        
    @property
    def ntotal(self): return len(self.internal_map)

# --- Tests ---

def test_index_adapter_contract():
    stub = StubAdapter()
    stub.build(384)
    stub.add(np.array([1, 2]), np.array([[0.1]*384, [0.2]*384]))
    assert stub.ntotal == 2
    stub.remove(np.array([1]))
    assert stub.ntotal == 1
    assert 2 in stub.internal_map
    assert 1 not in stub.internal_map

def test_index_fingerprint_determinism():
    f1 = compute_index_fingerprint("config1", "faiss", "cosine")
    f2 = compute_index_fingerprint("config1", "faiss", "cosine")
    f3 = compute_index_fingerprint("config2", "faiss", "cosine")
    f4 = compute_index_fingerprint("config1", "hnsw", "cosine")
    f5 = compute_index_fingerprint("config1", "faiss", "l2")
    
    assert f1 == f2
    assert f1 != f3
    assert f1 != f4
    assert f1 != f5

def test_adapter_internal_id_correctness():
    id1 = compute_adapter_internal_id("doc_1__prov__mod__v1")
    id2 = compute_adapter_internal_id("doc_1__prov__mod__v1")
    id3 = compute_adapter_internal_id("doc_2__prov__mod__v1")
    
    assert id1 == id2
    assert id1 != id3
    assert isinstance(id1, int)
    assert -(2**63) <= id1 <= (2**63 - 1)

def test_incremental_workload_matrix():
    valid_rows = [
        {"embedding_id": "e1", "text_checksum": "c1"},
        {"embedding_id": "e2", "text_checksum": "c2_new"},
        {"embedding_id": "e3", "text_checksum": "c3"}
    ]
    
    existing_id_map = [
        {"embedding_id": "e1", "text_checksum": "c1", "adapter_internal_id": 1},
        {"embedding_id": "e2", "text_checksum": "c2_old", "adapter_internal_id": 2},
        {"embedding_id": "e4", "text_checksum": "c4", "adapter_internal_id": 4}
    ]
    
    wl = determine_index_workload(valid_rows, existing_id_map)
    assert len(wl.reused) == 1
    assert wl.reused[0]["embedding_id"] == "e1"
    
    assert len(wl.reindexed) == 1
    assert wl.reindexed[0]["embedding_id"] == "e2"
    
    assert len(wl.added) == 1
    assert wl.added[0]["embedding_id"] == "e3"
    
    assert set(wl.removed_ids) == {2, 4}

def test_validate_index_dimension_mismatch():
    stub = StubAdapter()
    stub.build(384)
    # Simulate a backend mismatch by modifying the adapter's reported dimension
    stub._dim = 256
    
    valid_rows = [{"embedding_dimension": 384, "embedding_id": "e1", "embedding_vector": [0.1]*384}]
    findings = validate_index(stub, [], {}, valid_rows, stub.backend_version)
    
    criticals = [f for f in findings if f["code"] == "INDEX_DIMENSION_CONSISTENT"]
    assert len(criticals) == 1
    assert criticals[0]["severity"] == "FAIL"

def test_atomicity(tmp_path):
    global INDEX_DIR
    original_index_dir = INDEX_DIR
    import scripts.stage9_vector_indexing
    scripts.stage9_vector_indexing.INDEX_DIR = tmp_path
    
    try:
        stub = StubAdapter()
        stub.build(384)
        metadata = {"metric": "cosine"}
        id_map = [{"adapter_internal_id": 1, "embedding_id": "e1", "chunk_id": "c1", "doc_id": "d1", "text_checksum": "ts", "index_fingerprint": "fp", "indexed_at": "now"}]
        
        persist_index_atomic("fp1", stub, id_map, metadata)
        live = tmp_path / "fp1"
        assert live.exists()
        assert (live / "index.bin").exists()
        assert (live / "id_map.parquet").exists()
        assert (live / "index_metadata.json").exists()
        
        persist_index_atomic("fp1", stub, id_map, metadata)
        assert live.exists()
        
    finally:
        scripts.stage9_vector_indexing.INDEX_DIR = original_index_dir

def test_manifest_updates():
    records = {
        "d1": ManifestRecord(doc_id="d1", category="test", status=DocumentStatus.REGISTERED, artifact_paths={}),
        "d2": ManifestRecord(doc_id="d2", category="test", status=DocumentStatus.REGISTERED, artifact_paths={})
    }
    
    update_manifest_for_fingerprint(records, "fp1", {"d1"}, {"d2"})
    
    assert "vector_index" in records["d1"].artifact_paths
    assert records["d1"].status == DocumentStatus.REGISTERED
    
    assert "vector_index" not in records["d2"].artifact_paths
    assert records["d2"].status == DocumentStatus.QUARANTINED
    assert records["d2"].error_code == "FATAL_INDEXING_FAILED"

@patch('scripts.stage9_vector_indexing.load_manifest')
@patch('scripts.stage9_vector_indexing.save_manifest')
def test_real_corpus_run_no_op(save_mock, load_mock, tmp_path):
    records = {"d1": ManifestRecord(doc_id="d1", category="test", status=DocumentStatus.REGISTERED, artifact_paths={"embeddings": str(tmp_path / "d1_emb.parquet")})}
    load_mock.return_value = records
    
    emb_path = tmp_path / "d1_emb.parquet"
    table = pa.Table.from_pylist([{
        "embedding_id": "e1", "chunk_id": "c1", "doc_id": "d1",
        "provider": "prov", "model_name": "mod", "model_version": "v1",
        "embedding_dimension": 384, "embedding_vector": [0.1]*384,
        "text_checksum": "ts", "config_fingerprint": "cfp",
        "created_at": "now", "embedding_pipeline_version": "1.0",
        "source_chunk_char_count": 100
    }])
    pq.write_table(table, emb_path)
    
    global INDEX_DIR
    original_index_dir = INDEX_DIR
    import scripts.stage9_vector_indexing
    scripts.stage9_vector_indexing.INDEX_DIR = tmp_path
    
    try:
        run_stage9(StubAdapter, "cosine")
        assert save_mock.called
        
        dirs = list(tmp_path.glob("*"))
        fp_dir = [d for d in dirs if not d.name.endswith(".parquet")]
        assert len(fp_dir) == 1
        live_dir = fp_dir[0]
        assert (live_dir / "index_metadata.json").exists()
        assert (live_dir / "index_validation_report.json").exists()
        
        with open(live_dir / "index_validation_report.json") as f:
            rep = json.load(f)
            assert rep["outcome"] == "PASS" or rep["outcome"] == "WARNING"
            assert rep["stats"]["vector_count"] == 1
            
        # Rerun is no-op for vectors, meaning it skips building completely
        # but it DOES write a fresh validation report with reused_count.
        import time
        time.sleep(1.1) # ensure timestamp changes since ISO is 1-second resolution
        save_mock.reset_mock()
        run_stage9(StubAdapter, "cosine")
        
        with open(live_dir / "index_validation_report.json") as f:
            rep2 = json.load(f)
            assert rep2["stats"]["reused_count"] == 1
            assert rep2["stats"]["added_count"] == 0
            assert rep2["validated_at"] > rep["validated_at"]
            
    finally:
        scripts.stage9_vector_indexing.INDEX_DIR = original_index_dir


def _flaky_rename(real_rename, fail_times):
    state = {"calls": 0}

    def fake(src, dst):
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise PermissionError(5, "Access is denied")
        return real_rename(src, dst)

    return fake, state


def test_rename_with_retry_recovers_from_transient_permission_error(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    src.mkdir()
    fake, state = _flaky_rename(os.rename, fail_times=2)
    with patch("scripts.stage9_vector_indexing.os.rename", fake),          patch("scripts.stage9_vector_indexing.time.sleep"):
        _rename_with_retry(src, dst)
    assert dst.exists() and not src.exists()
    assert state["calls"] == 3  # two failures, then success


def test_rename_with_retry_gives_up_and_reraises(tmp_path):
    src, dst = tmp_path / "a", tmp_path / "b"
    src.mkdir()
    fake, state = _flaky_rename(os.rename, fail_times=99)
    with patch("scripts.stage9_vector_indexing.os.rename", fake),          patch("scripts.stage9_vector_indexing.time.sleep"):
        with pytest.raises(PermissionError):
            _rename_with_retry(src, dst, attempts=4)
    assert state["calls"] == 4
    assert src.exists() and not dst.exists()


def test_rename_with_retry_does_not_swallow_other_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        _rename_with_retry(tmp_path / "missing", tmp_path / "dst")

