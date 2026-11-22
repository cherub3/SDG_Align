"""Advisory low-confidence flag (3d): off by default, never refuses, never reorders or drops results."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import confidence as cf
from scripts.stage10_retrieval import retrieve, IndexHandle
from scripts.stage0_register import ManifestRecord, DocumentStatus


def test_default_threshold_is_the_dev_answerable_value():
    assert cf.DEFAULT_THRESHOLD == 0.6604


def test_flag_is_strictly_below_threshold_and_names_its_inputs():
    assert cf.confidence_advisory([{"score": 0.66, "dense_score": 0.6603}])["low_confidence"] is True
    assert cf.confidence_advisory([{"score": 0.66, "dense_score": 0.6604}])["low_confidence"] is False
    a = cf.confidence_advisory([{"score": 0.9, "dense_score": 0.5}], threshold=0.4)
    assert a == {"dense_score": 0.5, "threshold": 0.4, "low_confidence": False, "advisory_only": True}


def test_dense_score_comes_from_the_right_field():
    assert cf.top1_dense_score([{"score": 0.7}]) == 0.7                                   # dense only
    assert cf.top1_dense_score([{"score": 3.1, "fused_score": 0.8}]) == 0.8               # dense + rerank
    assert cf.top1_dense_score([{"score": 0.03, "dense_score": 0.7, "fused_score": 0.03}]) == 0.7   # hybrid wins
    assert cf.top1_dense_score([]) is None


def test_no_results_is_low_confidence():
    assert cf.confidence_advisory([])["low_confidence"] is True


def _setup(tmp_path):
    path = tmp_path / "dA.json"
    path.write_text(json.dumps({"chunks": [{"chunk_id": "a1", "text": "x", "category": "c", "doc_type": "d"}]}), encoding="utf-8")
    manifest = {"dA": ManifestRecord(doc_id="dA", category="c", status=DocumentStatus.READY_FOR_CHUNKING,
                                     artifact_paths={"vector_index": "x", "chunks": str(path)})}
    hits = [{"index_fingerprint": "idx", "distance": 0.3, "metric": "cosine", "embedding_id": "ea1", "chunk_id": "a1", "doc_id": "dA"}]
    provider = MagicMock()
    provider.embed_batch.return_value = [[1.0, 0.0]]
    return manifest, hits, provider


@patch('scripts.stage10_retrieval.resolve_index_fingerprints')
@patch('scripts.stage10_retrieval.search_index')
def test_retrieve_adds_the_hint_only_when_asked_and_never_changes_results(mock_search, mock_resolve, tmp_path):
    manifest, hits, provider = _setup(tmp_path)
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = hits
    base = {"query": "q", "index_fingerprints": ["idx"]}
    plain = retrieve(base, manifest, lambda *a: provider, lambda *a: None)
    assert "confidence" not in plain                                              # OFF by default
    on = retrieve({**base, "confidence_advisory": True}, manifest, lambda *a: provider, lambda *a: None)
    assert on["confidence"]["low_confidence"] is True and on["confidence"]["dense_score"] == pytest.approx(0.3)
    assert [r["chunk_id"] for r in on["results"]] == [r["chunk_id"] for r in plain["results"]] == ["a1"]   # never refuses or drops
    off = retrieve({**base, "confidence_advisory": {"threshold": 0.1}}, manifest, lambda *a: provider, lambda *a: None)
    assert off["confidence"]["low_confidence"] is False and len(off["results"]) == 1
