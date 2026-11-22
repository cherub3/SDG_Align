# SDG Align — Proposal Corpus Ingestion Architecture (Design Document)

Status: Approved for build · v1.1 · 2026-07-18 · post-verification update

## Context

The project has two finalized inputs (the SDG Targets Corpus of 169 official UN targets, and the collected proposal PDFs organized by category — Climate, Biodiversity, Health, Education, Water, Poverty, Responsible Consumption) and is moving into building the ingestion pipeline that turns the raw proposal PDFs into clean, structured, page-anchored text ready for semantic chunking and later hand-annotation into an evaluation gold set.

**This is a design-only deliverable.** No code is written in this phase. The output is a technical design document, verified against the already-approved `docs/ARCHITECTURE_BLUEPRINT.md` so it doesn't contradict existing decisions (Streamlit-only, SQLite, no Docker/vector DB, frozen `AppConfig`-style versioning, the five architectural principles).

**Naming decision:** the blueprint already uses numbered "Dataset 1–5" headers for its own artifacts (e.g., `Dataset 2` = cached target embeddings, `Dataset 5` = the 5-doc eval gold set) — a *different* numbering scheme than the conversational "Dataset #1/#2/#3" used to discuss this new work. To eliminate the collision permanently, this document uses **descriptive names only, no numbers**, for every artifact:

| Descriptive name | What it is | Corresponds to |
|---|---|---|
| **SDG Targets Corpus** | 169 official UN targets, `data/sdg_targets.json` | blueprint's "Dataset 1" |
| **Target Embeddings** | cached MiniLM vectors of the targets | blueprint's "Dataset 2" |
| **Uploaded Document** | single user-uploaded file, session-only | blueprint's "Dataset 3" |
| **Operational Database** | `sdg_align.db` (SQLite) | blueprint's "Dataset 4" |
| **Proposal Corpus** *(new — this document's subject)* | the ~12 official RRP/PIF/PAD PDFs, organized by category | was called "Dataset #2" in conversation |
| **Evaluation Gold Set** | hand-labeled chunks from the Proposal Corpus, per an annotation protocol | supersedes/expands blueprint's "Dataset 5" |

**Follow-up (small, out of scope here):** `docs/ARCHITECTURE_BLUEPRINT.md`'s own "Dataset 1–5" section headers should eventually be renamed to match this descriptive convention, so the whole project has one naming scheme.

**Discrepancy flags (verified against the actual repo, not assumed from conversation):**
- No folder for the Proposal Corpus exists on disk yet at `data/`. Only `data/un_sdg_raw.json` (raw UN API dump) is present. This design is prescriptive — it specifies where those files should live once organized — not a description of current state.
- `data/sdg_targets.json` (the SDG Targets Corpus itself) also doesn't exist yet — Phase 1 of the blueprint hasn't been executed. Doesn't block this design (ingestion has no runtime dependency on it), but it's an open build item.

---

## Design Document

### 1. End-to-end ingestion architecture

```
data/proposals/raw/<category>/*.pdf   (~12 official PDFs, pre-organized by SDG category folder)
        │
        ▼
┌───────────────────┐
│ Stage 0: Manifest  │  scan raw/ tree → doc_id = sha256(pdf_bytes), full digest (see §12)
│ Registration       │  → category = containing folder, verbatim (folder is the ONLY
│                    │  source of truth — never inferred from filename/content) →
│                    │  doc_type = title-page → filename → manual-override precedence
│                    │  (§4a, RRP/PIF/PAD/PRODOC — a separate, independent field from category)
│                    │  → append row to manifest.json (status=registered, started_at=now)
└─────────┬──────────┘
          │ per doc_id, sequential (≈12 docs — no need for parallelism)
          ▼
┌───────────────────┐
│ Stage 1: Open /    │  PyMuPDF open() → is this a readable, non-corrupt PDF?
│ Integrity Check    │  FATAL on failure → quarantine, continue to next doc
└─────────┬──────────┘
          ▼
┌───────────────────┐
│ Stage 2: Raw       │  per-page extraction: text + font/bbox dict (PyMuPDF) +
│ Extraction         │  markdown-structured text (pymupdf4llm) → raw_extraction.json
└─────────┬──────────┘
          ▼
┌───────────────────┐
│ Stage 3: Per-Page  │  reuse extract_text.py's char-density heuristic, but applied
│ Scanned/Empty      │  PER PAGE (not whole-doc only) — official docs often mix
│ Detection          │  born-digital body with scanned annex/signature pages
└─────────┬──────────┘
          ▼
┌───────────────────┐
│ Stage 4: Cleaning  │  dehyphenation, whitespace normalization, repeated
│ & Normalization    │  header/footer line stripping, encoding-artifact repair
└─────────┬──────────┘
          ▼
┌───────────────────┐
│ Stage 5: Structural│  headings/subheadings (font-size heuristic via
│ Tagging            │  pymupdf4llm), bullets/numbered lists preserved as
│                    │  markdown, table text retained (structure not parsed,
│                    │  regions flagged with page anchor + approx row count),
│                    │  appendix/references sections flagged by regex
└─────────┬──────────┘
          ▼
┌───────────────────┐
│ Stage 6: Doc-Level │  page-count match, non-empty check, encoding validity,
│ Validation Suite   │  duplicate-hash check, char/page threshold →
│                    │  validation_reports/<doc_id>_validation.json
└─────────┬──────────┘
          ▼
     pass?──no──▶ quarantine/<doc_id>/reason.json, manifest status=quarantined, CONTINUE BATCH
          │yes
          ▼
┌───────────────────┐
│ Stage 7: Metadata  │  assemble doc-level + page-level metadata →
│ Assembly           │  extracted/<doc_id>/metadata.json + clean_text.json
└─────────┬──────────┘
          ▼
┌───────────────────┐
│ Stage 8: Manifest  │  status=ready_for_chunking, artifact paths recorded
│ Finalization       │
└─────────┬──────────┘
          ▼
┌───────────────────┐
│ Stage 9: Batch     │  logs/ingest_run_<ts>.log (per-doc trace) +
│ Summary            │  logs/ingest_run_<ts>_summary.json (counts, failures)
└────────────────────┘
          │
          ▼
  clean_text.json + metadata.json × ~12 docs
  = "ready for semantic chunking" (out of scope beyond this point)
```

**Design reasoning for the overall shape:**
- **Per-document isolation, sequential processing.** At n≈12, there is no throughput problem — parallelism would be pure overengineering (harder-to-read logs, race conditions on the manifest) for zero measurable benefit. Sequential, one-doc-at-a-time processing with a per-doc try/except is simpler and easier to debug by hand ("Simple before scalable").
- **Skip-and-continue at the document level, not the batch level.** The SDG Targets Corpus is small and singular, so a corrupted reference file is correctly fatal (poisons everything downstream). The Proposal Corpus is a *collection* of independent documents — one bad PDF should never block the other 11 from becoming available for annotation. Deliberate, principled divergence from the fail-fast pattern used elsewhere.
- **No LLM calls anywhere in this pipeline.** Everything here is deterministic, local, code-only ("Deterministic before probabilistic"). This corpus becomes ground truth for evaluating the AI pipeline later — using the AI pipeline's own extractor to prepare the data used to score that pipeline would be circular and methodologically weak.
- **Category is folder-derived only, never inferred.** The `raw/<category>/` layout is already a curated, human-made decision — re-deriving category from filename text or document content would be redundant work that could actively disagree with the curation and silently overrule it. `doc_type` (RRP/PIF/PAD) is a genuinely separate concern — a classification the corpus curator didn't already make by hand — so it's the only field allowed to use a heuristic.

### 2. Directory structure

```
data/
  proposals/
    raw/
      climate/
        <doc_id>__<original_filename>.pdf
      biodiversity/
      health/
      education/
      water/
      poverty/
      responsible_consumption/
    manifest.json
    extracted/
      <doc_id>/
        raw_extraction.json
        clean_text.json
        metadata.json
    quarantine/
      <doc_id>/
        reason.json
    validation_reports/
      <doc_id>_validation.json
      batch_validation_summary.json
    logs/
      ingest_run_<YYYYMMDD_HHMMSS>.log
      ingest_run_<YYYYMMDD_HHMMSS>_summary.json
```

| Folder | Reason |
|---|---|
| `raw/<category>/` | Category-as-folder is the simplest organization for 7 categories × ~1–2 docs each. Originals stay on disk permanently (unlike the Uploaded Document path) — these are public, official documents with no PII constraint, and annotators need to re-open the source PDF by hand. |
| `manifest.json` | Single source of truth for ingestion state per document (doc_id → status, hashes, paths). |
| `extracted/<doc_id>/` | Colocates all derived artifacts for one document — trivial to inspect or rerun a single document without touching the other 11. |
| `quarantine/<doc_id>/` | Holds a structured *reason* record, not a moved file — quarantine is a status annotation, avoiding split-state bugs. |
| `validation_reports/` | Separate from `extracted/` — validation reports are about the ingestion *process*, scannable at a glance without wading into per-doc content. |
| `logs/` | Timestamped, append-never — every run (including reruns) leaves its own trace, auditable against prior runs. |

**Deliberately absent:** no `processed/embeddings/` folder — chunking/embedding is a later, separate phase; adding structure for it now would be speculative (overengineering).

### 3. Intermediate artifacts

| Artifact | Produced at | Why it exists |
|---|---|---|
| `raw_extraction.json` | Stage 2 | Cached pre-cleaning extraction — a **defined schema, not an open-ended dump** (see explicit shape below). Lets cleaning heuristics be re-tuned without re-reading the PDF — the slowest, most failure-prone step. Caching it once and iterating cheaply on cleaning logic is the highest-leverage artifact in the pipeline. |
| `clean_text.json` | Stage 4–5 | The actual input to downstream chunking/annotation — page-indexed, structurally tagged, boilerplate stripped. |
| `manifest.json` | Stages 0, 8 | Per-document status, hashes (dedup), category, doc_type, artifact paths, timing, error codes — enables idempotent reruns (skip any doc_id already `ready_for_chunking` unless forced). Enriched schema below. |
| `metadata.json` | Stage 7 | Descriptive metadata, kept separate from `clean_text.json` so it can be reviewed/edited (e.g., correcting a mis-detected doc_type) without touching extracted text. |
| `validation_reports/<doc_id>_validation.json` | Stage 6 | Makes "why was this quarantined" answerable in one file read, not a log grep. |
| `batch_validation_summary.json` | Stage 9 | One-glance corpus health check: N registered, N passed, N quarantined, N with excluded pages. |
| `logs/ingest_run_*.log` + `*_summary.json` | throughout | Human-readable trace + machine-parseable summary — same dual-format split used elsewhere in the project (eval producing metrics JSON + markdown table). |
| `quarantine/<doc_id>/reason.json` | Stage 6 (on failure) | Structured, typed failure reason — not free text — so failure categories can be counted/reported programmatically. |

**`raw_extraction.json` — explicit schema (not an arbitrary dump):**

```jsonc
{
  "doc_id": "…",
  "extractor": "pymupdf4llm",           // which library/version produced this
  "pages": [
    {
      "page_number": 1,
      "raw_text": "…unmodified per-page text…",
      "font_info": [                     // optional — only populated where heading
        {"text": "1. Executive Summary", "size": 16.0, "bold": true, "bbox": [72, 90, 340, 112]}
      ],
      "layout_metadata": {
        "table_bboxes": [[72, 400, 520, 600]],
        "block_count": 14
      }
    }
  ]
}
```

Four fields only at the page level — `page_number`, `raw_text`, `font_info` (optional, heading candidates only, not every span on the page), `layout_metadata` (table bboxes + block count, nothing finer). This is a deliberate boundary: `raw_extraction.json` exists to make cleaning re-runnable without re-parsing the PDF, not to be a general-purpose PyMuPDF object dump. If a future need calls for finer-grained layout data, that's a new, explicitly justified field — not a default "just save everything" posture, which would let the artifact drift into an inconsistent catch-all over time.

**`manifest.json` — enriched per-document record:**

```jsonc
{
  "doc_id": "doc_9f3a2b1c8e4d",
  "category": "climate",
  "doc_type": "RRP",
  "status": "ready_for_chunking",        // registered | quarantined | ready_for_chunking | failed
  "started_at": "2026-07-18T10:04:00Z",
  "completed_at": "2026-07-18T10:04:07Z",
  "pipeline_version": "0.1.0",           // = AppConfig.INGESTION_PIPELINE_VERSION at run time (see note below)
  "error_code": null,                    // one of the §6 failure vocabulary codes, or null
  "artifact_paths": {
    "raw_extraction": "data/proposals/extracted/doc_9f3a2b1c8e4d/raw_extraction.json",
    "clean_text": "data/proposals/extracted/doc_9f3a2b1c8e4d/clean_text.json",
    "metadata": "data/proposals/extracted/doc_9f3a2b1c8e4d/metadata.json"
  }
}
```

`started_at`/`completed_at` make stalled or partially-run documents identifiable (a doc stuck at `started_at` set but no `completed_at` after a crash is a clear rerun candidate). `pipeline_version` + `error_code` turn "why did this fail, and with which code version" into a single-field lookup instead of a log search.

**Versioning source of truth:** `pipeline_version` (manifest) and `ingestion_pipeline_version` (metadata.json) are both stamped from a single new field, `AppConfig.INGESTION_PIPELINE_VERSION`, added to the existing frozen `AppConfig` dataclass in `src/config.py` (the same object already used to stamp `LLM_MODEL`, `EMBEDDING_MODEL`, `DATASET_VERSION`, etc. into every run and report). This pipeline reads that one field rather than hardcoding a version string in the ingestion script — bumping it after a heuristic change (e.g., retuned header-stripping) is then a one-line edit in one place, and every artifact produced afterward reflects the bump automatically.

### 4a. `doc_type` classification — deterministic precedence

A single, fixed precedence order, evaluated in sequence, first match wins. Not left as an unspecified "heuristic" — the order itself is the specification:

1. **Title-page match.** Scan the extracted text of pages 1–3 for known document-type phrases (e.g., "Project Appraisal Document", "Project Information Form", "Regional Resilience Programme", "Programme Document", "Report and Recommendation of the President"). Also match short-form tokens: `PAD`, `RRP`, `PIF`, `PRODOC`. First match wins; `doc_type_confidence = "title_page_match"`. Verified to be more reliable than filename for the curated corpus, where descriptive filenames do not consistently encode the document type.
2. **Filename fallback.** If pages 1–3 are inconclusive, regex-match the original filename against the same token set (`RRP`, `PIF`, `PAD`, `PRODOC`). If exactly one token matches, `doc_type` is set, `doc_type_confidence = "filename_pattern"`.
3. **Manual override.** If both steps are inconclusive, `doc_type = "unknown"`, `doc_type_confidence = "unresolved"`, and the document is flagged in `batch_validation_summary.json` for a required human decision during the Stage 6 sanity pass (self-critique §4/§8). Once a human sets it, `doc_type_confidence = "manual_override"`.

This keeps `doc_type` deterministic end-to-end (no step is a probabilistic guess) while guaranteeing every document ends up correctly classified — either automatically or via an explicit, recorded human decision, never a silent default.

### 4. JSON schema for extracted documents

**`extracted/<doc_id>/metadata.json`:**

```jsonc
{
  "doc_id": "doc_9f3a2b1c8e4d",
  "title": "Climate Resilience and Adaptation Programme — Regional Resilience Programme",
  "title_extraction_method": "largest_heading",  // pdf_metadata | regex_title_field | largest_heading | manual_override | none_found — never guessed by an LLM
  "provenance": {
    "original_filename": "RRP-TAJ-2021-CLIMATE.pdf",
    "sha256": "…",
    "source_path": "data/proposals/raw/climate/doc_9f3a2b1c8e4d__RRP-TAJ-2021-CLIMATE.pdf",
    "ingested_at": "2026-07-18T10:04:00Z",
    "ingestion_pipeline_version": "0.1.0"  // = AppConfig.INGESTION_PIPELINE_VERSION
  },
  "classification": {
    "category": "climate",              // folder-derived, always — see Stage 0
    "doc_type": "RRP",                  // resolved via the §4a precedence — the one field allowed to infer
    "doc_type_confidence": "title_page_match"  // title_page_match | filename_pattern | manual_override | unresolved
  },
  "structure": {
    "page_count": 148,
    "extracted_page_count": 148,
    "excluded_pages": [112, 113],
    "has_tables_detected": true,
    "table_regions": [{"page": 34, "approx_rows": 12}],
    "sections_flagged": [
      {"type": "appendix", "start_page": 130},
      {"type": "references", "start_page": 145}
    ]
  },
  "validation": {
    "status": "ready_for_chunking",
    "validation_report_path": "data/proposals/validation_reports/doc_9f3a2b1c8e4d_validation.json"
  },
  "future_compatibility": {
    "language": "en",
    "ocr_applied": false,
    "schema_version": "1.0"
  }
}
```

**`extracted/<doc_id>/clean_text.json`:**

```jsonc
{
  "doc_id": "doc_9f3a2b1c8e4d",
  "full_text_char_count": 284213,
  "section_tree": [
    {"section_id": "2", "section_level": 1, "parent_section": null, "title": "Programme Description", "start_page": 12},
    {"section_id": "2.1", "section_level": 2, "parent_section": "2", "title": "Climate Rationale", "start_page": 13},
    {"section_id": "2.1.1", "section_level": 3, "parent_section": "2.1", "title": "Baseline Vulnerability", "start_page": 14}
  ],
  "pages": [
    {
      "page_number": 1,
      "text": "…cleaned page text…",
      "char_start": 0,
      "char_end": 1893,
      "headings": [{"section_id": "1", "title": "1. Executive Summary"}],
      "is_excluded": false
    }
  ]
}
```

**Field purpose, grouped:**
- **`title`/`title_extraction_method`** — extracted, not defaulted to null. Four-step deterministic precedence: (1) PDF metadata `Title` field, if non-empty; (2) regex extraction of project title patterns from pages 1–3 (`Project Title:`, `Title:`, `Name of Project:`); (3) largest heading heuristic (font/bbox data PyMuPDF already returns); (4) manual override. The title becomes a real, load-bearing field downstream — displayed in Streamlit, in evaluation reports, in citations, in debugging output — so a layered heuristic with a stated method beats defaulting to null. `title_extraction_method: "none_found"` is the honest fallback for the rare document where no candidate survives any step — still not a null with no explanation.
- **`provenance`** — every field answers "where did this text come from and can I trust it" ("Evidence before confidence" applied to the corpus itself, not just the app's output).
- **`classification`** — feeds the annotation guide's stratification (by category, by doc type) without the annotator re-deriving it by hand.
- **`structure`** — the load-bearing fields for the self-critique below (excluded pages, table regions) — where corpus quality problems become visible instead of silent.
- **`section_tree` / per-page `headings`** — the single highest-value structural addition to this design. Each heading is assigned a `section_id` (`"2"`, `"2.1"`, `"2.1.1"`) mirroring the document's own numbering where present, a `section_level` (depth), and a `parent_section` (its immediate ancestor's `section_id`), forming an explicit hierarchy tree rather than a flat list of heading strings. This lets a future chunker align chunk boundaries to actual document structure ("don't split mid-subsection") instead of guessing purely from font-size formatting — and lets the annotation guide reference "section 2.1.1" as a stable coordinate, independent of page number, when discussing ambiguous cases. **Edge case:** not every document numbers its headings (e.g., plain "Executive Summary" with no "1."). Where no native number exists, `section_id` is synthesized positionally (`"s1"`, `"s2"`, `"s2a"` for a child of `s2`) rather than left blank — every heading gets a stable id, native-numbered or synthetic, never a mix of "sometimes present."
- **`char_start`/`char_end`** — the single most important field for the product's citation-grounding value prop. Every future chunk must be traceable back to an exact page (see §9).
- **`future_compatibility`** — `language`, `ocr_applied`, `schema_version`: reserved, safe-defaulted, minimal (3 fields, not a speculative bag).

### 5. Metadata schema for downstream retrieval

A deliberately **leaner** subset of `metadata.json`, to avoid metadata bloat in whatever eval/chunking script consumes it:

```jsonc
{
  "doc_id": "doc_9f3a2b1c8e4d",
  "category": "climate",
  "doc_type": "RRP",
  "page_count": 148,
  "title": "Climate Resilience and Adaptation Programme — Regional Resilience Programme"
}
```

**Excluded on purpose:**
- `sha256`, `ingested_at`, `ingestion_pipeline_version` — provenance/audit concerns, irrelevant to retrieval scoring.
- `excluded_pages`, `table_regions` — ingestion-quality diagnostics, not retrieval signal.
- Per-page metadata isn't duplicated here — it lives in `clean_text.json`, where the chunker actually consumes it.

### 6. Logging strategy

- One log file per batch run, timestamped, append-only, human-readable (`ingest_run_<ts>.log`).
- One machine-parseable summary JSON per run (`ingest_run_<ts>_summary.json`) — counts by outcome, quarantined doc_ids with reason codes, docs with excluded pages.
- **Levels:** INFO (stage entry/exit per doc), WARNING (recoverable anomalies — excluded pages, uncertain header/footer heuristic, encoding repair), ERROR (quarantine event, with reason code). No document *content* logged above DEBUG (consistent with the app's own logging rule, even though these are public documents — habit consistency over marginal, near-zero privacy risk).
- **Shared failure vocabulary** (used identically in logs, `reason.json`, and the batch summary):
  - `FATAL_UNREADABLE` — PDF won't open / corrupt
  - `FAILED_VALIDATION` — stage 6 found a Critical structural/offset finding (readable, but inconsistent); counts as a failure (exit 1)
  - `FATAL_NO_TEXT` — zero extractable text (fully scanned doc)
  - `FATAL_EMPTY_FILE` — 0-byte / unreadable file
  - `FATAL_DUPLICATE` — sha256 matches an already-ingested doc_id
  - `PARTIAL_EXCLUDED_PAGES` — recoverable; doc proceeds with N pages excluded
  - `WARNING_HEADER_FOOTER_UNCERTAIN` — recoverable; low-confidence heuristic, flagged for spot-check
  - `WARNING_ENCODING_REPAIRED` — recoverable; mojibake normalized
- Closed, enumerated list — not a free-text judgment call ("Deterministic before probabilistic").

### 7. Validation strategy

| Check | How | Outcome |
|---|---|---|
| PDF opens without exception | `fitz.open()` try/except | Fail → `FATAL_UNREADABLE`, quarantine |
| Page count sane | `doc.page_count > 0` | Fail → quarantine as empty |
| Extracted page count matches PDF page count | count vs `doc.page_count` | Mismatch → WARNING, proceed |
| Per-page char density | reused char-density heuristic, applied per page | Below threshold → page excluded; if *all* pages fail → `FATAL_NO_TEXT`, quarantine |
| Whole-doc empty extraction | sum of non-excluded page char counts == 0 | → `FATAL_NO_TEXT`, quarantine |
| Encoding validity | replacement-character density per page | Attempt normalization; still bad → page excluded |
| Duplicate detection | `doc_id` (sha256-derived, §12) already present in manifest | Match → `FATAL_DUPLICATE`, skip, flag for manual review — dedup is structurally the same check as identity assignment, not a separate mechanism |
| Corrupted/mismatched structure | PyMuPDF raises mid-extraction | Isolated page failure → exclude page; total failure → `FATAL_UNREADABLE` |

Each check maps to exactly one deterministic outcome — no probabilistic judgment anywhere in validation.

### 8. Error handling / recovery policy

| Failure type | Policy | Justification |
|---|---|---|
| Corrupt/unopenable PDF | Quarantine, skip, continue batch | One bad file must never block the other 11 |
| Fully scanned document | Quarantine, skip, continue batch | Matches Uploaded Document path's philosophy (reject clearly) — quarantine instead of a UI message, since there's no interactive user; manifest + `reason.json` is the message |
| Individual scanned/low-text pages in an otherwise good doc | Exclude page, proceed with document | RRP/PAD docs routinely mix born-digital narrative with scanned annex/signature pages — quarantining a whole 148-page doc over 2 bad pages is disproportionate at n≈12 |
| Duplicate file (possibly filed under a different category) | Skip re-processing, flag for manual review | Because `doc_id` is content-derived (§12), a duplicate *naturally* resolves to the same `doc_id` regardless of which category folder it's filed under — so this case surfaces automatically rather than requiring separate detection logic |
| Page-count mismatch | Log warning, proceed | Not correctness-threatening; blocking here is disproportionate paranoia |
| Unexpected exception during extraction | Catch at per-document boundary, quarantine, continue batch | The per-document try/except is the actual resilience mechanism |
| **Retries** | **None, by design** | Extraction is deterministic and local (no network, no rate limit) — unlike Gemini calls, which need retry/backoff because they're genuinely flaky over the network. A retry loop here would cargo-cult the LLM wrapper's pattern into a context where it buys nothing. Deliberate non-symmetry, not an oversight. |
| **Idempotent reruns** | Manifest status gate: skip any doc_id already `ready_for_chunking` unless `--force` | Prevents wasted reprocessing of 8 good docs because doc 9 crashed the run — must be an explicit, tested code path, not assumed |

**Stop-the-batch is reserved for exactly one case not in the table above:** if `raw/` itself doesn't exist, or `manifest.json` is unreadable/corrupted — the *tracking system* being broken, not a single document. This is the bulk-pipeline analogue of "a corrupted reference corpus is fatal": a broken manifest poisons every downstream status decision.

### 9. Page boundary preservation

1. **Structural:** `clean_text.json.pages[]` is an ordered array keyed by `page_number` — text is never flattened into an undifferentiated blob. Non-negotiable given citation grounding is the entire point of the product.
2. **Offset-based:** each page carries `char_start`/`char_end` into the document's cumulative full text — lets a future chunker choose either strategy (chunk within page boundaries, or chunk across full text and resolve offsets back to page/page-span) without this design pre-committing to one.
3. **Table/section flags carry their own page anchor** — so the annotation guide can instruct labelers to treat flagged regions specially (e.g., skip labeling inside `references`) without re-deriving section boundaries.

This is deliberately the one area where this design over-invests relative to "avoid overengineering" — justified because page-level citation grounding is the load-bearing claim of the whole product. Getting it wrong at ingestion time is unrecoverable later without re-parsing every PDF.

### 10. Structural preservation — what's worth it at this scope

| Element | Preserve? | Reasoning |
|---|---|---|
| Headings/subheadings | Yes | Free via `pymupdf4llm`'s markdown output. High payoff: heading-aligned chunk boundaries produce topically coherent chunks. |
| Bullets/numbered lists | Yes | Also free from `pymupdf4llm`. High payoff: RRP/PAD "activities"/"beneficiaries" sections are frequently bulleted — collapsing them into run-on paragraphs would blur the element-level granularity the AI pipeline depends on. |
| Tables | **Table text is retained in `clean_text.json` via `pymupdf4llm`'s markdown output. Row/column structure is not reconstructed. Table regions are flagged with page anchors and approximate row counts.** | Verification confirmed that official ADB/GEF proposal documents (Results Frameworks, Logframes, DLIs, Design & Monitoring Frameworks, financing tables) frequently carry SDG-relevant evidence inside tables — silently dropping that text would bias the eval corpus toward narrative-only claims. Full table *parsing* (cell structure, row/column semantics) remains an explicit non-goal. The retained text may be noisy for complex layouts (merged cells, nested headers), but that is preferable to absence. Table region markers (page + approximate row count via PyMuPDF's `find_tables()` bbox detection) let annotators locate and assess table content without a structured parse. |
| Captions | No special handling | Folded into regular text — negligible payoff at 12 documents. |
| Appendices | Flag via regex (cheap), preserve as text | Annotators need to know when they've crossed into annex material (often boilerplate, not programmatic narrative worth SDG-mapping). |
| References/bibliography | Flag via regex, preserve as text | Same reasoning — real annotation-guide value (tell labelers to skip). |
| Footnotes | No special handling | Untangling footnote markers from body text is real engineering work for near-zero payoff at 12 documents in this genre. Explicitly named as a place a more ambitious engineer would over-invest. |
| Headers/footers (repeated boilerplate) | Strip from `clean_text`, keep in `raw_extraction` | Cheap, deterministic (repeated-line-frequency heuristic), meaningfully improves chunk quality near page boundaries. Kept in raw extraction so nothing is destructively lost if the heuristic misfires. |

### 11. PDF extraction library selection

| Library | Accuracy | Speed | Layout preservation | Table handling | Metadata | Complexity | Maintenance |
|---|---|---|---|---|---|---|---|
| **PyMuPDF (fitz)** | High, born-digital | Very fast (C bindings) | Font/bbox for heading heuristics | Basic bbox detection | Rich | Low — pip-only, no system binaries | Low — mature, huge install base |
| **pdfplumber** | High, char-level precision | Slower (pdfminer.six) | Strong bbox data | Best-in-class table extraction | Good | Low-medium | Low, redundant with PyMuPDF here |
| **pymupdf4llm** | Same as PyMuPDF | Same as PyMuPDF | **Best fit** — markdown output, headings/lists auto-detected | Markdown-ified table detection | Inherits PyMuPDF's | Very low — near-zero extra code vs hand-rolled heading detection | Low — maintained by PyMuPDF org |
| **Docling (IBM)** | Very high, DL layout model + OCR fallback | Slow, CPU-only here | Best-in-class | Best-in-class, true structure | Rich | High — pulls in torch + layout models | Higher — heavy dependency surface |
| **Unstructured** | High, format-general | Variable; heavy strategies pull detectron2/onnx/tesseract | Good | Good (optional heavy deps) | Good | Medium-high — Windows install friction (poppler/tesseract) | Higher — built for multi-thousand-doc scale, unused here |

**Recommendation: PyMuPDF + pymupdf4llm, one dependency family.**

- **Free tier / CPU-only:** rules out Docling's real advantage (DL layout model) — wasted if it can't run fast, and its OCR overlaps an explicit non-goal already committed to.
- **Solo engineer, ~12 docs not thousands:** Unstructured's/Docling's scale-oriented breadth is unused value paid for in full setup/maintenance cost — a direct violation of "Simple before scalable" applied to tooling choice.
- **Windows dev laptop, no Docker:** PyMuPDF/pymupdf4llm are pure pip wheels, no system binaries (no poppler, tesseract, torch) — consistent with why the rest of the stack (Streamlit, SQLite, sentence-transformers) was chosen for install simplicity.
- **Unifies both ingestion paths:** the blueprint names `pypdf` for the Uploaded Document path. This design recommends unifying both on PyMuPDF instead — factor the shared scanned-page char-density heuristic into one `src/pdf_utils.py` module consumed by both the single-upload extractor and this bulk pipeline. Avoids two similar-but-subtly-different scanned-detection implementations drifting apart. `pypdf` also lacks the font/bbox layout data this design needs for heading detection, so PyMuPDF is strictly more capable for both use cases.

### 12. Document identity — `doc_id` and everything that depends on it

Underspecified in the first pass of this design. Every downstream system — chunking, retrieval, evaluation, citations — keys off `doc_id`. A flaw here propagates silently to everything built on top of it.

**Requirements for `doc_id`:**
- **Deterministic** — regenerating it from the same file must always produce the same value; it cannot depend on ingestion run order or wall-clock time.
- **Never changes** — once assigned, stable for the life of the corpus, including across reruns of the ingestion pipeline.
- **Filename-independent** — renaming the PDF on disk must not change its identity.
- **Category-independent** — moving a file between category folders (e.g., a miscategorized document gets corrected from `health/` to `water/`) must not change its identity. Category is metadata *about* the document, not part of *what makes it that document*.
- **Unique forever** — no realistic collision risk, even if the corpus grows well past 12 documents.

**Chosen scheme: content-derived hash, full digest.**

```
doc_id = "doc_" + sha256(raw_pdf_bytes).hexdigest()   // full 64 hex characters, no truncation
```

- Computed once, at Stage 0, directly from the file's bytes — before category, filename, or doc_type are read. Identity is established from the one property intrinsic to the document (its content) before any extrinsic, curatable metadata (category, filename) is attached.
- **Full digest, not a truncated prefix.** Storage cost of 64 hex characters vs. 12 is negligible at this corpus size, and using the full digest removes any need to reason about truncation collision probability — there is no collision-risk argument to make, and none to revisit later if the corpus grows.
- **Satisfies every requirement above by construction:** identical bytes hash identically (deterministic, never changes); the hash has no relationship to filename or folder (independent of both).
- **Doubles as the duplicate-detection mechanism** (§7 validation) — a duplicate file resolves to the same `doc_id` on re-ingestion, so duplicate-detection and identity-assignment are the same check, not two separately maintained ones.
- **Human-readability is not a goal of `doc_id` itself.** The original filename and category stay available in `metadata.json.provenance` and in the `raw/<category>/doc_id__original_filename.pdf` naming convention, so a human browsing `raw/` still sees a readable filename while every programmatic reference uses the stable hash. A scheme that encodes category or filename into the id breaks on re-categorization or rename; one that encodes ingestion order breaks on reruns or insertions. The hash avoids all three by encoding none of them.

**Note on examples in this document:** every `doc_id` shown elsewhere (e.g., `doc_9f3a2b1c8e4d`) is a shortened illustrative value for readability. The actual stored and referenced value is always the full 64-character digest.

**Downstream dependency chain:**

```
doc_id (content hash, minted once at Stage 0)
  └─▶ chunk_id = f"{doc_id}_c{chunk_index:04d}"
        (chunk_index is deterministic given a fixed chunking_pipeline_version;
         re-chunking with an unchanged version must reproduce identical chunk_ids)
        └─▶ retrieval index entries keyed by chunk_id
              └─▶ evaluation gold-set labels keyed by chunk_id
                    └─▶ evidence-package citations referencing chunk_id → doc_id → page_number
```

Every layer above `doc_id` inherits its stability guarantees. If `doc_id` were derived from filename instead, a single rename during corpus cleanup would orphan every chunk, label, and citation pointing at that document — a failure surfacing downstream, later, and harder to diagnose than at the source. Anchoring identity to content at Stage 0 prevents that failure class entirely.

---

## Self-critique — attacking this design as the toughest reviewer

1. **Table text is now retained, but extraction quality for complex table layouts is unvalidated.** Verification confirmed that results-framework matrices, logframes, DLIs, and financing tables in official ADB/GEF proposal documents carry target-level SDG evidence — the earlier "flag but don't parse" approach would have silently starved the corpus of that content. The updated design retains table text via `pymupdf4llm`'s markdown output. The remaining risk: complex table layouts (merged cells, nested headers, multi-row spans) may render as garbled or reordered text in markdown, producing noise rather than coherent evidence. This is acceptable at n≈12, but a spot-check of the extracted text in table-dense pages (e.g., the Results Framework section of a sample RRP) should be part of the post-run sanity pass.

2. **The per-page scanned-detection threshold is unvalidated for this document population.** It's reused wholesale from a heuristic designed for ≤50-page uniform user uploads. Official RRP/PIF/PAD docs run 100–300+ pages with scanned cover/signature/annex pages mixed in — an untested population. At n≈12, every wrongly quarantined document is a large percentage loss. **Needs a hand spot-check against all real files before the pipeline is declared done.**

3. **Header/footer stripping is a hand-tuned magic-number heuristic with no test harness beyond eyeballing.** Can misfire in both directions (under-strip pollutes text; over-strip deletes a genuinely important repeated phrase). Raw text is preserved as a fallback, but nothing currently specifies who reviews the stripped output or how — a real gap.

4. **Doc-type classification precedence (§4a) is updated but the phrase and token lists are still unvalidated against real documents.** Category is solid (folder is the sole source of truth — Stage 0, §12). `doc_type` now has a fixed, three-step precedence — title-page match first, filename fallback second, manual override third — because verification showed curated filenames are not consistently reliable for type detection. What's still open: the title-page phrase list and filename-token fallback set are not yet validated against the actual ~12 documents. More documents than expected may fall through to `unresolved` if the real title pages use phrasing outside the assumed token set. That's an acceptable outcome (explicit flag, not silent error) but should be checked during the mandatory pre-implementation scan.

5. **Idempotency is described, not yet guaranteed.** If the script dies mid-batch, reruns are *supposed* to skip completed docs via the manifest — but this must be an explicit, tested code path when implemented, not an assumed property.

6. **`ingestion_pipeline_version` now has a defined source (`AppConfig.INGESTION_PIPELINE_VERSION`), but the bump discipline itself is still unenforced.** Naming the source of truth doesn't guarantee anyone remembers to increment it when a heuristic changes. Nothing in this design stops a retuned header-stripping rule from being reprocessed under an unchanged version number. That has to be a process rule (documented in `DECISIONS.md`, same as other version-bump conventions), not something the schema alone can enforce.

7. **The category folders force a single, arbitrary primary bucket onto documents that legitimately span several SDGs** (a Water+Health project has no clean home). `category` is a corpus-organization bucket, not an exhaustive SDG label — this needs to be said explicitly wherever the annotation guidelines get written, or it'll cause confusion later.

8. **Nearly every heuristic here is calibrated by eyeballing ~12 documents, not validated on a held-out set.** Correct trade-off at this scale, but the design currently reads as a deterministic, hands-off pipeline when it's really "semi-automated ingestion with a mandatory human sanity pass baked in." That human pass should be named as an explicit phase deliverable, not left implicit.

9. **The ceiling is low, on purpose, but undocumented as such.** Flat-JSON manifest, single-threaded sequential processing, and hand-eyeballed heuristics stop working well before real scale. Correct for n≈12; if the corpus ever grows past ~50 docs, this design should be named as hitting its ceiling then, not discovered as a surprise mid-scale-up.

10. **Manifest-as-JSON-file vs. a SQLite table is not fully defended above.** The rest of the system uses SQLite as the operational store. Rationale: this pipeline runs offline, before the app exists, producing input for a separate annotation process; a JSON manifest avoids coupling ingestion-tooling state to the running app's schema. Defensible, but should be recorded as a `DECISIONS.md` entry like every other stack choice in the blueprint, not left implicit here.

---

## Critical files for implementation

- `data/proposals/manifest.json` — new; the ingestion state machine's single source of truth
- `scripts/ingest_proposals.py` — new; batch pipeline entry point
- `src/pdf_utils.py` — new; shared PyMuPDF extraction + scanned-page-detection module, consumed by both this bulk pipeline and the future single-upload `src/extract_text.py`
- `src/extract_text.py` — planned (Phase 2 of the blueprint, not yet written); should be aligned to share `pdf_utils.py` rather than duplicating scanned-PDF detection
- `docs/ARCHITECTURE_BLUEPRINT.md` — needs a new "Proposal Corpus" section added under Data Architecture, plus the follow-up rename of its numbered "Dataset 1–5" headers to the descriptive names used in this document

## Verification

This is a design document, not code — there's nothing to run yet. Two checks below are **mandatory preconditions**, to be completed before implementation starts, not optional spot-checks:

1. **[MANDATORY — updated]** The "flag but don't parse" table decision has been revised: table text is now retained via `pymupdf4llm`'s markdown output (see §10). The remaining check is quality: after the first pipeline run, spot-check 2–3 table-dense pages (Results Framework, Logframe, DLI matrix) from actual documents and inspect whether the extracted text is coherent or garbled. If complex table layouts render as noise, note the specific documents and sections in `batch_validation_summary.json` for annotators to treat with extra caution.
2. **[MANDATORY]** Hand-open 2–3 of the actual PDFs and check: are they mostly born-digital, or is scanning heavier than assumed? Validate the per-page char-density threshold against real files. Also validate the §4a doc_type title-page phrase list and filename-token fallback list against the actual corpus filenames and title pages before trusting the classification on the full batch.
3. Once implemented: run the batch, inspect `batch_validation_summary.json`, and manually confirm the quarantine/exclusion decisions match what a human would decide looking at the same PDFs.
