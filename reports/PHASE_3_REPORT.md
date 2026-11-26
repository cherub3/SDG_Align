# Phase 3 report: from measured retrieval to a deployed, guarded service

Labels: **VERIFIED** = produced by a command, script or test in a file I can point to. **INFERRED** = reasoned, not measured. **UNKNOWN** = not measured.
No git was run. The Gemini key was never printed or committed. Per-step detail is in `PHASE_3_STEP1..6_REPORT.md`; this file is the roll-up.

## 1. What was done

| Step | What | Where |
|---|---|---|
| 1 | GCP readiness: project, region (asia-south1), cost/quota reading | `PHASE_3_STEP1_GCP_READINESS.md` |
| 2 | Container image recipe, daily LLM cap and 429 breaker (`scripts/quota_guard.py`), per-request call cap | `PHASE_3_STEP2_REPORT.md` |
| 3 | One Cloud Build of `api:v1` | `PHASE_3_STEP3_REPORT.md` |
| 4 | Structured abstention (`NOT_IN_CONTEXT`), templates 2.0.0 and 2.1.0, TEST runs, pre-stated keep rule | `PHASE_3_STEP4_REPORT.md` |
| 5 | Planner vs no planner, end to end, including a planner bug found and fixed | `PHASE_3_STEP5_REPORT.md` |
| 6 | Deploy `api:v2` to Cloud Run (IAM only), smoke test | `PHASE_3_STEP6_REPORT.md` |
| 7 | Served-path retrieval check against the deployed service (section 3) | this file |
| 8 | Frontend Mode A against the deployed API, npm audit (section 4) | this file |
| 9 | Mutation probe, full suite 3x, fresh-venv check (section 5) | this file |

## 2. Numbers

| Claim | Number | Label | Source |
|---|---|---|---|
| Retrieval: dense baseline R@5 (TEST, 44 answerable) | 0.57 [0.41, 0.70] | VERIFIED | `eval/results/phase2_ladder.md` |
| Retrieval: hybrid (BM25 + dense, RRF) R@5 | 0.77 [0.64, 0.89]; R@10 0.89; 3b vs 3a R@5 +0.204, p = 0.0039 | VERIFIED | `phase2_ladder.md`, `3d_test_hybrid.json` |
| Cross-encoder reranker | R@1 up, R@5 down (0.77 to 0.68), about 3.2 s/query, OFF by default | VERIFIED | `3c_verdict.md` |
| Abstention 2.0.0 on TEST (single run) | unanswerable refused 8/8; false refusal 13/44 = 29.5%; cross_document 9/10 | VERIFIED | `test_noplanner_summary.json` |
| Abstention 2.1.0 on TEST (single run, post-hoc candidate) | unanswerable refused 8/8; **false refusal 6/44 = 13.6% [4.5%, 25.0%]** | VERIFIED | `test_noplanner_v21_summary.json` |
| Keep rule (pre-stated: refuse >= 5/8 unanswerable AND false refusal <= 10%) | **FAILED for both templates** (2.1.0: 6/44 > 4/44) | VERIFIED | Step 4 report sections 7 and 9 |
| Planner (2.1.0, fixed) vs none | refusals identical: 6/44 vs 6/44, cross_document 2/10 vs 2/10; calls 2.96 vs 1 per request; p50 latency 15.0 s vs 1.2 s (mostly 12 RPM pacing; un-paced about 4 s vs 1.3 s, INFERRED) | VERIFIED / INFERRED | `step5_arms.json` |
| H1 (planner cuts cross-document false refusals by >= 3) | NOT SUPPORTED; the bar was arithmetically unreachable (baseline had 2) | VERIFIED | Step 5 report section 8 |
| Served path vs offline hybrid (section 3) | same retrieved chunks on all 66 gold queries; Recall@5 identical on the 56 answerable ones (TEST 0.7727, DEV 0.8333) | VERIFIED | `step7_served_vs_offline.json` |
| Cloud Run cold start | 41.3 s (instance start to ready, from logs) | VERIFIED | Step 6 report |
| Warm latency, reused connection | `/health` p50 48 ms; retrieval-only median 111 ms, max 151 ms over 10 warm requests (health: median 48 ms over 10) | VERIFIED | `step6_smoke.json` |
| Warm LLM request latency | 5.1 s and 2.3 s (n = 2; no p50/p95 claim) | VERIFIED | `step6_smoke.json` |
| Tests | 1034 passed, three consecutive full runs; scripts coverage 87% | VERIFIED | section 5 |
| Mutation probe, Phase 3 code (M59-M75, 17 mutants) | 17 of 17 killed after one fix (section 5); a no-op control survives | VERIFIED | `reports/mutation/mutation_results_M59_...M75.json`, `reports/mutation/mutation_results_M75.json` |
| Fresh-venv install and suite | 1034 passed, scripts coverage 87%, in a new venv | VERIFIED | section 5 |
| LLM calls spent in Steps 7-9 | 1 (the single Mode A query in the browser); limit was 2 | VERIFIED (browser network log shows one POST /run-query) | section 4 |

## 3. Step 7: served path vs offline (VERIFIED: `eval/results/step7_served_retrieval.json`, `step7_served_vs_offline.json`)
- 66 gold questions (14 DEV, 52 TEST) were sent to the deployed service with `retrieval_only: true`. Every response had `llm_calls: 0`. They were scored with the same code as the offline eval (`tools/eval_served.py` uses `score_item` and `summarize` from `tools/eval_retrieval.py`), after the frozen-input hash check.
- TEST (44 answerable): R@5 served 0.7727, offline 0.7727. DEV (12 answerable): 0.8333 and 0.8333.
- Per item: 0 items with a different first-hit rank, 0 with a top-1 score differing by more than 1e-3, 0 served chunks whose text differs from the local chunk file.
- **Difference found: none in retrieval.** Reason for the agreement (INFERRED from the setup): the image was built from the same derived corpus and index, the embedding model is pinned and baked in, and the served path uses the same hybrid parameters (RRF k = 10, BM25 weight 2) as the offline run. Latency differs (served p50 105 ms on TEST including the network, offline p50 54 ms), as expected.
- Limit: this checks retrieval identity, not answer quality. The answer step was not part of it.

## 4. Step 8: frontend (VERIFIED)
- **Which backend:** the deployed Cloud Run service, not a local one. A browser cannot send the IAM identity token, so I ran `tools/auth_proxy.py` on 127.0.0.1:8000 (it adds my `gcloud` identity token; the token is never printed or stored) and the Vite dev server on localhost:5173 (the default `VITE_BACKEND_URL` is `http://localhost:8000`). I did not use `gcloud run services proxy` because it asks for a component install. I made no public access and no `run.invoker` grant to anyone. Both processes were stopped afterwards (ports 8000 and 5173 verified closed).
- **Result:** the app detected the backend and switched to Mode A. The Pipeline Explorer ran the live query "What SDG goals are addressed?": POST /run-query 200 in 2.1 s, one stage (QUERY_PIPELINE, so the planner is off), a real answer listing SDGs 2, 5, 12, 13, 14, 15 and 17, status PASS. The Observability page listed the service's requests. 1 LLM call used.
- **Problem found and fixed (in my proxy, not the app):** the frontend gives the backend 1.5 s to answer before it falls back to sample data (`src/lib/mode-detection.ts`). My first proxy opened a new TLS connection to Cloud Run per request (about 1 s), so detection timed out and the page silently stayed on sample data. With connection reuse the proxy answers in about 0.28 s. Implication (INFERRED): a browser far from asia-south1 calling an IAM-protected service directly could also exceed 1.5 s on its first request and show sample data without saying so. I did not change the frontend.
- **Observed, not investigated:** the live answer shows "Citation data unavailable in Mode A" and a groundedness score of 0 with quality 0.11 for an answer that looks sensible. It is UNKNOWN whether the checker is strict or the mapping is off.
- **npm audit:** before, 7 vulnerabilities (2 moderate, 5 high: react-router, source-map-js, vite and others). `npm audit fix` without `--force` changed only `package-lock.json`; `package.json` is unchanged. After: **0 vulnerabilities**. `npm run build` exits 0. `npm run lint` gives 3 warnings (react-refresh export rules in provider files) and no errors. Nothing is left from the audit. There are no frontend unit tests in the repo (INFERRED from `package.json`, which has no test script).

## 5. Step 9: close-out checks (VERIFIED)
- **Mutation probe (serial, `tools/mutation_probe.py`):** I added 17 mutations for the Phase 3 code (M59-M75): planner flag default and parsing, direct planner step and index, `/health`, `retrieval_only` handling, count, route and index search, default template, abstention bare and mixed recognition, daily cap, breaker honoured, breaker opening on 429, the `PLANNER_COMPLETE_WITHOUT_ANSWER` finding, and the planner-instruction rule. Two problems showed up, both fixed:
  1. **My first run reported 17 of 17 killed, but a no-op control was also "killed".** A Step 4 test reads `eval/gold_set.jsonl`, which the probe's sandbox copy lacked, so every mutant failed for the wrong reason. I fixed the sandbox to copy `eval/`, and the probe now runs an unmutated control first and aborts if it does not pass.
  2. After the fix: **16 of 17 killed, M75 survived** ("retrieval_only searches no index"). The `retrieval_only` closure in the composition root had no direct test. I added `test_retrieve_only_searches_the_default_indexes_and_honours_top_k`, and M75 is now killed.
  Final: 17 of 17 killed, control survives. M1-M58 come from earlier phases and were not re-run here. Not covered by any mutant: the Cloud Run configuration, the frontend, and the 429 path against the real Gemini API.
- **Full suite, 3 consecutive runs:** 1034 passed each time; `scripts/` coverage 87% (>= 80 required). Run with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`.
- **Fresh venv:** a brand-new venv (Python 3.12.10, outside the repo, in the session scratch folder) was installed from `requirements.txt`, `requirements-local.txt` and `requirements-dev.txt` with the CPU-only torch index (torch 2.15.0+cpu); pip exit 0 (it logged several connection-reset retries and succeeded). The full suite then ran in that venv: **1034 passed, 87% coverage, exit 0**. The embedding model came from the existing local Hugging Face cache (offline flags set), so a first-time model download on a clean machine was NOT exercised here (the Docker build does that step and succeeded in Step 6).

## 6. Claims safe for a resume, and claims that are NOT safe
**Safe (each backed by a file above):**
- Built a hybrid BM25 + dense retriever and measured it on a frozen, split gold set: R@5 0.57 to 0.77 on the TEST split (no TEST-informed tuning for this comparison), with bootstrap CIs and paired tests (Phase 2).
- Verified that the deployed service returns the same retrieval results as the offline evaluation on all 66 gold questions (identical ranks), with zero LLM calls for the check.
- Deployed a containerised FastAPI RAG backend to Cloud Run (asia-south1) with IAM-only access, the API key in Secret Manager, scale-to-zero, one instance, a per-request call cap, and a daily LLM call cap with a 429 circuit breaker.
- Ran a pre-registered A/B of an LLM planner against no planner. It gave no improvement at about 3x the calls, so it ships off by default. Found and fixed a prompt gap in the planner using 3 recorded live responses and regression tests.
- 1034 automated tests (87% coverage of `scripts/`), a mutation probe with a control, and zero npm audit findings.

**NOT safe (do not claim):**
- That answers are accurate, grounded or free of hallucination. Correctness of answered replies on TEST was not hand-labelled, and the script proxy undercounts (Step 4).
- That the abstention works or meets its target. It **failed its own keep rule** (6/44 = 13.6% false refusals against the 10% limit). 8/8 unanswerable refused comes from n = 8, so the CI is wide. 2.1.0 was chosen after seeing 2.0.0 fail, so it is a post-hoc candidate.
- That the planner helps, or that it improved retrieval. It did not change refusals.
- That the system is production-grade, scalable or low-latency: one instance, in-memory state (observations, cache, conversations), free-tier Gemini (daily cap 10 in the service, 500 requests per day upstream), no load test, cold start 41 s, LLM latency measured with n = 2.
- Any statement about the answer quality shown in the Mode A UI (it showed groundedness 0 and quality 0.11 on a sensible answer, unexplained).
- That the corpus is licensed for redistribution: it is 6 documents, the licence is unconfirmed, and derived chunk text is inside a private image.
- Reranker gains (it is off, and R@5 got worse), or any multi-thread latency figure.
- That answers are deterministic. Gemini output is not bit-exact at temperature 0 (24 of 52 answers differed in wording between two runs). Refusal decisions matched, but do not claim determinism of answers.

## 7. GCP resources and IAM changes, with removal commands (project `sdg-align-fde`)
Use the full gcloud path if it is not on PATH. Order matters: delete the service first.

| Resource or change | Created in | Removal command |
|---|---|---|
| Cloud Run service `sdg-align-api` (revision `sdg-align-api-00001-hpd`, asia-south1) | Step 6 | `gcloud run services delete sdg-align-api --region asia-south1 --project sdg-align-fde` |
| Secret IAM binding: `sdg-align-run` has `roles/secretmanager.secretAccessor` on `gemini-api-key` | Step 6 | `gcloud secrets remove-iam-policy-binding gemini-api-key --member=serviceAccount:sdg-align-run@sdg-align-fde.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --project sdg-align-fde` |
| Service account `sdg-align-run` (no project roles) | Step 6 | `gcloud iam service-accounts delete sdg-align-run@sdg-align-fde.iam.gserviceaccount.com --project sdg-align-fde` |
| Secret `gemini-api-key` (1 version) | Step 6 | `gcloud secrets delete gemini-api-key --project sdg-align-fde` |
| Project IAM binding: default compute SA `44714566212-compute@developer.gserviceaccount.com` has `roles/cloudbuild.builds.builder` | Step 3 | `gcloud projects remove-iam-policy-binding sdg-align-fde --member=serviceAccount:44714566212-compute@developer.gserviceaccount.com --role=roles/cloudbuild.builds.builder --condition=None` |
| Artifact Registry repo `sdg-align` (images `api:v1`, `api:v2`, about 1.4 GB total, INFERRED) | Steps 3 and 6 | `gcloud artifacts repositories delete sdg-align --location asia-south1 --project sdg-align-fde` |
| Storage bucket `gs://sdg-align-fde_cloudbuild` (build source tarballs) | Steps 3 and 6 | `gcloud storage rm --recursive gs://sdg-align-fde_cloudbuild` |
| APIs enabled: `cloudbuild`, `artifactregistry`, `run`, `secretmanager` (all `.googleapis.com`) | Steps 3 and 6 | `gcloud services disable cloudbuild.googleapis.com artifactregistry.googleapis.com run.googleapis.com secretmanager.googleapis.com --project sdg-align-fde` (after deleting the resources above) |

Not created: no public access (`--no-allow-unauthenticated`, no `allUsers` binding), no Vertex AI, no Budget API, and no new resource in Steps 7-9 (I only read from the service, using my own identity token). The Gemini AI Studio key lives in `.env` (gitignored) and in the secret; revoke it in AI Studio when the project ends. Cost: INFERRED idle cost about zero (min instances 0) plus Artifact Registry storage. Billing was not checked.

## 8. Open items
- Groundedness 0 and quality 0.11 on a sensible live answer in the UI (unexplained).
- The frontend's 1.5 s mode-detection timeout can silently show sample data against a slow backend.
- 2.1.0 does not meet its keep rule. The real fix for cross-document refusals is retrieval that puts all needed passages in context; it was not attempted because retrieval was frozen.
- The fixed planner was only run with 2.1.0, and the quality of answered replies is not hand-labelled.
- The cause of the Q062 planner failure (a transient provider error, INFERRED) is not stored.
- The delay a request sees after scale-to-zero was measured only from startup logs. `min-instances=1` would remove it at a small standing cost (not done).
