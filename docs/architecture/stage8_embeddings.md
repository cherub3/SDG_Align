# Stage 8 — Embedding Generation

See `docs/pipeline_principles.md` for shared conventions.

## Scope

Stage 8 turns each eligible document's `chunks.json` (Stage 7's output) into embedding vectors,
persisted as `embeddings.parquet`, plus an always-written `embedding_validation_report.json`. It is
designed entirely against a **Provider Abstraction Layer** with zero concrete embedding provider
chosen or defaulted — no provider/model has been selected anywhere in this pipeline, and this design
must not pick one. It never reopens a PDF, never reads `clean_text.json` for text (chunk `text` is
already final in `chunks.json`), and performs no retrieval, ranking, ANN indexing, or anything past
vector generation — those remain future, separately-designed stages. This document does not amend
`INGESTION_ARCHITECTURE.md`'s own 10-stage pipeline; "Stage 8" is this project's 8th design unit
(per the "Stage N" Numbering Convention), a downstream, separately-versioned unit consuming Stage 7's
frozen output.

## Pipeline

```
manifest.json (13 docs total)
      │
      ▼
[1] Load manifest & filter
      gate: "chunks" in record.artifact_paths        (5 eligible today; never gates on record.status)
      │
      ▼
[2] Discover chunk artifacts
      read chunks.json per eligible doc                (never reopens PDFs; never reads clean_text.json)
      │
      ▼
[3] Validate prerequisites
      chunks.json parses, chunk_count > 0, chunk_validation_report.json exists
      │
      ▼
[4] Determine embedding workload
      for each chunk: embedding_id = f(chunk_id, provider, model_name, model_version)
      and text_checksum = sha256(chunk.text)
      │
      ▼
[5] Skip unchanged chunks
      embedding_id present in existing embeddings.parquet AND stored text_checksum matches → REUSE
      else → GENERATE
      │
      ▼
[6] Batch embedding generation
      GENERATE-marked chunks only, BATCH_SIZE=32, checkpointed every 5 batches, retried up to 3x
      on transient provider errors
      │
      ▼
[7] Validate embeddings
      full-validation, no-fail-fast, Critical/Recoverable
      │
      ▼
[8] Persist embeddings
      REUSE rows + new GENERATE rows merged, written atomically (tmp file + os.replace)
      │
      ▼
[9] Update manifest
      artifact_paths["embeddings"], artifact_paths["embedding_validation_report"], completed_at,
      pipeline_version, error_code; status untouched on success, QUARANTINED + FATAL_EMBEDDING_FAILED
      on FAIL
      │
      ▼
[10] Emit metrics
      per-run summary JSON: docs processed, chunks reused vs generated, per-provider counts, duration
```

## Design Decisions

1. **No embedding stage exists in `INGESTION_ARCHITECTURE.md`.** It ends at Batch Summary and
   explicitly declines to scaffold an embeddings folder. This document is a downstream, separately-
   versioned unit consuming that pipeline's frozen output, not an amendment to it.
2. **Document selection.** Gate on `"chunks" in record.artifact_paths`, never on `record.status`
   (all 5 chunked documents sit at `status="ready_for_chunking"`, which nothing further promotes).
   Why: Stage 7's FAIL path never sets `artifact_paths["chunks"]`, so the key's presence is already
   sufficient and reliable.
3. **`ManifestRecord` stays frozen.** Only two new `artifact_paths` keys (`embeddings`,
   `embedding_validation_report`) plus existing scalar fields — per the Manifest Update Convention.
   No new `DocumentStatus` member.
4. **No embedding model is chosen.** `ARCHITECTURE_BLUEPRINT.md`'s "Dataset 2" section already
   commits the broader app to a local `sentence-transformers` MiniLM model for embedding SDG targets
   — a different embedding space for a different purpose. Resolution: design entirely against the
   Provider Abstraction Layer (below), with zero concrete provider selected here; the MiniLM choice
   is noted only as context that *may* inform a future default, never assumed or inherited.
5. **`config_fingerprint` field added beyond the originally requested field list.** Why: a
   `(chunk_id, text_checksum)` pair alone can't distinguish "same chunk embedded twice under two
   different models" from "the same embedding, cached." A deterministic hash of the exact
   provider+model+dimension+parameter recipe, folded into the composite `embedding_id`, resolves
   this.
6. **One `embeddings.parquet` per document**, not one corpus-wide file. Why: a single shared file
   would mean a partial-write failure on one document risks the whole corpus's artifact, and would
   break the per-doc-directory pattern every prior stage already established.
7. **`clean_text.json` is not read.** `chunks.json` already carries the complete, final chunk `text`
   (post split/merge). Re-deriving text from `clean_text.json` would duplicate logic that already ran
   in Stage 7 and risk drift without a corresponding version bump, for no gain. Stage 8 reads
   `manifest.json`, `metadata.json` (for doc-level cross-checks only — even this is arguably
   redundant, since `category`/`doc_type`/`title` are already denormalized onto chunks), and
   `chunks.json`.
8. **Text checksum strategy.** Hashes sha256 over the raw UTF-8 bytes of `chunk["text"]` exactly as
   it appears in `chunks.json` — nothing else. Excludes `chunk_id`, `section_ids`, offsets, page
   ranges: a structural re-chunk that shifts boundaries without changing text byte-for-byte must not
   trigger a wasted re-embed. sha256 chosen for consistency with the project's existing hash choice
   (`doc_id` is already sha256-derived), not a collision-resistance requirement. `text_checksum`
   answers "did the content change"; `config_fingerprint` (Decision 5) answers "did the recipe
   change" — orthogonal axes of the same key; either changing requires regeneration.
9. **Versioning.** Provider library upgrade with model pinned unchanged: `model_version` must be
   bumped by whoever wires the adapter whenever output could change — Stage 8 cannot detect silent
   drift under an unchanged version string (Self-Critique #2). Model upgrade (new `model_name`/
   `model_version`): `config_fingerprint` changes → new `embedding_id` namespace → every chunk gets
   new rows; nothing overwritten, old rows persist until a future pruning stage. Dimension change:
   independently validated (`EMBEDDING_DIMENSION_CONSISTENT`, Critical) even though dimension is
   implied by model identity. Provider switch: fully separate namespace, full re-embed — vector
   spaces aren't comparable across providers. Reruns with unchanged config: `embedding_id` +
   `text_checksum` both match → full reuse, zero provider calls. No separate `cache_version` field —
   `embedding_id`+`text_checksum` already fully encode validity.
10. **Incremental embedding mechanism**, run per document at pipeline stages [4]-[5]:
    1. Load existing `embeddings.parquet`, if present, into a lookup keyed by
       `embedding_id -> text_checksum`.
    2. For each current chunk, compute the current run's `embedding_id` and `sha256(chunk.text)`.
    3. Present in the lookup with a matching checksum → **REUSE** (no provider call, row copied
       byte-identical).
    4. Otherwise → **GENERATE** (covers: new chunk, new config, or changed text — one rule for all
       three).
    5. Batching (Decision 11) receives the ordered GENERATE list only.
11. **Batching, checkpointing, resume, retries, rate limiting, memory.**
    - `BATCH_SIZE = 32` — bounds peak memory regardless of provider, comfortably under hosted-API
      request limits, large enough to amortize per-call overhead for local models. Clamped to
      `min(BATCH_SIZE, provider.max_batch_size)` when the adapter declares one.
    - Ordering: `chunks.json`'s own array order (already deterministic), never randomized — required
      for unambiguous checkpoint resume and reproducible logs.
    - `CHECKPOINT_INTERVAL_BATCHES = 5` (~160 chunks) — bounds max rework on interruption to ≤160
      chunks while keeping checkpoint I/O overhead small relative to embedding compute cost.
    - Checkpoint mechanism: append-only `embeddings.checkpoint.jsonl`, one JSON line per completed
      row for the current run — jsonl chosen because it's safely appendable mid-write, unlike
      Parquet. On resume, existing lines mark which `embedding_id`s are already done.
    - Final persistence: checkpoint rows merged with prior REUSE rows, written to
      `embeddings.parquet.tmp`, atomically renamed via `os.replace` — the previous run's artifact is
      never partially overwritten. Checkpoint deleted only after the atomic replace succeeds.
    - Resume after crash: `embeddings.checkpoint.jsonl` remains, `embeddings.parquet` untouched (last
      successful run's valid artifact); next invocation resumes past completed batches.
    - Partial failures: exhausted retries on one batch aborts the whole document's run for that
      config — no silent skip, no partial-coverage gap (mirrors Stage 7's `CHUNK_COVERAGE_EXACT`
      no-gap-tolerance philosophy). A mere run interruption does not quarantine the document — only
      an exhausted-retry fatal error or Critical validation finding does.
    - `MAX_RETRIES = 3` per batch, exponential backoff (`2s, 4s, 8s`), only when
      `provider.is_transient_error(exc)` is true. Non-transient errors fail immediately.
    - Rate limiting: the batch loop consults `provider.requests_per_minute` (if set) and sleeps
      between batches — one token-bucket-style wait, expressed once in the orchestrator.
    - Memory: today's corpus (13 docs, low thousands of chunks) fits trivially in memory — no
      streaming/out-of-core design engineered now (Self-Critique #11), matching the project's
      "simple before scalable" precedent.
12. **Validation suite.** Reuses the Validation Severity Tiers convention identically to Stage 6/7.
    See finding-code table below.
13. **Artifact format — Parquet.**

    | Format | Verdict | Why |
    |---|---|---|
    | NumPy (`.npy`/`.npz`) | Rejected | Homogeneous array only; per-row metadata needs a parallel sidecar — poor fit for per-doc incremental writes with mixed-provider, mixed-dimension rows. |
    | HDF5 | Rejected | Supports heterogeneous appendable datasets, but requires `h5py`/`libhdf5` — a system dependency inconsistent with the project's "pure pip wheels, no system binaries" constraint. |
    | Arrow / Feather (IPC) | Rejected | Optimizes for same-machine process-handoff speed, not durable on-disk storage — not this pipeline's use case. |
    | **Parquet** | **Chosen** | Columnar, compressed, self-describing schema (dimension/type mismatch caught at read time), supports nested/list columns for `embedding_vector`, splits cleanly per-doc, and each per-doc file is small enough (today ≤85 rows) that read-modify-atomic-rewrite per run is cheap. |

    Trade-off acknowledged: `pyarrow` and a numeric/provider library are new dependencies this stage
    introduces (`requirements.txt` today lists only `pymupdf`/`pymupdf4llm`) — deliberate, not an
    oversight.
14. **Directory structure.**
    ```
    data/proposals/embeddings/<doc_id>/embeddings.parquet
    data/proposals/embeddings/<doc_id>/embedding_validation_report.json
    data/proposals/embeddings/<doc_id>/embeddings.checkpoint.jsonl   (transient — mid-run or after an interrupted run only)
    ```
    Sibling to the existing `extracted/<doc_id>/` and `chunks/<doc_id>/` per-document directories —
    this is Stage 8's own directory, added now because Stage 8 itself now exists, not the
    speculative `processed/embeddings/` placeholder the architecture doc deliberately declined to
    add earlier.
15. **Manifest updates & failure semantics.** Per the Manifest Update Convention:
    `artifact_paths["embeddings"]` set only if the file was successfully, atomically written (PASS/
    WARNING); `artifact_paths["embedding_validation_report"]` always set. Unconditional every run:
    `completed_at`, `pipeline_version` (the shared `PIPELINE_VERSION` constant — never Stage 8's own
    `EMBEDDING_PIPELINE_VERSION`, which stays inside the parquet/report headers only). On success:
    `error_code = None`; `status` is **never touched** (status promotion remains a future stage's
    job). On FAIL (Critical validation finding, exhausted retries, or artifact-write failure):
    `status = QUARANTINED`, `error_code = "FATAL_EMBEDDING_FAILED"` — per the QUARANTINED-Reuse
    Convention, meaning embedding generation specifically could not complete, not that `chunks.json`
    or any upstream artifact is invalid. A mere run interruption is explicitly not a FAIL.
16. **Logging.** Per the Logging Specification, this stage's own closed-vocabulary additions:
    `WARNING_EMBEDDING_CHECKSUM_STALE` (a chunk queued for regeneration due to a text change —
    expected, normal), `WARNING_EMBEDDING_ORPHAN_CHUNK`, `WARNING_EMBEDDING_RATE_LIMITED`,
    `WARNING_EMBEDDING_RETRY` (a transient error retried and then succeeded); ERROR codes
    `FATAL_EMBEDDING_FAILED` (any FAIL outcome) and `FATAL_EMBEDDING_PROVIDER_UNAVAILABLE` (a
    distinguishable sub-case — the adapter itself couldn't be constructed/authenticated — kept
    separate purely for operator triage: "never even started" vs. "started and failed partway").
17. **Error handling.** Same per-document `try`/`except` boundary as every prior stage — one
    document's failure never blocks the batch. No document-level retry loop; a batch-level
    exhausted-retry is already the correctly-scoped failure unit. Idempotent reruns: a document with
    `"embeddings" in record.artifact_paths` already, under an unchanged `config_fingerprint`,
    produces zero provider calls on rerun — finer-grained, per-chunk incremental idempotency than
    Stage 7's coarser "skip if chunks already exist" gate.

## Schema

Embedding record — every field, and why it exists:

1. **`embedding_id`** (str) — deterministic composite key:
   `f"{chunk_id}__{provider}__{model_name}__{model_version}"`, any character outside
   `[A-Za-z0-9_.-]` replaced by `-` (model names commonly contain `/`). Never a random UUID —
   reproducibility requires the identical config against the identical chunk always yields the
   identical id. Human-readable by construction, matching Stage 7's own `chunk_id` design.
2. **`chunk_id`** (str) — FK back to `chunks.json`; the sole join key to text, position, and section
   metadata.
3. **`doc_id`** (str) — redundant with the `chunk_id` prefix, stored for direct per-doc filtering
   without string-parsing, mirroring Stage 7's own denormalization convenience.
4. **`provider`** (str).
5. **`model_name`** (str).
6. **`model_version`** (str) — pinned, never `"latest"`.
7. **`embedding_dimension`** (int) — stored redundantly (not just inferred from vector length) so a
   validator can check consistency without decoding every vector.
8. **`embedding_vector`** (list<float32>) — `float32`, not `float64` — halves storage with precision
   standard for cosine/dot-product similarity use.
9. **`text_checksum`** (str) — sha256 hex digest of the chunk's `text`, the staleness/change-
   detection key.
10. **`config_fingerprint`** (str) — sha256 hex digest of the canonical JSON of `{provider,
    model_name, model_version, embedding_dimension, <provider config_fingerprint_fields>}` — the
    "exact recipe" identity (Decision 5).
11. **`created_at`** (str, ISO 8601) — when this row was generated, reusing the existing
    `get_now_iso()` helper shared by Stages 0/1/7.
12. **`embedding_pipeline_version`** (str) — Stage 8's own independent version constant,
    `EMBEDDING_PIPELINE_VERSION = "1.0.0"`. Lives only in this schema and the validation report
    header, never touches `ManifestRecord.pipeline_version`.
13. **`source_chunk_char_count`** (int) — `len(chunk["text"])` at embedding time; a cheap sanity
    signal for the validator (catches a checksum-collision or bookkeeping bug) and useful for later
    average-tokens-per-chunk metrics.

**Deliberately excluded:** chunk `text`, `heading_path`, `category`/`doc_type`/`title`. Why:
duplicating full chunk text into every embedding row, multiplied by every provider/model rerun,
multiplies storage for no benefit — `chunks.json` remains the single source of truth for content,
and `text_checksum` is exactly the mechanism designed to detect drift without a duplicated copy.

`embedding_validation_report.json` — same shape as `chunk_validation_report.json`, plus a `stats`
block:

```jsonc
"stats": {
  "total_embeddings": 87,
  "reused_count": 80,
  "generated_count": 7,
  "avg_embedding_dimension": 384,
  "distinct_config_fingerprints": 1
}
```

**Finding codes** (Validation Severity Tiers convention):

**Critical** (any one → overall FAIL):
- `EMBEDDING_IDS_UNIQUE` — duplicate `embedding_id` within one doc's artifact.
- `EMBEDDING_COVERAGE_COMPLETE` — every `chunk_id` in the current `chunks.json`, under the run's
  `config_fingerprint`, has exactly one embedding row.
- `EMBEDDING_VECTOR_NOT_EMPTY` — a row has a null/zero-length vector.
- `EMBEDDING_DIMENSION_CONSISTENT` — all rows sharing a `config_fingerprint` report identical
  `embedding_dimension`, equal to `len(embedding_vector)`.
- `EMBEDDING_NO_NAN_INF` — no NaN/Inf float values anywhere in a vector.
- `EMBEDDING_PROVIDER_MATCH` — a row's `provider`/`model_name`/`model_version` are internally
  consistent with its own `config_fingerprint`.
- `EMBEDDING_ARTIFACT_READABLE` — the parquet file opens and its schema matches the expected column
  set/types.
- `EMBEDDING_CHECKSUM_WELL_FORMED` — `text_checksum` is present and exactly 64 hex characters.

**Recoverable** (→ WARNING unless a Critical also fired):
- `EMBEDDING_CHECKSUM_STALE` — a row's stored `text_checksum` no longer matches the current chunk's
  checksum. Expected/normal between an upstream text edit and the next Stage 8 run.
- `EMBEDDING_ORPHAN_CHUNK` — a row's `chunk_id` no longer exists in the current `chunks.json`. Never
  auto-deleted — additive, flagged for a future cleanup step.
- `EMBEDDING_CHECKPOINT_LEFTOVER` — `embeddings.checkpoint.jsonl` still exists after the run reports
  completion — a prior run was interrupted and not yet cleanly resumed/finalized.

## Functions / Contracts

**Provider Abstraction Layer** — contract every adapter must satisfy (orchestration never branches
on provider identity):

- `provider_name` — short, fixed string identifying the provider family (e.g.
  `"sentence_transformers"`, `"openai"`, `"voyage_ai"`, `"nomic"`). Part of `config_fingerprint`.
- `model_name` — the provider's own model identifier, verbatim.
- `model_version` — a **pinned** version/revision string; `"latest"` or any unpinned alias is
  disallowed by contract, since it silently breaks reproducibility. The contract requires
  `model_version` change whenever output could change — an operator responsibility, not something
  Stage 8 can verify automatically (Self-Critique #2).
- `embedding_dimension` — discovered from the provider's actual first returned vector at run start,
  not hardcoded per adapter; every subsequent vector is validated against it.
- `embed_batch(texts) -> results` — given an ordered list of chunk texts, returns one vector per text
  in the same order. Must be deterministic for local models given identical inputs/config; hosted
  APIs treated as deterministic-enough at a fixed `model_version` (Self-Critique #3).
- `is_transient_error(exception) -> bool` — classifies retryable failures (timeouts, rate limits,
  transient network errors) versus fatal ones (auth failure, malformed input, quota exhausted
  permanently). All provider-specific error taxonomy lives here.
- `requests_per_minute` (optional) — a provider-declared throttle the batch loop consults; `None`
  for unthrottled local providers.
- `max_batch_size` (optional) — a provider-declared upper bound on `embed_batch` input size;
  `BATCH_SIZE` is clamped to `min(BATCH_SIZE, provider.max_batch_size)` when set.
- `config_fingerprint_fields` — additional identity fields (beyond provider/model/version/dimension)
  this specific provider contributes to `config_fingerprint` (e.g. `normalize=True/False`,
  `task_type`). Extensible per provider without touching the fingerprint mechanism.

No default provider is stubbed or selected — implementing the first concrete adapter is a separate,
later task.

## Self-Critique

1. Provider lock-in at the config-fingerprint level — once embedded under one `config_fingerprint`,
   comparing against another provider's vectors is meaningless (different vector spaces). Inherent
   to embeddings generally; the fingerprint makes the incompatibility visible and structural rather
   than a silent bug.
2. `model_version` pinning relies on operator discipline, not automatic detection — Stage 8 can only
   enforce that `"latest"` is rejected, not that a library upgrade silently changed output under an
   unchanged version string. A documented contract obligation on the adapter implementer.
3. Hosted-API determinism is assumed, not guaranteed (e.g. floating-point non-determinism from
   batched GPU inference server-side). No client-side mitigation is possible; the checksum/
   fingerprint mechanism still correctly avoids unnecessary re-embedding.
4. Dimension migration requires a full re-embed with no partial-compatibility path — acceptable at
   13 documents / low thousands of chunks; would need a genuinely different design at much larger
   scale.
5. Storage growth is unbounded and append-only — every provider/model switch adds a full new row set
   per document, never pruned automatically. Negligible at today's scale; a future pruning/archival
   stage is the natural mitigation, not designed here.
6. Checkpoint corruption is not itself validated — a crash during a partial line write is mitigated
   by treating any unparseable trailing line as incomplete and re-embedding that one row (cheap,
   idempotent), but not exhaustively specified at the line level.
7. Rate limiting is a simple sleep-based token bucket, not a true adaptive limiter reacting to
   provider "retry-after" headers — acceptable because the retry/backoff policy already absorbs
   occasional rate-limit errors as transient failures.
8. API failures beyond `MAX_RETRIES` abort the whole document, not just the failing batch — accepted
   deliberately to avoid ever producing a silently-incomplete artifact; the checkpoint means a
   subsequent run resumes cheaply, so the cost is an extra invocation, not lost work.
9. Embedding reproducibility can't be verified independently of the provider — only the pipeline's
   own bookkeeping (checksums, dimensions, coverage) is internally consistent; an inherent limit of
   black-box provider integration.
10. Future ANN-index compatibility is unverified by design — no index is built or referenced here,
    per the "no vector DB" constraint; a future conversion step will be required, accepted as that
    future stage's cost.
11. Large-corpus scaling is not engineered for — in-memory batch processing, per-doc atomic rewrite,
    and full-corpus workload scans all assume low thousands of chunks; would not hold at 100k+
    chunks. Accepted under the "simple before scalable" precedent.
12. `has_table_content` is always inherited as-is from Stage 7 — Stage 8 only reads chunk `text`, so
    it embeds table content exactly as flattened upstream, an honest inherited gap, not compensated
    for here.
13. Five documents is a small real-corpus validation sample — literally all the real data past Stage
    7 today; expanding it is gated on more documents completing Stages 0-7, not on this design.
14. The provider abstraction can't fully anticipate every future provider's quirks (e.g. instruction-
    prefixed embeddings, multi-vector outputs) that might not fit the flat-dict fingerprint shape
    cleanly — a reasonable v1 scope, designed to be extended, not exhaustively future-proof.
15. No cost/budget tracking is designed for hosted providers — accepted as an operational/deployment
    concern, not a data-pipeline correctness concern, left to whoever operates a specific adapter.

No finding above requires an architectural redesign — every one is an accepted, bounded limitation.

## Test Plan

**Provider abstraction:**
1. `TestProviderContract` — a stub provider satisfying the full contract is accepted by the
   orchestrator with no provider-name branching in orchestration code.
2. `TestProviderContract.test_unpinned_model_version_rejected` — `model_version="latest"` is
   rejected at config-fingerprint construction time.
3. `TestProviderContract.test_max_batch_size_clamping` — `BATCH_SIZE` clamps to
   `provider.max_batch_size` when smaller.

**Embedding record schema & checksum:**
4. `TestChecksum.test_hash_excludes_position_metadata` — identical `text`, different position
   metadata → identical `text_checksum`.
5. `TestChecksum.test_hash_changes_on_text_change` — a single-character text change changes the
   checksum.
6. `TestEmbeddingId.test_deterministic` — identical `(chunk_id, provider, model_name, model_version)`
   always produces the identical `embedding_id`.
7. `TestEmbeddingId.test_sanitization` — a `model_name` containing `/` and spaces produces a
   filesystem/parquet-safe `embedding_id`.
8. `TestConfigFingerprint.test_changes_with_any_field` — changing provider, model_name,
   model_version, or embedding_dimension each independently changes the fingerprint.

**Pipeline stages:**
9. `TestDetermineWorkload` — a mixed unchanged/changed/new corpus correctly partitions REUSE vs
   GENERATE.
10. `TestBatchGeneration` — GENERATE workload processed in `chunks.json` order, in `BATCH_SIZE`
    batches, expected call count on the stub provider.
11. `TestPersistEmbeddings` — REUSE and GENERATE rows merge into the final parquet with no duplicate
    `embedding_id`s.
12. `TestUpdateManifest` — success sets `artifact_paths`, clears `error_code`, never touches
    `status`; FAIL sets `status=QUARANTINED`, `error_code="FATAL_EMBEDDING_FAILED"`, still writes the
    validation report.

**Rerun determinism & incremental regeneration:**
13. `TestRerunDeterminism.test_unchanged_config_full_reuse` — a second run with no upstream changes
    makes zero provider calls.
14. `TestIncrementalRegen.test_single_chunk_text_change` — changing one chunk's text regenerates only
    that chunk's row; every other row byte-identical.
15. `TestIncrementalRegen.test_model_change_regenerates_all_under_new_fingerprint` — switching
    `model_version` regenerates all chunks under the new fingerprint; old-fingerprint rows untouched.

**Provider abstraction & dimension validation:**
16. `TestDimensionValidation.test_mismatch_flagged_critical` — a wrong-length vector trips
    `EMBEDDING_DIMENSION_CONSISTENT` as Critical.
17. `TestDimensionValidation.test_nan_flagged_critical` — a NaN-containing vector trips
    `EMBEDDING_NO_NAN_INF`.

**Resume after interruption & partial batch failure:**
18. `TestResume.test_checkpoint_resumes_past_completed_batches` — a simulated crash after 2 of 5
    checkpointed batches; a second invocation embeds only the remainder.
19. `TestResume.test_no_corrupted_final_artifact_on_crash` — a simulated mid-run crash leaves the
    previous `embeddings.parquet` fully intact and readable.
20. `TestPartialBatchFailure.test_exhausted_retries_aborts_without_gap` — a stub provider that always
    fails one batch exhausts `MAX_RETRIES` and aborts without a partial-coverage artifact.
21. `TestPartialBatchFailure.test_nontransient_error_fails_fast` — a non-transient error is not
    retried.

**Corrupted embedding detection:**
22. `TestCorruptedArtifact.test_truncated_parquet_flagged` — a hand-truncated parquet trips
    `EMBEDDING_ARTIFACT_READABLE` as Critical.
23. `TestCorruptedArtifact.test_malformed_checksum_flagged` — a non-64-hex-char `text_checksum` trips
    `EMBEDDING_CHECKSUM_WELL_FORMED` as Critical.
24. `TestCorruptedArtifact.test_orphan_chunk_flagged_warning` — a row referencing an absent
    `chunk_id` trips `EMBEDDING_ORPHAN_CHUNK` as Recoverable, not deleted.

**Real corpus verification:**
25. `TestRealCorpus.test_five_eligible_documents_selected` — the real manifest's selection gate
    picks exactly the 5 documents with `"chunks" in artifact_paths`.
26. `TestRealCorpus.test_full_run_with_stub_provider` — a full run against all 5 real `chunks.json`
    files, with a deterministic stub provider (no network/model dependency in CI), produces one
    `embeddings.parquet` per doc with row count exactly equal to `chunk_count`, zero Critical
    findings.
27. `TestRealCorpus.test_rerun_against_real_corpus_is_no_op` — a second run against the same real
    corpus with the same stub config makes zero new-row writes.
