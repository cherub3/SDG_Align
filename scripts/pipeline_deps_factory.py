"""
Factory for PipelineDependencies (Stage 18).

Composes existing repository implementations:
  • retrieve()            — Stage 10, bound with manifest + adapter closures
  • llm_adapter           — LLM_PROVIDER wired by compose_application
  • cache_adapter         — InMemoryCacheAdapter (Phase 11)
  • default_model_name    — deployment scalar from configuration

The retrieve closure wraps the already-wired embedding_adapter rather than
introducing a separate provider-dispatch table.  The simplification is valid
for the current single-provider deployment.
"""

import os
from typing import Any, Dict, Optional

from scripts.stage0_register import load_manifest
from scripts.stage9_vector_indexing import FAISSAdapter, IndexAdapter
from scripts.stage10_retrieval import EmbeddingModelMismatchError, retrieve
from scripts.stage13_llm_execution import LLMAdapter
from scripts.stage17_response_caching import CacheAdapter
from scripts.stage18_api_response_serving import PipelineDependencies


# Retrieval mode of the served backend. "hybrid" (BM25 + dense, reciprocal rank fusion) is the measured best configuration
# (Phase 2, step 3b: test R@5 0.57 -> 0.77); "dense" is the Phase 1 baseline, kept for comparison and as a fallback.
RETRIEVAL_MODES = ("hybrid", "dense")
DEFAULT_RETRIEVAL_MODE = "hybrid"
# Exactly the setting that was selected on the dev split and measured once on test. Do not edit without re-measuring.
SERVED_HYBRID_PARAMS = {"rrf_k": 10, "w_bm25": 2.0, "depth": 50}


def resolve_retrieval_mode(environ: Optional[Dict[str, str]] = None) -> str:
    """Reads RETRIEVAL_MODE (unset or blank -> hybrid). Any value other than hybrid/dense raises ValueError, so a typo
    fails at startup instead of silently serving a different retrieval than the one that was measured."""
    env = os.environ if environ is None else environ
    raw = (env.get("RETRIEVAL_MODE") or "").strip().lower()
    if not raw:
        return DEFAULT_RETRIEVAL_MODE
    if raw not in RETRIEVAL_MODES:
        raise ValueError(f"RETRIEVAL_MODE must be one of {list(RETRIEVAL_MODES)}, got {raw!r}")
    return raw


def make_provider_adapter_factory(embedding_adapter: Any):
    """Returns the (provider, model, version) -> adapter callable that Stage 10 uses at query time.

    The wired embedding adapter is returned only when the index's embedding identity matches it
    exactly. Otherwise EmbeddingModelMismatchError is raised and retrieval refuses to search that
    index (finding INDEX_EMBEDDING_MODEL_MISMATCH) instead of silently comparing vectors that
    belong to different embedding spaces."""
    wired = (embedding_adapter.provider_name, embedding_adapter.model_name, embedding_adapter.model_version)

    def _provider_adapter_factory(provider: str, model: str, version: str):
        if (provider, model, version) != wired:
            raise EmbeddingModelMismatchError(
                f"index was built with {provider}/{model}/{version} but the wired embedding "
                f"adapter is {wired[0]}/{wired[1]}/{wired[2]}"
            )
        return embedding_adapter

    return _provider_adapter_factory


def build_pipeline_deps(
    llm_adapter: LLMAdapter,
    embedding_adapter: Any,
    cache_adapter: CacheAdapter,
    default_model_name: str,
) -> PipelineDependencies:
    """Construct a PipelineDependencies using only existing repository code.

    Args:
        llm_adapter:        The LLM_PROVIDER adapter from compose_application.
        embedding_adapter:  The EMBEDDING_PROVIDER adapter from compose_application.
        cache_adapter:      A CacheAdapter instance (e.g. InMemoryCacheAdapter).
        default_model_name: The default LLM model name string.

    Returns:
        A fully-populated PipelineDependencies TypedDict ready for Stage 18.
    """
    manifest = load_manifest()
    retrieval_mode = resolve_retrieval_mode()      # fails here, at startup, on an invalid value

    _provider_adapter_factory = make_provider_adapter_factory(embedding_adapter)

    def _index_adapter_factory(metric: str) -> IndexAdapter:
        return FAISSAdapter(metric)

    def _retrieve(request: Dict[str, Any]) -> Dict[str, Any]:
        # The served default is the measured hybrid configuration. A request that carries its own "hybrid" key
        # (including an explicit False for dense-only) is passed through untouched.
        if retrieval_mode == "hybrid" and "hybrid" not in request:
            request = {**request, "hybrid": dict(SERVED_HYBRID_PARAMS)}
        return retrieve(request, manifest, _provider_adapter_factory, _index_adapter_factory)

    return PipelineDependencies(
        retrieve=_retrieve,
        llm_adapter=llm_adapter,
        cache_adapter=cache_adapter,
        default_model_name=default_model_name,
    )
