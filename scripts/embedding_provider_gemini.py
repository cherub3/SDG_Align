import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import errors

# Adjust path to import from src/scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage8_embedding_generation import ProviderAdapter
from scripts.phase1_1_configuration_layer import ProviderSettings, ProviderRegistration


class GeminiEmbeddingAdapter(ProviderAdapter):
    """
    Concrete embedding provider adapter for Google Gemini via google-genai SDK.
    Fully implements Phase 1.3 architecture and Stage 8 ProviderAdapter contract.
    """

    def __init__(self, client: genai.Client, model_name: str, model_version: str):
        # SDK client ownership: constructed exactly once, held privately, never escapes.
        self._client = client
        
        # Provider identity: stable triple fixed at construction.
        self._model_name = model_name
        self._model_version = model_version
        
        # Discovered at runtime per Stage 8 contract
        self._embedding_dimension: Optional[int] = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def embedding_dimension(self) -> int:
        if self._embedding_dimension is None:
            raise RuntimeError("embedding_dimension not yet discovered (embed_batch has not returned any vectors)")
        return self._embedding_dimension

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # For Gemini embeddings, the model target is the exact model_name 
        # (e.g. 'text-embedding-004'). 
        response = self._client.models.embed_content(
            model=self._model_name,
            contents=texts
        )
        
        vectors = [emb.values for emb in response.embeddings]
        
        if self._embedding_dimension is None and vectors:
            self._embedding_dimension = len(vectors[0])
            
        return vectors

    def is_transient_error(self, exception: Exception) -> bool:
        """
        Classifies exceptions into Transient (True) or Fatal (False) 
        per Phase 1.3 Failure Handling rules.
        """
        if isinstance(exception, errors.APIError):
            # 429: Resource Exhausted (Rate Limit)
            # 500, 502, 503, 504: Transient server errors
            if getattr(exception, 'code', None) in (429, 500, 502, 503, 504):
                return True
            return False
            
        # Treat underlying network connection errors as transient
        exc_type = type(exception).__name__
        if exc_type in ("ConnectError", "TimeoutException", "ReadTimeout", "ConnectionError"):
            return True
            
        return False

    @property
    def requests_per_minute(self) -> Optional[int]:
        return 1500  # Typical Gemini embedding RPM limit

    @property
    def max_batch_size(self) -> Optional[int]:
        return 100  # Gemini SDK allows up to 100 texts per request

    @property
    def config_fingerprint_fields(self) -> Dict[str, Any]:
        return {}


def gemini_factory(settings: ProviderSettings, raw_credential: Optional[str]) -> ProviderAdapter:
    """
    Factory invoked by Phase 1.1 wire_dependencies().
    Consumes raw_credential exactly once to build the client.
    """
    extra = settings.get("extra", {})
    
    # 1. Construction-time validation
    model_name = extra.get("model_name")
    if not model_name:
        raise ValueError("Gemini provider requires 'model_name' in extra settings")
        
    model_version = extra.get("model_version")
    if not model_version:
        raise ValueError("Gemini provider requires 'model_version' in extra settings")
        
    _UNPINNED_ALIASES = {"latest", "stable", "preview", "beta"}
    if model_version.lower() in _UNPINNED_ALIASES:
        raise ValueError(
            f"Gemini provider 'model_version' must be pinned; "
            f"floating alias '{model_version}' is not permitted"
        )
        
    if not raw_credential:
        raise ValueError("Gemini provider requires a credential (API key)")
        
    # 2. SDK client construction (Embedding Lifecycle step [2])
    # The credential is consumed here and goes out of scope after the factory returns.
    client = genai.Client(api_key=raw_credential)
    
    # 3. Adapter instance returned
    return GeminiEmbeddingAdapter(client, model_name, model_version)


def get_provider_registration() -> ProviderRegistration:
    """
    Registration dict for Phase 1.1. Assembling into the global ProviderRegistry 
    remains a composition-root responsibility.
    """
    return {
        "seam": "EMBEDDING_PROVIDER",
        "provider_name": "gemini",
        "network_dependent": True,
        "factory": gemini_factory
    }
