"""Reranker latency vs CPU threads, standalone (no embedder, no retrieval). Latency only: it reads no gold set and selects nothing.
Usage: python tools/bench_rerank_threads.py   -> eval/results/3c_latency_threads.json
Why it exists: the eval harness runs the reranker after the local embedder, and the embedder pins torch to 1 thread
(determinism), so the end-to-end 3c numbers are single-thread numbers. This shows what the cost would be with more threads,
and that the scores do not change.
"""
import glob
import json
import os
import sys
import time

import torch

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO)
os.chdir(REPO)
from scripts.reranker import CrossEncoderReranker  # noqa: E402
from scripts.stage8_embedding_generation import embedding_text  # noqa: E402

chunks = [c for p in sorted(glob.glob("data/proposals/chunks/*/chunks.json")) for c in json.load(open(p, encoding="utf-8"))["chunks"]]
passages = [embedding_text(c) for c in chunks[:200:10]]            # 20 real chunks, a fixed deterministic sample
q = "what is the total budget of the project"
rows, ref = [], None
for th in (1, 2, 4, 8):
    ad = CrossEncoderReranker(num_threads=th)
    ad.score(q, ["warm up"])
    torch.set_num_threads(th)
    ts = []
    for _ in range(3):
        t = time.perf_counter()
        s = ad.score(q, passages)
        ts.append((time.perf_counter() - t) * 1000)
    ref = ref or s
    rows.append({"threads": th, "ms_for_20_passages_median_of_3": round(sorted(ts)[1]), "max_abs_score_diff_vs_1_thread": max(abs(a - b) for a, b in zip(s, ref))})
    print(rows[-1], flush=True)
json.dump({"passages": len(passages), "mean_chars": sum(map(len, passages)) // len(passages), "logical_cores": os.cpu_count(), "rows": rows},
          open("eval/results/3c_latency_threads.json", "w", encoding="utf-8", newline="\n"), indent=1)
