# Phase 1 report: chunk and data quality

Branch `phase-1-chunk-quality` (cut from `phase-0-foundation`), repo `sdg-align`. Nothing pushed; no GitHub remote.
Labels: VERIFIED = produced by a command whose output is in a file named here; INFERRED = my reading of verified facts; UNKNOWN = not measured.
Python venv for everything in this phase: `<venv outside the repo>` (CPython 3.12, outside the repo, 1.6 GB).

## 1. Status

**DONE, with one result that is not what was hoped.** The done-means is met (tests pass, 6 documents indexed, before/after table). The chunks are
measurably cleaner. The retrieval-usefulness gain is small and **not statistically significant**: cleaning-only mean usefulness 0.94 to 1.05 on a 0 to 2
scale over 13 questions, exact Wilcoxon p = 0.32 (VERIFIED, `reports/evidence/judging/results_cleaning_only.md`). I do not claim retrieval improved.
Why: cleaning removes noise but does not add answer-bearing passages, and for several questions no passage in the corpus states the answer.
There is no human label anywhere in this phase; usefulness is AI-judged (section 7).

## 2. Done-means check

| # | Check | Command | Output | Result |
|---|---|---|---|---|
| 1 | Tests pass | `pytest --cov` (3 runs, `reports/evidence/suite_3_runs.txt`) | `813 passed, 18 subtests passed` x3; coverage 85% (lines 87.8%, branches 79.2%) | **PASS** |
| 2 | Fresh clone, exactly the CI install steps | clean 3.12 venv, `pip install -r requirements.txt`, `-r requirements-dev.txt`, `pip check`, `pytest --cov --cov-fail-under=80` (`fresh_clone_phase1_final.log`) | install 179 s, 60 packages, `No broken requirements found.`; `812 passed, 1 skipped` (the skip is the real-model test: optional deps absent, skipped with a stated reason); `Required test coverage of 80% reached. Total coverage: 85.29%`; pytest exit 0 | **PASS** (local simulation of the CI steps, not run on GitHub) |
| 3 | 6 documents indexed | `index_metadata.json` of the rebuilt index | `document_count 6`, `chunk_count 497`, provider `local`, `BAAI/bge-small-en-v1.5` v1.5, 384 dims | **PASS** |
| 4 | Before/after table | `tools/chunk_metrics.py`, `tools/retrieval_eval.py`, `tools/compute_*.py` | tables in section 5 | **PASS** (shows a small, non-significant retrieval gain) |
| 5 | Mutation probe | `tools/mutation_probe.py` (`reports/mutation/mutation_results.json`) | 21 of 21 killed, each by a failing assertion | **PASS** |
| 6 | No secrets, PDFs, `LEARN_*.md` or `PHASE_1_PROGRESS.md` tracked | `git ls-files` filtered; `git check-ignore` | only `.env.example` matched; the others are ignored | **PASS** |

## 3. What changed (every commit on the branch since `phase-0-foundation`)

| Commit | File(s) | Change | Why |
|---|---|---|---|
| `ed342c8` | `reports/evidence/metrics_definitions.md` | Metric definitions frozen before any measurement | Stop me tuning rules to a number |
| `a356325` | `tools/chunk_metrics.py`, `tools/retrieval_eval.py`, `retrieval_before.json` | Chunk metrics, 15-question eval, Phase 0 baseline | Need a measured "before" |
| `e259e23` | `scripts/stage4_cleaning.py` | Remove `Page x of y` markers and HTML residue | 172 footer-residue and 173 HTML-residue chunks in baseline |
| `484145b` | `scripts/stage4_cleaning.py` | Remove table of contents and GEF template instructions | Boilerplate in retrieved passages |
| `717d8f3` | `scripts/stage4_cleaning.py` | Markdown tables become `Header: value` row text | 150 table-markup chunks |
| `628c11e` | `scripts/stage4_cleaning.py`, `tools/reset_for_rerun.py` | Cut footers glued into sentences; no blank-line piles; re-run helper | Remaining footer residue; fast re-runs |
| `a5bf7c2` | `scripts/stage7_chunking.py` | Heading-only spans merge forward; small spans merge within the branch | Tiny fragments |
| `bfa4a3a` | `scripts/stage7_chunking.py` | Split at sentence ends, pieces of at least 300 chars, table rows kept whole | 56.2% mid-sentence endings |
| `159c137` | `scripts/stage7_chunking.py` | Drop exact-duplicate chunks inside a document and record the ranges | 12 duplicate surplus |
| `5c453c9` | `reports/evidence/chunk_metrics_after_d3.json` | Record metrics after the merge/split/dedupe | Evidence |
| `7db8773` | `scripts/stage7_chunking.py` | Drop chunks under 300 chars that are only Markdown headings, record ranges | 9 annex-heading fragments |
| `74342ac` | `scripts/stage5_structure.py` | Repeated section ids get `-2`, `-3` suffixes | Jaguar failed `DUPLICATE_SECTION_ID`; other 5 documents' ids unchanged (`section_ids_unchanged_check.txt`) |
| `d790d98` | `scripts/stage6_validation.py`, `src/ingestion_types.py`, docs | Stage 6 failure sets `FAILED_VALIDATION`, not `FATAL_UNREADABLE` | A readable-but-inconsistent document is not an unreadable one |
| `94dd0d7` | `requirements*.txt`, CI workflow, `.gitignore`, README | Test tools moved to `requirements-dev.txt`; CI installs both; progress file ignored | Cleaner install surface |
| `5b54886` | `frontend/src/**` | "Deterministic" and "575 tests, GitHub CI confirmed" claims reworded | They were not true (CI never ran on GitHub) |
| `ac9c259` | `scripts/embedding_provider_local.py`, `scripts/backend_server.py`, `requirements-local.txt`, tests | Local sentence-transformers provider behind the adapter seam | Free, deterministic embeddings for stage 8 and query time |
| `3bfa1a7` | `tools/hash_build.py`, evidence files | Rebuild stages 4 to 9, determinism hashes, parity vs old HF vectors, `retrieval_after.json` | The "after" measurement |
| `15fc483` | `tools/make_blind_files.py`, blind files | Anonymised shuffled before/after file and sealed key | Blind protocol |
| `4d48441` | `blind_labels_ai_judge1.json` | Judge 1 labels, saved before the key was opened | Blind protocol. File renamed on 2026-11-25; content unchanged. |
| `fdb2a1c` | `frontend/src/**` | Stale index fingerprint and embedding row corrected | Checked against real data |
| `63a42ac` | `judging/PROTOCOL.md`, packet, rubric, checker, prompt builder | AI-judge protocol and kappa thresholds committed before any judge ran | Pre-registration |
| `8e8ce10` | `judging/labels_judge1_*.json` | Judge 1 re-derived by the frozen rubric alone (4 ids changed) | Remove my non-frozen rule |
| `91ea01b` | `judging/raw/calibration_judge2.json` | 6-item calibration run | Catch a misread rubric early |
| `47511f8` | `judging/labels_judge2*.json`, `tools/judge_agreement.py`, probe | Judge 2 (144 items), Judge 2b (30), agreement tool and tests, 8 new mutations | Independent judge, self-consistency |
| `73adbd4` | `judging/agreement*.json`, `disputed_ids.json` | Judge 1 vs Judge 2 agreement; disputed ids | Adjudication input |
| `8f6d0ef` | `judging/labels_judge3_disputed.json`, `labels_final.json` | Judge 3 adjudication and final labels, before unblinding | Final labels |
| `22d4652` | `tools/compute_phase1_results.py`, `tools/build_final_labels.py`, tests | Exact sign and Wilcoxon tests, final-label rule | Compute after the key opens |
| `a19d98a` | `judging/results*`, `rank1_investigation.txt`, `tools/rank1_investigation.py` | Unblinded results; rank-1 investigation | Results |
| `a2f0385` | README, DEPLOYMENT, OPERATIONAL_READINESS, `docs/architecture/stage4/5/7` | Doc drift fixed (test counts, local embedder, new rules) | Honest docs |
| `dc15a1a` | `tools/mutation_probe.py`, `tools/jaguar_contribution.py` | Probe copies `tools/`, counts only a failed assertion as KILLED | First full run reported false kills |
| `b9080a2` | `retrieval_after_5doc.json`, `tools/cleaning_only_new_items.py`, `tools/build_judge_prompt.py` | 5-document index from the after pipeline; 4 new passages | Remove the jaguar confound |
| `0cb72cd` | `judging/labels_judge4_cleaning_only_new.json` | Judge 4 labels for the 4 new passages, before computing | Label new passages in isolation |
| `1789167` | `tools/compute_cleaning_only.py`, `results_cleaning_only.*` | Cleaning-only comparison | Headline comparison |
| `4ef8c65` | `reports/mutation/mutation_results.json`, probe log | 21 of 21 mutations killed | Test strength |
| `c4bf5f0` | `reports/evidence/suite_3_runs.txt` | Suite run three times | Stability |
| (this report) | `reports/PHASE_1_REPORT.md` | The report | Close-out |

## 4. Tests

| | Phase 0 end | Now | Source |
|---|---|---|---|
| Tests | 744 | **813** (x3 runs, same result); fresh clone 812 passed + 1 skipped | `fresh_clone_pytest.log` (Phase 0), `suite_3_runs.txt` |
| Coverage | 84.6% | 85% total (lines 87.8%, branches 79.2%) | `coverage_before_after.txt`, `suite_3_runs.txt` |
| Mutations killed | 13 of 13 | **21 of 21** (8 added for Phase 1 rules) | `reports/mutation/mutation_results.json`, `mutation_probe_run.log` |

New mutations: M14 duplicate drop off, M15 heading-only drop off, M16 sentence-end preference off, M17 section-id disambiguation off,
M18 inline HTML not stripped, M19 table-of-contents removal off, M20 stage 6 failure code reverts, M21 local embedder not normalising.
The first full probe run printed "killed" for everything because the mutated copy lacked `tools/` and died at test collection; that was a false result,
fixed in `dc15a1a`, and the table above is from the corrected run (each kill is a failing assertion).

New tests, by file (69 test functions on this branch): `tests/test_stage4_cleaning_rules.py` (page markers, HTML, table of contents, template instructions,
table rows, glued footers: 25 tests, e.g. `test_toc_threshold_is_exactly_three_leader_lines`, `test_table_with_header_becomes_header_value_rows_in_place`);
`tests/test_stage7_chunk_quality.py` (merge, split, duplicates, heading-only drop, coverage proof, 2 end-to-end: `test_heading_only_span_is_dropped_and_range_reported`,
`test_chunk_document_drops_a_trailing_heading_only_section_and_still_passes_validation`);
`tests/test_stage5_structure.py::TestRepeatedSectionIds` (4: `test_two_and_three_repeats_get_occurrence_suffixes`, `test_nested_repeats_stay_unique_and_parents_resolve`, ...);
`tests/test_embedding_provider_local.py` (11, including `test_index_guard_accepts_the_local_adapter_and_rejects_another_model`);
`tests/test_judge_agreement.py` (4), `tests/test_phase1_stats.py` (3); `tests/test_stage_summary.py::test_failed_validation_is_a_failure_not_an_expected_quarantine`;
`tests/test_stage6_validation.py` (default failure code now `FAILED_VALIDATION`).
The new stage 4, 5 and 7 rule tests were each run against the old code and failed there; the stage 6 default-code test and the stage 7 end-to-end test too.

## 5. Measured results

### Headline: automatic metric and AI-judged usefulness side by side (cleaning-only = same 5 documents)

| Metric | Before | After (5 docs, cleaning only) | After (6 docs) | Source |
|---|---|---|---|---|
| **Automatic boilerplate share, top-5, all 15 questions** | 2.7% (2 of 75) | **0.0%** | 0.0% | `results_cleaning_only.md` |
| **AI-judged mean usefulness (0 to 2), 13 answerable** | 0.94 | **1.05** | 1.05 | same |
| AI-judged useful at 5 | 0.338 | 0.323 | 0.338 | same |
| AI-judged useful or partial at 5 | 0.600 | 0.723 | 0.708 | same |
| Questions with at least one useful result | 7 | 8 | 8 | same |
| Per-question win / loss / tie vs before | | 7 / 3 / 3 | 7 / 4 / 2 | same, `results.md` |
| Sign test p (two-sided) | | 0.34 | 0.55 | same |
| Exact Wilcoxon p (two-sided) | | **0.32** | 0.43 | same |
| Fragments in top-5 | 3 | 2 | 3 | same |
| Duplicates in top-5 | 0 | 0 | 0 | same |
| Expected document at rank 1 | 9/9 | 8/9 | 8/9 | same |

Reading it: AI-judged (3 independent judges, kappa = 0.84). The automatic rule under-counts: it found 2.7% boilerplate in the baseline top-5 while a
hand judgement in REVIEW 3.3 found about 25% unhelpful passages, because the rule only sees footers, table-of-contents dots and listed template openers, not
fragments, titles or table rows full of markup. Its drop to 0.0% therefore shows the cleaning removes what it was written to remove; it does not show retrieval improved.
n = 13 questions is small; failing to reject does not prove equality.

### Other label sets (6-document comparison, `judging/results.md`; cleaning-only in `results_cleaning_only.md`)

| Labels | Mean before | Mean after (6 docs) | W / L / T | Wilcoxon p (6 docs) | Wilcoxon p (cleaning only) |
|---|---|---|---|---|---|
| Final (adjudicated, headline) | 0.94 | 1.05 | 7 / 4 / 2 | 0.43 | 0.32 |
| Judge 1, frozen rubric | 0.92 | 1.06 | 8 / 3 / 2 | 0.24 | 0.19 |
| Judge 2 | 0.98 | 1.08 | 6 / 3 / 4 | 0.53 | 0.39 |
| Judge 1 as-is (**deviation**, contains a rule not in the rubric) | 0.86 | 1.06 | 10 / 2 / 1 | **0.059** (sign test 0.039) | not computed |

The as-is labels would have looked significant. That is the effect of a rule I added myself; it is shown only to make that bias visible and is not used.

### Chunk metrics (`retrieval_before.json`, `chunk_metrics_after_heading_drop.json`, `chunk_metrics_6docs.json`, `judging/jaguar_contribution.json`)

| Metric | Baseline, 5 docs | After, same 5 docs | After, 6 docs | Jaguar alone |
|---|---|---|---|---|
| Chunks | 429 | 385 | 497 | 112 |
| Fragments (<300 chars) | 26 (6.1%) | **10** | 17 | **7** |
| Duplicate surplus | 12 (8 groups) | **2** | 5 (4 groups) | 0 |
| Mid-sentence ending rate | 56.2% | **30.1%** | 29.4% | 26.8% |
| Table-markup chunks | 150 | 0 | 0 | |
| HTML residue chunks | 173 | 0 | 0 | |
| Footer residue chunks | 172 | 0 | 0 | |
| Boilerplate chunks (automatic rule) | 37 | 0 | 0 | |

Jaguar contributes 7 of the 17 fragments, 5 of the 65 answerable top-5 slots (2 useful, 1 partial, 2 not useful) in questions 3, 7, 10 and 12, and no rank-1 result.
The 10 fragments left in the 5 original documents (VERIFIED by listing, counted separately): 4 "Yes"-style form pieces
("Yes", "Civil Society Organizations: Yes" and two stakeholder-consultation question stubs) that the cross-branch merge rule forbids merging, and
6 other tiny pieces (a one-line output title, a short risk-classification block, a one-line list item, a "[1] CEMAM (2022)" reference, a "CUBA_PIF-12369_TOC" line, and a
287-character rio-markers block). Cross-document duplicates left on purpose (2 surplus copies in the 5 original documents, 5 in 4 groups with jaguar): text that several proposals
share, such as the "Stakeholder Engagement" paragraph; removing them would lose provenance.

### Judge reliability (`judging/agreement*.json`, `selfconsistency_j2_vs_j2b.json`, `labels_final.json`)

| Comparison | n | Exact agreement | Kappa unweighted | Kappa linear-weighted |
|---|---|---|---|---|
| Judge 1 frozen vs Judge 2, answerable questions (the threshold set) | 124 | 111 (89.5%) | **0.843** | 0.884 |
| Judge 1 frozen vs Judge 2, all 15 questions | 144 | 131 (91.0%) | 0.862 | 0.901 |
| Judge 2 vs Judge 2b (self-consistency, seeded subset, shuffled order) | 30 | 26 (86.7%) | 0.795 | 0.857 |

Pre-set rule (`judging/PROTOCOL.md`, committed `63a42ac`): kappa >= 0.6 reliable. Result: reliable. 13 disputed answerable items went to Judge 3; none were unresolved.
Confusion matrix (rows Judge 1 frozen, columns Judge 2, order N, P, U; 124 items): N 39 / 4 / 0; P 2 / 32 / 5; U 0 / 2 / 40. Disagreements cluster on
three kinds of passage: bare form fragments that say "Yes", passages that only mention a topic (a wind farm, NDC 3.0) without stating the answer, and coordination text.

### Determinism (`build_determinism_compare.txt`)
Two full rebuilds from stage 4 to stage 9 with the real local model: chunk text identical for 6 of 6 documents, vectors identical for 6 of 6, `index.bin` byte-identical,
index fingerprint directory identical. `id_map.parquet` differs only by its `indexed_at` timestamps; chunk and embedding files differ in timestamp fields.
Embedder parity (`embedder_parity_vs_hf.txt`): 10 sampled old chunks, old Hugging Face API vector vs the new local adapter vector, cosine min = mean = max = 1.000000.

### Unanswerable questions 14 and 15 (`results.md`)
No abstention exists, so these still return a top-1: before 0.575 and 0.684, after 0.608 and 0.681 (scores in the same range as answerable questions).

### Q3, a known regression from the heading merge (`rank1_investigation.txt`)
The one question whose expected document lost rank 1. The passage that was rank 1 (score 0.7255) now sits in a chunk that starts with the merged heading
"C. ALIGNMENT WITH GEF-8 PROGRAMMING STRATEGIES..." plus its template sentence; that chunk scores 0.688 (rank 12). The top-5 scores are within 0.006 of each other and no passage
in the index names a community, so the rank flip is a near-tie among weak matches (INFERRED), but the lower score is caused by the heading merge (VERIFIED, same passage re-scored).
Judged usefulness for Q3 is 0.2 before and 0.2 after in the cleaning-only comparison (0.0 in the 6-document result, because jaguar passages enter the top-5).
Proposed Phase 2 fix, not applied: keep a merged heading as chunk metadata and leave it, and the template sentence under it, out of the embedded text; verify on the gold set.

## 6. Cost and resources

* **Money: $0.** No paid or quota-limited API was called. Embeddings: local bge-small on CPU. Judges: LLM sub-agents run inside the working session, no separate API.
* **Network:** `pip install` of `requirements.txt`, `requirements-dev.txt`, `requirements-local.txt` (sentence-transformers 6.3.0, torch 2.15.0); `npm ci` for the frontend;
  the fresh-clone installs. The `BAAI/bge-small-en-v1.5` weights were already in the Hugging Face cache; runs used `HF_HUB_OFFLINE=1`.
* **Disk outside the repo:** the venv `<venv outside the repo>` is 1.6 GB; temporary clones with their own venvs and snapshots sit in the Windows temp folder (two fresh-clone folders of about 570 MB each, now deleted, plus small snapshots); the old-repo files were only read.

## 7. What did not work, or is still open (blunt)

* **No human labels.** The human check was replaced by AI judges. All three judges and the drafting model are from the same model family; agreement does not rule out shared blind spots. Judges are isolated by instruction, not by a sandbox.
* **The result is not significant.** n = 13; the cleaning-only p = 0.32. Useful-at-5 did not move. Do not read this as proof that cleaning does nothing; read it as "not shown".
* **Circularity.** The cleaning rules and the automatic boilerplate rule were written by reading the same 5 GEF documents they are measured on. A drop of the automatic metric to 0 is partly by construction. No unseen-document test exists.
* **Judge 4 labelled only 4 new passages,** with no second opinion (one label affects Q12 by 0.2).
* **Q3 regression** from the heading merge (section 5); fix proposed for Phase 2, not applied.
* **Leftover fragments:** 10 in the original 5 documents (4 "Yes"-style form pieces, 6 other), 17 with jaguar. Form-style tables where the extractor interleaves labels and values are not fixed.
* **Cross-document duplicates** remain (by design: removing them would lose provenance).
* **No abstention:** unanswerable questions still return a top-1 with a normal-looking score.
* **`FAILED_VALIDATION` is unit-tested only**; no real document triggers it now.
* **Jaguar** was added to the corpus in the "after" index; I separated its effect (section 5), but only by re-retrieval over a 5-document index.
* **7 of 13 PDFs are scanned images** and stay out until OCR; 6 documents is the ceiling.
* **CI has never run on GitHub;** the fresh-clone check is a local simulation of the workflow steps.
* **`npm audit`: 7 findings (2 moderate, 5 high), fix deferred to the deploy phase.** High: vite (direct), react-router-dom (direct), react-router, nanoid, source-map-js (transitive). Moderate: postcss (direct), postcss-selector-parser (transitive). A fix is available for all.
* **Frontend health panel is a static snapshot,** not a live check; its numbers were verified once on 2026-11-23.
* **Mutation probe:** it first reported false kills (see section 4). Fixed; the final run is trustworthy only because each kill is a failing assertion.

## 8. Doc and claim updates, and deviations from `metrics_definitions.md`

Updated: README, `OPERATIONAL_READINESS.md`, `DEPLOYMENT.md` (test count 813, local embedder, deps split, 6 documents and 497 vectors); `docs/architecture/stage4/5/7` (Phase 1 rules);
`docs/architecture/stage6_validation.md`, `docs/INGESTION_ARCHITECTURE.md`, `docs/IMPLEMENTATION_LOG.md` (`FAILED_VALIDATION`; the old design text said `FATAL_VALIDATION_FAILED`, a code that never existed); frontend claims (section 3).
Correction to what I said in the session: Phase 0's statement that `requirements.txt` carried pytest and pytest-cov was true; I had assumed otherwise. The split into `requirements-dev.txt` was a clean-up, not a fix.

Deviations from the frozen `metrics_definitions.md` (the file itself was never edited):
1. **Human check replaced by AI judges plus adjudication.** Section 5 of the frozen file and the blind protocol assumed a human label set for 5 questions. Replaced by 3 independent sub-agent judges, a 4th for 4 new passages, and a rule fixed in advance (`judging/PROTOCOL.md`).
2. **Judge 1's template-block rule** (a chunk with a large template-instruction block counts one level lower) was not in the frozen rubric. Judge 1 labels were re-derived without it (4 ids changed: Bd6c6f, Bc61b6, B935ab, Bddcfa); the as-is version is shown separately only.
3. **The NOT INDEXED bullet of the rubric was left out of the judges' copy** (it would reveal which questions have no answer in the index); questions 14 and 15 are scored 0 by that frozen rule regardless of the judges.
4. **The comparison was extended with a 5-document "cleaning-only" variant** because the "after" index has a document the "before" index did not; the headline is the cleaning-only one, the frozen 6-document comparison is shown next to it.
5. The frozen "no LLM" wording in section 5 of the definitions refers to the original plan; this phase uses LLM sub-agents as judges, under the protocol above.

## 9. Resume-safe facts (each with its proof file)

Only these. Nothing else from this phase is claimed.

* "Cleaned the ingestion output of 5 real GEF project documents: boilerplate chunks 37 to 0, table-markup chunks 150 to 0, HTML-residue chunks 173 to 0, footer-residue chunks 172 to 0, fragments 26 to 10, mid-sentence chunk endings 56% to 30%." Proof: `retrieval_before.json`, `chunk_metrics_after_heading_drop.json`.
* "Built a local, network-free embedding adapter behind an existing adapter interface; its vectors matched the hosted-API vectors on a 10-chunk sample (cosine 1.000000); two real rebuilds gave identical chunk text, identical vectors and a byte-identical FAISS `index.bin`." Proof: `embedder_parity_vs_hf.txt`, `build_determinism_compare.txt`.
* "Measured retrieval usefulness before and after on 15 fixed questions with a frozen rubric and a blinded, anonymised protocol. AI-judged (3 independent judges, kappa = 0.84), the cleaning-only change moved mean usefulness 0.94 to 1.05 on a 0 to 2 scale; not statistically significant (exact Wilcoxon p = 0.32, n = 13)." Proof: `judging/results_cleaning_only.md`, `judging/agreement_answerable13.json`.
* "Found and removed my own bias: a labelling rule I had added made the result look significant (p = 0.04); the frozen-rubric result is not." Proof: `judging/results.md` (judge1_asis vs final), `labels_judge1_frozen.json` (changed ids).
* "813 automated tests, 85% coverage; 21 of 21 injected faults caught; fresh-clone install in a clean Python 3.12 venv." Proof: `suite_3_runs.txt`, `reports/mutation/mutation_results.json`, `fresh_clone_phase1_final.log`.
* "Added deterministic, tested fixes: duplicate section ids disambiguated without changing ids of documents that had none; a distinct `FAILED_VALIDATION` status." Proof: `section_ids_unchanged_check.txt`, tests named in section 4.

**Why useful-at-5 did not move.** Cleaning removes noise (boilerplate, markup, fragments, duplicates), so the "partial or better" share rose (0.60 to 0.72) and not-useful results fell (26 to 18 of 65). It cannot add a passage that states an answer the top-5 never contained: for several questions (for example Q3, Q7, Q8, Q13) no passage in the index names what was asked. The number of fully useful passages therefore stayed about 22 of 65. Phase 2 targets exactly this with hybrid (keyword plus vector) search and a reranker, measured on a span-labelled gold set.

Not claimed: "improved retrieval", "human-validated", "production-ready", "byte-identical output" (the id map and file timestamps differ), anything about the frontend beyond "builds and its claims match what was verified".

## 10. Kept out of repository

`LEARN_1.md` (local, gitignored): design decisions and trade-offs, the mistakes made in this phase, and 12 interview questions with honest answers, including why AI judges and their limits,
what kappa means, how I avoided grading my own homework, why line-based cleaning rules, why `index.bin` is byte-identical but `id_map.parquet` is not, why not LangChain, and what I would do with a human labeller.
Also local and ignored: `reports/PHASE_1_PROGRESS.md`, the source PDFs and everything derived from them under `data/proposals/`.

## 11. Next phase preview

**Phase 2 = span-labelled gold set, recall@5 and MRR, "I don't know" behaviour, planner vs no-planner.**
* Gold set labelled by document plus page and quote (span), never by chunk id, so re-chunking cannot invalidate it. Cover the answerable questions and add unanswerable ones.
* Metrics: recall@5, MRR, plus the judged usefulness as a secondary view.
* Retrieval changes to test against the gold set: hybrid keyword plus vector search, a reranker, and the Q3 fix (embed body text without the merged heading and template sentence).
* Abstention: a score or margin rule so questions 14 and 15 return "I don't know" instead of a top-1.
* Planner vs no-planner comparison on the same gold set.
* Rubric fixes suggested by the judges' disagreements: say explicitly how to grade a bare "Yes" fragment, and how to grade a passage that only mentions a topic without stating the answer.
* **What I need from you:** (1) a human labeller for a seeded 40-item subset of the existing judged passages (to check the AI judges), or confirmation to skip it; (2) a decision on how many documents the gold set should cover and whether OCR for the 7 scanned PDFs is in scope; (3) the GitHub repo URL so CI can run for the first time; (4) approval of the Q3 fix as the first Phase 2 change.
