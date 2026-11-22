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

