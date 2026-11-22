"""Second-stage reranker seam, step 3c.

Retrieval (dense + BM25 fused) is cheap and recall-oriented; a cross-encoder reads (query, passage) TOGETHER and is
far better at ordering a short list, but is too slow to run over the whole corpus. So: fuse -> take top N -> rerank.

Same shape as the embedding-provider seam: a small abstract contract (`RerankAdapter`), one real implementation
(`CrossEncoderReranker`, local sentence-transformers CrossEncoder on CPU, pinned to a hub commit hash, no network at
run time) and a `MockReranker` for unit tests. The model id and revision live in config/rerank_model.json.

Scores are raw logits (unbounded, not probabilities). They are only comparable between passages for the SAME query,
which is why abstention (3d) has to be calibrated rather than assumed.
"""
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "rerank_model.json"
_UNPINNED = {"", "main", "latest", "stable", "master"}


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    cfg = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    if str(cfg.get("revision", "")).lower() in _UNPINNED:
        raise ValueError("rerank_model.json 'revision' must be a pinned hub commit hash, not a floating ref")
    return cfg


class RerankAdapter:
    """Contract for any reranker: score each passage against the query (higher = more relevant)."""

    @property
    def model_name(self) -> str:
        raise NotImplementedError

    @property
    def revision(self) -> str:
        raise NotImplementedError

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        raise NotImplementedError


class CrossEncoderReranker(RerankAdapter):
    """sentence-transformers CrossEncoder, CPU, one torch thread, eval mode. Loaded lazily on the first call."""

    def __init__(self, model_name: Optional[str] = None, revision: Optional[str] = None, max_length: Optional[int] = None,
                 batch_size: int = 16, num_threads: int = 1, model_loader: Optional[Callable[[], Any]] = None):
        cfg = load_config() if (model_name is None or revision is None or max_length is None) else {}
        self._name = model_name or cfg["model_id"]
        self._rev = revision or cfg["revision"]
        if self._rev.lower() in _UNPINNED:
            raise ValueError("reranker revision must be pinned")
        self._max_length = max_length or cfg.get("max_length", 512)
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._batch = batch_size
        self._threads = num_threads
        self._loader = model_loader or self._load
        self._model: Any = None

    def _load(self) -> Any:
        try:
            import torch
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - only without the optional deps
            raise RuntimeError("The reranker needs sentence-transformers and torch: pip install -r requirements-local.txt") from exc
        torch.set_num_threads(self._threads)
        return CrossEncoder(self._name, revision=self._rev, device="cpu", max_length=self._max_length)

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def revision(self) -> str:
        return self._rev

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        if not passages:
            return []
        if self._model is None:
            self._model = self._loader()
        out = self._model.predict([(query, p) for p in passages], batch_size=self._batch, show_progress_bar=False)
        return [float(x) for x in out]


class MockReranker(RerankAdapter):
    """Deterministic stand-in for tests: score = fn(query, passage). Counts calls so tests can assert on cost."""

    def __init__(self, fn: Callable[[str, str], float], model_name: str = "mock-reranker", revision: str = "mock-0"):
        self._fn, self._name, self._rev = fn, model_name, revision
        self.calls = 0
        self.passages_scored = 0

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def revision(self) -> str:
        return self._rev

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        self.calls += 1
        self.passages_scored += len(passages)
        return [float(self._fn(query, p)) for p in passages]


def rerank_results(results: List[Dict], query: str, adapter: RerankAdapter, text_of: Callable[[Dict], str],
                   n: int, top_k: int) -> Dict[str, Any]:
    """Rerank the first `n` of `results` (already best-first). Returns {"results", "ms", "n_scored"}.

    Each returned item keeps the stage-10 shape; `score` becomes the reranker logit (so the list stays score-descending,
    which the retrieval-result validator requires), the retrieval-stage score moves to `fused_score`, and ranks are
    reassigned from 0. Ties break on chunk_id so the order is fully deterministic. At most min(top_k, n) items come back:
    anything past the reranked pool has no score on the same scale, so it is not mixed in.
    """
    if n < 1:
        raise ValueError("rerank n must be at least 1")
    pool = [dict(r) for r in results[:n]]
    t = time.perf_counter()
    scores = adapter.score(query, [text_of(r) for r in pool])
    ms = (time.perf_counter() - t) * 1000
    if len(scores) != len(pool):
        raise ValueError(f"reranker returned {len(scores)} scores for {len(pool)} passages")
    for r, s in zip(pool, scores):
        r["fused_score"] = r["score"]
        r["rerank_score"] = s
        r["score"] = s
    pool.sort(key=lambda r: (-r["score"], r["chunk_id"]))
    out = pool[:max(1, top_k)]
    for i, r in enumerate(out):
        r["rank"] = i
    return {"results": out, "ms": ms, "n_scored": len(pool)}
