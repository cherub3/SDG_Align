# SDG Align — System Architecture & Engineering Blueprint

**Author role:** Principal Product Engineer / AI Architect mentoring a new graduate
**Status:** Approved for build · v1.0 · 2026-07-17
**Scope:** Portfolio-grade MVP. Deployable entirely free. Single reviewer. No production SaaS ambitions in v1.

---

> ## ⚠️ Delivery status (Phase 1 vs. this blueprint)
>
> This blueprint describes the **full "SDG Align" product vision** — the intended end goal. It is
> retained as the north-star design.
>
> **What is built today (Phase 1)** is the deterministic ingestion + retrieval-augmented-generation
> (RAG) + agent-orchestration **pipeline foundation** that this product sits on: a frozen 22-stage
> pipeline (Stages 0–21) documented under [`docs/architecture/`](architecture/) and implemented in
> [`scripts/`](../scripts/), with 481 passing tests. See the [root README](../README.md) for the
> current, accurate description of what runs.
>
> **Not yet built** (goal-level, alignment-specific components described below): the LLM Pass 1
> extractor / Pass 2 verifier, the SDG-target retriever over `data/sdg_targets.json` (only the raw
> provenance `data/un_sdg_raw.json` exists), the evidence validator, gap analysis, and the Streamlit
> UI (`pages/`). Where this document names those components or files as present, read them as
> **planned**, not delivered. Note also that Phase 1 uses **faiss** for vector indexing (Stage 9)
> rather than the NumPy-only approach this blueprint originally proposed.

---

# Architecture Principles (`docs/PRINCIPLES.md`)

Five principles, committed as a standalone file. Every architectural decision in this document traces back to at least one of them; DECISIONS.md entries cite them by name.

1. **Human before AI.** The AI drafts; the human decides. Enforced structurally — the evidence package can only read approved rows.
2. **Deterministic before probabilistic.** Anything that enforces trust (evidence validator, gap analysis, audit trail) is plain code with a recitable rule. LLMs are used only where judgment is genuinely required.
3. **Simple before scalable.** NumPy over vector DBs, SQLite over Postgres, Streamlit over React — until measured need exists, complexity is a cost with no buyer.
4. **Evidence before confidence.** No citation, no suggestion. Version stamps on every output. Numbers always shipped with their limitations.
5. **Ship before optimize.** One flawless path (upload → review → export → user test) beats ten half-features. Everything else waits on the backlog.

---

# Overall Product Architecture

## The pipeline in one diagram

```
                         ┌──────────────────────────────┐
                         │  data/sdg_targets.json       │
                         │  (17 goals, 169 targets,     │
                         │   official UN text, version) │
                         └────────────┬─────────────────┘
                                      │ embedded ONCE at startup
                                      │ (cached .npy)
                                      ▼
 USER                          ┌─────────────┐
  │ upload PDF/DOCX/TXT        │  Retriever  │
  ▼                            │  (MiniLM +  │
┌─────────┐   ┌────────────┐   │   cosine)   │
│ Upload  │──▶│ Text       │   └──────▲──────┘
│ screen  │   │ Extraction │          │ top-k candidate targets
└─────────┘   │ + guards   │          │ per element
              └─────┬──────┘          │
                    │ plain text      │
                    ▼                 │
              ┌────────────┐  elements│
              │ LLM Pass 1 │──────────┘
              │ Extractor  │  (objectives, activities,
              │ (Gemini)   │   beneficiaries as JSON)
              └─────┬──────┘
                    │ element + its top-k candidates
                    ▼
              ┌────────────┐
              │ LLM Pass 2 │  per candidate: aligned? reasoning,
              │ Verifier   │  confidence estimate 0–100,
              │ (Gemini)   │  exact quote, matched phrases
              └─────┬──────┘
                    ▼
              ┌────────────┐
              │ Evidence   │  quote must string-match official
              │ Validator  │  target text → else SUPPRESSED
              └─────┬──────┘
                    │ validated suggestions ──────────────┐
                    ▼                                     │
              ┌────────────┐      ┌───────────┐          ▼
              │ Human      │─────▶│ Gap       │    ┌──────────┐
              │ Review UI  │      │ Analysis  │    │ SQLite   │
              │ approve /  │      │ claimed vs│    │ audit +  │
              │ reject +   │      │ evidenced │    │ analytics│
              │ reason /   │      └─────┬─────┘    └────┬─────┘
              │ edit       │            │               │
              └─────┬──────┘            ▼               ▼
                    │             ┌───────────┐   ┌───────────┐
                    └────────────▶│ Evidence  │   │ Analytics │
                                  │ Package   │   │ Dashboard │
                                  │ (DOCX)    │   │ (M&E)     │
                                  └───────────┘   └───────────┘
```

## Why this shape

- **Two LLM passes, not one.** Extraction and verification are different cognitive tasks. Separating them means each prompt is simple, testable, and debuggable. One mega-prompt would be cheaper but unauditable.
- **Retrieval between the passes.** The verifier never free-associates over all 169 targets; it only judges candidates the retriever surfaced. This bounds cost, bounds hallucination surface, and makes every suggestion traceable to a similarity score.
- **The evidence validator is deterministic code, not AI.** The one component that enforces trust must not itself be probabilistic. (Named *evidence validator*, not "citation guard": today it validates quotes; tomorrow it can validate target codes, URLs, and dataset versions without a rename.)
- **Human review is structural, not decorative.** The evidence package generator physically cannot read unapproved suggestions — it queries only approved rows. Human-in-the-loop is enforced by the data model, not by a checkbox.
- **Everything downstream of review is boring.** Gap analysis, reporting, analytics are deterministic SQL and string logic. Boring is correct here.

---

# Data Architecture

## Dataset 1: `data/sdg_targets.json` (the reference corpus)

| Aspect | Detail |
|---|---|
| Purpose | The single source of truth for official SDG goal and target text. Every citation is validated against this file. |
| Source | UN Stats SDG API (`https://unstats.un.org/SDGAPI/v1/sdg/Goal/List?includechildren=true`) — official, free, no key. Raw response kept as `data/un_sdg_raw.json` for provenance. |
| Format | JSON, UTF-8. |
| Schema | `{ "meta": { "source_url", "retrieved_date", "framework_version", "dataset_version" }, "goals": [ { "code": "4", "title", "description", "targets": [ { "code": "4.1", "description" } ] } ] }` |
| Versioning | `meta.dataset_version` (semver, starts 1.0.0). Bumped only if the UN revises target text. Version is stamped into every evidence package and eval run. |
| Validation | Load-time checks: exactly 17 goals, 169 targets, no empty descriptions, all target codes match `^\d+\.[0-9a-c]+$`. App refuses to start on failure — a corrupted reference corpus is a fatal error, not a warning. |
| Storage | Committed to git (it is public data; ~200 KB condensed). |
| Update process | Manual re-fetch script + review of diff + version bump + DECISIONS.md entry. Never auto-updated. |
| Limitations | English only. Targets only (232 indicators deliberately excluded from MVP — they are measurement instruments, not alignment statements). |

## Dataset 2: `data/target_embeddings.npy` (derived artifact)

- **Purpose:** precomputed MiniLM embeddings of the 169 targets so retrieval is instant.
- **Source:** derived from Dataset 1; regenerated automatically whenever `sdg_targets.json`'s version or the embedding model name changes (a sidecar `.meta.json` records both — mismatch triggers rebuild).
- **Format:** float32 NumPy array, shape (169, 384), plus sidecar metadata.
- **Storage:** NOT committed (`.gitignore`); rebuilt in ~5 seconds on any machine. Derived artifacts don't belong in git.
- **Limitation:** tied to `all-MiniLM-L6-v2`; changing models invalidates it (handled by the sidecar check).

## Dataset 3: User documents (transient)

- **Purpose:** the input under analysis.
- **Format:** PDF / DOCX / TXT, ≤ 50 pages, born-digital English.
- **Storage:** **never persisted.** Processed in memory / Streamlit's temp upload buffer; only extracted elements and mappings enter SQLite. This is a privacy feature, stated in-app.
- **Limitation:** scanned PDFs, images, and complex tables are rejected with a clear message, not silently mangled.

## Dataset 4: `sdg_align.db` (SQLite operational store)

See Database Architecture. Contains mappings and decisions — never full document text.

## Dataset 5: `eval/gold_set/` (evaluation ground truth)

- **Purpose:** measure the pipeline against organizations' self-reported SDG mappings.
- **Source:** 5 publicly available NGO/UN agency annual reports or proposals that state their own SDG alignment.
- **Format:** the public PDF + a hand-written YAML per document: `{ doc_id, source_url, published_year, stated_goals: [..], stated_targets: [..] (if given), notes }`.
- **Versioning:** `eval_set_version` in a manifest file; any change to the set bumps it. Eval results always cite the version they ran against.
- **Validation:** each YAML reviewed against the source PDF by hand before inclusion.
- **Limitations (stated verbatim in evaluation.md):** n=5; ground truth is *self-reported* by the organizations (they may over- or under-claim); mostly goal-level, so target-level scoring is partial; single annotator built the set.

---

# AI Architecture

Each stage exists for exactly one reason. If a stage's reason disappears, delete the stage.

**1. Extraction pipeline (Gemini pass 1).** Turns unstructured prose into a small list of typed elements (objective / activity / beneficiary, each with the source sentence). *Why it exists:* alignment must be judged per project element, not per document — "we build schools" and "we employ women" align to different targets. Strict JSON schema output; malformed JSON → one retry → fail loudly.

**2. Embedding pipeline (local MiniLM).** Embeds 169 targets once (cached) and each extracted element at runtime. *Why local:* zero cost, offline-capable, deployable on Streamlit Cloud's CPU; 169 vectors need nothing heavier. *Why it exists at all:* to shortlist candidates so the verifier judges k targets instead of 169 — cost and hallucination control.

**3. Retrieval (cosine similarity, NumPy).** Top-k targets per element (k in config, default 5). *Why not BM25/hybrid/vector DB:* the corpus is 169 short texts; dense cosine over a NumPy matrix is sufficient, transparent, and one line of math. Complexity here would buy nothing measurable.

**4. Verification (Gemini pass 2).** For each (element, candidate) it answers: genuinely aligned? reasoning, confidence estimate 0–100, an **exact quote** from the target text, and the **matched phrases** from the document (this powers "Why this suggestion?" in the UI). *Why it exists:* embedding similarity is topical, not logical — "girls' education" is near target 4.1 whether the project supports it or undermines it. The verifier adds the judgment layer, batched one call per element to respect free-tier limits.

**5. Evidence validation (deterministic code).** Normalized string-match of the quote against official target text. No match → suggestion **suppressed** (logged with `suppressed_flag`, never shown as approvable). *Why it exists:* this is the anti-hallucination contract — "no citation, no suggestion." It must be code, not another LLM call, because the trust anchor cannot itself hallucinate.

**6. Human review.** Every surviving suggestion requires approve / reject (with structured reason: wrong target · wrong reasoning · missing context · low confidence · other) / edit. Confidence < 60 badged "low confidence — review carefully." *Why it exists:* responsible-AI design and honest positioning — the tool drafts, the human decides. Structurally enforced (see Database Architecture).

**7. Gap analysis (deterministic).** Claimed SDGs = goal/target numbers found in the document (regex `SDG\s*\d+(\.\d+)?` / "Goal N", plus an LLM listing of explicitly claimed goals with the claiming sentence). Evidenced SDGs = goals with ≥ 1 *approved* mapping. Gap = claimed − evidenced (quoted claiming sentence shown); surplus = evidenced − claimed ("unclaimed alignment found"). *Why deterministic:* the most interviewer-probed feature must have a rule you can recite.

**8. Evidence package generation.** DOCX containing: approved mappings with citations, rejected mappings with reasons, reviewer notes, gap analysis, timestamps, all five versions (LLM model, embedding model, SDG dataset, eval set, app), and a **pipeline summary funnel** — elements extracted → candidates retrieved → suggestions verified → approved by reviewer → exported. *Why the funnel:* one small table that shows an auditor exactly how much filtering happened between raw AI output and the final claims — it makes the human-in-the-loop process visible in the document itself. *Why "evidence package" not "report":* the audience is funders/auditors; completeness and reproducibility are the value, not prose.

**9. Evaluation pipeline.** Offline script over the gold set: precision, recall, FP/FN, per-goal breakdown, citation-correctness audit, inter-rater agreement. *Why it exists:* converts "it seems to work" into numbers with stated limitations. See Evaluation Architecture.

**10. Analytics pipeline.** SQL aggregates over SQLite rendered as the M&E dashboard. *Why it exists:* monitoring & evaluation is a first-class UNDP concern; acceptance rate and rejected-by-reason are genuine product-quality signals, not vanity metrics.

**Confidence framing rule (global):** scores are always labeled *model confidence estimate*, never probability. LLM self-reported confidence is uncalibrated; it is a triage signal for the reviewer. This caveat appears in the UI, LIMITATIONS.md, and the README.

---

# Database Architecture

SQLite, one file, WAL mode. Single-user by design.

```
documents 1 ──── * runs 1 ──── * suggestions 1 ──── 0..1 reviews
                                      │
claims (per run, for gap analysis) ───┘  (same run_id parent)
```

## Tables

**`documents`** — one row per uploaded document's *metadata* (never content).
`id PK · filename · page_count · char_count · uploaded_at · status (processing|reviewed|exported|failed)`
*Why:* analytics needs a document-level grain; privacy demands metadata-only.

**`runs`** — one pipeline execution over a document.
`id PK · document_id FK · llm_model · embedding_model · sdg_dataset_version · app_version · top_k · started_at · finished_at · status`
*Why:* re-running a document after a model change must not overwrite history. Version stamps live here — this is what makes evidence packages reproducible.

**`suggestions`** — one AI suggestion.
`id PK · run_id FK · element_type · element_text · source_sentence · target_code · similarity_score · similarity_method (e.g. "cosine/all-MiniLM-L6-v2") · retrieval_rank · confidence · reasoning · citation_quote · matched_phrases (JSON) · suppressed_flag · created_at`
*Why:* the immutable record of what the AI said, including suppressed items — the audit trail's raw material. `retrieval_rank` (1..k) enables the analytics question "do reviewers approve rank-1 candidates or dig deeper?" — if rank-4 candidates get approved while rank-1 gets rejected, retrieval quality is the problem, not verification. `similarity_method` removes ambiguity about what the score *is* (cosine similarity, not dot product or distance) and survives future retriever changes.

**`reviews`** — one human decision per suggestion.
`id PK · suggestion_id FK UNIQUE · decision (approve|reject|edit) · reject_reason (enum) · reject_note · edited_target_code · review_seconds · decided_at`
*Why:* separated from `suggestions` so AI output is never mutated by human action — the audit trail is the *join* of the two. `UNIQUE(suggestion_id)` enforces one decision per suggestion.

**`claims`** — SDGs the document itself claims.
`id PK · run_id FK · goal_code · target_code NULL · claiming_sentence · detection_method (regex|llm)`
*Why:* gap analysis input; keeping the claiming sentence quotable is what makes gap findings defensible.

**Audit trail** = a SQL VIEW over `suggestions LEFT JOIN reviews`, not a table. Derived truths should not be stored twice.

## Indexes

`suggestions(run_id)` · `reviews(suggestion_id)` (implicit via UNIQUE) · `runs(document_id)` · `claims(run_id)`. That's all — at MVP scale (< 10⁴ rows) more indexes are decoration.

## Future scalability (documented, not built)

The schema ports to Postgres unchanged. Multi-user = add `users` + `reviews.user_id`. Concurrency, migrations (Alembic), and row-level security are v3 concerns. Saying "I deliberately didn't build this" with the migration path written down is stronger than half-building it.

---

# Evaluation Architecture

**Framing rule:** every number is reported as *"on a small evaluation set of five publicly available documents…"* — never a bare percentage.

1. **Gold dataset:** 5 public documents with self-stated SDG mappings (Dataset 5 above), versioned.
2. **Matching protocol:** run pipeline → auto-approve nothing → compare *suggested* goal set (and targets where the org stated them) against stated mappings. Goal-level primary, target-level secondary.
3. **Metrics per document and pooled:**
   - **Precision** = suggested ∩ stated / suggested — "when we claim alignment, is the org's own report with us?"
   - **Recall** = suggested ∩ stated / stated — "do we find what they say they do?"
   - **False positives** listed individually with the element that caused each — over-claiming is the reputationally dangerous failure for an alignment tool, so FPs get a written post-mortem line each.
   - **False negatives** listed with hypothesized cause (extraction miss vs retrieval miss vs verifier rejection — the pipeline stage is identifiable from logs).
   - **Per-goal performance table** (17 rows) — exposes whether the tool is only good at "easy" goals (4, 8) and weak on governance-flavored ones (16, 17).
   - **Top-k recall (retrieval isolation):** for every gold mapping, was the correct target *anywhere in the retriever's top-k* before verification? This separates retrieval failures from verifier failures — end-to-end precision/recall alone conflates the two stages, and a low top-k recall means fix the retriever, not the prompts.
4. **Citation correctness:** manual audit of 30 randomly sampled citations; report % whose quote exactly matches official text (should be ~100% *because the evidence validator enforces it* — the audit verifies the validator, which is the honest thing to test).
5. **Inter-rater agreement:** one independent reviewer (professor or NGO staff) blind-reviews ~20 mappings (approve/reject); report simple agreement % and Cohen's kappa. Even one external rater converts "I think it's right" into evidence.
6. **Human acceptance rate:** from live `reviews` data — % approved, tracked over versions; the standing quality proxy after launch.
7. **Failure analysis:** a written section categorizing every FP/FN into: extraction miss · retrieval miss · verifier over-reach · genuine gold-set ambiguity. This section is worth more in an interview than the metrics themselves.
8. **Known limitations (stated up front):** n=5 · self-reported ground truth · goal-level bias · single annotator built the set · review-time measured on one reviewer is not generalizable.

---

# Product Management Architecture

All artifacts live in `/docs`, versioned in git — the commit history *is* the process evidence.

- **PRD.md** — structure: Problem (⚠ *versioned*: v0 hypothesis preserved verbatim, v1 post-interview revision beside it — the "assumed X, user said Y" artifact) · Personas · User journey (current vs with tool) · Success metrics · Non-goals · Open questions.
- **Personas (2):** *Priya, NGO program manager* — non-technical, reports to funders quarterly, fears being caught over-claiming; *Arjun, freelance grant writer* — time-poor, needs defensible citations, bills by the hour.
- **User journey:** today: read 169 targets → hand-map → hope nobody checks (~2–4 h). With tool: upload → review AI suggestions ~15 min → export evidence package with citations.
- **North Star Metric:** average alignment review time per document (target ≈ 10 min, baseline from discovery interview). **Supporting:** mapping acceptance rate · % suggestions edited · low-confidence share · export completion rate.
- **Backlog:** GitHub Projects board, three columns — MVP / v2 / Someday. The Someday column (OCR, multi-language, auth, teams, agents) is *proof of restraint*, referenced in interviews as "features I said no to."
- **Roadmap:** see Future Roadmap section.
- **Decision log — DECISIONS.md:** dated timeline entries: *Date · Decision · Reason · Alternatives · Evidence · Result*. Covers: Gemini free tier · local MiniLM · cosine+NumPy over vector DBs · top-k retrieval · threshold 60 ("initial heuristic to reduce reviewer workload during MVP testing; subject to revision from user feedback" — no invented science) · SQLite · Streamlit · DOCX evidence package · citation-or-suppress · single verification pass · **no fine-tuning** ("corpus is 169 targets; lightweight retrieval sufficed; fine-tuning adds complexity without evidence of improved user outcomes") · **not full RAG** ("retrieval + verification; a full RAG pipeline adds complexity without measurable MVP benefit").
- **ADRs:** the 4–5 biggest decisions (stack, two-pass AI design, evidence validator, no-persistence privacy model, schema) get one-page ADRs (Context / Decision / Consequences); DECISIONS.md holds the rest.
- **LIMITATIONS.md** (standalone): current limitations · known failure modes · out-of-scope decisions · roadmap. Linked from the in-app Limitations panel.
- **PRIVACY.md:** see Security section.
- **Risk register:** the top-20 table below, reviewed weekly, kept in docs.
- **Release notes / CHANGELOG.md:** per version, with *reasons* ("v1 assumed X → user said Y → v2 does Z").
- **Versioning:** app semver in `config.py`; every evidence package and eval run stamps app + model + embedding + dataset + eval-set versions.

---

# UX Architecture

Design language: government-grade — clean, high-contrast, minimal, no dark-neon anything. Streamlit defaults with light theming.

**1. Upload screen.** Drop zone (PDF/DOCX/TXT), stated limits ("born-digital, English, ≤ 50 pages") *before* upload, privacy note ("your document is processed in-session and never stored"), Analyze button. Sidebar on every screen: Limitations panel + privacy note + version footer.

**2. Processing (loading states).** Staged progress — "Extracting text → Identifying project elements → Matching SDG targets → Verifying alignments" — with element counts as they appear. Rate-limit retries surface as "API busy, retrying (attempt 2/3)…" — never a frozen spinner.

**3. Review screen (the heart).** One card per suggestion: element text + source sentence · target code + official text · confidence badge (color-coded; < 60 = amber "low confidence — review carefully") · **"Why this suggestion?"** expander (matched phrases + quoted target text + reasoning) · Approve / Reject / Edit. Reject opens the structured-reason picker; Edit opens a target selector. Progress indicator ("7 of 12 reviewed"); review time captured silently per card. Suppressed suggestions visible in a collapsed "suppressed by evidence validator" section — transparency without approvability.

**4. Gap Analysis screen.** Two columns: *Claimed* (with quoted claiming sentence) vs *Evidenced* (approved mappings). Gaps flagged: "Document claims SDG 5 — no approved supporting activity found." Surplus flagged positively: "Unclaimed alignment found: SDG 8.6." Locked with a notice until review is complete — gap analysis over unreviewed data would be AI judging AI.

**5. Evidence Package screen.** Full preview (approved + rejected-with-reasons + gaps + version stamps + methodology note), reviewer-notes field, Download DOCX. Export logs `exported` status (completes the audit trail).

**6. Analytics screen (M&E dashboard).** Documents processed · suggested vs accepted · acceptance rate · rejected-by-reason breakdown · confidence distribution histogram · avg review time per mapping (single-reviewer caveat displayed *on the chart*) · most-disputed targets · common gaps · acceptance rate by retrieval rank (rank-1 rejected while rank-4 approved ⇒ retrieval, not verification, needs work).

**Error states (each has designed copy, not a stack trace):** scanned/unreadable PDF ("no extractable text — scanned documents aren't supported yet; OCR is on the roadmap") · empty file · > 50 pages · zero elements extracted · zero alignments found ("no alignment detected" rendered as a *legitimate finding*, not an error) · everything-low-confidence (banner advising full manual review) · API failure after retries (apology + "your document was not stored").

**Empty states:** Review/Gap/Report before any upload → one-line explainer + "Upload a document to begin" link; Analytics with no data → "No documents analyzed yet."

---

# Security and Privacy

**Threat model (proportionate, not paranoid):** the realistic threats are (1) leaking a user's unpublished proposal, (2) leaking the API key, (3) over-trust in AI output. Not in scope: hostile multi-tenant attacks (single-user), DoS (free tier, no SLA).

- **Data retention:** documents live only in session memory; on session end nothing document-shaped survives. SQLite keeps element excerpts + mappings only.
- **Deletion flow:** "Delete my document data" button removes the document row and cascades runs/suggestions/reviews/claims. Deletion is honest — no soft-delete pretending.
- **Temporary files:** Streamlit's upload buffer only; explicit cleanup after extraction; nothing written to disk under a document's name.
- **API keys:** local dev → `.env` (gitignored, `.env.example` committed); deployment → Streamlit Cloud secrets. Key never logged, never in exception messages (the LLM wrapper redacts).
- **Logging:** pipeline stages and timings logged; document *content* never logged above DEBUG, and DEBUG off in deployment.
- **PII handling:** uploaded proposals may contain beneficiary PII. Mitigations: in-session-only processing, excerpt-level persistence, a stated warning on the upload screen, and PRIVACY.md citing Google's API data-use terms (extracted text is sent to Gemini; users are told so before uploading).
- **Third-party surface:** exactly one external call target (Gemini API). Small surface is a feature; documented as such.

---

# Deployment Architecture

- **Development:** Windows laptop, Python 3.11 venv, `streamlit run app.py`, local `.env`, local SQLite file.
- **Testing:** same environment; `pytest` for unit/integration; a `make eval`-style script (`python -m eval.run_eval`) for evaluation runs. No separate staging — for a single-maintainer free-tier product a staging environment is cost without benefit (documented trade-off).
- **Production:** Streamlit Community Cloud, deployed from `main`. CPU-only (MiniLM fits), `GEMINI_API_KEY` in app secrets. SQLite on Streamlit Cloud is ephemeral across redeploys — acceptable for MVP and *disclosed in LIMITATIONS.md* (analytics reset on redeploy; evidence packages are downloaded by the user, so nothing of theirs is lost).
- **Secrets:** `.env` locally / secrets manager on cloud; a startup check fails fast with a clear message if the key is missing.
- **GitHub structure:** single repo `sdg-align`, layout as in the build plan; README is the case study; `/docs` holds all PM artifacts.
- **Branch strategy:** `main` = deployable; short-lived feature branches merged via PR-to-self (yes, even solo — the PR descriptions become process evidence). No develop branch, no gitflow — overkill for one person.
- **Release strategy:** tagged releases `v1.0`, `v2.0` matching CHANGELOG entries; deploy = merge to main; rollback = revert commit (Streamlit redeploys automatically).

---

# Testing Architecture

- **Unit tests (pytest):** evidence validator (exact / fuzzy-normalized / fabricated quotes) · gap-analysis set logic · regex claim detection · sdg_targets.json validator · config/version stamping. These are the deterministic trust-critical parts — they get the densest coverage.
- **Integration tests:** pipeline stages chained with the LLM **mocked** (recorded fixture responses): text-in → suggestions-out, including the malformed-JSON retry path and the suppression path. DB layer tested against a temp SQLite file (schema, cascade delete, the audit view).
- **End-to-end (manual, scripted checklist):** real Gemini key, sample public PDF, full upload → review → gap → export → analytics walk, plus every error state (empty file, scanned PDF, oversized, forced rate limit). Checklist lives in `docs/testing_checklist.md`; run before every release.
- **Evaluation testing:** `run_eval.py` on the gold set is part of the release gate — a release that degrades pooled precision/recall needs a written justification in the CHANGELOG.
- **User Acceptance Testing:** the Phase-3 real-user session — user drives their own document, maintainer observes silently, notes hesitations verbatim, then structured debrief (What's wrong? What don't you trust? Would you use it next cycle?). Findings feed v2 directly.
- **What is deliberately not tested:** LLM output *quality* via unit tests (that's what the eval pipeline is for — asserting on nondeterministic text in pytest is theater).

---

# Project Timeline (4 weeks)

```
Week 1  ─ Foundation ──────────────────────────────────────────
  Mon–Tue   Phase 1 (scaffold, SDG dataset, validation)     ─┐
  Tue–Wed   Phase 2 (text extraction + guards)               │ parallel with
  Wed–Fri   Phase 3 (extractor) + Phase 4 (retriever)        │ user outreach
                                                             │ + interview
Week 2  ─ AI core + persistence ──────────────────────────── │ (off-computer)
  Mon–Tue   Phase 5 (verifier + evidence validator)         ─┘
  Wed       Phase 6 (SQLite + audit)
  Thu–Fri   Phase 7 start (Upload + Review screens)
Week 3  ─ Product complete ────────────────────────────────────
  Mon–Tue   Phase 7 finish (Gap, Evidence, Analytics, errors)
  Wed–Thu   Phase 8 (gold set + eval run + failure analysis)
  Fri       Deploy to Streamlit Cloud (Phase 9 start)
Week 4  ─ Validation + packaging ──────────────────────────────
  Mon–Tue   Real-user test (UAT) → v2 fixes (top 1–2 issues only)
  Wed–Thu   Phase 9 finish (README case study, docs, CHANGELOG)
  Fri       Buffer. It will be needed.
```

**Dependencies:** 3 needs 2; 5 needs 3+4; 6 blocks 7's review screen; 8 needs 5; UAT needs deployment. **Parallelizable:** user outreach (all weeks, off-computer) · gold-set collection (any time after week 1) · docs drafting (PRD/personas from day 1; DECISIONS.md continuously).

---

# Phased Build Plan

> Format note: all phases share `pytest` + the preferred stack; per-phase "External libraries" lists only what the phase *introduces*.

## Phase 1 — Foundation & Reference Corpus

1. **Goal:** runnable skeleton + validated official SDG dataset.
2. **Why:** everything downstream cites this corpus; if it's wrong, every citation is wrong. Also: day-1 commit history is itself portfolio evidence.
3. **Deliverables:** repo scaffold, `sdg_targets.json` + validator, DECISIONS.md started, PRD v0 (pre-interview hypothesis, preserved forever).
4. **Folder structure:** full tree as in Overall Architecture (empty modules with docstrings).
5. **Files:** `requirements.txt` · `.gitignore` · `.env.example` · `data/sdg_targets.json` · `data/un_sdg_raw.json` · `scripts/build_sdg_dataset.py` · `src/config.py` · `docs/{PRINCIPLES.md, PRD.md, DECISIONS.md, data_sources.md}` · `README.md` (stub).
6. **Responsibilities:** `build_sdg_dataset.py` condenses the raw UN API dump and stamps meta; `config.py` exposes a single frozen dataclass `AppConfig` (`APP_VERSION · DATASET_VERSION · EMBEDDING_MODEL · LLM_MODEL · TOP_K · LOW_CONFIDENCE_THRESHOLD · SIMILARITY_METHOD`) rather than loose module-level constants — one importable object, immutable, trivially stampable into runs and evidence packages, and mockable in tests; validator (in the build script + a load-time check) enforces 17/169/no-empties.
7. **Libraries introduced:** `requests` (dataset fetch only).
8. **Data in:** UN Stats SDG API JSON. 9. **Data out:** versioned `sdg_targets.json`.
10. **Validation checkpoint:** validator passes; a human spot-checks 5 targets against the UN website.
11. **Risks:** UN API shape changes (mitigation: raw dump committed). 12. **Trade-off:** committing public data to git vs fetching at runtime — chose commit (reproducibility beats freshness for a stable corpus).
13. **Scalability note:** indicators (232) can be added later as a child array without schema breakage.
14. **Commit milestone:** `feat: project scaffold + versioned official SDG target corpus`.
15. **DoD:** fresh clone + `pip install` + validator run succeeds on another machine.

## Phase 2 — Document Ingestion & Guards

1. **Goal:** PDF/DOCX/TXT → clean text, with every unsupported input rejected loudly.
2. **Why:** garbage-in is the top real-world failure mode; the guards *are* the stated scope limitation made executable.
3. **Deliverables:** `src/extract_text.py` + unit tests + 3 sample fixture documents.
4. **Files:** `src/extract_text.py` · `tests/test_extract_text.py` · `tests/fixtures/{sample.pdf, sample.docx, scanned.pdf, empty.txt}`.
5. **Responsibilities:** one public function `extract(file) -> ExtractedDoc | ExtractionError`; detects scanned PDFs (near-zero chars/page), empty files, > 50 pages; returns page/char counts for `documents` metadata.
6. **Libraries introduced:** `pypdf`, `python-docx`.
7. **Data in:** uploaded file bytes. 8. **Data out:** plain text + metadata, or a typed error with user-facing message.
9. **Validation checkpoint:** all fixture cases produce the designed outcome; scanned PDF produces the designed message, not an exception.
10. **Risks:** PDF extraction quality varies wildly (mitigation: guards + honest limitation, not heroics). 11. **Trade-off:** no OCR, no table parsing — scope honesty over capability breadth.
12. **Scalability:** OCR slot documented (v3); interface won't change.
13. **Commit:** `feat: document ingestion with explicit scope guards`.
14. **DoD:** tests green; each rejection path has final user-facing copy.

## Phase 3 — Element Extraction (LLM pass 1)

1. **Goal:** text → typed project elements (objective/activity/beneficiary) with source sentences, as validated JSON.
2. **Why:** per-element granularity is what makes target-level mapping possible; source sentences make every element traceable.
3. **Deliverables:** `src/llm.py` (Gemini wrapper) + `src/extractor.py` + CLI harness + mocked tests.
4. **Files:** `src/llm.py` · `src/extractor.py` · `scripts/run_pipeline.py` (CLI, grows each phase) · `tests/test_extractor.py` (fixture responses).
5. **Responsibilities:** `llm.py` — single JSON-mode call function with exponential backoff, rate-limit handling, key redaction, malformed-JSON single retry; `extractor.py` — prompt + schema validation + chunking for long docs.
6. **Libraries introduced:** `google-genai`, `python-dotenv`, `tenacity` (or hand-rolled backoff — decide in DECISIONS.md).
7. **Data in:** plain text. 8. **Data out:** `[{type, text, source_sentence}]`.
9. **Validation checkpoint:** CLI run on sample PDF yields sensible elements; malformed-JSON path exercised via mock.
10. **Risks:** free-tier rate limits (mitigation: backoff + chunk batching); prompt drift across Gemini versions (mitigation: model version pinned in config, stamped in runs).
11. **Trade-off:** one extraction call per document chunk vs per-section calls — fewer calls wins on free tier.
12. **Scalability:** extractor is provider-agnostic behind `llm.py`; swapping models is a config change.
13. **Commit:** `feat: LLM element extraction with structured output and retry`. 14. **DoD:** CLI produces valid JSON on all three sample docs; zero unhandled exceptions on API failure.

## Phase 4 — Embedding & Retrieval

1. **Goal:** each element → top-k candidate SDG targets with similarity scores.
2. **Why:** bounds verifier cost and hallucination surface; makes suggestions traceable to a score.
3. **Deliverables:** `src/retriever.py` + embedding cache with sidecar invalidation + tests.
4. **Files:** `src/retriever.py` · `tests/test_retriever.py`.
5. **Responsibilities:** build/load `target_embeddings.npy` (+ `.meta.json` sidecar: dataset version + model name; mismatch → rebuild); embed elements; cosine top-k via NumPy.
6. **Libraries introduced:** `sentence-transformers`, `numpy`.
7. **Data in:** elements + target corpus. 8. **Data out:** per element: `[(target_code, similarity)] × k`.
9. **Validation checkpoint:** sanity probes — "girls' primary school enrollment" must surface 4.1/4.2 in top-k; "youth unemployment" must surface 8.6.
10. **Risks:** MiniLM misses on abstract governance targets (16.x) — *measured* in Phase 8's per-goal table rather than guessed.
11. **Trade-off:** dense-only retrieval; defense on record in DECISIONS.md.
12. **Scalability:** interface returns (code, score) — a future hybrid retriever slots in behind the same signature.
13. **Commit:** `feat: local embedding retrieval over SDG target corpus`. 14. **DoD:** retrieval < 1 s per document on CPU; sanity probes pass; cache rebuild-on-mismatch proven by test.

## Phase 5 — Verification & Evidence Validator

1. **Goal:** candidates → judged suggestions with reasoning, confidence estimate, exact quote, matched phrases; fabricated quotes suppressed.
2. **Why:** this is the product's trust core — the judgment layer plus the deterministic anti-hallucination contract.
3. **Deliverables:** `src/verifier.py` + `src/evidence_validator.py` + tests (the evidence validator gets the densest tests in the repo).
4. **Files:** `src/verifier.py` · `src/evidence_validator.py` · `tests/test_evidence_validator.py` · `tests/test_verifier.py`.
5. **Responsibilities:** verifier — one batched call per element over its k candidates, strict output schema (`aligned, confidence, reasoning, citation_quote, matched_phrases`); evidence validator — normalize (whitespace/case/punctuation) then require exact containment in official target text; failures → `suppressed_flag`, logged, never approvable.
6. **Libraries introduced:** none new.
7. **Data in:** (element, candidates, official texts). 8. **Data out:** validated suggestion records.
9. **Validation checkpoint:** hand-run 10 element–target pairs including 3 designed traps (topically-close-but-not-aligned); validator test suite includes a deliberately fabricated quote.
10. **Risks:** verifier sycophancy (agrees with every candidate) — mitigation: prompt demands a *no* option with reasoning, and acceptance rate is monitored; confidence clustering at 80–90 — mitigation: it's a triage signal, framed as such.
11. **Trade-off:** single verification pass, no self-consistency voting — 5× cost for marginal MVP gain, rejected in DECISIONS.md.
12. **Scalability:** the validator could later also check target codes, URLs, and dataset versions (hence the name), or accept paraphrase-tolerant matching — the latter explicitly rejected for v1 because exactness is the point.
13. **Commit:** `feat: alignment verification with evidence validator (citation-or-suppress)`. 14. **DoD:** trap cases handled; fabricated quote provably suppressed; all 10 hand-run pairs judged reasonably.

## Phase 6 — Persistence & Audit

1. **Goal:** full SQLite schema, audit view, cascade deletion.
2. **Why:** human-in-the-loop and audit trail become *structural* here — the report can only ever read approved rows.
3. **Deliverables:** `src/db.py` + schema DDL + tests (including cascade-delete and audit-view tests).
4. **Files:** `src/db.py` · `src/schema.sql` · `tests/test_db.py`.
5. **Responsibilities:** connection management (WAL), schema creation, typed insert/query functions per table, `audit_trail` view, `delete_document(id)` cascade, analytics aggregate queries.
6. **Libraries introduced:** none (stdlib `sqlite3`).
7. **Data in:** pipeline outputs + review decisions. 8. **Data out:** query functions for UI, report, analytics.
9. **Validation checkpoint:** cascade delete leaves zero orphans; audit view reproduces the exact suggestion→decision history.
10. **Risks:** Streamlit rerun model causing double-writes — mitigation: idempotent writes keyed on natural keys + session-state guards.
11. **Trade-off:** raw SQL over an ORM — at 5 tables, SQLAlchemy is indirection without payoff (DECISIONS.md).
12. **Scalability:** schema is Postgres-portable; migration path documented, not built.
13. **Commit:** `feat: persistence layer with structural human-in-the-loop and audit view`. 14. **DoD:** every table round-trips; deletion flow verified; report queries return approved-only.

## Phase 7 — Streamlit Application

1. **Goal:** the complete UX — upload → review → gap → evidence package → analytics, all error/loading/empty states.
2. **Why:** the product *is* this workflow; polish here beats any additional feature (the definition of done for the whole project is one flawless path).
3. **Deliverables:** all five screens per UX Architecture + gap module + report module.
4. **Files:** `app.py` · `pages/1_Review.py` · `pages/2_Gap_Analysis.py` · `pages/3_Report.py` · `pages/4_Analytics.py` · `src/gaps.py` · `src/report.py`.
5. **Responsibilities:** `app.py` — upload, guards, staged pipeline progress, sidebar (limitations/privacy/versions); Review — cards, confidence badges, "Why this suggestion?", structured reject reasons, silent review-time capture; `gaps.py` — the deterministic rule (regex + LLM claims vs approved evidence); `report.py` — evidence-package DOCX (approved + rejected-with-reasons + gaps + version stamps + methodology note); Analytics — the M&E aggregates with the single-reviewer caveat rendered on-chart.
6. **Libraries introduced:** `python-docx` (reuse), `pandas` (analytics display only).
7. **Data in:** all prior phases via `db.py`. 8. **Data out:** DOCX evidence package; SQLite state.
9. **Validation checkpoint:** full manual walk of the golden path + all seven designed error states, on desktop widths.
10. **Risks:** Streamlit session-state bugs on rerun (the classic) — mitigation: all mutations through idempotent db.py calls; UI state derived from DB, not duplicated.
11. **Trade-off:** Streamlit's UI ceiling accepted for free deploy + Python-only velocity (DECISIONS.md).
12. **Scalability:** because logic lives in `src/`, a future FastAPI+frontend rebuild reuses everything below the UI.
13. **Commit:** `feat: complete review workflow, gap analysis, evidence package, M&E dashboard`. 14. **DoD:** golden path flawless; every error state shows designed copy; export contains all version stamps.

## Phase 8 — Evaluation

1. **Goal:** execute the Evaluation Architecture; publish honest numbers.
2. **Why:** destroys the "vague eval claims" critique; produces the failure-analysis narrative interviews reward.
3. **Deliverables:** gold set (5 docs + YAML) · `eval/run_eval.py` · `docs/evaluation.md` with metrics, per-goal table, citation audit, inter-rater result, failure analysis, limitations paragraph *first*.
4. **Files:** `eval/gold_set/*` · `eval/manifest.yaml` (eval_set_version) · `eval/run_eval.py` · `docs/evaluation.md`.
5. **Responsibilities:** run_eval — batch pipeline over gold docs, compare vs YAML, emit metrics JSON + markdown table; manifest pins versions.
6. **Libraries introduced:** `pyyaml`.
7. **Data in:** gold PDFs + stated mappings. 8. **Data out:** versioned metrics + written analysis.
9. **Validation checkpoint:** every FP/FN individually explained and categorized (extraction/retrieval/verifier/gold-ambiguity).
10. **Risks:** results are mediocre — mitigation: *publish them anyway with analysis*; an honest 71% with a failure taxonomy outscores a suspicious 95%.
11. **Trade-off:** n=5 accepted and disclaimed everywhere.
12. **Scalability:** run_eval is version-stamped, so future model swaps get before/after comparisons for free.
13. **Commit:** `feat: gold-set evaluation with per-goal metrics and failure analysis`. 14. **DoD:** evaluation.md complete including the inter-rater section (or a dated plan for it if the external rater is still pending).

## Phase 9 — Deployment, UAT & Packaging

1. **Goal:** live public link, real-user test, v2 iteration, README-as-case-study.
2. **Why:** "shipped, tested with a real user, iterated" is the entire differentiator of this portfolio project.
3. **Deliverables:** Streamlit Cloud deployment · UAT notes with verbatim quotes · v2 (top 1–2 fixes only) · CHANGELOG · README case study · final docs sweep.
4. **Files:** `.streamlit/config.toml` · `docs/user_test_notes.md` · `CHANGELOG.md` · final `README.md` · `docs/{ARCHITECTURE.md, LIMITATIONS.md, PRIVACY.md, testing_checklist.md}` finalized.
5. **Responsibilities:** README structure fixed: Problem → Research → User interview → Design → Architecture → Evaluation → Iteration → Lessons learned (installation at the bottom); CHANGELOG entries carry reasons.
6. **Libraries introduced:** none.
7. **Data in:** everything. 8. **Data out:** live URL + the complete case study.
9. **Validation checkpoint:** full E2E checklist run against the *deployed* app; a stranger can follow the README.
10. **Risks:** no user materialized — mitigation: gold-set validation framed as "validated against five organizations' self-reported mappings," outreach continues; Streamlit cold starts — disclosed in LIMITATIONS.md.
11. **Trade-off:** ephemeral SQLite on redeploy accepted and disclosed (users download their evidence packages; nothing of theirs is lost).
12. **Scalability:** v2/v3 roadmap items each have a documented slot.
13. **Commit:** `release: v1.0 — deployed MVP with evaluation and case study` (tagged `v1.0`). 14. **DoD:** live link works from a clean browser; UAT executed or fallback framing in place; every doc referenced in this blueprint exists and is current.

---

# Risks (Top 20)

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | Problem hypothesis is wrong (NGOs don't work this way) | Med | High | Phase-0 discovery interview; versioned PRD; pivot willingly — defend the user, not the blueprint |
| 2 | No real user says yes | Med | High | 10+ outreach messages day 1, continued weekly; fallback = gold-set framing |
| 3 | Gemini free-tier rate limits break the demo | Med | High | Batched calls (~10–15/doc), exponential backoff, visible retry state; test under forced 429 |
| 4 | Verifier sycophancy (approves everything) | Med | High | Prompt demands justified "no"; acceptance rate monitored; trap cases in Phase 5 checkpoint |
| 5 | Evidence validator too strict (kills valid suggestions via formatting) | Med | Med | Normalization layer; suppression *rate* tracked in analytics |
| 6 | PDF extraction garbage on real-world docs | High | Med | Guards + honest scope limits; three fixture formats tested |
| 7 | Evaluation results are poor | Med | Med | Publish anyway with failure taxonomy — honesty is the portfolio value |
| 8 | Scope creep (agents, OCR, auth…) | High | High | Someday column; "polish one path" rule; this table as standing reminder |
| 9 | Streamlit session-state double-write bugs | High | Med | Idempotent DB writes; UI state derived from DB |
| 10 | Free Gemini model deprecated mid-project | Low | Med | Model name in config; provider-agnostic `llm.py` |
| 11 | Streamlit Cloud resource limits (MiniLM memory) | Low | Med | MiniLM is ~90 MB — fits; verified in week-3 deploy, with fallback to smaller model |
| 12 | SQLite wiped on redeploy surprises a user | Med | Low | Disclosed in-app and in LIMITATIONS.md; evidence packages are downloaded |
| 13 | API key leaked via git or logs | Low | High | .gitignore from commit 1; wrapper redaction; Streamlit secrets |
| 14 | Uploaded doc contains PII sent to Gemini | Med | Med | Pre-upload notice; in-session-only processing; PRIVACY.md cites Google terms |
| 15 | Confidence scores read as calibrated probability | High | Med | "Model confidence estimate" label everywhere + uncalibrated caveat in UI |
| 16 | Accenture start date compresses weeks 3–4 | Med | Med | Phases 1–7 are the core; docs/packaging can slip to evenings; buffer Friday |
| 17 | Gold-set ground truth itself is wrong (orgs over-claim) | Med | Med | Stated as a known limitation; failure analysis separates "we disagree with the org" cases |
| 18 | Inter-rater reviewer never materializes | Med | Low | Fallback: document the plan + run self re-review at 2 weeks' distance, disclosed honestly |
| 19 | Long docs blow past Gemini context in one chunk | Med | Med | Chunked extraction in Phase 3; 50-page cap does most of the work |
| 20 | Interviewer asks a "why" with no documented answer | Med | High | DECISIONS.md timeline covers every stack/threshold choice; ADRs for the big five |

---

# Future Roadmap

**Version 1 (MVP — everything in this document, nothing more):** upload → extract → retrieve → verify → cite-or-suppress → human review → gap analysis → evidence package → analytics → gold-set evaluation → deployed free → case-study README.

**Version 2 (only after real-user feedback; candidates, to be cut down by what the user actually says):** top 1–2 UAT fixes (mandatory) · editable evidence-package narrative sections · per-target notes fields · CSV export of mappings · confidence-threshold slider for reviewers · expanded gold set (10–15 docs) · second inter-rater.

**Beyond v2 (deliberately unplanned):** OCR, multi-language, multi-user/auth, Postgres, indicator-level mapping, API access. These live on the Someday backlog column, not on the roadmap — a roadmap entry is a commitment, and no evidence justifies committing to them yet.

Rule: nothing moves left in this list without evidence from a real user.
