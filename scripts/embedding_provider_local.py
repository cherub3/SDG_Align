"""Local embedding provider: sentence-transformers on CPU, no network, no credential.

Same ProviderAdapter contract as the hosted providers, so it works for stage 8 (indexing) and for
stage 10 (query time) through the same composition root. Select it with
    EMBEDDING_PROVIDER=local
    EMBEDDING_PROVIDER_EXTRA_MODEL_NAME=BAAI/bge-small-en-v1.5      (default)
    EMBEDDING_PROVIDER_EXTRA_MODEL_VERSION=v1.5                      (default)
    EMBEDDING_PROVIDER_EXTRA_REVISION=<hub commit hash>              (default: pinned below)

`sentence-transformers` and `torch` are optional (requirements-local.txt); they are imported only
when the first batch is embedded, so importing this module and constructing the adapter need neither.

Determinism: CPU only, one torch thread (fixed reduction order), eval mode, no dropout, vectors
L2-normalised, and the model weights pinned to a hub commit hash. Same input on the same machine
gives the same vectors (checked by tools/ and recorded in reports/evidence/).
"""
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage8_embedding_generation import ProviderAdapter
from scripts.phase1_1_configuration_layer import ProviderSettings, ProviderRegistration

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_MODEL_VERSION = "v1.5"
# Hub commit of BAAI/bge-small-en-v1.5 whose weights produced the Phase 1 index.
DEFAULT_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
DEFAULT_BATCH_SIZE = 32
_UNPINNED_ALIASES = {"latest", "stable", "preview", "beta"}


ALLOW_DOWNLOAD_ENV = "ALLOW_MODEL_DOWNLOAD"


class LocalModelUnavailableError(RuntimeError):
    """The local embedding model is not in the local cache and downloading is not allowed."""


def _download_allowed() -> bool:
    return (os.environ.get(ALLOW_DOWNLOAD_ENV) or "").strip().lower() in ("1", "true", "yes")


def _load_sentence_transformer(model_name: str, revision: Optional[str], num_threads: int) -> Any:
    # Offline by default: the model is read from the local Hugging Face cache only, so a query can never trigger a
    # silent download. Setting the env vars BEFORE the import matters (huggingface_hub reads them at import time);
    # local_files_only=True below is the belt to that braces. A one-time download needs ALLOW_MODEL_DOWNLOAD=true.
    offline = not _download_allowed()
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - exercised only without the optional deps
        raise RuntimeError(
            "The 'local' embedding provider needs sentence-transformers and torch: "
            "pip install -r requirements-local.txt"
        ) from exc
    torch.set_num_threads(num_threads)
    try:
        model = SentenceTransformer(model_name, device="cpu", revision=revision, local_files_only=offline)
    except Exception as exc:
        if offline:
            raise LocalModelUnavailableError(
                f"local embedding model {model_name!r} (revision {revision}) is not in the local Hugging Face cache and "
                f"downloads are disabled. Place the model in the cache once (set {ALLOW_DOWNLOAD_ENV}=true for a single "
                f"run on a trusted network), or bake it into the image. Cause: {exc}") from exc
        raise
    model.eval()
    return model


class LocalEmbeddingAdapter(ProviderAdapter):
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, model_version: str = DEFAULT_MODEL_VERSION,
                 revision: Optional[str] = DEFAULT_REVISION, batch_size: int = DEFAULT_BATCH_SIZE,
                 num_threads: int = 1, model_loader: Optional[Callable[[], Any]] = None):
        if model_version.lower() in _UNPINNED_ALIASES:
            raise ValueError(f"local provider 'model_version' must be pinned; floating alias "
                             f"'{model_version}' is not permitted")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._model_name = model_name
        self._model_version = model_version
        self._revision = revision
        self._batch_size = batch_size
        self._num_threads = num_threads
        self._loader = model_loader or (lambda: _load_sentence_transformer(model_name, revision, num_threads))
        self._model: Any = None
        self._embedding_dimension: Optional[int] = None

    @property
    def provider_name(self) -> str:
        return "local"

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

    def warm_up(self) -> None:
        """Loads the model now (idempotent). Used at server startup so a missing model fails there, loudly."""
        if self._model is None:
            self._model = self._loader()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        import numpy as np
        if not texts:
            return []
        if self._model is None:
            self._model = self._loader()
        raw = self._model.encode(list(texts), batch_size=self._batch_size, convert_to_numpy=True,
                                 normalize_embeddings=False, show_progress_bar=False)
        vectors = np.asarray(raw, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0                      # an all-zero vector stays zero instead of NaN
        vectors = vectors / norms
        if self._embedding_dimension is None:
            self._embedding_dimension = int(vectors.shape[1])
        return vectors.tolist()

    def is_transient_error(self, exception: Exception) -> bool:
        return False                                 # local compute: a failure is never worth retrying

    @property
    def max_batch_size(self) -> Optional[int]:
        return self._batch_size

    @property
    def config_fingerprint_fields(self) -> Dict[str, Any]:
        return {"revision": self._revision, "normalized": True, "device": "cpu"}


def local_factory(settings: ProviderSettings, raw_credential: Optional[str]) -> ProviderAdapter:
    """Factory for Phase 1.1 wire_dependencies(). No credential is used or needed."""
    extra = settings.get("extra", {})
    return LocalEmbeddingAdapter(
        model_name=extra.get("model_name", DEFAULT_MODEL_NAME),
        model_version=extra.get("model_version", DEFAULT_MODEL_VERSION),
        revision=extra.get("revision", DEFAULT_REVISION),
        batch_size=int(extra.get("batch_size", DEFAULT_BATCH_SIZE)),
        num_threads=int(extra.get("num_threads", 1)),
    )


def get_provider_registration() -> ProviderRegistration:
    return {
        "seam": "EMBEDDING_PROVIDER",
        "provider_name": "local",
        "network_dependent": False,
        "factory": local_factory,
    }
