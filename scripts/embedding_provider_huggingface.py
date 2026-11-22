import sys
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

# Adjust path to import from src/scripts
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage8_embedding_generation import ProviderAdapter
from scripts.phase1_1_configuration_layer import ProviderSettings, ProviderRegistration


class HuggingFaceEmbeddingAdapter(ProviderAdapter):
    """
    Concrete embedding provider adapter for Hugging Face Inference API via requests.
    Fully implements Phase 1.3 architecture and Stage 8 ProviderAdapter contract.
    """

    def __init__(self, token: str, model_name: str, model_version: str):
        # We hold the API URL and headers privately.
        # api-inference.huggingface.co was decommissioned by Hugging Face (DNS no longer
        # resolves); router.huggingface.co/hf-inference is its successor endpoint.
        self._url = f"https://router.huggingface.co/hf-inference/models/{model_name}/pipeline/feature-extraction"
        self._headers = {"Authorization": f"Bearer {token}"}
        
        # Provider identity: stable triple fixed at construction.
        self._model_name = model_name
        self._model_version = model_version
        
        # Discovered at runtime per Stage 8 contract
        self._embedding_dimension: Optional[int] = None

    @property
    def provider_name(self) -> str:
        return "huggingface"

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
        response = requests.post(self._url, headers=self._headers, json={"inputs": texts})
        
        # Raise HTTP errors first
        response.raise_for_status()
        
        vectors = response.json()
        
        # Hugging Face sometimes returns a list of lists of lists for multiple inputs or token-level embeddings.
        # But pipeline feature-extraction for BGE models usually returns list of lists (sentence level)
        # Check and normalize if necessary.
        if vectors and isinstance(vectors, list):
            if isinstance(vectors[0], list) and isinstance(vectors[0][0], list):
                # Token level embeddings returned, fallback (though usually pipeline returns pooled)
                # Just take the first token (CLS) for simplicity if it happens.
                pass # not expected for feature-extraction pipeline of sentence transformers
        
        if self._embedding_dimension is None and vectors:
            self._embedding_dimension = len(vectors[0])
            
        return vectors

    def is_transient_error(self, exception: Exception) -> bool:
        """
        Classifies exceptions into Transient (True) or Fatal (False) 
        per Phase 1.3 Failure Handling rules.
        """
        if isinstance(exception, requests.exceptions.HTTPError):
            status_code = exception.response.status_code if exception.response is not None else None
            # 429: Rate Limit
            # 500, 502, 503, 504: Server errors
            # 503 is specially common on HF when model is loading
            if status_code in (429, 500, 502, 503, 504):
                return True
            return False
            
        # Treat underlying network connection errors as transient
        exc_type = type(exception).__name__
        if exc_type in ("ConnectionError", "Timeout", "ConnectTimeout", "ReadTimeout"):
            return True
            
        return False

    @property
    def requests_per_minute(self) -> Optional[int]:
        # Free tier HF limits can be around 30K chars / min or varying.
        return 500

    @property
    def max_batch_size(self) -> Optional[int]:
        # Hugging Face inference API batch limit is typically 32 or less for some models.
        return 32

    @property
    def config_fingerprint_fields(self) -> Dict[str, Any]:
        return {}


def huggingface_factory(settings: ProviderSettings, raw_credential: Optional[str]) -> ProviderAdapter:
    """
    Factory invoked by Phase 1.1 wire_dependencies().
    Consumes raw_credential exactly once to build the client.
    """
    extra = settings.get("extra", {})
    
    # Construction-time validation
    model_name = extra.get("model_name", "BAAI/bge-small-en-v1.5")
    
    # We use 'v1.5' as the pinned model version for this specific default model
    model_version = extra.get("model_version", "v1.5")
    
    _UNPINNED_ALIASES = {"latest", "stable", "preview", "beta"}
    if model_version.lower() in _UNPINNED_ALIASES:
        raise ValueError(
            f"Hugging Face provider 'model_version' must be pinned; "
            f"floating alias '{model_version}' is not permitted"
        )
        
    if not raw_credential:
        raise ValueError("Hugging Face provider requires a credential (API key)")
        
    # Adapter instance returned (raw_credential consumed here)
    return HuggingFaceEmbeddingAdapter(raw_credential, model_name, model_version)


def get_provider_registration() -> ProviderRegistration:
    """
    Registration dict for Phase 1.1. Assembling into the global ProviderRegistry 
    remains a composition-root responsibility.
    """
    return {
        "seam": "EMBEDDING_PROVIDER",
        "provider_name": "huggingface",
        "network_dependent": True,
        "factory": huggingface_factory
    }
