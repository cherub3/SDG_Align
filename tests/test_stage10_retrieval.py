import pytest
import numpy as np
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.stage10_retrieval import (
    preprocess_query,
    normalize_index_fingerprints,
    normalize_score,
    select_top_k,
    validate_retrieval_result,
    RetrievalInternalError,
    retrieve,
    RETRIEVAL_PIPELINE_VERSION,
    DEFAULT_TOP_K
)
from src.ingestion_types import ManifestRecord, DocumentStatus

def test_preprocess_query():
    assert preprocess_query("  hello world  ") == "hello world"
    assert preprocess_query(" café") == "café"
    assert preprocess_query("") == ""

def test_normalize_index_fingerprints():
    # Deduplicates and preserves order
    assert normalize_index_fingerprints(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
    with pytest.raises(ValueError, match="INDEX_FINGERPRINTS_EMPTY"):
        normalize_index_fingerprints([])

def test_normalize_score():
    assert normalize_score(0.5, "cosine") == 0.5
    assert normalize_score(0.0, "l2") == 1.0
    assert normalize_score(1.0, "l2") == 0.5

def test_select_top_k():
    candidates = [
        {"chunk_id": "c1", "score": 0.5, "text": "foo"},
        {"chunk_id": "c1", "score": 0.8, "text": "foo better"}, # Should win over c1 above
        {"chunk_id": "c2", "score": 0.5, "text": "bar"},
        {"chunk_id": "c3", "score": 0.9, "text": "baz"},
    ]
    # Highest score wins for dedup -> c1(0.8), c2(0.5), c3(0.9)
    # Sort score desc -> c3(0.9), c1(0.8), c2(0.5)
    result = select_top_k(candidates, 2)
    assert len(result) == 2
    assert result[0]["chunk_id"] == "c3"
    assert result[0]["rank"] == 0
    assert result[1]["chunk_id"] == "c1"
    assert result[1]["rank"] == 1
    
def test_select_top_k_tie_break():
    candidates = [
        {"chunk_id": "b", "score": 0.5},
        {"chunk_id": "a", "score": 0.5},
    ]
    # Tie break by chunk_id asc
    result = select_top_k(candidates, 2)
    assert result[0]["chunk_id"] == "a"
    assert result[1]["chunk_id"] == "b"

def test_validate_retrieval_result_internal_error():
    # duplicate chunk
    with pytest.raises(RetrievalInternalError):
        validate_retrieval_result({"results": [{"chunk_id": "1", "rank": 0, "score": 1.0, "index_fingerprint": "f1"}, {"chunk_id": "1", "rank": 1, "score": 0.5, "index_fingerprint": "f1"}], "searched_index_fingerprints": ["f1"]})
    
    # rank not contiguous
    with pytest.raises(RetrievalInternalError):
        validate_retrieval_result({"results": [{"chunk_id": "1", "rank": 0, "score": 1.0, "index_fingerprint": "f1"}, {"chunk_id": "2", "rank": 2, "score": 0.5, "index_fingerprint": "f1"}], "searched_index_fingerprints": ["f1"]})
        
    # score non-increasing
    with pytest.raises(RetrievalInternalError):
        validate_retrieval_result({"results": [{"chunk_id": "1", "rank": 0, "score": 0.5, "index_fingerprint": "f1"}, {"chunk_id": "2", "rank": 1, "score": 1.0, "index_fingerprint": "f1"}], "searched_index_fingerprints": ["f1"]})
        
    # index not searched
    with pytest.raises(RetrievalInternalError):
        validate_retrieval_result({"results": [{"chunk_id": "1", "rank": 0, "score": 0.5, "index_fingerprint": "f2"}], "searched_index_fingerprints": ["f1"]})

def test_retrieve_query_empty():
    request = {"query": "   ", "index_fingerprints": ["idx1"]}
    res = retrieve(request, {}, lambda *args: None, lambda *args: None)
    assert res["status"] == "FAIL"
    assert any(f["code"] == "QUERY_EMPTY" for f in res["findings"])

def test_retrieve_index_empty():
    request = {"query": "hello", "index_fingerprints": []}
    res = retrieve(request, {}, lambda *args: None, lambda *args: None)
    assert res["status"] == "FAIL"
    assert any(f["code"] == "INDEX_FINGERPRINTS_EMPTY" for f in res["findings"])

@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
def test_retrieve_query_embedding_failed(mock_resolve):
    mock_resolve.return_value = [
        MagicMock(fingerprint="idx1", metadata={"provider": "test", "embedding_dimension": 4})
    ]
    def failing_provider(*args):
        raise ValueError("API down")
        
    request = {"query": "hello", "index_fingerprints": ["idx1"]}
    res = retrieve(request, {}, failing_provider, lambda *args: None)
    
    assert res["status"] == "FAIL"
    assert any(f["code"] == "QUERY_EMBEDDING_FAILED" for f in res["findings"])

@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
def test_retrieve_embedding_dimension_mismatch(mock_resolve):
    mock_resolve.return_value = [
        MagicMock(fingerprint="idx1", metadata={"provider": "test", "embedding_dimension": 8})
    ]
    mock_provider = MagicMock()
    mock_provider.embed_batch.return_value = [np.array([1, 2, 3, 4])] # dim 4
    
    request = {"query": "hello", "index_fingerprints": ["idx1"]}
    res = retrieve(request, {}, lambda *args: mock_provider, lambda *args: None)
    
    assert res["status"] == "FAIL"
    assert any(f["code"] == "EMBEDDING_DIMENSION_MISMATCH" for f in res["findings"])

@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_zero_results(mock_search, mock_resolve):
    mock_resolve.return_value = [
        MagicMock(fingerprint="idx1", metadata={"provider": "test", "embedding_dimension": 4})
    ]
    mock_provider = MagicMock()
    mock_provider.embed_batch.return_value = [np.array([1, 2, 3, 4])]
    
    mock_search.return_value = []
    
    request = {"query": "hello", "index_fingerprints": ["idx1"]}
    res = retrieve(request, {}, lambda *args: mock_provider, lambda *args: None)
    
    assert res["status"] == "PASS"
    assert res["zero_results"] is True
    assert any(f["code"] == "ZERO_RESULTS" for f in res["findings"])
    assert res["results"] == []

from scripts.stage10_retrieval import IndexHandle

@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_partial_status(mock_search, mock_resolve):
    # One successful, one FAIL
    mock_resolve.return_value = [
        IndexHandle("idx_success", {"provider": "test", "embedding_dimension": 4}, Path("path1")),
        IndexHandle("idx_fail", {}, Path("path2"), {"severity": "FAIL", "code": "INDEX_ARTIFACT_READABLE", "message": "fail"})
    ]
    
    mock_provider = MagicMock()
    mock_provider.embed_batch.return_value = [np.array([1, 2, 3, 4])]
    
    mock_search.return_value = []
    
    request = {"query": "hello", "index_fingerprints": ["idx_success", "idx_fail"]}
    res = retrieve(request, {}, lambda *args: mock_provider, lambda *args: None)
    
    assert res["status"] == "PARTIAL"
    assert res["searched_index_fingerprints"] == ["idx_success"]
    assert res["requested_index_fingerprints"] == ["idx_success", "idx_fail"]
    assert any(f["code"] == "INDEX_ARTIFACT_READABLE" and f["severity"] == "FAIL" for f in res["findings"])
