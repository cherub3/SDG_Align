"""Step 3c diagnostics: where the reranker helped and hurt, and whether its scores separate answerable from unanswerable
questions better than the dense cosine (input for 3d). Reads result files only; runs no retrieval.

Usage: python tools/diag_rerank.py            -> eval/results/3c_diagnostics.json (+ printed summary)

Separation numbers are DESCRIPTIVE. Nothing here selects a threshold; 3d must pick its rule on dev only.
"""
import json
import os
import sys

import numpy as np
from scipy.stats import binomtest

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eval", "results")
J = lambda n: json.load(open(os.path.join(R, n), encoding="utf-8"))  # noqa: E731


def auroc(pos, neg):
    """P(a random answerable item scores higher than a random unanswerable one); ties count half. 0.5 = no separation."""
    if not pos or not neg:
        return None
    w = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(w / (len(pos) * len(neg)), 3)


def stats(v):
    return {"n": len(v), "min": round(min(v), 3), "median": round(float(np.median(v)), 3), "max": round(max(v), 3)} if v else None


def per_type(a, b):
    ia = {r["qid"]: r for r in a["items"] if r["type"] != "unanswerable"}
    ib = {r["qid"]: r for r in b["items"] if r["type"] != "unanswerable"}
    groups = {"ALL": list(ia)}
    for q, r in ia.items():
        groups.setdefault("type=" + r["type"], []).append(q)
        groups.setdefault("paraphrased" if r["paraphrased"] else "not paraphrased", []).append(q)
    out = {}
    for g, qs in groups.items():
        row = {"n": len(qs)}
        for m in ("recall@1", "recall@5", "recall@10"):
            up = sum(ib[q][m] > ia[q][m] for q in qs)
            dn = sum(ib[q][m] < ia[q][m] for q in qs)
            row[m] = {"A": round(float(np.mean([ia[q][m] for q in qs])), 3), "B": round(float(np.mean([ib[q][m] for q in qs])), 3),
                      "better": up, "worse": dn}
            if g == "ALL":
                row[m]["mcnemar_exact_p"] = round(float(binomtest(up, up + dn, 0.5).pvalue), 4) if up + dn else 1.0
        row["mean_delta_RR"] = round(float(np.mean([ib[q]["mrr@10"] - ia[q]["mrr@10"] for q in qs])), 3)
        out[g] = row
    return out


def worse_items(a, b, metric):
    ia = {r["qid"]: r for r in a["items"] if r["type"] != "unanswerable"}
    ib = {r["qid"]: r for r in b["items"] if r["type"] != "unanswerable"}
    return [{"qid": q, "type": ia[q]["type"], "first_hit_rank_A": ia[q]["first_hit_rank"], "first_hit_rank_B": ib[q]["first_hit_rank"]}
            for q in sorted(ia) if ib[q][metric] < ia[q][metric]]


def separation(dense_items, rerank_items):
    """Top-1 dense cosine (3a run) vs top-1 reranker logit and top1-top2 reranker margin (3c run), per item."""
    d = {r["qid"]: r for r in dense_items}
    out = {"dense_cosine_top1": ([], []), "rerank_top1": ([], []), "rerank_margin_top1_minus_top2": ([], [])}
    kinds = {"near_miss": {k: [] for k in out}, "off_corpus": {k: [] for k in out}}
    for r in rerank_items:
        un = r["type"] == "unanswerable"
        vals = {"dense_cosine_top1": d[r["qid"]]["top1_score"], "rerank_top1": r["top1_score"],
                "rerank_margin_top1_minus_top2": r["top_scores"][0] - r["top_scores"][1] if len(r["top_scores"]) > 1 else None}
        for k, v in vals.items():
            if v is None:
                continue
            out[k][1 if un else 0].append(v)
            if un:
                kinds[r["kind"]][k].append(v)
    return {k: {"answerable": stats(p), "unanswerable": stats(n), "AUROC": auroc(p, n),
                "near_miss": stats(kinds["near_miss"][k]), "off_corpus": stats(kinds["off_corpus"][k]),
                "AUROC_near_miss_only": auroc(p, kinds["near_miss"][k]), "AUROC_off_corpus_only": auroc(p, kinds["off_corpus"][k])}
            for k, (p, n) in out.items()}


if __name__ == "__main__":
    a, b = J("3b_test_fast.json"), J("3c_test.json")
    res = {"compared": "3c (hybrid + rerank n=20) vs 3b (hybrid), test split, same 44 answerable items",
           "by_group": per_type(a, b), "worse_at_recall@5": worse_items(a, b, "recall@5"), "worse_at_recall@1": worse_items(a, b, "recall@1"),
           "worse_at_recall@10": worse_items(a, b, "recall@10"),
           "separation_test": separation(J("3a_test_fast.json")["items"], b["items"]),
           "separation_dev": separation(J("3a_dev_merged+template.json")["items"], J("3c_dev_n20.json")["items"]),
           "separation_pooled_dev_plus_test_DESCRIPTIVE_ONLY": separation(J("3a_test_fast.json")["items"] + J("3a_dev_merged+template.json")["items"],
                                                                        b["items"] + J("3c_dev_n20.json")["items"])}
    json.dump(res, open(os.path.join(R, "3c_diagnostics.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(res, indent=1))
