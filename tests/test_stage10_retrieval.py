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
    apply_metadata_filters,
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


# ---------------------------------------------------------------------------
# Metadata filters: exercised for real (no mocking of the filter logic)
# ---------------------------------------------------------------------------

def _cand(doc, chunk, score=0.5):
    return {"doc_id": doc, "chunk_id": chunk, "score": score}


_CHUNKS = {
    "dA": {"a1": {"chunk_id": "a1", "category": "climate", "doc_type": "proposal"},
           "a2": {"chunk_id": "a2", "category": "climate", "doc_type": "proposal"}},
    "dB": {"b1": {"chunk_id": "b1", "category": "health", "doc_type": "proposal"}},
    "dC": {"c1": {"chunk_id": "c1", "category": "health", "doc_type": "report"}},
}
_ALL = [_cand("dA", "a1"), _cand("dA", "a2"), _cand("dB", "b1"), _cand("dC", "c1")]


def _ids(cands):
    return sorted(c["chunk_id"] for c in cands)


def test_filter_category_keeps_only_matching_category():
    assert _ids(apply_metadata_filters(_ALL, {"category": "health"}, _CHUNKS)) == ["b1", "c1"]
    assert _ids(apply_metadata_filters(_ALL, {"category": "climate"}, _CHUNKS)) == ["a1", "a2"]


def test_filter_unknown_category_returns_nothing():
    assert apply_metadata_filters(_ALL, {"category": "water"}, _CHUNKS) == []


def test_filter_doc_type_and_doc_ids():
    assert _ids(apply_metadata_filters(_ALL, {"doc_type": "report"}, _CHUNKS)) == ["c1"]
    assert _ids(apply_metadata_filters(_ALL, {"doc_ids": ["dA", "dC"]}, _CHUNKS)) == ["a1", "a2", "c1"]


def test_filters_combine_with_and():
    got = apply_metadata_filters(_ALL, {"category": "health", "doc_type": "proposal"}, _CHUNKS)
    assert _ids(got) == ["b1"]
    assert apply_metadata_filters(_ALL, {"category": "health", "doc_ids": ["dA"]}, _CHUNKS) == []


def test_no_filters_keeps_everything_that_has_a_chunk_record():
    assert _ids(apply_metadata_filters(_ALL, {}, _CHUNKS)) == ["a1", "a2", "b1", "c1"]
    # a candidate whose chunk record is missing is dropped, never passed through
    assert _ids(apply_metadata_filters(_ALL + [_cand("dA", "ghost")], {}, _CHUNKS)) == ["a1", "a2", "b1", "c1"]


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_applies_category_filter_end_to_end(mock_search, mock_resolve, tmp_path):
    """retrieve() with a category filter must return only that category's chunks (real chunk files)."""
    manifest = {}
    for doc, cat, chunk_ids in (("dA", "climate", ["a1"]), ("dB", "health", ["b1"])):
        path = tmp_path / f"{doc}.json"
        path.write_text(json.dumps({"chunks": [
            {"chunk_id": c, "text": f"text {c}", "category": cat, "doc_type": "proposal"} for c in chunk_ids]}),
            encoding="utf-8")
        manifest[doc] = ManifestRecord(doc_id=doc, category=cat, status=DocumentStatus.READY_FOR_CHUNKING,
                                       artifact_paths={"vector_index": "x", "chunks": str(path)})
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = [
        {"index_fingerprint": "idx", "distance": 0.9, "metric": "cosine", "embedding_id": "e1", "chunk_id": "a1", "doc_id": "dA"},
        {"index_fingerprint": "idx", "distance": 0.8, "metric": "cosine", "embedding_id": "e2", "chunk_id": "b1", "doc_id": "dB"},
    ]
    provider = MagicMock()
    provider.embed_batch.return_value = [[1.0, 0.0]]

    unfiltered = retrieve({"query": "q", "index_fingerprints": ["idx"]}, manifest, lambda *a: provider, lambda *a: None)
    assert sorted(r["chunk_id"] for r in unfiltered["results"]) == ["a1", "b1"]

    filtered = retrieve({"query": "q", "index_fingerprints": ["idx"], "filters": {"category": "health"}},
                        manifest, lambda *a: provider, lambda *a: None)
    assert [r["chunk_id"] for r in filtered["results"]] == ["b1"]

