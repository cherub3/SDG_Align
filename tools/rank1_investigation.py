"""Step 6: which question lost 'expected document at rank 1' between the baseline and the rebuilt index, and why.

Reads reports/evidence/retrieval_before.json and retrieval_after.json (top-5 per question), then re-embeds the chunks of the
current index with the local adapter to score the passage that used to be rank 1 against the question.
Usage (repo root, needs requirements-local.txt):  HF_HUB_OFFLINE=1 python tools/rank1_investigation.py
"""
import glob
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from scripts.embedding_provider_local import LocalEmbeddingAdapter  # noqa: E402

EV = os.path.join(REPO, "reports", "evidence")


def main():
    b = json.load(open(os.path.join(EV, "retrieval_before.json"), encoding="utf-8"))
    a = json.load(open(os.path.join(EV, "retrieval_after.json"), encoding="utf-8"))
    changed = [x["n"] for x, y in zip(b["results"], a["results"])
               if x["expected_doc"] not in ("any", "NOT INDEXED")
               and (x["top5"][0]["doc"] == x["expected_doc"]) != (y["top5"][0]["doc"] == y["expected_doc"])]
    print("questions whose rank-1 correctness changed:", changed)
    rows = []
    for f in sorted(glob.glob(os.path.join(REPO, "data", "proposals", "chunks", "*", "chunks.json"))):
        rows += json.load(open(f, encoding="utf-8"))["chunks"]
    ad = LocalEmbeddingAdapter()
    for n in changed:
        q = b["results"][n - 1]["question"]
        print(f"\nQ{n}: {q}")
        for name, d in (("BEFORE", b), ("AFTER", a)):
            print(name)
            for t in d["results"][n - 1]["top5"]:
                print(f"  rank {t['rank'] + 1} score {t['score']} {t['doc']} len {t['len']} {t['text'].strip()[:110]!r}")
        old_top = b["results"][n - 1]["top5"][0]["text"]
        probe = old_top.strip()[:60]
        vecs = np.array(ad.embed_batch([q] + [c["text"] for c in rows]))
        scores = vecs[1:] @ vecs[0]
        order = list(np.argsort(-scores))
        print(f"\nThe passage that was rank 1 before starts {probe!r}")
        for pos, i in enumerate(order[:40]):
            t = rows[i]["text"]
            if old_top.strip()[-120:] in t:
                print(f"  in the new index it is part of a chunk of {len(t)} chars, rank {pos + 1}, score {scores[i]:.4f};"
                      f" chunk starts {t.strip()[:150]!r}")
        print(f"  new top-5 scores: {[round(float(scores[i]), 4) for i in order[:5]]};"
              f" spread top1-top5 = {float(scores[order[0]] - scores[order[4]]):.4f}")


if __name__ == "__main__":
    main()
