# End-to-End Example — Stage 0 → Stage 21

This document walks one input through the entire delivered pipeline. It uses the **existing corpus**
under `data/proposals/` and the **existing test fixtures** as the canonical, runnable wiring examples
— no new functionality is introduced here.

```
 PDF proposal
     │
     ▼   Ingestion (runnable CLIs, Stages 0–9)
 register → integrity → extract → detect → clean → structure → validate → chunk → embed → index
     │
     ▼   Query-time RAG (library, Stages 10–18)  ── handle_request()
 retrieve → assemble context → build prompt → cached LLM → citations → groundedness → quality → APIResponse
     │
     ▼   Agent layer (library, Stages 19–21)     ── plan_and_execute()
 conversation memory (19) · tool calling (20) · planner (21) → AgentResult
```

---

## Part A — Ingestion (Stages 0–9), on the real corpus

The repository ships a real 13-document corpus under
[`data/proposals/raw/`](../data/proposals/raw/) (climate, health, poverty, water, biodiversity,
education, responsible-consumption proposals).

Run the ingestion stages in order from the repository root:

```bash
python scripts/stage0_register.py          # writes data/proposals/manifest.json
python scripts/stage1_integrity.py
python scripts/stage2_extraction.py        # data/proposals/extracted/<doc_id>/raw_extraction.json
python scripts/stage3_detection.py         # quarantines scanned/image-only PDFs
python scripts/stage4_cleaning.py          # .../clean_text.json
python scripts/stage5_structure.py         # adds section_tree, headings to clean_text.json
python scripts/stage6_validation.py        # .../metadata.json + validation report
python scripts/stage7_chunking.py          # data/proposals/chunks/<doc_id>/chunks.json
python scripts/stage8_embedding_generation.py   # data/proposals/embeddings/<doc_id>/embeddings.parquet
python scripts/stage9_vector_indexing.py   # data/proposals/vector_index/<fingerprint>/index.bin
```

**Observable result** (already present in the repo from a prior run, so you can inspect it without
re-running):

- `data/proposals/manifest.json` — one `ManifestRecord` per document.
- Per-document artifacts keyed by a content-hash `doc_id`, e.g.
  `doc_e75ba796c7d58cc1c27571b733bbe09cfc2afbfbce2271dd66ffbe2ca179500f/` with
  `raw_extraction.json`, `clean_text.json`, `metadata.json`, and `chunks.json`.
- A faiss index under `data/proposals/vector_index/477879bb…/` (`index.bin`, `id_map.parquet`,
  `index_metadata.json`).
- As documented in [`VERIFICATION_LOG.md`](VERIFICATION_LOG.md): of the 13 documents, 7 are genuinely
  scanned/image-only and are correctly quarantined at Stage 3; the remaining 6 flow through to chunks,
  embeddings, and the index.

The `vector_index_run1/` and `vector_index_run2/` directories are prior runs kept to demonstrate the
**byte-identical determinism** guarantee — indexing the same embeddings produces the same index
fingerprint.

## Part B — Query-time RAG (Stages 10–18) via `handle_request()`

Stage 18 orchestrates the frozen chain 10 → 11 → 12 → 17 → 14 → 15 → 16 and returns a single
`APIResponse`. It is a library function:

```python
from scripts.stage18_api_response_serving import handle_request, PipelineDependencies

# `deps` bundles the concrete adapters (LLMAdapter, CacheAdapter, index access, etc.).
# The canonical, runnable wiring is in tests/test_stage18_api_response_serving.py
# (StubLLMAdapter + InMemoryCacheAdapter) — those in-memory adapters need no credentials.
response = handle_request(
    {
        "query": "What are the SDG financing gaps in the proposals?",
        "index_fingerprints": ["477879bbe2e14b2497203048cd992057509c05cd2188c0bd5f971f6ade8cdc17"],
        "filters": {},
        "pipeline_options": {},
    },
    deps,  # PipelineDependencies
)

# response is an APIResponse dict: status (SUCCESS/PARTIAL_SUCCESS/…), answer text,
# citations, groundedness classification, quality metrics, cache provenance,
# the upstream identity-chain ids, and all findings.
```

The **executable reference** for this call is
[`tests/test_stage18_api_response_serving.py`](../tests/test_stage18_api_response_serving.py), which
wires stub adapters and asserts the full response shape end to end.

## Part C — Agent layer (Stages 19–21) via `plan_and_execute()`

Stage 21 is the top-level planner. It coordinates Stage 18 (query pipeline), Stage 19 (conversation
memory), and Stage 20 (tools) through an `AgentDependencies` bundle:

```python
from scripts.stage21_agent_planning import plan_and_execute, AgentDependencies

result = plan_and_execute(
    {"query": "Summarise the financing gaps and check them with the calculator tool."},
    agent_deps,  # AgentDependencies: handle_request, select_memory, append_turn,
                 # execute_tool, tool_registry, planner_llm_adapter, …
)

# result is an AgentResult dict:
#   status        → PASS | PARTIAL | FAIL
#   plan          → the executed AgentPlan (ordered PlanSteps, deterministic ids)
#   final_response→ the APIResponse from the terminal QUERY_PIPELINE step
#   tool_results  → embedded ToolExecutionRecords
#   findings      → Stage 21's own findings
#   upstream_findings → all downstream findings, aggregated unchanged
```

The **executable reference** is
[`tests/test_stage21_agent_planning.py`](../tests/test_stage21_agent_planning.py) — in particular
`test_plan_and_execute_success`, which drives a plan of a tool step followed by a query-pipeline step
and asserts the aggregated `AgentResult`.

## Final output

The pipeline's terminal artifact is an **`AgentResult`** (or, for a single non-conversational turn,
an **`APIResponse`** from Stage 18 directly). Both are deterministic, transport-agnostic in-memory
objects with stable content-hash identities and a complete, auditable trail of every stage that
contributed — exactly the substrate the goal-level SDG-alignment layer is designed to build on.

## Reproducing the whole thing

```bash
pip install -r requirements.txt
# (optional) re-run ingestion — Stages 0–9 above
python -m pytest        # exercises Stages 0–21 end to end via their test suites → 481 passed
```
