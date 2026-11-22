"""Tune the reranker's candidate depth N on the DEV split only. Usage: python tools/tune_rerank.py --out eval/results/3c_dev_grid.json

Grid: N in {20, 30, 50} fused candidates handed to the cross-encoder, on top of the CHOSEN 3b fusion (rrf_k=10, w_bm25=2, depth=50).
Selection rule, stated before any result was looked at (user instruction, 3c):
    highest dev MRR@10; if tied, the SMALLER N (it is cheaper: rerank latency grows with N).
The test split is never touched here (evaluate('dev', ...) only). A no-rerank reference row is run for context and is NOT a candidate.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_retrieval as ev  # noqa: E402

FUSION = {"rrf_k": 10, "w_bm25": 2.0, "depth": 50}      # 3b's dev-selected setting, fixed
N_GRID = (20, 30, 50)


def pick(rows):
    return sorted(rows, key=lambda r: (-r["mrr@10"], r["n_rerank"]))[0]


def row(res, n):
    s = res["summary"]["ALL answerable"]
    return {"n_rerank": n, **{m: s[m][0] for m in ("recall@1", "recall@5", "recall@10", "mrr@10", "ndcg@10")}, "n": s["n"],
            "latency_ms_p50": res["latency_ms_per_query"]["p50"], "latency_ms_p95": res["latency_ms_per_query"]["p95"],
            "rerank_ms_p50": (res["latency_ms_rerank_only"] or {}).get("p50")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ref = row(ev.evaluate("dev", ev.build_retriever(hybrid=FUSION), "dev 3b reference (no rerank)"), 0)
    print("REFERENCE", ref, flush=True)
    rows = []
    for n in N_GRID:
        rows.append(row(ev.evaluate("dev", ev.build_retriever(hybrid=FUSION, rerank={"n": n}), f"dev rerank n={n}"), n))
        print(rows[-1], flush=True)
    best = pick(rows)
    json.dump({"split": "dev", "fusion": FUSION, "selection_rule": "max dev MRR@10; tie: smaller N", "reference_no_rerank": ref,
               "grid": rows, "chosen": best}, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    print("CHOSEN", best)
