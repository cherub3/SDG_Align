"""Hard cap on paid / quota-limited LLM calls per request (planner + answer, retries included).

The planner loop can call the planner up to 25 times and each retrieval step calls the answer LLM, which itself retries
transient errors up to 5 times. Without a cap one request could make dozens of billed calls. The cap is enforced where the
call is actually made: the two adapters are wrapped once, in the composition root, so every call path (planner step, answer
call, answer retry) is counted and none can bypass it.

  MAX_LLM_CALLS_PER_REQUEST   integer >= 1, default 6 (a normal request is 3: plan, answer, plan-complete).
                              Unset, blank, non-numeric or < 1 falls back to the default (never to "unlimited").

The budget lives in a ContextVar set by `request_budget()` around one request, so concurrent requests do not share it.
Outside a request (tests, library use) no budget is active and nothing is capped.
"""
import contextvars
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional

from scripts.stage13_llm_execution import LLMAdapter, LLMInvalidRequestError
from scripts.stage21_agent_planning import PlannerInvocationError, PlannerLLMAdapter

DEFAULT_MAX_LLM_CALLS_PER_REQUEST = 6
ENV_VAR = "MAX_LLM_CALLS_PER_REQUEST"


class LLMCallBudgetExceeded(LLMInvalidRequestError):
    """Answer-LLM call refused. A non-retryable class, so stage 13 reports one failed call and does not retry."""


class PlannerCallBudgetExceeded(PlannerInvocationError):
    """Planner call refused. Stage 21 turns it into a PLANNER_INVOCATION_FAILED finding."""

    def __init__(self, message: str):
        super().__init__(message, "LLM_CALL_BUDGET_EXCEEDED")


def max_llm_calls_per_request(environ: Optional[Dict[str, str]] = None) -> int:
    env = os.environ if environ is None else environ
    try:
        value = int((env.get(ENV_VAR) or "").strip())
    except ValueError:
        return DEFAULT_MAX_LLM_CALLS_PER_REQUEST
    return value if value >= 1 else DEFAULT_MAX_LLM_CALLS_PER_REQUEST


class _Budget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.used >= self.limit:
                return False
            self.used += 1
            return True


_current: "contextvars.ContextVar[Optional[_Budget]]" = contextvars.ContextVar("llm_call_budget", default=None)


@contextmanager
def request_budget(limit: Optional[int] = None):
    """Activates a fresh budget for the duration of one request. `limit` defaults to MAX_LLM_CALLS_PER_REQUEST."""
    budget = _Budget(max_llm_calls_per_request() if limit is None else limit)
    token = _current.set(budget)
    try:
        yield budget
    finally:
        _current.reset(token)


def _charge(kind: str) -> None:
    budget = _current.get()
    if budget is None:
        return
    if not budget.take():
        msg = f"per-request LLM call cap reached ({budget.limit}); refusing {kind} call. Raise {ENV_VAR} to allow more."
        raise (PlannerCallBudgetExceeded(msg) if kind == "planner" else LLMCallBudgetExceeded(msg))


class BudgetedLLMAdapter(LLMAdapter):
    def __init__(self, inner: Any):
        self._inner = inner

    def invoke(self, system_prompt, user_prompt, config):
        _charge("answer")
        return self._inner.invoke(system_prompt, user_prompt, config)

    def __getattr__(self, name):                 # provider_name, model_version_reported, ...
        return getattr(self._inner, name)


class BudgetedPlannerAdapter(PlannerLLMAdapter):
    def __init__(self, inner: Any):
        self._inner = inner

    def plan(self, planner_prompt, config):
        _charge("planner")
        return self._inner.plan(planner_prompt, config)

    def __getattr__(self, name):
        return getattr(self._inner, name)
