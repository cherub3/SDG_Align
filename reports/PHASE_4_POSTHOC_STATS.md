# Phase 4 post hoc statistics: arm A (single call) vs arm B (ADK multi-agent)

**Status: POST HOC. Not pre-registered.** The Phase 4 keep rule (`reports/PHASE_4_REPORT.md` section 3) is a point-estimate gate and named no significance test. This file adds one afterwards, on the same TEST rows, so it cannot change the keep-rule verdict.

**Multiple use of TEST.** The 52 TEST items have been scored for two abstention templates (2.0.0, 2.1.0), the planner arm, and this agent arm; template 2.1.0 was chosen after 2.0.0 failed on TEST. No correction for multiple comparisons is applied here, and none would rescue a result this small.

## What was computed

- Inputs: `eval/results/test_noplanner_v21.jsonl` (A) and `eval/results/test_agents_v1.jsonl` (B); no model call, no other input.
- Flags per item come from the project's own metric function (`arm_metrics` in `tools/eval_agents.py`) run on one row at a time, so they are the flags behind `eval/results/test_agents_v1_summary.json`. The counts match that summary (checked by a test).
- Test: exact two-sided McNemar on the discordant pairs (binomial, p = 0.5). CI: percentile bootstrap of the paired difference (B minus A), 10,000 resamples, seed 1, as in `tools/compare_arms.py`.
- Code: `tools/phase4_posthoc.py`. Output: `eval/results/phase4_mcnemar_posthoc.json`. Test: `tests/test_phase4_posthoc.py` recomputes everything from the row files and compares it with the stored JSON.

## Results

**False refusal on the 44 answerable items** (event = the answer is exactly `NOT_IN_CONTEXT`)

| | B refused | B answered |
|---|---|---|
| **A refused** | 1 | 5 |
| **A answered** | 2 | 36 |

A 6/44, B 3/44. Discordant pairs: 7 (5 only A, 2 only B). Difference B minus A: -0.0682, 95% CI [-0.1818, +0.0455]. **Exact McNemar p = 0.4531.**

**Automatic wrong answer on all 52 items** (event = the automatic proxy marks the answer wrong)

| | B wrong | B not wrong |
|---|---|---|
| **A wrong** | 9 | 7 |
| **A not wrong** | 3 | 33 |

A 16/52, B 12/52. Discordant pairs: 10 (7 only A, 3 only B). Difference B minus A: -0.0769, 95% CI [-0.1923, +0.0385]. **Exact McNemar p = 0.3438.**

The same flag on the 44 answerable items alone gives the same table cells for discordance (7 and 3, the 8 unanswerable items add 0 wrong in both arms), difference -0.0909, CI [-0.2273, +0.0455], p = 0.3438.

## Reading

- Both differences point toward B, and both intervals include zero. With 7 and 10 discordant pairs there is not enough information to separate B from chance. This is not evidence of no difference; it is a sample too small for a significance claim.
- "Wrong" is the automatic proxy, not a correctness label. It can miss paraphrased correct answers and accept a wrong answer that repeats the right words. Nothing in this file is a correctness label for arm B.
- The keep-rule verdict ("eligible as default") stands as pre-registered; it did not depend on a significance test. A resume line should not say the improvement is significant.
- Arms differ in more than the method: A ran earlier, on a different API key and an older google-genai SDK, and B's prompt adds a citation rule (`reports/PHASE_4_REPORT.md` sections 3 and 3a).
