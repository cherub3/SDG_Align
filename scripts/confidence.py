"""Advisory retrieval-confidence flag, step 3d. NEVER refuses and never changes the results; OFF unless the request asks.

Verdict (eval/results/3d_abstention.json): the top-1 dense cosine cannot separate unanswerable from answerable questions
(threshold 0.6604 picked on dev answerable items only: 11.4% false refusal on test, 50% of off-corpus and 50% of near-miss
questions flagged; flagging every off-corpus question would need 38.6% false flags). So this is a hint for a human or for
the answer stage, not a gate. Real abstention is an answer-level "not in context" check, built in the deploy phase.
"""
from typing import Any, Dict, List, Optional

DEFAULT_THRESHOLD = 0.6604          # dev-answerable rule: largest t with <=10% dev false refusal (tools/abstain.py)


def top1_dense_score(results: List[Dict[str, Any]]) -> Optional[float]:
    """Cosine of the top-1 chunk: `dense_score` (hybrid), else `fused_score` (dense + rerank), else `score` (dense only)."""
    if not results:
        return None
    r = results[0]
    for key in ("dense_score", "fused_score", "score"):
        if key in r:
            return float(r[key])
    return None


def confidence_advisory(results: List[Dict[str, Any]], threshold: Optional[float] = None) -> Dict[str, Any]:
    t = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    s = top1_dense_score(results)
    return {"dense_score": s, "threshold": t, "low_confidence": s is None or s < t, "advisory_only": True}
