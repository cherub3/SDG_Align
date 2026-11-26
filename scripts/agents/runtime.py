"""Per-question run record: caps, token totals and the trace. Held in a ContextVar so concurrent questions never share it."""
import contextvars
import datetime as _dt
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class CapExceeded(Exception):
    """A hard cap was reached (kind: 'llm_calls'). The run ends with NOT_IN_CONTEXT, never a partial answer."""

    def __init__(self, kind: str):
        super().__init__(f"cap reached: {kind}")
        self.kind = kind


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class RunContext:
    correlation_id: str
    max_llm_calls: int
    max_searches: int
    calls: int = 0
    tool_calls: int = 0               # searches actually run (refused ones are only in the trace)
    retries: int = 0                  # model attempts repeated after a 5xx (not counted in `calls`)
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_thought: int = 0
    llm_ms: float = 0.0
    trace: List[Dict[str, Any]] = field(default_factory=list)
    search_results: List[List[Dict[str, Any]]] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)
    context_blocks: List[Dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _open: Dict[Any, Any] = field(default_factory=dict)

    def take_call(self) -> None:
        with self._lock:
            if self.calls >= self.max_llm_calls:
                raise CapExceeded("llm_calls")
            self.calls += 1

    def take_search(self) -> Optional[int]:
        """Slot number (1-based) for a new search, or None when the search cap is used up."""
        with self._lock:
            if self.tool_calls >= self.max_searches:
                return None
            self.tool_calls += 1
            return self.tool_calls

    def start(self, key: Any) -> None:
        self._open[key] = (time.monotonic(), now_iso())

    def finish(self, key: Any):
        t0, iso = self._open.pop(key, (time.monotonic(), now_iso()))
        return iso, now_iso(), (time.monotonic() - t0) * 1000.0


current_run: "contextvars.ContextVar[Optional[RunContext]]" = contextvars.ContextVar("agents_run", default=None)
