# AI-judge evaluation protocol (written and committed BEFORE any judge ran and before the key was opened)

Replaces the human-label step of `metrics_definitions.md` section 5 (the frozen file is not edited; this is a
recorded deviation, see PHASE_1_REPORT section 8). No human labelled anything.

## Judges
* **Judge 1** (the main LLM session): labels already committed (`blind_labels_ai_judge1.json`, commit 4d48441) in the
  as-is form, which includes one rule that is NOT in the frozen rubric (a chunk with a large template-instruction block counts one
  level lower). A frozen-rubric-only version is derived in step 3 and is the version used in all headline numbers.
  File renamed on 2026-11-25; content unchanged.
* **Judge 2**, **Judge 2b** (self-consistency), **Judge 3** (adjudication): fresh LLM sub-agents from the same model family. No paid API.
  (Wording edited on 2026-11-26: tool names removed from the two lines above; no other change.)
* Each judge gets ONLY the rubric (`rubric.md`), the instruction "You are rating search results for relevance. Use only the rubric.",
  and its items (question + passage text). It never gets the key, other judges' labels, cleaning rules, code, commit history, metrics,
  versions, or the project goal. The prompt files are saved verbatim in `prompts/`; the raw output of each judge is saved in `raw/`
  before any parsing. Isolation is by instruction, not by sandbox (a sub-agent has file tools); this is a stated limitation.
* The rubric file leaves out the frozen bullet about the two NOT INDEXED questions (it would reveal which questions have no answer in
  the index). Questions 14 and 15 are scored 0 for every result by that frozen rule, whatever the judges said.

## Reliability thresholds (Cohen's kappa, Judge 1 frozen vs Judge 2, over the 13 answerable questions = 124 items)
* kappa >= 0.6: reliable.
* 0.4 <= kappa < 0.6: moderate, use with caution.
* kappa < 0.4: unreliable, so the headline usefulness result is reported as INCONCLUSIVE and the rubric is flagged for a fix in Phase 2.
Both the unweighted and the linear-weighted kappa are reported; the thresholds apply to the unweighted one.

## Final label
For an item where Judge 1 (frozen) and Judge 2 agree: that label. Where they differ: Judge 3 labels it, the final label is the majority
of the three; if all three differ the final label is P and the item is listed as "unresolved". Questions 14 and 15: 0 by the frozen rule.

## Results computed after unblinding (script: tools/compute_phase1_results.py)
Per version: useful@5, (useful+partial)@5, mean usefulness score (U=2, P=1, N=0) over the 13 answerable questions; boilerplate share in
top-5 (frozen automatic rule); fragments and duplicates in top-5; expected document at rank 1.
Per question: win / loss / tie on mean usefulness score in top-5 (after vs before). Significance: two-sided exact sign test and
Wilcoxon signed-rank on the 13 per-question differences. n = 13 is small and the test has low power; this is stated in the report.
A claim of "after beat before" requires BOTH p < 0.05 on the paired test AND kappa >= 0.6; otherwise the report says "no significant
difference shown" (or INCONCLUSIVE when kappa < 0.4).
Headline = final labels (frozen rubric). Also shown: Judge 1 frozen alone, Judge 2 alone, Judge 1 as-is (deviation).
