"""POST HOC paired statistics for the Phase 4 arms (A: single call, template 2.1.0; B: ADK multi-agent). Not pre-registered.

Reads only existing row files; makes no model call. Uses the project's own metric function (tools/eval_agents.arm_metrics) one item at a time,
so the flags are identical to those behind eval/results/test_agents_v1_summary.json.

    python tools/phase4_posthoc.py            # writes eval/results/phase4_mcnemar_posthoc.json
"""
import json
import os
import sys

import numpy as np
from scipy.stats import binomtest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)

RESULTS = os.path.join(REPO, "eval", "results")
OUT = os.path.join(RESULTS, "phase4_mcnemar_posthoc.json")
ROWS_A, ROWS_B = "test_noplanner_v21.jsonl", "test_agents_v1.jsonl"
BOOT, SEED = 10000, 1


def item_flags():
    """Per item: type, refused (decision NOT_IN_CONTEXT, answerable only), wrong (automatic proxy), for arms A and B."""
    import eval_agents as e
    ea = e.ea
    items = {i["qid"]: i for i in ea.load_items("test")}
    spans, texts = e.chunk_index()
    a_rows = {r["qid"]: r for r in ea.read_rows(os.path.join(RESULTS, ROWS_A))}
    b_rows = {r["qid"]: r for r in ea.read_rows(os.path.join(RESULTS, ROWS_B))}
    assert set(a_rows) == set(items) == set(b_rows), "both arms must cover the 52 TEST items"
    out = []
    for q in sorted(items):
        it = items[q]
        ma = e.arm_metrics([a_rows[q]], items, texts, spans, "A")
        mb = e.arm_metrics([b_rows[q]], items, texts, spans, "B")
        out.append({"qid": q, "type": it["type"], "answerable": it["type"] != "unanswerable",
                    "refused_A": bool(ma["false_refusals_answerable"] + ma["refusals_unanswerable"]),
                    "refused_B": bool(mb["false_refusals_answerable"] + mb["refusals_unanswerable"]),
                    "wrong_A": bool(ma["wrong_answers_automatic"]), "wrong_B": bool(mb["wrong_answers_automatic"])})
    return out


def mcnemar(a, b):
    """a, b: parallel boolean lists (event in A, event in B). Exact two-sided McNemar on the discordant pairs."""
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    both, only_a, only_b, neither = int((a & b).sum()), int((a & ~b).sum()), int((~a & b).sum()), int((~a & ~b).sum())
    d = only_a + only_b
    p = float(binomtest(min(only_a, only_b), d, 0.5).pvalue) if d else 1.0
    rng = np.random.default_rng(SEED)
    n = len(a)
    idx = rng.integers(0, n, size=(BOOT, n))
    diffs = b[idx].mean(axis=1) - a[idx].mean(axis=1)
    return {"n": n, "table": {"both": both, "only_A": only_a, "only_B": only_b, "neither": neither},
            "events_A": int(a.sum()), "events_B": int(b.sum()), "discordant": d,
            "difference_B_minus_A": round(float(b.mean() - a.mean()), 4),
            "ci95_paired_bootstrap": [round(float(np.percentile(diffs, 2.5)), 4), round(float(np.percentile(diffs, 97.5)), 4)],
            "mcnemar_exact_p": round(p, 4)}


def compute():
    f = item_flags()
    ans = [x for x in f if x["answerable"]]
    res = {
        "status": "POST HOC. Not pre-registered. TEST has been used for two abstention templates, one planner arm and this agent arm; no correction for multiple use.",
        "arms": {"A": ROWS_A, "B": ROWS_B},
        "method": "exact McNemar on discordant pairs (scipy binomtest, two-sided); CI = percentile bootstrap of the paired difference, 10000 resamples, seed 1 (as tools/compare_arms.py)",
        "false_refusal_answerable_44": mcnemar([x["refused_A"] for x in ans], [x["refused_B"] for x in ans]),
        "automatic_wrong_all_52": mcnemar([x["wrong_A"] for x in f], [x["wrong_B"] for x in f]),
        "automatic_wrong_answerable_44": mcnemar([x["wrong_A"] for x in ans], [x["wrong_B"] for x in ans]),
        "note": "'wrong' is the automatic proxy (tools/answer_checks.py), not a correctness label. Nothing here is a human or AI correctness label for arm B.",
    }
    return res, f


if __name__ == "__main__":
    res, flags = compute()
    json.dump(res, open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1))
