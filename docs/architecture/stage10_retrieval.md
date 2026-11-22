# Stage 10 — Retrieval

Stages 0–9 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Scope

Stage 10 answers exactly one question — given a query string and a caller-chosen set of Stage 9
indexes, which chunks are most relevant, in what deterministic order — and stops there. It embeds
the query (via Stage 8's own `ProviderAdapter` contract, unchanged), searches one or more live
`index_fingerprint` directories (via Stage 9's own `IndexAdapter` contract, unchanged), joins hits
back to their full chunk records, applies caller-supplied metadata filters, and returns a ranked,
internally-validated in-memory result. Stage 10 introduces no new backend abstraction of its own —
it is a pure consumer of the two contracts Stage 8 and Stage 9 already froze.

Out of scope, explicitly: answer generation, LLM prompting/orchestration, citation formatting,
reranking with an LLM or cross-encoder, retrieval-quality evaluation, feedback loops, result
caching, conversation memory, any UI, any network-facing API. No PDF is ever reopened; no chunk is
ever generated; no embedding is ever generated for corpus content (only for the query itself, using
the exact same provider/model already recorded on the target index). Those boundaries are restated
in Future Stage Boundaries.

## Inputs

Read-only, never mutated, in every case:

- `manifest.json` — resolves `doc_id → artifact_paths` for the `chunks` and `vector_index` keys, and
  is the live source of truth for "is this document's chunk still eligible" (see Design Decisions).
- Every candidate `index_fingerprint`'s live triad: `index.bin`, `id_map.parquet`,
  `index_metadata.json` (and, informationally, `index_validation_report.json` — see Design
  Decisions).
- Each contributing document's `chunks.json` (Stage 7 output) — the sole source of full chunk
  records (`text`, `heading_path`, `section_ids`, page range, denormalized `category`/`doc_type`/
  `title`); read lazily, only for `doc_id`s that actually appear in a query's candidate set.
- `metadata.json`, read only for the narrow purpose of validating a caller-supplied filter value
  against the corpus's known classification values (see Design Decisions) — not used for chunk
  assembly, since `chunks.json` already carries the fields needed for that.

## Outputs

None persisted. Stage 10 produces zero artifacts and writes to no file — the first fully read-only
stage in this pipeline. Its sole output is an in-memory `RetrievalResult` (see Schema) returned
directly to the caller. Whether/how a caller logs, caches, or serves that result is explicitly a
later stage's concern (see Future Stage Boundaries).

## Pipeline

```
RetrievalRequest { query, index_fingerprints, top_k, filters }
      │
      ▼
[1] preprocess_query(query)          — strip() + Unicode NFC only; empty (post-strip) → QUERY_EMPTY,
      status="FAIL", done. Frozen, permanently: no lowercasing, stemming, lemmatization, synonym
      expansion, spell correction, or stopword removal (see Design Decisions).
      │
      ▼
[2] normalize_index_fingerprints(index_fingerprints)
      empty list ──▶ INDEX_FINGERPRINTS_EMPTY, status="FAIL", done, nothing else runs
      duplicate entries ──▶ silently deduplicated, first-appearance order preserved, no finding
      │
      ▼
[3] resolve_index_fingerprints(deduplicated list, manifest)
      no live directory ever existed for a fingerprint ──▶ INDEX_NOT_FOUND (WARNING), ignored
      live triad exists but fails to deserialize ──▶ INDEX_ARTIFACT_READABLE (FAIL), excluded
      │
      ▼
[4] group resolved indexes by distinct (provider, model_name, model_version, embedding_dimension)
      — a request naming fingerprints under different providers simply yields more than one group,
      each handled fully independently from here on; never an error condition (Design Decisions)
      │
      ▼
[5] embed_query(query, provider_adapter) once per distinct group
      failure ──▶ QUERY_EMBEDDING_FAILED (FAIL), every index in that group excluded, continue with
      the rest
      │
      ▼
[6] for each surviving index_fingerprint, independently:
      ├─▶ [6a] validate query vector dimension == index_metadata.embedding_dimension
      │        mismatch ──▶ EMBEDDING_DIMENSION_MISMATCH (FAIL), this index excluded
      ├─▶ [6b] k_search = min(top_k * OVERFETCH_MULTIPLIER, index.ntotal)
      ├─▶ [6c] adapter.search(query_vector, k_search)  →  (distances, internal_ids)
      ├─▶ [6d] map internal_ids → id_map rows → embedding_id/chunk_id/doc_id
      ├─▶ [6e] normalize_score(distance, index_metadata.metric)  — per-metric deterministic transform
      └─▶ [6f] cross-check doc_id still has "vector_index" in manifest[doc_id].artifact_paths and
               status != QUARANTINED — a doc quarantined after indexing is silently excluded here
      ▼
[7] apply_metadata_filters(all candidates, filters)   — AND of category/doc_type/doc_ids, exact
      match; an unknown filter value never excludes or fails anything by itself (Design Decisions)
      │
      ▼
[8] assemble_results(surviving candidates)   — join to full chunks.json record per candidate; `text`
      copied verbatim, byte-for-byte — no truncation, modification, normalization, or highlighting
      │
      ▼
[9] merge_and_rank(assembled)
      ├─▶ [9a] dedup by chunk_id across indexes first — highest normalized score wins, loser dropped
      ├─▶ [9b] sort surviving candidates by score desc, tie-break by chunk_id asc
      ├─▶ [9c] truncate to top_k
      └─▶ [9d] assign rank 0..len(results)-1, contiguous — computed only here, strictly after dedup
               and truncation, never before
      ▼
[10] validate_retrieval_result(result)   — internal invariant self-check; fires only on a genuine
      Stage 10 bug, raises RetrievalInternalError rather than returning a malformed result
      │
      ▼
RetrievalResult { status, results[], findings[], ... }
```

## Backends (reused, not reinvented)

Stage 10 defines no new pluggable-backend contract. It consumes exactly two already-frozen ones:

- **`ProviderAdapter`** (Stage 8) — `embed_query` is a thin wrapper calling
  `provider_adapter.embed_batch([query])[0]`; the same determinism assumption Stage 8 already
  documents (Self-Critique #3) is inherited, not re-verified.
- **`IndexAdapter`** (Stage 9) — `search_index` calls `adapter.deserialize(index_path)` then
  `adapter.search(query_vector, k)`, exactly the same `search()` method Stage 9's contract already
  reserved for "internal validation use only" — Stage 10 is the first and only caller that exercises
  it for its intended real purpose. No orchestration in Stage 10 ever branches on `backend_name` or
  `provider_name`.

Both adapter factories are runtime configuration, supplied by the caller — never hard-coded,
matching Stage 8/9's own `adapter_factory` convention.

## Design Decisions

1. **Explicit `index_fingerprints`, never auto-discovered-and-searched.** A caller must name which
   index(es) to query — via a literal fingerprint string or by first calling
   `list_available_indexes()` to discover one by its `provider`/`model_name`/`backend_name`/`metric`
   fields. Stage 10 never guesses "search everything" on the caller's behalf — silently mixing vector
   spaces of different providers/metrics is exactly the kind of hidden-state decision the shared
   Design Philosophy (Principle: no hidden state) forbids.
2. **Multi-index search is independent-then-merged, not a single combined index.** Each requested
   `index_fingerprint` is searched on its own, normalized to a comparable score, then merged before
   top-K selection. Query-embedding calls are deduplicated by distinct `(provider, model_name,
   model_version, embedding_dimension)` group — two indexes sharing the same embedding config (e.g.
   same vectors, two different backends/metrics) embed the query exactly once.
3. **Score normalization is a fixed, named, per-metric transform — never learned or calibrated.**
   `cosine` (inner product over L2-normalized vectors, Stage 9's own realization) — the raw
   `IndexAdapter.search()` distance is used directly as `score`, already bounded ≈`[-1, 1]`. `l2` —
   `score = 1 / (1 + distance)`, a fixed monotonic transform into `(0, 1]`. Scores are only strictly
   comparable within one metric family; mixing a cosine and an l2 index in one request is allowed but
   flagged as a documented, accepted limitation (see Known Limitations), never silently corrected.
4. **Deterministic tie-break: ascending `chunk_id`.** Two candidates with an identical normalized
   score are ordered by `chunk_id` string ascending — required by Principle 1 (deterministic,
   byte-identical output); a hash/float comparison alone is not a total order under ties.
5. **Metadata filtering happens after vector search, entirely against `chunks.json`'s own
   denormalized fields (`category`, `doc_type`, `title`) — never pushed into the backend.**
   `IndexAdapter.search()` (Stage 9's frozen contract) has no filter parameter; simplest-correct at
   this corpus's scale. Filters are an AND of exact-match equality only — `category`, `doc_type`,
   `doc_ids` (an explicit allow-list) — no boolean query language, no partial/fuzzy match.
6. **`metadata.json` is read only to validate a filter value, never to assemble a result.** Every
   field a result needs (`category`/`doc_type`/`title`) is already denormalized onto every chunk
   record by Stage 7 — re-reading `metadata.json` per result would duplicate that join for no gain
   (the same "arguably redundant" acknowledgment Stage 8 Decision 7 already made). Its one real use:
   if a caller's `category`/`doc_type` filter value never appears in any loaded document's
   `metadata.json`, that's surfaced as a WARNING `FILTER_VALUE_UNKNOWN` finding — catches a typo'd
   filter without ever blocking retrieval. An unknown filter value never causes retrieval to fail on
   its own: the request still proceeds exactly as if the value were valid, and may legitimately end
   in `zero_results=true` if nothing actually matches — `FILTER_VALUE_UNKNOWN` is advisory only, and
   a future implementation must never treat it as a rejection reason.
7. **The manifest is the current source of truth for "is this document still searchable," re-checked
   at query time, not trusted from the index alone.** Reuses Stage 9's own definition verbatim:
   `"vector_index" in record.artifact_paths`. A document quarantined by some later process after
   being indexed is silently excluded from results — its vectors may still physically be in the
   index (no rebuild has pruned them yet), but Stage 10 never surfaces them. This is a deliberate,
   query-time-only check; it never writes back to the manifest (see Manifest).
8. **`index_validation_report.json`'s latest `outcome` is read informationally, never as a
   correctness gate.** Per Stage 9's Atomicity guarantee, the live triad is always internally
   self-consistent regardless of whether the *most recent* rebuild attempt for that fingerprint
   succeeded — a failed rebuild simply means the live index hasn't incorporated recent corpus
   changes yet. If the latest report's `outcome == "FAIL"`, Stage 10 still searches the live index
   (it's safe to do so) but attaches a Recoverable `INDEX_STALE_VALIDATION` finding so the caller
   knows the results may not reflect the newest corpus state.
9. **No `run_stage10()` batch entrypoint.** Every prior stage's `run_stageN()` orchestrates one pass
   over the whole corpus; Stage 10 has no batch analog — it is invoked once per query. `retrieve(request)`
   is the sole public entrypoint.
10. **A chunk indexed under more than one requested `index_fingerprint` is deduplicated by
    `chunk_id`, higher normalized score wins, deterministically.** Prevents the same content
    appearing twice in one multi-index result merely because a caller searched two overlapping
    indexes (e.g. same corpus, two metrics). Deduplication runs *before* sorting and truncation
    (Pipeline [9a]–[9d]) — `rank` is assigned only after dedup and truncation are both already
    final, never before, so there is no window where a duplicate could consume a `top_k` slot that
    should have gone to a distinct chunk.
11. **Query preprocessing is limited to exactly `strip()` + Unicode NFC normalization — frozen,
    permanently.** No lowercasing, stemming, lemmatization, synonym expansion, spell correction, or
    stopword removal, ever. Why: every one of those is a fuzzy/probabilistic text transformation:
    Principle 5 (deterministic before probabilistic) permits a heuristic only when it is a fixed,
    named, documented rule, and none of the excluded techniques can be expressed that way without a
    linguistic resource (a stemmer, a spell-check dictionary, a synonym table) this project doesn't
    otherwise depend on anywhere. Whatever robustness a query needs to phrasing variation is entirely
    the embedding provider's own concern, not Stage 10's.
12. **`index_fingerprints` input normalization is a frozen, explicit policy, not implied behavior.**
    An empty list is a request-level failure (`INDEX_FINGERPRINTS_EMPTY`, `status="FAIL"`, nothing
    else runs) — a caller must always name at least one index. Duplicate entries are silently
    deduplicated, first-appearance order preserved, no finding — passing the same fingerprint twice
    is not an error, just redundant input. An entry with no matching live directory at all —
    `INDEX_NOT_FOUND`, WARNING, ignored — is deliberately distinguished from a matching-but-corrupted
    triad (`INDEX_ARTIFACT_READABLE`, FAIL, excluded): "never built" (a wrong id, or an index not yet
    built) is a common, benign situation; "was built, is now broken" is a genuine problem worth a
    stronger signal. Entries spanning more than one provider/model/backend/metric are never an error
    either — they simply form more than one group at Pipeline [4], each embedded and searched fully
    independently (Design Decision 2).

## Schema

All three are in-memory Python structures — none persisted, no file format to version.

**`RetrievalRequest`**
```jsonc
{
  "query": "climate adaptation financing mechanisms",
  "index_fingerprints": ["a3f9..."],       // required, non-empty, explicit — see Design Decisions #1
  "top_k": 10,                              // 1 <= top_k <= MAX_TOP_K
  "filters": {
    "category": "climate",                 // optional, exact match
    "doc_type": "RRP",                      // optional, exact match
    "doc_ids": null                         // optional explicit allow-list, exact match
  }
}
```

**`RetrievedChunk`**
```jsonc
{
  "rank": 0,                                // 0-indexed, contiguous within one result
  "score": 0.8421,                          // normalized similarity, higher = more relevant
  "index_fingerprint": "a3f9...",           // which index this hit came from
  "embedding_id": "doc_..._2.1.1_0__prov__mod__v1",
  "chunk_id": "doc_..._2.1.1_0",
  "doc_id": "doc_9f3a2b1c8e4d",
  "text": "...",                            // verbatim chunks.json text, no truncation
  "heading_path": ["2. Project Background", "2.1 Climate Rationale"],
  "section_ids": ["2.1.1"],
  "page_start": 34, "page_end": 35,
  "category": "climate", "doc_type": "RRP", "title": "Climate Resilience..."
}
```

**`RetrievalResult`**
```jsonc
{
  "query": "climate adaptation financing mechanisms",   // post-preprocessing
  "retrieval_pipeline_version": "1.0.0",
  "retrieved_at": "2026-07-20T12:00:00Z",
  "status": "PASS",                          // PASS | PARTIAL | FAIL — see Validation
  "zero_results": false,
  "requested_index_fingerprints": ["a3f9..."],
  "searched_index_fingerprints": ["a3f9..."], // subset that actually contributed
  "results": [ /* RetrievedChunk, ..., len <= top_k */ ],
  "findings": [ /* {severity, code, message, index_fingerprint?} */ ]
}
```

## Constants

```python
RETRIEVAL_PIPELINE_VERSION = "1.0.0"
DEFAULT_TOP_K = 10
MAX_TOP_K = 100            # hard ceiling — guards a pathological request, never silently raised
OVERFETCH_MULTIPLIER = 3   # k_search = min(top_k * OVERFETCH_MULTIPLIER, index.ntotal)
L2_SCORE_EPSILON = 1e-8    # guards divide-by-zero in the l2 normalize_score transform
```

## Validation

Two distinct tiers, neither identical to the Validation Severity Tiers convention's
document-quarantine model — Stage 10 has no document to quarantine and no persisted artifact to
mark FAIL/PASS/WARNING against. Instead:

**Request-level findings** — scoped to one `index_fingerprint` (or, for `QUERY_EMPTY`, to the whole
request) and non-fatal to the rest of the request. Recorded in `RetrievalResult.findings[]`:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `QUERY_EMPTY` | FAIL | request | `status="FAIL"`, `results=[]`, no index touched |
| `INDEX_FINGERPRINTS_EMPTY` | FAIL | request | `status="FAIL"`, `results=[]`, no index touched |
| `INDEX_NOT_FOUND` | WARNING | per-index | no live directory ever existed for this fingerprint; ignored, absent from `searched_index_fingerprints` |
| `INDEX_ARTIFACT_READABLE` | FAIL | per-index | live triad exists but fails to deserialize; excluded (mirrors Stage 9's own code) |
| `QUERY_EMBEDDING_FAILED` | FAIL | per-provider-group | every index in that group excluded |
| `EMBEDDING_DIMENSION_MISMATCH` | FAIL | per-index | that index excluded |
| `FILTER_VALUE_UNKNOWN` | WARNING | request | informational only, never excludes or fails anything |
| `INDEX_STALE_VALIDATION` | WARNING | per-index | informational only, index still searched |
| `ZERO_RESULTS` | WARNING | request | attached when `zero_results=true`, not an error |

`status` is computed once, at the end, from this truth table (evaluated top-to-bottom, first
matching row wins):

| Condition | `status` |
|---|---|
| `QUERY_EMPTY` or `INDEX_FINGERPRINTS_EMPTY` fired | `FAIL` |
| `searched_index_fingerprints` is empty (every requested fingerprint ended up ignored or excluded) | `FAIL` |
| At least one fingerprint searched, and at least one requested fingerprint was excluded by a FAIL-severity per-index/per-group finding | `PARTIAL` |
| Every requested (post-dedup) fingerprint was searched successfully | `PASS` |
| `PASS`, and zero candidates survive filtering | `PASS`, with `zero_results=true` |

A WARNING-severity per-index finding (`INDEX_NOT_FOUND`, `INDEX_STALE_VALIDATION`) never by itself
downgrades `status` to `PARTIAL` — an ignored, never-built fingerprint is treated exactly as if the
caller had never requested it; `status` only reflects FAIL-severity exclusions. `zero_results` is
fully orthogonal to `status` and is never conflated with `FAIL` — it can be `true` under either
`PASS` or `PARTIAL`.

**Internal invariant self-check** — `validate_retrieval_result()`, run unconditionally on the
assembled result before it is ever returned, checking properties that must hold by construction and
are never expected to fail under correct operation: no duplicate `chunk_id`; `score` non-increasing
across `rank` order; `rank` values exactly `0..len(results)-1`; every result's `index_fingerprint` is
a member of `searched_index_fingerprints`; `len(results) <= MAX_TOP_K`. Any violation raises
`RetrievalInternalError` rather than being returned as a malformed `RetrievalResult` — there is no
quarantine mechanism to route a genuine Stage 10 bug around, so this fails loud instead of degrading
gracefully, unlike every document-level Critical finding in Stages 6–9.

Retrieval and validation responsibilities are deliberately separate. `retrieve()` alone guarantees
`results` has already been truncated to the request's own `top_k` (Pipeline [9c], strictly before
`validate_retrieval_result()` is ever called) — `top_k` belongs to `RetrievalRequest`, not
`RetrievalResult`, so it is intentionally unavailable to the validator. The validator validates only
properties expressible from the `RetrievalResult` itself; request-specific constraints (such as the
caller's `top_k`) are guaranteed earlier by `retrieve()` and are therefore outside the validator's
scope. Its own invariant check is instead the global `MAX_TOP_K` ceiling: a result that exceeds the
pipeline's own hard ceiling is unambiguous evidence of a genuine internal bug, which is the exact
class of failure this self-check exists to catch.

## Failure Handling

- **An empty `index_fingerprints` list** — `INDEX_FINGERPRINTS_EMPTY`, `status="FAIL"` immediately;
  no index is touched, no embedding call is made.
- **A duplicate fingerprint in `index_fingerprints`** — not a failure; silently deduplicated,
  first-appearance order preserved, no finding.
- **A requested fingerprint with no live directory at all** — `INDEX_NOT_FOUND`, WARNING, ignored;
  every other requested fingerprint proceeds unaffected. Treated as if the caller had simply never
  requested it — never contributes to `status="PARTIAL"` on its own.
- **A requested fingerprint whose live triad exists but fails to deserialize** —
  `INDEX_ARTIFACT_READABLE`, FAIL, that index excluded, every other requested index proceeds
  unaffected (mirrors Stage 9's per-fingerprint isolation, applied here per-index within one
  request).
- **A request naming fingerprints under more than one provider/model/backend/metric** — not a
  failure; each distinct group is embedded and searched independently (Pipeline [4]).
- **The query embedding provider is unavailable or errors** — `QUERY_EMBEDDING_FAILED`, FAIL, every
  index needing that provider config is excluded; indexes under a different, working provider config
  still proceed.
- **Every requested index ends up ignored or excluded** — `status="FAIL"`, `results=[]`; the caller
  can inspect `findings[]` to see exactly which per-index reason(s) caused it.
- **A filter value that matches nothing in any loaded document's `metadata.json`** —
  `FILTER_VALUE_UNKNOWN`, WARNING, advisory only; the request proceeds exactly as normal and may
  legitimately end in `zero_results=true`. Never a rejection reason.
- **Zero candidates survive filtering** — not a failure. `status="PASS"` (or `"PARTIAL"` if some
  other index was independently excluded), `zero_results=true`, `results=[]`, one `ZERO_RESULTS`
  WARNING finding.
- **An empty query string (post-`strip()`)** — `QUERY_EMPTY`, `status="FAIL"` immediately; no index
  is touched, no embedding call is made.
- **A genuine Stage 10 bug (invariant violation)** — `RetrievalInternalError` raised, not returned as
  a result; the only case where Stage 10 raises rather than returning a structured outcome.

## Manifest

Stage 10 is the pipeline's first fully **read-only** stage with respect to `manifest.json` — it never
calls `save_manifest`, never sets `artifact_paths`, `status`, `error_code`, or `completed_at` on any
record. It reads the manifest exactly twice per query: once to resolve `doc_id → artifact_paths`
for each candidate's `chunks` path (Result Assembly), and once to re-check `"vector_index" in
artifact_paths` / `status != QUARANTINED` per candidate (Design Decision 7). No `DocumentStatus`
value is ever written; no new lifecycle concept is introduced. "Is this document currently
searchable" is decided fresh, at query time, from whatever the manifest says right now — a document
quarantined by any process after Stage 9 last ran is transparently excluded without Stage 9 ever
needing to rebuild.

## Artifact Interaction

Reads only, from a fixed, caller-uncontrolled set of roots — `manifest.json`'s own `artifact_paths`
values and the fixed `vector_index/` directory Stage 9 already owns. Never writes to
`embeddings.parquet`, `chunks.json`, `metadata.json`, `manifest.json`, or anything under
`vector_index/<fingerprint>/`. No atomicity concern exists because there is nothing to persist — the
question Stage 9's Atomicity section answers ("how do we swap a triad safely") has no Stage 10
analog.

## Directory Structure

None added. Stage 10 is the first stage in this pipeline that introduces no new artifact directory —
it is a pure read path over `data/proposals/{chunks,embeddings,vector_index}/`, already owned by
Stages 7–9.

## Logging

Per the shared Logging Specification (`stage: "stage10_retrieval"`, `doc_id: null` always — entries
are query-scoped, not document-scoped). New codes this stage adds: `WARNING_INDEX_STALE_VALIDATION`,
`WARNING_FILTER_VALUE_UNKNOWN`, `WARNING_ZERO_RESULTS`. No new `FATAL_*` code — Stage 10 never sets a
manifest `error_code`, since it never writes to the manifest at all (see Manifest).

## Configuration

Runtime-supplied, never hard-coded, mirroring Stage 8/9's own `adapter_factory` convention:
`provider_adapter_factory` (resolved per distinct provider/model/version group needed to embed the
query) and `index_adapter_factory` (resolved per `index_fingerprint`'s own recorded `backend_name`
in its `index_metadata.json`) — a caller supplies factories, not concrete backend choices; Stage 10
never imports a specific provider or ANN library by name in its orchestration path. `top_k`,
`filters`, and `index_fingerprints` are per-request configuration, never defaulted from any global or
environment state.

## Concurrency

Fully safe under concurrent calls. Because Stage 10 performs zero writes, any number of `retrieve()`
calls — including against the same `index_fingerprint` — may run simultaneously with no locking, no
shared mutable state, and no race condition; each call deserializes its own in-memory `IndexAdapter`
instance from the on-disk triad. This is a direct consequence of Manifest and Artifact Interaction
above (read-only), not a separate mechanism.

## Security Considerations

- Query text is opaque data — never interpolated into a file path, shell command, or `eval`. Any
  network call the query embedding requires is entirely the provider adapter's own concern (Stage
  8's contract), outside Stage 10's control surface.
- `filters.doc_ids`/`category`/`doc_type` are compared by exact string equality only — never used to
  construct a dynamic file path; every artifact path Stage 10 opens is resolved exclusively through
  `manifest.json`'s own `artifact_paths` or the fixed `vector_index/` root, never by
  string-concatenating caller input into a path.
- No write capability anywhere in this design — eliminates an entire class of injection/corruption
  risk by construction, not by runtime validation.

## Functions / Contracts

- `preprocess_query(raw_query: str) -> str` — deterministic `strip()` + Unicode NFC normalization; no
  stemming, no stopword removal, no query expansion (Principle 5 — deterministic before
  probabilistic).
- `list_available_indexes(manifest) -> List[IndexSummary]` — read-only discovery helper; enumerates
  every live `vector_index/<fingerprint>/index_metadata.json`, no adapter instantiation required.
- `resolve_index_fingerprints(requested, manifest) -> List[IndexHandle]` — validates each requested
  fingerprint's live triad exists and is readable; loads its `index_metadata.json`.
- `embed_query(query, provider_adapter) -> np.ndarray` — wraps `provider_adapter.embed_batch([query])[0]`;
  dimension-validated by the caller against the target index's declared `embedding_dimension`.
- `search_index(index_handle, query_vector, k, index_adapter_factory) -> List[Candidate]` —
  deserializes the `IndexAdapter` via the caller-supplied `index_adapter_factory` (the same
  runtime-configuration convention as `provider_adapter_factory`, see Configuration), calls
  `adapter.search()`, maps `adapter_internal_id → id_map` row. `index_adapter_factory` exists solely
  to preserve backend independence and testability, matching Stage 9's own `adapter_factory`
  convention — it must never be used to introduce backend-specific branching inside `search_index`
  itself.
- `normalize_score(raw_distance, metric) -> float` — the fixed per-metric transform (Design Decision
  3).
- `apply_metadata_filters(candidates, filters, chunks_by_doc) -> List[Candidate]` — pure filter,
  order-preserving.
- `normalize_index_fingerprints(requested: List[str]) -> List[str]` — deduplicates, first-appearance
  order preserved; raises/flags `INDEX_FINGERPRINTS_EMPTY` if the input list is empty.
- `assemble_results(candidates, chunks_by_doc, index_fingerprint) -> List[RetrievedChunk]` — joins
  each candidate to its full `chunks.json` record; `text` copied verbatim, byte-for-byte — never
  truncated, modified, normalized, or highlighted.
- `select_top_k(all_candidates, top_k) -> List[RetrievedChunk]` — cross-index dedup by `chunk_id`
  (highest score wins) *first*, then deterministic sort, tie-break, truncate, and only then
  contiguous rank assignment (Design Decision 10).
- `validate_retrieval_result(result) -> None` — internal invariant self-check; raises
  `RetrievalInternalError` on violation.
- `retrieve(request: RetrievalRequest) -> RetrievalResult` — the sole public entrypoint;
  orchestrates Pipeline [1]–[9]; never writes to the manifest or any artifact.

## Known Limitations

- Fixed `OVERFETCH_MULTIPLIER` can under-fill `top_k` after an aggressive filter (e.g. a narrow
  `doc_ids` allow-list matching few chunks) — Stage 10 returns fewer than `top_k` rather than padding
  or iteratively widening the search.
- Cross-index score comparison in a multi-index request is only strictly fair within one metric
  family — mixing a `cosine` and an `l2` index produces an internally consistent but not
  mathematically calibrated combined ranking.
- No relevance-quality signal is computed or asserted — Stage 10 proves structural correctness of
  ranking (determinism, no duplicates) only, never semantic relevance; that question belongs to a
  future, separate evaluation stage (the same limitation Stage 9's self-query check already
  accepted).
- `FILTER_VALUE_UNKNOWN` can only see `metadata.json` for documents that actually surfaced as
  candidates in one query — a filter value valid corpus-wide but absent from that query's specific
  candidates is indistinguishable from a genuinely invalid one; Recoverable-only, by design.
- Query embedding determinism inherits Stage 8's own accepted limitation (Self-Critique #3): a
  hosted-API provider's determinism at a fixed `model_version` is assumed, not independently
  verified here.
- One query touching several `index_fingerprints` issues one `embed_batch` call per distinct
  provider/model/version group, not one global batch — fine for one query at a time; a future
  batch-query surface would need its own batching design.

## Accepted Tradeoffs

- **No persisted output artifact, no manifest writes at all.** The first fully read-only stage in
  the pipeline — simplifies reasoning about side effects at the cost of breaking the otherwise-
  universal "every stage updates the manifest" pattern.
- **Explicit `index_fingerprints` required, never auto-discovered.** More caller burden (must call
  `list_available_indexes()` first, or already know the fingerprint) in exchange for eliminating a
  whole class of "silently searched the wrong index" surprises.
- **Metadata filtering happens after vector search, never pushed into the backend.** Simplest
  correct behavior at this corpus's scale; a future large-corpus need for pre-filtered ANN search
  would require extending the `IndexAdapter` contract itself, not redesigning Stage 10 alone.
- **Fixed overfetch-then-filter, not an adaptive/iterative widening loop.** Bounded, predictable cost
  per query; accepts occasionally returning fewer than `top_k` results over guaranteeing exactly
  `top_k` whenever theoretically possible.
- **Filters are AND-only, equality-only, three fixed fields.** No boolean query language — a
  reasonable v1 scope matching the "deterministic before probabilistic" principle; extending the
  filter language is a bounded future change, not a redesign.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not
this document.

- Query preprocessing rejects an empty (post-`strip()`) query deterministically, every time, without
  touching any index or issuing any embedding call.
- Index resolution never searches a fingerprint outside the caller's own `index_fingerprints` list;
  an unresolvable fingerprint contributes zero results and one `INDEX_NOT_FOUND` finding scoped to
  it, without blocking any other requested fingerprint.
- Query embedding dimension is validated against each target index's own recorded
  `embedding_dimension` before any `search()` call; a mismatch excludes only that index.
- Result ordering is strictly normalized-score descending, ties broken by ascending `chunk_id`,
  reproducibly across repeated identical requests.
- `len(results) <= top_k` always; `rank` values are exactly `0..len(results)-1`, contiguous.
- No duplicate `chunk_id` ever appears twice in one result, even when indexed under two distinct
  fingerprints in one multi-index request — higher score wins, deterministically.
- A zero-candidate outcome produces `status="PASS"` (or `"PARTIAL"`), `zero_results=true`,
  `results=[]` — never conflated with `status="FAIL"`.
- Determinism: identical `(query, index_fingerprints, filters, top_k)` against an unchanged live
  index and unchanged provider config produces a byte-identical `RetrievalResult` (`retrieved_at`
  excluded), across repeated calls and process restarts.
- Immutability: `manifest.json`, every `chunks.json`, `metadata.json`, and every file under
  `vector_index/<fingerprint>/` are byte-identical on disk before and after any `retrieve()` call.

## Real Corpus Verification

Against the real, current corpus (Stage 9's live `vector_index/` output — one `index_fingerprint` at
341 vectors, per the real `index_metadata.json`): `list_available_indexes()` surfaces exactly that
one fingerprint; a representative real query against it returns `len(results) <= top_k` real chunks,
each resolvable back to a real `doc_id`/`chunk_id` present in that document's own `chunks.json`; a
`category` filter matching a known real document's `category` returns only chunks from documents
carrying that value, spot-checked by eye; every returned chunk's `text` is confirmed byte-identical
to that same `chunk_id`'s `text` field in its own document's `chunks.json` — no truncation, no
modification, no normalization, no highlighting, exactly as stored; two identical repeated real
queries produce a byte-identical `RetrievalResult.results` (timestamp excluded); every upstream
artifact (`manifest.json`, every `chunks.json`, `embeddings.parquet`, `metadata.json`, everything
under `vector_index/`) is confirmed byte-identical before and after the run.

## Future Stage Boundaries

Stage 11+ (not designed here) owns everything Stage 10 deliberately excludes: answer generation, LLM
prompting/orchestration, citation formatting, reranking with an LLM or cross-encoder, hybrid BM25/
sparse/keyword retrieval, Reciprocal Rank Fusion or any other multi-signal fusion technique,
retrieval-quality evaluation, feedback loops, result caching, conversation memory, and any
network-facing API or UI. Stage 10's own ranking is exclusively dense-vector similarity search over
already-built Stage 9 indexes, exactly as defined in Design Decisions — no keyword/sparse signal is
computed or blended in, now or implicitly left open for a future patch; introducing one is a new
stage's job, not an extension of this one. Stage 10 hands a `RetrievalResult` back in memory; how a
caller persists, caches, serves, or builds on top of it is entirely out of this design's scope.
