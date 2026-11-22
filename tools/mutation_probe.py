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
]


def run_one(mid, desc, rel, old, new):
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"mut_{mid}_"))
    try:
        for d in ("scripts", "src", "tests", "config"):
            shutil.copytree(ROOT / d, work / d, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "pyproject.toml", work / "pyproject.toml")
        target = work / rel
        text = target.read_text(encoding="utf-8")
        if text.count(old) != 1:
            return {"id": mid, "description": desc, "file": rel, "result": f"NOT_APPLIED (matches={text.count(old)})"}
        target.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
                              cwd=work, capture_output=True, text=True)
        out = proc.stdout.strip().splitlines()
        return {"id": mid, "description": desc, "file": rel,
                "result": "KILLED" if proc.returncode != 0 else "SURVIVED",
                "pytest": out[-1] if out else proc.stderr[-200:]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    wanted = set(argv)
    results = []
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
