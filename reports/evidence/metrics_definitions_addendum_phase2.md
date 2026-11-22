# Addendum to the Phase 1 metric definitions (written in Phase 2)

`metrics_definitions.md` stays frozen and unedited: it was frozen before any measurement and the Phase 1 numbers were produced under it.
This addendum is the place for (A) rubric clarifications for FUTURE judging, taken from where the Phase 1 judges disagreed, and (B) the Phase 2 retrieval metrics.
Nothing in (A) was applied retroactively; Phase 1 results are unchanged.

## A. Usefulness rubric: clarifications for future judging

Phase 1 evidence: Judge 1 (frozen) vs Judge 2, 124 answerable items, 111 exact agreements (89.5%), kappa 0.843; 13 disagreements went to Judge 3
(`PHASE_1_REPORT.md` section 5, "Judge reliability"). The confusion matrix (rows Judge 1, columns Judge 2, order N, P, U) was N 39/4/0, P 2/32/5, U 0/2/40.
The disagreements clustered on three kinds of passage. The frozen rubric said nothing explicit about them, so each clarification below makes the existing "when unsure choose the lower level" rule concrete.

1. **Bare form fragments** (a field or checkbox whose text is only "Yes", "No", "N/A" or a number with no question or subject in the chunk): **not useful (0)** unless the question itself is that field's yes/no and the field label is inside the chunk, in which case **partial (1)**. A value without its label cannot answer a question on its own.
2. **Passages that only mention a topic** (the question's subject appears, for example a wind farm or "NDC 3.0", but the chunk does not state the asked-for fact): **partial (1)** at most; **useful (2)** only if the asked-for fact is stated in the chunk text.
3. **Coordination or stakeholder-list text** (who meets whom, committees, arrangements) when the question asks about an activity or outcome: **partial (1)** if it names the activity, otherwise **not useful (0)**.
4. **Template-instruction blocks**: unchanged and still **not useful (0)** when the block is the substantive content. A chunk is NOT lowered one level merely because it also contains a template block (Judge 1's original extra rule was a deviation, see `PHASE_1_REPORT.md` section 8).
5. Unchanged: judge reads question + chunk text only; when unsure, choose the lower level.

Recommended for any future usefulness judging: give the judge these five rules, label at least 30 items twice (shuffled), and report kappa before using the labels.

## B. Phase 2 retrieval metrics (definitions in code, frozen with the gold set)

* Gold set `eval/gold_set.jsonl`, hashes in `eval/GOLD_FROZEN.txt` (the evaluator refuses to run if they change). 66 items: 56 answerable, 10 unanswerable (5 near_miss, 5 off_corpus). Split 14 dev / 52 test, fixed in `eval/gold_split.json`.
* **Hit rule** (`tools/gold_common.is_hit`): same doc_id and the chunk's character range in the stage-4 clean text overlaps a gold span by at least min(50 characters, 50% of the span). An item is hit at rank r if any of its spans is hit.
* **Recall@k** (k = 1, 5, 10): 1 if any hit in the top k. **MRR@10**: reciprocal rank of the first hit, 0 if none. **nDCG@10**: gain 1 for a chunk that newly covers a gold span, ideal = min(#spans, 10). **all-spans@10**: every span covered by the top 10 (multi_passage and cross_document items only).
* **Intervals and tests**: percentile bootstrap over items (10,000 resamples, seed 1). Paired comparisons on the same items: exact McNemar on R@5 hit/miss and Wilcoxon signed-rank on reciprocal rank, with the paired delta and its bootstrap interval.
* **Dev vs test**: every tuning choice uses the 14 dev items only; the 52 test items are measured once per configuration. Dev has 12 answerable and only 2 unanswerable items, so nothing about refusal can be tuned on it.
* **Refusal metrics** (3d): refusal rate on unanswerable items (near_miss and off_corpus reported separately), false-refusal rate on answerable items, R@5 on the answered subset.
