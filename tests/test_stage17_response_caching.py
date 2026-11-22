"""Tests for Stage 17 — Response Caching."""

import pytest
import datetime
from typing import Dict, Any, Optional

from scripts.stage1_integrity import get_now_iso
from scripts.stage13_llm_execution import (
    LLMAdapter, 
    RawLLMResult, 
    LLMExecutionInputError,
    LLMExecutionInternalError
)
from scripts.stage17_response_caching import (
    CacheAdapter,
    execute_with_cache,
    ResponseCachingInputError,
    ResponseCachingInternalError,
    compute_cache_key,
    RESPONSE_CACHING_PIPELINE_VERSION,
    validate_cached_execution_result
)

class StubLLMAdapter(LLMAdapter):
    def __init__(self, raw_result: RawLLMResult):
        self.provider_name = "stub"
        self.model_version_reported = "stub-v1"
        self.raw_result = raw_result
        self.invoke_count = 0

    def invoke(self, system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult:
        self.invoke_count += 1
        return self.raw_result

class InMemoryCacheAdapter(CacheAdapter):
    def __init__(self, backend_name="in_memory"):
        self._backend_name = backend_name
        self.store: Dict[str, Dict[str, Any]] = {}
        self.get_count = 0
        self.put_count = 0
        
    @property
    def backend_name(self) -> str:
        return self._backend_name

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        self.get_count += 1
        return self.store.get(cache_key)

    def put(self, cache_key: str, entry: Dict[str, Any]) -> None:
        self.put_count += 1
        self.store[cache_key] = entry

    def get_statistics(self) -> Dict[str, Any]:
        return {"size": len(self.store)}

class FaultyCacheAdapter(InMemoryCacheAdapter):
    def __init__(self, fail_get=False, fail_put=False):
        super().__init__()
        self.fail_get = fail_get
        self.fail_put = fail_put

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        if self.fail_get:
            raise RuntimeError("Backend get failed")
        return super().get(cache_key)

    def put(self, cache_key: str, entry: Dict[str, Any]) -> None:
        if self.fail_put:
            raise RuntimeError("Backend put failed")
        super().put(cache_key, entry)

def get_mock_prompt_package(status="PASS") -> Dict[str, Any]:
    return {
        "prompt_package_id": "pp-123",
        "status": status,
        "system_prompt": "You are a helpful assistant.",
        "user_prompt": "Hello",
        "findings": []
    }

def get_mock_execution_config() -> Dict[str, Any]:
    return {
        "model_name": "test-model",
        "temperature": 0.5,
        "max_output_tokens": 100,
        "timeout_seconds": 30,
        "max_retry_attempts": 2
    }

def get_success_raw_result() -> RawLLMResult:
    return RawLLMResult(
        response_text="Hi there!",
        finish_reason="complete",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        provider_request_id="req-123"
    )

def test_execute_with_cache_miss_then_hit():
    prompt_pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    # Call 1: Miss
    result1 = execute_with_cache(prompt_pkg, llm, cache, config)
    
    assert result1["cache_hit"] is False
    assert any(f["code"] == "CACHE_MISS" for f in result1["findings"])
    assert llm.invoke_count == 1
    assert cache.get_count == 1
    assert cache.put_count == 1
    
    cache_key = result1["cache_key"]
    assert cache_key in cache.store
    
    # Call 2: Hit
    result2 = execute_with_cache(prompt_pkg, llm, cache, config)
    
    assert result2["cache_hit"] is True
    assert any(f["code"] == "CACHE_HIT" for f in result2["findings"])
    assert llm.invoke_count == 1  # Did not invoke again
    assert cache.get_count == 2
    assert cache.put_count == 1   # Did not put again
    
    # Verify byte-identical LLMResponse returned on hit
    assert result1["llm_response"] == result2["llm_response"]
    assert result2["cache_key"] == cache_key

def test_cache_key_generation_deterministic():
    pkg = get_mock_prompt_package()
    config1 = {"model_name": "m1", "temperature": 0.5}
    config2 = {"model_name": "m1", "temperature": 0.5, "timeout_seconds": 999}
    
    llm = StubLLMAdapter(get_success_raw_result())
    cache1 = InMemoryCacheAdapter()
    cache2 = InMemoryCacheAdapter()
    
    res1 = execute_with_cache(pkg, llm, cache1, config1)
    res2 = execute_with_cache(pkg, llm, cache2, config2)
    
    # timeout_seconds does not affect cache key
    assert res1["cache_key"] == res2["cache_key"]

def test_malformed_prompt_package():
    pkg = {"prompt_package_id": "id"} # Missing status
    with pytest.raises(ResponseCachingInputError, match="PROMPT_PACKAGE_MALFORMED"):
        execute_with_cache(pkg, StubLLMAdapter(get_success_raw_result()), InMemoryCacheAdapter(), get_mock_execution_config())

def test_malformed_execution_config():
    pkg = get_mock_prompt_package()
    config = {"temperature": 0.5} # Missing model_name
    with pytest.raises(ResponseCachingInputError, match="EXECUTION_CONFIG_MALFORMED"):
        execute_with_cache(pkg, StubLLMAdapter(get_success_raw_result()), InMemoryCacheAdapter(), config)

def test_ttl_expiration():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    execute_with_cache(pkg, llm, cache, config)
    assert llm.invoke_count == 1
    
    # Immediately expired
    res2 = execute_with_cache(pkg, llm, cache, config, cache_ttl_seconds=0)
    assert res2["cache_hit"] is False
    assert any(f["code"] == "CACHE_ENTRY_EXPIRED" for f in res2["findings"])
    assert llm.invoke_count == 2 # Called again because of expiry

def test_non_cacheable_status():
    pkg = get_mock_prompt_package(status="FAIL")
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    # Assuming Stage 13 execute_prompt passes through the prompt package status if it fails validation?
    # Actually, Stage 13 generates a response and if the model fails, status becomes FAIL. 
    # For testing, we just need execute_prompt to return a FAIL status. 
    # Stage 13 returns status="PASS" for a successful invoke.
    # To mock a FAIL status from Stage 13 without rewriting execute_prompt, 
    # we can pass a malformed prompt package that Stage 13 fails on? 
    # But Stage 13 execute_prompt raises exceptions for malformed packages. 
    # Stage 13 sets status=FAIL if `invoke()` raises LLMContentPolicyError or LLMInvalidRequestError.
    
    class FailedStubLLMAdapter(StubLLMAdapter):
        def invoke(self, sys_p, usr_p, conf):
            self.invoke_count += 1
            raise LLMContentPolicyError("Blocked")
            
    res = execute_with_cache(pkg, FailedStubLLMAdapter(get_success_raw_result()), cache, config)
    
    assert res["cache_hit"] is False
    assert res["status"] == "SKIPPED"
    assert any(f["code"] == "CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS" for f in res["findings"])
    assert cache.put_count == 0 # No write attempted

def test_cache_backend_failures():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    
    # Fail GET
    cache = FaultyCacheAdapter(fail_get=True)
    res = execute_with_cache(pkg, llm, cache, config)
    assert res["cache_hit"] is False
    assert any(f["code"] == "CACHE_READ_FAILED" for f in res["findings"])
    assert cache.put_count == 1 # Still writes on miss
    
    # Fail PUT
    cache2 = FaultyCacheAdapter(fail_put=True)
    res2 = execute_with_cache(pkg, llm, cache2, config)
    assert res2["cache_hit"] is False
    assert any(f["code"] == "CACHE_WRITE_FAILED" for f in res2["findings"])

def test_invariant_cache_key_formula_mismatch():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    cache = InMemoryCacheAdapter()
    llm = StubLLMAdapter(get_success_raw_result())
    
    res = execute_with_cache(pkg, llm, cache, config)
    res["cache_key"] = "tampered"
    
    with pytest.raises(ResponseCachingInternalError, match="CACHE_KEY_FORMULA_MISMATCH"):
        validate_cached_execution_result(res, pkg, config)

def test_invariant_cached_llm_response_id_mismatch():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    cache = InMemoryCacheAdapter()
    llm = StubLLMAdapter(get_success_raw_result())
    
    res = execute_with_cache(pkg, llm, cache, config)
    res["llm_response"]["llm_response_id"] = "tampered"
    
    with pytest.raises(ResponseCachingInternalError, match="CACHED_LLM_RESPONSE_ID_MISMATCH"):
        validate_cached_execution_result(res, pkg, config)

def test_cache_key_unicode_normalization():
    pkg1 = get_mock_prompt_package()
    pkg1["prompt_package_id"] = "café" # e accent
    
    pkg2 = get_mock_prompt_package()
    pkg2["prompt_package_id"] = "cafe\u0301" # e + combining acute
    
    config = get_mock_execution_config()
    
    key1 = compute_cache_key(pkg1["prompt_package_id"], config["model_name"], config)
    key2 = compute_cache_key(pkg2["prompt_package_id"], config["model_name"], config)
    
    assert key1 != key2

def test_cache_key_deterministic_ordering():
    from scripts.stage17_response_caching import canonical_json
    dict1 = {"a": 1, "b": 2}
    dict2 = {"b": 2, "a": 1}
    assert canonical_json(dict1) == canonical_json(dict2)

def test_cache_overwrite_behavior():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    res1 = execute_with_cache(pkg, llm, cache, config)
    assert cache.put_count == 1
    
    # Force a miss by expiring the cache
    res2 = execute_with_cache(pkg, llm, cache, config, cache_ttl_seconds=0)
    assert res2["cache_hit"] is False
    assert cache.put_count == 2
    
    # Cache store size should still be 1
    assert len(cache.store) == 1

def test_immutable_cached_entry():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    execute_with_cache(pkg, llm, cache, config)
    
    res = execute_with_cache(pkg, llm, cache, config)
    res["llm_response"]["status"] = "TAMPERED"
    
    cached_entry = cache.get(res["cache_key"])
    assert cached_entry["llm_response"]["status"] == "PASS"

def test_immutable_upstream_artifact():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    import copy
    pkg_copy = copy.deepcopy(pkg)
    
    execute_with_cache(pkg, llm, cache, config)
    assert pkg == pkg_copy

def test_cache_eligibility_partial():
    pkg = get_mock_prompt_package(status="PARTIAL")
    config = get_mock_execution_config()
    
    class PartialLLMAdapter(StubLLMAdapter):
        def invoke(self, sys_p, usr_p, conf):
            self.invoke_count += 1
            raw = get_success_raw_result()
            raw.finish_reason = "length"
            return raw
            
    llm = PartialLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    res = execute_with_cache(pkg, llm, cache, config)
    assert res["status"] == "PARTIAL"
    assert cache.put_count == 1
    
    res2 = execute_with_cache(pkg, llm, cache, config)
    assert res2["cache_hit"] is True

def test_ttl_explicit_none_behavior():
    from scripts.stage17_response_caching import is_cache_entry_expired
    entry = {"cached_at": "2020-01-01T00:00:00Z"}
    assert is_cache_entry_expired(entry, None) is False

def test_ttl_expiration_boundary():
    from scripts.stage17_response_caching import is_cache_entry_expired
    now = get_now_iso()
    entry = {"cached_at": now}
    assert is_cache_entry_expired(entry, 0) is True
    assert is_cache_entry_expired(entry, 1) is False

def test_ttl_non_expired_entry():
    from scripts.stage17_response_caching import is_cache_entry_expired
    now = get_now_iso()
    entry = {"cached_at": now}
    assert is_cache_entry_expired(entry, 3600) is False

def test_invariant_cache_key_self_mismatch():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    cache = InMemoryCacheAdapter()
    llm = StubLLMAdapter(get_success_raw_result())
    
    execute_with_cache(pkg, llm, cache, config)
    res = execute_with_cache(pkg, llm, cache, config)
    
    with pytest.raises(ResponseCachingInternalError, match="CACHE_KEY_SELF_MISMATCH"):
        validate_cached_execution_result(res, pkg, config, retrieved_entry_cache_key="tampered")

def test_invariant_non_cacheable_status_written():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    cache = InMemoryCacheAdapter()
    llm = StubLLMAdapter(get_success_raw_result())
    
    res = execute_with_cache(pkg, llm, cache, config)
    res["status"] = "FAIL"
    
    with pytest.raises(ResponseCachingInternalError, match="NON_CACHEABLE_STATUS_WRITTEN"):
        validate_cached_execution_result(res, pkg, config, retrieved_entry_cache_key=None)

def test_invariant_cache_hit_flag_inconsistent():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    cache = InMemoryCacheAdapter()
    llm = StubLLMAdapter(get_success_raw_result())
    
    res = execute_with_cache(pkg, llm, cache, config)
    res["cache_hit"] = True
    
    with pytest.raises(ResponseCachingInternalError, match="CACHE_HIT_FLAG_INCONSISTENT"):
        validate_cached_execution_result(res, pkg, config, retrieved_entry_cache_key=None)

def test_invariant_prompt_package_id_mismatch():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    cache = InMemoryCacheAdapter()
    llm = StubLLMAdapter(get_success_raw_result())
    
    res = execute_with_cache(pkg, llm, cache, config)
    
    res["llm_response"]["prompt_package_id"] = "different"
    
    with pytest.raises(ResponseCachingInternalError, match="PROMPT_PACKAGE_ID_MISMATCH"):
        validate_cached_execution_result(res, pkg, config, retrieved_entry_cache_key=None)

def test_malformed_cache_entry():
    pkg = get_mock_prompt_package()
    config = get_mock_execution_config()
    llm = StubLLMAdapter(get_success_raw_result())
    cache = InMemoryCacheAdapter()
    
    res1 = execute_with_cache(pkg, llm, cache, config)
    
    cache_key = res1["cache_key"]
    del cache.store[cache_key]["llm_response"]
    
    res2 = execute_with_cache(pkg, llm, cache, config)
    
    assert res2["cache_hit"] is False
    assert any(f["code"] == "CACHE_ENTRY_MALFORMED" for f in res2["findings"])

