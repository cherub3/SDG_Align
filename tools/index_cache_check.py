"""Fix 7 proof: the in-memory FAISS index cache changes speed, not results.

For every query of the chosen split(s) it runs the served retrieval (hybrid, rrf_k=10, w_bm25=2, depth=50) with the cache
OFF (the old behaviour: index.bin read from disk on every query) and ON, with top_k=50, and requires the two ranked lists
(chunk_id and score) to be identical. It then times both configurations in alternating passes so machine load affects both
equally. Needs the local corpus, index and embedding model (offline). Does not call git or any network.

Usage: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python tools/index_cache_check.py [--splits test dev] [--passes 5]
Writes reports/evidence/index_cache_check.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import eval_retrieval as ev  # noqa: E402


def main(splits, passes):
    from scripts import stage10_retrieval as s10
    from scripts.pipeline_deps_factory import SERVED_HYBRID_PARAMS
    run = ev.build_retriever(top_k=50, hybrid=dict(SERVED_HYBRID_PARAMS))     # chdirs to the repo root
    queries = [(it["qid"], s, it["question"]) for s in splits for it in ev.load_items(s)]

    def ranked(q):
        run(q)
        return [(r["chunk_id"], r["score"]) for r in run.last["results"]]

    s10.INDEX_CACHE_ENABLED = False
    off = {qid: ranked(q) for qid, _, q in queries}                           # also warms the model, BM25 and chunk caches
    s10.INDEX_CACHE_ENABLED = True
    on = {qid: ranked(q) for qid, _, q in queries}
    mismatches = [qid for qid in off if off[qid] != on[qid]]
    lens = sorted({len(v) for v in off.values()})

    lat = {"off": {sp: [] for sp in splits}, "on": {sp: [] for sp in splits}}
    for _ in range(passes):
        for mode in ("off", "on"):
            s10.INDEX_CACHE_ENABLED = mode == "on"
            for qid, sp, q in queries:
                t = time.perf_counter()
                run(q)
                lat[mode][sp].append((time.perf_counter() - t) * 1000)
    s10.INDEX_CACHE_ENABLED = True

    def stats(x):
        return {"n": len(x), "p50_ms": round(float(np.percentile(x, 50)), 1), "p95_ms": round(float(np.percentile(x, 95)), 1),
                "mean_ms": round(float(np.mean(x)), 1)}
    out = {"queries": len(queries), "splits": splits, "top_k": 50, "list_lengths_seen": lens, "passes": passes,
           "identical_top50_for_every_query": not mismatches, "mismatching_qids": mismatches,
           "latency_ms": {m: {**{sp: stats(v) for sp, v in lat[m].items()}, "all": stats(sum(lat[m].values(), []))} for m in lat},
           "note": "OFF = index.bin deserialised from disk on every query (old behaviour); ON = cached in memory. Alternating passes, same process, "
                   "embedding model already loaded, so this is query-time retrieval latency only (cold start excluded)."}
    path = os.path.join(REPO, "reports", "evidence", "index_cache_check.json")
    json.dump(out, open(path, "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(out, indent=1))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", nargs="+", default=["test", "dev"])
    ap.add_argument("--passes", type=int, default=5)
    a = ap.parse_args()
    sys.exit(main(a.splits, a.passes))
