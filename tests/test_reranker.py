"""Cross-encoder reranker seam, step 3c. No model download: the real model is replaced by a mock or a fake loader."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import reranker as rr
from scripts.stage10_retrieval import retrieve, IndexHandle, RetrievalInternalError
from scripts.stage0_register import ManifestRecord, DocumentStatus


def _res(cid, score, text=None):
    return {"chunk_id": cid, "doc_id": "dA", "score": score, "rank": 0, "text": text or cid, "index_fingerprint": "idx"}


def _overlap(q, p):          # toy relevance: number of shared words
    return len(set(q.split()) & set(p.split()))


def test_committed_config_pins_a_revision_and_names_the_license():
    cfg = rr.load_config()
    assert len(cfg["revision"]) == 40 and cfg["license"] == "apache-2.0"
    assert cfg["model_id"] == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_config_rejects_a_floating_revision(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"model_id": "m", "revision": "main"}), encoding="utf-8")
    with pytest.raises(ValueError):
        rr.load_config(p)


def test_cross_encoder_adapter_is_lazy_and_scores_pairs_in_order():
    fake = MagicMock()
    fake.predict.return_value = [0.5, -2.0]
    loads = []
    ad = rr.CrossEncoderReranker("m", "a" * 40, 128, model_loader=lambda: loads.append(1) or fake)
    assert loads == []                                          # nothing loaded at construction
    assert ad.score("q", ["x", "y"]) == [0.5, -2.0]
    assert ad.score("q", ["x", "y"]) == [0.5, -2.0] and loads == [1]    # loaded once
    assert fake.predict.call_args.args[0] == [("q", "x"), ("q", "y")]
    assert ad.score("q", []) == []


def test_cross_encoder_adapter_refuses_an_unpinned_revision_and_bad_batch():
    with pytest.raises(ValueError):
        rr.CrossEncoderReranker("m", "main", 128, model_loader=lambda: None)
    with pytest.raises(ValueError):
        rr.CrossEncoderReranker("m", "a" * 40, 128, batch_size=0, model_loader=lambda: None)


def test_rerank_reorders_by_reranker_score_and_keeps_the_fused_score():
    pool = [_res("a", 0.9, "nothing"), _res("b", 0.8, "jaguar corridor"), _res("c", 0.7, "jaguar")]
    out = rr.rerank_results(pool, "jaguar corridor", rr.MockReranker(_overlap), lambda r: r["text"], n=3, top_k=3)
    got = out["results"]
    assert [r["chunk_id"] for r in got] == ["b", "c", "a"]
    assert [r["rank"] for r in got] == [0, 1, 2]
    assert got[0]["fused_score"] == 0.8 and got[0]["rerank_score"] == 2 and got[0]["score"] == 2
    assert all(got[i]["score"] >= got[i + 1]["score"] for i in range(2))     # validator needs score-descending
    assert pool[0]["score"] == 0.9 and "rerank_score" not in pool[0]          # input untouched


def test_rerank_only_scores_the_first_n_and_returns_at_most_top_k():
    pool = [_res(c, 1 - i / 10, c) for i, c in enumerate("abcdef")]
    ad = rr.MockReranker(lambda q, p: -ord(p))                                  # prefers earlier letters
    out = rr.rerank_results(pool, "q", ad, lambda r: r["text"], n=4, top_k=2)
    assert ad.passages_scored == 4 and out["n_scored"] == 4
    assert [r["chunk_id"] for r in out["results"]] == ["a", "b"]
    assert out["ms"] >= 0


def test_rerank_ties_break_on_chunk_id_and_n_must_be_positive():
    pool = [_res("b", 0.5), _res("a", 0.4)]
    out = rr.rerank_results(pool, "q", rr.MockReranker(lambda q, p: 1.0), lambda r: r["text"], n=2, top_k=2)
    assert [r["chunk_id"] for r in out["results"]] == ["a", "b"]
    with pytest.raises(ValueError):
        rr.rerank_results(pool, "q", rr.MockReranker(lambda q, p: 1.0), lambda r: r["text"], n=0, top_k=2)


def test_rerank_rejects_a_reranker_that_returns_the_wrong_number_of_scores():
    bad = MagicMock()
    bad.score.return_value = [1.0]
    with pytest.raises(ValueError):
        rr.rerank_results([_res("a", 1), _res("b", 0.5)], "q", bad, lambda r: r["text"], n=2, top_k=2)


def _setup(tmp_path):
    path = tmp_path / "dA.json"
    path.write_text(json.dumps({"chunks": [
        {"chunk_id": "a1", "text": "general background", "category": "c", "doc_type": "d"},
        {"chunk_id": "a2", "text": "jaguar corridor protected", "category": "c", "doc_type": "d"},
        {"chunk_id": "a3", "text": "budget table", "category": "c", "doc_type": "d"}]}), encoding="utf-8")
    manifest = {"dA": ManifestRecord(doc_id="dA", category="c", status=DocumentStatus.READY_FOR_CHUNKING,
                                     artifact_paths={"vector_index": "x", "chunks": str(path)})}
    hits = [{"index_fingerprint": "idx", "distance": d, "metric": "cosine", "embedding_id": "e" + c, "chunk_id": c, "doc_id": "dA"}
            for c, d in (("a1", 0.9), ("a3", 0.8), ("a2", 0.5))]
    provider = MagicMock()
    provider.embed_batch.return_value = [[1.0, 0.0]]
    return manifest, hits, provider


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_reranks_through_the_seam_and_reports_the_model(mock_search, mock_resolve, tmp_path):
    manifest, hits, provider = _setup(tmp_path)
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = hits
    base = {"query": "jaguar corridor", "index_fingerprints": ["idx"], "top_k": 3}
    plain = retrieve(base, manifest, lambda *a: provider, lambda *a: None)
    assert [r["chunk_id"] for r in plain["results"]] == ["a1", "a3", "a2"] and "rerank" not in plain

    ad = rr.MockReranker(_overlap, "mock", "rev1")
    out = retrieve({**base, "rerank": {"n": 3}}, manifest, lambda *a: provider, lambda *a: None, lambda: ad)
    assert [r["chunk_id"] for r in out["results"]] == ["a2", "a1", "a3"]          # the reranker rescued a2
    assert out["results"][0]["fused_score"] == pytest.approx(0.5)
    assert out["rerank"]["model"] == "mock" and out["rerank"]["revision"] == "rev1" and out["rerank"]["n"] == 3
    # the reranker saw the text that was embedded, not an id or a score
    assert ad.passages_scored == 3


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_rerank_n_smaller_than_the_pool_only_scores_n(mock_search, mock_resolve, tmp_path):
    manifest, hits, provider = _setup(tmp_path)
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = hits
    ad = rr.MockReranker(_overlap)
    out = retrieve({"query": "jaguar corridor", "index_fingerprints": ["idx"], "top_k": 3, "rerank": {"n": 2}},
                   manifest, lambda *a: provider, lambda *a: None, lambda: ad)
    assert ad.passages_scored == 2 and len(out["results"]) == 2          # only the first n are scored and returned
    assert {r["chunk_id"] for r in out["results"]} == {"a1", "a3"}
    # rank 0..: contiguous and score-descending, so the retrieval-result validator accepted it
    assert [r["rank"] for r in out["results"]] == list(range(len(out["results"])))


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_rerank_without_a_wired_adapter_fails_loudly(mock_search, mock_resolve, tmp_path):
    manifest, hits, provider = _setup(tmp_path)
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = hits
    with pytest.raises(RetrievalInternalError):
        retrieve({"query": "q", "index_fingerprints": ["idx"], "rerank": {"n": 2}}, manifest, lambda *a: provider, lambda *a: None)


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_rerank_with_no_results_is_a_zero_result_not_a_crash(mock_search, mock_resolve, tmp_path):
    manifest, _, provider = _setup(tmp_path)
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = []
    out = retrieve({"query": "q", "index_fingerprints": ["idx"], "rerank": {"n": 5}}, manifest, lambda *a: provider,
                   lambda *a: None, lambda: rr.MockReranker(_overlap))
    assert out["results"] == [] and out["zero_results"] is True
