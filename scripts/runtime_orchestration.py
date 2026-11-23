from typing import Dict, Any
from scripts.application_bootstrap import ApplicationInstance
from scripts.call_budget import request_budget
from scripts.stage21_agent_planning import plan_and_execute

def execute_request(application_instance: ApplicationInstance, agent_request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes exactly one request against an already-bootstrapped application instance.
    
    This function implements the Request Lifecycle:
    1. Invokes the frozen public request-processing contract exactly once.
    2. Returns the result unchanged on success.
    3. Propagates any exception unchanged on failure.
    
    It introduces no retries, fallback logic, background execution, or mutable state.
    """
    agent_deps = application_instance["agent_dependencies"]

    if agent_request.get("retrieval_only") is True:
        # Ranked chunks only: no planner, no answer model, nothing charged to the LLM budget or the daily cap.
        retrieve_only = getattr(agent_deps, "retrieve_only", None)
        if retrieve_only is None:
            raise RuntimeError("retrieval_only is not available: retrieval is not wired")
        found = retrieve_only(agent_request)
        return {"retrieval_only": True, "query": agent_request["query"], "llm_calls": 0,
                "status": found.get("status"), "chunks": found.get("results", []), "findings": found.get("findings", [])}
    
    # One LLM-call budget per request (MAX_LLM_CALLS_PER_REQUEST); enforced inside the wrapped adapters.
    with request_budget():
        result = plan_and_execute(
            agent_request=agent_request,
            agent_dependencies=agent_deps
        )
    
    return result
