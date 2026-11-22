"""
Factory for PipelineDependencies (Stage 18).

Composes existing repository implementations:
  • retrieve()            — Stage 10, bound with manifest + adapter closures
  • llm_adapter           — LLM_PROVIDER wired by compose_application
  • cache_adapter         — InMemoryCacheAdapter (Phase 11)
  • default_model_name    — deployment scalar from configuration

The retrieve closure follows the same pattern as build_retrieval_closures()
in composition_root.py: it wraps the already-wired embedding_adapter rather
than introducing a separate provider-dispatch table.  The simplification is
valid for the current single-provider demo deployment.
"""

from typing import Any, Dict

from scripts.stage0_register import load_manifest
from scripts.stage9_vector_indexing import FAISSAdapter, IndexAdapter
from scripts.stage10_retrieval import retrieve
from scripts.stage13_llm_execution import LLMAdapter
from scripts.stage17_response_caching import CacheAdapter
from scripts.stage18_api_response_serving import PipelineDependencies


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

    def _provider_adapter_factory(provider: str, model: str, version: str):
        # Single-provider deployment: return the wired adapter regardless of
        # the index metadata's (provider, model, version) discriminator.
        # Consistent with build_retrieval_closures()'s embed_query closure.
        return embedding_adapter

    def _index_adapter_factory(metric: str) -> IndexAdapter:
        return FAISSAdapter(metric)

    def _retrieve(request: Dict[str, Any]) -> Dict[str, Any]:
        return retrieve(request, manifest, _provider_adapter_factory, _index_adapter_factory)

    return PipelineDependencies(
        retrieve=_retrieve,
        llm_adapter=llm_adapter,
        cache_adapter=cache_adapter,
        default_model_name=default_model_name,
    )
