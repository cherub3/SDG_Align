"""Planner arm (Phase 3 step 5): the SAME 52 TEST items and the same pipeline as tools/eval_answers.py, but each request goes through
the agent planner (plan -> QUERY_PIPELINE step(s) -> COMPLETE), exactly as the served backend does (runtime_orchestration.execute_request,
MAX_LLM_CALLS_PER_REQUEST=6 enforced, planner + answer calls both counted).

  python tools/eval_planner.py --split test --template 2.0.0 --label test_planner_v20 --max-requests 52 --expect-prompt-sha256 <sha>
  python tools/eval_planner.py --split dev --template 2.0.0 --label offline_planner --max-requests 14 --fake      (no network)

Safety: stops on the first 429 / LLM error, and before a request when fewer than 6 calls remain under the guard cap
(cap = 450 minus the calls already logged today in eval/results/quota_ledger.json), so a request is never cut in half.
Rows are appended as they finish; re-running a label resumes. Every live call is counted in the ledger at the end of the run.
"""
import argparse
import datetime as _dt
import glob
import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import answer_checks as ac  # noqa: E402
import eval_answers as ea  # noqa: E402
import freeze_gold as fg  # noqa: E402
import gold_common as gc  # noqa: E402

DAY_CAP = 450
PER_REQUEST_MAX = 6
LEDGER = os.path.join(ea.RESULTS, "quota_ledger.json")


def pacific_today():
    from scripts.quota_guard import pacific_day
    return pacific_day()


def ledger_used_today():
    if not os.path.exists(LEDGER):
        return 0, pacific_today()
    d = json.load(open(LEDGER, encoding="utf-8"))
    today = pacific_today()
    return sum(e["calls"] for e in d["entries"] if e["day_pacific"] == today), today


def ledger_add(label, calls, note=""):
    d = json.load(open(LEDGER, encoding="utf-8")) if os.path.exists(LEDGER) else {"note": "Gemini calls made by the eval runners, by Pacific day (quota resets at midnight Pacific).", "entries": []}
    d["entries"].append({"day_pacific": pacific_today(), "label": label, "calls": calls, "note": note})
    json.dump(d, open(LEDGER, "w", encoding="utf-8", newline="\n"), indent=1)


def build_planner_runner(template, fake, guard_cap):
    os.chdir(REPO)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from scripts.cache_adapter import InMemoryCacheAdapter
    from scripts.call_budget import BudgetedLLMAdapter, BudgetedPlannerAdapter
    from scripts.composition_root import _discover_index_fingerprints
    from scripts.embedding_provider_local import LocalEmbeddingAdapter
    from scripts.model_config import default_gemini_model
    from scripts.pipeline_deps_factory import build_pipeline_deps
    from scripts.quota_guard import GuardedLLMAdapter, GuardedPlannerAdapter, QuotaGuard
    from scripts.runtime_orchestration import execute_request
    from scripts.stage13_llm_execution import LLMAdapter, LLMQuotaExhaustedError, RawLLMResult
    from scripts.stage18_api_response_serving import handle_request
    from scripts.stage20_tool_function_calling import execute_tool
    from scripts.stage21_agent_planning import AgentDependencies, PlannerInvocationError, PlannerLLMAdapter
    from scripts.tool_registry import CallableToolAdapter, InMemoryToolRegistry

    model = default_gemini_model()
    emb = LocalEmbeddingAdapter()
    fps = _discover_index_fingerprints(emb)
    if len(fps) != 1:
        raise SystemExit(f"expected exactly one matching index, found {fps}")
    spans = {}
    for doc in os.listdir(gc.CHUNKS):
        p = os.path.join(gc.CHUNKS, doc, "chunks.json")
        if os.path.exists(p):
            for c in json.load(open(p, encoding="utf-8"))["chunks"]:
                spans[c["chunk_id"]] = (c["doc_id"], c["char_start"], c["char_end"])

    class Log:
        def __init__(self):
            self.reset()

        def reset(self):
            self.answer_calls, self.planner_calls, self.prompts, self.ptok, self.ctok, self.error = 0, 0, [], 0, 0, None
            self.planner_queries, self.answer_ms, self.planner_ms = [], 0, 0
    log = Log()

    class AnswerRec(LLMAdapter):
        provider_name = "recorder"

        def __init__(self, inner):
            self.inner = inner

        @property
        def model_version_reported(self):
            return getattr(self.inner, "model_version_reported", None)

        def invoke(self, system_prompt, user_prompt, config):
            log.answer_calls += 1
            log.prompts.append(user_prompt)
            t = time.time()
            try:
                r = self.inner.invoke(system_prompt, user_prompt, config)
            except Exception as e:                       # noqa: BLE001
                log.error = log.error or e
                raise
            log.answer_ms += int((time.time() - t) * 1000)
            log.ptok += r.prompt_tokens or 0
            log.ctok += r.completion_tokens or 0
            return r

    class PlannerRec(PlannerLLMAdapter):
        def __init__(self, inner):
            self.inner = inner

        def plan(self, planner_prompt, config):
            log.planner_calls += 1
            t = time.time()
            try:
                d = self.inner.plan(planner_prompt, config)
            except Exception as e:                       # noqa: BLE001
                log.error = log.error or e
                raise
            log.planner_ms += int((time.time() - t) * 1000)
            ns = d.get("next_step") if isinstance(d, dict) else None
            if isinstance(ns, dict) and ns.get("step_type") == "QUERY_PIPELINE":
                log.planner_queries.append((ns.get("step_input") or {}).get("query"))
            return d

    if fake:
        class ScriptedAnswer(LLMAdapter):
            provider_name, model_version_reported = "scripted-offline", "none"

            def invoke(self, system_prompt, user_prompt, config):
                q = re.search(r"Question:\n(.*?)\n\n<context>", user_prompt, re.S).group(1)
                ctx = user_prompt.split("<context>", 1)[1]
                caps = [w for w in re.findall(r"\b[A-Z][a-z]{3,}\b", q) if w not in ("What", "Which", "How", "Where", "Under", "Rank", "According")]
                text = "NOT_IN_CONTEXT" if (caps and not any(w.lower() in ctx.lower() for w in caps)) or "Chunk ID:" not in ctx else ctx.split("Chunk ID:")[1].split("\n\n", 1)[1][:200].strip()
                return RawLLMResult(text, "complete", len(user_prompt) // 4, len(text) // 4, len(user_prompt) // 4 + len(text) // 4, "fake")

        class ScriptedPlanner(PlannerLLMAdapter):
            def plan(self, planner_prompt, config):
                ctx = json.loads(planner_prompt)
                if not ctx["executed_steps"]:
                    return {"decision": "EXECUTE_STEP", "next_step": {"step_type": "QUERY_PIPELINE", "step_input": {"query": ctx["query"]}}}
                return {"decision": "COMPLETE", "final_answer_step_index": 0}
        inner_a, inner_p, guard = ScriptedAnswer(), ScriptedPlanner(), QuotaGuard(cap=10_000, pace=0)
    else:
        from scripts.llm_provider_gemini import gemini_llm_factory
        from scripts.planner_provider_gemini import gemini_planner_factory
        from tools_env import gemini_key
        key = gemini_key()
        if not key:
            raise SystemExit("GEMINI_API_KEY not set in the environment or .env; no call made.")
        st = {"seam": "LLM_PROVIDER", "provider_name": "gemini", "credential_ref": "", "extra": {}}
        inner_a = gemini_llm_factory(st, key)
        inner_p = gemini_planner_factory({**st, "seam": "PLANNER_LLM_PROVIDER"}, key)
        guard = QuotaGuard(cap=guard_cap, pace=ea.PACE_RPM)
    answer = BudgetedLLMAdapter(GuardedLLMAdapter(AnswerRec(inner_a), guard))
    planner = BudgetedPlannerAdapter(GuardedPlannerAdapter(PlannerRec(inner_p), guard))
    pipe = build_pipeline_deps(answer, emb, InMemoryCacheAdapter(), model)

    def _handle(request, deps):
        if not request.get("index_fingerprints"):
            request = {**request, "index_fingerprints": list(fps)}
        return handle_request(request, deps)

    def _no_conv(*a, **k):
        raise RuntimeError("conversation memory is not used in this evaluation")
    agent = AgentDependencies(handle_request=_handle, select_memory=_no_conv, append_turn=_no_conv, get_conversation=_no_conv,
                              execute_tool=execute_tool, tool_registry=InMemoryToolRegistry(), tool_adapter=CallableToolAdapter({}),
                              planner_llm_adapter=planner, pipeline_deps=pipe, default_planner_model_name=model)
    app = {"agent_dependencies": agent}

    def ask(it):
        if guard.cap - guard.used < PER_REQUEST_MAX:
            raise ea.StopRun(f"BUDGET_WOULD_EXCEED before {it['qid']}: guard used {guard.used}/{guard.cap}, a request can need {PER_REQUEST_MAX}; checkpointed")
        log.reset()
        req = {"query": it["question"], "pipeline_options": {"template_version": template, "temperature": 0.0, "max_output_tokens": ea.MAX_OUTPUT_TOKENS,
                                                             "max_retry_attempts": 1, "timeout_seconds": 90}}
        t0 = time.time()
        res = execute_request(app, req)
        wall = int((time.time() - t0) * 1000)
        if isinstance(log.error, LLMQuotaExhaustedError) or (isinstance(log.error, PlannerInvocationError) and log.error.code == "QUOTA_EXHAUSTED") or guard.tripped:
            raise ea.StopRun(f"429 / quota at {it['qid']} (guard used {guard.used}/{guard.cap}); this request is NOT recorded")
        fr = res.get("final_response")
        text = fr["answer"]["response_text"] if fr else ""
        ctx_ids = [c for p in log.prompts for c in ea._CHUNK_ID.findall(p)]
        row = {"qid": it["qid"], "type": it["type"], "kind": it.get("kind"), "question": it["question"], "response_text": text,
               "agent_status": res["status"], "plan_status": res["plan"]["plan_status"], "n_steps": res["plan"]["total_step_count"],
               "step_types": [s["step_type"] for s in res["plan"]["steps"]], "step_statuses": [s["step_status"] for s in res["plan"]["steps"]],
               "planner_queries": log.planner_queries, "query_rewritten": any(q and q.strip() != it["question"].strip() for q in log.planner_queries),
               "no_final_response": fr is None, "finding_codes": sorted({f["code"] for f in res["findings"]}),
               "api_status": fr["status"] if fr else None, "api_decision": fr["answer"]["decision"] if fr else None,
               "planner_calls": log.planner_calls, "answer_calls": log.answer_calls, "total_calls": log.planner_calls + log.answer_calls,
               "latency_ms": wall, "planner_ms": log.planner_ms, "answer_ms": log.answer_ms,
               "prompt_tokens": log.ptok, "completion_tokens": log.ctok, "total_tokens": log.ptok + log.ctok,
               "groundedness_score": fr["groundedness"]["groundedness_score"] if fr else None, "context_chunk_ids": ctx_ids, "guard_used": guard.used}
        if it["type"] != "unanswerable":
            gold = [(e["doc_id"], e["clean_start"], e["clean_end"]) for e in it["evidence"]]
            row["gold_in_context"] = any(c in spans and any(spans[c][0] == d and gc.is_hit(spans[c][1], spans[c][2], s, e) for d, s, e in gold) for c in ctx_ids)
        return row
    return ask, guard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--max-requests", type=int, required=True)
    ap.add_argument("--expect-prompt-sha256")
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    bad = fg.check_frozen()
    if bad:
        raise SystemExit("REFUSING TO RUN, frozen inputs differ: " + "; ".join(bad))
    sha = ea.prompt_sha256(a.template)
    if a.expect_prompt_sha256 and a.expect_prompt_sha256 != sha:
        raise SystemExit(f"REFUSING TO RUN: prompt template {a.template} hash {sha} != expected {a.expect_prompt_sha256}")
    if a.split == "test" and not a.expect_prompt_sha256 and not a.fake:
        raise SystemExit("REFUSING TO RUN on TEST without --expect-prompt-sha256.")
    used, day = ledger_used_today()
    cap = max(0, DAY_CAP - used)
    items = ea.load_items(a.split)
    by_qid = {i["qid"]: i for i in items}
    out = os.path.join(ea.RESULTS, f"{a.label}.jsonl")
    ask, guard = build_planner_runner(a.template, a.fake, cap)
    info = ea.run_items(items, ask, out, a.max_requests)
    if not a.fake:
        ledger_add(a.label, guard.used, f"planner arm, template {a.template}, {info['calls_this_run']} requests started")
    rows = ea.read_rows(out)
    summ, _ = ea.summarize_rows(rows, by_qid)
    tc = sorted(r["total_calls"] for r in rows)
    lat = sorted(r["latency_ms"] for r in rows)
    pct = lambda v, q: v[min(len(v) - 1, int(q * len(v)))] if v else None  # noqa: E731
    summ["calls_per_request"] = {"mean": round(sum(tc) / len(tc), 2) if tc else None, "p50": pct(tc, .5), "max": tc[-1] if tc else None, "total": sum(tc)}
    summ["latency_ms_per_request"] = {"p50": pct(lat, .5), "p95": pct(lat, .95), "max": lat[-1] if lat else None}
    summ["planner"] = {"no_final_response": sum(r["no_final_response"] for r in rows), "query_rewritten": sum(r["query_rewritten"] for r in rows),
                       "mean_steps": round(sum(r["n_steps"] for r in rows) / len(rows), 2) if rows else None,
                       "more_than_one_query_step": sum(r["step_types"].count("QUERY_PIPELINE") > 1 for r in rows)}
    summary = {"label": a.label, "split": a.split, "template_version": a.template, "prompt_sha256": sha, "fake_model": a.fake, "arm": "planner",
               "items_in_split": len(items), "items_done": len(rows), **info, "guard_cap_this_run": cap, "guard_used_this_run": guard.used,
               "ledger_used_before_run": used, "day_pacific": day, "frozen_file_sha256": fg.sha_file(fg.FROZEN),
               "summary": summ, "keep_rule": ac.keep_rule(summ) if len(rows) == len(items) else "not evaluated (run incomplete)"}
    json.dump(summary, open(os.path.join(ea.RESULTS, f"{a.label}_summary.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps({k: summary[k] for k in ("label", "items_done", "calls_this_run", "stopped", "guard_used_this_run", "keep_rule")}, indent=1))
    print(json.dumps({k: summ[k] for k in ("refusal_rate_unanswerable", "false_refusal_rate_answerable", "calls_per_request", "latency_ms_per_request", "planner")}, indent=1))


if __name__ == "__main__":
    main()
