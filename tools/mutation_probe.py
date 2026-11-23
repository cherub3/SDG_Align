"""Cheap mutation probe: does the test suite notice when a critical line is deliberately broken?

For each mutation below the probe copies scripts/, src/, tests/ and config/ into a temporary
directory, applies exactly ONE textual change to the COPY, runs the whole suite there and records
KILLED (tests failed, good) or SURVIVED (tests still pass, i.e. a gap). The real source tree is
never modified.

Usage (from the repo root):
    python tools/mutation_probe.py              # all mutations
    python tools/mutation_probe.py M1 M5        # selected ones
Results are written to reports/mutation_results.json (full run) or reports/mutation_results_<ids>.json.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

# (id, description, file, exact text to replace (must occur once), replacement)
MUTATIONS = [
    ("M1", "chunk split threshold halved", "scripts/stage7_chunking.py",
     "        if len(text) <= MAX_CHUNK_CHARS:", "        if len(text) <= MAX_CHUNK_CHARS // 2:"),
    ("M2", "forward merge ignores MAX_CHUNK_CHARS", "scripts/stage7_chunking.py",
     "        if combined_len <= MAX_CHUNK_CHARS and not _crosses_appendix_boundary(a, b):",
     "        if True and not _crosses_appendix_boundary(a, b):"),
    ("M13", "backward merge ignores MAX_CHUNK_CHARS", "scripts/stage7_chunking.py",
     "            if combined_len <= MAX_CHUNK_CHARS and eligible and",
     "            if True and eligible and"),
    ("M3", "retrieval top-k off by one", "scripts/stage10_retrieval.py",
     "    truncated = surviving[:top_k]", "    truncated = surviving[:top_k + 1]"),
    ("M4", "retrieval sorts worst-first", "scripts/stage10_retrieval.py",
     '    surviving.sort(key=lambda x: x["score"], reverse=True)', '    surviving.sort(key=lambda x: x["score"])'),
    ("M5", "retrieval category filter disabled", "scripts/stage10_retrieval.py",
     '        if "category" in filters and chunk.get("category") != filters["category"]:', "        if False:"),
    ("M6", "citation threshold >= -> > 0", "scripts/stage14_citation_extraction.py",
     "        if score >= citation_match_threshold:", "        if score > 0:"),
    ("M7", "groundedness threshold ignored", "scripts/stage15_groundedness_validation.py",
     "    if best_score >= groundedness_threshold:", "    if best_score >= 0.0:"),
    ("M8", "cache key drops model_name", "scripts/stage17_response_caching.py",
     '    hash_input = {\n        "prompt_package_id": prompt_package_id,\n        "model_name": model_name,',
     '    hash_input = {\n        "prompt_package_id": prompt_package_id,\n        "model_name": "x",'),
    ("M9", "planner step limit off by one", "scripts/stage21_agent_planning.py",
     '        if planner_context["step_count"] >= config["max_plan_steps"]:',
     '        if planner_context["step_count"] > config["max_plan_steps"]:'),
    ("M10", "context budget never cuts off", "scripts/stage11_context_assembly.py",
     '            if total + block["estimated_tokens"] > context_budget_tokens:',
     '            if total + block["estimated_tokens"] > context_budget_tokens * 2:'),
    ("M11", "tool schema: integer maximum not enforced", "scripts/stage20_tool_function_calling.py",
     "                    if max_val is not None and value > max_val:", "                    if False:"),
    ("M12", "tool schema: required arguments not enforced", "scripts/stage20_tool_function_calling.py",
     "            if req not in arguments:", "            if False:"),
    # --- Phase 1 rules ---
    ("M14", "exact-duplicate chunk drop disabled", "scripts/stage7_chunking.py",
     "        if key and key in seen:", "        if False:"),
    ("M15", "heading-only chunk drop disabled", "scripts/stage7_chunking.py",
     "        if _span_len(s) < MIN_CHUNK_CHARS and _is_markdown_heading_only(text):", "        if False:"),
    ("M16", "split no longer prefers sentence ends", "scripts/stage7_chunking.py",
     "_ends_sentence(text[max(0, p - 12):p])", "False"),
    ("M17", "repeated section ids not disambiguated", "scripts/stage5_structure.py",
     "        if section_id in used_ids:", "        if False:"),
    ("M18", "inline HTML tags (<mark>, <u>) not stripped", "scripts/stage4_cleaning.py",
     '    text = _INLINE_TAG_RE.sub("", text)', "    pass"),
    ("M19", "table-of-contents removal disabled", "scripts/stage4_cleaning.py",
     "    if sum(leader) < MIN_TOC_LEADER_LINES:\n        return text", "    if True:\n        return text"),
    ("M20", "stage 6 failure code reverts to FATAL_UNREADABLE", "scripts/stage6_validation.py",
     "            record.error_code = ERROR_FAILED_VALIDATION", '            record.error_code = "FATAL_UNREADABLE"'),
    ("M21", "local embedder no longer L2-normalises", "scripts/embedding_provider_local.py",
     "        vectors = vectors / norms", "        vectors = vectors"),
    # --- Phase 2 rules (hybrid, reranker, advisory, hit rule) ---
    ("M22", "RRF fusion ignores the BM25 weight", "scripts/hybrid_search.py",
     '(bm25_rank, p["w_bm25"])', "(bm25_rank, 1.0)"),
    ("M23", "RRF constant k ignored (hard-coded 60)", "scripts/hybrid_search.py",
     "fused = rrf_fuse([(dense_rank, p[\"w_dense\"]), (bm25_rank, p[\"w_bm25\"])], p[\"rrf_k\"],",
     "fused = rrf_fuse([(dense_rank, p[\"w_dense\"]), (bm25_rank, p[\"w_bm25\"])], 60,"),
    ("M24", "RRF depth cut removed", "scripts/hybrid_search.py",
     "        for r, cid in enumerate(ranked[:depth], 1):", "        for r, cid in enumerate(ranked, 1):"),
    ("M25", "BM25 idf loses its +1 (can go negative)", "scripts/hybrid_search.py",
     "math.log(1.0 + (n - f + 0.5) / (f + 0.5))", "math.log((n - f + 0.5) / (f + 0.5))"),
    ("M26", "BM25 length normalisation disabled (b=0)", "scripts/hybrid_search.py",
     "B = 0.75", "B = 0.0"),
    ("M27", "rerank N cut-off ignored (scores the whole pool)", "scripts/reranker.py",
     "    pool = [dict(r) for r in results[:n]]", "    pool = [dict(r) for r in results]"),
    ("M28", "reranker order reversed (worst first)", "scripts/reranker.py",
     '    pool.sort(key=lambda r: (-r["score"], r["chunk_id"]))', '    pool.sort(key=lambda r: (r["score"], r["chunk_id"]))'),
    ("M29", "reranking switched ON by default", "scripts/stage10_retrieval.py",
     '    rerank = request.get("rerank")  ', '    rerank = request.get("rerank", {"n": 20})  '),
    ("M30", "hybrid switched ON by default in retrieve()", "scripts/stage10_retrieval.py",
     '    hybrid = request.get("hybrid")  ', '    hybrid = request.get("hybrid", True)  '),
    ("M31", "advisory threshold changed", "scripts/confidence.py",
     "DEFAULT_THRESHOLD = 0.6604", "DEFAULT_THRESHOLD = 0.5"),
    ("M32", "advisory flag comparison flipped (<= instead of <)", "scripts/confidence.py",
     's is None or s < t', 's is None or s <= t'),
    ("M33", "advisory switched ON by default", "scripts/stage10_retrieval.py",
     'advisory = request.get("confidence_advisory")  ', 'advisory = request.get("confidence_advisory", True)  '),
    ("M34", "span-overlap hit rule: any overlap counts", "tools/gold_common.py",
     "    need = min(50, 0.5 * (gold_end - gold_start))", "    need = 1"),
    ("M35", "span-overlap hit rule: 50-char cap removed", "tools/gold_common.py",
     "    need = min(50, 0.5 * (gold_end - gold_start))", "    need = 0.5 * (gold_end - gold_start)"),
    ("M36", "served default flipped to dense", "scripts/pipeline_deps_factory.py",
     'DEFAULT_RETRIEVAL_MODE = "hybrid"', 'DEFAULT_RETRIEVAL_MODE = "dense"'),
    ("M37", "invalid RETRIEVAL_MODE silently accepted", "scripts/pipeline_deps_factory.py",
     "    if raw not in RETRIEVAL_MODES:", "    if False:"),
    ("M38", "served hybrid params changed (rrf_k 10 -> 60)", "scripts/pipeline_deps_factory.py",
     'SERVED_HYBRID_PARAMS = {"rrf_k": 10, "w_bm25": 2.0, "depth": 50}', 'SERVED_HYBRID_PARAMS = {"rrf_k": 60, "w_bm25": 2.0, "depth": 50}'),
    ("M39", "served path never injects hybrid", "scripts/pipeline_deps_factory.py",
     '        if retrieval_mode == "hybrid" and "hybrid" not in request:', "        if False:"),
    ("M40", "served path overrides a request's own hybrid setting", "scripts/pipeline_deps_factory.py",
     '        if retrieval_mode == "hybrid" and "hybrid" not in request:', '        if retrieval_mode == "hybrid":'),
    # --- Phase 2.5 hardening ---
    ("M41", "missing-index check removed (server starts with no index)", "scripts/startup_checks.py",
     "    if not found:", "    if False:"),
    ("M42", "embedding-model mismatch check removed", "scripts/startup_checks.py",
     "    if not matching:", "    if False:"),
    ("M43", "empty-manifest check removed", "scripts/startup_checks.py",
     "    if not servable:", "    if False:"),
    ("M44", "empty-chunks check removed", "scripts/startup_checks.py",
     "        if n == 0:", "        if False:"),
    ("M45", "server startup skips the data checks", "scripts/backend_server.py",
     "    summary = verify_serving_data(instance.get(\"embedding_adapter\"))", "    summary = {}"),
    ("M46", "server startup skips the embedder warm-up (missing model found only on first query)", "scripts/backend_server.py",
     "    if callable(warm_up):\n        warm_up()", "    if False:\n        warm_up()"),
    ("M47", "RETRIEVAL_MODE validation skipped in compose_application", "scripts/composition_root.py",
     "    resolve_retrieval_mode(raw.get(\"values\", {}))", "    pass"),
    ("M48", "NETWORK_CALLS_PERMITTED default flipped to true", "scripts/phase1_1_configuration_layer.py",
     'values.get("NETWORK_CALLS_PERMITTED", "false")', 'values.get("NETWORK_CALLS_PERMITTED", "true")'),
    ("M49", "per-request LLM call cap ignored", "scripts/call_budget.py",
     "    if not budget.take():", "    if False:"),
    ("M50", "per-request LLM call cap default raised to 600", "scripts/call_budget.py",
     "DEFAULT_MAX_LLM_CALLS_PER_REQUEST = 6", "DEFAULT_MAX_LLM_CALLS_PER_REQUEST = 600"),
    ("M51", "invalid cap value means unlimited-ish (no fallback to default)", "scripts/call_budget.py",
     "    return value if value >= 1 else DEFAULT_MAX_LLM_CALLS_PER_REQUEST", "    return value if value >= 1 else 10 ** 6"),
    ("M52", "request budget not activated per request", "scripts/runtime_orchestration.py",
     "    with request_budget():", "    if True:"),
    ("M53", "local embedder: offline mode removed (downloads allowed by default)", "scripts/embedding_provider_local.py",
     "    offline = not _download_allowed()", "    offline = False"),
    ("M54", "local embedder: local_files_only ignored", "scripts/embedding_provider_local.py",
     "local_files_only=offline)", "local_files_only=False)"),
    ("M55", "index cache key ignores file changes (stale index served)", "scripts/stage10_retrieval.py",
     "            key = _file_key(path) + (metric,)", "            key = (str(path), metric)"),
    ("M56", "index cache never hits (reloads every query)", "scripts/stage10_retrieval.py",
     "            if hit is not None:", "            if False:"),
    ("M57", "index cache switched off by default", "scripts/stage10_retrieval.py",
     "INDEX_CACHE_ENABLED = True", "INDEX_CACHE_ENABLED = False"),
    ("M58", "scipy pin removed from requirements-dev.txt", "requirements-dev.txt",
     "scipy==1.18.1", "# scipy removed"),

    # --- Phase 3: served flags, abstention, quota guard, planner fix ---
    ("M59", "planner ON by default (flag default flipped)", "scripts/composition_root.py",
     'values.get("PLANNER_ENABLED", "false")', 'values.get("PLANNER_ENABLED", "true")'),
    ("M60", "PLANNER_ENABLED accepts any value as true", "scripts/composition_root.py",
     '.strip().lower() == "true" and wired_planner is not None', '.strip().lower() != "zzz" and wired_planner is not None'),
    ("M61", "direct planner never issues the query step", "scripts/direct_planner.py",
     "        if not executed:", "        if executed:"),
    ("M62", "direct planner completes with the wrong step index", "scripts/direct_planner.py",
     'len(executed) - 1}', 'len(executed)}'),
    ("M63", "/health reports not ok", "scripts/backend_server.py",
     'content={"status": "ok"}', 'content={"status": "down"}'),
    ("M64", "retrieval_only ignored by execute_request", "scripts/runtime_orchestration.py",
     '    if agent_request.get("retrieval_only") is True:', "    if False:"),
    ("M65", "retrieval_only reports a nonzero LLM call count", "scripts/runtime_orchestration.py",
     '"llm_calls": 0,', '"llm_calls": 1,'),
    ("M66", "HTTP route drops the retrieval_only flag", "scripts/backend_server.py",
     "    if payload.retrieval_only:", "    if False:"),
    ("M67", "served default template reverted to 1.0.0", "scripts/stage12_prompt_construction.py",
     'DEFAULT_TEMPLATE_VERSION = "2.1.0"', 'DEFAULT_TEMPLATE_VERSION = "1.0.0"'),
    ("M68", "abstention: bare NOT_IN_CONTEXT no longer recognised", "scripts/abstention.py",
     "    if core.upper() == SENTINEL:", "    if False:"),
    ("M69", "abstention: sentinel mixed with an answer not flagged", "scripts/abstention.py",
     "    if _SENTINEL_ANYWHERE.search(text):", "    if False:"),
    ("M70", "daily LLM call cap not enforced", "scripts/quota_guard.py",
     "            if self.used >= self.cap:", "            if False:"),
    ("M71", "429 breaker not honoured", "scripts/quota_guard.py",
     "            if self.tripped:", "            if False:"),
    ("M72", "a 429 does not open the breaker (answer adapter)", "scripts/quota_guard.py",
     "            return self._inner.invoke(system_prompt, user_prompt, config)\n        except LLMQuotaExhaustedError:\n            self.guard.trip()\n",
     "            return self._inner.invoke(system_prompt, user_prompt, config)\n        except LLMQuotaExhaustedError:\n            pass\n"),
    ("M73", "invalid COMPLETE finding renamed", "scripts/stage21_agent_planning.py",
     '"code": "PLANNER_COMPLETE_WITHOUT_ANSWER",', '"code": "OTHER",'),
    ("M74", "planner instruction loses the never-COMPLETE-first rule", "scripts/planner_provider_gemini.py",
     "Never return COMPLETE or FAIL while executed_steps is empty.", ""),
    ("M75", "retrieval_only searches no index", "scripts/composition_root.py",
     '"index_fingerprints": list(default_fingerprints)}', '"index_fingerprints": []}'),

]


def run_one(mid, desc, rel, old, new):
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"mut_{mid}_"))
    try:
        for d in ("scripts", "src", "tests", "config", "tools"):
            shutil.copytree(ROOT / d, work / d, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "eval", work / "eval", ignore=shutil.ignore_patterns("__pycache__", "results"))   # some tests read the gold files
        shutil.copy(ROOT / "pyproject.toml", work / "pyproject.toml")
        for req in ROOT.glob("requirements*.txt"):          # tests/test_requirements_declared.py reads them
            shutil.copy(req, work / req.name)
        target = work / rel
        text = target.read_text(encoding="utf-8")
        if text.count(old) != 1:
            return {"id": mid, "description": desc, "file": rel, "result": f"NOT_APPLIED (matches={text.count(old)})"}
        target.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", f"--basetemp={work / '.pt'}"],
                              cwd=work, capture_output=True, text=True)
        out = proc.stdout.strip().splitlines()
        last = out[-1] if out else proc.stderr[-200:]
        if proc.returncode == 0:
            result = "SURVIVED"
        elif " failed" in last:
            result = "KILLED"                       # a test assertion failed: the suite noticed the change
        else:
            result = "SETUP_ERROR"                  # collection/import error: says nothing about the tests
        return {"id": mid, "description": desc, "file": rel, "result": result, "pytest": last}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    wanted = set(argv)
    results = []
    control = run_one("C0", "no-op control (must survive)", "scripts/direct_planner.py", "        if not executed:", "        if not executed:  # control")
    print(control, flush=True)
    if control["result"] != "SURVIVED":
        print("CONTROL FAILED: the unmutated copy does not pass the suite, so KILLED means nothing. Fix the copy first.")
        return 2
    for m in MUTATIONS:
        if wanted and m[0] not in wanted:
            continue
        results.append(run_one(*m))
        print(results[-1], flush=True)
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    name = "mutation_results.json" if not wanted else "mutation_results_" + "_".join(sorted(wanted)) + ".json"
    (reports / name).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    killed = sum(r["result"] == "KILLED" for r in results)
    print(f"\nkilled {killed} / {len(results)}; survived: "
          f"{[r['id'] for r in results if r['result'] != 'KILLED']}")
    return 0 if all(r["result"] == "KILLED" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
