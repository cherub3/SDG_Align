# Phase 3, Step 5: planner vs no planner, end to end

Status: PRE-REGISTRATION (written before any planner call). Results sections are added below as they are produced.
Labels: VERIFIED = produced by a script into a file in this pass; INFERRED = reasoned, not measured; UNKNOWN = not measured.
No git, no Cloud Run, no Secret Manager.

## 1. What is compared

Same 52 TEST items, same model (`gemini-3.5-flash-lite`), same retrieval (hybrid, top 10, 4000-token context), same temperature 0, same prompt template within a pair. The only difference between the arms is the route:

| Arm | Route | Gemini calls per request (expected) |
|---|---|---|
| No planner | `handle_request` directly: retrieve, one answer call | 1 |
| Planner | `execute_request`, as the served backend does: planner call, QUERY_PIPELINE step (one answer call), planner call to COMPLETE, with MAX_LLM_CALLS_PER_REQUEST=6 enforced | 3 (up to 6) |

Template pairs: 2.0.0 (frozen, failed the Step 4 keep rule), and 2.1.0 (second configuration, Step 4 section 8) if the call budget allows. The no-planner TEST arms already exist (`test_noplanner`, `test_noplanner_v21`); planner arms are `test_planner_v20` and `test_planner_v21`.
Runner: `tools/eval_planner.py` (stops on the first 429, never starts a request that could exceed the day's cap, checkpoints per request, resumes by label). Comparison: `tools/compare_arms.py` (per-type, paired, exact McNemar, bootstrap CI).

## 2. Hypothesis (stated before the planner arms run)

**H1: the planner reduces false refusals on cross-document questions.**
Pre-stated success criterion for H1, per template: on the 10 cross_document TEST items, the planner arm refuses at least 3 fewer than the matching no-planner arm, while refusing at least 5 of the 8 unanswerable items. Anything less is reported as "not supported". The paired exact McNemar p-value and a bootstrap CI are reported, but with n = 10 a p below 0.05 needs at least 6 improvements and no regressions, so the criterion above is a practical bar, not a significance claim.
Secondary (descriptive, no criterion): effect on the other question types, on unanswerable refusals, on calls and on latency per request.

## 3. What I expect, and why (INFERRED, to be checked against the results)

- The planner prompt is the JSON context (query, empty tool list, executed steps) plus a short system instruction; it is not told how retrieval works. I expect it to pass the user's question through unchanged in one QUERY_PIPELINE step and then COMPLETE. If so, retrieval and the answer call are identical to the no-planner arm and answers at temperature 0 should match, so the effect on refusals would be about zero while calls and latency about triple.
- Even if the planner splits a cross-document question into several QUERY_PIPELINE steps, the final answer is ONE step's response (`final_answer_step_index`); nothing in the code merges answers across steps. A split would therefore not combine evidence from several documents. The only route to fewer false refusals is a rewritten query whose single retrieval happens to cover more of the needed evidence.
- The run records whether the planner rewrote the query, how many query steps it issued and its step statuses, so this expectation can be confirmed or refuted from the rows.

## 4. Budget and safety (stated before running)

- Calls already made today (Pacific day): 1 to 3 smoke calls (exact count UNKNOWN, 3 assumed), 28 DEV, 52 TEST (2.0.0), 52 TEST (2.1.0) = about 135. Logged in `eval/results/quota_ledger.json`.
- Planner arm: expected 52 x 3 = 156 calls (worst 52 x 6 = 312). After the first planner arm the ledger is about 291 expected. A second planner arm expected 156 more would reach about 447, just under the 450 limit; the runner stops cleanly when fewer than 6 calls remain under the 450 cap and checkpoints, and the run is resumed after the quota resets (midnight Pacific).
- The no-planner arms use 1 call per request; the planner arms use at least 3, so the planner arm takes about 3 times longer: about 13 minutes per arm at 12 RPM.
- Cost: free tier, US$0 billed. Free-tier terms as in Step 4.
- If any 429 occurs the run stops, keeps its rows, and reports.

## 5. Result so far: planner arm with 2.0.0 ABORTED, no valid comparison (VERIFIED from eval/results/test_planner_v20.jsonl, 17 rows)

I started `test_planner_v20` and stopped it myself after 17 of 52 requests, because every row showed the same thing:
- All 17 requests: 1 Gemini call (the planner), 0 answer calls, 0 steps. 14 ended plan_status COMPLETED with no step run, 3 ended FAILED (agent_status PARTIAL x14, FAIL x3). No request produced a final response.
- p50 latency per request about 5.0 s (one planner call plus pacing).
- A 503 Service Unavailable appeared on the 18th call; I stopped the process.

Reading: with the planner as shipped (system instruction in `scripts/planner_provider_gemini.py`, tool list empty), the live `gemini-3.5-flash-lite` planner chooses COMPLETE on its first decision and never issues a QUERY_PIPELINE step. So the served planner path returns no answer for these questions. This is INFERRED from the rows (the planner's reasoning text was not inspected); the cause could be the prompt or the empty tool list. My offline dry run did not catch it, because the fake planner was scripted to issue the step. That was a gap in the dry run.

H1 (planner reduces cross-document false refusals): NOT TESTABLE as the planner stands. 0 of 17 requests got as far as retrieval and answering, so there are no refusals to compare, and the pre-registered criterion cannot be evaluated. These rows must not be read as "the planner refuses less" or "more".
The 17 rows are kept as `eval/results/test_planner_v20.jsonl` and are not a TEST measurement of answer quality. Calls used: 17 (logged in the ledger as `test_planner_v20_aborted`, by hand). Today's ledger total about 152 of 450.
Not done: the 2.1.0 planner arm (same failure expected, so I did not spend calls on it). Making the planner issue a query step needs a change to the planner prompt or tool list, which would be a change to served code and a new pre-registration; I have not made it.

## 6. Diagnosis of the planner failure (VERIFIED from eval/results/planner_probe_dev.json; 3 live calls on DEV items Q007, Q032, Q048)

Code reading (offline): the planner prompt is the JSON context (query, empty available_tools, executed_steps [], step_count 0) plus a system instruction that only said "determine the next step ... EXECUTE_STEP, COMPLETE or FAIL". Nowhere does it say that QUERY_PIPELINE answers a question, or that an empty tool list is normal. The step types appear only as schema enum values.
Raw live outputs (saved verbatim): Q007 and Q032 returned COMPLETE with final_answer_step_index 0 while no step had run; Q048 returned FAIL with the rationale "No tools are available to query the required data". Stage 21 then found no step at index 0, set no final response and raised no finding, so the run looked like a quiet PARTIAL. So the cause is the planner instruction (model reads "no tools" as "nothing to do"), plus stage 21 hiding the invalid COMPLETE. Both are fixed; the DEV probe used 3 of the 3 allowed calls and the fix itself has NOT been re-run on DEV.

Changes (one concern each, tests first; two of the three new tests failed on the old code, the third characterises FAIL handling and passed before):
1. `SYSTEM_INSTRUCTION` in scripts/planner_provider_gemini.py now states: QUERY_PIPELINE answers the question and is built in; an empty tool list is normal; with no executed steps return EXECUTE_STEP / QUERY_PIPELINE with the question copied exactly; never COMPLETE or FAIL with no executed step; after the query step, COMPLETE with that step's index. SHA-256 of the new instruction: ddf8bd9b9c7818c9e3d810b83a739e747f2df529a777793034ce5e0b71c41ce7.
2. stage 21 now adds finding PLANNER_COMPLETE_WITHOUT_ANSWER (WARNING) when COMPLETE names no executed step.
Tests: tests/test_planner_live_regression.py uses the recorded raw responses above through the real Gemini adapter and stage 21.
The Groq and OpenRouter planners have their own copies of the old instruction; not used and left unchanged.

## 7. Pre-registration of the fixed-planner arm (written before the run)

- Arm: `test_planner_v21`: fixed planner, template 2.1.0 only (hash 34a89dc9...), all 52 TEST items, same settings as the no-planner arm `test_noplanner_v21`. The 2.0.0 planner arm is not run.
- Honest note on independence: the failing 17 TEST rows of the aborted run showed the failure mode (no query step) before I fixed it, so TEST was seen once in that way. The fix text was derived from the 3 DEV outputs and the code, not tuned on TEST answers; the TEST arm is run once.
- H1 and its criterion are unchanged (section 2): at least 3 fewer refusals than test_noplanner_v21 on the 10 cross_document items (2/10 refused there) while refusing at least 5/8 unanswerable. Note that the baseline has only 2 cross_document refusals, so a reduction of 3 is arithmetically impossible: H1 cannot be met with this baseline and I state that now. I will still report the paired counts descriptively.
- Expected (INFERRED): the planner passes the question through, answers match the no-planner arm at temperature 0 and calls triple (3 per request), unless the planner rewrites the query.
- Stop rule: I check the first rows after about 2 minutes; if the planner again runs no query step I stop. 429 stops. Budget: expected 156 calls, worst 312; used today about 155 of 450, so the arm fits even at 6 calls per request only up to the cap; the runner stops cleanly if fewer than 6 remain.

## 8. Result: fixed planner, template 2.1.0, all 52 TEST items (VERIFIED from eval/results/test_planner_v21.jsonl and eval/results/step5_arms.json)

Run once, no 429. The fixed planner works as designed: 51 of 52 requests ran exactly one QUERY_PIPELINE step with the question unchanged (query_rewritten 0/52) and used 3 Gemini calls (plan, answer, complete). One request (Q062, an unanswerable near-miss item) failed with PLANNER_INVOCATION_FAILED after 1 call and has no answer (cause of the provider error not stored; INFERRED transient, as a 503 was seen earlier). It is counted as NOT refused.

| Measure | No planner (2.1.0) | Planner (2.1.0) |
|---|---|---|
| Unanswerable refused | 8/8 | 7/8 (Q062 had no answer, not a wrong answer) |
| False refusal, answerable | 6/44 | 6/44 |
| single_fact | 2/15 | 2/15 |
| numbers_tables | 1/11 | 1/11 |
| multi_passage | 1/8 | 1/8 |
| cross_document | 2/10 | 2/10 |
| Gemini calls per request | 1 (total 52) | mean 2.96, max 3 (total 154) |
| Latency per request p50 / p95 / max | 1.2 s / 1.6 s / 2.0 s | 15.0 s / 17.0 s / 17.8 s |

Paired against the no-planner arm (exact McNemar, bootstrap CI): answerable 6 -> 6 refused, 0 newly, 0 no longer (p = 1.0); cross_document 2 -> 2, delta 0.0, CI [0.0, 0.0]; unanswerable 8 -> 7 only because of the failed Q062 request.
The two arms' answers differ in wording on 24 of 52 items even at temperature 0, so Gemini output is not bit-exact between runs; refusal decisions were identical on all 44 answerable items.

Latency caveat: the runner paces at 12 requests per minute (5 s per call), so the 15 s planner figure is mostly pacing, not model time. Un-paced model time per request at p50 was about 2.4 s of planner calls plus 1.4 s of answer call (INFERRED to exclude the pacing; recorded by wrapping the adapters). In serving, with no pacing, expect roughly 3 sequential calls, about 4 s, against about 1.3 s without the planner.

H1: NOT SUPPORTED. The planner did not reduce cross_document false refusals (2 -> 2). As stated in the pre-registration, the criterion was arithmetically unreachable against this baseline (only 2 refusals to remove), so this arm cannot test whether a planner could help the 2.0.0 arm's 9/10 cross_document refusals; that arm was not run with the fixed planner. The expectation in section 3 was confirmed: the planner passes the question through and adds 3x calls and about 3x latency for no change in refusals.
Cost: 154 calls. Day total in the ledger: 309 of 450.
Not done: fixed planner arm with 2.0.0; Gemini nondeterminism not quantified beyond the 24 differing texts; correctness of the planner answers not hand-labelled.
Recommendation (mine, INFERRED): ship without the planner on the default path, say so, and keep it as an opt-in.
