import pytest
import copy
from typing import Dict, Any

from scripts.stage21_agent_planning import (
    AgentPlanningInputError,
    AgentPlanningInternalError,
    PlannerInvocationError,
    PlannerLLMAdapter,
    AgentDependencies,
    PlannerState,
    validate_agent_request,
    validate_planner_decision,
    validate_plan_step,
    validate_agent_result,
    resolve_planning_config,
    build_initial_context,
    build_planner_prompt,
    execute_plan_step,
    build_agent_result,
    plan_and_execute,
    _transition,
    _canonical_json,
    AGENT_PLANNING_VERSION,
)


class MockToolRegistry:
    def list_tools(self):
        return [{"tool_name": "calc"}, {"tool_name": "search"}]

class MockPlannerLLMAdapter(PlannerLLMAdapter):
    def __init__(self, decisions=None, raise_error=False):
        self.decisions = decisions or []
        self.call_count = 0
        self.raise_error = raise_error
        
    def plan(self, prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        self.call_count += 1
        if self.raise_error:
            raise PlannerInvocationError("Mock LLM error", "LLM_ERROR")
        if self.decisions:
            return self.decisions.pop(0)
        return {"decision": "FAIL"}


@pytest.fixture
def agent_deps():
    return AgentDependencies(
        handle_request=lambda req, deps: {"status": "SUCCESS", "findings": []},
        select_memory=lambda cid, cfg: {"memory": "mock"},
        append_turn=lambda cid, turn: {"status": "OPEN"},
        get_conversation=lambda cid: {"status": "OPEN"},
        execute_tool=lambda req, reg, adp: {"output": "mock_tool"},
        tool_registry=MockToolRegistry(),
        tool_adapter=None,
        planner_llm_adapter=MockPlannerLLMAdapter(),
        pipeline_deps=None,
        default_planner_model_name="test-model"
    )

@pytest.fixture
def valid_request():
    return {
        "query": "Test query"
    }


def test_validate_agent_request():
    with pytest.raises(AgentPlanningInputError, match="must be a dict"):
        validate_agent_request([])
    
    with pytest.raises(AgentPlanningInputError, match="query must be a non-empty string"):
        validate_agent_request({})
        
    with pytest.raises(AgentPlanningInputError, match="must be a dict if present"):
        validate_agent_request({"query": "q", "tool_preferences": []})
        
    validate_agent_request({"query": "Valid"})


def test_resolve_planning_config(agent_deps):
    cfg = resolve_planning_config(None, agent_deps)
    assert cfg["model_name"] == "test-model"
    assert cfg["temperature"] == 0.0
    assert cfg["max_plan_steps"] == 10
    
    cfg = resolve_planning_config({"max_plan_steps": 100, "planner_temperature": -1}, agent_deps)
    assert cfg["max_plan_steps"] == 25
    assert cfg["temperature"] == 0.0


def test_state_transitions():
    assert _transition(PlannerState.INITIALIZING, PlannerState.PLANNING) == PlannerState.PLANNING
    
    with pytest.raises(AgentPlanningInternalError):
        _transition(PlannerState.INITIALIZING, PlannerState.EVALUATING)
        
    with pytest.raises(AgentPlanningInternalError):
        _transition(PlannerState.COMPLETED, PlannerState.PLANNING)


def test_validate_planner_decision():
    with pytest.raises(AgentPlanningInputError, match="invalid decision type"):
        validate_planner_decision({"decision": "UNKNOWN"})
        
    with pytest.raises(AgentPlanningInputError, match="unknown step_type"):
        validate_planner_decision({
            "decision": "EXECUTE_STEP",
            "next_step": {"step_type": "UNKNOWN"}
        })
        
    validate_planner_decision({"decision": "COMPLETE"})


def test_build_initial_context(agent_deps, valid_request):
    ctx = build_initial_context(valid_request, agent_deps)
    assert ctx["query"] == "Test query"
    assert len(ctx["available_tools"]) == 2
    
    # Filter tools
    req = {"query": "Q", "tool_preferences": {"allowed_tools": ["calc"]}}
    ctx = build_initial_context(req, agent_deps)
    assert len(ctx["available_tools"]) == 1
    assert ctx["available_tools"][0]["tool_name"] == "calc"
    
    # Conversation handling
    req = {"query": "Q", "conversation_id": "c1"}
    ctx = build_initial_context(req, agent_deps)
    assert ctx["conversation_memory"] == {"memory": "mock"}


def test_execute_plan_step(agent_deps, valid_request):
    step = {
        "step_index": 0,
        "step_type": "QUERY_PIPELINE",
        "step_input": {}
    }
    res = execute_plan_step(step, agent_deps, valid_request, {"available_tools": []})
    assert res["step_status"] == "COMPLETED"
    assert res["step_result"] == {"status": "SUCCESS", "findings": []}
    
    # Tool missing
    step = {
        "step_index": 0,
        "step_type": "TOOL_INVOCATION",
        "step_input": {"tool_name": "calc"}
    }
    res = execute_plan_step(step, agent_deps, valid_request, {"available_tools": []})
    assert res["step_status"] == "FAILED"
    assert any(f["code"] == "TOOL_NOT_AVAILABLE" for f in res["step_findings"])


def test_plan_and_execute_success(agent_deps, valid_request):
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(decisions=[
        {"decision": "EXECUTE_STEP", "next_step": {"step_type": "TOOL_INVOCATION", "step_input": {"tool_name": "calc"}}},
        {"decision": "EXECUTE_STEP", "next_step": {"step_type": "QUERY_PIPELINE", "step_input": {}}},
        {"decision": "COMPLETE", "final_answer_step_index": 1}
    ])
    
    result = plan_and_execute(valid_request, agent_deps)
    assert result["status"] == "PASS"
    assert result["plan"]["total_step_count"] == 2
    assert result["final_response"]["status"] == "SUCCESS"
    assert len(result["tool_results"]) == 1
    assert result["plan"]["plan_status"] == "COMPLETED"


def test_plan_and_execute_failure(agent_deps, valid_request):
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(decisions=[
        {"decision": "FAIL"}
    ])
    
    result = plan_and_execute(valid_request, agent_deps)
    assert result["status"] == "FAIL"
    assert result["plan"]["total_step_count"] == 0
    assert result["plan"]["plan_status"] == "FAILED"


def test_plan_and_execute_llm_error(agent_deps, valid_request):
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(raise_error=True)
    
    result = plan_and_execute(valid_request, agent_deps)
    assert result["status"] == "FAIL"
    assert any(f["code"] == "PLANNER_INVOCATION_FAILED" for f in result["findings"])
    assert result["plan"]["plan_status"] == "FAILED"


def test_plan_and_execute_step_limit(agent_deps, valid_request):
    decisions = [{"decision": "EXECUTE_STEP", "next_step": {"step_type": "TOOL_INVOCATION", "step_input": {"tool_name": "calc"}}}] * 15
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(decisions=decisions)
    
    result = plan_and_execute(valid_request, agent_deps)
    assert result["status"] == "PARTIAL"  # because tools succeed but limit reached
    assert result["plan"]["plan_status"] == "STEP_LIMIT_REACHED"
    assert result["plan"]["total_step_count"] == 10  # default max
    assert any(f["code"] == "PLAN_STEP_LIMIT_REACHED" for f in result["findings"])


def test_agent_result_validation(agent_deps, valid_request):
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(decisions=[
        {"decision": "COMPLETE"}
    ])
    result = plan_and_execute(valid_request, agent_deps)
    
    # Validation should pass
    validate_agent_result(result)
    
    # Tamper with count
    bad_result = copy.deepcopy(result)
    bad_result["plan"]["total_step_count"] = 99
    with pytest.raises(AgentPlanningInternalError, match="RESULT_STEP_COUNT_MISMATCH"):
        validate_agent_result(bad_result)
        
    # Tamper with ID
    bad_result2 = copy.deepcopy(result)
    bad_result2["agent_result_id"] = "ar_tampered"
    with pytest.raises(AgentPlanningInternalError, match="RESULT_ID_MISMATCH"):
        validate_agent_result(bad_result2)


def _valid_completed_result(agent_deps, valid_request):
    """Produce a valid AgentResult (one QUERY_PIPELINE step, COMPLETE) for tamper tests."""
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(decisions=[
        {"decision": "EXECUTE_STEP", "next_step": {"step_type": "QUERY_PIPELINE", "step_input": {}}},
        {"decision": "COMPLETE", "final_answer_step_index": 0}
    ])
    return plan_and_execute(valid_request, agent_deps)


def test_invariant_step_index_not_contiguous(agent_deps, valid_request):
    result = _valid_completed_result(agent_deps, valid_request)
    bad = copy.deepcopy(result)
    bad["plan"]["steps"][0]["step_index"] = 5
    with pytest.raises(AgentPlanningInternalError, match="RESULT_STEP_INDEX_NOT_CONTIGUOUS"):
        validate_agent_result(bad)


def test_invariant_status_response_mismatch(agent_deps, valid_request):
    result = _valid_completed_result(agent_deps, valid_request)
    bad = copy.deepcopy(result)
    bad["status"] = "PASS"
    bad["final_response"] = None
    with pytest.raises(AgentPlanningInternalError, match="RESULT_STATUS_RESPONSE_MISMATCH"):
        validate_agent_result(bad)


def test_invariant_plan_id_mismatch(agent_deps, valid_request):
    result = _valid_completed_result(agent_deps, valid_request)
    bad = copy.deepcopy(result)
    bad["plan"]["agent_plan_id"] = "ap_tampered0000000"
    with pytest.raises(AgentPlanningInternalError, match="RESULT_PLAN_ID_MISMATCH"):
        validate_agent_result(bad)


def test_invariant_tool_results_mismatch(agent_deps, valid_request):
    result = _valid_completed_result(agent_deps, valid_request)
    bad = copy.deepcopy(result)
    bad["tool_results"].append({"output": "phantom"})
    with pytest.raises(AgentPlanningInternalError, match="RESULT_TOOL_RESULTS_MISMATCH"):
        validate_agent_result(bad)


def test_failed_tool_step_returns_result(agent_deps, valid_request):
    # Fix 1 regression: a plan with a failed (unavailable) tool step must return a valid
    # AgentResult, not raise RESULT_TOOL_RESULTS_MISMATCH.
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(decisions=[
        {"decision": "EXECUTE_STEP", "next_step": {"step_type": "TOOL_INVOCATION", "step_input": {"tool_name": "unknown_tool"}}},
        {"decision": "COMPLETE", "final_answer_step_index": 0}
    ])
    result = plan_and_execute(valid_request, agent_deps)
    assert result["plan"]["steps"][0]["step_status"] == "FAILED"
    assert len(result["tool_results"]) == 1
    validate_agent_result(result)


def test_conversation_append_findings_aggregated(agent_deps):
    agent_deps.append_turn = lambda cid, turn: {
        "status": "OPEN",
        "findings": [{"severity": "WARNING", "code": "STORE_LATENCY", "message": "slow"}]
    }
    agent_deps.planner_llm_adapter = MockPlannerLLMAdapter(decisions=[
        {"decision": "EXECUTE_STEP", "next_step": {"step_type": "CONVERSATION_APPEND", "step_input": {"speaker": "USER", "content": "hi"}}},
        {"decision": "COMPLETE"}
    ])
    req = {"query": "Q", "conversation_id": "c1"}
    result = plan_and_execute(req, agent_deps)
    assert result["plan"]["steps"][0]["step_type"] == "CONVERSATION_APPEND"
    assert result["plan"]["steps"][0]["step_status"] == "COMPLETED"
    assert any(f["code"] == "STORE_LATENCY" for f in result["upstream_findings"])


def test_conversation_not_found(agent_deps):
    agent_deps.get_conversation = lambda cid: None
    with pytest.raises(AgentPlanningInputError, match="CONVERSATION_NOT_FOUND"):
        plan_and_execute({"query": "Q", "conversation_id": "missing"}, agent_deps)


def test_conversation_closed(agent_deps):
    agent_deps.get_conversation = lambda cid: {"status": "CLOSED"}
    with pytest.raises(AgentPlanningInputError, match="CONVERSATION_CLOSED"):
        plan_and_execute({"query": "Q", "conversation_id": "closed1"}, agent_deps)


def test_empty_conversation_id_rejected():
    with pytest.raises(AgentPlanningInputError, match="conversation_id must be a non-empty string"):
        validate_agent_request({"query": "Q", "conversation_id": ""})


def test_determinism_hashes():
    plan_canonical = _canonical_json({"query": "test", "step_count": 0, "step_types": []})
    import hashlib
    expected_id = "ap_" + hashlib.sha256(plan_canonical.encode("utf-8")).hexdigest()[:16]
    
    assert "ap_" in expected_id
    assert len(expected_id) == 19
