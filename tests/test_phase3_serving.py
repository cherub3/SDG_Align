"""Phase 3 step 6: planner off by default, /health, retrieval_only, served default template 2.1.0."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from scripts import backend_server
from scripts.stage21_agent_planning import AgentDependencies, plan_and_execute


def _deps(handle_request=None, planner=None, retrieve_only=None):
    return AgentDependencies(handle_request=handle_request, select_memory=None, append_turn=None, get_conversation=None,
                             execute_tool=None, tool_registry=None, tool_adapter=None, planner_llm_adapter=planner,
                             pipeline_deps=None, default_planner_model_name="m", retrieve_only=retrieve_only)


# ---- 1. planner flag -------------------------------------------------------------------------------------------
def test_direct_planner_issues_one_query_step_then_completes_without_any_llm():
    from scripts.direct_planner import DirectPlannerAdapter
    p = DirectPlannerAdapter()
    first = p.plan(json.dumps({"query": "What is X?", "executed_steps": [], "step_count": 0}), {})
    assert first["decision"] == "EXECUTE_STEP"
    assert first["next_step"] == {"step_type": "QUERY_PIPELINE", "step_input": {"query": "What is X?"}, "step_rationale": "direct"}
    second = p.plan(json.dumps({"query": "What is X?", "executed_steps": [{"step_index": 0}], "step_count": 1}), {})
    assert second["decision"] == "COMPLETE" and second["final_answer_step_index"] == 0


def test_direct_planner_end_to_end_returns_the_answer_with_zero_planner_calls():
    from scripts.direct_planner import DirectPlannerAdapter
    handled = []

    def handle(req, deps):
        handled.append(req["query"])
        return {"status": "SUCCESS", "findings": [], "answer": {"text": "A"}}
    res = plan_and_execute({"query": "Q?"}, _deps(handle_request=handle, planner=DirectPlannerAdapter()))
    assert handled == ["Q?"] and res["status"] == "PASS" and res["final_response"]["answer"]["text"] == "A"
    assert res["plan"]["total_step_count"] == 1


def test_choose_planner_adapter_defaults_to_direct_and_only_uses_llm_planner_when_enabled():
    from scripts.composition_root import choose_planner_adapter
    from scripts.direct_planner import DirectPlannerAdapter
    llm = object()
    assert isinstance(choose_planner_adapter({}, llm), DirectPlannerAdapter)
    assert isinstance(choose_planner_adapter({"PLANNER_ENABLED": "false"}, llm), DirectPlannerAdapter)
    assert isinstance(choose_planner_adapter({"PLANNER_ENABLED": "yes please"}, llm), DirectPlannerAdapter)
    assert choose_planner_adapter({"PLANNER_ENABLED": "true"}, llm) is llm
    assert isinstance(choose_planner_adapter({"PLANNER_ENABLED": "true"}, None), DirectPlannerAdapter)  # nothing wired: stay direct


# ---- 2. /health ------------------------------------------------------------------------------------------------
def _client():
    inst = {"agent_dependencies": _deps()}
    patcher = patch.object(backend_server, "_create_application_instance", return_value=inst)
    patcher.start()
    return TestClient(backend_server.app), patcher


def test_health_ok_without_calling_any_llm_or_planner():
    client, patcher = _client()
    try:
        with client:
            r = client.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"
    finally:
        patcher.stop()


# ---- 3. retrieval_only -----------------------------------------------------------------------------------------
def test_retrieval_only_returns_ranked_chunks_and_never_plans_or_calls_an_llm():
    from scripts.runtime_orchestration import execute_request
    seen = []
    ro = lambda req: (seen.append(req["query"]) or {"results": [{"rank": 0, "chunk_id": "c1", "text": "t"}], "status": "PASS"})
    planner = MagicMock()
    with patch("scripts.runtime_orchestration.plan_and_execute") as pe:
        out = execute_request({"agent_dependencies": _deps(planner=planner, retrieve_only=ro)}, {"query": "Q?", "retrieval_only": True})
    pe.assert_not_called()
    planner.plan.assert_not_called()
    assert seen == ["Q?"] and out["retrieval_only"] is True and out["chunks"][0]["chunk_id"] == "c1" and out["llm_calls"] == 0


def test_retrieval_only_flag_passes_through_the_http_route():
    client, patcher = _client()
    try:
        with patch.object(backend_server, "observe_request", return_value={"retrieval_only": True}) as obs, client:
            r = client.post("/run-query", json={"query": "Q?", "retrieval_only": True})
        assert r.status_code == 200
        assert obs.call_args[0][1]["retrieval_only"] is True
        with patch.object(backend_server, "observe_request", return_value={}) as obs, client:
            client.post("/run-query", json={"query": "Q?"})
        assert "retrieval_only" not in obs.call_args[0][1]
    finally:
        patcher.stop()


# ---- 4. served default template ---------------------------------------------------------------------------------
def test_served_default_template_is_2_1_0():
    from scripts.stage12_prompt_construction import DEFAULT_TEMPLATE_VERSION
    assert DEFAULT_TEMPLATE_VERSION == "2.1.0"


def test_compose_default_has_no_llm_planner_and_flag_true_wraps_it():
    from scripts.composition_root import compose_application
    from scripts.direct_planner import DirectPlannerAdapter
    from scripts.call_budget import BudgetedPlannerAdapter

    class _L:
        def invoke(self, *a, **k): raise AssertionError("no LLM call expected")

    class _P:
        def plan(self, *a, **k): raise AssertionError("no planner call expected")
    llm_reg = {"seam": "LLM_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _L()}
    pl_reg = {"seam": "PLANNER_LLM_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _P()}
    base = {"LLM_PROVIDER": "x", "PLANNER_LLM_PROVIDER": "x"}
    assert isinstance(compose_application([llm_reg, pl_reg], env=base)["agent_dependencies"].planner_llm_adapter, DirectPlannerAdapter)
    on = compose_application([llm_reg, pl_reg], env=dict(base, PLANNER_ENABLED="true"))
    assert isinstance(on["agent_dependencies"].planner_llm_adapter, BudgetedPlannerAdapter)


def test_served_to_ranked_maps_chunks_to_spans_and_counts_text_mismatches():
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools"))
    from eval_served import served_to_ranked
    local = {"c1": {"doc_id": "d", "char_start": 0, "char_end": 10, "text": "a"}, "c2": {"doc_id": "d", "char_start": 10, "char_end": 20, "text": "b"}}
    ranked, mism = served_to_ranked([{"chunk_id": "c2", "text": "b"}, {"chunk_id": "c1", "text": "CHANGED"}], local)
    assert ranked == [("d", 10, 20), ("d", 0, 10)] and mism == 1


def test_retrieve_only_searches_the_default_indexes_and_honours_top_k():
    from scripts import composition_root as cr
    calls = []

    class _L:
        pass

    class _E:
        pass
    llm_reg = {"seam": "LLM_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _L()}
    emb_reg = {"seam": "EMBEDDING_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _E()}
    fake_deps = {"retrieve": lambda req: (calls.append(req) or {"results": [], "status": "PASS"})}
    with patch.object(cr, "_discover_index_fingerprints", return_value=["fp1"]), patch.object(cr, "build_pipeline_deps", return_value=fake_deps):
        out = cr.compose_application([llm_reg, emb_reg], env={"LLM_PROVIDER": "x", "EMBEDDING_PROVIDER": "x"})
    ro = out["agent_dependencies"].retrieve_only
    ro({"query": "Q?", "pipeline_options": {"top_k": 3}})
    ro({"query": "Q2?"})
    assert calls[0] == {"query": "Q?", "index_fingerprints": ["fp1"], "top_k": 3}
    assert calls[1] == {"query": "Q2?", "index_fingerprints": ["fp1"]}
