import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import eval_retrieval as ev  # noqa: E402


def item(spans, typ="multi_passage"):
    return {"type": typ, "evidence": [{"doc_id": d, "clean_start": s, "clean_end": e} for d, s, e in spans]}


def test_hit_at_rank_and_wrong_doc_does_not_count():
    it = item([("A", 100, 200)], "single_fact")
    r = ev.score_item(it, [("B", 100, 200), ("A", 0, 50), ("A", 90, 210)])
    assert r["first_hit_rank"] == 3 and r["recall@1"] == 0 and r["recall@5"] == 1 and abs(r["mrr@10"] - 1 / 3) < 1e-9


def test_all_spans_and_ndcg_perfect():
    it = item([("A", 0, 100), ("A", 500, 600)])
    r = ev.score_item(it, [("A", 0, 100), ("A", 500, 600)])
    assert r["all_spans@10"] == 1.0 and abs(r["ndcg@10"] - 1.0) < 1e-9
    r2 = ev.score_item(it, [("A", 0, 100), ("A", 10, 90)])   # second chunk covers nothing new
    assert r2["all_spans@10"] == 0.0 and r2["ndcg@10"] < 1.0


def test_threshold_boundary():
    it = item([("A", 0, 200)], "single_fact")
    assert ev.score_item(it, [("A", 150, 400)])["recall@1"] == 1.0      # 50 chars overlap
    assert ev.score_item(it, [("A", 151, 400)])["recall@1"] == 0.0      # 49
