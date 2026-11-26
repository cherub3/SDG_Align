# Phase 3 Step 1: GCP readiness (read-only; nothing created, enabled or deployed)

## REVISION 4 (2026-11-23): model switched to gemini-3.5-flash-lite, 500 requests/day (wins over Revision 3 numbers)

**Facts**
- VERIFIED: the first smoke call to `gemini-2.5-flash-lite` returned HTTP 404 "no longer available to new users, use gemini-3.5-flash-lite". AI Studio then showed that model at 0/20, so the 404 did not count.
- User-read from AI Studio Rate Limit page (Default Gemini Project, free tier, 2026-11-23): `gemini-3.5-flash-lite` = 15 RPM, 250K TPM, **500 RPD**. Not independently verifiable by me.
- Data use, from the official pricing page (https://ai.google.dev/gemini-api/docs/pricing, section "Gemini 3.5 Flash-Lite", read in the built-in browser 2026-11-23): Free tier "Used to improve our products: **Yes**"; Paid tier: "No". Price on the free tier: free of charge. Paid-tier prices listed for reference only: $0.30 input / $2.50 output per 1M tokens. So prompts and chunk text sent in evals and the demo may be used by Google; the corpus is public GEF/UNDP text (your decision).
- VERIFIED live smoke call (1 call): HTTP 200, "OK", 8 prompt + 1 completion tokens, 1,823 ms, model_version_reported `gemini-3.5-flash-lite` (`reports/evidence/gemini_smoke.json`).
- The model id is pinned in `config/llm_model.json`; code reads it via `scripts/model_config.py`.

**Rules (replace Revision 3 rules 3, 5, 6, 7)**
- Pace 12 RPM (one call start every 5 s; `LLM_PACE_RPM=12`; limit is 15). 429 = stop, never retry (unchanged).
- Planner arm is measured on all 52 TEST items. The Revision 3 "no LLM judge" rule stays (correctness stays a script check), now because of method cleanliness, not quota.
- Eval runs use their own guard cap of 450/day (50 held as slack). Server `DAILY_LLM_CALL_CAP` stays clamped to 18 and defaults to 10: demo is separate and small. Demo calls share the same project 500/day, so on eval days the demo cap should be 0.

**Calls**
| Step | Calls (expected / worst) |
|---|---|
| 2 smoke (done: 1 failed 404 + 1 ok) | 2 |
| 4 DEV prompt tuning: 14 per pass, up to 2 passes | 14 to 28 |
| 4 TEST no-planner, 52 items, once | 52 |
| 5 TEST planner arm, 52 items x about 3 (cap 6) | about 156 / 312 |
| 5/9 stability rerun, both arms, same prompt/config | about 208 / 364 |
| 6 smoke on Cloud Run + 8 frontend (about) | about 5 |
| Total | about 440 expected, about 750 worst |

**Calendar** (12 RPM = 500 calls take about 42 minutes of wall time, so time is not the limit; the daily count is)
- Day 1: DEV (<=28) + TEST no-planner (52) + planner arm (about 156, worst 312): worst 392, under the 450 guard.
- Day 2: stability rerun, both arms: about 208, worst 364.
- If a worst case would pass 450, the runner checkpoints and stops, and the rest runs after the midnight-Pacific reset.
- Tokens: about 12 calls/min x a few thousand tokens is far under 250K TPM (to be measured, not assumed).

**What more calls change in the claims**
- Planner vs no-planner is now 52 paired items, not 18: it can detect a smaller difference, but only on this gold set. McNemar still needs several discordant pairs.
- Abstention is still limited by the number of unanswerable items (8 on TEST, 2 on DEV), not by calls. A rerun shows run-to-run stability at temperature 0; it does not add independent items. All "CANNOT support" items from Revision 3 about abstention significance, near-miss vs off-corpus, other models and generalisation remain.
- A stability rerun can support "same configuration, two runs on one day, k answers differed". It cannot support stability across days or model updates.

## REVISION 3 (2026-11-23): redesign for 20 requests per day. Supersedes Revision 2 wherever they differ.
Facts (from you, AI Studio Rate Limit page, 2026-11-23): key lives in "Default Gemini Project" (gen-lang-client-0169941563), Free tier, no billing. `gemini-2.5-flash-lite`: 10 RPM, 250K TPM, **20 RPD**; `gemini-2.5-flash`: 5 RPM, 250K TPM, 20 RPD. RPD resets at midnight Pacific. Limits are per project, so eval runs, the live demo, smoke tests and anything you try in the AI Studio playground all draw from the same 20.
Assumption (UNKNOWN): a call that returns an error may still count toward RPD. I plan as if it does.

### Rules that follow from 20 RPD
1. Retrieval eval, retrieval endpoint tests, latency of retrieval, container cold start: 0 Gemini calls, fully offline.
2. No retry on 429, ever. A 429 stops the run, saves progress, exits non-zero. Today's code treats 429 as transient and retries it (INFERRED from the Phase 2.5 test, which raises `LLMTransientError("429")`; to be verified in Step 2 and fixed with a test that fails on the old code). Other transient errors: at most 1 retry, and it counts against both caps.
3. Client-side pacing at 1 call per 7 s (under 10 RPM).
4. Every eval run is resumable: a checkpoint file records each answered qid; a rerun never repeats a call. Runs span days.
5. Planner is OFF by default everywhere (it costs about 3x calls).
6. No Gemini LLM judge (it would eat the budget). The "secondary LLM judge" in the Step 4 brief is dropped. Correctness is the script check only (answer supported by the gold `answer_quote` span), plus the existing script-based citation/groundedness checks.
7. Daily budget I plan against: 18 calls per day, 2 held back as slack.

### Gemini calls per request
| Mode | Calls | Source |
|---|---|---|
| Retrieval only (`/retrieve`-style, evals, Step 7) | 0 | VERIFIED by design |
| Answer, planner off | 1 | by design (INFERRED: confirmed in Step 2 with a fake-adapter test that counts calls) |
| Answer, planner on | about 3 (plan, answer, plan-complete), hard cap 6 | from Phase 2.5 report; to be measured in Step 2/5 |
| Demo default (planner off) | 1 | |
Demo caps (Step 6): `MAX_LLM_CALLS_PER_REQUEST=2`, daily cap `DAILY_LLM_CALL_CAP=10` (below 20, leaves room for manual use and slack), per-client rate limit, and a circuit breaker: after any 429 the service answers "daily LLM limit reached, retrieval still works" until midnight Pacific. While the evals run the demo cap is 0 (retrieval-only), so the demo cannot starve the eval. Limit of this design: with min-instances=0 the in-memory daily counter resets whenever the instance restarts, so Google's own 20 RPD plus the 429 breaker is the real hard stop; a persistent counter (small GCS object, free tier) is an option I will ask about in Step 6.

### Calls per step
| Step | Gemini calls | Notes |
|---|---|---|
| 1 | 0 | |
| 2 adapters | 1 live smoke (after the project owner's approval) | unit tests use fakes |
| 3 container | 0 | cold start and p50/p95 measured on retrieval only |
| 4 abstention | DEV 14 per prompt pass (max 2 passes = 28) + TEST 52 = 66 to 80 | |
| 5 planner vs none | planner arm: 18 TEST items x about 3 = about 54 (cap 6 => at most 108). No-planner arm = reuse the Step 4 TEST answers, 0 new calls | same questions, same retrieval |
| 6 deploy | 2 (of the 5 smoke questions: 2 with LLM, 3 retrieval-only) | |
| 7 served-path | 0 | |
| 8 frontend | 2 | one real query + one retry slot |
| 9 | 0 | |
| Total | about 139 expected, about 193 worst | |
Calendar at 18 calls per day: about 8 days (Day 1: smoke + DEV pass 1; Day 2: DEV pass 2 only if pass 1 fails the pre-stated keep rule; Days 3 to 5: TEST no-planner 52; Days 6 to 8: planner arm 54). If DEV pass 2 is not needed it is 7 days. Steps 2, 3, 6 (build), 7 and the offline parts of 9 happen on the idle quota days and cost 0 calls.

### The small eval, and exactly what it can and cannot support
Gold set facts (VERIFIED from `eval/gold_set.jsonl`, `gold_split.json`): 66 items = 56 answerable + 10 unanswerable (5 near-miss, 5 off-corpus). DEV 14 (12 answerable, 2 unanswerable), TEST 52 (44 answerable, 8 unanswerable; the near-miss/off-corpus split of those 8 is printed before running).
Design: one model (`gemini-2.5-flash-lite`), temperature 0, one run per question (no repeats), prompt frozen before TEST, keep rules written down before TEST, TEST once per configuration. Planner arm = the 18 TEST items of type cross_document (10) and multi_passage (8), where a planner could matter.
Pre-stated keep rule (from your brief): refuses a majority of unanswerable TEST items (at least 5 of 8) with false refusal on answerable at most about 10% (at most 4 of 44).

CAN support:
- Point estimates with bootstrap/Wilson intervals for: answer supported by the gold quote on the 44 answerable TEST items (interval about plus or minus 12 points), false-refusal rate on those 44 (3 of 44 = 6.8%, Wilson upper bound about 18%), and a raw count "refused k of 8".
- Exact, deterministic cost facts: Gemini calls per request with and without the planner, measured latency per request (local machine to API, labelled as such), tokens per call.
- Whether the keep rule was met as a count, stated plainly, including if it fails.
- A paired comparison on 18 items that can only detect a large difference: McNemar exact needs about 6 or more discordant pairs all going one way to reach p<0.05.

CANNOT support:
- Any statistical claim about abstention: 8 TEST unanswerable items (about 4 near-miss, 4 off-corpus) give 5 of 8 a 95% lower bound near 25%, so "refuses the majority" is not provable, and near-miss vs off-corpus cannot be compared at n of about 4 each. DEV has only 2 unanswerable items, so prompt tuning on DEV barely informs abstention; it mainly checks that answerable questions are not wrongly refused.
- "The planner does not help" or "the planner helps": at n=18 a non-significant result means no evidence at this size, not no effect.
- Groundedness quality by an LLM judge (none is run), human-rated answer quality, performance with any other model, stability across days or reruns (one run, temperature 0, free-tier model may change), performance on questions outside this 66-item AI-drafted gold set, or production traffic behaviour.
- Anything about answer correctness beyond "the answer text is supported by the gold quote span" (a script check that misses valid paraphrases and can pass lucky overlaps; the checker's own false-positive/negative rate is reported on a hand-read sample of 10 from DEV, which costs no Gemini calls).

### Cost with the 20 RPD plan
Gemini $0 (free tier; all calls in a no-billing project). Nothing else changed from Revision 2: expected about $0.2 per month, credit-covered, worst case about $4. Data-use note unchanged: free-tier prompts may be used by Google to improve its products.

---

## REVISION 2 (2026-11-23): decision after your answers (Vertex dropped, AI Studio free tier chosen). Where Revision 3 above differs, Revision 3 wins.
Decisions (project owner): trial signed up 23 Nov 2026, so credit does not cover Vertex AI Gemini. No Vertex, no account upgrade. Budget API stays disabled (the project owner confirmed the "Rs 500 Monthly Budget Alert" at 50/90/100/150% in the console; it was not visible from the CLI, so VERIFIED by the project owner, not by a command).
- LLM + planner: Gemini API via Google AI Studio API key, free tier, existing API-key adapters. Key goes in Secret Manager, never in code, image or git.
- Model: `gemini-2.5-flash-lite`.
- Cloud Run, Cloud Build, Artifact Registry, Secret Manager in asia-south1, paid from trial credit (these four are not on the credit exclusion list).
- Deploy sets `NETWORK_CALLS_PERMITTED=true` explicitly (Gemini API is a network call); `MAX_LLM_CALLS_PER_REQUEST` stays enforced.

### AI Studio free tier (official pages, read 2026-11-23, VERIFIED unless marked)
- Pricing https://ai.google.dev/gemini-api/docs/pricing (redirects to aistudio.google.com/docs/pricing): `gemini-2.5-flash-lite` Free Tier input and output "Free of charge". Paid tier $0.10 in / $0.40 out per 1M tokens.
- Data use, same page: Free Tier "Used to improve our products: Yes"; Paid Tier "No". So on the free tier, every prompt sent (question + retrieved passages + the planner prompt) may be used by Google to improve products. The corpus is public UNDP/GEF material, but never send private text through this key, and do not put the live demo's users on notice-free assumptions: say so in the README.
- Rate limits, https://ai.google.dev/gemini-api/docs/rate-limits: limits are per project (not per key), RPD resets at midnight Pacific, and the page does not list per-model free numbers; it says to view them in AI Studio. So the free RPM / TPM / RPD for gemini-2.5-flash-lite are UNKNOWN. Open question: AI Studio > the key's project > Rate limits shows the three numbers. The eval scripts pace themselves to them and stop on a 429 (never retry-loop).
- Availability: https://ai.google.dev/gemini-api/docs/deprecations lists `gemini-2.5-flash-lite` as "not deprecated ... until further notice", no shutdown date (its sibling gemini-2.5-flash shuts down 1 Dec 2026). Risk: it may be retired later; pin the id in config and record the date.
- Tiers: "Tier 1 = set up and link an active billing account". WARNING (INFERRED from that table): if the key's project has billing linked (sdg-align-fde does), it may be Tier 1 = paid, with the $0.10/$0.40 price and NOT covered by trial credit (the credit page excludes "Gemini API in AI Studio costs"). To stay free, create the key in a project with no billing linked and confirm AI Studio shows it as Free tier before any call. Do not create the key from sdg-align-fde.

### Secret Manager pricing (https://cloud.google.com/secret-manager/pricing, VERIFIED)
Active secret versions: 6 free per month per billing account, then $0.06 per version-month ($0.000082192/hour). Access operations: 10,000 free per month, then $0.03 per 10,000. Management operations free. Rotation notifications: 3 free. Our use: 1 secret, 1 or 2 versions, a few accesses per container start = free. Secret Manager API must be enabled (free, needed for Step 6; not enabled now).

### Revised cost table (INFERRED token counts as before: about 5.5M input + 0.73M output tokens for the whole phase)
| Item | Expected | Worst case | Paid by |
|---|---|---|---|
| Gemini 2.5 Flash-Lite, key in a no-billing project (free tier) | $0 | $0 (calls just return 429 when the daily limit is hit; evals take longer or split across days) | n/a |
| Gemini 2.5 Flash-Lite if the key's project turns out to be paid Tier 1 | $0.84 (Rs 80) | $2.5 (Rs 240) | NOT trial credit (excluded); would hit the account directly. Avoided by the key rule above |
| Cloud Build, about 5 builds x 15 min | $0 (2,500 free min) | $0.6 | credit |
| Artifact Registry, about 2 GB image | $0.15 per month | $1 per month | credit |
| Cloud Run, 1 instance max, daily cap | $0 (free tier) | under $2 | credit |
| Secret Manager, 1 secret | $0 | $0.06 per month | credit |
| Logging / Trace | UNKNOWN, expected near $0 | UNKNOWN | credit |
| Cloud Run outbound data to Gemini API / clients | UNKNOWN, kilobytes per request | UNKNOWN | credit |
Expected total about $0.2 per month (credit-covered); worst case about $4, or $6.5 if the key lands on the paid tier. The Rs 500 (about $5.3) alert would only be near in the worst case.

The Vertex-specific lines below (the 3.x Flash prices, `aiplatform` API, region question, "sign-up date" open item) are kept for the record but no longer apply. The `aiplatform` API will NOT be enabled.

---

Labels: VERIFIED = read from a command or official page in this pass. INFERRED = my estimate. UNKNOWN = not checked.

## Checks (gcloud 594.0.1)
| Item | Result |
|---|---|
| Account / project | the project owner account, project `sdg-align-fde` ACTIVE (VERIFIED) |
| ADC | `print-access-token` succeeds (VERIFIED; token not printed) |
| Billing | linked and enabled on billing account 019950-2FB0FA-DD10BA (VERIFIED) |
| Budget alert (Rs 500) | UNKNOWN from CLI: Budget API is not enabled on the project, so `budgets list` fails. It was not enabled. Check in Console > Billing > Budgets, or enable the billingbudgets API (free) with the project owner's approval |
| APIs enabled | logging, cloudtrace only. NOT enabled: run, aiplatform, artifactregistry, cloudbuild, secretmanager (VERIFIED) |
| Existing resources | none checkable until APIs are on (UNKNOWN) |
| Docker | not installed; Cloud Build will be used |

## Does the trial credit cover the services?
Source: https://docs.cloud.google.com/free/docs/free-cloud-features (VERIFIED, read in browser)
- Trial = $300 credit, valid 90 days, "products and services covered by the Free Trial".
- "The $300 credit can't pay for Gemini platform (formerly ... Vertex AI) services if you sign up for a free trial or upgrade to a paid account on or after November 16, 2026."
- Also excluded: Gemini API in AI Studio, and partner (MaaS) models.
- Cloud Run, Cloud Build, Artifact Registry: no exclusion listed on that page, so credit applies (and they have free tiers).
- OPEN: the sign-up date is not known. Rs 28,569 is about $300, matching the standard trial. If the account signed up on/after 16 Nov 2026, Vertex Gemini calls are NOT covered by credit and would bill the card once the account is upgraded to paid (a pure free-trial account may not be able to use it at all). UNKNOWN until the date is confirmed.

## Prices (official pages, read 2026-11-23, USD)
- Cloud Run https://cloud.google.com/run/pricing: asia-south1 is Tier 1. Request-based billing: CPU active $0.000024/vCPU-s, memory $0.0000025/GiB-s, $0.40 per 1M requests. Free tier per month: 180,000 vCPU-s, 360,000 GiB-s, 2M requests (stated for us-central1, applied as a Tier 1 spend discount, aggregated per billing account). Unauthenticated-denied requests are not billed.
- Cloud Build https://cloud.google.com/build/pricing: 2,500 free build-minutes per month per billing account, promotional, e2-standard-2 default pool only, subject to change; then $0.006/min. Queue time not billed.
- Artifact Registry https://cloud.google.com/artifact-registry/pricing: first 0.5 GiB-month free, then $0.000136986 per GiB-hour (about $0.10/GiB-month), per billing account. Same-location transfer to Cloud Run/Build is free.
- Gemini https://cloud.google.com/vertex-ai/generative-ai/pricing (page title now "Agent Platform Pricing"). The first price column is presumably standard (I did not confirm the column headers). Per 1M tokens, input / output:
  - gemini-2.5-flash-lite (global): $0.10 / $0.40
  - gemini-3.1-flash-lite: global $0.25 / $1.50; non-global $0.275 / $1.65
  - gemini-3.5-flash-lite: global $0.30 / $2.50; non-global $0.33 / $2.75
  - gemini-3.6/3.7/3.8-flash: introductory $0.75 / $3.75 global ($0.825 / $4.125 non-global) through 31 Dec 2026, then $1.50 / $7.50
  - Only successful (200) requests are charged.
- Not verified: Secret Manager, Cloud Logging, Cloud Trace pricing (UNKNOWN; Secret Manager is avoided unless API-key auth is chosen).

## Region
- Cloud Run / Artifact Registry / Cloud Build: asia-south1 (Mumbai). It is Tier 1 for Cloud Run (VERIFIED).
- Gemini: the locations page has a Mumbai column but its availability cells did not extract, so Gemini serving in asia-south1 is UNKNOWN. Global endpoint lists the Flash and Flash-Lite ids (VERIFIED) but offers no data residency and is about 10% cheaper. Proposal: try asia-south1 in the single smoke call (a failed request is not charged); if it is refused, use `global`.

## Cost table for the whole phase (INFERRED: token counts and call counts are my estimates; Rs 95/$ from your credit figures)
Assumed request: planner on = 3 calls, about 9k in / 1.5k out total; answer only = 1 call, about 4k in / 0.4k out. Phase total: about 600 answer calls, 300 planner-mode requests, 200 judge calls = about 5.5M input, 0.73M output tokens.
| Item | Expected | Worst case | Note |
|---|---|---|---|
| Gemini, gemini-3.1-flash-lite non-global (recommended) | $2.7 (Rs 260) | $8 (Rs 760) | 3x call overrun |
| Gemini, gemini-3.6-flash non-global (introductory price) | $7.5 (Rs 710) | $23 (Rs 2,200) | stronger model |
| Gemini, gemini-2.5-flash-lite global (cheapest) | $0.9 (Rs 90) | $3 (Rs 280) | older model |
| Cloud Build (about 5 builds x 15 min) | $0 (inside 2,500 free min) | $0.6 | |
| Artifact Registry (about 2 GB image, a few tags) | $0.15/mo | $1/mo | delete old tags |
| Cloud Run (2 vCPU / 4 GiB, max 1 instance, daily cap) | $0 (inside free tier) | under $2 | worst case = free tier exceeded by 5x |
| Logging / Trace / Secret Manager | UNKNOWN, expected near $0 | UNKNOWN | |
Your Rs 500 budget alert (about $5.3) would fire on the Gemini line in the 3.6-flash case. Whether the Gemini spend comes out of credit or your card depends on the sign-up date question above.
