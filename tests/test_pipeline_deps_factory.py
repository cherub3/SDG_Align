"""
Tests for build_pipeline_deps and Stage 10 compatibility.
"""

from unittest.mock import MagicMock
import pytest

from scripts.pipeline_deps_factory import build_pipeline_deps, make_provider_adapter_factory
from scripts.stage10_retrieval import EmbeddingModelMismatchError
from scripts.cache_adapter import InMemoryCacheAdapter
from scripts.stage18_api_response_serving import PipelineDependencies


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_llm_adapter():
    m = MagicMock()
    m.execute_prompt = MagicMock(return_value={"status": "PASS", "content": "ok"})
    return m


def _mock_embedding_adapter():
    m = MagicMock()
    m.embed_batch = MagicMock(return_value=[[0.1] * 768])
    return m


# ── build_pipeline_deps construction ──────────────────────────────────────────

class TestBuildPipelineDeps:
    def _make(self):
        return build_pipeline_deps(
            llm_adapter=_mock_llm_adapter(),
            embedding_adapter=_mock_embedding_adapter(),
            cache_adapter=InMemoryCacheAdapter(),
            default_model_name="gemini-test",
        )

    def test_returns_pipeline_dependencies_dict(self):
        deps = self._make()
        assert isinstance(deps, dict)

    def test_retrieve_callable_attached(self):
        deps = self._make()
        assert callable(deps["retrieve"])

    def test_llm_adapter_attached(self):
        llm = _mock_llm_adapter()
        deps = build_pipeline_deps(
            llm_adapter=llm,
            embedding_adapter=_mock_embedding_adapter(),
            cache_adapter=InMemoryCacheAdapter(),
            default_model_name="gemini-test",
        )
        assert deps["llm_adapter"] is llm

    def test_cache_adapter_attached(self):
        cache = InMemoryCacheAdapter()
        deps = build_pipeline_deps(
            llm_adapter=_mock_llm_adapter(),
            embedding_adapter=_mock_embedding_adapter(),
            cache_adapter=cache,
            default_model_name="gemini-test",
        )
        assert deps["cache_adapter"] is cache

    def test_default_model_name_attached(self):
        deps = build_pipeline_deps(
            llm_adapter=_mock_llm_adapter(),
            embedding_adapter=_mock_embedding_adapter(),
            cache_adapter=InMemoryCacheAdapter(),
            default_model_name="my-model",
        )
        assert deps["default_model_name"] == "my-model"

    def test_all_required_keys_present(self):
        deps = self._make()
        assert set(deps.keys()) >= {"retrieve", "llm_adapter", "cache_adapter", "default_model_name"}


# ── Stage 10 retrieve callable integration ────────────────────────────────────

class TestRetrieveCallable:
    """Tests the retrieve closure without real index files.

    In the test environment data/proposals/manifest.json does not exist, so
    load_manifest() returns {}.  Requesting non-existent fingerprints exercises
    Stage 10's INDEX_NOT_FOUND path and returns status FAIL — proving the
    closure is correctly composed without requiring live FAISS indexes.
    """

    def _retrieve(self):
        deps = build_pipeline_deps(
            llm_adapter=_mock_llm_adapter(),
            embedding_adapter=_mock_embedding_adapter(),
            cache_adapter=InMemoryCacheAdapter(),
            default_model_name="gemini-test",
        )
        return deps["retrieve"]

    def test_retrieve_returns_dict(self):
        result = self._retrieve()({"query": "test", "index_fingerprints": ["nonexistent_fp"]})
        assert isinstance(result, dict)

    def test_retrieve_returns_known_keys(self):
        result = self._retrieve()({"query": "test", "index_fingerprints": ["nonexistent_fp"]})
        assert "status" in result
        assert "results" in result
        assert "findings" in result

    def test_retrieve_empty_fingerprints_returns_fail(self):
        result = self._retrieve()({"query": "test", "index_fingerprints": []})
        assert result["status"] == "FAIL"
        assert any(f["code"] == "INDEX_FINGERPRINTS_EMPTY" for f in result["findings"])

    def test_retrieve_missing_index_returns_fail(self):
        result = self._retrieve()({"query": "test", "index_fingerprints": ["fp_does_not_exist"]})
        assert result["status"] == "FAIL"

    def test_retrieve_empty_query_returns_fail(self):
        result = self._retrieve()({"query": "", "index_fingerprints": ["fp_x"]})
        assert result["status"] == "FAIL"
        assert any(f["code"] == "QUERY_EMPTY" for f in result["findings"])


# ── make_provider_adapter_factory: enforce the model at query time ────────────

class _FakeEmbeddingAdapter:
    provider_name = "huggingface"
    model_name = "BAAI/bge-small-en-v1.5"
    model_version = "v1.5"


class TestProviderAdapterFactory:
    def test_returns_the_wired_adapter_when_identity_matches(self):
        adapter = _FakeEmbeddingAdapter()
        factory = make_provider_adapter_factory(adapter)
        assert factory("huggingface", "BAAI/bge-small-en-v1.5", "v1.5") is adapter

    @pytest.mark.parametrize("provider,model,version", [
        ("gemini", "BAAI/bge-small-en-v1.5", "v1.5"),               # different provider
        ("huggingface", "BAAI/bge-base-en-v1.5", "v1.5"),           # different model
        ("huggingface", "BAAI/bge-small-en-v1.5", "v2.0"),          # different version
        ("stub_provider", "stub-model", "v1.0"),                    # the stub index shipped in the repo
        (None, None, None),                                         # index metadata missing the fields
    ])
    def test_refuses_any_other_embedding_identity(self, provider, model, version):
        factory = make_provider_adapter_factory(_FakeEmbeddingAdapter())
        with pytest.raises(EmbeddingModelMismatchError) as exc:
            factory(provider, model, version)
        assert "huggingface/BAAI/bge-small-en-v1.5/v1.5" in str(exc.value)  # names the wired adapter



# ── Retrieval mode of the served backend (Phase 2 serving fix) ────────────────

import json
from pathlib import Path
from unittest.mock import patch

from scripts import pipeline_deps_factory as pdf
from scripts.stage10_retrieval import IndexHandle, retrieve as stage10_retrieve
from src.ingestion_types import DocumentStatus, ManifestRecord


class TestResolveRetrievalMode:
    def test_unset_defaults_to_hybrid(self):
        assert pdf.resolve_retrieval_mode({}) == "hybrid"

    def test_blank_defaults_to_hybrid(self):
        assert pdf.resolve_retrieval_mode({"RETRIEVAL_MODE": "   "}) == "hybrid"

    def test_dense_is_accepted_case_and_space_insensitive(self):
        assert pdf.resolve_retrieval_mode({"RETRIEVAL_MODE": " Dense "}) == "dense"

    def test_hybrid_is_accepted(self):
        assert pdf.resolve_retrieval_mode({"RETRIEVAL_MODE": "hybrid"}) == "hybrid"

    @pytest.mark.parametrize("bad", ["hybird", "bm25", "rerank", "0", "true"])
    def test_any_other_value_raises(self, bad):
        with pytest.raises(ValueError, match="RETRIEVAL_MODE"):
            pdf.resolve_retrieval_mode({"RETRIEVAL_MODE": bad})

    def test_reads_the_process_environment_by_default(self, monkeypatch):
        monkeypatch.setenv("RETRIEVAL_MODE", "dense")
        assert pdf.resolve_retrieval_mode() == "dense"

    def test_served_hybrid_params_are_the_measured_ones(self):
        assert pdf.SERVED_HYBRID_PARAMS == {"rrf_k": 10, "w_bm25": 2.0, "depth": 50}
        assert pdf.DEFAULT_RETRIEVAL_MODE == "hybrid"


class _P:
    """Embedding adapter whose identity matches the test index handle; returns a fixed query vector."""
    provider_name, model_name, model_version = "p", None, None

    def embed_batch(self, texts):
        return [[1.0, 0.0]]


def _deps(monkeypatch, env=None):
    monkeypatch.delenv("RETRIEVAL_MODE", raising=False)
    if env is not None:
        monkeypatch.setenv("RETRIEVAL_MODE", env)
    return build_pipeline_deps(llm_adapter=_mock_llm_adapter(), embedding_adapter=_P(),
                               cache_adapter=InMemoryCacheAdapter(), default_model_name="m")


class TestServedRetrievalMode:
    """The closure the HTTP backend calls must apply the measured hybrid configuration unless told otherwise."""

    def _spy(self, monkeypatch, env=None):
        calls = []
        monkeypatch.setattr(pdf, "retrieve", lambda req, *a, **k: calls.append(req) or {"status": "PASS"})
        _deps(monkeypatch, env)["retrieve"]({"query": "q", "index_fingerprints": ["idx"]})
        return calls[0]

    def test_default_injects_the_measured_hybrid_params(self, monkeypatch):
        assert self._spy(monkeypatch)["hybrid"] == {"rrf_k": 10, "w_bm25": 2.0, "depth": 50}

    def test_dense_mode_leaves_the_request_dense_only(self, monkeypatch):
        assert "hybrid" not in self._spy(monkeypatch, "dense")

    def test_invalid_mode_fails_at_build_time(self, monkeypatch):
        with pytest.raises(ValueError, match="RETRIEVAL_MODE"):
            _deps(monkeypatch, "typo")

    def test_a_request_that_sets_hybrid_itself_is_not_overridden(self, monkeypatch):
        calls = []
        monkeypatch.setattr(pdf, "retrieve", lambda req, *a, **k: calls.append(req) or {"status": "PASS"})
        retrieve_fn = _deps(monkeypatch)["retrieve"]
        retrieve_fn({"query": "q", "index_fingerprints": ["i"], "hybrid": False})
        retrieve_fn({"query": "q", "index_fingerprints": ["i"], "hybrid": {"rrf_k": 60}})
        assert calls[0]["hybrid"] is False and calls[1]["hybrid"] == {"rrf_k": 60}

    def test_the_callers_request_dict_is_not_mutated(self, monkeypatch):
        monkeypatch.setattr(pdf, "retrieve", lambda req, *a, **k: {"status": "PASS"})
        req = {"query": "q", "index_fingerprints": ["i"]}
        _deps(monkeypatch)["retrieve"](req)
        assert "hybrid" not in req


def _lexical_fixture(tmp_path):
    path = tmp_path / "dA.json"
    path.write_text(json.dumps({"chunks": [
        {"chunk_id": "a1", "text": "general background text", "category": "c", "doc_type": "d"},
        {"chunk_id": "a2", "text": "zebra quagga okapi", "category": "c", "doc_type": "d"}]}), encoding="utf-8")
    manifest = {"dA": ManifestRecord(doc_id="dA", category="c", status=DocumentStatus.READY_FOR_CHUNKING,
                                     artifact_paths={"vector_index": "x", "chunks": str(path)})}
    hits = [{"index_fingerprint": "idx", "distance": 0.9, "metric": "cosine", "embedding_id": "e1", "chunk_id": "a1", "doc_id": "dA"},
            {"index_fingerprint": "idx", "distance": 0.2, "metric": "cosine", "embedding_id": "e2", "chunk_id": "a2", "doc_id": "dA"}]
    return manifest, hits


@patch("scripts.stage10_retrieval.resolve_index_fingerprints")
@patch("scripts.stage10_retrieval.search_index")
def test_served_path_matches_the_evaluated_hybrid_path_end_to_end(mock_search, mock_resolve, tmp_path, monkeypatch):
    """Through the real stage-10 retrieve(): the served default returns exactly what the Phase 2 eval configuration
    returns (a lexical match beats a higher cosine), and RETRIEVAL_MODE=dense restores the dense order."""
    manifest, hits = _lexical_fixture(tmp_path)
    mock_resolve.return_value = [IndexHandle("idx", {"provider": "p", "embedding_dimension": 2}, Path("p"))]
    mock_search.return_value = hits
    monkeypatch.setattr(pdf, "load_manifest", lambda: manifest)
    req = {"query": "zebra quagga", "index_fingerprints": ["idx"]}

    served = _deps(monkeypatch)["retrieve"](dict(req))
    evaluated = stage10_retrieve({**req, "hybrid": dict(pdf.SERVED_HYBRID_PARAMS)}, manifest, lambda *a: _P(), lambda *a: None)
    assert [r["chunk_id"] for r in served["results"]] == ["a2", "a1"]
    assert served["results"] == evaluated["results"]

    dense = _deps(monkeypatch, "dense")["retrieve"](dict(req))
    assert [r["chunk_id"] for r in dense["results"]] == ["a1", "a2"]
