"""Hybrid retrieval: BM25 (lexical) + dense (vector) fused with reciprocal rank fusion. Step 3b.

Design, all deliberate and all disclosed in reports/PHASE_2_REPORT.md:
  * BM25 is built in memory, deterministically, from the same chunk records the vector index was built from, over the
    same text that was embedded (`embedding_text`: embed_text if present, else text). No new dependency, no state on disk.
  * Tokenizer: lower-case; a token is a run of letters/digits, OR a number that keeps its internal separators
    ("1,250,000", "3.5", "2026-2030" stays "2026" and "2030"). Numbers are kept as tokens, never dropped. No stemming,
    no stop-word list: inverse document frequency already down-weights common words, and a stop list would delete
    words like "no" or "not" that matter to the questions.
  * BM25 Okapi, k1=1.5, b=0.75 (library defaults, not tuned); idf = ln(1 + (N - n + 0.5) / (n + 0.5)), never negative.
  * Fusion: score(chunk) = sum over lists L of w_L / (rrf_k + rank_L(chunk)), rank starting at 1, using only the first
    `depth` entries of each list. Ties break on chunk_id so the order is fully deterministic.
  * The fused score is NOT a cosine similarity. The cosine of the dense hit is carried along as `dense_score` so the
    abstention step (3d) can still threshold on it.
"""
import math
import re
from collections import Counter

import numpy as np
from typing import Dict, List, Optional, Sequence, Tuple

K1 = 1.5
B = 0.75
DEFAULT_PARAMS = {"rrf_k": 60, "w_bm25": 1.0, "w_dense": 1.0, "depth": 50}

# a number with internal , or . separators, or a plain alphanumeric run
_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)+|[^\W_]+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


class BM25Index:
    """Okapi BM25 over a fixed list of (chunk_id, text) pairs."""

    def __init__(self, docs: Sequence[Tuple[str, str]], k1: float = K1, b: float = B):
        self.k1, self.b = k1, b
        self.ids = [d[0] for d in docs]
        self.tf = [Counter(tokenize(d[1])) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg_len = (sum(self.len) / len(self.len)) if self.len else 0.0
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(self.ids)
        self.idf = {t: math.log(1.0 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        # Query-time arrays: per term, the chunks containing it (row indices) and their term frequencies; plus each
        # chunk's length-normaliser. Scoring a query is then a few numpy operations instead of a Python loop over chunks.
        postings: Dict[str, Tuple[list, list]] = {}
        for i, c in enumerate(self.tf):
            for t, f in c.items():
                postings.setdefault(t, ([], []))
                postings[t][0].append(i)
                postings[t][1].append(f)
        self._post = {t: (np.asarray(ix, dtype=np.int64), np.asarray(fs, dtype=np.float64)) for t, (ix, fs) in postings.items()}
        self._norm = (self.k1 * (1.0 - self.b + self.b * np.asarray(self.len, dtype=np.float64) / self.avg_len)
                      if self.len else np.zeros(0))

    def scores(self, query: str) -> Dict[str, float]:
        """BM25 score for every chunk with a non-zero score."""
        q = [t for t in tokenize(query) if t in self.idf]
        acc = np.zeros(len(self.ids), dtype=np.float64)
        for t in q:                                     # repeated query terms count repeatedly, as in the textbook formula
            ix, f = self._post[t]
            acc[ix] += self.idf[t] * f * (self.k1 + 1.0) / (f + self._norm[ix])
        return {self.ids[i]: float(acc[i]) for i in np.flatnonzero(acc > 0.0)}


def rank_by_score(scores: Dict[str, float]) -> List[str]:
    """chunk_ids best-first; ties broken on chunk_id so the order never depends on dict order."""
    return [cid for cid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def rrf_fuse(rankings: Sequence[Tuple[Sequence[str], float]], rrf_k: float, depth: int) -> Dict[str, float]:
    """Reciprocal rank fusion of (ranked chunk_id list, weight) pairs, each cut to its first `depth` entries."""
    fused: Dict[str, float] = {}
    for ranked, weight in rankings:
        for r, cid in enumerate(ranked[:depth], 1):
            fused[cid] = fused.get(cid, 0.0) + weight / (rrf_k + r)
    return fused


_CACHE: Dict[tuple, BM25Index] = {}


def build_bm25(chunks: Sequence[dict], text_of) -> BM25Index:
    """BM25 over `chunks` (stage-7 records). Cached on the exact (chunk_id, text) content, so it is rebuilt only when it changed."""
    docs = sorted(((c["chunk_id"], text_of(c)) for c in chunks), key=lambda d: d[0])
    key = tuple((cid, hash(txt)) for cid, txt in docs)
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = BM25Index(docs)
    return _CACHE[key]


def fuse_candidates(dense_candidates: List[dict], bm25: BM25Index, query: str, params: Optional[dict] = None) -> List[dict]:
    """Re-score dense candidates with RRF over (dense rank, BM25 rank). Returns candidates for chunks found by either list.

    `dense_candidates` must already carry `score` (cosine) and be searched deep enough to cover `depth`. A chunk that BM25
    ranks inside `depth` but the dense list does not contain cannot be returned (it has no embedding_id); the caller
    searches the dense index at least `depth` deep so this only happens for chunks beyond the dense cut.
    """
    p = {**DEFAULT_PARAMS, **(params or {})}
    by_id = {c["chunk_id"]: c for c in dense_candidates}
    dense_rank = rank_by_score({cid: c["score"] for cid, c in by_id.items()})
    bm25_scores = bm25.scores(query)
    bm25_rank = rank_by_score(bm25_scores)
    fused = rrf_fuse([(dense_rank, p["w_dense"]), (bm25_rank, p["w_bm25"])], p["rrf_k"], int(p["depth"]))
    out = []
    for cid, s in fused.items():
        if cid not in by_id:
            continue
        c = dict(by_id[cid])
        c["dense_score"] = c["score"]
        c["bm25_score"] = bm25_scores.get(cid, 0.0)
        c["score"] = s
        out.append(c)
    return out
