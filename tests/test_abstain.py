"""Step 3d abstention rule: threshold selection and application (no model, no retrieval)."""
import numpy as np

from tools import abstain as ab


def test_threshold_is_largest_with_at_most_ten_percent_false_refusal_on_answerable():
    s = [0.9, 0.5, 0.7, 0.6, 0.8, 0.95, 0.85, 0.75, 0.65, 0.55, 0.92, 0.88]      # 12 items -> at most 1 refused
    t = ab.pick_threshold(s)
    assert t == sorted(s)[1] and sum(x < t for x in s) == 1                      # second-smallest score; only the smallest is refused


def test_threshold_with_fewer_than_ten_items_refuses_none():
    assert ab.pick_threshold([0.5, 0.6, 0.7]) == 0.5                              # floor(0.3)=0 -> smallest score, nothing < it


def test_apply_counts_refusals_by_kind_and_scores_the_answered_subset():
    mk = lambda q, ty, d, r5=1.0, kind=None: {"qid": q, "type": ty, "kind": kind, "recall@5": r5, "top1_scores": {"dense_score": d}}  # noqa: E731
    items = [mk("a", "single_fact", 0.9), mk("b", "single_fact", 0.5, 0.0), mk("n", "unanswerable", 0.4, kind="near_miss"),
             mk("o", "unanswerable", 0.95, kind="off_corpus")]
    r = ab.apply(items, 0.6, np.random.default_rng(1))
    assert r["false_refusal_answerable"]["k"] == 1 and r["refusal_near_miss"]["k"] == 1 and r["refusal_off_corpus"]["k"] == 0
    assert r["recall@5_answered_subset"]["n"] == 1 and r["recall@5_answered_subset"]["value"] == 1.0
    assert [x["qid"] for x in r["unanswerable_answered_anyway"]] == ["o"]
