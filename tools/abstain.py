"""Step 3d: score-threshold abstention on the 3b pipeline (hybrid, no rerank), using the dense cosine of the top-1 result.

RULE (stated before it was computed, from the user's instruction):
  refuse a query iff dense_score(top-1) < t.
  t = the LARGEST threshold for which the DEV ANSWERABLE items (12) false-refuse at most 10% (<=1 of 12).
  The 2 dev unanswerable items are NOT used for tuning (far too few). No margin rule: a single score is simpler.
Measured once on test. The threshold-vs-refusal curve is DESCRIPTIVE ONLY (not used for selection).
Usage: python tools/abstain.py -> eval/results/3d_abstention.json
"""
import json
import math
import os

import numpy as np

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eval", "results")
J = lambda n: json.load(open(os.path.join(R, n), encoding="utf-8"))  # noqa: E731
MAX_FALSE_REFUSAL = 0.10
BOOT, SEED = 10000, 1


def pick_threshold(answerable_scores, max_fr=MAX_FALSE_REFUSAL):
    """Largest t with #(s < t)/n <= max_fr. Refuse is strict '<', so t equals the (k+1)-th smallest score, k=floor(max_fr*n)."""
    s = sorted(answerable_scores)
    k = math.floor(max_fr * len(s) + 1e-9)
    return s[k]


def ci(x, rng):
    x = np.asarray(x, float)
    if len(x) == 0:
        return None
    m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(BOOT)]
    return [round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)]


def rate(flags, rng):
    return {"n": len(flags), "k": int(sum(flags)), "rate": round(float(np.mean(flags)), 3) if flags else None, "ci95": ci(flags, rng)}


def apply(items, t, rng):
    s = lambda r: r["top1_scores"]["dense_score"]  # noqa: E731
    ans = [r for r in items if r["type"] != "unanswerable"]
    un = [r for r in items if r["type"] == "unanswerable"]
    answered = [r for r in ans if s(r) >= t]
    out = {"threshold": t, "false_refusal_answerable": rate([s(r) < t for r in ans], rng),
           "refusal_unanswerable_all": rate([s(r) < t for r in un], rng),
           "refusal_near_miss": rate([s(r) < t for r in un if r["kind"] == "near_miss"], rng),
           "refusal_off_corpus": rate([s(r) < t for r in un if r["kind"] == "off_corpus"], rng),
           "recall@5_all_answerable": round(float(np.mean([r["recall@5"] for r in ans])), 3),
           "recall@5_answered_subset": {"n": len(answered), "value": round(float(np.mean([r["recall@5"] for r in answered])), 3),
                                        "ci95": ci([r["recall@5"] for r in answered], rng)},
           "unanswerable_answered_anyway": [{"qid": r["qid"], "kind": r["kind"], "dense": s(r)} for r in un if s(r) >= t]}
    return out


def curve(items):
    s = lambda r: r["top1_scores"]["dense_score"]  # noqa: E731
    ans = [s(r) for r in items if r["type"] != "unanswerable"]
    nm = [s(r) for r in items if r["type"] == "unanswerable" and r["kind"] == "near_miss"]
    oc = [s(r) for r in items if r["type"] == "unanswerable" and r["kind"] == "off_corpus"]
    ts = sorted(set(round(v, 4) for v in ans + nm + oc))
    f = lambda v, t: round(float(np.mean([x < t for x in v])), 3)  # noqa: E731
    return [{"t": t, "false_refusal": f(ans, t), "refuse_near_miss": f(nm, t), "refuse_off_corpus": f(oc, t)} for t in ts]


if __name__ == "__main__":
    dev, test = J("3d_dev_hybrid.json")["items"], J("3d_test_hybrid.json")["items"]
    dev_ans = [r["top1_scores"]["dense_score"] for r in dev if r["type"] != "unanswerable"]
    t = pick_threshold(dev_ans)
    rng = np.random.default_rng(SEED)
    res = {"rule": __doc__.split("RULE")[1].split("Measured")[0].strip(), "dev_answerable_n": len(dev_ans),
           "dev_answerable_scores_sorted": sorted(dev_ans), "threshold": t,
           "dev_check": apply(dev, t, np.random.default_rng(SEED)), "test": apply(test, t, rng),
           "test_curve_DESCRIPTIVE_ONLY_not_used_for_selection": curve(test),
           "test_score_summary": {"answerable": sorted(r["top1_scores"]["dense_score"] for r in test if r["type"] != "unanswerable"),
                                  "near_miss": sorted(r["top1_scores"]["dense_score"] for r in test if r.get("kind") == "near_miss"),
                                  "off_corpus": sorted(r["top1_scores"]["dense_score"] for r in test if r.get("kind") == "off_corpus")}}
    json.dump(res, open(os.path.join(R, "3d_abstention.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "test_curve_DESCRIPTIVE_ONLY_not_used_for_selection"}, indent=1))
