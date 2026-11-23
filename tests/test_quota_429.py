"""A 429 (quota exhausted) is never retried: one call, then stop. Fails on the code before this fix, where 429 was a transient error."""
from unittest.mock import Mock

import pytest
from google.genai import errors

from scripts.llm_provider_gemini import GeminiLLMAdapter
from scripts.planner_provider_gemini import GeminiPlannerLLMAdapter
from scripts.stage13_llm_execution import (
    LLMQuotaExhaustedError, LLMTransientError, invoke_with_retry, map_adapter_error, resolve_execution_config,
)
from scripts.stage21_agent_planning import PlannerInvocationError


def _client(code):
    c = Mock()
    c.models.generate_content.side_effect = errors.APIError(code, {"error": {"message": "quota"}}, None)
    return c


def test_429_is_a_quota_error_not_a_transient_one():
    with pytest.raises(LLMQuotaExhaustedError) as e:
        GeminiLLMAdapter(_client(429)).invoke("", "q", {"model_name": "m"})
    assert not isinstance(e.value, LLMTransientError)


def test_429_is_attempted_exactly_once_even_with_retries_allowed():
    client = _client(429)
    cfg = {**resolve_execution_config({"model_name": "m"}), "max_retry_attempts": 5}
    res, err, attempts, _ = invoke_with_retry("s", "u", GeminiLLMAdapter(client), cfg)
    assert res is None and isinstance(err, LLMQuotaExhaustedError)
    assert client.models.generate_content.call_count == 1 and attempts == 1


@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_server_errors_are_still_transient(code):
    with pytest.raises(LLMTransientError):
        GeminiLLMAdapter(_client(code)).invoke("", "q", {"model_name": "m"})


def test_quota_error_has_its_own_code():
    assert map_adapter_error(LLMQuotaExhaustedError("x")) == "LLM_INVOCATION_QUOTA_EXHAUSTED"


def test_planner_429_is_reported_as_quota_exhausted_and_called_once():
    client = _client(429)
    with pytest.raises(PlannerInvocationError) as e:
        GeminiPlannerLLMAdapter(client).plan("p", {"model_name": "m"})
    assert e.value.code == "QUOTA_EXHAUSTED"
    assert client.models.generate_content.call_count == 1


# ---- finish_reason must be read from the real SDK enum (str(enum) is 'FinishReason.STOP', not 'STOP') ----

def _resp(reason, text="OK"):
    from google.genai import types
    r = Mock()
    r.text = text
    r.candidates = [Mock(finish_reason=getattr(types.FinishReason, reason))]
    r.prompt_feedback = None
    r.usage_metadata = None
    r.model_version = "m"
    return r


@pytest.mark.parametrize("reason,expected", [("STOP", "complete"), ("MAX_TOKENS", "length"), ("SAFETY", "content_filter")])
def test_real_sdk_finish_reason_enum_is_mapped(reason, expected):
    c = Mock()
    c.models.generate_content.return_value = _resp(reason)
    assert GeminiLLMAdapter(c).invoke("", "q", {"model_name": "m"}).finish_reason == expected


def test_planner_safety_block_is_recognised_from_the_real_enum():
    c = Mock()
    c.models.generate_content.return_value = _resp("SAFETY", text="")
    with pytest.raises(PlannerInvocationError) as e:
        GeminiPlannerLLMAdapter(c).plan("p", {"model_name": "m"})
    assert e.value.code == "SAFETY_BLOCK"
