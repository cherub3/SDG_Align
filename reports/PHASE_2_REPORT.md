# Phase 2 Report: evaluation set and retrieval ladder

Branch `phase-2-eval` (no remote yet; nothing pushed). Every number below comes from a script into `eval/results/`; the ladder is `eval/results/phase2_ladder.{json,md}` (built by `tools/ladder.py`). Labels: VERIFIED = produced by a script or test in this repo; INFERRED = my reading of it; UNKNOWN = not measured.

## 1. Status
- Steps 1, 2, 3a, 3b, 3c, 3d and the Step 5 close-out are done. **Step 4 (query planner) is deliberately skipped** (section 7).
- Kept: dense retrieval over cleaned embed text (3a) plus BM25 hybrid fusion (3b) as the recommended configuration. Not kept: the reranker (3c, off by default) and the abstention gate (3d, an advisory field only, never refuses).
- Library default config (VERIFIED, README and tests): `retrieve()` is **dense-only** unless the request carries `hybrid`. The measured config is `{"rrf_k":10,"w_bm25":2.0,"depth":50}`. `rerank` and `confidence_advisory` are off by default.

## 2. "Done means" check
| Item | Result |
|---|---|
| Frozen gold set, hashes enforced | VERIFIED: 66 items, `eval/GOLD_FROZEN.txt`, refusal tests |
| Seeded dev/test split, test scored once per config | VERIFIED: 14 dev / 52 test, seed 20261123 |
| Each step measured with CIs and paired tests | VERIFIED (section 5) |
| Mutation probe covers the new code | VERIFIED: M22-M35, 14/14 killed (2 needed a new test) |
| Suite stable 3x | VERIFIED: 871 passed x3 |
| Fresh clone passes the CI command | VERIFIED with a caveat (section 4) |
| Docs match behaviour | VERIFIED: README, stage10 doc, test counts |
| Planner measured | NOT DONE (skipped by decision) |

## 3. What changed (commits on `phase-2-eval`)
`945f2ad` gold set, verifier, split, hashes. `f859588` eval harness and baseline. `a465366` hash-refusal tests, diagnostics. `7cdd19f` 3a. `6e1dce9` 3b. `2e275f9` vectorised hybrid (p50 205 to 45 ms, top-50 bit-identical). `14074e8` 3c reranker seam. `e5cb143` 3d abstention measured. `d2a7fbd` advisory field. `f04cad2` mutation probe M22-M35. `e2c482b` ladder, rubric addendum, docs. `9d9471b` fresh-clone fix.

## 4. Tests
- Working tree: 871 passed, three runs in a row. Fresh clone: 870 passed, 1 skipped (the test that needs the real corpus). Coverage in the CI scope is 85.76% against the 80% gate. The "74%" I quoted earlier came from `--cov=tools` only.
- Mutation probe: 14 new mutants (RRF weight, k and depth; BM25 idf and length normalisation; rerank N and order; rerank, hybrid and advisory defaults; advisory threshold and `<` vs `<=`; hit-rule overlap and 50-char cap). First run: 12 killed, **2 survived** (M22 BM25 weight ignored, M23 k hard-coded). A test that pins exact fused scores killed both. Lesson: the old tests checked ordering, not the numbers.
- The fresh clone found a real bug: `tools/gold_common.doc_names()` crashed at collection when the gitignored corpus was absent. Fixed in `9d9471b`.
- Caveat: the clone used the existing venv (`pip check` is clean), not a brand-new `pip install` of the CI requirements, because that needs the network and I had not been cleared to use it. The first GitHub Actions run, once a remote exists, is the true check.

## 5. Measured results (test split, 44 answerable items, 95% bootstrap CIs)
| config | R@1 | R@5 | R@10 | MRR@10 | latency p50 / p95 ms |
|---|---|---|---|---|---|
| baseline | 0.32 [0.18,0.45] | 0.57 [0.41,0.70] | 0.59 [0.43,0.73] | 0.42 [0.29,0.55] | 86.6 / 116.9 |
| 3a embed-text cleanup | 0.34 [0.20,0.48] | 0.57 [0.43,0.70] | 0.66 [0.52,0.80] | 0.43 [0.31,0.56] | 41.4 / 73.4 |
| 3b BM25 hybrid (rrf_k=10, w_bm25=2) | 0.39 [0.25,0.52] | 0.77 [0.64,0.89] | 0.89 [0.77,0.98] | 0.55 [0.43,0.66] | 45.4 / 76.9 |
| 3c + MiniLM rerank N=20 (off by default) | 0.55 [0.41,0.68] | 0.68 [0.55,0.82] | 0.86 [0.75,0.95] | 0.62 [0.50,0.75] | 3182.6 / 3306.9 |
| 3d advisory on 3b | same as 3b | same | same | same | 53.9 / 85.6 |

Paired tests (exact McNemar on R@5, Wilcoxon on reciprocal rank):
- 3a vs baseline: R@5 +0.000 (1 better / 1 worse, p=1.0), R@10 +0.068 (3/0, p=0.25), MRR +0.015 (p=0.48). Not significant.
- **3b vs 3a: R@5 +0.204 [+0.091,+0.318] (9/0, p=0.0039); R@10 +0.227 (10/0, p=0.002); MRR +0.113 [+0.017,+0.215] (p=0.021).** The only clearly significant gain. It comes from adding BM25. Default fusion (k=60, equal weights) gives R@5 0.75 and MRR 0.54, one question apart (p=1.0 and 0.68), so the tuning is not what matters.
- 3c vs 3b: R@1 +0.159 (9/2, p=0.065), R@5 -0.091 (0/4, p=0.125), MRR +0.075 [-0.016,+0.174] (p=0.205). Nothing is significant. It is better at rank 1 and worse at rank 5, and hurts multi_passage questions (R@5 0.875 to 0.625). It fails the rule "keep only if it helps or is neutral and simpler": a 90 MB model, torch at query time, about 70x latency. Worse items: R@5 Q011, Q019, Q035, Q042; R@10 Q025.
- 3d vs 3b: no change by design.

3d abstention (rule fixed before computing: threshold = the largest value where dev answerable items false-refuse at most 10%, giving 0.6604). On test: false refusal 5/44 = 11.4% [2.3,20.5]; near_miss refused 2/4; off_corpus refused 2/4 (CIs 0-100%). Refusing all off-corpus items needs t=0.7481 and a 38.6% false-refusal rate. AUROC answerable vs unanswerable: dense cosine 0.82; reranker top-1 0.77 (off_corpus 0.93, near_miss 0.61). **Verdict: cosine cannot separate off-corpus from answerable questions, so it is not kept as a refusal gate.** Abstention moves to the answer stage (an LLM "not in context" check) in the deploy phase.

Latency caveat: the numbers come from separate runs under different machine load. Baseline 86.6 vs 3a 41.4 ms is not a real speedup (the dense path is unchanged) and the means include cold-start loading.

## 6. Cost, resources, network
- No paid or quota-limited API was called. No secrets were read.
- **Slip, disclosed:** one Q3 re-score ran without `HF_HUB_OFFLINE=1` and sent unauthenticated HEAD requests (metadata only) to huggingface.co. Offline flags (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`) have been set on every run since.
- **Reranker download (once, approved 2026-11-23):** `cross-encoder/ms-marco-MiniLM-L-6-v2`, revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`, `model.safetensors` 90,870,598 bytes (about 91 MB), sha256 `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae`, licence Apache-2.0, source https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2. Connection resets forced several retries. It is pinned in `config/rerank_model.json`. `bge-reranker-base` was not downloaded.
- Dev scores were printed before `tools/abstain.py` ran. The rule is mechanical, so that could not have changed the threshold.
- Compute is CPU only; the embedder pins torch to 1 thread. Standalone rerank benchmark, 20 passages: 3041 ms at 1 thread, 1240 ms at 4. End-to-end multi-thread was never measured.

## 7. Open issues
1. **Small n.** Test has 44 answerable and 8 unanswerable items. CIs are wide and most deltas are not significant. The unanswerable subgroups have n=4.
2. **AI-drafted gold set.** Drafted and reviewed by sub-agents of my own model family, not independent human labels.
3. **Flat 12-item dev.** Many grid cells tie, so the dev picks (rrf_k=10, w_bm25=2, N=20, t=0.6604) are weakly supported. Dev has only 2 unanswerable items, so none were used for tuning.
4. **Near-miss abstention is unsolved.** Retrieval cannot tell "on topic but not stated" from an answer. It needs the answer-level check.
5. **Torch thread pinning.** The embedder resets torch to 1 thread, so rerank latency with more threads is unmeasured end to end.
6. **Ecuador source contradiction.** p26 says MAE leads execution, p30 says GGGI. Q005 and Q037 were dropped. This is a candidate future "conflicting sources" test.
7. **Planner unmeasured.** Step 4 was skipped: it needs an LLM, and free-tier quota would make results depend on availability. It will be measured end to end with answer quality on Vertex AI Gemini in the deploy phase.
8. The template-opener list was read from the same 6 documents it is measured on.
9. The rubric fixes from Phase 1 judge disagreements are written as proposals in `reports/evidence/metrics_definitions_addendum_phase2.md`. They are **not re-validated and not applied retroactively**. `metrics_definitions.md` stays frozen.

## 8. Doc/claim updates and deviations
- README: stale "no gold set / unmeasured" lines replaced, default-config statement added, test count 813 to 871 (also in `OPERATIONAL_READINESS.md`). `docs/architecture/stage10_retrieval.md` documents `hybrid`, `rerank` and `confidence_advisory`.
- Gold set: planned 70, delivered 66 (Q005, Q037, Q041, Q054 dropped).
- 3b selection used a rule fixed beforehand (max dev MRR@10, tie R@10, tie closest to defaults), not a "default unless at least 2 questions better" guard.
- 3d is an advisory field (`low_confidence`, `dense_score`), off by default, by decision. Step 4 was skipped by decision.

## 9. Resume-safe facts
- Built a gold-set evaluation harness (66 items frozen by hash, seeded dev/test split, test scored once per config) over a RAG pipeline of GEF/UNDP documents.
- Hybrid BM25 plus dense retrieval with reciprocal rank fusion raised test Recall@5 from 0.57 to 0.77 (paired gain 95% CI [+0.09,+0.32], exact McNemar p=0.004, n=44).
- Evaluated a cross-encoder reranker and a similarity-threshold abstention gate with paired tests, and rejected both when they missed pre-stated keep rules (reranker: +0.16 R@1 but -0.09 R@5, not significant, about 70x latency).
- Ran a mutation probe (35 mutants) alongside 871 tests at 86% coverage. The Phase 2 additions went from 12/14 killed to 14/14 after one added test.
- Do NOT claim: a significant gain from tuning, a working abstention, a measured planner, or human-labelled ground truth.

## 10. Kept out of repository
`LEARN_*.md` and `PHASE_*_PROGRESS.md` (gitignored, local); corpus data under `data/`; model weights (HF cache); no secrets.

## 11. Next phase preview
Deploy phase on GCP: Vertex AI Gemini for generation, answer-level "not in context" abstention (measured), the query planner measured end to end with answer quality, and an answer-quality eval. When the GitHub URL arrives: add the remote, push `phase-0-foundation`, `phase-1-chunk-quality` and `phase-2-eval`, and confirm a real Actions run passes.
