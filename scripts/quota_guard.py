"""Daily call cap and 429 circuit breaker for the Gemini free tier (20 requests/day per project, reset at midnight Pacific).

  DAILY_LLM_CALL_CAP   integer 0..18, default 10. 0 = no LLM calls at all (retrieval-only). Values above 18 are clamped to 18 and
                       invalid values fall back to 10, so the cap is always below Google's 20/day and never "unlimited".

Behaviour (applies to answer and planner calls alike, retries included, since both go through the same wrappers):
  * every attempted call counts, whether or not it succeeds (whether Google counts failed calls is UNKNOWN, so we assume it does);
  * once the day's cap is reached, further calls are refused without touching the network;
  * a 429 from the provider trips a breaker: all calls are refused until the next midnight Pacific. Nothing is retried.

State is per process and in memory. With Cloud Run min-instances=0 it resets when an instance restarts, so the real hard stop is
Google's own limit plus the breaker; this cap is a second, cheaper line of defence (see PHASE_3_STEP1_GCP_READINESS.md).
"""
import datetime as _dt
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

from scripts.stage13_llm_execution import LLMAdapter, LLMQuotaExhaustedError
from scripts.stage21_agent_planning import PlannerInvocationError, PlannerLLMAdapter

DEFAULT_DAILY_LLM_CALL_CAP = 10
MAX_DAILY_LLM_CALL_CAP = 18
ENV_VAR = "DAILY_LLM_CALL_CAP"
PACE_ENV_VAR = "LLM_PACE_RPM"
QUOTA_PLANNER_CODE = "QUOTA_EXHAUSTED"


def daily_llm_call_cap(environ: Optional[Dict[str, str]] = None) -> int:
    env = os.environ if environ is None else environ
    try:
        value = int((env.get(ENV_VAR) or "").strip())
    except ValueError:
        return DEFAULT_DAILY_LLM_CALL_CAP
    if value < 0:
        return DEFAULT_DAILY_LLM_CALL_CAP
    return min(value, MAX_DAILY_LLM_CALL_CAP)


def pace_rpm(environ: Optional[Dict[str, str]] = None) -> int:
    """LLM_PACE_RPM: calls per minute the process may start (0/unset/invalid = no pacing). Eval runs use 12 (limit is 15)."""
    env = os.environ if environ is None else environ
    try:
        v = int((env.get(PACE_ENV_VAR) or "").strip())
    except ValueError:
        return 0
    return v if v >= 1 else 0


def pacific_day(now_utc: Optional[_dt.datetime] = None) -> str:
    """Calendar date in America/Los_Angeles (falls back to fixed UTC-8 when tz data is unavailable)."""
    now = now_utc or _dt.datetime.now(_dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        local = now.astimezone(ZoneInfo("America/Los_Angeles"))
    except Exception:
        local = now.astimezone(_dt.timezone(_dt.timedelta(hours=-8)))
    return local.date().isoformat()


class QuotaGuard:
    def __init__(self, cap: Optional[int] = None, clock: Callable[[], str] = pacific_day, pace: Optional[int] = None,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic):
        self.cap = daily_llm_call_cap() if cap is None else cap
        self._interval = 60.0 / pace_value if (pace_value := (pace_rpm() if pace is None else pace)) else 0.0
        self._sleep, self._mono, self._next_slot = sleep, monotonic, 0.0
        self._clock = clock
        self._lock = threading.Lock()
        self._day = clock()
        self.used = 0
        self.tripped = False

    def _roll(self) -> None:
        today = self._clock()
        if today != self._day:                     # midnight Pacific passed: new quota day, breaker resets
            self._day, self.used, self.tripped = today, 0, False

    def before_call(self) -> None:
        with self._lock:
            self._roll()
            if self.tripped:
                raise LLMQuotaExhaustedError("QUOTA_BREAKER_OPEN: provider returned 429; no LLM calls until midnight Pacific")
            if self.used >= self.cap:
                raise LLMQuotaExhaustedError(f"DAILY_LLM_CALL_CAP reached ({self.used}/{self.cap}); no LLM calls until midnight Pacific")
            self.used += 1
            wait = 0.0
            if self._interval:                      # reserve the next start slot under the lock, sleep outside it
                now = self._mono()
                slot = max(now, self._next_slot)
                self._next_slot = slot + self._interval
                wait = slot - now
        if wait > 0:
            self._sleep(wait)

    def trip(self) -> None:
        with self._lock:
            self.tripped = True

    def status(self) -> Dict[str, Any]:
        with self._lock:
            self._roll()
            return {"day_pacific": self._day, "used": self.used, "cap": self.cap, "breaker_open": self.tripped}


class GuardedLLMAdapter(LLMAdapter):
    def __init__(self, inner: Any, guard: QuotaGuard):
        self._inner, self.guard = inner, guard

    def invoke(self, system_prompt, user_prompt, config):
        self.guard.before_call()
        try:
            return self._inner.invoke(system_prompt, user_prompt, config)
        except LLMQuotaExhaustedError:
            self.guard.trip()
            raise

    def __getattr__(self, name):
        return getattr(self._inner, name)


class GuardedPlannerAdapter(PlannerLLMAdapter):
    def __init__(self, inner: Any, guard: QuotaGuard):
        self._inner, self.guard = inner, guard

    def plan(self, planner_prompt, config):
        try:
            self.guard.before_call()
        except LLMQuotaExhaustedError as e:
            raise PlannerInvocationError(str(e), QUOTA_PLANNER_CODE) from e
        try:
            return self._inner.plan(planner_prompt, config)
        except PlannerInvocationError as e:
            if e.code == QUOTA_PLANNER_CODE:
                self.guard.trip()
            raise

    def __getattr__(self, name):
        return getattr(self._inner, name)
