from typing import Dict, Any
from scripts.application_bootstrap import ApplicationInstance
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
    
    result = plan_and_execute(
        agent_request=agent_request,
        agent_dependencies=agent_deps
    )
    
    return result
