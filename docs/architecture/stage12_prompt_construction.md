# Stage 12 — Prompt Construction

Stages 0–11 remain completely frozen; nothing below proposes any change to existing code or shipped
docs. This stage is implemented; the design below reflects the shipped code and its test suite.

See `docs/pipeline_principles.md` for shared conventions.

## Overview

Stage 12 turns Stage 11's `ContextPackage` into a `PromptPackage`: a deterministic, fully-rendered
system prompt, user prompt, and combined prompt string, ready to hand to a future LLM-invocation
stage. It performs no retrieval, no context assembly, no generation, no reasoning — it is a pure,
in-memory transformation of already-final context output into rendered prompt text.
`construct_prompt(context_package, template_version, prompt_budget_tokens)` is the sole public
entrypoint.

## Scope

Stage 12 answers exactly one question — given a `ContextPackage`, what deterministic system prompt,
user prompt, and combined prompt string should a caller send to a model — and stops there. It never
invokes an LLM, never generates an answer, never reasons about content, never detects hallucination,
never formats a citation, never reranks or re-scores a block, never remembers a prior turn, never
streams, never evaluates output quality. Those boundaries are restated in Future Stage Boundaries.

## Responsibilities

Stage 12 shall: receive a `ContextPackage`; structurally validate it before use; load a versioned,
static prompt template pair; assemble a deterministic system prompt; assemble a deterministic user
prompt with the query and rendered context injected; preserve Stage 11's own block ordering exactly
(never re-rank); preserve every block's provenance reference in the rendered context text; preserve
whatever metadata a downstream consumer needs to trace rendered text back to its source; estimate and
report prompt token usage against a configurable budget; and assemble a `PromptPackage` whose own
internal invariants are self-checked before it is ever returned.

## Inputs

Two required inputs, only one of them in-memory:

- `ContextPackage` (Stage 11's own output schema, unchanged) — the sole source of the query, every
  context block, and their full provenance.
- Static prompt template files, read from a fixed, version-controlled directory (see Directory
  Structure) — never generated at runtime, never derived from any corpus artifact.

No other input is read. `manifest.json`, `chunks.json`, `metadata.json`, vector indexes, and
embeddings are never opened — every field a rendered prompt needs already exists on `ContextPackage`
and its own `context_blocks`, verbatim (see Design Decisions #1). No PDF is ever reopened; no chunk
is ever regenerated; no vector search or embedding call is ever performed here; and Stage 12 never
reads `RetrievalResult` directly — only what `ContextPackage` already carries forward from it
(`retrieval_findings`).

## Outputs

None persisted. Stage 12 produces zero artifacts and writes to no file — the third fully read-only,
zero-manifest-interaction stage in this pipeline's query-time path, extending the posture Stage 10
and Stage 11 both already established. Its sole output is an in-memory `PromptPackage` (see Schema)
returned directly to the caller.

## Pipeline

```
ContextPackage { status, context_blocks[], findings[], ... }
      │
      ▼
[1] validate_context_package(context_package)   — Stage 12's own structural input check: required
      keys present, correctly typed. Malformed input raises PromptConstructionInputError
      immediately — this should never happen under correct operation, since Stage 11 already
      self-validates its own output before returning it (see Validation). Distinct from, and never
      calling, Stage 11's own identically-named internal function.
      │
      ▼
[2] resolve template_version and prompt_budget_tokens   — caller-supplied or defaulted/clamped
      (Configuration); no global or environment state consulted
      │
      ▼
[3] load_prompt_template(template_version)   — reads system_prompt.txt, user_prompt.txt, and
      template_metadata.json from config/prompt_templates/<template_version>/ (Directory Structure);
      a missing directory or missing file raises PROMPT_TEMPLATE_NOT_FOUND; a template_version
      disagreeing with template_metadata.json's own declared value raises TEMPLATE_VERSION_MISMATCH
      — both raised as PromptConstructionInputError, immediately
      │
      ▼
[4] render_system_prompt(system_template_text)   — returned verbatim, no substitution (Prompt
      Template Strategy) — the system prompt is deliberately static and context-free
      │
      ▼
[5] render_context_text(context_package.context_blocks)   — fixed per-block format, joined by
      BLOCK_SEPARATOR, in existing rank order (Context Insertion Policy); an empty block list
      (including the `status == "FAIL"` case, where context_blocks is always already empty)
      naturally yields context_text = ""
      │
      ▼
[6] render_user_prompt(user_template_text, context_package.query, context_text)   — substitutes
      {{query}} and {{context_text}} placeholders exactly once, in a single non-recursive pass over
      the template text only (Prompt Template Strategy, Security Considerations)
      │
      ▼
[7] assemble_prompt(system_prompt, user_prompt)   — system_prompt + SYSTEM_USER_SEPARATOR +
      user_prompt (Prompt Assembly)
      │
      ▼
[8] estimate_prompt_tokens(assembled_prompt)   — fixed char-ratio estimate over the full combined
      string (Token Budgeting Strategy)
      │
      ▼
[9] build_prompt_package(...)   — computes prompt_package_id, prompt_utilization, and this stage's
      own findings (CONTEXT_PACKAGE_STATUS_FAIL / PROMPT_BUDGET_EXCEEDED /
      PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET); status is a pure passthrough of
      context_package.status
      │
      ▼
[10] validate_prompt_package(package)   — internal invariant self-check on the assembled output;
      raises PromptConstructionInternalError on violation
      │
      ▼
PromptPackage { status, system_prompt, user_prompt, context_text, assembled_prompt, findings[], ... }
```

## Prompt Assembly Pipeline Diagram

```
                    ┌──────────────────────┐
                    │    ContextPackage      │
                    └──────────┬────────────┘
                               │
                    validate_context_package()
                               │
                     load_prompt_template(template_version)
                               │
                 ┌─────────────┴─────────────┐
                 ▼                            ▼
        render_system_prompt()      render_context_text(context_blocks)
                 │                            │
                 │                  render_user_prompt(query, context_text)
                 │                            │
                 └─────────────┬──────────────┘
                               ▼
                       assemble_prompt()
                               │
                     estimate_prompt_tokens()
                               │
                      build_prompt_package()
                               │
                     validate_prompt_package()
                               │
                               ▼
                        PromptPackage
```

## PromptPackage Schema

```jsonc
{
  "prompt_package_id": "...",                // deterministic identity, see Determinism Guarantees
  "prompt_pipeline_version": "1.0.0",        // this stage's own independent version constant,
                                              // matching Stage 11's context_pipeline_version /
                                              // Stage 10's retrieval_pipeline_version convention
  "constructed_at": "2026-07-20T12:00:00Z",  // timestamp, excluded from every determinism comparison
  "template_version": "1.0.0",               // which template pair under config/prompt_templates/
                                              // was used to render this package
  "context_package_id": "...",               // copied verbatim from the input ContextPackage
  "status": "PASS",                          // PASS | PARTIAL | FAIL — inherited from ContextPackage
  "system_prompt": "...",                    // fully-rendered, static per template_version
  "context_text": "...",                     // rendered context_blocks, see Context Insertion Policy
  "user_prompt": "...",                      // fully-rendered user template, context_text already
                                              // substituted in
  "assembled_prompt": "...",                 // system_prompt + SYSTEM_USER_SEPARATOR + user_prompt —
                                              // the single string a caller would send to a model
                                              // under a simple concatenated-prompt format
  "prompt_budget_tokens": 8000,              // the budget this package was assembled against
  "estimated_prompt_tokens": 7910,           // estimate_prompt_tokens(assembled_prompt)
  "prompt_utilization": 0.989,               // estimated_prompt_tokens / prompt_budget_tokens; never
                                              // clamped to [0.0, 1.0] — see Token Budgeting Strategy
  "findings": [ /* this stage's own findings: {severity, code, message} — see Design Decisions #8
                   for why this field is named findings, not warnings */ ],
  "context_findings": [ /* ContextPackage.findings[], copied verbatim — full upstream provenance */ ]
}
```

## Prompt Template Strategy

A prompt template pair (`system_prompt.txt`, `user_prompt.txt`) is a static, version-controlled pair
of plain-text files under `config/prompt_templates/<template_version>/` (Directory Structure) —
never generated at runtime, never derived from any corpus artifact, never containing a per-query or
per-corpus value baked in.

Substitution uses a fixed, named placeholder syntax — `{{name}}` — replaced via a single, literal,
non-recursive string-substitution pass over the template text only (never a general templating
engine such as Jinja2): no conditionals, no loops, no expression evaluation. This is a deliberate
scope limit (Design Decisions #2), consistent with Principle 5 (deterministic before probabilistic)
and this project's general preference for the simplest mechanism that is fully deterministic and
auditable by inspection.

Exactly two placeholders are defined for v1: `{{query}}` and `{{context_text}}`, both valid only
inside `user_prompt.txt`. `system_prompt.txt` supports no placeholders at all — it is returned
verbatim by `render_system_prompt()` (Design Decisions #3).

**Unknown-placeholder policy — frozen.** Substitution is exactly two fixed, literal find-and-replace
operations (the exact substrings `{{query}}` and `{{context_text}}`), nothing else — there is no
generic `{{name}}` grammar, no placeholder-discovery step, and no enumeration of what a template
"should" contain. A consequence, stated explicitly so no future implementer has to decide it: any
other `{{...}}`-shaped sequence in a template (a typo, an unsupported name, e.g. `{{unknown_variable}}`)
is not recognized as a placeholder at all — it is never substituted, never validated, and passes
through to the rendered output completely unchanged, exactly as if it were ordinary template text.
This never raises, never produces a WARNING finding, and never triggers a validation error — it is
literal-text passthrough, full stop, the only behavior consistent with "substitution is two named
find-replace operations" rather than a real templating engine. Symmetrically, a template that omits
`{{query}}` or `{{context_text}}` entirely simply never receives that content — also literal-text
passthrough of whatever the template author wrote, also never raised or flagged (Known Limitations).

**Versioning — frozen.** `template_version` is per-request configuration, supplied by the caller or
defaulted to `DEFAULT_TEMPLATE_VERSION` (mirrors Stage 11's own `context_budget_tokens` caller-
supplied-with-default convention), and is used to *resolve* which directory to read
(`config/prompt_templates/<template_version>/`). But the directory name is only a lookup key, never
the source of truth for the value that ends up in `PromptPackage.template_version`: every template
directory also contains a third file, `template_metadata.json`, whose own `template_version` field
is the sole authoritative source — `load_prompt_template()` reads it and copies its value verbatim
into the returned package, never deriving it by string-parsing the directory path. If the metadata
file's own `template_version` field disagrees with the directory name used to resolve it, that is a
structural integrity failure — `TEMPLATE_VERSION_MISMATCH`, raised immediately, alongside
`PROMPT_TEMPLATE_NOT_FOUND` in the same input-validation tier (Validation §1). This mirrors Stage 9's
own metadata-vs-content consistency checking pattern (`index_metadata.json`'s own fields are never
assumed correct merely because a directory name matches).

A `template_version` naming no existing directory, or a directory missing any of the three required
files (`system_prompt.txt`, `user_prompt.txt`, `template_metadata.json`), raises
`PromptConstructionInputError` (`PROMPT_TEMPLATE_NOT_FOUND`) — a missing template is a
caller/configuration error, never a data problem, and never produces a degraded `PromptPackage`.

## Context Insertion Policy

`context_text` is produced by `render_context_text(context_blocks)`, applied to
`ContextPackage.context_blocks` in their existing rank order — never reordered, never resorted
(Ordering Guarantees). Each surviving `ContextBlock` is rendered using this fixed, literal per-block
format:

```
[Block {rank}] Source: {title} ({doc_id})
Section: {heading_path joined by " > "}
Pages: {page_start}-{page_end}
Chunk ID: {chunk_id}

{text}
```

Rendered blocks are joined by the fixed separator `BLOCK_SEPARATOR = "\n\n---\n\n"` (Constants). An
empty `context_blocks` list (including every case where `ContextPackage.status == "FAIL"`, which
Stage 11 already guarantees implies `context_blocks == []`) yields `context_text = ""` through this
same single code path — no special-cased branch is needed (Design Decisions #4). `text` is inserted
byte-for-byte, exactly as it arrived on the `ContextBlock` — never truncated, modified, summarized,
or re-normalized.

## Token Budgeting Strategy

Token estimation reuses Stage 11's exact fixed character-ratio formula, but Stage 12 defines its own
independent copy — `estimate_prompt_tokens(text) = ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)`, its
own local `CHARS_PER_TOKEN_ESTIMATE = 4.0` constant — never importing Stage 11's private function
(Design Decisions #5, the same each-stage-owns-its-own-copy pattern Stage 11 already established for
`validate_retrieval_result`). Unlike Stage 11, which estimates per-block, Stage 12 estimates once,
over the full `assembled_prompt` string (`system_prompt` + `SYSTEM_USER_SEPARATOR` + `user_prompt`)
— what matters at this stage is total prompt size, including template scaffolding overhead, not any
individual block's own size (that was already Stage 11's concern).

`prompt_budget_tokens` is per-request configuration (mirrors Stage 11's own `context_budget_tokens`
convention exactly): supplied by the caller, clamped to `[1, MAX_PROMPT_BUDGET_TOKENS]`, defaulting
to `DEFAULT_PROMPT_BUDGET_TOKENS` when omitted.

`prompt_utilization` is one explicit, frozen formula — never merely described in prose:

```python
prompt_utilization = estimated_prompt_tokens / prompt_budget_tokens
```

No clamping is applied to this value (see below) — it is the raw quotient, exactly as computed.

Enforcement is **validate-and-flag only, never corrective** (Design Decisions #4) — a deliberate,
sharp departure from Stage 11's own prefix-truncation enforcement. Stage 12 has no lever to shrink an
oversized prompt: it may never modify `ContextPackage`, split a `ContextBlock`, or drop one from
`context_text` (the read-only guarantee, and chunk atomicity frozen since Stage 7). Two distinct
conditions are named:

- **`PROMPT_BUDGET_EXCEEDED`** (WARNING) — `estimated_prompt_tokens > prompt_budget_tokens`. The
  package is still fully assembled and returned; deciding what to do about an oversized prompt (a
  larger-context model, a smaller `context_budget_tokens` on the next Stage 11 call, or rejecting the
  request) is explicitly a Stage 13+ decision, never Stage 12's.
- **`PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET`** (WARNING) — the base overhead alone (system_prompt +
  SYSTEM_USER_SEPARATOR + a user_prompt rendered with `context_text = ""`) already exceeds
  `prompt_budget_tokens`, independent of any specific `ContextPackage`. This is a stronger signal —
  a construction impossibility rooted in template/budget configuration, not in this particular
  query's retrieved content — but it is deliberately still WARNING severity and never raised: the
  package is still well-formed and fully inspectable, which is more useful for debugging a
  misconfigured budget than an exception that prevents ever seeing the result (Design Decisions #4).

Neither condition ever downgrades `status` (Validation) — the same "WARNING never alters status"
rule Stage 10 and Stage 11 both already established, extended one stage further. `prompt_utilization`
is `estimated_prompt_tokens / prompt_budget_tokens` and, unlike Stage 11's own
`budget_utilization`, is **not** clamped to `[0.0, 1.0]` — it can legitimately exceed `1.0`, since
overflow here is only ever reported, never truncated back into range.

## Ordering Guarantees

`context_text`'s block order strictly preserves `ContextPackage.context_blocks`'s own rank order —
Stage 12 never independently sorts, re-scores, or re-ranks anything. Since Stage 11 already
guarantees `context_blocks` is a contiguous, already-ordered prefix, Stage 12 performs no ordering
decision of its own at all — `render_context_text` is a pure, order-preserving map-then-join over
whatever `context_blocks` already is.

## Provenance Guarantees

Every rendered block in `context_text` carries its own `doc_id`, `chunk_id`, `title`, full
`heading_path`, and page range in a fixed header line (Context Insertion Policy) — enabling a
downstream reader or model to trace any span of `context_text` back to its exact source without
needing to re-open `ContextPackage`. No two blocks are ever merged into one rendered span, even when
adjacent in rank order and from the same document — chunk atomicity, and therefore per-block
provenance, is preserved unbroken one stage further than Stage 11 already carried it.

## Design Decisions

1. **`ContextPackage` alone is sufficient input; `manifest.json`/`chunks.json`/`metadata.json`/
   `RetrievalResult` are never opened.** Every field a rendered prompt needs already exists,
   verbatim, on `ContextPackage` and its own `context_blocks` — re-reading any upstream artifact
   would only duplicate work Stage 10 and Stage 11 already did, for no gain (the identical call
   Stage 11 already made one stage upstream for the identical reason).
2. **Templating is plain `{{name}}` string substitution, never a templating engine.** No new
   dependency, no conditional/loop logic to reason about, fully deterministic and auditable by
   inspection — a reasonable v1 scope matching Principle 5 (deterministic before probabilistic).
3. **The system prompt is static and context-free; only the user prompt is templated with real
   substitution.** Model instructions shouldn't vary with retrieved content — keeping them entirely
   static per `template_version` is simpler to reason about and avoids conflating "instructions" with
   "retrieved data" inside one rendered string.
4. **Prompt-budget enforcement is validate-and-flag only, never corrective.** Stage 12 has no lever
   to shrink an oversized prompt without violating the read-only guarantee or chunk atomicity — so
   unlike Stage 11's prefix truncation, an oversized prompt here is always reported, never fixed;
   correcting it is explicitly deferred to Stage 13+ or to a smaller `context_budget_tokens` chosen
   on a subsequent Stage 11 call.
5. **Token estimation is Stage 12's own copy of Stage 11's fixed-ratio formula, applied once to the
   full assembled prompt, never per-block.** Per-block sizing was already Stage 11's concern; Stage
   12 additionally accounts for template scaffolding overhead that Stage 11 could never have seen.
6. **`prompt_package_id` is a deterministic hash over identity-determining inputs, never the
   rendered text itself.** The exact hash input, matching Stage 9/11's sha256-over-canonical-json
   pattern precisely — no field beyond these three:
   ```python
   hash_input = {
       "context_package_id": context_package["context_package_id"],
       "template_version": template_version,       # from template_metadata.json, post-mismatch-check
       "prompt_budget_tokens": prompt_budget_tokens
   }
   prompt_package_id = sha256(canonical_json(hash_input)).hexdigest()
   ```
   `system_prompt`/`user_prompt`/`assembled_prompt` are deliberately **not** hashed: they are already
   fully determined by these three inputs plus the on-disk template files for that
   `template_version` (themselves identified by `template_version`) — hashing the larger, derived
   text would be redundant, not additionally identity-bearing, and would make the id needlessly
   expensive to compute for a long `assembled_prompt`. This is the identical "hash the
   identity-determining inputs, not the derived payload" choice Stage 9's `index_fingerprint` and
   Stage 11's `context_package_id` already made one stage upstream (Stage 11 also excludes chunk
   `text` itself from its own hash, relying on `chunk_id` as the stable identity-bearing proxy for
   content).
7. **`status` is a pure passthrough of `ContextPackage.status`.** Stage 12 introduces no new FAIL or
   PARTIAL condition of its own; its own findings (`PROMPT_BUDGET_EXCEEDED`,
   `PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET`) are always WARNING-severity and never alter `status`,
   mirroring Stage 10 and Stage 11's identical rule, extended one stage further.
8. **The findings field is named `findings`, not `warnings`.** A deliberate, minor deviation from the
   field name used in this stage's own originating request, in favor of exact naming consistency
   with `RetrievalResult.findings[]` and `ContextPackage.findings[]` — introducing a differently-named
   field for the identical `{severity, code, message}` concept would only invite confusion for a
   caller already used to Stage 10/11's convention.
9. **No FAIL short-circuit branch, unlike Stage 11's own Pipeline [2].** Stage 11 already guarantees
   `status == "FAIL"` implies `context_blocks == []`; an empty block list already renders to
   `context_text = ""` through the ordinary `render_context_text` path with no special case needed —
   so Stage 12's pipeline is uniform across PASS/PARTIAL/FAIL, unlike Stage 11's own two-branch
   pipeline.
10. **Stage 12 defines its own `validate_context_package()`, deliberately reusing Stage 11's function
    name.** Different module, different responsibility: this one structurally validates a *received*
    `ContextPackage` as Stage 12's own input gate, never Stage 11's own internal pre-return
    self-check. The name is intentionally symmetric with Stage 11's contract, not accidental — Stage
    12 never imports or calls Stage 11's version (the identical pattern Stage 11 already established
    one stage upstream for Stage 10's name).
11. **A malformed `ContextPackage` raises, rather than returning a degraded `PromptPackage`.** Since
    Stage 11 already self-validates its own output before ever returning it, a malformed
    `ContextPackage` reaching Stage 12 indicates a caller error or a genuine upstream bug, not a
    normal degraded-but-expected outcome — the same fail-loud posture Stage 11 reserves for its own
    input boundary, applied here one stage further downstream.
12. **`PromptPackage` is fully in-memory, never persisted, matching Stage 10 and Stage 11's own
    posture exactly.** Nothing in this stage's own input list implies a persistence requirement, and
    a future Stage 13+ is expected to consume the returned object directly in-process — the third
    consecutive zero-artifact, zero-manifest-interaction stage in this pipeline's query-time path.

## Validation

Three distinct, clearly-scoped groups of named codes — deliberately not `pipeline_principles.md`
§4's Critical/Recoverable document-quarantine model, since Stage 12 has no document to quarantine and
no persisted artifact to mark FAIL/PASS/WARNING against (the identical reasoning Stage 10 and Stage
11 both already gave for their own Validation sections).

**1. Input validation codes** — raised, never returned as part of any `PromptPackage`:

| Code | Raised as | Trigger |
|---|---|---|
| `CONTEXT_PACKAGE_MALFORMED` | `PromptConstructionInputError` | the received `ContextPackage` is missing a required key or has a wrong-typed value (Pipeline [1]); no `PromptPackage` is produced at all |
| `PROMPT_TEMPLATE_NOT_FOUND` | `PromptConstructionInputError` | `template_version` names no existing directory, or the directory is missing any of `system_prompt.txt` / `user_prompt.txt` / `template_metadata.json` (Pipeline [3]); no `PromptPackage` is produced at all |
| `TEMPLATE_VERSION_MISMATCH` | `PromptConstructionInputError` | `template_metadata.json`'s own `template_version` field disagrees with the directory name used to resolve it (Prompt Template Strategy — Versioning); no `PromptPackage` is produced at all |

**2. Package-level findings** — recorded in `PromptPackage.findings[]`, never raised:

| Code | Severity | Scope | Effect |
|---|---|---|---|
| `CONTEXT_PACKAGE_STATUS_FAIL` | FAIL | package | passthrough of `ContextPackage.status == "FAIL"`; `context_text` is empty, prompt still fully assembled |
| `PROMPT_BUDGET_EXCEEDED` | WARNING | package | `estimated_prompt_tokens > prompt_budget_tokens`; never downgrades `status` |
| `PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET` | WARNING | package | base overhead alone (system + separator + user-with-empty-context) already exceeds `prompt_budget_tokens`; never downgrades `status`; may co-occur with `PROMPT_BUDGET_EXCEEDED` |

`status` truth table (pure passthrough, no additional Stage 12 condition):

| Condition | `status` |
|---|---|
| `ContextPackage.status == "FAIL"` | `FAIL` |
| `ContextPackage.status == "PARTIAL"` | `PARTIAL` |
| `ContextPackage.status == "PASS"` | `PASS` |

**3. Internal invariant codes** — raised by `validate_prompt_package()`, run unconditionally on the
assembled package before it is ever returned; never returned as part of any `PromptPackage`:

| Code | Trigger |
|---|---|
| `ASSEMBLED_PROMPT_MISMATCH` | `assembled_prompt != system_prompt + SYSTEM_USER_SEPARATOR + user_prompt` |
| `CONTEXT_TEXT_NOT_SUBSTITUTED` | `context_text` is non-empty but does not appear as a substring of `user_prompt` |
| `TOKEN_ESTIMATE_MISMATCH` | `estimated_prompt_tokens != estimate_prompt_tokens(assembled_prompt)` |
| `PROMPT_UTILIZATION_MISMATCH` | `prompt_utilization != estimated_prompt_tokens / prompt_budget_tokens` |
| `CONTEXT_PACKAGE_ID_MISMATCH` | `package.context_package_id != input ContextPackage.context_package_id` |

Any of these five raises `PromptConstructionInternalError` rather than being returned as a malformed
`PromptPackage` — the same fail-loud posture as Stage 10's `RetrievalInternalError` and Stage 11's
`ContextAssemblyInternalError`, and never expected to fire under correct operation.

## Logging

Per the shared Logging Specification (`stage: "stage12_prompt_construction"`, `doc_id: null` always
— entries are package-scoped, not document-scoped). New codes this stage adds:
`WARNING_PROMPT_BUDGET_EXCEEDED`, `WARNING_PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET`. No new `FATAL_*`
code — Stage 12 never sets a manifest `error_code`, since it never touches the manifest at all (see
Manifest Interaction).

## Manifest Interaction

None. Stage 12 never opens, reads, or writes `manifest.json` — the second stage in this pipeline
with zero manifest interaction of any kind, extending Stage 11's own posture: every field it needs
already arrived on `ContextPackage`, and a template file is static configuration, never something the
manifest describes.

## Artifact Interaction

Reads only, and only three static, version-controlled files per request (`system_prompt.txt`,
`user_prompt.txt`, `template_metadata.json`), from a fixed, caller-uncontrolled root
(`config/prompt_templates/<template_version>/`) — never a corpus artifact.
Never reads or writes `manifest.json`, `chunks.json`, `metadata.json`, `embeddings.parquet`, or
anything under `vector_index/`. Never writes anything, anywhere. No atomicity concern exists because
there is nothing to persist, and the template files themselves are never written by this stage — only
by whoever authors and checks in a new `template_version` directory, entirely outside this pipeline's
runtime.

## Directory Structure

```
config/prompt_templates/<template_version>/
  system_prompt.txt
  user_prompt.txt
  template_metadata.json      # { "template_version": "1.0.0" } — the authoritative source of
                               # PromptPackage.template_version; the directory name is only a
                               # lookup key (Prompt Template Strategy)
```

Static, version-controlled, checked into the repository — not runtime-generated, not an artifact of
any pipeline run, and not sibling to `data/proposals/{chunks,embeddings,vector_index}/`, which holds
only per-corpus pipeline outputs. A new `template_version` is introduced by adding a new directory,
never by mutating an existing one in place (mirrors the immutable-fingerprint-directory convention
Stage 9 already established for `vector_index/<index_fingerprint>/`).

## Determinism Guarantees

- **Stable `prompt_package_id`.** Deterministic sha256 over exactly `context_package_id`,
  `template_version`, and `prompt_budget_tokens` — no timestamp/UUID/random input.
- **Stable prompt ordering / stable context ordering.** `context_text`'s block order is entirely
  inherited from `ContextPackage.context_blocks`; never independently sorted.
- **Stable serialization.** The per-block format and `BLOCK_SEPARATOR` are fixed strings; identical
  block content always yields byte-identical `context_text`.
- **Stable template rendering.** `render_system_prompt`/`render_user_prompt` are pure functions of
  their own arguments (template text, query, context_text) — no randomness, no environment
  dependence, no locale-sensitive formatting.
- **Stable token estimation.** `estimate_prompt_tokens` is a pure function of its `text` argument
  alone, using a fixed constant ratio — identical text always yields an identical estimate.
- **Stable output.** Identical `(ContextPackage, template_version, prompt_budget_tokens)` produces a
  byte-identical `PromptPackage` (`constructed_at` excluded), across repeated calls and process
  restarts, provided the on-disk template files for that `template_version` are themselves unchanged.

## Failure Handling

- **A malformed `ContextPackage`** (missing/wrong-typed required key) — `PromptConstructionInputError`
  (`CONTEXT_PACKAGE_MALFORMED`) raised immediately; no `PromptPackage` returned.
- **A `template_version` naming no existing directory, or missing any required file** —
  `PromptConstructionInputError` (`PROMPT_TEMPLATE_NOT_FOUND`) raised immediately; no `PromptPackage`
  returned.
- **`template_metadata.json`'s own declared `template_version` disagrees with the directory used to
  resolve it** — `PromptConstructionInputError` (`TEMPLATE_VERSION_MISMATCH`) raised immediately; no
  `PromptPackage` returned.
- **A template containing an unrecognized `{{...}}` sequence, or omitting `{{query}}`/
  `{{context_text}}` entirely** — not a failure of any kind; literal-text passthrough, per the frozen
  Unknown-placeholder policy (Prompt Template Strategy).
- **`ContextPackage.status == "FAIL"`** — graceful, well-formed `PromptPackage{status="FAIL"}`;
  `context_text = ""` naturally, via the ordinary rendering path (no special case); the system and
  user prompts are still fully rendered; `CONTEXT_PACKAGE_STATUS_FAIL` finding recorded.
- **`ContextPackage.status == "PARTIAL"`** — prompt assembled normally from whatever `context_blocks`
  Stage 11 provided; `PromptPackage.status` stays `PARTIAL`; `ContextPackage.findings[]` carried
  forward verbatim into `context_findings`.
- **`ContextPackage.context_blocks == []`** (Stage 11's own `is_empty`, under a PASS or PARTIAL
  status) — `render_context_text` naturally produces `context_text = ""`; no distinct finding beyond
  whatever `ContextPackage.findings[]` already carried forward (e.g. `CONTEXT_EMPTY`).
- **`estimated_prompt_tokens > prompt_budget_tokens`** — `PROMPT_BUDGET_EXCEEDED` WARNING; package
  still fully assembled and returned; `status` unaffected.
- **Base template overhead alone exceeds `prompt_budget_tokens`** — `PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET`
  WARNING, in addition to `PROMPT_BUDGET_EXCEEDED`; package still fully assembled and returned;
  `status` unaffected.
- **`template_version` or `prompt_budget_tokens` omitted** — defaulted to
  `DEFAULT_TEMPLATE_VERSION`/`DEFAULT_PROMPT_BUDGET_TOKENS`; `prompt_budget_tokens`, if supplied, is
  clamped to `[1, MAX_PROMPT_BUDGET_TOKENS]` (mirrors Stage 11's own `context_budget_tokens`
  clamping).
- **A genuine Stage 12 bug** (one of the five named internal invariant codes in Validation §3) —
  `PromptConstructionInternalError` raised, not returned as a malformed `PromptPackage`.

## Configuration

`template_version` and `prompt_budget_tokens` are per-request configuration, never defaulted from any
global or environment state except via the named `DEFAULT_TEMPLATE_VERSION`/
`DEFAULT_PROMPT_BUDGET_TOKENS` constants when the caller omits them entirely — the same per-request
convention Stage 11 already established for `context_budget_tokens`. Stage 12 consumes no adapter
factories of any kind; it never touches `ProviderAdapter` or `IndexAdapter`.

## Concurrency

Fully safe under concurrent calls. Stage 12 performs zero writes and holds no shared mutable state —
`construct_prompt()` is a pure function of its own arguments plus the on-disk template files it
reads (themselves never written at runtime); any number of calls, including against identical input
and identical or differing `template_version`s, may run simultaneously with no locking and no race
condition.

## Security Considerations

- **Prompt injection boundaries.** Chunk `text` embedded in `context_text` may contain adversarial
  instructions authored into the source corpus itself. Stage 12 performs no content sanitization,
  intent inspection, or instruction-detection on any chunk's text — doing so would require a
  fuzzy/probabilistic judgment call this stage is not permitted to make (Principle 5, deterministic
  before probabilistic). This is an accepted, explicitly out-of-scope risk: establishing any defense
  (for example, instructing a model via the system prompt to treat retrieved content as data rather
  than instructions) is a Stage 13+ or model-level concern, never Stage 12's. Stage 12's own
  contribution is purely structural — each block carries a clear provenance header (Context Insertion
  Policy) that gives a downstream reader or model a structural signal of where retrieved content
  starts and ends — but this is an aid, never a security control.
- **Template escaping policy.** `{{name}}` substitution is a single, non-recursive pass over the
  *template* text only — inserted content (`query`, `context_text`) is never re-scanned for
  placeholder tokens. A chunk whose text happens to contain the literal substring `{{` cannot trigger
  a second substitution pass or escape its own rendered boundary. This is placeholder-collision
  avoidance in a plain string-substitution scheme, not HTML/SQL escaping — no such context exists
  here, since the output is plain text, never executed or interpreted by anything Stage 12 itself
  controls.
- **Read-only guarantees.** Stage 12 never modifies `manifest.json`, `ContextPackage`, any
  `RetrievalResult`, any chunk, any metadata, any vector index, or any embedding. No upstream
  artifact is ever mutated; no write capability exists anywhere in this design.
- **Handling of malformed `ContextPackage`s.** A structurally invalid input always raises
  immediately (Failure Handling) — never silently coerced, never partially processed, never returned
  as a degraded-but-plausible-looking `PromptPackage`.

## Public Function Contracts

- `validate_context_package(package: ContextPackage) -> None` — Stage 12's own structural input
  check; raises `PromptConstructionInputError` (code `CONTEXT_PACKAGE_MALFORMED`) on a missing/
  wrong-typed required key. Distinct from, and never calling, Stage 11's own function of the same
  name (Design Decision #10).
- `load_prompt_template(template_version: str) -> Tuple[str, str, str]` — reads
  `config/prompt_templates/<template_version>/{system_prompt.txt,user_prompt.txt,template_metadata.json}`;
  returns `(system_template_text, user_template_text, resolved_template_version)`, where
  `resolved_template_version` is `template_metadata.json`'s own `template_version` field value,
  verbatim — the authoritative value that flows into `PromptPackage.template_version`, never a
  string derived from the directory path. Raises `PromptConstructionInputError` (code
  `PROMPT_TEMPLATE_NOT_FOUND`) if the directory or any of the three required files is missing;
  raises `PromptConstructionInputError` (code `TEMPLATE_VERSION_MISMATCH`) if
  `resolved_template_version != template_version` (the requested value used to resolve the
  directory).
- `render_system_prompt(system_template_text: str) -> str` — returns the text verbatim; no
  substitution is ever performed (Prompt Template Strategy).
- `render_context_text(context_blocks: List[ContextBlock]) -> str` — the fixed per-block format
  (Context Insertion Policy), joined by `BLOCK_SEPARATOR`, in the blocks' existing order; an empty
  list returns `""`.
- `render_user_prompt(user_template_text: str, query: str, context_text: str) -> str` — substitutes
  `{{query}}` and `{{context_text}}` exactly once each, in a single non-recursive pass over the
  template text.
- `assemble_prompt(system_prompt: str, user_prompt: str) -> str` — returns
  `system_prompt + SYSTEM_USER_SEPARATOR + user_prompt`.
- `estimate_prompt_tokens(text: str) -> int` — fixed character-ratio transform (Token Budgeting
  Strategy); pure function of `text` alone; total (always succeeds).
- `build_prompt_package(context_package: ContextPackage, resolved_template_version: str,
  system_prompt: str, user_prompt: str, context_text: str, assembled_prompt: str,
  prompt_budget_tokens: int) -> PromptPackage` — `resolved_template_version` is
  `load_prompt_template`'s own metadata-sourced return value (never the caller's raw request
  string); computes `prompt_package_id`, `estimated_prompt_tokens`, `prompt_utilization`, and this
  stage's own `findings`; sets `status` as a pure passthrough of `context_package.status`.
- `validate_prompt_package(package: PromptPackage) -> None` — internal invariant self-check; raises
  `PromptConstructionInternalError` (one of the five named codes in Validation §3) on violation.
- `construct_prompt(context_package: ContextPackage, template_version: Optional[str] = None,
  prompt_budget_tokens: Optional[int] = None) -> PromptPackage` — the sole public entrypoint;
  orchestrates Pipeline [1]–[10]; never reads or writes any artifact except the three static
  template files for the resolved `template_version`, and never touches the manifest.

## Constants

```python
PROMPT_PIPELINE_VERSION = "1.0.0"
DEFAULT_TEMPLATE_VERSION = "1.0.0"
DEFAULT_PROMPT_BUDGET_TOKENS = 8000
MAX_PROMPT_BUDGET_TOKENS = 100000    # hard ceiling — guards a pathological request, never silently raised
CHARS_PER_TOKEN_ESTIMATE = 4.0       # fixed, documented English-text approximation; Stage 12's own
                                      # copy of Stage 11's identical constant (Design Decisions #5)
BLOCK_SEPARATOR = "\n\n---\n\n"      # fixed separator joining rendered context blocks
SYSTEM_USER_SEPARATOR = "\n\n"       # fixed separator joining system_prompt and user_prompt into
                                      # assembled_prompt
PROMPT_TEMPLATES_DIR = "config/prompt_templates"
```

## Known Limitations

- The token estimate is the same fixed char-ratio approximation Stage 11 uses, now applied to the
  fully-templated string — can meaningfully over/under-estimate actual usage for any specific
  downstream model; revisit once a model/tokenizer is actually selected (the same gap Stage 11
  already inherited from Stage 7, now inherited one stage further downstream).
- Prompt injection embedded in corpus text is not defended against by this stage — see Security
  Considerations; establishing any defense is explicitly a Stage 13+ or model-level concern.
- An oversized prompt is flagged, never corrected — Stage 12 cannot drop or truncate a
  `ContextBlock` (chunk atomicity and the read-only guarantee both forbid it), so resolving a budget
  violation requires either a smaller `context_budget_tokens` on a subsequent Stage 11 call, or a
  Stage 13+ decision (a larger-context model, or rejecting the request).
- Template files are static and hand-authored; this design does not validate that a template
  actually contains the `{{query}}`/`{{context_text}}` placeholders it needs — a template missing a
  placeholder silently renders without that content substituted in (documented, not structurally
  prevented).
- Any cross-index score-comparability limitation already accepted by Stage 10, and passed through
  unchanged by Stage 11, is invisible at this stage — Stage 12 renders whatever block order it
  receives without judging how that order was produced.

## Accepted Tradeoffs

- **Plain `{{name}}` string substitution, not a templating engine.** Avoids a new dependency, keeps
  rendering fully deterministic and auditable; accepts no conditionals/loops in templates as a v1
  scope limit.
- **No persisted `PromptPackage` artifact.** Matches Stage 10 and Stage 11's own precedent — no
  audit trail exists unless a caller persists it independently.
- **Budget enforcement is observe-only, never corrective.** Simpler and strictly safer — never
  silently drops content a caller might have needed — at the cost of not being able to "fix" an
  oversized prompt itself.
- **The system prompt is static per `template_version`, never dynamically composed.** A reasonable
  v1 scope; a future stage needing a dynamic system prompt (e.g. per-corpus instructions) would
  require a new `template_version` directory, not a redesign of this stage.
- **`findings` deliberately renamed from the originating request's `warnings`.** Kept symmetric with
  Stage 10/11's own field naming rather than introducing a synonymous-but-differently-named field —
  accepted as an intentional, documented deviation from the literal request wording (Design Decision
  #8).

## Validation Requirements

What must be true, grouped by concern — an eventual test suite owns exact test names/counts, not
this document.

- A malformed `ContextPackage` is rejected deterministically, every time, without producing any
  `PromptPackage`.
- An unresolvable `template_version` (missing directory or missing file), or a
  `template_metadata.json` whose declared `template_version` disagrees with the directory used to
  resolve it, is rejected deterministically, every time, without producing any `PromptPackage`.
- An unrecognized `{{...}}` sequence in a template, or an omitted `{{query}}`/`{{context_text}}`
  placeholder, never raises and never produces a finding — literal-text passthrough, every time.
- `context_text`'s block order is always identical to `ContextPackage.context_blocks`'s own order —
  never independently sorted.
- No chunk's `text` is ever truncated, modified, or re-normalized when inserted into `context_text` —
  byte-identical to its source `ContextBlock.text`.
- `assembled_prompt` always equals exactly `system_prompt + SYSTEM_USER_SEPARATOR + user_prompt`;
  `context_text`, when non-empty, always appears verbatim as a substring of `user_prompt`.
- `estimated_prompt_tokens` always equals `estimate_prompt_tokens(assembled_prompt)`;
  `prompt_utilization` always equals `estimated_prompt_tokens / prompt_budget_tokens` exactly, with
  no clamping.
- `ContextPackage.status == "FAIL"` always produces `PromptPackage.status == "FAIL"` with
  `context_text == ""`, while `system_prompt` and `user_prompt` are still both fully rendered
  (non-empty, template-derived) — never an empty or null prompt pair.
- Every one of the five internal invariant codes (`ASSEMBLED_PROMPT_MISMATCH`,
  `CONTEXT_TEXT_NOT_SUBSTITUTED`, `TOKEN_ESTIMATE_MISMATCH`, `PROMPT_UTILIZATION_MISMATCH`,
  `CONTEXT_PACKAGE_ID_MISMATCH`) fires under its documented condition and only that condition.
- `PROMPT_BUDGET_EXCEEDED` fires if and only if `estimated_prompt_tokens > prompt_budget_tokens`;
  `PROMPT_TEMPLATE_OVERHEAD_EXCEEDS_BUDGET` fires if and only if the base-overhead-only estimate
  (empty `context_text`) already exceeds `prompt_budget_tokens`; neither ever alters `status`.
- Determinism: identical `(ContextPackage, template_version, prompt_budget_tokens)`, against
  unchanged on-disk template files, produces a byte-identical `PromptPackage` (`constructed_at`
  excluded), across repeated calls and process restarts.
- Immutability: the input `ContextPackage` object, and every on-disk template file read, are never
  mutated by any Stage 12 function.

## Real Corpus Verification

Against the real, current corpus (via a real `ContextPackage` produced by Stage 11 from a real Stage
10 `RetrievalResult`): a representative multi-block `ContextPackage` renders a `context_text` whose
block order and content are confirmed byte-identical to the source `context_blocks`; a deliberately
small `prompt_budget_tokens` (smaller than the assembled prompt's own real token estimate) produces
`PROMPT_BUDGET_EXCEEDED` with `prompt_utilization > 1.0`, while the returned `PromptPackage` is still
fully populated and well-formed; a generously large budget produces no budget finding at all; a
`template_version` pointing at a real, checked-in template pair renders both `system_prompt` and
`user_prompt` with the expected placeholders replaced, spot-checked by eye against the raw template
files; two separate `ContextPackage`s built from the same underlying query and index, but through two
independent Stage 10 + Stage 11 calls, produce two independently-computed but internally consistent
`PromptPackage`s.

**Determinism, explicitly:** the same real `ContextPackage`, run through `construct_prompt()` twice
with identical `template_version` and `prompt_budget_tokens`, produces two byte-identical
`PromptPackage`s (`constructed_at` excluded) — checked directly, not only implied, including
`prompt_package_id`, `context_text`, `user_prompt`, and `assembled_prompt`.

Immutability: the input `ContextPackage` object, every real upstream artifact (`manifest.json`, every
`chunks.json`, `embeddings.parquet`, `metadata.json`, everything under `vector_index/`), and every
on-disk prompt template file are confirmed byte-identical before and after the call.

## Future Stage Boundaries

Stage 13+ (not designed here) owns everything Stage 12 deliberately excludes: LLM invocation, answer
generation, response streaming, tool calling, citation formatting, retrieval-quality or answer-quality
evaluation, conversation memory, hallucination detection, and any network-facing API or UI. Stage 12
hands a `PromptPackage` back in memory; how a caller invokes a model with `assembled_prompt` (or with
`system_prompt`/`user_prompt` as separate messages in a structured API call), streams a response,
formats a citation, or evaluates the answer is entirely out of this design's scope.
