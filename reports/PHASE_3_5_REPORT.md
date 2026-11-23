# Phase 3.5: three fixes

Labels: VERIFIED = produced by a script into a file in this pass; INFERRED = reasoned, not measured; UNKNOWN = not measured.
0 LLM calls. No redeploy. No git. No new GCP resources.

## 1. Groundedness 0 and quality 0.11 on a sensible answer

Verdict: not a bug. The score is strict, and the UI was mislabelling it. No backend code changed.

How it is computed (VERIFIED by reading `scripts/stage14_citation_extraction.py`, `stage15_groundedness_validation.py`, `stage16_answer_quality_evaluation.py`):
- Stage 14 cites a sentence when at least 60% of its character 5-grams occur in a retrieved chunk (a set overlap, so paraphrase can pass).
- Stage 15 calls a sentence GROUNDED only when the longest contiguous verbatim run shared with one chunk is at least 80% of the sentence. `groundedness_score` is the share of GROUNDED sentences. A faithful paraphrase, or a correct sentence with a lead-in such as "Based on the provided excerpts,", scores 0.
- Stage 16: quality = 0.7 x groundedness + 0.3 x citation presence. With groundedness 0 and every sentence cited, quality is 0.3. The 0.11 seen live is 0.3 x a citation presence of about 0.37.

Evidence (VERIFIED, `tools/diagnose_groundedness.py` -> `eval/results/groundedness_diagnosis.json`, arm `test_noplanner_v21`, chunk text from the local chunk files, so INFERRED to equal the assembled context text):
- 38 answered replies, 96 sentences: 58 cited by stage 14, only 16 reach the 80% verbatim bar. Median 5-gram overlap 0.71, median longest-substring ratio 0.40.
- 27 of 38 answered rows have groundedness 0.
- Of the 31 replies labelled correct (section 3), 21 have groundedness 0 and 9 have 1.0. The score does not track correctness. It tracks how much of the reply is copied.

Fix chosen (as you specified: relabel, since it is strict, not broken):
- Frontend now shows "Verbatim overlap: N% of sentences (strict; paraphrase scores 0)" in place of a bare number in a green pill, and "Strict quality score" with a tooltip giving the formula (`frontend/src/lib/backend-adapter.ts`, `animated-pipeline-demo.tsx`, `pipeline-explorer.tsx`).
- Tests: `tests/test_groundedness_strictness.py` (3). These are characterisation tests, not failing-first: there was no defect to fail on, so they passed on first run. They pin the behaviour so the label stays honest.
- Not changed: the metric itself and the stage 15 threshold (frozen code). A semantic groundedness measure would be new work.
- Not done: the frontend has no test runner, so the label change has no automated test (built and linted, and seen in the browser for the banner only; the relabelled pill was not re-screenshotted live).

## 2. Frontend: visible fallback banner, timeout that survives a cold start

Changes (`frontend/src/lib/mode-detection.ts`, `providers/operating-mode-provider.tsx`, new `components/layout/backend-status-banner.tsx`, `root-layout.tsx`):
- Detection timeout 1.5 s -> 60 s (the measured Cloud Run instance start was 41.3 s, VERIFIED in the Step 6 report). The page never waits for it: sample data shows at once.
- State machine: checking -> (after 1.5 s) waking -> live or unavailable.
  - waking: "Waking up the backend (it can take about a minute after being idle). Showing sample data until it responds."
  - unavailable: "Backend unavailable, showing sample data. Results on this page are not live."
  - live: no banner. A late response still switches to Mode A.
- Check (VERIFIED in the built-in browser against the Vite dev server):
  - No backend on port 8000: the unavailable banner appears.
  - A throwaway server that answered after 6 s: the waking banner showed while waiting and was gone after the response. (The first sample was taken after the page had already loaded, so the sub-1.5 s "no banner yet" state was not captured.)
- `npm run build` exits 0; lint has the same 3 pre-existing react-refresh warnings and no errors.
- Limits: with a backend that stays down, the browser holds the pending request for up to 60 s before the banner switches from "waking" to "unavailable" (a refused connection switches at once). The dev servers I started were stopped; ports 5173 and 8000 verified closed. The deployed service was not touched.

## 3. Hand-labelled correctness, 2.1.0 no-planner, TEST, 44 answerable

Method: two independent blind AI labelling runs (Claude models), kappa 0.95, the single disagreement adjudicated by the project owner.
- Labeller A: Claude (this project's assistant). Labeller B: Claude Opus 4.6 in Antigravity, run blind, without seeing A's labels. Both are Claude models, so this is labeller independence, not model-family independence. A Gemini run was attempted but read the existing labels first, so it was discarded and is not reported as a labeller.
- Agreement (VERIFIED, `tools/compare_labelers.py` re-run, `eval/results/labeler_agreement.json` unchanged on recompute): 43/44 agree, 97.73% raw, Cohen's kappa 0.9498. The only disagreement was Q036 (A: correct, B: partial).
- Q036 adjudicated by the project owner as partial (`eval/review/label_review_sheet.md`): part 2 (workshop commitments) fully covered; part 1 omits SIM closure, job losses, forest pressure and suspended ecoguard patrols.
- Nobody else has checked the labels; apart from that one verdict no human labelled anything. Only the gold answer quotes were consulted, not the source PDFs.
Rubric: correct = all gold-required facts stated correctly; partial = some right, rest missing or declared missing, nothing contradicting gold; wrong = contradicts gold; refused = exactly NOT_IN_CONTEXT.
Files: final labels `eval/test_v21_correctness_final.json`; labeller A `eval/test_v21_correctness_labels.json`; labeller B `eval/test_v21_correctness_labels_independent.json`; summary `eval/results/test_v21_correctness_summary.json` from `tools/score_handlabels.py` (VERIFIED, Wilson 95% CI).

| Measure | k/n | Rate | 95% CI |
|---|---|---|---|
| Correct, of all 44 answerable | 31/44 | 70.5% | 55.8% to 81.8% |
| Correct or partial, of 44 | 37/44 | 84.1% | 70.6% to 92.1% |
| Correct, of the 38 answered | 31/38 | 81.6% | 66.6% to 90.8% |
| Wrong, of the 38 answered | 1/38 | 2.6% | 0.5% to 13.5% |
| Refused (false refusal) | 6/44 | 13.6% | 6.4% to 26.7% |

Counts: 31 correct, 6 partial, 1 wrong, 6 refused. The refusal count matches the earlier 6/44. (Before adjudication labeller A alone had 32 correct; the adjudicated figure supersedes it.)
By type (correct / partial / wrong / refused): single_fact 13/0/0/2; numbers_tables 9/0/1/1; multi_passage 5/2/0/1; cross_document 4/4/0/2.
The one wrong reply: Q024 gave total GEF financing 4,371,000 against gold 4,010,092 (co-financing was right). The six partials (Q036, Q039, Q053, Q055, Q056, Q057) each answer part of the question; four are cross_document.

Caveats:
- n = 44, one run, one temperature; Gemini output is not bit-exact between runs. The CI covers sampling only, not labeller error. Both labellers are Claude models and may share blind spots; Q053 (partial vs correct) is a judgment call both labellers agreed on.
- Correct here means matches the gold quote; it does not prove the reply cites the right place in the document.
- Correct replies can still score groundedness 0 (section 1): 21 of the 31 correct replies have groundedness 0, 9 have 1.0. Do not combine the two.

Resume-safe: "On 44 answerable TEST questions, two independent blind AI labelling runs (Claude models, kappa 0.95, one disagreement adjudicated by the project owner) found 31 fully correct (70.5%, 95% CI 56 to 82%), 6 partial, 1 wrong, 6 refused."
Not safe: "human-verified accuracy"; "independent of Claude" (both labellers are Claude); any accuracy figure without the refusals and the partials; reading groundedness 0 as ungrounded.

## Files changed or added
- `frontend/src/lib/mode-detection.ts`, `frontend/src/lib/backend-adapter.ts`, `frontend/src/providers/operating-mode-provider.tsx`, `frontend/src/components/layout/root-layout.tsx`, `frontend/src/components/layout/backend-status-banner.tsx` (new), `frontend/src/components/page/home/animated-pipeline-demo.tsx`, `frontend/src/routes/pipeline-explorer.tsx`
- `tests/test_groundedness_strictness.py` (new)
- `tools/diagnose_groundedness.py` (new), `tools/score_handlabels.py` (new)
- `eval/test_v21_correctness_labels.json`, `eval/test_v21_correctness_labels_independent.json`, `eval/test_v21_correctness_final.json`, `eval/results/labeler_agreement.json`, `eval/review/label_review_sheet.md`, `tools/compare_labelers.py` (labelling inputs; new), `eval/results/groundedness_diagnosis.json` (new), `eval/results/test_v21_correctness_summary.json` (new)
- `reports/PHASE_3_5_REPORT.md` (new)
Full suite after these changes: 1037 passed, scripts coverage 87% (VERIFIED, one run).
