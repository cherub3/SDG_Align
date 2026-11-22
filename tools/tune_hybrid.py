"""Tune the hybrid fusion on the DEV split only. Usage: python tools/tune_hybrid.py --out eval/results/3b_dev_grid.json

Grid: rrf_k x w_bm25 (dense weight fixed at 1) x depth. Selection rule, fixed before looking at any result:
highest dev MRR@10; ties broken by dev Recall@10, then by distance from the defaults (rrf_k=60, w_bm25=1, depth=50).
The test split is never touched here (evaluate('dev', ...) only).
"""
import argparse
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_retrieval as ev  # noqa: E402

RRF_K = (10, 30, 60)
W_BM25 = (0.5, 1.0, 2.0)
DEPTH = (20, 50, 100)
DEFAULT = (60, 1.0, 50)


def pick(rows):
    def key(r):
        d = (abs(RRF_K.index(r["rrf_k"]) - RRF_K.index(DEFAULT[0])) + abs(W_BM25.index(r["w_bm25"]) - W_BM25.index(DEFAULT[1]))
             + abs(DEPTH.index(r["depth"]) - DEPTH.index(DEFAULT[2])))
        return (-r["mrr@10"], -r["recall@10"], d)
    return sorted(rows, key=key)[0]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for k, w, d in itertools.product(RRF_K, W_BM25, DEPTH):
        params = {"rrf_k": k, "w_bm25": w, "depth": d}
        res = ev.evaluate("dev", ev.build_retriever(hybrid=params), f"dev rrf_k={k} w={w} depth={d}")
        s = res["summary"]["ALL answerable"]
        rows.append({**params, "recall@1": s["recall@1"][0], "recall@5": s["recall@5"][0], "recall@10": s["recall@10"][0],
                     "mrr@10": s["mrr@10"][0], "ndcg@10": s["ndcg@10"][0], "n": s["n"]})
        print(rows[-1], flush=True)
    best = pick(rows)
    json.dump({"split": "dev", "selection_rule": "max dev MRR@10, tie: dev R@10, tie: closest to defaults", "grid": rows, "chosen": best},
              open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print("CHOSEN", best)
