# Phase 3 Step 6: Cloud Run deploy (DONE; smoke test passed)
Labels: VERIFIED = from a command or test run in this pass. No git. The key value was never read or printed by me.

## Code changes before the build (api:v2), each with a test (tests/test_phase3_serving.py + 3 updated wiring tests)
| Change | Detail |
|---|---|
| Planner flag | `PLANNER_ENABLED` (default false). Off = `scripts/direct_planner.py`, a deterministic planner (1 QUERY_PIPELINE step, then COMPLETE), 0 planner LLM calls. On = the Gemini planner as before. `choose_planner_adapter` in composition_root. |
| `GET /health` | `{"status":"ok"}`, no model, retrieval or embedding call. |
| `retrieval_only` | request field `"retrieval_only": true` on POST /run-query returns ranked chunks, `llm_calls: 0`, no planner, no answer model. |
| Default template | `DEFAULT_TEMPLATE_VERSION = "2.1.0"`. Did NOT meet the keep rule (6/44 false refusals, 13.6%, limit 10%); stated in README and here. |
Three existing wiring tests (call_budget, composition_root, quota_guard) now set `PLANNER_ENABLED=true`, since they test the LLM-planner wrapping. Suite: 1032 passed; scripts coverage 86% (VERIFIED).

## GCP changes made (remove at project end)
| Action | Command | Status |
|---|---|---|
| Enable APIs | `gcloud services enable run.googleapis.com secretmanager.googleapis.com --project sdg-align-fde` | VERIFIED |
| Create empty secret | `gcloud secrets create gemini-api-key --replication-policy=user-managed --locations=asia-south1` | VERIFIED |
| Secret value | added by the project owner; only the versions were listed (version 1 enabled), the value was never read; temp file confirmed deleted | VERIFIED |
| Service account | `gcloud iam service-accounts create sdg-align-run` (no project roles) | VERIFIED. Remove: `gcloud iam service-accounts delete sdg-align-run@sdg-align-fde.iam.gserviceaccount.com` |
| IAM binding (the only one) | `gcloud secrets add-iam-policy-binding gemini-api-key --member=serviceAccount:sdg-align-run@sdg-align-fde.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor` | VERIFIED. Remove: same with `remove-iam-policy-binding` |
| Build | one Cloud Build, id d0cabe43-f58c-45c7-b4fd-c8e048238fe3, 6m08s, SUCCESS; image `.../sdg-align/api:v2`, digest `sha256:3a83885e20f90070776842ab8f70a198b213e726d9e3edc787e73944e513de91`; log `reports/evidence/cloudbuild_v2.log` | VERIFIED |
| Deploy | service `sdg-align-api`, revision `sdg-align-api-00001-hpd`, asia-south1, `--no-allow-unauthenticated`, max-instances 1, min-instances 0, 2 CPU / 2 Gi, timeout 120 s, SA sdg-align-run, env NETWORK_CALLS_PERMITTED=true, LLM_PROVIDER=gemini, LLM_PROVIDER_CREDENTIAL_REF=env:GEMINI_API_KEY, LLM_PROVIDER_EXTRA_MODEL=gemini-3.5-flash-lite, MAX_LLM_CALLS_PER_REQUEST=2, DAILY_LLM_CALL_CAP=10, PLANNER_ENABLED=false; key mounted from Secret Manager only | VERIFIED. Remove: `gcloud run services delete sdg-align-api --region asia-south1` |
URL: https://sdg-align-api-44714566212.asia-south1.run.app (IAM-authenticated only). The smoke calls used the project owner's own identity token; no run.invoker grant was made to anyone.
Nothing else changed: no public access, no other roles, Vertex AI not used.

## Smoke test (eval/results/step6_smoke.json, tools/cloud_smoke.py; DEV items only; token never printed or stored)
Note on files: the first run printed the six first-phase records but its JSON write was cut off by a closed pipe on my side. Those six records are saved in `step6_smoke_first.json` from the console output; the warm repeats were then re-run alone (no extra LLM calls) and merged into step6_smoke.json.
| Check | Result (VERIFIED) |
|---|---|
| GET /health | 200 `{"status":"ok"}` |
| LLM question Q007 | 200, agent status PASS, 1 step, 5.07 s |
| LLM question Q008 | 200, agent status PASS, 1 step, 2.30 s |
| Retrieval-only Q013, Q017, Q022 | 200 each, `llm_calls: 0`, 10 chunks each, about 1.0 s each (new connection each) |
| Warm /health, 10 calls, one reused connection | p50 48 ms, p95 900 ms (the max is the first call, which opens the TLS connection), max 900 ms |
| Warm retrieval-only, 10 calls, reused connection | median 111 ms, max 151 ms (n = 10; too few for a p95) |
| LLM requests, warm | only 2 samples (5.07 s and 2.30 s); p50/p95 are not meaningful at n=2. I limited LLM calls to 2 to protect DAILY_LLM_CALL_CAP=10 and the free-tier quota |
| Cold start | VERIFIED from Cloud Run logs of the deploy rollout: instance start 13:19:34.85, process started +13 s, startup checks plus embedding model load +28 s, ready at 13:20:16.17: **41.3 s**. A first request after scale-to-zero waits about that long (within the 120 s request timeout). The smoke requests themselves hit an already-warm instance, so a request-level cold start was NOT measured (UNKNOWN beyond the startup log) |
Daily LLM cap use in the service so far: 2 of 10 (INFERRED from the 2 requests; the cap counter is in process memory and resets on a new instance).
Not checked: concurrency under load, the Gemini 429 path on Cloud Run, billing (INFERRED: idle cost 0 with min-instances 0; the image adds Artifact Registry storage of about 1.4 GB across v1 and v2).
Step 7 (served-path check), the frontend and close-out are NOT started.
