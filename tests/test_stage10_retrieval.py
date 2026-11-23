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
    normalize_query_vector,
    EmbeddingModelMismatchError,
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


# ---------------------------------------------------------------------------
# Query vector normalisation
# ---------------------------------------------------------------------------

def test_normalize_query_vector_returns_unit_float32_and_keeps_direction():
    out = normalize_query_vector([3, 4])
    assert out.dtype == np.float32
    assert out.shape == (2,)
    assert float(np.linalg.norm(out)) == pytest.approx(1.0, abs=1e-6)
    assert out.tolist() == pytest.approx([0.6, 0.8], abs=1e-6)


def test_normalize_query_vector_leaves_unit_vectors_unchanged():
    unit = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert normalize_query_vector(unit).tolist() == [0.0, 1.0, 0.0]


@pytest.mark.parametrize("bad", [[0.0, 0.0, 0.0], [], [float("nan"), 1.0], [float("inf"), 1.0], [[1.0, 2.0], [3.0, 4.0]]])
def test_normalize_query_vector_rejects_unusable_vectors(bad):
    with pytest.raises(ValueError):
        normalize_query_vector(bad)


def _manifest_and_chunks(tmp_path):
    path = tmp_path / "dA.json"
    path.write_text(json.dumps({"chunks": [{"chunk_id": "a1", "text": "t", "category": "c", "doc_type": "d"}]}), encoding="utf-8")
    return {"dA": ManifestRecord(doc_id="dA", category="c", status=DocumentStatus.READY_FOR_CHUNKING,
                                 artifact_paths={"vector_index": "x", "chunks": str(path)})}


_HIT = [{"index_fingerprint": "idx", "distance": 0.9, "metric": "cosine", "embedding_id": "e1", "chunk_id": "a1", "doc_id": "dA"}]


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_normalises_the_query_for_an_l2_index(mock_search, mock_resolve, tmp_path):
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2, "normalization": "l2"}, Path("p"))]
    mock_search.return_value = _HIT
    provider = MagicMock()
    provider.embed_batch.return_value = [[3.0, 4.0]]  # NOT unit length

    retrieve({"query": "q", "index_fingerprints": ["idx"]}, _manifest_and_chunks(tmp_path), lambda *a: provider, lambda *a: None)

    searched_with = mock_search.call_args.args[1]
    assert float(np.linalg.norm(searched_with)) == pytest.approx(1.0, abs=1e-6)
    assert searched_with.tolist() == pytest.approx([0.6, 0.8], abs=1e-6)


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_does_not_rescale_the_query_for_a_non_normalised_index(mock_search, mock_resolve, tmp_path):
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2, "normalization": "none"}, Path("p"))]
    mock_search.return_value = _HIT
    provider = MagicMock()
    provider.embed_batch.return_value = [[3.0, 4.0]]

    retrieve({"query": "q", "index_fingerprints": ["idx"]}, _manifest_and_chunks(tmp_path), lambda *a: provider, lambda *a: None)

    assert mock_search.call_args.args[1].tolist() == [3.0, 4.0]


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_zero_query_vector_is_an_embedding_failure_not_a_nan_search(mock_search, mock_resolve):
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2, "normalization": "l2"}, Path("p"))]
    provider = MagicMock()
    provider.embed_batch.return_value = [[0.0, 0.0]]

    res = retrieve({"query": "q", "index_fingerprints": ["idx"]}, {}, lambda *a: provider, lambda *a: None)

    assert res["status"] == "FAIL"
    assert any(f["code"] == "QUERY_EMBEDDING_FAILED" for f in res["findings"])
    mock_search.assert_not_called()


# ---------------------------------------------------------------------------
# Refuse to search an index built with a different embedding model
# ---------------------------------------------------------------------------

def _mismatch_factory(provider, model, version):
    raise EmbeddingModelMismatchError(f"index built with {provider}/{model}/{version}")


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_refuses_an_index_from_a_different_embedding_model(mock_search, mock_resolve):
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "gemini", "model_name": "m", "model_version": "1",
                                                     "embedding_dimension": 2, "normalization": "l2"}, Path("p"))]
    res = retrieve({"query": "q", "index_fingerprints": ["idx"]}, {}, _mismatch_factory, lambda *a: None)

    assert res["status"] == "FAIL"
    assert res["results"] == []
    assert res["searched_index_fingerprints"] == []
    finding = next(f for f in res["findings"] if f["code"] == "INDEX_EMBEDDING_MODEL_MISMATCH")
    assert finding["severity"] == "FAIL"
    assert finding["index_fingerprint"] == "idx"
    mock_search.assert_not_called()  # the index file is never even opened


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_searches_the_matching_index_and_flags_the_mismatched_one(mock_search, mock_resolve, tmp_path):
    good = IndexHandle("idx", {"provider": "hf", "model_name": "bge", "model_version": "v1.5",
                               "embedding_dimension": 2, "normalization": "l2"}, Path("p"))
    stale = IndexHandle("old", {"provider": "gemini", "model_name": "emb", "model_version": "1",
                                "embedding_dimension": 2, "normalization": "l2"}, Path("q"))
    mock_resolve.return_value = [good, stale]
    mock_search.return_value = _HIT
    provider = MagicMock()
    provider.embed_batch.return_value = [[1.0, 0.0]]

    def factory(prov, mod, ver):
        if (prov, mod, ver) != ("hf", "bge", "v1.5"):
            raise EmbeddingModelMismatchError("different model")
        return provider

    res = retrieve({"query": "q", "index_fingerprints": ["idx", "old"]}, _manifest_and_chunks(tmp_path), factory, lambda *a: None)

    assert res["status"] == "PARTIAL"
    assert res["searched_index_fingerprints"] == ["idx"]
    assert [f["index_fingerprint"] for f in res["findings"] if f["code"] == "INDEX_EMBEDDING_MODEL_MISMATCH"] == ["old"]
    assert [r["chunk_id"] for r in res["results"]] == ["a1"]
    assert mock_search.call_count == 1



@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_hybrid_promotes_the_lexical_match_and_keeps_the_cosine(mock_search, mock_resolve, tmp_path):
    """dense alone ranks a1 first; BM25 finds the rare words only in a2, so hybrid puts a2 first. Dense mode is untouched."""
    path = tmp_path / "dA.json"
    path.write_text(json.dumps({"chunks": [
        {"chunk_id": "a1", "text": "general background text", "category": "c", "doc_type": "d"},
        {"chunk_id": "a2", "text": "zebra quagga okapi", "category": "c", "doc_type": "d"}]}), encoding="utf-8")
    manifest = {"dA": ManifestRecord(doc_id="dA", category="c", status=DocumentStatus.READY_FOR_CHUNKING,
                                     artifact_paths={"vector_index": "x", "chunks": str(path)})}
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = [
        {"index_fingerprint": "idx", "distance": 0.9, "metric": "cosine", "embedding_id": "e1", "chunk_id": "a1", "doc_id": "dA"},
        {"index_fingerprint": "idx", "distance": 0.2, "metric": "cosine", "embedding_id": "e2", "chunk_id": "a2", "doc_id": "dA"}]
    provider = MagicMock()
    provider.embed_batch.return_value = [[1.0, 0.0]]

    dense = retrieve({"query": "zebra quagga", "index_fingerprints": ["idx"]}, manifest, lambda *a: provider, lambda *a: None)
    assert [r["chunk_id"] for r in dense["results"]] == ["a1", "a2"]
    assert "dense_score" not in dense["results"][0]

    hyb = retrieve({"query": "zebra quagga", "index_fingerprints": ["idx"], "hybrid": {"rrf_k": 1, "w_bm25": 2.0}},
                   manifest, lambda *a: provider, lambda *a: None)
    assert [r["chunk_id"] for r in hyb["results"]] == ["a2", "a1"]
    assert hyb["results"][0]["dense_score"] == pytest.approx(0.2) and hyb["results"][0]["bm25_score"] > 0
    assert mock_search.call_args.args[2] >= 10 ** 6          # hybrid searches the whole index


def test_chunk_and_id_map_caches_follow_the_file(tmp_path):
    """The per-file caches must serve a repeat read from memory but notice when the file changes."""
    import os
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    from scripts import stage10_retrieval as s10

    cp = tmp_path / "c.json"
    cp.write_text(json.dumps({"chunks": [{"chunk_id": "a"}]}), encoding="utf-8")
    assert s10._load_chunk_list(cp) == [{"chunk_id": "a"}]
    assert s10._load_chunk_list(cp) is s10._load_chunk_list(cp)
    cp.write_text(json.dumps([{"chunk_id": "a"}, {"chunk_id": "b"}]), encoding="utf-8")   # bare list accepted, bigger file
    assert len(s10._load_chunk_list(cp)) == 2

    ip = tmp_path / "id_map.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame({"adapter_internal_id": [0, 0, 1], "embedding_id": ["e0", "dup", "e1"],
                                                      "chunk_id": ["c0", "cdup", "c1"], "doc_id": ["d", "d", "d"]})), ip)
    m = s10._load_id_map(ip)
    assert m[0] == ("e0", "c0", "d") and m[1] == ("e1", "c1", "d")      # first row wins on a duplicate id


# ---------------- fix 7: the deserialised FAISS index is cached in memory and reloaded when the file changes ----------------

class _CountingAdapter:
    """Stands in for FAISSAdapter: counts how often the index file is deserialised."""
    loads = 0

    def __init__(self, metric):
        self.metric = metric

    def deserialize(self, path):
        type(self).loads += 1


def _cache_reset(monkeypatch):
    import scripts.stage10_retrieval as s10
    monkeypatch.setattr(s10, "_INDEX_CACHE", {})
    monkeypatch.setattr(s10, "INDEX_CACHE_ENABLED", True)
    _CountingAdapter.loads = 0
    return s10


def test_index_file_is_deserialised_once_not_per_query(tmp_path, monkeypatch):
    s10 = _cache_reset(monkeypatch)
    f = tmp_path / "index.bin"
    f.write_bytes(b"abc")
    got = [s10._loaded_index(f, "cosine", _CountingAdapter) for _ in range(5)]
    assert _CountingAdapter.loads == 1 and all(g is got[0] for g in got)


def test_index_is_reloaded_when_the_file_changes(tmp_path, monkeypatch):
    s10 = _cache_reset(monkeypatch)
    f = tmp_path / "index.bin"
    f.write_bytes(b"abc")
    first = s10._loaded_index(f, "cosine", _CountingAdapter)
    f.write_bytes(b"abcdef")                              # new size (and mtime) -> new key
    second = s10._loaded_index(f, "cosine", _CountingAdapter)
    assert _CountingAdapter.loads == 2 and second is not first
    assert len(s10._INDEX_CACHE) == 1                     # the stale version was dropped, not kept alongside


def test_a_changed_mtime_alone_reloads(tmp_path, monkeypatch):
    import os
    s10 = _cache_reset(monkeypatch)
    f = tmp_path / "index.bin"
    f.write_bytes(b"abc")
    s10._loaded_index(f, "cosine", _CountingAdapter)
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    s10._loaded_index(f, "cosine", _CountingAdapter)
    assert _CountingAdapter.loads == 2


def test_different_metrics_are_cached_separately(tmp_path, monkeypatch):
    s10 = _cache_reset(monkeypatch)
    f = tmp_path / "index.bin"
    f.write_bytes(b"abc")
    a = s10._loaded_index(f, "cosine", _CountingAdapter)
    b = s10._loaded_index(f, "l2", _CountingAdapter)
    assert a is not b and _CountingAdapter.loads == 2


def test_disabled_cache_and_unreadable_path_behave_like_before(tmp_path, monkeypatch):
    s10 = _cache_reset(monkeypatch)
    f = tmp_path / "index.bin"
    f.write_bytes(b"abc")
    monkeypatch.setattr(s10, "INDEX_CACHE_ENABLED", False)
    s10._loaded_index(f, "cosine", _CountingAdapter)
    s10._loaded_index(f, "cosine", _CountingAdapter)
    assert _CountingAdapter.loads == 2 and not s10._INDEX_CACHE
    monkeypatch.setattr(s10, "INDEX_CACHE_ENABLED", True)
    s10._loaded_index(tmp_path / "absent.bin", "cosine", _CountingAdapter)       # stat fails -> uncached, still deserialised
    assert _CountingAdapter.loads == 3 and not s10._INDEX_CACHE


def test_cache_is_bounded(tmp_path, monkeypatch):
    s10 = _cache_reset(monkeypatch)
    monkeypatch.setattr(s10, "MAX_CACHED_INDEXES", 2)
    for i in range(5):
        f = tmp_path / f"i{i}.bin"
        f.write_bytes(b"x")
        s10._loaded_index(f, "cosine", _CountingAdapter)
    assert len(s10._INDEX_CACHE) <= 2


def test_real_faiss_results_are_identical_with_and_without_the_cache(tmp_path, monkeypatch):
    from scripts.stage9_vector_indexing import FAISSAdapter
    s10 = _cache_reset(monkeypatch)
    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(40, 8)).astype("float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    ad = FAISSAdapter("cosine")
    ad.build(8)
    ad.add(np.arange(40, dtype="int64"), vecs)
    f = tmp_path / "index.bin"
    ad.serialize(f)
    q = rng.normal(size=(1, 8)).astype("float32")
    q /= np.linalg.norm(q)
    uncached = FAISSAdapter("cosine")
    uncached.deserialize(f)
    d0, i0 = uncached.search(q, 10)
    cached = s10._loaded_index(f, "cosine", FAISSAdapter)
    for _ in range(3):
        d1, i1 = s10._loaded_index(f, "cosine", FAISSAdapter).search(q, 10)
        assert (i0 == i1).all() and np.array_equal(d0, d1)
    assert s10._loaded_index(f, "cosine", FAISSAdapter) is cached


def test_the_index_cache_is_on_by_default_in_the_shipped_code():
    import scripts.stage10_retrieval as s10
    assert s10.INDEX_CACHE_ENABLED is True and s10.MAX_CACHED_INDEXES >= 1
