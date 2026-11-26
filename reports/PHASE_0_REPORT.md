# Phase 0 Report: Foundation

Repository: `<repo root>` (new standalone repo, branch `phase-0-foundation`, 21 commits on top of the initial commit).
Final code commit: `d4b2224`; evidence-only commits after it (`d8d89b2`, `37d6085`).
Baseline for every "before" number: the review of the parent repo (`REVIEW.md` and its `review_artifacts/` in the parent repo). That folder is outside this repo.

---

## 1. Status

**DONE, with one caveat: CI was verified by simulation, not on GitHub.**

All four "done means" conditions are met (section 2). The caveat: "fresh-clone CI passes" was proven by cloning the branch into a new folder, creating a brand-new Python 3.12 venv, and running the exact workflow steps locally. No GitHub remote exists yet, so the workflow file itself has never executed on GitHub Actions (I only parsed it as valid YAML).

Also not done on purpose: nothing was pushed, no remote was created, the parent repo was not touched.

---

## 2. Done-means check

| # | Done means | Command | Output | Result |
|---|---|---|---|---|
| 1 | Fresh-clone CI passes | `git clone --branch phase-0-foundation <repo path> <tmp>`; new venv (3.12.10); `pip install -r requirements.txt`; `pip check`; `python -m pytest --cov --cov-report=xml --cov-fail-under=80` | install exit 0 (240 s, 60 distributions); `No broken requirements found.`; `744 passed, 1 warning`; `Required test coverage of 80% reached. Total coverage: 84.60%`; `pytest exit=0`; `coverage.xml` produced | **PASS** (simulated). Files: `reports/evidence/fresh_clone_install.txt`, `fresh_clone_pytest.log` |
| 2 | All tests pass | same, plus 3 plain runs in the fresh clone | `744 passed` x3 (17.85 s, 17.71 s, 18.06 s), 18 subtests passed each | **PASS**. File: `reports/evidence/stability_runs.txt` |
| 3 | Mutation probe shows M1, M2, M5, M13 killed | `python tools/mutation_probe.py` | `killed 13 / 13; survived: []` (M1 KILLED, M2 KILLED, M5 KILLED, M13 KILLED, plus the 9 that were already killed) | **PASS**. File: `reports/mutation/mutation_results.json` |
| 4 | Claims audit has no FALSE rows Phase 0 could fix | Section 8 below | every FALSE row from REVIEW 4.3 that is a wording or code-comment problem is corrected; remaining FALSE rows are behaviour, not wording | **PASS** (see 8 for the rows left open and why) |

---

## 3. What changed

54 files changed, +1,894 / -232 lines versus the initial commit.

| File(s) | Change | Why |
|---|---|---|
| *(new repo)* | Standalone repo created: 212 tracked files, 3.7 MB working tree. Excludes `data/`, all PDFs, `.env`, review material, `node_modules`, local tool folders. `.gitignore` covers raw PDFs and derived data, `.env*`, `review_artifacts/`, `node_modules/`, venvs. `.gitattributes` forces LF. | You asked for a clean history with no PDFs or secrets |
| `scripts/download_corpus.py` (+ README section) | Stub that lists the 13 expected PDFs with SHA-256, verifies placed files (`--check`), prints the manifest. **No download URLs**: none are invented | Source licence unconfirmed; lets the corpus be reproduced exactly |
| `requirements.txt`, `pyproject.toml` | One exactly-pinned file with every direct dependency (adds fastapi, uvicorn, pydantic, httpx, requests, numpy, pandas, python-dotenv, pytest-cov). `pyproject.toml` no longer holds a second list; gains pytest and coverage config | The old CI install could not run the backend tests; two lists had drifted |
| `.github/workflows/test.yml` | At the repo root; Python 3.12; clean install; `pip check`; `pytest --cov --cov-fail-under=80`; uploads `coverage.xml` | CI must be where GitHub looks, and gate on coverage |
| `scripts/stage9_vector_indexing.py` | `_rename_with_retry` for the directory swap; leftover-backup removal tolerates errors | Two tests failed intermittently on Windows (`WinError 5`) |
| `scripts/embedding_provider_huggingface.py` | `timeout=` on the HTTP call (default 30 s, configurable) | A stalled connection could hang a worker forever (bandit B113) |
| `scripts/backend_server.py`, `.env.example` | Blank/whitespace query or conversation_id and over-long query (`MAX_QUERY_CHARS`, default 4000) return 422; downstream `AgentPlanningInputError` returns 422; unexpected errors stay 500 with details hidden | Empty query returned 500; a 1 MB query was accepted |
| `scripts/stage21_agent_planning.py` | `datetime.now(timezone.utc)` with the same `...Z` format | Deprecated `utcnow()`; 51 warnings per run |
| `scripts/request_observability.py` | Observation store is a `deque(maxlen=1000)` | Unbounded list leaked memory |
| `scripts/composition_root.py`, `pipeline_deps_factory.py`, tests | Removed dead `build_retrieval_closures`/`retrieval_closures` (no production caller); removed 8 unused assignments (ruff F841) | Dead code from REVIEW 5.3 |
| `tests/` (6 files) | Rewrote the F821 test, the two "cannot fail" tests and the weak stage 6 test; each proven to fail when the behaviour it guards is broken | REVIEW 2.3 |
| `tests/test_stage7_chunking.py`, `test_stage10_retrieval.py` | 13 tests for chunk size bounds and the category filter | Kill M1, M2, M13, M5 |
| `scripts/stage10_retrieval.py` | `normalize_query_vector` (float32, unit length, rejects zero/NaN/inf/non-1-D) applied when the index metadata says `normalization: l2`; new `EmbeddingModelMismatchError` -> finding `INDEX_EMBEDDING_MODEL_MISMATCH` | Scores are only true cosines if the query is unit length; refuse to compare vectors from different models |
| `scripts/pipeline_deps_factory.py` | `make_provider_adapter_factory` actually checks `(provider, model, version)` against the wired adapter; it used to ignore its arguments | Enforce the embedding model at query time (your decision) |
| `scripts/composition_root.py` | Index discovery also matches `model_version` | Same |
| `src/stage_summary.py` (new) + stages 0-9 | `run_stageN()` returns a `StageSummary`; every CLI prints it and exits 0/1; `--strict` | Item E |
| `scripts/stage0_register.py` | A moved file (old path gone) updates category and `source_path`; a second copy is skipped as a duplicate | The Ecuador move would otherwise never change its category |
| `README.md`, `OPERATIONAL_READINESS.md`, `DEPLOYMENT.md`, `docs/pipeline_principles.md`, code comments | Claim corrections (section 8) | Item A |
| `tools/mutation_probe.py`, `reports/` | Mutation probe committed; results and evidence files | Reproducibility |
| `tests/test_stage_summary.py`, `test_download_corpus.py` | 24 tests (16 + 2 strict + 6) incl. real subprocess exit codes | New code needs tests |

---

## 4. Tests before / after

| | Before (parent repo, REVIEW) | After (fresh clone, final commit) | Source |
|---|---|---|---|
| Tests passed | 667 (+12 subtests) | **744** (+18 subtests) | `reports/evidence/fresh_clone_pytest.log`; before: `<parent repo>/review_artifacts\pytest_run1.log` |
| Failures / flaky | 0 in 3 runs | 0 in 3 runs + 1 coverage run | `reports/evidence/stability_runs.txt` |
| Warnings per run | 59 | 1 (Starlette `httpx` deprecation, not ours) | same logs |
| Coverage (line + branch) | 83% | **84.60%** | `coverage_before_after.txt`, log |
| Mutations killed | 9 of 13 | **13 of 13** | `reports/mutation/mutation_results.json`; before: `review_artifacts/mutation_results.json` |
| Net new tests | | **+77** | suite totals per commit: 667, 670, 673, 680, 681, 683, 682, 684, 697, 717, 733, 736, 738, 744 |

New tests by area: stage 9 retry (+3), HF timeout (+3), API validation (+7 net), `_now()` (+1), observation cap (+2), removed dead-code test (-1), rewritten tests (+2), mutation-killing (+13), retrieval normalisation and model guard (+20), stage CLI (+16, later +2), stage 0 move (+3), download stub (+6).

Modules at or below 80% before, and now (full table: `reports/evidence/coverage_before_after.txt`):

| Module | Before | After |
|---|---|---|
| stage10_retrieval | 58% | 74% |
| composition_root | 67% | 76% |
| stage3_detection | 66% | 76% |
| stage0_register | 62% | 69% |
| stage9_vector_indexing | 70% | 71% |
| stage20 | 78% | 80% |
| stage2 / stage1 / stage4 | 70 / 71 / 79 | **68 / 69 / 78 (went down)** |
| llm+planner providers (groq, openrouter) | 63-68% | unchanged |

The stage 1/2/4 dips are the new summary wiring: it runs in `__main__` and in subprocess tests, which are deliberately not measured by pytest-cov. Still under 80%: composition_root, 4 provider modules, stage 0, stage 10.

---

## 5. Measured results

| Number | Value | Source file |
|---|---|---|
| Tests passed in a fresh clone | 744 | `reports/evidence/fresh_clone_pytest.log` |
| Coverage | 84.60% (gate 80%) | same |
| Plain-run stability | 744 x 3, 17.7-18.1 s each | `reports/evidence/stability_runs.txt` |
| Mutations killed | 13 / 13 | `reports/mutation/mutation_results.json` |
| Rewritten tests caught the break | 5 / 5 deliberate breaks caught | `reports/evidence/break_it_demo.txt` |
| Ecuador move on a real-data sandbox copy | manifest category `climate` -> `biodiversity`; all 91 chunk records `climate` -> `biodiversity`; chunk text and chunk ids identical; both `index.bin` SHA-256 unchanged; **0** embedding API calls; stage 0/6/7/8/9 all exit 0 | `reports/evidence/ecuador_move_check.json` |
| CLI exit codes (live) | corrupt PDF: stage 1 exit **1**; scanned PDF: stage 3 exit **0**; same manifest with `--strict`: exit **1**, lists both quarantined docs | `reports/evidence/cli_exit_code_demo.txt` |
| Fresh install | brand-new Python 3.12.10 venv, 60 distributions, `pip check` clean, 240 s | `reports/evidence/fresh_clone_install.txt` |
| New repo size | 212 tracked files, 3.7 MB working tree | `git ls-files`, `du` (not saved as a file) |

The ~3 failures in 8 runs of the Windows rename flake were observed during this session but **not saved to a file**, so they are not citable.

---

## 6. Cost and resources

- **API spend: $0.** No Hugging Face, Gemini, Groq or OpenRouter call was made. The Ecuador check used the real HF adapter with `requests.post` patched to raise, and the call counter stayed at 0.
- **Network:** `pip install` only (240 s for the fresh venv), plus git operations on local folders.
- **Disk outside the repo** (safe to delete): a Python 3.12 venv, a second fresh-clone venv, two fresh clones, and the sandbox copies under the session scratchpad; each venv is roughly 0.5 GB. The old repo's `review_artifacts/` (about 700 MB) is untouched.
- **Time:** the suite takes 17-27 s; the full mutation probe takes several minutes (13 isolated runs; run twice; not timed precisely). Total elapsed time for the phase was not measured.
- **Secrets:** none read or written. `.env` was not copied. A key-pattern scan of the initial copy found nothing; no later commit adds credentials.

---

## 7. What did not work or is still open (blunt)

**Things that went wrong during Phase 0 and how they were caught**
1. **An intermittent Windows failure existed** (`PermissionError` on renaming a just-written directory in stage 9): it hit 3 of the first 8 runs in the new repo, none in the review's 3 runs. Fixed with a bounded retry. The cause (antivirus or indexer locking a fresh directory) is inferred, not confirmed.
2. **The F821 test passed for the wrong reason.** Fixing the import was not enough: the test fed a FAIL prompt package, so the LLM was never called and the exception path never ran. Rewritten.
3. **The first M1 test attempt did not kill M1.** The mutation is nearly equivalent: the splitter has a second redundant length check. The only visible difference was that the mutant resets the `degenerate` flag on spans that were not split, so a test for that was added. The redundant guard could be removed later.
4. **My new subprocess tests broke coverage collection** (pytest-cov could not combine non-branch child data). The 744 tests passed, but the CI coverage step would have crashed. Found only because I ran the CI steps in a fresh clone.
5. **`--strict` was wrong on re-runs** (it skipped already-quarantined documents and exited 0). Found by a live demo, fixed to look at the whole manifest.
6. A commit message says "18 new tests" for the retrieval change; the real count is 20 (parametrised cases). Cosmetic.

**Not fixed, by scope**
- **Jaguar document** (`ecuador_jaguar_landscape_connectivity.pdf`) still fails stage 6 (`DUPLICATE_SECTION_ID`), and stage 6 labels any validation failure `FATAL_UNREADABLE`, which is misleading. Chunking and structure redesign are out of scope.
- **Retrieval quality is unchanged**: about 25% boilerplate in the top-5, no abstention. No measurement exists yet.
- **Stage 10 is still 74% covered**: the real FAISS search, `resolve_index_fingerprints` and `list_available_indexes` are untested.
- **Security and cost items from REVIEW remain open**: no auth, prompt injection, no single-flight on the cache (concurrent identical misses make several paid LLM calls), timeout does not cancel the LLM call, in-memory state per instance.
- **The frontend was not touched or rebuilt** in the new repo (no `node_modules` there), CI does not build it, it has no tests, and four UI strings still say "deterministic".
- **Python 3.11 not tested** (not installed). Final verification was on 3.12 (CI target) only; early commits were also run on 3.14.
- **The mutation probe is cheap**: 13 hand-picked textual mutations, not a mutation-testing tool. 13/13 says nothing about all the others.
- **Mutation results were produced on commit `9347d37`**; later commits only add tests, but the probe was not rerun after them.
- **The parent repo and its remote** (`origin = github.com/aqe17za/sdg-align-ai-platform`) still contain the 13 PDFs plus 44 derived files, and its history keeps them. If that repo is public, removing them needs a history rewrite and force-push. I did nothing there.
- **`docs/ARCHITECTURE_BLUEPRINT.md`** (copied into the new repo) contains the line "every component must be explainable in one sentence in an interview". I left it; you may not want it in a public doc.
- About 110 "byte-identical" mentions in `docs/architecture/*.md` were not rewritten; only the shared principle doc carries the correction.

---

## 8. Doc and claim updates

| Claim (where) | Before | Now |
|---|---|---|
| "Stateless" (`backend_server.py`, `composition_root.py` comments) | FALSE | Reworded; README now has "Process-local state". **The state itself is unchanged** (still in memory, per instance) |
| "byte-identical output" (README, 2 places) | FALSE for rebuilds | README "Determinism" section: content deterministic, files differ in timestamps, hosted APIs excluded; `pipeline_principles.md` corrected |
| "633 tests" (OPERATIONAL_READINESS) | FALSE (stale) | 744 (with the historical 633 labelled) |
| "no production index" / "ships a 4-dim stub" (OPERATIONAL_READINESS, DEPLOYMENT) | FALSE | States the truth: the repo ships no corpus or index; a local 384-dim HF index existed |
| "Phase 1 has no required environment variables" (README) | FALSE | Lists what the backend needs vs tests |
| "No paid services or API keys are required" (README) | PARTLY TRUE | Tests need none; ingestion and the backend need provider credentials |
| "Three Gemini registrations" docstring | FALSE | Fixed |
| "Groundedness / answer quality / citation extraction" (README stage table) | TRUE-but-misleading | Rows now say lexical overlap and structural score, not correctness |
| 8 quarantined documents `FATAL_UNREADABLE` (DEPLOYMENT) | FALSE | 7 scanned (`FATAL_NO_TEXT`) + 1 stage 6 failure |
| "Fully tested pipeline" | PARTLY TRUE | Unchanged wording; now backed by 744 tests and 13/13 mutations, still no retrieval-quality tests |

**FALSE or PARTLY TRUE rows left, and why**
- **"Multi-agent", "ReAct", "self-reflection"**: the repo's own docs never claim these. It is a single planner loop with an empty tool registry. Do not use that wording on a resume.
- **"Concurrency-safe cache"**: the code docstring only claims GIL-level safety; there is still no single-flight. A behaviour fix, not a wording fix.
- **Frontend "deterministic" strings and "Mode A/B/C tested"**: frontend is out of scope for Phase 0.

---

## 9. Resume-safe facts (with proof files)

Safe, because each has a saved file:
1. "Grew the test suite from 667 to 744 tests; line+branch coverage 83% -> 84.6%, with an 80% CI gate." Proof: `reports/evidence/fresh_clone_pytest.log`; baseline `review_artifacts/pytest_run1.log` (parent repo).
2. "Built a mutation probe over 13 critical functions; 4 initially survived, all 13 are now killed." Proof: `reports/mutation/mutation_results.json`, `tools/mutation_probe.py`; baseline `review_artifacts/mutation_results.json` (parent repo).
3. "Ingestion CLIs exit non-zero on failed documents (with an expected-quarantine policy and `--strict`)." Proof: `reports/evidence/cli_exit_code_demo.txt`.
4. "Verified a fresh clone builds in a clean Python 3.12 venv (60 packages, `pip check` clean) and passes the suite." Proof: `reports/evidence/fresh_clone_install.txt`, `fresh_clone_pytest.log`. Say "simulated locally", not "on GitHub Actions".
5. "A document move re-categorised the corpus without changing the vector index (byte-identical `index.bin`, zero embedding calls)." Proof: `reports/evidence/ecuador_move_check.json`. It ran on a sandbox copy.

**Not resume-safe**: retrieval quality, answer quality, anything about latency or cost, "deployed", "multi-agent", "stateless", "prompt-injection hardened", and the Windows flake rate.

---

## 10. What I must understand

Kept out of the repository by decision (private study notes, local only).

---

## 11. Next phase preview and what I need from you

**Proposed Phase 1 (adjusted from REVIEW 5.1): make quality measurable.** Gold set of 50-100 questions on the 5 indexed documents, an eval harness (recall@k, MRR, answer correctness with human labels), then run the planner against a no-planner baseline. In parallel the cheap security fixes: delimit untrusted chunk text, server-generated conversation ids, single-flight on the cache.

**Things I need from you**
1. **Create the GitHub remote.** Nothing is pushed until the project owner decides. That unlocks a real Actions run.
2. **Where are the 13 PDFs locally** (to rebuild the corpus and the index in the new repo), and may I re-run stage 8 with the local `bge-small` model instead of the HF API so it costs nothing?
3. **Is the old GitHub repo (`aqe17za/sdg-align-ai-platform`) public?** If so, a history rewrite plan to remove the PDFs and derived files is needed.
4. **Should `reports/PHASE_0_REPORT.md` and `LEARN_0.md` be committed?** I left both untracked because they contain interview Q&A and you asked to keep interview material out of the new repo.
5. **Keep or remove the "explainable in an interview" line** in `docs/ARCHITECTURE_BLUEPRINT.md`.
6. **Exit-code policy OK?** (`FATAL_NO_TEXT` exits 0; `--strict` fails on any quarantine.)
7. **Who labels the gold set**, and do you want an LLM judge as a second opinion?
8. **License choice** (since resolved: the code is MIT-licensed, see `LICENSE`) and the author/contact details in the README.
