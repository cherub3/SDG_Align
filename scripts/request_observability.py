import time
import uuid
from datetime import datetime, timezone
from collections import deque
from typing import Deque, Dict, Any, List, Optional
from scripts.application_bootstrap import ApplicationInstance
from scripts.runtime_orchestration import execute_request

class ObservationRecord:
    """
    Immutable observation record carrying correlation identity, outcome, and duration.
    Never retains request or result payload content.
    """
    def __init__(self, correlation_id: str, outcome: str, duration: float, timestamp: Optional[str] = None):
        self._correlation_id = correlation_id
        self._outcome = outcome
        self._duration = duration
        # ISO 8601, UTC: when the record was written (the end of the request).
        self._timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    @property
    def timestamp(self) -> str:
        return self._timestamp

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    @property
    def outcome(self) -> str:
        return self._outcome

    @property
    def duration(self) -> float:
        return self._duration

# Maximum number of ObservationRecords kept in memory; the oldest are dropped first.
MAX_OBSERVATION_RECORDS = 1000

# In-memory-only, per-process observation record store (Track B Phase 6). Cleared on every process
# restart and NOT shared between instances. Bounded (oldest records are discarded) so it cannot
# grow without limit. deque.append and list(deque) are safe under CPython's GIL for this usage.
# A demo-grade store, not a production observability backend.
_observation_records: Deque[ObservationRecord] = deque(maxlen=MAX_OBSERVATION_RECORDS)


def get_observation_records() -> List[ObservationRecord]:
    """Returns a snapshot copy of the in-memory observation records collected so far."""
    return list(_observation_records)


def observe_request(
    application_instance: ApplicationInstance,
    agent_request: Dict[str, Any],
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wraps Phase 2.2's runtime execution to observe timing, outcome, and identity.
    Produces one ObservationRecord per invocation.
    Does not catch or reinterpret exceptions (no try/except).
    """
    correlation_id = correlation_id or str(uuid.uuid4())
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
