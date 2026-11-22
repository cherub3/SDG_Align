"""Dump the top-N (chunk span + score) for every dev+test question, to prove a refactor did not change results.
Usage: python tools/dump_topn.py --out FILE [--hybrid JSON] [--n 50]. Offline flags must be set by the caller."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_retrieval as ev  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--hybrid")
    ap.add_argument("--n", type=int, default=50)
    a = ap.parse_args()
    retr = ev.build_retriever(top_k=a.n, hybrid=json.loads(a.hybrid) if a.hybrid else None)
    out = {}
    for split in ("dev", "test"):
        for it in ev.load_items(split):
            out[it["qid"]] = [[d, s, e, repr(float(sc))] for d, s, e, sc in retr(it["question"])]
    json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"))
    print(len(out), "questions dumped")
