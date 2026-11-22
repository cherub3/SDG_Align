import time
import uuid
from typing import Dict, Any, List
from scripts.application_bootstrap import ApplicationInstance
from scripts.runtime_orchestration import execute_request

class ObservationRecord:
    """
    Immutable observation record carrying correlation identity, outcome, and duration.
    Never retains request or result payload content.
    """
    def __init__(self, correlation_id: str, outcome: str, duration: float):
        self._correlation_id = correlation_id
        self._outcome = outcome
        self._duration = duration

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    @property
    def outcome(self) -> str:
        return self._outcome

    @property
    def duration(self) -> float:
        return self._duration

# In-memory-only observation record store (Track B Phase 6). Cleared on every process restart,
# unbounded, and not synchronized beyond CPython's GIL guarantee on list.append/list(...) copies —
# a demo-grade store, not a production observability backend.
_observation_records: List[ObservationRecord] = []


def get_observation_records() -> List[ObservationRecord]:
    """Returns a snapshot copy of the in-memory observation records collected so far."""
    return list(_observation_records)


def observe_request(application_instance: ApplicationInstance, agent_request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wraps Phase 2.2's runtime execution to observe timing, outcome, and identity.
    Produces one ObservationRecord per invocation.
    Does not catch or reinterpret exceptions (no try/except).
    """
    correlation_id = str(uuid.uuid4())
    start_time = time.time()
    outcome = "failed"
    
    try:
        result = execute_request(
            application_instance=application_instance, 
            agent_request=agent_request
        )
        outcome = "completed"
        return result
    finally:
        duration = time.time() - start_time
        _observation_records.append(ObservationRecord(
            correlation_id=correlation_id,
            outcome=outcome,
            duration=duration
        ))
