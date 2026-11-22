import pytest
import time
from typing import Dict, Any, Optional

from scripts.stage13_llm_execution import (
    execute_prompt,
    validate_prompt_package,
    resolve_execution_config,
    map_adapter_error,
    LLMAdapter,
    RawLLMResult,
    LLMTransientError,
    LLMAuthError,
    LLMContentPolicyError,
    LLMInvalidRequestError,
    LLMExecutionInputError,
    LLMExecutionInternalError,
    validate_llm_response,
)

class MockLLMAdapter(LLMAdapter):
    def __init__(self, provider_name="mock_provider", version="1.0", behavior="pass", error_cls=None, attempts_before_success=1, text="Hello"):
        self.provider_name = provider_name
        self.model_version_reported = version
        self.behavior = behavior
        self.error_cls = error_cls
        self.attempts_before_success = attempts_before_success
        self.current_attempt = 0
        self.text = text
        self.invocations = 0
        
    def invoke(self, system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult:
        self.invocations += 1
        self.current_attempt += 1
        
        if self.current_attempt < self.attempts_before_success:
            if self.error_cls:
                err = self.error_cls("Mock error")
                if self.error_cls == LLMTransientError and self.behavior == "timeout":
                    err.is_timeout = True
                raise err
            raise Exception("Generic error")
            
        if self.behavior == "pass":
            return RawLLMResult(self.text, "complete", 10, 20, 30, "req-123")
        elif self.behavior == "partial":
            return RawLLMResult(self.text, "length", 10, 20, 30, "req-123")
        elif self.behavior == "empty":
            return RawLLMResult("", "complete", 10, 0, 10, "req-123")
        elif self.error_cls:
            err = self.error_cls("Terminal error")
            if self.error_cls == LLMTransientError and self.behavior == "timeout":
                err.is_timeout = True
            raise err
            
        return RawLLMResult(self.text, "complete", 10, 20, 30, "req-123")

def get_mock_prompt_package(status="PASS"):
    return {
        "prompt_package_id": "pkg_123",
        "status": status,
        "system_prompt": "System instructions",
        "user_prompt": "User query",
        "findings": [{"code": "UPSTREAM", "severity": "WARNING"}]
    }
    
def test_validate_prompt_package():
    pkg = get_mock_prompt_package()
    validate_prompt_package(pkg)
    
    del pkg["system_prompt"]
    with pytest.raises(LLMExecutionInputError, match="PROMPT_PACKAGE_MALFORMED"):
        validate_prompt_package(pkg)
        
def test_resolve_execution_config():
    with pytest.raises(LLMExecutionInputError):
        resolve_execution_config(None)
        
    with pytest.raises(LLMExecutionInputError):
        resolve_execution_config({"temperature": 0.5})
        
    res = resolve_execution_config({"model_name": "claude-3-haiku-20240307"})
    assert res["model_name"] == "claude-3-haiku-20240307"
    assert res["max_output_tokens"] == 2000
    assert res["timeout_seconds"] == 60
    assert res["max_retry_attempts"] == 3
    
def test_execute_prompt_pass():
    adapter = MockLLMAdapter()
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "PASS"
    assert res["response_text"] == "Hello"
    assert res["finish_reason"] == "complete"
    assert res["prompt_tokens"] == 10
    assert res["total_tokens"] == 30
    assert res["attempt_count"] == 1
    assert adapter.invocations == 1
    assert res["prompt_findings"] == [{"code": "UPSTREAM", "severity": "WARNING"}]
    
def test_execute_prompt_partial():
    adapter = MockLLMAdapter(behavior="partial")
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "PARTIAL"
    assert res["response_text"] == "Hello"
    assert res["finish_reason"] == "length"
    assert any(f["code"] == "LLM_RESPONSE_TRUNCATED" for f in res["findings"])

def test_execute_prompt_empty():
    adapter = MockLLMAdapter(behavior="empty")
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "PASS"
    assert res["response_text"] == ""
    assert any(f["code"] == "LLM_RESPONSE_EMPTY" for f in res["findings"])

def test_execute_prompt_skipped():
    adapter = MockLLMAdapter()
    pkg = get_mock_prompt_package(status="FAIL")
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "SKIPPED"
    assert res["response_text"] == ""
    assert res["attempt_count"] == 0
    assert adapter.invocations == 0
    assert any(f["code"] == "LLM_INVOCATION_SKIPPED_UPSTREAM_FAIL" for f in res["findings"])

def test_execute_prompt_retry_success(monkeypatch):
    import scripts.stage13_llm_execution as stage13
    monkeypatch.setattr(stage13, "RETRY_BACKOFF_BASE_SECONDS", 0.01)
    
    adapter = MockLLMAdapter(error_cls=LLMTransientError, attempts_before_success=2)
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "PASS"
    assert adapter.invocations == 2
    assert res["attempt_count"] == 2
    assert len([f for f in res["findings"] if f["code"] == "LLM_INVOCATION_TRANSIENT_ERROR"]) == 1
    
def test_execute_prompt_retry_exhausted(monkeypatch):
    import scripts.stage13_llm_execution as stage13
    monkeypatch.setattr(stage13, "RETRY_BACKOFF_BASE_SECONDS", 0.01)
    
    adapter = MockLLMAdapter(error_cls=LLMTransientError, attempts_before_success=99)
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1", "max_retry_attempts": 3})
    
    assert res["status"] == "FAIL"
    assert res["response_text"] == ""
    assert adapter.invocations == 3
    assert res["attempt_count"] == 3
    assert any(f["code"] == "LLM_RETRY_EXHAUSTED" for f in res["findings"])
    assert len([f for f in res["findings"] if f["code"] == "LLM_INVOCATION_TRANSIENT_ERROR"]) == 3

def test_execute_prompt_auth_error():
    adapter = MockLLMAdapter(error_cls=LLMAuthError, attempts_before_success=99)
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "FAIL"
    assert adapter.invocations == 1
    assert any(f["code"] == "LLM_INVOCATION_AUTH_ERROR" for f in res["findings"])
    
def test_execute_prompt_content_policy():
    adapter = MockLLMAdapter(error_cls=LLMContentPolicyError, attempts_before_success=99)
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "FAIL"
    assert adapter.invocations == 1
    assert any(f["code"] == "LLM_INVOCATION_CONTENT_POLICY_ERROR" for f in res["findings"])
    
def test_execute_prompt_invalid_request():
    adapter = MockLLMAdapter(error_cls=LLMInvalidRequestError, attempts_before_success=99)
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1"})
    
    assert res["status"] == "FAIL"
    assert adapter.invocations == 1
    assert any(f["code"] == "LLM_INVOCATION_INVALID_REQUEST_ERROR" for f in res["findings"])
    
def test_execute_prompt_timeout(monkeypatch):
    import scripts.stage13_llm_execution as stage13
    monkeypatch.setattr(stage13, "RETRY_BACKOFF_BASE_SECONDS", 0.01)
    
    adapter = MockLLMAdapter(behavior="timeout", error_cls=LLMTransientError, attempts_before_success=99)
    pkg = get_mock_prompt_package()
    res = execute_prompt(pkg, adapter, {"model_name": "model1", "max_retry_attempts": 2})
    
    assert res["status"] == "FAIL"
    assert adapter.invocations == 2
    assert len([f for f in res["findings"] if f["code"] == "LLM_INVOCATION_TIMEOUT"]) == 2
    assert any(f["code"] == "LLM_RETRY_EXHAUSTED" for f in res["findings"])
    
def test_determinism():
    adapter1 = MockLLMAdapter(text="One")
    adapter2 = MockLLMAdapter(text="Two")
    
    pkg = get_mock_prompt_package()
    config = {"model_name": "model1"}
    
    res1 = execute_prompt(pkg, adapter1, config)
    res2 = execute_prompt(pkg, adapter2, config)
    
    assert res1["llm_response_id"] == res2["llm_response_id"]
    assert res1["response_text"] != res2["response_text"]
    
def test_validate_llm_response_invariants():
    pkg = get_mock_prompt_package()
    config = {"model_name": "model"}
    adapter = MockLLMAdapter()
    res = execute_prompt(pkg, adapter, config)
    
    # 1. RESPONSE_STATUS_TEXT_MISMATCH
    r1 = res.copy()
    r1["status"] = "FAIL"
    r1["response_text"] = "should be empty"
    with pytest.raises(LLMExecutionInternalError, match="RESPONSE_STATUS_TEXT_MISMATCH"):
        validate_llm_response(r1)
        
    r1b = res.copy()
    r1b["status"] = "PASS"
    r1b["response_text"] = ""
    r1b["findings"] = [] # no empty finding
    with pytest.raises(LLMExecutionInternalError, match="RESPONSE_STATUS_TEXT_MISMATCH"):
        validate_llm_response(r1b)
        
    # 2. FINISH_REASON_STATUS_MISMATCH
    r2 = res.copy()
    r2["finish_reason"] = "length"
    # status is PASS in res
    with pytest.raises(LLMExecutionInternalError, match="FINISH_REASON_STATUS_MISMATCH"):
        validate_llm_response(r2)
        
    r2b = res.copy()
    r2b["status"] = "PARTIAL"
    r2b["finish_reason"] = "complete"
    with pytest.raises(LLMExecutionInternalError, match="FINISH_REASON_STATUS_MISMATCH"):
        validate_llm_response(r2b)
        
    # 3. TOKEN_COUNT_MISMATCH
    r3 = res.copy()
    r3["total_tokens"] = 999
    with pytest.raises(LLMExecutionInternalError, match="TOKEN_COUNT_MISMATCH"):
        validate_llm_response(r3)
        
    # 4. ATTEMPT_COUNT_INVALID
    r4 = res.copy()
    r4["attempt_count"] = 0
    with pytest.raises(LLMExecutionInternalError, match="ATTEMPT_COUNT_INVALID"):
        validate_llm_response(r4)
        
    r4b = res.copy()
    r4b["status"] = "SKIPPED"
    r4b["attempt_count"] = 1
    # also fix response_text to avoid mismatch
    r4b["response_text"] = ""
    with pytest.raises(LLMExecutionInternalError, match="ATTEMPT_COUNT_INVALID"):
        validate_llm_response(r4b)

def test_execute_prompt_id_mismatch(monkeypatch):
    import scripts.stage13_llm_execution as stage13
    
    original_build = stage13.build_llm_response
    
    def tampered_build(*args, **kwargs):
        res = original_build(*args, **kwargs)
        res["prompt_package_id"] = "TAMPERED_ID"
        return res
        
    monkeypatch.setattr(stage13, "build_llm_response", tampered_build)
    
    adapter = MockLLMAdapter()
    pkg = get_mock_prompt_package()
    config = {"model_name": "model1"}
    
    with pytest.raises(LLMExecutionInternalError, match="PROMPT_PACKAGE_ID_MISMATCH"):
        stage13.execute_prompt(pkg, adapter, config)
