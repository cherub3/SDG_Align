# Stage 9 — Vector Indexing

Stages 0–8 remain completely frozen; nothing below proposes any change to existing code or
shipped docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Scope

Stage 9 builds and validates a searchable vector index from Stage 8's `embeddings.parquet` output:
(1) select and re-validate eligible embedding rows, (2) build/update/persist a vector index (via a
pluggable `IndexAdapter`, see Backend) plus its id-to-metadata mapping, (3) validate the resulting
index's own structural integrity and write a report. Out of scope: retrieval, ranking, answering
questions, calling an LLM, evaluating retrieval quality — later stages' jobs. Inputs, read-only,
never mutated: `manifest.json`, every eligible document's `embeddings.parquet`, and `metadata.json`
(denormalized `category`/`doc_type`/`title` only). No PDF is ever reopened; no embedding is ever
regenerated.

## Pipeline

```
manifest.json
      │
      ▼
[1] Load manifest & select eligible documents
      gate: "embeddings" in record.artifact_paths        (never record.status)
      ▼
[2] Discover config_fingerprints present corpus-wide, combine each with this run's configured
      backend_name + metric → one index_fingerprint per combination (see Backend, Incremental Indexing)
      ▼
[3] For each index_fingerprint, independently:
      ├─▶ [3a] Load & re-validate source rows; a document whose rows fail is EXCLUDED from this
      │        build only — never blocks the rest of the corpus (see Design Decisions)
      ├─▶ [3b] Load existing index (if any) for this index_fingerprint from the live directory
      ├─▶ [3c] Determine indexing workload: REUSE / ADD / RE-INDEX / REMOVE (see Incremental Indexing)
      ├─▶ [3d] Apply workload to a staging copy — the live index is untouched throughout
      ├─▶ [3e] Validate the staging index — full-validation, no-fail-fast (see Schema)
      ├─▶ [3f] Write index_validation_report.json — ALWAYS, regardless of outcome (see Atomicity)
      ├─▶ [3g] Any Critical finding? ──yes──▶ discard staging; live index untouched; no manifest
      │        │                              write for this fingerprint's documents
      │        │no
      ├─▶ [3h] Atomically swap staging directory over the live one (see Atomicity)
      └─▶ [3i] Update manifest for every contributing document (see Manifest)
      ▼
[4] Save manifest once, emit a run-level metrics summary
```

## Backend

**Contract (`IndexAdapter`)** — mirrors Stage 8's own `ProviderAdapter` pattern: no orchestration
logic (workload determination, atomicity, validation, manifest updates) ever branches on which ANN
library is in use.
- `backend_name` (str), `backend_version` (str, informational only — excluded from
  `index_fingerprint`, see Schema).
- `metric` (str) — one of `"cosine" | "inner_product" | "l2"`.
- `build(dim)`, `add(ids, vectors)`, `remove(ids)` — **true** removal, not a soft/tombstone mark.
- `search(query, k)` — internal validation use only (see Schema's `INDEX_SELF_QUERY_SANITY`); never
  exposed for real retrieval.
- `serialize(path)` / `deserialize(path)`, `ntotal` (property).

**Comparison:**

| | FAISS | hnswlib | Annoy | ScaNN |
|---|---|---|---|---|
| Performance (this scale) | Exact, sub-ms for thousands of vectors; no training step for Flat | Approximate, fast, but solves a problem this corpus doesn't have yet | Approximate; comparable at small scale | Optimized for far larger scale than this corpus |
| Memory | Flat ≈ `n × d × 4` bytes, negligible here | Graph overhead per vector vs. Flat | Tree forest, moderate overhead | Heaviest of the four |
| Incremental updates | `IndexIDMap2` supports true `add`/`remove` | `add_items` only; deletion is soft-mark-only, never reclaims space | **None** — immutable after `build()`; directly conflicts with "incremental" | Not designed around small, frequent updates |
| Cross-platform | Official pip wheels, Win/Linux/macOS | Pip-installable, no system binary | Pip-installable, no system binary | Historically weak Windows support |
| Serialization | Single-file binary, stable within a major version | Single file | Memory-mapped, read-only after build | Own SavedModel-style format, heavier |
| Community maturity | Largest, most production use | Solid, narrower, single index type | Mature but feature-frozen | Smaller outside Google-scale users |
| Verdict | **Chosen** | Rejected — soft-delete-only is a worse fit than real removal | Rejected — immutability disqualifies it | Rejected — scale/platform mismatch |

**Chosen: FAISS, exact search (`IndexIDMap2(IndexFlatIP)`), the first `IndexAdapter`
implementation.** Two reasons: (a) at this corpus's real scale (341 vectors today per the real
`embedding_validation_report.json`) brute-force is sub-millisecond and needs no training step; (b)
exact search is the only ANN-adjacent option compatible with Principle 1 (deterministic,
byte-identical output) — HNSW/IVF graph construction is order- and threading-dependent, so two
builds from identical input aren't guaranteed byte-identical. `faiss-cpu` ships pip wheels for
Windows/Linux/macOS, matching the project's "pure pip wheels, no system binaries" constraint. Since
the contract isolates this choice, nothing else in this design depends on FAISS specifically — a
future backend swap (an approximate index, once scale genuinely demands one) is scoped to a new
adapter implementation plus a new `backend_name`, no other change (see Known Limitations).

## Design Decisions

1. **Document selection.** Gate is `"embeddings" in record.artifact_paths`, never `record.status` —
   nothing in the frozen codebase ever promotes status past what Stage 0–3 already set.
2. **Index scope: one corpus-wide index per `index_fingerprint`, not per document.** A deliberate
   break from every prior stage's per-doc-directory convention — a document-scoped index can't be
   searched across the corpus, defeating the point. Two documents under different
   `config_fingerprint`, metric, or backend get separate, non-comparable indexes, never merged.
3. **Deterministic `index_fingerprint` — the index's own identity.**
   `index_fingerprint = sha256(canonical_json({config_fingerprint, backend_name, metric}))`. Built
   from exactly those three deterministic inputs — never a timestamp, UUID, or random value.
   `backend_version` is deliberately excluded (a library version bump doesn't change the vector
   space — see Incremental Indexing) and recorded informationally only.
4. **ID identity inside the index: `embedding_id`, not `chunk_id`.** `embedding_id` already encodes
   `chunk_id` + provider + model + version, so it's the correct join key for "is this exact embedding
   already indexed" — `chunk_id` alone can't distinguish two different embeddings of the same chunk
   under two configs. Each `embedding_id` maps to a fixed `adapter_internal_id` via a deterministic
   hash (see Constants) — stable across reruns and independent of what else is added/removed,
   required for true incremental add/remove without reshuffling every other vector's id. Collision
   risk is caught defensively by `INDEX_ID_NO_COLLISION` (Schema), not assumed away. `id_map.parquet`
   (Schema) resolves `adapter_internal_id → embedding_id → chunk_id → doc_id`.
5. **Distance metric — named explicitly, never a backend default.** `metric = "cosine"`, implemented
   as inner product over L2-normalized vectors (normalization applied by Stage 9 itself before every
   `add`/`search`, recomputed fresh each time rather than stored back into Stage 8's frozen schema).
   A first-class `index_fingerprint` input: changing it produces a new namespace, never a silent
   reinterpretation of an existing one.
6. **Incremental workload rule.** Per valid row: `embedding_id` present + `text_checksum` matches →
   REUSE. Present, checksum differs → RE-INDEX. Absent → ADD. An `id_map` entry no longer present
   among current valid rows → REMOVE. Direct extension of Stage 8's own `determine_workload` reuse
   rule one level downstream (see Incremental Indexing for the full scenario matrix).
7. **Per-document failure isolation.** Stage 9 independently re-validates every source row (does not
   blindly trust Stage 8's own report). A document whose rows fail is excluded from this
   `index_fingerprint`'s build only, flagged `INDEX_DOCUMENT_PARTIALLY_EXCLUDED`/
   `INDEX_DOCUMENT_EXCLUDED` (Recoverable), and quarantined on its own manifest record only — a
   **Critical** finding is reserved exclusively for problems with the index artifact itself.
8. **Search-sanity validation reconciled against the "no search" scope boundary.** Every check in
   Schema's `INDEX_SELF_QUERY_SANITY` is an internal, discarded self-query against vectors already
   known to be in the index — never an externally-served query, never a ranked result returned to
   any caller, never a relevance judgment. The same distinction Stage 6 draws for "resolves metadata
   fields" without performing SDG classification.

## Incremental Indexing

Every named scenario, exhaustively, with `index_fingerprint` stability marked explicitly:

| Scenario | `index_fingerprint` changes? | Effect |
|---|---|---|
| One chunk's text changes (`chunk_id` unchanged) | No | Same `embedding_id`, new `text_checksum` → **RE-INDEX** that one vector only. |
| A chunk is deleted | No | Its `embedding_id` disappears from valid rows → **REMOVE** on next build; `INDEX_ORPHAN_VECTOR` until then. |
| Rerun with no real change | No | Every row's `embedding_id`+`text_checksum` match → **REUSE** for all, zero adapter calls. |
| Embedding provider, model, or model_version changes | Yes | New `config_fingerprint` → new `index_fingerprint`; **ADD**-only under the new namespace; old index untouched, not deleted. |
| Embedding dimension changes | Yes | Collapses into the model-change case (`config_fingerprint` already encodes dimension) — never a partial/in-place migration. |
| Similarity metric changes | Yes | New namespace, full rebuild; old-metric index remains valid under its own fingerprint. |
| Index backend changes | Yes | New namespace, full rebuild via the new adapter; no attempt to convert one backend's format to another's. |
| Index backend library version changes only | No | `backend_version` excluded from the fingerprint (Design Decision 3) — reused as-is; `INDEX_BACKEND_VERSION_DRIFT` (Recoverable) surfaces it informationally. |
| A document becomes newly eligible | No (same config/metric/backend) | **ADD** for that document's vectors only; every other document untouched. |
| A document becomes ineligible again | No | Its rows absent from current valid rows → **REMOVE** for all its vectors, same mechanism as a deleted chunk at document granularity. |

## Schema

**`index_metadata.json`** — one per `index_fingerprint` directory:
```jsonc
{
  "index_fingerprint": "...",           // this index's deterministic identity — the directory name
  "config_fingerprint": "...",          // Stage 8's own namespace; one of the three fingerprint inputs
  "backend_name": "faiss",              // one of the three fingerprint inputs
  "backend_version": "1.8.0",           // informational only — excluded from the fingerprint
  "backend_detail": "IndexIDMap2(IndexFlatIP)",  // exact backend-native composition used
  "metric": "cosine",                   // the third fingerprint input
  "metric_implementation": "inner_product",  // how the adapter actually realizes the metric
  "normalization": "l2",
  "provider": "...", "model_name": "...", "model_version": "...",  // denormalized, human-readable
  "embedding_dimension": 384,
  "vector_count": 341,                  // == index.ntotal == len(id_map)
  "document_count": 5,
  "chunk_count": 341,                   // == vector_count today; kept separate for a future
                                         // multi-vector-per-chunk provider
  "index_pipeline_version": "1.0.0",    // stage-local, distinct from the shared PIPELINE_VERSION
  "created_at": "...",
  "source_doc_ids": ["doc_...", "..."]
}
```

**`id_map.parquet`** — one row per indexed vector: `adapter_internal_id` (int64, deterministic hash
of `embedding_id`), `embedding_id`, `chunk_id`, `doc_id`, `text_checksum` (the staleness signal, see
Incremental Indexing), `index_fingerprint`, `indexed_at`.

**`index_validation_report.json`** — mirrors `embedding_validation_report.json`'s real, shipped
shape (`index_fingerprint`, `config_fingerprint`, `index_pipeline_version`, `pipeline_version`,
`validated_at`, `outcome`, `summary{outcome,error_count,warning_count,finding_count}`,
`stats{vector_count,documents_included,documents_excluded,added_count,reused_count,reindexed_count,
removed_count}`, `findings[]`).

**Validation finding codes** (Critical/Recoverable per `docs/pipeline_principles.md` §4):

Critical (→ this fingerprint's build FAILs; staging discarded, live index untouched):
`INDEX_ARTIFACT_READABLE`, `INDEX_VECTOR_COUNT_MATCHES_ID_MAP`, `INDEX_NO_DUPLICATE_IDS`,
`INDEX_DIMENSION_CONSISTENT`, `INDEX_ID_NO_COLLISION`, `INDEX_COVERAGE_COMPLETE`,
`INDEX_SELF_QUERY_SANITY` (a known vector's top-1 result is itself at similarity ≈ 1.0, AND
`search()` succeeds/returns a result at all), `INDEX_NOT_EMPTY`.

Recoverable (→ WARNING unless a Critical also fired): `INDEX_ORPHAN_VECTOR` (never auto-removed by
the validator — only the next build's REMOVE step prunes it), `INDEX_METADATA_STALE` (recorded
counts vs. a fresh `id_map` recount), `INDEX_DOCUMENT_PARTIALLY_EXCLUDED`,
`INDEX_BACKEND_VERSION_DRIFT` (informational — a backend's on-disk format is generally stable within
a major version, so this alone never implies `INDEX_ARTIFACT_READABLE` should fail).

## Constants

Named, undocumented-elsewhere thresholds this design introduces (same pattern as every prior
stage's own `MIN_CHARS_PER_PAGE`/`HEADER_FOOTER_MIN_OCCURRENCES`-style constants):
```python
ADAPTER_ID_HASH_HEX_CHARS = 15        # hex chars of sha256(embedding_id) used to build
                                       # adapter_internal_id — a deterministic 60-bit value,
                                       # safely within signed int64
SELF_QUERY_SAMPLE_SIZE = 10           # min(10, ntotal) known vectors sampled per self-query check
SELF_QUERY_SIMILARITY_TOLERANCE = 1e-4  # float32 tolerance for "top-1 result is itself, sim ≈ 1.0"
STAGING_DIR_SUFFIX = ".building"      # transient staging directory naming convention
```

## Atomicity

`index.<ext>`, `id_map.parquet`, and `index_metadata.json` must stay mutually consistent as one
unit — replacing only the index binary, or replacing the three files as separate
`tmp`+`os.replace()` operations (Stage 8's own single-file pattern), risks a live directory whose
metadata describes a different index than what's actually on disk. Instead: the entire build for one
`index_fingerprint` happens inside `vector_index/<index_fingerprint>.building/`, and the whole
directory — index, id_map, and metadata together — is atomically swapped over the live one with one
`os.replace(staging_dir, live_dir)`, a single filesystem rename, atomic on both POSIX and NTFS.

No mid-build checkpoint file (contrast with Stage 8): `IndexAdapter.add()` on an exact Flat-style
index is local, memory-bound, cheap — no network calls, no training step — so a full staging build
completes fast even from scratch. Crash-safety comes from two guarantees: the live index is never
touched until staging is fully validated and ready to swap, and the next run's own incremental
workload determination naturally resumes by only doing the delta.
`index_validation_report.json` is written unconditionally, independent of whether the triad swap
happens — a totally-failed build still leaves a report explaining why.

## Manifest

`ManifestRecord` is frozen (11 fields, no new `DocumentStatus` member). Stage 9 introduces **no new
lifecycle concept of any kind** — no `INDEX_BUILT`/`INDEX_READY`/`INDEX_COMPLETE` pseudo-status,
nothing beyond the same `artifact_paths`-presence pattern every prior stage already uses. Every
document that contributed at least one vector to a successful `index_fingerprint` build gets
`artifact_paths["vector_index"]` (the fingerprint's directory path) and
`artifact_paths["index_validation_report"]` set — the same shared value across every contributing
document's own record, since the artifact is corpus-scoped, not document-scoped. `status` stays
untouched on success. A document excluded during re-validation gets `status = QUARANTINED`,
`error_code = "FATAL_INDEXING_FAILED"` on its own record only; a document whose fingerprint's whole
build failed Critical is left completely untouched — nothing about its state actually changed. "Is
this document searchable" is answered purely by `"vector_index" in record.artifact_paths`, never a
status value.

## Directory Structure

```
data/proposals/vector_index/<index_fingerprint>/
  index.<ext>                     # backend-native binary, via IndexAdapter.serialize()
  id_map.parquet
  index_metadata.json
  index_validation_report.json
data/proposals/vector_index/<index_fingerprint>.building/   # transient, mid-build only
```
Sibling to `extracted/`, `chunks/`, `embeddings/` — no speculative structure beyond what this stage
itself needs.

## Logging

New codes only, same seven-field shared structure: `WARNING_INDEX_EMBEDDING_STALE` (a RE-INDEX was
triggered — expected), `WARNING_INDEX_ORPHAN_VECTOR`, `WARNING_INDEX_DOCUMENT_PARTIALLY_EXCLUDED`,
`WARNING_INDEX_BACKEND_VERSION_DRIFT`, `FATAL_INDEXING_FAILED` (per-document manifest `error_code`),
`FATAL_INDEX_BUILD_FAILED` (corpus-level — a Critical index-structural finding aborted the swap for
an entire fingerprint; distinct from `FATAL_INDEXING_FAILED`, which is always scoped to one
document's own excluded rows).

## Concurrency

Not supported. Only one Stage 9 process may execute at a time, corpus-wide — no file-locking
mechanism guards two simultaneous runs racing to write the same staging directory. The same
single-operator, single-process assumption every stage from Stage 0 through 8 already makes
implicitly, stated explicitly here because a corpus-wide shared artifact makes a collision more
consequential in practice than it ever was for any prior stage's per-document artifacts.

## Functions / Contracts

- `load_eligible_documents(manifest) -> List[ManifestRecord]` — filters `"embeddings" in
  record.artifact_paths`.
- `discover_config_fingerprints(records) -> Set[str]` — data-driven, corpus-wide scan.
- `compute_index_fingerprint(config_fingerprint, backend_name, metric) -> str` — deterministic
  sha256 over exactly those three inputs.
- `load_rows_for_fingerprint(records, config_fingerprint) -> Dict[str, List[Dict]]` — grouped by
  `doc_id`.
- `revalidate_rows(doc_id, rows) -> Tuple[List[Dict], List[Dict]]` — independent structural
  re-check; a non-empty Critical finding list excludes the document.
- `compute_adapter_internal_id(embedding_id) -> int` — deterministic hash (Constants).
- `normalize_vectors(vectors: np.ndarray) -> np.ndarray` — L2-normalize, pure/deterministic.
- `load_existing_index(index_fingerprint, adapter_factory) -> Optional[Tuple[IndexAdapter,
  pd.DataFrame, Dict]]` — reads the live (not staging) triad if present.
- `determine_index_workload(valid_rows, existing_id_map) -> IndexWorkload` — partitions into
  adds/reindexes/removes/reuses.
- `apply_workload_to_staging(existing_index, workload, dim, adapter_factory) -> Tuple[IndexAdapter,
  pd.DataFrame]` — never branches on `backend_name`.
- `run_self_query_sanity_check(index, id_map, sample_size) -> List[Dict]` — findings only; never
  returns ranked results to any caller.
- `validate_index(index, id_map, metadata, valid_rows) -> List[Dict]` — every Critical/Recoverable
  check in Schema, full-validation, no-fail-fast.
- `persist_index_atomic(index_fingerprint, index, id_map, metadata) -> Path` — staging + one
  directory-level `os.replace`; only called when no Critical finding fired.
- `write_index_validation_report(index_fingerprint, findings, outcome, stats) -> Path` — always
  called, single-file atomic write.
- `update_manifest_for_fingerprint(manifest, index_fingerprint, included_doc_ids, excluded) -> None`
  — sets `artifact_paths` for included docs; `QUARANTINED`/`FATAL_INDEXING_FAILED` for excluded docs
  only; introduces no new `DocumentStatus` value.
- `run_stage9(adapter_factory, metric) -> None` — orchestrates Pipeline [1]–[4]; backend and metric
  are run-time configuration, never hard-coded; loads/saves manifest once. Assumes single-invocation
  (Concurrency).

## Known Limitations

- Exact search's query cost grows linearly with vector count — fine at hundreds–low-thousands of
  vectors, not designed to scale further; the `IndexAdapter` contract makes a future approximate
  backend a bounded change, not a redesign.
- Any future move to an approximate backend weakens the byte-identical-output determinism guarantee
  for that one artifact (HNSW/IVF graph construction is order/threading-dependent) — a real,
  known cost of ever making that switch.
- The `IndexAdapter` contract may not fit a backend with a fundamentally different update model
  (e.g. a training/fitting step before any `add`) without extension — reasonable v1 scope, not
  exhaustively future-proof.
- The deterministic-hash `adapter_internal_id` has a theoretical, astronomically small collision
  risk at this scale — detected (`INDEX_ID_NO_COLLISION`), not cryptographically ruled out.
- A single shared, corpus-wide index breaks every prior stage's clean per-document artifact
  ownership — mitigated by per-document isolation, not eliminated: a corpus-level Critical finding
  still blocks the whole fingerprint's update in that run.
- The self-query sanity check proves structural soundness only, never retrieval quality — that
  question belongs to a future, separate evaluation stage.
- Embedding-version incompatibility across the corpus (documents under different fingerprints) is
  pushed downstream — a future retrieval stage must itself decide which index(es) to query.
- No automatic pruning/archival beyond the next incremental build's own REMOVE step — a
  temporarily-ineligible document's vectors linger until it's genuinely gone on a later build.
- `index_metadata.json`'s denormalized counts can drift from `id_map`'s own ground truth if hand-
  edited — detected (`INDEX_METADATA_STALE`), not structurally prevented.

## Accepted Tradeoffs

- **Full in-memory build.** Negligible today (a few MB–tens of MB); would need batched/on-disk
  construction at much larger scale — "simple before scalable," matching Stage 8's own precedent.
- **No mid-build checkpoint.** Local, memory-bound `add()` calls are cheap enough that a full
  staging rebuild is fast; crash-safety comes from the untouched-live-index guarantee instead.
- **`faiss-cpu` is a new dependency**, like `pyarrow` was for Stage 8 — no pure-stdlib alternative
  exists for vector indexing at all; isolated behind `IndexAdapter` so a future swap doesn't ripple.
- **Cross-version serialization isn't contractually guaranteed** bit-identical across FAISS
  versions — detectable via `backend_version`/`INDEX_BACKEND_VERSION_DRIFT`, not prevented; a
  version bump can always safely trigger a full, cheap reindex.
- **Concurrent builds are unsupported, undetected at runtime** — documented, not mechanically
  enforced, matching every prior stage's own implicit single-process assumption.
- **Normalization is recomputed on every build**, even for REUSEd vectors, rather than cached — a
  cheap, deterministic, idempotent operation; simplicity chosen over a small, unneeded optimization.

## Validation Requirements

What must be true, grouped by concern — the eventual test suite owns exact test names/counts, not
this document.

- **Backend independence.** No orchestration function branches on `backend_name`; a stub
  `IndexAdapter` satisfying the contract is sufficient to exercise the full pipeline; `remove()` is
  true removal, verifiable via a subsequent `search()`.
- **`index_fingerprint` determinism.** Identical `(config_fingerprint, backend_name, metric)` always
  yields the identical fingerprint, across process restarts; changing `backend_name` or `metric`
  alone changes it; changing `backend_version` alone does not; no timestamp/uuid/random ever
  contributes to it.
- **`adapter_internal_id` correctness.** Deterministic per `embedding_id`; a forced collision trips
  `INDEX_ID_NO_COLLISION`; two different embeddings of the same `chunk_id` (different configs)
  produce two distinct `id_map` rows, proving `chunk_id` alone is never the join key.
- **Incremental workload — every row in the Incremental Indexing matrix.** Unchanged
  `embedding_id`+`text_checksum` → zero adapter calls; a changed checksum → exactly one
  remove+add pair; a new/deleted `embedding_id` → exactly one add/remove; a provider, dimension,
  metric, or backend change → a full `ADD`-only workload under a new, separate `index_fingerprint`,
  old index left untouched; a `backend_version`-only change → `REUSE`, no new fingerprint.
- **Validation — every Critical and Recoverable code in Schema fires under its documented
  condition** and only that condition (a corrupted index file, a count mismatch, a duplicate id, a
  dimension mismatch, a coverage gap, a failed or successful self-query, an empty index with
  eligible rows; an orphan vector, stale metadata, a partially-excluded document, backend-version
  drift).
- **Atomicity.** The live directory is unmodified until the final swap; a successful build leaves
  index/id_map/metadata mutually consistent, never a stale mix; a Critical finding during staging
  validation leaves the live triad byte-identical to before the run; the validation report is
  written even on total failure; a simulated crash mid-build, followed by a plain rerun, completes
  normally with no special recovery path; no partial triad is ever visible in the live directory.
- **Manifest.** Included documents get both `artifact_paths` keys set; `status` is untouched on
  success; no manifest fixture in the suite ever writes a `DocumentStatus` value or string beyond
  the four existing ones; an excluded document is quarantined independently of the rest of the
  corpus; a fingerprint-level Critical failure leaves every contributing document's manifest record
  completely unchanged.
- **Determinism.** A no-op rerun makes zero adapter calls; a from-scratch rebuild run twice produces
  a byte-identical index binary and `id_map.parquet` (timestamps excluded); a single chunk's text
  change re-indexes exactly that one vector, nothing else.

## Real Corpus Verification

Against the real, current corpus (5 eligible documents, 341 vectors per the current real
`embedding_validation_report.json` stats): the selection gate picks exactly those 5 documents,
correctly grouped by their real `config_fingerprint`(s); a full run produces `vector_count` exactly
equal to the sum of valid real rows; the built index passes every Critical validator with zero
findings; two from-scratch rebuilds are byte-identical (timestamps excluded); every real document's
manifest record gets the expected `artifact_paths` additions with `status` unchanged; the validation
report exists, parses, and its stats agree with `index_metadata.json`; every upstream artifact
(`embeddings.parquet`, `chunks.json`, `metadata.json`, and every other `manifest.json` field) is
byte-identical before and after the run.
