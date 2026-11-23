import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


# =================================================================================================
# Constants
# =================================================================================================
AGENT_PLANNING_VERSION = "1.0.0"

DEFAULT_MAX_PLAN_STEPS = 10
MAX_PLAN_STEPS = 25
DEFAULT_PLANNER_TEMPERATURE = 0.0
MAX_PLANNER_TEMPERATURE = 1.0


# =================================================================================================
# Exceptions
# =================================================================================================
class AgentPlanningInputError(ValueError):
    """Raised for malformed requests or invalid planner steps (structural failure)."""
    pass

class AgentPlanningInternalError(RuntimeError):
    """Raised for invariant violations."""
    pass

class PlannerInvocationError(Exception):
    """Raised by PlannerLLMAdapter on failure."""
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# =================================================================================================
# Schemas and Contracts
# =================================================================================================
class PlannerLLMAdapter(ABC):
    @abstractmethod
    def plan(self, planner_prompt: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes a planning-capable LLM with the given prompt.
        Returns a structured PlannerDecision. On failure, raises PlannerInvocationError."""
        pass


@dataclass
class AgentDependencies:
    handle_request: Callable
    select_memory: Callable
    append_turn: Callable
    get_conversation: Callable
    execute_tool: Callable
    tool_registry: Any
    tool_adapter: Any
    planner_llm_adapter: PlannerLLMAdapter
    pipeline_deps: Any
    default_planner_model_name: str
    retrieve_only: Optional[Callable] = None   # ranked chunks, no LLM (request option retrieval_only)


# =================================================================================================
# Planner State Machine
# =================================================================================================
class PlannerState:
    INITIALIZING = "INITIALIZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    VALID_TRANSITIONS = {
        INITIALIZING: {PLANNING, FAILED},
        PLANNING: {EXECUTING, COMPLETED, FAILED},
        EXECUTING: {EVALUATING},
        EVALUATING: {PLANNING, COMPLETED, FAILED},
        COMPLETED: set(),
        FAILED: set()
    }


def _transition(current_state: str, next_state: str) -> str:
    if next_state not in PlannerState.VALID_TRANSITIONS.get(current_state, set()):
        raise AgentPlanningInternalError(
            f"Invalid state transition: {current_state} -> {next_state}"
        )
    return next_state


# =================================================================================================
# Helpers
# =================================================================================================
def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


def _now() -> str:
    # Same "...Z" UTC format as before; datetime.utcnow() is deprecated since Python 3.12.
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# =================================================================================================
# Validation
# =================================================================================================
def validate_agent_request(agent_request: Dict[str, Any]) -> None:
    if not isinstance(agent_request, dict):
        raise AgentPlanningInputError("AGENT_REQUEST_MALFORMED: agent_request must be a dict")
    
    if "query" not in agent_request or not isinstance(agent_request["query"], str) or not agent_request["query"]:
        raise AgentPlanningInputError("AGENT_REQUEST_MALFORMED: query must be a non-empty string")
    
    # Types for optional fields
    for field, expected_type in [
        ("conversation_id", str),
        ("tool_preferences", dict),
        ("planning_config", dict),
        ("pipeline_options", dict)
    ]:
        val = agent_request.get(field)
        if val is not None and not isinstance(val, expected_type):
            raise AgentPlanningInputError(f"AGENT_REQUEST_MALFORMED: {field} must be a {expected_type.__name__} if present")

    conversation_id = agent_request.get("conversation_id")
    if conversation_id is not None and not conversation_id:
        raise AgentPlanningInputError("AGENT_REQUEST_MALFORMED: conversation_id must be a non-empty string if present")


def validate_planner_decision(decision: Dict[str, Any]) -> None:
    if not isinstance(decision, dict):
        raise AgentPlanningInputError("PLAN_STEP_INVALID: decision must be a dict")
    
    decision_type = decision.get("decision")
    if decision_type not in ("EXECUTE_STEP", "COMPLETE", "FAIL"):
        raise AgentPlanningInputError(f"PLAN_STEP_INVALID: invalid decision type {decision_type}")
    
    if decision_type == "EXECUTE_STEP":
        next_step = decision.get("next_step")
        if not isinstance(next_step, dict):
            raise AgentPlanningInputError("PLAN_STEP_INVALID: next_step must be a dict for EXECUTE_STEP")
        step_type = next_step.get("step_type")
        if step_type not in ("QUERY_PIPELINE", "CONVERSATION_MEMORY", "CONVERSATION_APPEND", "TOOL_INVOCATION"):
            raise AgentPlanningInputError(f"PLAN_STEP_INVALID: unknown step_type {step_type}")
        if not isinstance(next_step.get("step_input"), dict):
            raise AgentPlanningInputError("PLAN_STEP_INVALID: step_input must be a dict")


def validate_plan_step(step: Dict[str, Any]) -> None:
    step_type = step.get("step_type")
    if step_type not in ("QUERY_PIPELINE", "CONVERSATION_MEMORY", "CONVERSATION_APPEND", "TOOL_INVOCATION"):
        raise AgentPlanningInputError(f"PLAN_STEP_INVALID: unknown step_type {step_type}")
    if not isinstance(step.get("step_input"), dict):
        raise AgentPlanningInputError("PLAN_STEP_INVALID: step_input must be a dict")


def validate_agent_result(result: Dict[str, Any]) -> None:
    plan = result["plan"]
    steps = plan["steps"]
    total_step_count = plan["total_step_count"]
    
    if total_step_count != len(steps):
        raise AgentPlanningInternalError("RESULT_STEP_COUNT_MISMATCH")
    
    for i, step in enumerate(steps):
        if step["step_index"] != i:
            raise AgentPlanningInternalError("RESULT_STEP_INDEX_NOT_CONTIGUOUS")
    
    status = result["status"]
    final_resp = result["final_response"]
    if status == "PASS" and final_resp is None:
        raise AgentPlanningInternalError("RESULT_STATUS_RESPONSE_MISMATCH")
    if all(s.get("step_status") == "FAILED" for s in steps) and steps and final_resp is not None:
        raise AgentPlanningInternalError("RESULT_STATUS_RESPONSE_MISMATCH")
    
    # Verify plan ID
    step_types = [s["step_type"] for s in steps]
    plan_canonical = _canonical_json({"query": result["query"], "step_count": total_step_count, "step_types": step_types})
    expected_plan_id = "ap_" + hashlib.sha256(plan_canonical.encode("utf-8")).hexdigest()[:16]
    if result["plan"]["agent_plan_id"] != expected_plan_id:
        raise AgentPlanningInternalError("RESULT_PLAN_ID_MISMATCH")
    
    # Verify result ID
    res_canonical = _canonical_json({"agent_plan_id": result["plan"]["agent_plan_id"], "conversation_id": result["conversation_id"], "query": result["query"]})
    expected_res_id = "ar_" + hashlib.sha256(res_canonical.encode("utf-8")).hexdigest()[:16]
    if result["agent_result_id"] != expected_res_id:
        raise AgentPlanningInternalError("RESULT_ID_MISMATCH")
    
    # Verify tool results
    tool_steps = [s for s in steps if s["step_type"] == "TOOL_INVOCATION"]
    if len(result["tool_results"]) != len(tool_steps):
        raise AgentPlanningInternalError("RESULT_TOOL_RESULTS_MISMATCH")


# =================================================================================================
# Lifecycle Helpers
# =================================================================================================
def resolve_planning_config(planning_config: Optional[Dict[str, Any]], deps: AgentDependencies) -> Dict[str, Any]:
    config = planning_config or {}
    
    model_name = config.get("planner_model_name")
    if model_name is None:
        model_name = deps.default_planner_model_name
        
    temp = config.get("planner_temperature")
    if temp is None:
        temp = DEFAULT_PLANNER_TEMPERATURE
    temp = max(0.0, min(float(temp), MAX_PLANNER_TEMPERATURE))
    
    max_steps = config.get("max_plan_steps")
    if max_steps is None:
        max_steps = DEFAULT_MAX_PLAN_STEPS
    max_steps = max(1, min(int(max_steps), MAX_PLAN_STEPS))
    
    return {
        "model_name": model_name,
        "temperature": temp,
        "max_plan_steps": max_steps
    }


def build_initial_context(agent_request: Dict[str, Any], deps: AgentDependencies) -> Dict[str, Any]:
    # Resolve tools
    tool_prefs = agent_request.get("tool_preferences") or {}
    enabled = tool_prefs.get("enabled", True)
    allowed_tools = tool_prefs.get("allowed_tools")
    
    available_tools = []
    if enabled and deps.tool_registry:
        all_tools = deps.tool_registry.list_tools() if hasattr(deps.tool_registry, 'list_tools') else []
        for t in all_tools:
            if allowed_tools is None or t.get("tool_name") in allowed_tools:
                available_tools.append(t)
    
    # Resolve conversation memory
    conv_id = agent_request.get("conversation_id")
    conv_memory = None
    if conv_id:
        try:
            # Check if closed
            conv_state = deps.get_conversation(conv_id)
            if not conv_state:
                raise AgentPlanningInputError("CONVERSATION_NOT_FOUND")
            if conv_state.get("status") == "CLOSED":
                raise AgentPlanningInputError("CONVERSATION_CLOSED")
            
            # Select memory
            conv_memory = deps.select_memory(conv_id, {})
        except AgentPlanningInputError:
            raise
        except Exception:
            # For other errors, it's a CONVERSATION_MEMORY_UNAVAILABLE finding, handled at result assembly or step
            pass

    return {
        "query": agent_request["query"],
        "conversation_memory": conv_memory,
        "available_tools": available_tools,
        "executed_steps": [],
        "planner_state": PlannerState.PLANNING,
        "step_count": 0
    }


def build_planner_prompt(planner_context: Dict[str, Any]) -> str:
    # Pure deterministic serialization of context
    return _canonical_json(planner_context)


def execute_plan_step(step: Dict[str, Any], deps: AgentDependencies, agent_request: Dict[str, Any], planner_context: Dict[str, Any]) -> Dict[str, Any]:
    step["started_at"] = _now()
    step["step_status"] = "EXECUTING"
    
    step_type = step["step_type"]
    step_input = step["step_input"]
    
    findings = []
    result = None
    status = "FAILED"
    
    try:
        if step_type == "QUERY_PIPELINE":
            # APIRequest
            api_request = {
                "query": step_input.get("query", agent_request["query"]),
                "index_fingerprints": step_input.get("index_fingerprints", []),
                "filters": step_input.get("filters", {}),
                "pipeline_options": agent_request.get("pipeline_options", {})
            }
            resp = deps.handle_request(api_request, deps.pipeline_deps)
            result = resp
            if resp.get("status") in ("SUCCESS", "PARTIAL_SUCCESS"):
                status = "COMPLETED"
                
        elif step_type == "CONVERSATION_MEMORY":
            conv_id = agent_request.get("conversation_id")
            if not conv_id:
                raise ValueError("No conversation_id provided")
            mem_pkg = deps.select_memory(conv_id, step_input)
            result = mem_pkg
            status = "COMPLETED"
            
        elif step_type == "CONVERSATION_APPEND":
            conv_id = agent_request.get("conversation_id")
            if not conv_id:
                raise ValueError("No conversation_id provided")
            turn = step_input
            conv_state = deps.append_turn(conv_id, turn)
            result = conv_state
            status = "COMPLETED"
            
        elif step_type == "TOOL_INVOCATION":
            tool_name = step_input.get("tool_name")
            if tool_name not in [t.get("tool_name") for t in planner_context["available_tools"]]:
                findings.append({"severity": "WARNING", "code": "TOOL_NOT_AVAILABLE", "message": f"Tool {tool_name} not available"})
                status = "FAILED"
            else:
                tool_req = {
                    "tool_name": tool_name,
                    "arguments": step_input.get("arguments", {})
                }
                tool_resp = deps.execute_tool(tool_req, deps.tool_registry, deps.tool_adapter)
                result = tool_resp
                status = "COMPLETED"
                
    except Exception as e:
        status = "FAILED"
        findings.append({"severity": "WARNING", "code": "PLAN_STEP_EXECUTION_FAILED", "message": str(e)})

    step["step_result"] = result
    step["step_status"] = status
    step["step_findings"] = findings
    step["completed_at"] = _now()
    
    return step


def build_agent_result(
    agent_request: Dict[str, Any], 
    plan: Dict[str, Any], 
    final_response: Optional[Dict[str, Any]], 
    tool_results: List[Dict[str, Any]], 
    memory_used: Optional[Dict[str, Any]], 
    package_findings: List[Dict[str, Any]]
) -> Dict[str, Any]:
    
    upstream_findings = []
    
    # Collect upstream findings
    for step in plan["steps"]:
        res = step.get("step_result")
        if res:
            if step["step_type"] in ("QUERY_PIPELINE", "TOOL_INVOCATION", "CONVERSATION_MEMORY", "CONVERSATION_APPEND"):
                upstream_findings.extend(res.get("findings", []))
                
    # Determine status
    status = "PASS"
    has_failed_planner = any(f["code"] in ("PLANNER_INVOCATION_FAILED", "PLAN_STEP_INVALID") for f in package_findings)
    if has_failed_planner or plan["plan_status"] == "FAILED":
        status = "FAIL"
    elif all(s["step_status"] == "FAILED" for s in plan["steps"]) and len(plan["steps"]) > 0:
        status = "FAIL"
    elif final_response:
        api_status = final_response.get("status")
        if api_status == "PIPELINE_FAILURE":
            status = "FAIL"
        elif api_status == "PARTIAL_SUCCESS":
            status = "PARTIAL"
        elif api_status == "SUCCESS":
            status = "PASS"
    elif plan["plan_status"] == "STEP_LIMIT_REACHED":
        status = "PARTIAL"
    else:
        # No final response and not step limit reached.
        # According to invariant: status == "PASS" and final_response is None -> RESULT_STATUS_RESPONSE_MISMATCH
        status = "PARTIAL"


    query = agent_request["query"]
    conv_id = agent_request.get("conversation_id")
    
    res_canonical = _canonical_json({"agent_plan_id": plan["agent_plan_id"], "conversation_id": conv_id, "query": query})
    res_id = "ar_" + hashlib.sha256(res_canonical.encode("utf-8")).hexdigest()[:16]
    
    return {
        "agent_result_id": res_id,
        "agent_planning_version": AGENT_PLANNING_VERSION,
        "planned_at": _now(),
        "query": query,
        "conversation_id": conv_id,
        "status": status,
        "plan": plan,
        "final_response": final_response,
        "tool_results": tool_results,
        "conversation_memory_used": memory_used,
        "findings": package_findings,
        "upstream_findings": upstream_findings
    }


# =================================================================================================
# Main Entrypoint
# =================================================================================================
def plan_and_execute(agent_request: Dict[str, Any], agent_dependencies: AgentDependencies) -> Dict[str, Any]:
    state = PlannerState.INITIALIZING
    
    try:
        validate_agent_request(agent_request)
    except AgentPlanningInputError:
        raise
        
    config = resolve_planning_config(agent_request.get("planning_config"), agent_dependencies)
    
    package_findings = []
    
    try:
        planner_context = build_initial_context(agent_request, agent_dependencies)
        if planner_context["conversation_memory"] is None and agent_request.get("conversation_id"):
            package_findings.append({
                "severity": "WARNING",
                "code": "CONVERSATION_MEMORY_UNAVAILABLE",
                "message": "Could not retrieve conversation memory."
            })
    except AgentPlanningInputError:
        raise

    state = _transition(state, PlannerState.PLANNING)
    
    steps = []
    plan_status = "COMPLETED"
    final_response = None
    
    while state in (PlannerState.PLANNING, PlannerState.EVALUATING):
        if planner_context["step_count"] >= config["max_plan_steps"]:
            package_findings.append({
                "severity": "WARNING",
                "code": "PLAN_STEP_LIMIT_REACHED",
                "message": f"Reached max steps: {config['max_plan_steps']}"
            })
            plan_status = "STEP_LIMIT_REACHED"
            state = _transition(state, PlannerState.COMPLETED)
            break
            
        planner_context["planner_state"] = state
        prompt = build_planner_prompt(planner_context)
        
        try:
            decision = agent_dependencies.planner_llm_adapter.plan(prompt, config)
            validate_planner_decision(decision)
        except PlannerInvocationError as e:
            package_findings.append({
                "severity": "FAIL",
                "code": "PLANNER_INVOCATION_FAILED",
                "message": str(e)
            })
            plan_status = "FAILED"
            state = _transition(state, PlannerState.FAILED)
            break
        except AgentPlanningInputError as e:
            package_findings.append({
                "severity": "FAIL",
                "code": "PLAN_STEP_INVALID",
                "message": str(e)
            })
            plan_status = "FAILED"
            state = _transition(state, PlannerState.FAILED)
            break
            
        decision_type = decision["decision"]
        
        if decision_type == "COMPLETE":
            idx = decision.get("final_answer_step_index")
            if idx is not None and 0 <= idx < len(steps):
                final_response = steps[idx].get("step_result")
            else:
                package_findings.append({
                    "severity": "WARNING",
                    "code": "PLANNER_COMPLETE_WITHOUT_ANSWER",
                    "message": f"Planner returned COMPLETE with final_answer_step_index={idx!r} but {len(steps)} step(s) executed."
                })
            state = _transition(state, PlannerState.COMPLETED)
            break
            
        elif decision_type == "FAIL":
            plan_status = "FAILED"
            state = _transition(state, PlannerState.FAILED)
            break
            
        elif decision_type == "EXECUTE_STEP":
            next_step_data = decision["next_step"]
            try:
                validate_plan_step(next_step_data)
            except AgentPlanningInputError as e:
                package_findings.append({
                    "severity": "FAIL",
                    "code": "PLAN_STEP_INVALID",
                    "message": str(e)
                })
                plan_status = "FAILED"
                state = _transition(state, PlannerState.FAILED)
                break
                
            state = _transition(state, PlannerState.EXECUTING)
            
            step = {
                "step_index": planner_context["step_count"],
                "step_type": next_step_data["step_type"],
                "step_rationale": next_step_data.get("step_rationale", ""),
                "step_input": next_step_data["step_input"],
                "step_result": None,
                "step_status": "PENDING",
                "step_findings": [],
                "started_at": None,
                "completed_at": None
            }
            
            executed_step = execute_plan_step(step, agent_dependencies, agent_request, planner_context)
            steps.append(executed_step)
            
            planner_context["executed_steps"].append(executed_step)
            planner_context["step_count"] += 1
            
            state = _transition(state, PlannerState.EVALUATING)
            state = _transition(state, PlannerState.PLANNING)

    total_step_count = len(steps)
    step_types = [s["step_type"] for s in steps]
    plan_canonical = _canonical_json({"query": agent_request["query"], "step_count": total_step_count, "step_types": step_types})
    plan_id = "ap_" + hashlib.sha256(plan_canonical.encode("utf-8")).hexdigest()[:16]
    
    completed_step_count = sum(1 for s in steps if s["step_status"] == "COMPLETED")
    failed_step_count = sum(1 for s in steps if s["step_status"] == "FAILED")
    
    plan = {
        "agent_plan_id": plan_id,
        "agent_planning_version": AGENT_PLANNING_VERSION,
        "steps": steps,
        "plan_status": plan_status,
        "total_step_count": total_step_count,
        "completed_step_count": completed_step_count,
        "failed_step_count": failed_step_count
    }
    
    tool_results = [s["step_result"] for s in steps if s["step_type"] == "TOOL_INVOCATION"]
    
    result = build_agent_result(
        agent_request=agent_request,
        plan=plan,
        final_response=final_response,
        tool_results=tool_results,
        memory_used=planner_context.get("conversation_memory"),
        package_findings=package_findings
    )
    
    validate_agent_result(result)
    
    return result
