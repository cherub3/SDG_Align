# Pipeline Principles

Shared conventions for every stage in `docs/architecture/`. Defined once here; stage docs cite this
file by section name instead of restating.

## 1. Design Philosophy

1. **Deterministic.** Every stage's output is a pure function of its inputs. No randomness, no
   wall-clock dependence in content (timestamps are the one exception, excluded from every
   rerun-determinism comparison). Identical input produces byte-identical *content*: the wall-clock
   fields (`generated_at`, `indexed_at`, `*_at`) differ between runs, so artifact files are not
   byte-identical. Hosted embedding and LLM APIs are outside this guarantee (see the README's
   "Determinism" section).
2. **Read-only on artifacts a stage doesn't own.** A stage only writes the artifact(s) it produces.
   Upstream artifacts are opened read-only. Grandfathered exceptions: Stage 3 mutates Stage 2's
   `raw_extraction.json` in place; Stage 5 mutates `clean_text.json` in place (its own artifact,
   extended, not another stage's).
3. **No PDF reopening past Stage 2.** Only Stage 1 (integrity check) and Stage 2 (extraction) call
   into PyMuPDF against the original file. Every later stage works exclusively from already-extracted
   JSON artifacts.
4. **Idempotent.** Re-running any stage against the same input produces the same output (modulo
   timestamps). Where a stage mutates an artifact in place, it replaces the relevant field(s)
   wholesale rather than appending.
5. **Deterministic before probabilistic.** Every heuristic is a fixed, named, documented rule — a
   regex, a threshold comparison, a structural graph-walk. No fuzzy matching, no scoring/ranking
   judgment, no AI/LLM call anywhere in this pipeline. Where a signal is unavailable, the design
   reports an honest "we don't know" state (`none_found`, `null`) rather than fabricating one.

## 2. Logging Specification

One shared log-entry structure; only the closed vocabulary of event/warning codes varies per stage:

```jsonc
{
  "stage": "stage6_validation",           // module identifier, matches the stage's script name
  "doc_id": "doc_...",                    // document this entry concerns; null for batch-level
  "event": "validate_document.complete",  // dotted lifecycle event (*.start/*.complete), or a
                                           // stage's own closed WARNING_*/FATAL_* code
  "elapsed_ms": 42,
  "severity": "INFO",                     // INFO | WARNING | ERROR — no other level
  "warning_code": null,                   // present only when severity == WARNING
  "exception": null                       // present only for an ERROR from an unexpected crash
}
```

- **Levels:** INFO (stage entry/exit per document), WARNING (recoverable anomaly), ERROR (quarantine
  or failure event). No document content logged above DEBUG.
- **Closed vocabulary:** codes are drawn from each stage's own closed set, never free text. Each
  stage doc states only the codes it *adds* to this shared vocabulary.

**Constants:** every named threshold introduced by a stage (`MIN_CHARS_PER_PAGE`,
`HEADER_FOOTER_MIN_OCCURRENCES`, `MIN`/`TARGET`/`MAX_CHUNK_CHARS`, etc.) is a stage-local module
constant. Future consolidation into a shared config module is flagged, not designed, here.

## 3. "Stage N" Numbering Convention

`docs/INGESTION_ARCHITECTURE.md` defines its own 10-stage pipeline (Stage 0–9, ending at Batch
Summary) and explicitly excludes chunking and embedding from it. "Stage N" in `docs/architecture/`
means the Nth design unit in this project's own build sequence, not a claim about the architecture
doc's literal numbering. Stage 4–8 here are downstream, separately-versioned units consuming that
pipeline's frozen output — they do not amend or renumber `INGESTION_ARCHITECTURE.md`.

## 4. Validation Severity Tiers

Every stage past Stage 5 that runs a validator suite uses the same two-tier model, full-validation,
no-fail-fast: every check runs to completion regardless of earlier findings.

- **Critical** — would make downstream use of the artifact unsafe or impossible (corrupted offsets,
  unreadable artifact, broken coverage). Any Critical finding → overall `FAIL` → quarantine.
- **Recoverable** — an enrichment-layer imperfection that doesn't block safe downstream use (an
  unresolved classification field, a hierarchy inconsistency, an isolated small chunk). Any
  Recoverable finding with no Critical → overall `WARNING` → proceeds normally.
- No finding at all → `PASS`.

Findings share one shape: `{severity, code, message, detail?}`. A stage's own report file always
includes a `summary` (`pass`/`warning`/`fail` counts) and is always written, regardless of outcome.

## 5. QUARANTINED-Reuse Convention

`DocumentStatus` (`src/ingestion_types.py`) has exactly four members: `REGISTERED`, `QUARANTINED`,
`READY_FOR_CHUNKING`, `FAILED`. No stage past Stage 5 introduces a new member. Each stage that
quarantines a document on a Critical/FAIL outcome reuses `QUARANTINED` with its own narrower
meaning — stated explicitly in that stage's own doc — meaning only "this stage specifically could
not complete for this document," never "upstream artifacts are invalid." Upstream artifacts remain
valid and already-validated; only this stage's own output is missing.

## 6. Manifest Update Convention

`ManifestRecord` is frozen (11 fields, `src/ingestion_types.py`). A stage only ever adds new keys to
the existing `artifact_paths: Dict[str, str]` and touches existing scalar fields
(`completed_at`, `pipeline_version`, `error_code`, and — failure only — `status`). On success, a
stage never advances `status` past whatever value it found — status promotion is a separate,
later stage's job, not the producing stage's own. Each stage's own pipeline-version constant
(`CHUNKING_PIPELINE_VERSION`, `EMBEDDING_PIPELINE_VERSION`, etc.) lives only in that stage's own
artifact headers, never in `ManifestRecord.pipeline_version` (which always stores the single shared
`PIPELINE_VERSION` constant from `stage1_integrity.py`).
