# Phase 2.5 report: hardening before deploy

No GCP, no paid call, no network except `pip` (fresh venv). No git command was run. Everything is uncommitted.
Labels: VERIFIED = produced by a command in this pass.

## What changed (file | why)

| File | Why (fix #) |
|---|---|
| `requirements-dev.txt` | `scipy==1.18.1` (same as your venv); CI never installed it (1) |
| `tests/test_requirements_declared.py` (new) | Fails if scipy is not pinned in the CI install set; every CI requirement must be pinned exactly (1) |
| `.env.example` | `EMBEDDING_PROVIDER=local`, `NETWORK_CALLS_PERMITTED=false`, LLM/planner blocks commented out as opt-in, paid vs free labelled (2) |
| `README.md`, `DEPLOYMENT.md` | Configuration section now matches `.env.example` (local embedder, opt-in, cap, fail-fast) (2); Mode A claim and test count corrected (9) |
| `OPERATIONAL_READINESS.md` | Mode A rows no longer "verified"; test count (9) |
| `scripts/startup_checks.py` (new) | Refuses to start if manifest/chunks/index missing or empty, or the index's embedding model differs from the configured one (3) |
| `scripts/backend_server.py` | Runs the checks, then loads the embedder at startup (3, 6) |
| `scripts/composition_root.py` | Validates `RETRIEVAL_MODE` in every configuration (4); wraps LLM and planner adapters with the call cap (5) |
| `scripts/phase1_1_configuration_layer.py` | `NETWORK_CALLS_PERMITTED` defaults to `false` (5) |
| `scripts/call_budget.py` (new), `scripts/runtime_orchestration.py` | Hard per-request cap on planner + answer LLM calls, retries included: `MAX_LLM_CALLS_PER_REQUEST`, default 6 (5) |
| `scripts/embedding_provider_local.py` | Offline forced in code, `local_files_only=True`, clear error for a missing model, `warm_up()`; download only with `ALLOW_MODEL_DOWNLOAD=true` (6) |
| `scripts/stage10_retrieval.py` | FAISS index kept in memory, reloaded when `index.bin` path/mtime/size changes (7) |
| `tools/index_cache_check.py` (new), `reports/evidence/index_cache_check.json` | Proof for fix 7 (7) |
| `venvssdg-alignScriptsActivate.ps1` | Deleted (8) |
| `tools/mutation_probe.py` | Mutants M41-M58; copies `requirements*.txt`; per-mutant pytest temp dir (10) |
| `reports/PHASE_2_REPORT.md` | Stale "35 mutants" note corrected (9) |
| `tests/test_startup_checks.py`, `test_call_budget.py` (new); additions to `test_embedding_provider_local.py`, `test_stage10_retrieval.py`; one assertion in `test_composition_root.py` | Tests for fixes 3-7 |

## Tests

| | Before | After |
|---|---|---|
| Suite (repo venv, offline) | 888 passed | **944 passed**, 3 plain runs identical (VERIFIED) |
| CI-scope coverage | 85.76% (Phase 2 report) | **86.43%** (`--cov-fail-under=80` met) |
| **Brand-new venv, `requirements.txt` + `requirements-dev.txt` only** | not tested (scipy missing) | `pip check` clean; **942 passed, 2 skipped** (needs the real corpus; needs the real model), coverage **86.34%** |

The fresh-venv run used a copy of the final code without `data/`, `.git` or the local-embedding packages. It is the CI command run locally; it has still never run on GitHub.
A bug I found and fixed on the way: my new server-exit subprocess test broke coverage collection (child process coverage data). The test now strips the coverage hooks from the child.

## Fix 7 proof (`reports/evidence/index_cache_check.json`)
- All 66 gold queries (52 test + 14 dev), top-50 hybrid: **identical chunk ids and scores with cache off and on** for every query.
- Latency (alternating passes, model already loaded, 5 passes): p50 **58.8 ms off, 57.2 ms on**; p95 92.7 vs 92.2 ms. The gain is about 1.5 ms: the 767 KB index is already in the OS file cache and embedding the query dominates. Keep the change for correctness at scale, but do not claim a speedup.

## Mutants
Probe now holds **58** (40 before). New M41-M58 cover: missing-index, mismatch, empty-manifest, empty-chunks checks removed; server skipping checks or warm-up; mode validation skipped; network default flipped to true; cap ignored, default raised, invalid value unlimited, budget not activated; offline removed, `local_files_only` ignored; index cache key ignoring file changes, never hitting, off by default; scipy pin removed.
**18 / 18 killed, 0 survived.** Two test-quality problems were found and fixed first: an unbounded loop in my own test hung one mutant (now bounded), and the probe's mutant copies did not include `requirements*.txt`. Note: results come from several probe invocations (parallel runs collided on pytest's shared temp folder and gave false SETUP_ERRORs; those were rerun serially/alone). No single combined results file exists for M41-M58.

## .gitignore lines for you to add
```
reports/ONBOARDING_UNDERSTANDING.md
LEARN_*.md
venvss*.ps1
```
(`LEARN_*.md` is already in `.gitignore`; the stray file is deleted, the third line only guards against a repeat.)

## Choices I made (your "safest option" rule)
- Call cap default **6** (a normal request is 3: plan, answer, plan-complete); invalid values fall back to 6, never to unlimited.
- With the safe defaults the server starts with the local embedder only: no LLM/planner, so `/run-query` cannot answer until you opt in. That is intended.
- Model download is blocked unless `ALLOW_MODEL_DOWNLOAD=true` (needed once for a Docker build or a new machine).
- Mode A claim: no evidence file exists in the repo, so README now says not verified end to end.

## Still open
- Phase 3: Vertex AI via ADC (Gemini adapters still use API keys), Dockerfile, real end-to-end run, answer-level abstention, planner measurement.
- CI has never run on GitHub. `npm audit` findings, no auth, in-memory state, timeout does not cancel an LLM call (the cap bounds the cost, not the wait).
- Startup checks verify file presence and metadata, not that vectors are valid; `build_pipeline_deps` still validates mode a second time from `os.environ`.
- Fix 7 gave no measurable latency gain at this corpus size.

## Files to commit (all currently uncommitted)
Modified: `.env.example`, `README.md`, `DEPLOYMENT.md`, `OPERATIONAL_READINESS.md`, `requirements-dev.txt`, `scripts/backend_server.py`, `scripts/composition_root.py`, `scripts/phase1_1_configuration_layer.py`, `scripts/runtime_orchestration.py`, `scripts/embedding_provider_local.py`, `scripts/stage10_retrieval.py`, `tools/mutation_probe.py`, `tests/test_composition_root.py`, `tests/test_embedding_provider_local.py`, `tests/test_stage10_retrieval.py`, `reports/PHASE_2_REPORT.md`.
New: `scripts/call_budget.py`, `scripts/startup_checks.py`, `tests/test_call_budget.py`, `tests/test_startup_checks.py`, `tests/test_requirements_declared.py`, `tools/index_cache_check.py`, `reports/evidence/index_cache_check.json`, `reports/mutation_results_M41_*.json` files, `reports/PHASE_2_5_REPORT.md`.
Plus whatever from the earlier serving fix is still uncommitted (`scripts/pipeline_deps_factory.py`, `tests/test_pipeline_deps_factory.py`, `reports/mutation_results_M36_M37_M38_M39_M40.json`, README/report edits).
Do not commit: `reports/ONBOARDING_UNDERSTANDING.md`, `.coverage`, `coverage.xml`.

Commit message: `Phase 2.5 hardening: fail-fast startup, LLM call cap, network opt-in, offline embedder, index cache, scipy pin`
