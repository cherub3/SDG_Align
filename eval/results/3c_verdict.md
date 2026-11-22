# Step 3c verdict: cross-encoder reranker (MiniLM-L-6-v2, N=20) is implemented, tested, OFF by default

Decision (user, 2026-11-23): keep the code and tests, flag off by default, do NOT download bge-reranker-base.

Reasons (numbers in 3c_test.json, 3c_diagnostics.json):
- R@1 up (0.386 -> 0.545, 9 better / 2 worse, McNemar p=0.065) but R@5 down (0.773 -> 0.682, 0 better / 4 worse) and R@10 down; nothing significant at 0.05.
- multi_passage got worse (R@1 0.50 -> 0.375, R@5 0.875 -> 0.625): a pointwise scorer judges each passage alone, so it cannot reward a set of passages that together answer the question.
- 3.2 s per query on 1 CPU thread (45 ms -> 3183 ms), about 70x.
- Domain mismatch: MS MARCO is short web passages vs. long (~1230 chars) project-document chunks with tables.

OPEN ISSUE (thread pinning): the local embedder calls torch.set_num_threads(1) for determinism, which also pins the reranker.
A standalone benchmark (tools/bench_rerank_threads.py) gives 3041 ms (1 thread) vs 1240 ms (4 threads) for 20 passages with scores identical to ~1e-6,
but the end-to-end harness never ran multi-threaded. Not resolved; do not quote a multi-thread end-to-end latency.
