# Stage 17 — Response Caching

Stages 0–16 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 17 wraps Stage 13's own frozen `execute_prompt()` with a deterministic cache lookup: given a
`PromptPackage` and an `LLMExecutionConfig`, it computes a deterministic `cache_key` identifying that
exact request, checks a caller-supplied `CacheAdapter` for a previously-stored `LLMResponse` under that
key, and either returns the cached response unmodified (a hit) or calls Stage 13's own `execute_prompt()`
exactly once, stores the result if it is cache-worthy, and returns it (a miss). It performs no
generation of its own, no re-validation of a cached response's own content, and no decision about
whether a cached response is still *correct* — only whether an identical request has already been
answered and, if so, whether that answer is still fresh enough to reuse.
`execute_with_cache(prompt_package, llm_adapter, cache_adapter, execution_config)` is the sole public
entrypoint.

Stage 17 is the first stage in this pipeline's query-time path (Stage 10 onward) to own and mutate a
persisted artifact — the cache store itself, via the `CacheAdapter` contract — rather than being fully
read-only and zero-artifact like Stage 10 through Stage 16 each were (see Read-Only Guarantees, Design
Decisions #2).

## Scope

Stage 17 answers exactly one question — has an identical request already produced a cache-worthy
`LLMResponse`, and if so, is it still fresh enough to return instead of invoking the model again — and
stops there. It never regenerates a response itself; never evaluates, validates, or scores an answer's
quality or groundedness; never extracts or reformats a citation; never changes a prompt or alters
retrieval; never decides *whether* a request should have been made at all (that determination already
happened upstream, at Stage 11/12); never invokes an LLM directly (it only ever delegates to Stage 13's
own frozen `execute_prompt()` on a miss); never modifies a cached entry once stored (an entry is
replaced wholesale on a fresh write, never patched in place); never serves a network-facing API. Those
boundaries are restated in Non-Responsibilities and Future Stage Boundaries.

## Responsibilities

Stage 17 shall: receive a `PromptPackage`, an `LLMAdapter`, a `CacheAdapter`, and an optional
`LLMExecutionConfig`; structurally validate the `PromptPackage` and resolve the execution config before
use; compute a deterministic `cache_key` identifying the exact request; look up that key in the
`CacheAdapter`; on a hit that is still fresh, return the cached `LLMResponse` unmodified; on a miss, or
an expired hit, invoke Stage 13's own unmodified `execute_prompt()` exactly once, store the result if
its `status` is cache-worthy, and return it; degrade gracefully to a forced miss if the `CacheAdapter`
itself fails; and assemble a `CachedExecutionResult` whose own internal invariants are self-checked
before it is ever returned.

## Non-Responsibilities

Stage 17 explicitly does **not** perform, and no future patch to this stage may silently add without a
new design pass: modifying a cached `LLMResponse` in any way, at read time or write time (an entry is
stored exactly as Stage 13 returned it, and returned exactly as stored — see Design Decisions #6);
regenerating a response by any means other than delegating to Stage 13's own unmodified
`execute_prompt()`; evaluating answer quality (Stage 16's frozen job) or groundedness (Stage 15's
frozen job) of a cached or freshly-generated response; extracting or reformatting a citation (Stage
14's frozen job); constructing a prompt or assembling context (Stage 11/12's frozen jobs); performing
retrieval, embedding, or reranking of any kind; semantic similarity or fuzzy matching of *any* two
requests — two requests either produce the identical deterministic `cache_key` or they are treated as
completely unrelated, never "close enough" (Principle 5); choosing or implementing a concrete cache
storage backend (Cache Storage Abstraction); serving a network-facing API or streaming a response to a
caller; conversation memory or multi-turn orchestration; tool or function calling; agent planning.
Every one of these remains reserved for a later, separate design, or is permanently out of this
pipeline's scope under Principle 5 (Future Stage Boundaries).

## Inputs

Three required inputs, and one optional one — the minimum needed to decide a hit/miss and, on a miss,
to delegate correctly to Stage 13:

- `PromptPackage` (Stage 12's own output schema, unchanged) — the sole source of `prompt_package_id`
  (the request-identity anchor for `cache_key`) and `status` (needed to pass through unmodified to
  Stage 13 on a miss; Stage 17 performs no independent judgment of it). Required because a cache key
  cannot be computed, and Stage 13 cannot be invoked on a miss, without it.
- `LLMAdapter` (Stage 13's own frozen contract) — required only for the miss path, where it is passed
  through to Stage 13's own `execute_prompt()` completely unmodified; Stage 17 never calls
  `adapter.invoke()` directly itself (Design Decisions #1).
- `CacheAdapter` (this stage's own new contract, see Cache Storage Abstraction) — required for both the
  lookup and the (conditional) write; without it there is nothing for Stage 17 to actually do beyond
  what Stage 13 already does alone.
- `LLMExecutionConfig` (Stage 13's own schema, unchanged), optional — resolved via Stage 17's own
  private copy of Stage 13's defaulting/clamping logic (Design Decisions #7) before the cache key is
  computed, since the resolved (not raw) config is what determines both the request Stage 13 would
  send and the cache key identifying it.

No other input is read. `ContextPackage`, `RetrievalResult`, `manifest.json`, `chunks.json`,
`metadata.json`, vector indexes, and embeddings are never opened — every field Stage 17 needs already
exists on `PromptPackage`, exactly as Stage 13 itself already established one stage downstream of them.

## Outputs

`CachedExecutionResult` (see Cache Entry Schema and Cache Metadata) is Stage 17's sole in-memory return
value — never persisted by Stage 17 itself as a distinct artifact. The genuinely new, persisted state
this stage introduces is the cache store's own entries, written via the caller-supplied `CacheAdapter`
— an artifact Stage 17 owns (Read-Only Guarantees), but whose format, location, and backend are
entirely undefined by this architecture (Cache Storage Abstraction), unlike every `data/proposals/`
artifact any earlier stage owns.

## Pipeline Ordering

Stage 17's own **design sequence number** (17, per the Stage 14 Roadmap Definition Pass) does not
match its **runtime invocation position**. In actual execution order, Stage 17 sits between Stage 12
(prompt construction) and Stage 13 (LLM execution) — its own entrypoint decides whether Stage 13 is
invoked at all for a given request:

```
Stage 11 (Context Assembly) → Stage 12 (Prompt Construction) → PromptPackage
                                                                      │
                                                                      ▼
                                              Stage 17 — execute_with_cache(prompt_package,
                                                          llm_adapter, cache_adapter, execution_config)
                                                                      │
                                          compute cache_key (Cache Key Construction)
                                                                      │
                                                    cache_adapter.get(cache_key)
                                                                      │
                                    ┌─────────────── hit, fresh ──────┴────── miss / hit, expired ───────┐
                                    ▼                                                                     ▼
                    return cached LLMResponse                                     Stage 13 — execute_prompt(prompt_package,
                    unmodified (Cache Hit Behavior)                                          llm_adapter, execution_config)
                                    │                                                                     │
                                    │                                          status in CACHEABLE_STATUSES?
                                    │                                              ├─yes─▶ cache_adapter.put(cache_key, entry)
                                    │                                              └─no──▶ no write (Cache Miss Behavior)
                                    │                                                                     │
                                    └─────────────────────────┬───────────────────────────────────────────┘
                                                                ▼
                                                build_cached_execution_result()
                                                                │
                                                validate_cached_execution_result()
                                                                │
                                                                ▼
                                                       CachedExecutionResult
                                                                │
                                                                ▼
                                              Stage 14 (Citation Extraction) reads result.llm_response
```

Stage 14 through Stage 16 (already designed) continue to consume an `LLMResponse` exactly as before —
they are unaffected by, and unaware of, whether that `LLMResponse` came from a cache hit or a fresh
Stage 13 call; `CachedExecutionResult.llm_response` is byte-for-byte the same `LLMResponse` schema Stage
13 already produces. No change to Stage 14/15/16's own frozen inputs is implied or required by this
design (Frozen Pipeline Boundary, restated in Design Decisions #6).

## Cache Storage Abstraction

Stage 17 defines a small, closed `CacheAdapter` contract, mirroring the `ProviderAdapter` (Stage 8) /
`IndexAdapter` (Stage 9) / `LLMAdapter` (Stage 13) pattern exactly — no orchestration function in this
stage's own Pipeline ever branches on which concrete backend is in use, and no concrete backend is
chosen or implied by this design (unlike Stage 9's own eventual choice of FAISS):

- `backend_name` (str) — informational only, e.g. `"in_memory"`, `"redis"`, `"sqlite"`; never branched
  on by Stage 17's own orchestration.
- `get(cache_key: str) -> Optional[CacheEntry]` — returns the stored entry for `cache_key`, or `None`
  if absent. Must not raise for a simple "not found" outcome — only for a genuine backend failure
  (connection error, corrupted read), which Stage 17 treats as a forced miss (Failure Handling).
- `put(cache_key: str, entry: CacheEntry) -> None` — stores `entry` under `cache_key`, replacing any
  existing entry under that key wholesale (never a partial/merged update — Idempotent, per
  `pipeline_principles.md` §1.4). A `put` failure is likewise treated as non-fatal (Failure Handling):
  the already-computed `LLMResponse` is still returned to the caller even if it could not be cached.
- `get_statistics() -> CacheStatistics` — optional in effect (an adapter may always return zeros); Stage
  17 itself never maintains its own call-scoped hit/miss counters, since meaningful statistics span
  many calls and therefore belong to the adapter's own persisted state, never to one
  `execute_with_cache()` invocation's own local memory.

No adapter method is ever assumed to provide atomicity, transactional isolation, or its own expiration
policy — freshness (Cache Validation) and cache-worthiness (Cache Miss Behavior) are decided entirely
by Stage 17's own orchestration, never delegated to the adapter. A future concrete `CacheAdapter`
implementation (in-memory dict, local file, Redis, or any other store) satisfies this contract without
requiring any change to `execute_with_cache()`, `compute_cache_key()`, or any other Stage 17 function —
the same backend-independence guarantee Stage 9's `IndexAdapter` and Stage 13's `LLMAdapter` each
already provide one layer down.

## Cache Entry Schema

`CacheEntry` — what a `CacheAdapter` actually stores and returns; an in-memory structure whose
persisted form (if any) is entirely the adapter's own concern:

```jsonc
{
  "cache_key": "...",                  // the exact key this entry is stored under — duplicated onto
                                        // the entry itself so a retrieved entry is self-describing and
                                        // independently checkable (Validation §3, CACHE_KEY_SELF_MISMATCH)
  "llm_response": { /* Stage 13's own LLMResponse, byte-for-byte, never modified in any way */ },
  "prompt_package_id": "...",          // copied verbatim from the PromptPackage that produced this
                                        // entry — informational/debugging only, never re-derived from
                                        // or compared against llm_response.prompt_package_id at read
                                        // time beyond the existing PROMPT_PACKAGE_ID_MISMATCH check
  "model_name": "...",                 // copied verbatim from the resolved LLMExecutionConfig —
                                        // informational only
  "cached_at": "2026-07-21T12:00:00Z"  // when this entry was first written; excluded from every
                                        // determinism comparison; never updated on a subsequent hit
                                        // (a hit never re-writes the entry — Cache Hit Behavior)
}
```

**What is stored — exhaustively, the five fields above and nothing else.** `cache_key`, the verbatim
`llm_response`, `prompt_package_id`, `model_name`, `cached_at`. No other field is ever written into a
`CacheEntry` by any Stage 17 function.

**What is not stored — stated explicitly so the payload is never ambiguous.** The full `PromptPackage`
object (only its `prompt_package_id` is kept, for debugging/traceability — never `system_prompt`,
`user_prompt`, `context_text`, or `assembled_prompt`); the full `LLMExecutionConfig` object (only
`model_name` is kept — never `temperature`, `max_output_tokens`, `timeout_seconds`, or
`max_retry_attempts`, since all of those already participate in `cache_key` itself and restating them
on the entry would be exactly the "unnecessary duplication of upstream payloads" every prior stage's
own Outputs discipline already warns against); any `ContextPackage`, `RetrievalResult`, or corpus
artifact (Stage 17 never reads any of these — Inputs); any hit/miss statistics, access count, or
last-accessed timestamp (Cache Storage Abstraction's `get_statistics()` is the adapter's own
responsibility, never folded into the entry itself — Design Decisions #2, Cache Storage Abstraction);
any `response_caching_pipeline_version` or schema-version marker (Cache Key Construction's own
Versioning strategy deliberately keeps `cache_key` version-field-free, and a `CacheEntry` correctness
concern is handled the identical way — a formula change is a new architecture revision, never an
in-band field).

## Cache Metadata

`CachedExecutionResult` — Stage 17's sole return value, wrapping Stage 13's own frozen `LLMResponse`
verbatim plus this stage's own cache-specific metadata; an in-memory structure, never persisted by
Stage 17 itself:

```jsonc
{
  "response_caching_pipeline_version": "1.0.0",
  "resolved_at": "2026-07-21T12:00:05Z",  // when Stage 17 itself resolved this call (hit or miss);
                                          // excluded from every determinism comparison
  "cache_key": "...",                    // this request's own deterministic identity — see Cache Key
                                          // Construction; always equals llm_response.llm_response_id
                                          // (Design Decisions #4, CACHED_LLM_RESPONSE_ID_MISMATCH)
  "cache_hit": true,                     // false on a miss OR an expired hit (Cache Validation)
  "status": "PASS",                      // copied verbatim from llm_response.status — never
                                          // independently computed (Design Decisions #9)
  "cached_at": "2026-07-20T09:00:00Z",   // on a hit: the entry's own original cached_at, unchanged;
                                          // on a miss: set fresh, equal to this entry's new cached_at
  "cache_backend_name": "...",           // copied from CacheAdapter.backend_name — informational only
  "llm_response": { /* Stage 13's own LLMResponse, byte-for-byte, exactly as stored or exactly as
                        Stage 13 itself just returned — never modified in any way (Design Decisions #6) */ },
  "findings": [ /* this stage's own findings: {severity, code, message} */ ]
}
```

No separate `cached_execution_result_id` field is introduced: `llm_response.llm_response_id` already
serves as this result's own identity anchor, and — by Design Decisions #4 — is always identical to
`cache_key` for a cacheable response, making a third, redundant id field unnecessary (mirrors Stage
11's own Design Decision #9, which rejected a redundant `block_index` alongside `rank` for the
identical reason: two fields that would always mean the same thing invite drift, not clarity).

## Cache Key Construction

`compute_cache_key(prompt_package_id, model_name, resolved_execution_config)` uses the **identical
formula** to Stage 13's own `llm_response_id` hash (Stage 13's Design Decisions #6), computed by Stage
17's own private copy — never importing Stage 13's internal hash helper (each-stage-owns-its-own-copy,
per Stage 11 through Stage 16's own established convention):

```python
hash_input = {
    "prompt_package_id": prompt_package["prompt_package_id"],
    "model_name": resolved_execution_config["model_name"],
    "execution_config": {
        "temperature": resolved_execution_config.get("temperature"),
        "max_output_tokens": resolved_execution_config["max_output_tokens"],  # already resolved/clamped
    }
}
cache_key = sha256(canonical_json(hash_input)).hexdigest()
```

**Fields that participate.** Exactly `prompt_package_id`, `model_name`, `temperature`, and the
*resolved* `max_output_tokens` — nothing else. `timeout_seconds` and `max_retry_attempts` never
participate: neither affects what the model actually generates, only how the request is retried on a
transient failure (mirrors Stage 13's own identical exclusion of these two fields from its own
`llm_response_id` hash, for the identical reason).

**Canonical serialization.** `canonical_json` — the same deterministic, key-sorted JSON serialization
convention every prior stage's own identity hash already uses (Stage 9's `index_fingerprint`, Stage
11's `context_package_id`, Stage 12's `prompt_package_id`, Stage 13's `llm_response_id`).

**Hashing algorithm.** sha256, hex-encoded — the same algorithm every prior stage's own identity hash
already uses; no new hash algorithm is introduced anywhere in this design.

**Ordering guarantees.** `canonical_json`'s own key-sorting guarantees the hash is independent of
dict/kwarg construction order — the same guarantee every prior stage's own identity hash already
relies on; `compute_cache_key` never depends on any iteration order of its own.

**Treatment of optional fields.** `resolved_execution_config` is always the fully **resolved** config
(post-defaulting, post-clamping) — never the caller's raw, possibly-partial input. This guarantees two
callers who each omit `temperature`/`max_output_tokens` entirely, and two callers who each explicitly
pass the *default* value, all four hash identically — omission and explicit-default are indistinguishable
requests, and must produce the identical `cache_key` (Design Decisions #7).

**Versioning strategy.** No in-band schema-version field is embedded in the hash — keeping `cache_key`
identical to Stage 13's own `llm_response_id`, exactly, always, by construction (Design Decisions #4).
Should this formula itself ever need to change, that is a new architecture revision to this stage's own
document, exactly like any other frozen stage's amendment policy (Frozen Pipeline Boundary) — cache
invalidation across such a revision is an explicit deployment concern (flushing or namespacing the
store), never something the key formula itself needs to encode.

**How cache validity is tied to model identity, execution configuration, prompt construction, and
architecture version — stated explicitly, one at a time:**
- **Model identity** — `model_name` participates in `cache_key` directly (Cache Key Construction);
  requesting a different model always produces a different key. `model_version` (Stage 13's own
  provider-reported field on `LLMResponse`, when available) is never part of the key, mirroring Stage
  13's own identical exclusion — a provider-reported version is informational metadata on the response,
  not a caller-selectable request parameter, the same reasoning Stage 13's own `llm_response_id` hash
  already applied.
- **Execution configuration** — `temperature` and resolved `max_output_tokens` participate directly;
  `timeout_seconds`/`max_retry_attempts` never do (both stated already, above). No separate version
  field is needed for execution config, since every field that affects generated content is already
  hashed directly.
- **Prompt construction** — never re-hashed by Stage 17 at all. `prompt_package_id` alone stands in for
  the *entire* upstream chain that produced it — Stage 12's own template rendering, Stage 11's context
  assembly, Stage 10's retrieval, all the way back to the corpus itself — because Stage 12's own
  `prompt_package_id` is already a deterministic hash over its own identity-determining inputs (Stage
  12's Design Decisions #6). A change to the prompt template, the retrieved context, or the underlying
  corpus necessarily produces a different `context_package_id` and therefore a different
  `prompt_package_id`, which necessarily produces a different `cache_key` — cache validity with respect
  to prompt construction is naturally incorporated through this existing id chain, never requiring an
  explicit version field of Stage 17's own.
- **Architecture version** — `RESPONSE_CACHING_PIPELINE_VERSION` (Constants) exists and is recorded on
  `CachedExecutionResult`, but is deliberately **not** a hash input and is **not** stored on `CacheEntry`
  (Cache Entry Schema's own "what is not stored" list) — it describes this stage's own document version,
  never a property of the cached request itself, and a bump to it never invalidates an existing entry by
  itself. Should `RESPONSE_CACHING_PIPELINE_VERSION` ever need to change in a way that *does* require
  invalidating existing entries (e.g. the cache key formula itself changes), that is handled exactly as
  the paragraph above already states: an explicit deployment-level flush or namespace change, never an
  in-band field on the key or the entry.

**Deterministic behavior — the same logical request always produces the same cache key; different
logical requests never collide except by cryptographic hash collision.** A direct, provable consequence
of the formula above being a pure function of exactly `prompt_package_id`, `model_name`, `temperature`,
and resolved `max_output_tokens` — the same guarantee Stage 13's own `llm_response_id` already provides
one layer down, inherited here unchanged.

**Unambiguous by construction — stated without qualification.** The formula above is not merely "the
same idea" as Stage 13's own hash; it is defined by reproducing Stage 13's exact `hash_input` shape and
canonical serialization algorithm verbatim (Stage 13's Design Decisions #6), applied by Stage 17's own
private copy of that same procedure. There is exactly one way to compute `cache_key` from a given
`(prompt_package_id, model_name, resolved_execution_config)` triple — the code block above, nothing
else — so two byte-identical request definitions always produce byte-identical `cache_key` values, and
no second, looser paraphrase of the formula exists anywhere else in this document.

## Cache Lookup Strategy

`lookup_cache(cache_adapter, cache_key, cache_ttl_seconds)`:
1. Call `cache_adapter.get(cache_key)`. A backend failure (the adapter raises) is caught and treated as
   `None` — a forced miss (Failure Handling) — never propagated as an exception out of Stage 17's own
   entrypoint.
2. If `None`, return `(hit=False, entry=None)` — proceed to Cache Miss Behavior.
3. If an entry is returned, structurally validate it (Cache Validation) and check freshness against
   `cache_ttl_seconds` (Cache Validation). A structurally invalid or expired entry is treated exactly
   like `None` — `(hit=False, entry=None)` — never returned to the caller, and never a fatal error.
4. Otherwise, return `(hit=True, entry=entry)`.

Lookup never mutates the store — a `get()` call alone never triggers a `put()`, even when the retrieved
entry turns out to be expired or invalid; the eventual re-write (if any) only happens through the
ordinary Cache Miss Behavior path that follows.

## Cache Hit Behavior

On a fresh (non-expired, structurally valid) hit: `llm_response` is the entry's own stored
`LLMResponse`, returned completely unmodified — no field is recomputed, re-validated against Stage 13's
own internal invariants, or altered in any way. `cached_at` on the result equals the entry's own
original `cached_at`, never updated to "now" — a hit never re-writes the store (idempotent read, no
side effect). `cache_hit = True`. `findings` may include `CACHE_HIT` (informational — see Validation).
Ordering: since a hit never calls Stage 13 at all, `attempt_count`, `latency_ms`, and every other Stage
13-internal field on the wrapped `LLMResponse` still reflect whatever they were at the moment that
response was *originally* generated on some earlier miss — never Stage 17's own current lookup latency
(Known Limitations).

## Cache Miss Behavior

On a miss (`cache_adapter.get()` returned `None`, or the entry was expired/invalid):
1. Call Stage 13's own unmodified `execute_prompt(prompt_package, llm_adapter, resolved_execution_config)`
   — exactly once, with no retry logic of Stage 17's own beyond whatever Stage 13's own Retry Policy
   already performs internally.
2. `is_cacheable_status(llm_response["status"])` — `True` iff `status in CACHEABLE_STATUSES`
   (`{"PASS", "PARTIAL"}`, Constants). `SKIPPED` and `FAIL` are never cache-worthy (Design Decisions
   #3).
3. If cacheable: build a `CacheEntry` (`cache_key`, `llm_response` verbatim, `prompt_package_id`,
   `model_name`, `cached_at = now`) and call `cache_adapter.put(cache_key, entry)`. A `put` failure is
   caught and recorded as a `CACHE_WRITE_FAILED` WARNING finding — the already-computed `llm_response`
   is still returned to the caller regardless (Failure Handling); the request was never blocked on
   caching succeeding.
4. If not cacheable: no write is attempted at all; a `CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS`
   WARNING finding is recorded instead.
5. Build the `CachedExecutionResult` with `cache_hit = False`, `cached_at = now` (a fresh entry, or the
   moment of a skipped write), and the just-produced `llm_response`.

Insertion policy is always whole-entry replacement, never a partial or merged update — matching
`pipeline_principles.md` §1.4 (Idempotent): a rerun of an identical request that happens to land on
another miss (e.g. because the previous entry expired) simply overwrites the old entry wholesale.

## Cache Insertion Ordering

There is exactly one valid execution sequence for each of the two outcomes `execute_with_cache()` can
reach — stated here as the sole authoritative ordering, restating (never contradicting) Cache Lookup
Strategy and Cache Miss Behavior above:

**Hit path:**
```
resolve_execution_config()
      ↓
compute_cache_key()
      ↓
cache_adapter.get(cache_key)
      ↓
Cache Validation (structural well-formedness, then freshness)
      ↓
valid and fresh?
      ↓ yes
return cached llm_response, unmodified (cache_hit = True) — cache_adapter.put() is NEVER called
```

**Miss path** (no entry, or an entry that failed Cache Validation):
```
resolve_execution_config()
      ↓
compute_cache_key()
      ↓
cache_adapter.get(cache_key) → None, or an entry that fails Cache Validation
      ↓
Stage 13 — execute_prompt(prompt_package, llm_adapter, resolved_execution_config)
      ↓
is_cacheable_status(llm_response.status)
      ↓ yes                                   ↓ no
cache_adapter.put(cache_key, entry)     (no write attempted)
      ↓                                        ↓
      └────────────────┬───────────────────────┘
                        ↓
     build_cached_execution_result() → validate_cached_execution_result() → return (cache_hit = False)
```

Two invariants hold across both sequences, with no exception: `cache_adapter.put()` is **never** called
before `cache_adapter.get()` for the same request (a lookup always precedes any possible write), and
cache-eligibility (`is_cacheable_status`) is **always** evaluated after Stage 13's own `execute_prompt()`
returns and **before** any `cache_adapter.put()` call — never the reverse, and never concurrently. No
other ordering is valid; a future implementation that reorders either step is not a legitimate
interpretation of this architecture.

## Cache Validation

Structural and freshness checks applied to any `CacheEntry` retrieved via `cache_adapter.get()`,
**before** it is ever trusted as a hit — Stage 17 does not blindly trust a store's own returned content,
the same "does not blindly trust the upstream/external source" posture Stage 9 and Stage 14/15 each
already established for their own inputs:

1. **Structural well-formedness** (`validate_cache_entry`) — the entry has all five required keys
   (`cache_key`, `llm_response`, `prompt_package_id`, `model_name`, `cached_at`), and `llm_response`
   itself carries at minimum `llm_response_id`, `status`, `prompt_package_id` (the three fields Stage
   17 itself reads or checks). A structurally malformed entry is treated as a forced miss — never
   raised as an exception, since a corrupted external store entry is an expected, recoverable
   condition, not a Stage 17 bug.
2. **Freshness** (`is_cache_entry_expired`) — `(now - entry["cached_at"]).total_seconds() >
   cache_ttl_seconds`, when `cache_ttl_seconds` is not `None`. `cache_ttl_seconds = None` means "never
   expires" — the freshness check is skipped entirely. `cache_ttl_seconds = 0` is a distinct, valid,
   meaningful value: every entry is immediately considered stale, effectively disabling reuse (a cache
   *write* still happens normally on the resulting miss) without disabling the cache mechanism itself.
   An expired entry is treated exactly as a miss — Cache Miss Behavior runs normally, and the stale
   entry is wholesale-replaced by whatever fresh entry results.
3. **Self-consistency** (checked as an internal invariant at result-assembly time, not at lookup time —
   Validation §3, `CACHE_KEY_SELF_MISMATCH`) — the retrieved entry's own `cache_key` field must equal
   the `cache_key` it was looked up under; a store returning the wrong entry under a given key is a
   genuine bug, not an expected external-store imperfection, and is therefore an internal invariant
   rather than a lookup-time recoverable check.

Cache-worthiness (whether a *freshly-generated* response is cacheable) is a distinct concern from Cache
Validation (whether a *retrieved* entry is trustworthy) — the former is covered under Cache Miss
Behavior, `is_cacheable_status`.

## Cache Immutability

Stated explicitly, as its own guarantee, rather than left implicit across Design Decisions #6 and Cache
Miss Behavior's own "whole-entry replacement" language:

- **A `CacheEntry` is immutable after insertion.** Once `cache_adapter.put(cache_key, entry)` returns,
  nothing in this architecture ever calls a mutating operation against that specific stored entry again
  — there is no `update()`, `patch()`, or `append()` method anywhere in the `CacheAdapter` contract
  (Cache Storage Abstraction), and Stage 17's own orchestration never constructs one.
- **A subsequent write under the same `cache_key` is always a full replacement, never an in-place
  update.** The *only* way an entry's stored content ever changes is a brand-new `cache_adapter.put()`
  call carrying a brand-new `CacheEntry` object, built fresh from a brand-new Stage 13 `execute_prompt()`
  result — the old entry is superseded wholesale, never edited field-by-field. This is the same
  Idempotent replacement policy already stated in Cache Miss Behavior; it is restated here as an
  immutability guarantee, not a new rule.
- **The replacement policy is deterministic: last-write-wins under `cache_key` identity.** Whichever
  `put()` call for a given `cache_key` is applied last (by the `CacheAdapter`'s own ordering — Stage 17
  imposes no ordering of its own beyond calling `put()` at most once per `execute_with_cache()`
  invocation) is the entry a subsequent `get()` returns; this is the same last-write-wins semantics
  already named in Concurrency for the cache-stampede scenario, restated here as the entry's own
  replacement contract.
- **A cached artifact is byte-identical to the stored output, forever, until replaced.** Between being
  written and later being read back, a `CacheEntry`'s own `llm_response` is never altered by anything —
  no re-serialization, no re-normalization, no field patch. Cache Hit Behavior already states a hit
  returns the entry "completely unmodified"; this section states the complementary guarantee from the
  storage side: nothing between the `put()` and the `get()` ever touches the stored bytes either.

## Design Decisions

1. **Stage 17 wraps Stage 13's own frozen `execute_prompt()`; it never invokes an `LLMAdapter`
   directly.** This is the load-bearing resolution of the Stage 14 Roadmap Definition Pass's own open
   caveat: Stage 17's real invocation position sits between Stage 12 and Stage 13, not after Stage 16 —
   its design sequence number reflects only when it was designed, never its runtime order. Delegating
   to Stage 13's own unmodified entrypoint (rather than reimplementing any part of request construction
   or retry handling) keeps Stage 13's own frozen contract completely untouched, per the Frozen
   Pipeline Boundary.
2. **Stage 17 is the first query-time stage since Stage 9 to own and mutate a persisted artifact.**
   Principle 2 (read-only *on artifacts a stage doesn't own*) is what makes this legitimate: a cache
   store is Stage 17's own artifact, exactly as `vector_index/` is Stage 9's own artifact — writing to
   it is not a violation of the read-only posture Stage 10 through Stage 16 each maintain toward
   *upstream* artifacts they don't own. `PromptPackage`, every earlier-stage artifact, and the manifest
   remain strictly read-only to Stage 17 (Read-Only Guarantees) — only the cache store itself is ever
   written.
3. **Only `PASS`/`PARTIAL` responses are ever cached; `SKIPPED`/`FAIL` never are.** Caching a failure
   would mean an identical future request receives a stale failure forever instead of a fresh retry —
   the opposite of what caching is for. A `SKIPPED`/`FAIL` response is still returned to the caller
   normally on a miss; it is simply never written to the store.
4. **`cache_key` uses the identical formula to Stage 13's own `llm_response_id` hash — deliberately,
   not coincidentally.** Both answer the same underlying question ("does this exact request have a
   deterministic identity"), just at two different layers: Stage 13 identifies a response after
   generating it; Stage 17 identifies a request before deciding whether to generate it at all. A
   provable consequence: whenever a `CachedExecutionResult`'s own `llm_response` was produced by this
   exact `cache_key`'s request, `llm_response.llm_response_id == cache_key` always — checked directly
   (`CACHED_LLM_RESPONSE_ID_MISMATCH`, Validation §3), never merely assumed.
5. **A cache backend failure degrades to a forced miss; it is never a fatal error for the whole call.**
   The cache is an optimization layer over Stage 13's own always-correct-if-slower path; a broken
   `CacheAdapter` (a down Redis instance, a corrupted local file) must never prevent the pipeline from
   producing an answer. Both `get()` and `put()` failures are caught and recorded as WARNING findings,
   never propagated as exceptions that abort the request.
6. **A cached `LLMResponse` is never modified, at read time or write time.** Stored exactly as Stage 13
   returned it; returned exactly as stored. Stage 17 has no lever to "fix" or re-validate a cached
   response's own content — that would mean Stage 17 silently second-guessing Stage 13's own frozen
   output, exactly the kind of scope creep Stage 15's own Design Decisions #7 already rejected for
   itself one layer up (no lever to correct a low-quality answer).
7. **`resolved_execution_config` — the fully defaulted/clamped config, never the caller's raw input —
   is what determines the cache key.** Stage 17 defines its own private copy of Stage 13's own
   defaulting/clamping logic (never importing it, per the each-stage-owns-its-own-copy convention) so
   that the cache key can be computed *before* deciding whether Stage 13 needs to be called at all —
   using the raw, possibly-partial config would make two logically-identical requests (one omitting a
   field, one supplying its default explicitly) hash differently, defeating the entire purpose of the
   cache key.
8. **No semantic or fuzzy matching between two requests, ever.** Two requests either produce the
   identical `cache_key` or they are entirely unrelated as far as Stage 17 is concerned — no
   "close enough" prompt similarity, no embedding-based nearest-cache-entry lookup. This is a direct
   application of Principle 5 (deterministic before probabilistic): a fuzzy cache-key match would be
   exactly the kind of probabilistic judgment this pipeline forbids everywhere.
9. **`status` on `CachedExecutionResult` is a pure passthrough of `llm_response.status`, never
   independently computed.** Whether the underlying response came from a hit or a fresh Stage 13 call,
   its own `status` already fully describes the outcome; Stage 17 adds no new status vocabulary of its
   own (mirrors Stage 10 through Stage 12/14/15/16's own passthrough convention, not Stage 13's own
   independently-computed status).
10. **Concurrent identical requests may both miss and both independently invoke Stage 13 — a
    documented, accepted "cache stampede," never prevented by Stage 17's own contract.** Preventing it
    would require the `CacheAdapter` contract to guarantee cross-call locking or a
    check-and-reserve/compare-and-set primitive — a real capability some backends can offer but not
    all, and not required by this design (Concurrency, Known Limitations). A specific `CacheAdapter`
    implementation may add its own atomicity if its backend supports it; Stage 17's own orchestration
    never assumes it does.
11. **No cache eviction policy beyond TTL-driven staleness is specified.** Size-bounded eviction (LRU,
    LFU, or any capacity limit) is entirely the `CacheAdapter` implementation's own concern — Stage 17's
    contract has no `evict()` or `size()` method, and no orchestration function ever needs one, since
    `put()`'s own wholesale-replacement semantics are sufficient for Stage 17's own correctness
    regardless of how (or whether) a given backend bounds its own total size.
12. **`CachedExecutionResult` is fully in-memory, never persisted by Stage 17 itself as a distinct
    artifact** — the *cache entries* Stage 17 writes via `CacheAdapter.put()` are its own owned,
    persisted state (Design Decisions #2), but the wrapping `CachedExecutionResult` returned to a
    caller is not separately saved anywhere, exactly as Stage 10 through Stage 16 each never persist
    their own return value either.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md` §4's
Critical/Recoverable document-quarantine model, since Stage 17 has no document to quarantine and no
persisted-per-document artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10
through Stage 16 each already gave for their own Validation sections).

**1. Input validation codes** — raised, never returned as part of any `CachedExecutionResult`:

| Code | Raised as | Trigger |
|---|---|---|
| `PROMPT_PACKAGE_MALFORMED` | `ResponseCachingInputError` | the received `PromptPackage` is missing `prompt_package_id` or `status`, or either is wrong-typed; no `CachedExecutionResult` is produced at all |
| `EXECUTION_CONFIG_MALFORMED` | `ResponseCachingInputError` | the resolved `LLMExecutionConfig` is missing `model_name`, or `model_name` is wrong-typed — mirrors Stage 13's own identical requirement one layer down |

**2. Package-level findings** — recorded in `CachedExecutionResult.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `CACHE_HIT` | INFO | package | a fresh, valid entry was found and returned; `cache_hit = True` |
| `CACHE_MISS` | INFO | package | no valid entry was found; Stage 13's own `execute_prompt()` was invoked |
| `CACHE_ENTRY_EXPIRED` | WARNING | package | a matching entry existed but failed the freshness check (Cache Validation); treated as a miss |
| `CACHE_ENTRY_MALFORMED` | WARNING | package | a matching entry existed but failed structural validation (Cache Validation); treated as a miss |
| `CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS` | WARNING | package | the fresh `llm_response.status` was `SKIPPED`/`FAIL`; no write attempted (Design Decisions #3) |
| `CACHE_READ_FAILED` | WARNING | package | `cache_adapter.get()` itself raised; treated as a forced miss (Failure Handling) |
| `CACHE_WRITE_FAILED` | WARNING | package | `cache_adapter.put()` itself raised; the freshly-computed `llm_response` is still returned (Failure Handling) |

Exactly one of `CACHE_HIT` or `CACHE_MISS` is present on every `CachedExecutionResult`, never both,
never neither — `cache_hit` and this pair of findings are always consistent
(`CACHE_HIT_FLAG_INCONSISTENT`, Validation §3). No finding here ever alters `status` — `status` is a
pure passthrough of `llm_response.status` regardless of which cache path was taken (Design Decisions
#9).

**3. Internal invariant codes** — raised by `validate_cached_execution_result()`, run unconditionally
on the assembled result before it is ever returned; never returned as part of any
`CachedExecutionResult`:

| Code | Trigger |
|---|---|
| `CACHE_KEY_FORMULA_MISMATCH` | the recomputed `compute_cache_key(prompt_package_id, model_name, resolved_execution_config)` does not equal the `cache_key` actually used for this lookup/write |
| `CACHE_KEY_SELF_MISMATCH` | on a hit, the retrieved `CacheEntry`'s own `cache_key` field does not equal the `cache_key` it was looked up under |
| `CACHED_LLM_RESPONSE_ID_MISMATCH` | `llm_response["llm_response_id"] != cache_key`, for any result whose `llm_response["status"]` is cacheable (`PASS`/`PARTIAL`) |
| `NON_CACHEABLE_STATUS_WRITTEN` | a `CacheEntry` was actually written (`CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS` did **not** fire) whose `llm_response["status"]` is not in `CACHEABLE_STATUSES` |
| `CACHE_HIT_FLAG_INCONSISTENT` | `cache_hit == True` without a `CACHE_HIT` finding present, or `cache_hit == False` without a `CACHE_MISS` finding present, or both `CACHE_HIT` and `CACHE_MISS` present together |
| `PROMPT_PACKAGE_ID_MISMATCH` | `llm_response["prompt_package_id"] != input PromptPackage["prompt_package_id"]` |

Any of these six raises `ResponseCachingInternalError` rather than being returned as a malformed
`CachedExecutionResult` — the same fail-loud posture as Stage 10 through Stage 16's own
internal-invariant exceptions, and never expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage17_response_caching"`, `doc_id: null` always —
entries are request-scoped, not document-scoped). New codes this stage adds:
`INFO_CACHE_HIT`, `INFO_CACHE_MISS`, `WARNING_CACHE_ENTRY_EXPIRED`, `WARNING_CACHE_ENTRY_MALFORMED`,
`WARNING_CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS`, `WARNING_CACHE_READ_FAILED`,
`WARNING_CACHE_WRITE_FAILED`. No new `FATAL_*` code — Stage 17 never sets a manifest `error_code`,
since it never touches the manifest at all (see Manifest Interaction).

## Manifest Interaction

None. Stage 17 never opens, reads, or writes `manifest.json` — extending Stage 11 through Stage 16's
own zero-manifest-interaction posture: a cache entry is keyed by request identity
(`prompt_package_id`/`model_name`/config), not document identity, and has no natural document to
attach a manifest record to.

## Artifact Interaction

Stage 17 reads and writes exactly one kind of state — cache entries, via the caller-supplied
`CacheAdapter` — and nothing else. `PromptPackage`, `LLMAdapter`, and every earlier-stage artifact or
in-memory object remain strictly read-only. Unlike every `data/proposals/`-scoped artifact any earlier
stage owns, the cache store's own location, format, and backend are entirely undefined by this
architecture (Cache Storage Abstraction) — a caller-supplied concrete `CacheAdapter` decides all of
that, entirely outside this pipeline's own `data/proposals/` artifact tree.

## Directory Structure

None fixed by this architecture. Stage 17 introduces no new artifact directory under `data/proposals/`
— a concrete `CacheAdapter` implementation is free to use any storage location or format it chooses
(an in-process dict needs none at all; a file-backed adapter might use its own directory; a networked
adapter needs none on the local filesystem at all), and none is prescribed here, per this design's own
explicit "do not choose a concrete backend" instruction.

## Determinism

Stage 17 is the second stage in this pipeline (after Stage 13) to draw an explicit line between what it
guarantees deterministic and what it does not — for a materially different reason than Stage 13's own:
Stage 17's own logic is a pure function of its inputs, but *whether a given call is a hit* depends on
the cache store's own prior, mutable, stateful contents — not reproducible in isolation, the same way a
database read's result depends on what was previously written to that database.

**Stated exhaustively, as a single checklist, before the detailed breakdown below:**
- Identical inputs (`prompt_package_id`, `model_name`, `temperature`, resolved `max_output_tokens`)
  always produce an identical `cache_key`.
- Given an identical `cache_key` and an identical cache-store state at the moment of lookup, the
  hit/miss **decision** itself is deterministic — `lookup_cache()` is a pure function of `cache_key`,
  `cache_ttl_seconds`, and whatever `cache_adapter.get()` returns for that exact key at that exact
  moment; the *store's own prior contents* are the one genuinely external, stateful input (see below),
  but the decision logic applied to them is not.
- Insertion behavior is deterministic: `is_cacheable_status()` is a pure, total function of `status`
  alone, and a `put()` is attempted if and only if it returns `True` — never conditional on any other
  signal.
- Overwrite behavior is deterministic: last-write-wins under `cache_key` identity, always a full
  wholesale replacement, never a partial merge (Cache Immutability).
- No randomness of any kind feeds into `cache_key`, the hit/miss decision logic, `is_cacheable_status`,
  or `validate_cached_execution_result()`'s own outcome.
- `cached_at` and `resolved_at` are the only fields ever excluded from a determinism comparison — no
  timestamp of any kind ever participates in `cache_key` or in any other hashed/compared value.
- `canonical_json`'s own key-sorting guarantees `cache_key` never depends on dict/kwarg construction or
  iteration order (already stated in Cache Key Construction's own "Ordering guarantees" — restated here
  as part of this stage's own Determinism checklist, not a new guarantee).

**Deterministic (guaranteed, byte-identical across runs, given identical input and identical cache
state):**
- **`cache_key` computation.** A pure function of `prompt_package_id`, `model_name`, and the *resolved*
  `temperature`/`max_output_tokens` alone (Cache Key Construction) — identical logical requests always
  produce the identical `cache_key`, with no timestamp, UUID, or random value ever contributing to it.
- **Freshness/validation logic.** `is_cache_entry_expired` and `validate_cache_entry` are pure functions
  of their own arguments and the fixed `cache_ttl_seconds` policy — no hidden state, no randomness.
- **Cache-worthiness classification.** `is_cacheable_status` is a pure, total function of `status`
  alone, against the fixed `CACHEABLE_STATUSES` constant.
- **`validate_cached_execution_result()`'s own outcome.** Identical `CachedExecutionResult` content
  always produces an identical validation outcome.

**Explicitly NOT deterministic (inherent to a stateful cache; never assumed, never hidden):**
- **Hit vs. miss outcome.** Depends entirely on the cache store's own prior contents at the moment of
  lookup — a genuinely external, mutable, cross-call state Stage 17 does not control and cannot make
  reproducible from within a single call's own inputs alone.
- **`resolved_at`, `cached_at` (on a miss).** Wall-clock by definition; excluded from every determinism
  comparison, the same treatment every other stage already gives its own timestamp field.
- **Everything Stage 13 itself already documents as non-deterministic** (`response_text`,
  `finish_reason`, token counts, `latency_ms`, `attempt_count`, `provider_request_id`) — inherited
  unchanged on a miss, since Stage 17 never alters any field of a freshly-generated `LLMResponse`
  (Design Decisions #6).

## Read-Only Guarantees

Stage 17 never modifies `manifest.json`, any `PromptPackage`, `ContextPackage`, `RetrievalResult`, any
chunk, any metadata, any vector index, any embedding, or a stored `LLMResponse`'s own content (Design
Decisions #6). The one deliberate, necessary exception in this entire design: Stage 17 **does** write
to the cache store it owns, via `CacheAdapter.put()` — exactly as Stage 9 writes to `vector_index/`,
its own owned artifact (Design Decisions #2). Every artifact or in-memory object Stage 17 does not
itself own remains strictly read-only, with no exception.

## Failure Handling

- **A malformed `PromptPackage` or `LLMExecutionConfig`** (missing/wrong-typed required key) —
  `ResponseCachingInputError` (`PROMPT_PACKAGE_MALFORMED` / `EXECUTION_CONFIG_MALFORMED`) raised
  immediately; no `CachedExecutionResult` returned; `cache_adapter.get()` is never called.
- **`cache_adapter.get()` itself raises** — caught, treated as a forced miss; `CACHE_READ_FAILED`
  WARNING recorded; Stage 13's own `execute_prompt()` is invoked exactly as on an ordinary miss.
- **A retrieved `CacheEntry` fails structural validation** — `CACHE_ENTRY_MALFORMED` WARNING; treated
  as a miss; the malformed entry is never returned to the caller and is silently superseded by whatever
  fresh entry the resulting miss produces (if cacheable).
- **A retrieved `CacheEntry` is expired** (`cache_ttl_seconds` not `None`, and stale) —
  `CACHE_ENTRY_EXPIRED` WARNING; treated as a miss; wholesale-replaced on the resulting write, if
  cacheable.
- **Stage 13's own `execute_prompt()` itself raises** (`LLMExecutionInputError`,
  `LLMExecutionInternalError`) — propagated unchanged; Stage 17 performs no error translation or
  swallowing of Stage 13's own exceptions, since a Stage 13-level failure is not a Stage 17 concern to
  reinterpret.
- **The fresh `llm_response.status` is `SKIPPED` or `FAIL`** — `CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS`
  WARNING; no write attempted; `llm_response` is still returned normally, `cache_hit = False`.
- **`cache_adapter.put()` itself raises** — caught; `CACHE_WRITE_FAILED` WARNING recorded; the already-
  computed `llm_response` is still returned to the caller, `cache_hit = False` — a caching failure never
  blocks a successful generation from reaching the caller.
- **`cache_ttl_seconds` omitted** — defaulted to `DEFAULT_CACHE_TTL_SECONDS`; if supplied, clamped to
  `[0, MAX_CACHE_TTL_SECONDS]`; `None` is a distinct, valid sentinel meaning "never expires" and is
  never clamped away (Cache Validation).
- **A genuine Stage 17 bug** (one of the six named internal invariant codes in Validation §3) —
  `ResponseCachingInternalError` raised, not returned as a malformed `CachedExecutionResult`.

## Cache Backend Failure

The complete, exhaustive degradation policy for every operation the `CacheAdapter` contract exposes —
restating Failure Handling's own individual bullets here as one consolidated policy, per operation:

- **Lookup failure** (`cache_adapter.get()` raises) — caught by `lookup_cache()`; treated exactly as
  `(hit=False, entry=None)`, i.e. a forced miss. `CACHE_READ_FAILED` WARNING recorded. Deterministic
  outcome: Stage 13's own `execute_prompt()` is invoked exactly as it would be on an ordinary,
  no-entry-found miss — there is no separate "lookup broken" code path, only the ordinary miss path.
- **Write failure** (`cache_adapter.put()` raises) — caught by `store_cache_entry()`;
  `CACHE_WRITE_FAILED` WARNING recorded. Deterministic outcome: the already-computed `llm_response` (the
  actual answer to the caller's request) is returned exactly as if the write had succeeded, with
  `cache_hit = False` — a write failure changes nothing about what is returned, only whether a future
  identical request will find an entry to hit against.
- **Delete failure — not applicable; there is no delete operation in this contract.** The
  `CacheAdapter` contract (Cache Storage Abstraction) defines exactly three methods — `get`, `put`,
  `get_statistics` — and no `delete`/`evict`/`invalidate` method of any kind (Design Decisions #11: no
  eviction policy beyond TTL-driven staleness is specified by this architecture at all). Stage 17 never
  calls a delete-style operation, so there is no delete-failure case to define; a concrete
  `CacheAdapter` implementation that offers its own internal eviction (e.g. an LRU cache silently
  dropping an old entry) does so entirely outside this contract, invisibly to Stage 17's own
  orchestration, and any such internal eviction failure is that implementation's own concern, never
  something Stage 17 observes or reacts to.
- **Every backend failure above degrades to a WARNING finding on an otherwise-successful
  `CachedExecutionResult` — never a `ResponseCachingInternalError`, never a `ResponseCachingInputError`,
  and never an exception that reaches the caller.** Stated as the one summary guarantee this section
  exists to make explicit: **a `CacheAdapter` failure never alters downstream pipeline semantics.**
  Stage 14 through Stage 16 receive the identical `LLMResponse` shape, with the identical content,
  regardless of whether the cache behind Stage 17 is fully healthy, entirely broken, or somewhere in
  between — the only externally-visible difference a backend failure produces is which WARNING findings
  appear in `CachedExecutionResult.findings[]` and, over repeated calls, degraded latency (every request
  effectively becomes a miss, at Stage 13's own cost, never Stage 17's own cost) — never a difference in
  correctness, never a difference in `status`, and never a new failure mode a downstream stage would
  need to handle that it didn't already need to handle for an ordinary cache miss.

## Configuration

`cache_ttl_seconds` is per-request configuration, never defaulted from any global or environment state
except via the named `DEFAULT_CACHE_TTL_SECONDS` constant when the caller omits it — the same
per-request convention Stage 11 through Stage 16 each already established for their own tunables. The
`CacheAdapter` itself (or a factory producing one) is likewise runtime-supplied, never hard-coded,
matching Stage 8/9/13's own `adapter_factory` convention — Stage 17 never imports a specific cache
backend by name in its own orchestration path. `CACHEABLE_STATUSES` is a fixed constant, never
per-request configurable — allowing a caller to redefine which statuses are cache-worthy would let two
callers derive different cached content from the identical `cache_key`, undermining the key's own
meaning as a stable request identity.

## Concurrency

Not fully safe under concurrent calls sharing a `cache_key`, and this is a documented, accepted
limitation rather than a guarantee this design provides. Two concurrent calls for the identical request
may both observe a miss (or both observe an expired entry) before either has written a fresh entry —
both then independently invoke Stage 13's own `execute_prompt()` (a "cache stampede") and both
eventually call `cache_adapter.put()`, with the store's own last-write-wins semantics deciding which
entry survives. Neither outcome is incorrect — both `LLMResponse`s are individually valid, cache-worthy
responses to the identical request — merely redundant work, never data corruption. Stage 17's own
contract requires no locking, compare-and-set, or other cross-call coordination from `CacheAdapter`; a
specific implementation may add its own atomicity against its own backend if it needs to (Known
Limitations).

## Security Considerations

- **Cached content may be sensitive.** A stored `llm_response.response_text` may embed retrieved corpus
  content, and by extension anything that content itself carries; encryption at rest, access control,
  and retention policy for the cache store are entirely the `CacheAdapter` implementation's/deployment's
  own concern, never addressed by this architecture (mirrors Stage 13's own identical "provider-side
  retention is outside this design's visibility" caveat, one layer further downstream).
- **Cache poisoning, if the backend is shared or networked.** A `CacheAdapter` backed by a shared or
  networked store (e.g. Redis) without its own access control could in principle be written to by an
  unauthorized party; this is entirely outside Stage 17's own control surface — the same "can only be
  addressed by the adapter/deployment layer, not by Stage 17's own orchestration" posture Stage 13's
  own credential-handling note already established for its own adapter boundary.
- **No local write capability against any artifact Stage 17 does not own** — every risk class this
  guarantee eliminates for every prior stage (Stage 10 through Stage 16's own identical language) is
  eliminated here too, for every artifact *except* the cache store itself, which this design explicitly
  and deliberately permits Stage 17 to write (Design Decisions #2).

## Public Function Contracts

- `validate_prompt_package_for_cache(package: PromptPackage) -> None` — Stage 17's own structural input
  check; inspects exactly `prompt_package_id` and `status` — no other `PromptPackage` field is
  inspected. Raises `ResponseCachingInputError` (code `PROMPT_PACKAGE_MALFORMED`) on violation. Distinct
  from, and never calling, Stage 12's own function of the same purpose.
- `resolve_execution_config(config: Optional[LLMExecutionConfig]) -> LLMExecutionConfig` — Stage 17's
  own private copy of Stage 13's defaulting/clamping logic; raises `ResponseCachingInputError` (code
  `EXECUTION_CONFIG_MALFORMED`) if `model_name` is missing after resolution.
- `compute_cache_key(prompt_package_id: str, model_name: str, resolved_execution_config:
  LLMExecutionConfig) -> str` — the fixed formula (Cache Key Construction); pure function of its three
  arguments; total.
- `lookup_cache(cache_adapter: CacheAdapter, cache_key: str, cache_ttl_seconds: Optional[int]) ->
  Tuple[bool, Optional[CacheEntry]]` — returns `(is_fresh_hit, entry_or_none)`; applies Cache Validation
  internally; never raises on a backend `get()` failure (caught, treated as `(False, None)`).
- `validate_cache_entry(entry: CacheEntry) -> bool` — structural well-formedness check (Cache
  Validation §1); returns `False` rather than raising, since a malformed external entry is an expected,
  recoverable condition.
- `is_cache_entry_expired(entry: CacheEntry, cache_ttl_seconds: Optional[int]) -> bool` — the freshness
  check (Cache Validation §2); pure function of its two arguments and the current wall-clock time;
  always `False` when `cache_ttl_seconds is None`.
- `is_cacheable_status(status: str) -> bool` — `True` iff `status in CACHEABLE_STATUSES`; pure, total
  function of its one argument.
- `store_cache_entry(cache_adapter: CacheAdapter, cache_key: str, llm_response: LLMResponse,
  prompt_package_id: str, model_name: str) -> bool` — builds and writes a `CacheEntry` only when
  `is_cacheable_status(llm_response["status"])`; returns whether a write was actually attempted; never
  raises on a backend `put()` failure (caught, recorded as a finding by the caller).
- `build_cached_execution_result(llm_response: LLMResponse, cache_key: str, cache_hit: bool,
  cached_at: str, cache_backend_name: str, findings: List[Dict]) -> CachedExecutionResult` — assembles
  the final result; `status` is copied verbatim from `llm_response["status"]`.
- `validate_cached_execution_result(result: CachedExecutionResult, prompt_package: PromptPackage,
  resolved_execution_config: LLMExecutionConfig) -> None` — internal invariant self-check; raises
  `ResponseCachingInternalError` (one of the six named codes in Validation §3) on violation.
- `execute_with_cache(prompt_package: PromptPackage, llm_adapter: LLMAdapter, cache_adapter:
  CacheAdapter, execution_config: Optional[LLMExecutionConfig] = None, cache_ttl_seconds:
  Optional[int] = None) -> CachedExecutionResult` — the sole public entrypoint; orchestrates Cache
  Lookup Strategy → (Cache Hit Behavior | Cache Miss Behavior, the latter delegating to Stage 13's own
  unmodified `execute_prompt()`) → result assembly → internal self-check; never touches the manifest or
  any artifact besides the cache store.

## Constants

```python
RESPONSE_CACHING_PIPELINE_VERSION = "1.0.0"
CACHEABLE_STATUSES = ("PASS", "PARTIAL")   # closed set — only these LLMResponse statuses are ever
                                            # written to the cache (Design Decisions #3)
DEFAULT_CACHE_TTL_SECONDS = 3600           # 1 hour default freshness window
MAX_CACHE_TTL_SECONDS = 604800             # 7-day hard ceiling — guards a pathological configuration;
                                            # None (never expires) is a distinct sentinel, never clamped
```

## Known Limitations

- **Stage 17 does not validate cache correctness semantically, in any sense.** A cache hit is returned
  because its `cache_key` matches, never because Stage 17 judged the cached content to still be
  accurate, relevant, or well-formed in any meaning-aware sense — Cache Validation checks only
  structural well-formedness and freshness (age), never content correctness.
- **Stage 17 does not verify groundedness of a cached or freshly-generated answer.** That remains
  exclusively Stage 15's own frozen job (Non-Responsibilities); Stage 17 does not know, and never asks,
  whether a returned `LLMResponse` is well-grounded.
- **Stage 17 does not evaluate answer quality of a cached or freshly-generated answer.** That remains
  exclusively Stage 16's own frozen job (Non-Responsibilities); a low-quality cached answer is returned
  exactly as readily as a high-quality one, with no distinction drawn.
- **Stage 17 never regenerates a stale answer on its own initiative.** "Stale" here means only "past its
  configured `cache_ttl_seconds`" — a purely time-based, content-blind notion. An expired entry results
  in exactly one thing: a miss, followed by the ordinary Cache Miss Behavior path (a fresh Stage 13
  call); Stage 17 has no separate "detect and proactively refresh a degraded answer" behavior, and never
  inspects `response_text` to decide whether regeneration is warranted.
- **Stage 17 never invalidates a cache entry based on the answer's own content.** The only invalidation
  mechanisms this architecture defines are TTL expiry (Cache Validation) and a caller flushing/
  namespacing the store outside this design entirely (Cache Key Construction's own Versioning
  strategy) — never a judgment that a specific cached `response_text` has become wrong, outdated in
  substance, or otherwise unfit, since making that judgment would require exactly the kind of semantic
  evaluation Stage 15/16 own and Principle 5 forbids Stage 17 from attempting itself.
- **A cache hit's own `latency_ms`/`attempt_count`/`provider_request_id` reflect the original miss that
  produced the entry, never the current lookup.** A caller reading these fields on a hit and assuming
  they describe "this call" would be misled — they describe whichever earlier call actually generated
  the cached content (Cache Hit Behavior).
- **Concurrent identical requests may both miss ("cache stampede") — redundant cost, never data
  corruption, and not prevented by this design.** A `CacheAdapter` implementation may add its own
  atomicity against its own backend; none is required by Stage 17's own contract (Concurrency).
- **No cache eviction policy beyond TTL-driven staleness is specified.** Total store size, LRU/LFU
  eviction, or any capacity bound is entirely a `CacheAdapter` implementation concern, invisible to
  Stage 17's own orchestration (Design Decisions #11).
- **No cross-request or fuzzy similarity matching, by design, not by omission.** Two prompts differing
  by even one character (and therefore one different `prompt_package_id`) are entirely unrelated cache
  entries, even if a human would judge them "essentially the same question" — Principle 5 forbids any
  fuzzy-match alternative (Design Decisions #8).
- **A cache backend failure is silently absorbed as a forced miss/failed write, never surfaced as a hard
  error.** This is a deliberate reliability choice (Design Decisions #5), but it also means a
  persistently broken `CacheAdapter` produces no user-facing failure signal beyond repeated WARNING
  findings — a caller monitoring cache health must inspect `findings[]` or `CacheAdapter.get_statistics()`
  itself, since Stage 17 never escalates a backend failure into a request-level failure.
- **No cache invalidation mechanism beyond TTL expiry and a schema-formula revision.** If the underlying
  corpus, model, or template changes in a way that should invalidate previously-cached answers without
  changing `prompt_package_id`/`model_name`/`temperature`/`max_output_tokens` themselves (it structurally
  cannot, since `prompt_package_id` already encodes the entire upstream context chain — but this is
  restated here as an explicit non-goal, not derived from first principles by a future reader), no
  targeted invalidation primitive is offered beyond waiting out the TTL or flushing the whole store.

## Accepted Tradeoffs

- **No concrete cache backend chosen, unlike Stage 9's own eventual FAISS choice.** Maximizes
  deployment flexibility (in-memory for tests, Redis for production, anything in between) at the cost
  of leaving performance/durability characteristics entirely to whichever `CacheAdapter` a caller
  supplies — a deliberate scope limit per this design's own explicit instruction.
- **Cache stampede is accepted, not prevented.** Simpler contract, no coordination primitive required
  of every possible backend, at the cost of occasional redundant Stage 13 calls under concurrent
  identical requests (Concurrency, Known Limitations).
- **Cache backend failures degrade silently to WARNING findings, never a hard failure.** Maximizes
  pipeline resilience — a broken cache never blocks an answer — at the cost of no automatic escalation
  when a cache has been effectively non-functional for an extended period; a caller must monitor
  `findings[]`/`get_statistics()` itself.
- **No eviction policy, no cross-request similarity matching.** Both are deliberate scope limits
  (Design Decisions #8, #11) consistent with keeping Stage 17's own contract as small and
  backend-independent as possible; either could be a future, separately-designed extension without
  requiring a redesign of `execute_with_cache()`'s own contract.

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not this
document.

- A malformed `PromptPackage` or resolved `LLMExecutionConfig` is rejected deterministically, every
  time, without producing any `CachedExecutionResult` and without any `CacheAdapter` call being made.
- Given an identical `(prompt_package_id, model_name, temperature, resolved max_output_tokens)`,
  `compute_cache_key` is byte-identical across repeated calls, independent of `timeout_seconds`/
  `max_retry_attempts`, and independent of whether the caller omitted a field or supplied its explicit
  default value.
- A cache hit with a fresh, structurally valid entry never calls `llm_adapter.invoke()` (verifiable via
  a call-count assertion against Stage 13's own adapter), and returns `llm_response` byte-identical to
  what was originally stored.
- A cache miss (no entry, an expired entry, or a malformed entry) always results in exactly one call to
  Stage 13's own `execute_prompt()`, and — when `status` is cacheable — exactly one
  `cache_adapter.put()` call storing an entry whose `llm_response` is byte-identical to what
  `execute_prompt()` returned.
- `llm_response.status in {"SKIPPED", "FAIL"}` never results in a `cache_adapter.put()` call, verifiable
  via a call-count assertion; `llm_response` is still returned to the caller with `cache_hit == False`.
- `cache_ttl_seconds = None` never treats any entry as expired, regardless of its own age;
  `cache_ttl_seconds = 0` treats every entry as immediately expired, regardless of its own age.
- A `cache_adapter.get()` or `cache_adapter.put()` failure never propagates as an exception out of
  `execute_with_cache()` — the request always still completes and returns a well-formed
  `CachedExecutionResult`, with the matching WARNING finding recorded.
- For any cacheable `CachedExecutionResult`, `llm_response.llm_response_id == cache_key` always, and
  `cache_key == compute_cache_key(...)` recomputed fresh from the result's own identity-determining
  inputs, always.
- Exactly one of `CACHE_HIT`/`CACHE_MISS` is present on every result, consistent with `cache_hit`,
  every time.
- Every one of the six internal invariant codes (`CACHE_KEY_FORMULA_MISMATCH`,
  `CACHE_KEY_SELF_MISMATCH`, `CACHED_LLM_RESPONSE_ID_MISMATCH`, `NON_CACHEABLE_STATUS_WRITTEN`,
  `CACHE_HIT_FLAG_INCONSISTENT`, `PROMPT_PACKAGE_ID_MISMATCH`) fires under its documented condition and
  only that condition.
- Immutability: `PromptPackage`, `LLMAdapter`, and any retrieved `CacheEntry`/`LLMResponse` object are
  never mutated by any Stage 17 function, regardless of outcome; a stored `CacheEntry`'s own
  `llm_response` is never altered between being written and later being read back.
- No artifact besides the cache store (via `CacheAdapter`) is ever read or written by any Stage 17
  function, under any input or outcome — verifiable by asserting zero filesystem/manifest calls against
  a stub `CacheAdapter` across every test scenario.

## Real Corpus Verification

Against a real `PromptPackage` produced by the live Stage 10 → 11 → 12 chain, executed through a
concrete (or a realistic, contract-conformant stub) `CacheAdapter` and `LLMAdapter`: a first call for a
given real `PromptPackage`/`execution_config` combination misses, invokes Stage 13's own real
`execute_prompt()`, and — assuming a `PASS`/`PARTIAL` outcome — stores an entry; a second, immediately
following call for the identical `PromptPackage`/`execution_config` hits, returns an `llm_response`
byte-identical to the first call's own result, and makes zero calls to `llm_adapter.invoke()`
(confirmed via the adapter's own call count); a third call using a `cache_ttl_seconds = 0` override
against the same store misses again despite the entry's continued presence, confirming freshness
enforcement independent of eviction; a real `PromptPackage` whose upstream `status == "FAIL"`
(`Stage 12` already skipped generation) always misses and — after Stage 13 itself returns `SKIPPED` —
is confirmed to never produce a `cache_adapter.put()` call.

**Determinism, explicitly:** like Stage 13, this section cannot state "two calls always produce a
byte-identical result" unconditionally — that would misstate what this stage actually guarantees.
Instead: `compute_cache_key` is confirmed byte-identical across both calls above; the *hit* call's own
`llm_response` is confirmed byte-identical to the *miss* call's own `llm_response` (proving the cache
correctly preserved Stage 13's own non-deterministic content, rather than regenerating or altering it);
and `validate_cached_execution_result()` passes on both results independently.

Immutability: the input `PromptPackage` object, every real upstream artifact (`manifest.json`, every
`chunks.json`, `embeddings.parquet`, `metadata.json`, everything under `vector_index/`, every on-disk
prompt template file), and the stored `CacheEntry`'s own `llm_response` (read back byte-identical to
what was written) are confirmed unchanged/consistent before and after each call.

## Future Stage Boundaries

Stage 18+ (not designed here) owns everything Stage 17 deliberately excludes: exposing this pipeline as
a network-facing API, response streaming to an external caller, conversation memory or multi-turn
session state, tool/function calling, and agent planning. Specifically:

- **Stage 18 — Network-Facing API / Response Serving** owns turning a `CachedExecutionResult` (and
  everything Stage 14–16 build on top of its own `llm_response`) into an actual HTTP/streamed response
  to an external caller — Stage 17 hands its result back in memory only, exactly as every stage since
  Stage 10 already does. Stated as one precise, independent split of responsibility, kept completely
  separate rather than partially overlapping: **Stage 17 decides *whether* a cached artifact should be
  returned** (the hit/miss decision, Cache Lookup Strategy) — it never decides *how* that artifact
  reaches an external caller. **Stage 18 decides *how* the artifact is exposed to clients** (transport
  protocol, serialization format, streaming vs. buffered delivery, HTTP status codes, authentication) —
  it never decides *whether* the underlying `LLMResponse` came from a cache hit or a fresh generation,
  and never re-implements or second-guesses Stage 17's own hit/miss decision. Neither stage's own
  responsibility ever needs to inspect or reimplement the other's: Stage 18 consumes
  `CachedExecutionResult.llm_response` exactly as it would consume any other `LLMResponse`, indifferent
  to `cache_hit`'s own value; Stage 17 is never aware that a network-facing caller exists at all.
- **Stage 19 — Conversation Memory / Multi-Turn Orchestration** owns session-level state across
  repeated pipeline invocations — a different kind of state than Stage 17's own request-keyed cache,
  never conflated with it; Stage 17's `cache_key` has no notion of a conversation or session at all.
- **Stage 20 — Tool/Function Calling** owns extending the LLM invocation model itself, likely revising
  Stage 13's own frozen `LLMAdapter` contract — entirely out of scope for Stage 17, which only ever
  calls Stage 13's existing, unmodified `execute_prompt()`.
- **Stage 21 — Agent Planning** owns multi-step autonomous reasoning built on Stage 19 and Stage 20 —
  no part of that responsibility is touched here.

Stage 17 hands a `CachedExecutionResult` back in memory; how a caller serves it, remembers it across a
conversation, or builds an agent loop on top of it is entirely out of this design's scope.

## Verification (of this plan)

This is a design-only task — no code is written. Verification is a read-through against the task's own
explicit section list and stage-boundary requirements:

- Every one of the 22 explicitly-requested sections (Overview, Inputs, Outputs, Responsibilities,
  Non-Responsibilities, Pipeline Ordering, Cache Lookup Strategy, Cache Key Construction, Cache Storage
  Abstraction, Cache Entry Schema, Cache Hit Behavior, Cache Miss Behavior, Cache Validation, Cache
  Metadata, Design Decisions, Constants, Configuration, Validation, Failure Handling, Public Function
  Contracts, Determinism, Complexity — folded into Public Function Contracts' O(1)/O(n) statements per
  function plus this section's own note below — Known Limitations, Future Stage Boundaries) is present
  above, alongside every supplementary section Stage 9 through Stage 16's own docs also carry (Scope,
  Schemas — folded into Cache Entry Schema/Cache Metadata, Logging, Manifest/Artifact Interaction,
  Directory Structure, Read-Only Guarantees, Security Considerations, Concurrency, Accepted Tradeoffs,
  Validation Requirements, Real Corpus Verification), per this project's own Consistency Requirement to
  match Stages 11–16's own style exactly.
- **Complexity, stated explicitly here since no dedicated section header was used:** every Stage 17
  function is O(1) in its own arguments except `execute_with_cache` itself, which is O(1) plus whatever
  complexity Stage 13's own `execute_prompt()` contributes on a miss (unchanged, inherited, never
  re-analyzed here) and whatever complexity the caller-supplied `CacheAdapter.get()`/`put()` themselves
  contribute (backend-dependent, outside this architecture's own control — Cache Storage Abstraction).
- Every named backend-independence requirement is met: no orchestration function branches on
  `backend_name`; a stub `CacheAdapter` is sufficient to exercise the entire pipeline; no concrete
  backend is chosen anywhere in this document.
- Every named exclusion (semantic verification, factual verification, answer quality/groundedness
  evaluation, citation extraction/rendering, prompt construction, retrieval, reranking, LLM invocation
  performed directly rather than via Stage 13's own contract, tool calling, conversation memory, agent
  planning, a network-facing API) is confirmed absent and explicitly named as excluded
  (Non-Responsibilities, Scope, Future Stage Boundaries).
- The open caveat from the Stage 14 Roadmap Definition Pass — Stage 17's numeric position vs. its
  runtime position — is explicitly resolved, not assumed away (Context, Pipeline Ordering, Design
  Decisions #1).
- Determinism explicitly separates what is guaranteed from what is not, mirroring Stage 13's own
  precedent rather than Stage 14–16's own unconditional guarantee — correctly, since Stage 17 is
  genuinely stateful in a way none of Stage 14–16 are.
- The single Read-Only Guarantees exception (the cache store itself) is stated explicitly and justified
  against Principle 2, rather than silently contradicting the "fully read-only" language every one of
  Stage 10 through Stage 16's own docs uses.
- Document style (headings, prose density, no implementation notes, no review diary, no narrative
  history) matches Stage 9–16 precedent throughout.
