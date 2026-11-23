"""Daily LLM call cap and 429 breaker (free tier: 20 requests/day)."""
from unittest.mock import Mock

import pytest

from scripts.call_budget import BudgetedLLMAdapter
from scripts.composition_root import compose_application
from scripts.quota_guard import (
    DEFAULT_DAILY_LLM_CALL_CAP, MAX_DAILY_LLM_CALL_CAP, GuardedLLMAdapter, GuardedPlannerAdapter, QuotaGuard,
    daily_llm_call_cap, pacific_day,
)
from scripts.stage13_llm_execution import LLMQuotaExhaustedError, invoke_with_retry, resolve_execution_config
from scripts.stage21_agent_planning import PlannerInvocationError


class _Llm:
    provider_name, model_version_reported = "p", "v"

    def __init__(self, error=None):
        self.calls, self.error = 0, error

    def invoke(self, s, u, c):
        self.calls += 1
        if self.error:
            raise self.error
        return "ok"


class _Planner:
    def __init__(self, error=None):
        self.calls, self.error = 0, error

    def plan(self, p, c):
        self.calls += 1
        if self.error:
            raise self.error
        return {"decision": "COMPLETE"}


def _guard(cap, day=None):
    day = day or ["2026-11-23"]
    return QuotaGuard(cap=cap, clock=lambda: day[0]), day


def test_cap_parsing_is_always_below_twenty_and_never_unlimited():
    assert daily_llm_call_cap({}) == DEFAULT_DAILY_LLM_CALL_CAP == 10
    for bad in ("", "x", "-1", "1.5"):
        assert daily_llm_call_cap({"DAILY_LLM_CALL_CAP": bad}) == 10
    assert daily_llm_call_cap({"DAILY_LLM_CALL_CAP": "0"}) == 0
    assert daily_llm_call_cap({"DAILY_LLM_CALL_CAP": "999"}) == MAX_DAILY_LLM_CALL_CAP == 18
    assert MAX_DAILY_LLM_CALL_CAP < 20


def test_the_call_after_the_cap_never_reaches_the_provider():
    g, _ = _guard(3)
    llm = _Llm()
    a = GuardedLLMAdapter(llm, g)
    for _ in range(3):
        a.invoke("s", "u", {})
    with pytest.raises(LLMQuotaExhaustedError, match="DAILY_LLM_CALL_CAP"):
        a.invoke("s", "u", {})
    assert llm.calls == 3 and g.status()["used"] == 3


def test_planner_and_answer_calls_share_one_daily_count():
    g, _ = _guard(2)
    llm, pl = _Llm(), _Planner()
    GuardedPlannerAdapter(pl, g).plan("p", {})
    GuardedLLMAdapter(llm, g).invoke("s", "u", {})
    with pytest.raises(PlannerInvocationError) as e:
        GuardedPlannerAdapter(pl, g).plan("p", {})
    assert e.value.code == "QUOTA_EXHAUSTED" and (pl.calls, llm.calls) == (1, 1)


def test_cap_zero_means_retrieval_only():
    g, _ = _guard(0)
    llm = _Llm()
    with pytest.raises(LLMQuotaExhaustedError):
        GuardedLLMAdapter(llm, g).invoke("s", "u", {})
    assert llm.calls == 0


def test_a_429_opens_the_breaker_and_no_further_call_is_made():
    g, _ = _guard(10)
    llm = _Llm(error=LLMQuotaExhaustedError("429"))
    a = GuardedLLMAdapter(llm, g)
    with pytest.raises(LLMQuotaExhaustedError):
        a.invoke("s", "u", {})
    llm.error = None                                          # even if the provider would now answer, the breaker stays open
    with pytest.raises(LLMQuotaExhaustedError, match="BREAKER"):
        a.invoke("s", "u", {})
    assert llm.calls == 1 and g.status()["breaker_open"] is True


def test_a_planner_429_opens_the_breaker_for_the_answer_adapter_too():
    g, _ = _guard(10)
    pl = _Planner(error=PlannerInvocationError("quota", "QUOTA_EXHAUSTED"))
    with pytest.raises(PlannerInvocationError):
        GuardedPlannerAdapter(pl, g).plan("p", {})
    llm = _Llm()
    with pytest.raises(LLMQuotaExhaustedError):
        GuardedLLMAdapter(llm, g).invoke("s", "u", {})
    assert llm.calls == 0


def test_other_planner_errors_do_not_open_the_breaker():
    g, _ = _guard(10)
    with pytest.raises(PlannerInvocationError):
        GuardedPlannerAdapter(_Planner(error=PlannerInvocationError("x", "JSON_DECODE_ERROR")), g).plan("p", {})
    assert g.status()["breaker_open"] is False


def test_the_counter_and_breaker_reset_on_a_new_pacific_day():
    g, day = _guard(1)
    llm = _Llm(error=LLMQuotaExhaustedError("429"))
    a = GuardedLLMAdapter(llm, g)
    with pytest.raises(LLMQuotaExhaustedError):
        a.invoke("s", "u", {})
    day[0] = "2026-11-24"
    llm.error = None
    assert a.invoke("s", "u", {}) == "ok" and g.status() == {"day_pacific": "2026-11-24", "used": 1, "cap": 1, "breaker_open": False}


def test_stage13_does_not_retry_a_capped_or_broken_call():
    g, _ = _guard(1)
    llm = _Llm()
    a = GuardedLLMAdapter(llm, g)
    cfg = {**resolve_execution_config({"model_name": "m"}), "max_retry_attempts": 5}
    invoke_with_retry("s", "u", a, cfg)                       # uses the single allowed call
    _, err, attempts, _ = invoke_with_retry("s", "u", a, cfg)
    assert isinstance(err, LLMQuotaExhaustedError) and attempts == 1 and llm.calls == 1


def test_attribute_delegation():
    g, _ = _guard(1)
    assert GuardedLLMAdapter(_Llm(), g).provider_name == "p"
    assert GuardedPlannerAdapter(_Planner(), g).calls == 0


def test_pacific_day_follows_pacific_not_utc():
    import datetime as dt
    t = dt.datetime(2026, 11, 24, 7, 30, tzinfo=dt.timezone.utc)      # 23:30 on the 23rd in Pacific (PST, UTC-8)
    assert pacific_day(t) == "2026-11-23"
    assert pacific_day(t + dt.timedelta(hours=1)) == "2026-11-24"


def test_compose_wraps_with_the_guard_inside_the_request_budget():
    llm_reg = {"seam": "LLM_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _Llm()}
    pl_reg = {"seam": "PLANNER_LLM_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _Planner()}
    out = compose_application([llm_reg, pl_reg], env={"LLM_PROVIDER": "x", "PLANNER_LLM_PROVIDER": "x", "DAILY_LLM_CALL_CAP": "1", "PLANNER_ENABLED": "true"})
    llm = out["llm_adapter"]
    assert isinstance(llm, BudgetedLLMAdapter) and isinstance(llm._inner, GuardedLLMAdapter)
    llm.invoke("s", "u", {})
    with pytest.raises(LLMQuotaExhaustedError):                          # the cap came from DAILY_LLM_CALL_CAP in the env
        llm.invoke("s", "u", {})
    pl = out["agent_dependencies"].planner_llm_adapter
    with pytest.raises(PlannerInvocationError):                          # planner shares the same guard
        pl.plan("p", {})


# ---- pacing (12 RPM against a 15 RPM limit) ----

def test_pace_rpm_parsing():
    from scripts.quota_guard import pace_rpm
    assert pace_rpm({}) == 0 and pace_rpm({"LLM_PACE_RPM": "x"}) == 0 and pace_rpm({"LLM_PACE_RPM": "-2"}) == 0
    assert pace_rpm({"LLM_PACE_RPM": "12"}) == 12


def test_calls_are_spaced_five_seconds_apart_at_12_rpm():
    t, slept = [100.0], []
    g = QuotaGuard(cap=10, clock=lambda: "d", pace=12, sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)), monotonic=lambda: t[0])
    for _ in range(3):
        g.before_call()
    assert slept == [5.0, 5.0]                  # first call immediate, then one start every 5 s


def test_no_pacing_by_default_and_a_refused_call_does_not_sleep():
    slept = []
    g = QuotaGuard(cap=1, clock=lambda: "d", pace=0, sleep=slept.append)
    g.before_call()
    with pytest.raises(LLMQuotaExhaustedError):
        g.before_call()
    g2 = QuotaGuard(cap=0, clock=lambda: "d", pace=12, sleep=slept.append)
    with pytest.raises(LLMQuotaExhaustedError):
        g2.before_call()
    assert slept == []


def test_model_config_pin():
    from scripts.model_config import default_gemini_model, default_pace_rpm
    assert default_gemini_model() == "gemini-3.5-flash-lite" and default_pace_rpm() == 12
