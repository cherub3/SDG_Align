"""Fix 5: zero paid calls without an explicit opt-in, and a hard per-request cap on LLM calls."""
import threading
from unittest.mock import Mock

import pytest

from scripts import backend_server
from scripts.call_budget import (
    DEFAULT_MAX_LLM_CALLS_PER_REQUEST, BudgetedLLMAdapter, BudgetedPlannerAdapter, LLMCallBudgetExceeded,
    PlannerCallBudgetExceeded, max_llm_calls_per_request, request_budget,
)
from scripts.composition_root import compose_application
from scripts.phase1_1_configuration_layer import (
    ConfigurationWiringError, build_provider_registry, load_raw_settings, validate_settings, wire_dependencies,
)
from scripts.runtime_orchestration import execute_request
from scripts.stage13_llm_execution import LLMTransientError, invoke_with_retry, resolve_execution_config


# ---------------- network opt-in ----------------

def test_network_calls_are_off_unless_explicitly_enabled():
    assert validate_settings(load_raw_settings(env={}))["runtime"]["network_calls_permitted"] is False
    on = validate_settings(load_raw_settings(env={"NETWORK_CALLS_PERMITTED": "true"}))
    assert on["runtime"]["network_calls_permitted"] is True


@pytest.mark.parametrize("value", ["", "false", "0", "no", "TRUE1", "yes"])
def test_only_the_word_true_opts_in(value):
    s = validate_settings(load_raw_settings(env={"NETWORK_CALLS_PERMITTED": value}))
    assert s["runtime"]["network_calls_permitted"] is False


def test_a_hosted_provider_cannot_be_wired_with_default_settings():
    reg = {"seam": "LLM_PROVIDER", "provider_name": "openrouter", "network_dependent": True, "factory": Mock()}
    env = {"LLM_PROVIDER": "openrouter", "LLM_PROVIDER_CREDENTIAL_REF": "env:K", "K": "secret"}
    with pytest.raises(ConfigurationWiringError, match="NETWORK_CALLS_DISABLED"):
        compose_application([reg], env=env)
    assert reg["factory"].call_count == 0                 # the factory (which would build a paid client) never ran


def test_default_wiring_reaches_no_provider_factory_unless_network_is_enabled():
    settings = validate_settings(load_raw_settings(env={"EMBEDDING_PROVIDER": "huggingface"}))
    reg = {"seam": "EMBEDDING_PROVIDER", "provider_name": "huggingface", "network_dependent": True, "factory": Mock()}
    with pytest.raises(ConfigurationWiringError):
        wire_dependencies(settings, build_provider_registry([reg]))


def test_every_hosted_provider_is_marked_network_dependent_and_only_local_is_not():
    regs = backend_server._build_registrations()
    by = {(r["seam"], r["provider_name"]): r["network_dependent"] for r in regs}
    assert by[("EMBEDDING_PROVIDER", "local")] is False
    hosted = {k: v for k, v in by.items() if k != ("EMBEDDING_PROVIDER", "local")}
    assert hosted and all(hosted.values()), hosted


def test_the_local_embedder_wires_with_default_settings():
    local = [r for r in backend_server._build_registrations() if r["provider_name"] == "local"]
    out = compose_application(local, env={"EMBEDDING_PROVIDER": "local"})
    assert out["embedding_adapter"].provider_name == "local"


# ---------------- per-request cap ----------------

def test_cap_default_is_low_and_invalid_values_fall_back_to_it_never_to_unlimited():
    assert DEFAULT_MAX_LLM_CALLS_PER_REQUEST <= 6
    assert max_llm_calls_per_request({}) == DEFAULT_MAX_LLM_CALLS_PER_REQUEST
    for bad in ("", "abc", "0", "-3", "1.5"):
        assert max_llm_calls_per_request({"MAX_LLM_CALLS_PER_REQUEST": bad}) == DEFAULT_MAX_LLM_CALLS_PER_REQUEST
    assert max_llm_calls_per_request({"MAX_LLM_CALLS_PER_REQUEST": " 3 "}) == 3


class _Planner:
    def __init__(self):
        self.calls = 0

    def plan(self, prompt, config):
        self.calls += 1
        return {"decision": "COMPLETE"}


class _Llm:
    provider_name = "p"
    model_version_reported = "v"

    def __init__(self, error=None):
        self.calls, self.error = 0, error

    def invoke(self, system_prompt, user_prompt, config):
        self.calls += 1
        if self.error:
            raise self.error
        return "ok"


def test_planner_and_answer_calls_share_one_budget_and_the_extra_call_is_never_made():
    planner, llm = _Planner(), _Llm()
    bp, bl = BudgetedPlannerAdapter(planner), BudgetedLLMAdapter(llm)
    with request_budget(3):
        bp.plan("p", {})
        bl.invoke("s", "u", {})
        bp.plan("p", {})
        with pytest.raises(PlannerCallBudgetExceeded):
            bp.plan("p", {})
        with pytest.raises(LLMCallBudgetExceeded):
            bl.invoke("s", "u", {})
    assert (planner.calls, llm.calls) == (2, 1)           # 3 made, the 4th and 5th never reached the provider


def test_answer_retries_count_against_the_cap():
    llm = _Llm(error=LLMTransientError("429"))
    cfg = {**resolve_execution_config({"model_name": "m"}), "max_retry_attempts": 5}
    with request_budget(2):
        res, err, attempts, _ = invoke_with_retry("s", "u", BudgetedLLMAdapter(llm), cfg)
    assert llm.calls == 2 and res is None                 # the retry loop is cut off by the cap, not run 5 times
    assert isinstance(err, LLMCallBudgetExceeded)


def test_exceeding_the_cap_is_a_planner_failure_the_caller_can_handle():
    from scripts.stage21_agent_planning import PlannerInvocationError
    with request_budget(1):
        bp = BudgetedPlannerAdapter(_Planner())
        bp.plan("p", {})
        with pytest.raises(PlannerInvocationError) as e:
            bp.plan("p", {})
    assert e.value.code == "LLM_CALL_BUDGET_EXCEEDED"


def test_wrappers_delegate_attributes_the_pipeline_reads():
    assert BudgetedLLMAdapter(_Llm()).provider_name == "p"
    assert BudgetedLLMAdapter(_Llm()).model_version_reported == "v"


def test_no_budget_outside_a_request_means_no_cap():
    planner = _Planner()
    bp = BudgetedPlannerAdapter(planner)
    for _ in range(50):
        bp.plan("p", {})
    assert planner.calls == 50


def test_budgets_are_per_request_and_not_shared_between_threads():
    planner, results = _Planner(), []

    def one_request():
        with request_budget(2):
            bp = BudgetedPlannerAdapter(planner)
            bp.plan("p", {})
            bp.plan("p", {})
            try:
                bp.plan("p", {})
                results.append("over")
            except PlannerCallBudgetExceeded:
                results.append("capped")

    threads = [threading.Thread(target=one_request) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == ["capped"] * 4 and planner.calls == 8


def test_compose_application_wraps_both_adapters(monkeypatch):
    llm_reg = {"seam": "LLM_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _Llm()}
    pl_reg = {"seam": "PLANNER_LLM_PROVIDER", "provider_name": "x", "network_dependent": False, "factory": lambda s, c: _Planner()}
    env = {"LLM_PROVIDER": "x", "PLANNER_LLM_PROVIDER": "x", "PLANNER_ENABLED": "true"}
    out = compose_application([llm_reg, pl_reg], env=env)
    assert isinstance(out["llm_adapter"], BudgetedLLMAdapter)
    assert isinstance(out["agent_dependencies"].planner_llm_adapter, BudgetedPlannerAdapter)


def test_execute_request_gives_each_request_its_own_budget_from_the_environment(monkeypatch):
    monkeypatch.setenv("MAX_LLM_CALLS_PER_REQUEST", "2")
    seen = []

    def fake_plan_and_execute(agent_request, agent_dependencies):
        bp = BudgetedPlannerAdapter(_Planner())
        n = 0
        try:
            for _ in range(10):                            # bounded, so a missing budget fails the assertion instead of looping
                bp.plan("p", {})
                n += 1
        except PlannerCallBudgetExceeded:
            pass
        seen.append(n)
        return {"status": "ok"}

    monkeypatch.setattr("scripts.runtime_orchestration.plan_and_execute", fake_plan_and_execute)
    inst = {"agent_dependencies": Mock()}
    execute_request(inst, {"query": "q"})
    execute_request(inst, {"query": "q"})
    assert seen == [2, 2]                                  # a fresh budget each time, from MAX_LLM_CALLS_PER_REQUEST
