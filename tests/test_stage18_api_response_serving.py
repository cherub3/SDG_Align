"""Tests for Stage 18 — API / Response Serving."""

import pytest
import copy
from typing import Dict, Any

from scripts.stage13_llm_execution import LLMAdapter, RawLLMResult
from scripts.stage17_response_caching import CacheAdapter
from scripts.stage18_api_response_serving import (
    handle_request,
    validate_api_request,
    assign_request_id,
    APIRequestInputError,
    APIResponseInternalError,
    PipelineOrchestrationError,
    PipelineDependencies
)
from unittest.mock import patch

@pytest.fixture(autouse=True)
def mock_prompt_template():
    with patch("scripts.stage12_prompt_construction.load_prompt_template") as mock_load:
        mock_load.return_value = ("System prompt", "User prompt {{query}} {{context_text}}", "1.0.0")
        yield mock_load

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

    def get(self, cache_key: str) -> dict:
        self.get_count += 1
        return self.store.get(cache_key)

    def put(self, cache_key: str, entry: dict) -> None:
        self.put_count += 1
        self.store[cache_key] = entry

    def get_statistics(self) -> dict:
        return {"size": len(self.store)}

def get_success_raw_result() -> RawLLMResult:
    return RawLLMResult(
        response_text="Test response",
        finish_reason="complete",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        provider_request_id="req-1"
    )

def mock_retrieve(request: Dict[str, Any]) -> Dict[str, Any]:
    mock_retrieve.call_count += 1
    return {
        "query": request["query"],
        "requested_index_fingerprints": request["index_fingerprints"],
        "searched_index_fingerprints": request["index_fingerprints"],
        "top_k": request.get("top_k", 10),
        "results": [{"chunk_id": "c1", "doc_id": "d1", "text": "Chunk text", "score": 0.9, "rank": 0, "index_fingerprint": "idx-1", "embedding_id": "e1"}],
        "status": "PASS",
        "findings": [{"severity": "INFO", "code": "SEARCHED", "message": "msg"}],
        "metadata_findings": []
    }
mock_retrieve.call_count = 0

def get_base_request() -> Dict[str, Any]:
    return {
        "query": "climate change",
        "index_fingerprints": ["idx-1"]
    }

def get_base_deps() -> PipelineDependencies:
    mock_retrieve.call_count = 0
    return {
        "retrieve": mock_retrieve,
        "llm_adapter": StubLLMAdapter(get_success_raw_result()),
        "cache_adapter": InMemoryCacheAdapter(),
        "default_model_name": "default-model"
    }

def test_request_validation_missing_query():
    req = get_base_request()
    del req["query"]
    with pytest.raises(APIRequestInputError, match="QUERY_MISSING_OR_INVALID_TYPE"):
        validate_api_request(req)

def test_request_validation_empty_fingerprints():
    req = get_base_request()
    req["index_fingerprints"] = []
    with pytest.raises(APIRequestInputError, match="INDEX_FINGERPRINTS_MISSING_OR_EMPTY"):
        validate_api_request(req)

def test_request_validation_unsupported_filters():
    req = get_base_request()
    req["filters"] = {"unsupported": "value"}
    with pytest.raises(APIRequestInputError, match="UNSUPPORTED_OPTION"):
        validate_api_request(req)

def test_request_validation_unsupported_pipeline_options():
    req = get_base_request()
    req["pipeline_options"] = {"unsupported_key": 42}
    with pytest.raises(APIRequestInputError, match="UNSUPPORTED_OPTION"):
        validate_api_request(req)

def test_request_validation_query_wrong_type():
    req = get_base_request()
    req["query"] = {"dict": "not string"}
    with pytest.raises(APIRequestInputError, match="QUERY_MISSING_OR_INVALID_TYPE"):
        validate_api_request(req)

def test_request_validation_index_fingerprints_wrong_type():
    req = get_base_request()
    req["index_fingerprints"] = "not_a_list"
    with pytest.raises(APIRequestInputError, match="INDEX_FINGERPRINTS_MISSING_OR_EMPTY"):
        validate_api_request(req)

def test_request_validation_malformed_pipeline_options():
    req = get_base_request()
    req["pipeline_options"] = {"top_k": "not an int"}
    with pytest.raises(APIRequestInputError, match="PIPELINE_OPTIONS_MALFORMED"):
        validate_api_request(req)

def test_request_validation_float_int_coercion():
    req = get_base_request()
    # It allows int for float (e.g. groundedness_threshold=1)
    req["pipeline_options"] = {"groundedness_threshold": 1}
    validate_api_request(req)

def test_successful_request_lifecycle():
    req = get_base_request()
    deps = get_base_deps()
    
    resp = handle_request(req, deps)
    
    # Assert successful orchestration
    assert resp["status"] == "SUCCESS"
    assert resp["api_pipeline_version"] == "1.0.0"
    assert "request_id" in resp
    assert resp["query"] == "climate change"
    assert resp["answer"]["response_text"] == "Test response"
    assert "groundedness_score" in resp["groundedness"]
    assert "answer_quality_score" in resp["quality"]
    
    # Check provenance
    assert resp["provenance"]["requested_index_fingerprints"] == ["idx-1"]
    assert "context_package_id" in resp["provenance"]
    assert "llm_response_id" in resp["provenance"]
    
    # Check pipeline findings are populated
    assert "retrieval" in resp["pipeline_findings"]
    assert len(resp["pipeline_findings"]["retrieval"]) > 0

def test_cache_hit_bypasses_llm():
    req = get_base_request()
    deps = get_base_deps()
    
    resp1 = handle_request(req, deps)
    assert deps["llm_adapter"].invoke_count == 1
    assert resp1["cache"]["cache_hit"] is False
    
    # Rerun identical request
    resp2 = handle_request(req, deps)
    
    # Should be a cache hit
    assert resp2["cache"]["cache_hit"] is True
    # LLM invoke count should NOT increase
    assert deps["llm_adapter"].invoke_count == 1

def test_determinism_excluding_metadata():
    req = get_base_request()
    deps = get_base_deps()
    
    resp1 = handle_request(req, deps)
    
    # Need to clear cache to do a deterministic rerun of the miss path
    deps["cache_adapter"].store.clear()
    resp2 = handle_request(req, deps)
    
    # Ensure they have different request IDs
    assert resp1["request_id"] != resp2["request_id"]
    
    # Exclude metadata for determinism check
    r1_compare = dict(resp1)
    r2_compare = dict(resp2)
    for k in ["request_id", "received_at", "resolved_at"]:
        r1_compare.pop(k)
        r2_compare.pop(k)
        
    # Exclude cache timestamps
    r1_compare["cache"] = dict(r1_compare["cache"])
    r2_compare["cache"] = dict(r2_compare["cache"])
    r1_compare["cache"].pop("cached_at")
    r2_compare["cache"].pop("cached_at")
    
    assert r1_compare == r2_compare

def test_model_name_defaulting():
    req = get_base_request()
    deps = get_base_deps()
    
    resp = handle_request(req, deps)
    
    assert any(f["code"] == "MODEL_NAME_DEFAULTED" for f in resp["findings"])

def test_upstream_immutability():
    req = get_base_request()
    req_copy = copy.deepcopy(req)
    deps = get_base_deps()
    
    handle_request(req, deps)
    
    assert req == req_copy

def test_error_mapping_pipeline_failure():
    req = get_base_request()
    deps = get_base_deps()
    
    from scripts.stage13_llm_execution import LLMContentPolicyError
    class BlockedLLMAdapter(StubLLMAdapter):
        def invoke(self, s, u, c):
            raise LLMContentPolicyError("blocked")
            
    deps["llm_adapter"] = BlockedLLMAdapter(get_success_raw_result())
    
    resp = handle_request(req, deps)
    
    assert resp["status"] == "PIPELINE_FAILURE"
    assert any(f["code"] == "PIPELINE_STATUS_FAILED" for f in resp["findings"])

def test_error_mapping_partial_success():
    from scripts.stage18_api_response_serving import map_pipeline_status
    assert map_pipeline_status("PARTIAL") == "PARTIAL_SUCCESS"

def test_error_mapping_skipped():
    from scripts.stage18_api_response_serving import map_pipeline_status
    assert map_pipeline_status("SKIPPED") == "PIPELINE_FAILURE"

def test_pipeline_status_partial_finding():
    req = get_base_request()
    deps = get_base_deps()
    
    with patch("scripts.stage18_api_response_serving.evaluate_answer_quality") as mock_eval:
        mock_eval.return_value = {"status": "PARTIAL", "findings": [], "answer_quality_report_id": "r1"}
        resp = handle_request(req, deps)
        
    assert resp["status"] == "PARTIAL_SUCCESS"
    assert any(f["code"] == "PIPELINE_STATUS_PARTIAL" for f in resp["findings"])

def test_internal_invariant_failure_propagates_loudly():
    from scripts.stage18_api_response_serving import validate_api_response
    
    # Create fake objects
    resp = {
        "status": "SUCCESS",
        "answer": {"response_text": "text", "spans": []},
        "request_id": "bad-uuid", # Will trigger REQUEST_ID_MISSING_OR_MALFORMED
        "pipeline_findings": {
            "retrieval": [], "context_assembly": [], "prompt_construction": [],
            "response_caching": [], "citation_extraction": [], "groundedness_validation": [],
            "answer_quality_evaluation": []
        }
    }
    
    with pytest.raises(APIResponseInternalError, match="REQUEST_ID_MISSING_OR_MALFORMED"):
        validate_api_response(
            response=resp,
            quality_report={"status": "PASS", "findings": []},
            retrieval_result={"findings": []},
            context_package={"findings": []},
            prompt_package={"findings": []},
            cached_result={"llm_response": {"response_text": "text"}, "findings": []},
            cited_response={"spans": [], "citation_findings": []},
            groundedness_report={"groundedness_findings": []}
        )

def test_internal_invariant_response_status_mismatch():
    from scripts.stage18_api_response_serving import validate_api_response
    resp = {
        "status": "SUCCESS",
        "answer": {"response_text": "text", "spans": []},
        "request_id": "12345678-1234-5678-1234-567812345678",
        "pipeline_findings": {
            "retrieval": [], "context_assembly": [], "prompt_construction": [],
            "response_caching": [], "citation_extraction": [], "groundedness_validation": [],
            "answer_quality_evaluation": []
        }
    }
    with pytest.raises(APIResponseInternalError, match="RESPONSE_STATUS_MAPPING_MISMATCH"):
        validate_api_response(
            response=resp,
            quality_report={"status": "FAIL", "findings": []}, # FAIL maps to PIPELINE_FAILURE, mismatching SUCCESS
            retrieval_result={"findings": []}, context_package={"findings": []},
            prompt_package={"findings": []}, cached_result={"llm_response": {"response_text": "text"}, "findings": []},
            cited_response={"spans": [], "citation_findings": []}, groundedness_report={"groundedness_findings": []}
        )

def test_internal_invariant_provenance_broken():
    from scripts.stage18_api_response_serving import validate_api_response
    resp = {
        "status": "SUCCESS",
        "answer": {"response_text": "text", "spans": []},
        "request_id": "12345678-1234-5678-1234-567812345678",
        "provenance": {"context_package_id": "bad-id"},
        "pipeline_findings": {
            "retrieval": [], "context_assembly": [], "prompt_construction": [],
            "response_caching": [], "citation_extraction": [], "groundedness_validation": [],
            "answer_quality_evaluation": []
        }
    }
    with pytest.raises(APIResponseInternalError, match="PROVENANCE_ID_CHAIN_BROKEN"):
        validate_api_response(
            response=resp,
            quality_report={"status": "PASS", "findings": []},
            retrieval_result={"findings": []}, context_package={"context_package_id": "good-id", "findings": []},
            prompt_package={"findings": []}, cached_result={"llm_response": {"response_text": "text"}, "findings": []},
            cited_response={"spans": [], "citation_findings": []}, groundedness_report={"groundedness_findings": []}
        )

def test_internal_invariant_answer_text_mismatch():
    from scripts.stage18_api_response_serving import validate_api_response
    resp = {
        "status": "SUCCESS",
        "answer": {"response_text": "bad text", "spans": []},
        "request_id": "12345678-1234-5678-1234-567812345678",
        "pipeline_findings": {
            "retrieval": [], "context_assembly": [], "prompt_construction": [],
            "response_caching": [], "citation_extraction": [], "groundedness_validation": [],
            "answer_quality_evaluation": []
        }
    }
    with pytest.raises(APIResponseInternalError, match="ANSWER_TEXT_MISMATCH"):
        validate_api_response(
            response=resp,
            quality_report={"status": "PASS", "findings": []},
            retrieval_result={"findings": []}, context_package={"findings": []},
            prompt_package={"findings": []}, cached_result={"llm_response": {"response_text": "good text"}, "findings": []},
            cited_response={"spans": [], "citation_findings": []}, groundedness_report={"groundedness_findings": []}
        )

def test_internal_invariant_spans_mismatch():
    from scripts.stage18_api_response_serving import validate_api_response
    resp = {
        "status": "SUCCESS",
        "answer": {"response_text": "text", "spans": [{"text": "bad"}]},
        "request_id": "12345678-1234-5678-1234-567812345678",
        "pipeline_findings": {
            "retrieval": [], "context_assembly": [], "prompt_construction": [],
            "response_caching": [], "citation_extraction": [], "groundedness_validation": [],
            "answer_quality_evaluation": []
        }
    }
    with pytest.raises(APIResponseInternalError, match="SPANS_MISMATCH"):
        validate_api_response(
            response=resp,
            quality_report={"status": "PASS", "findings": []},
            retrieval_result={"findings": []}, context_package={"findings": []},
            prompt_package={"findings": []}, cached_result={"llm_response": {"response_text": "text"}, "findings": []},
            cited_response={"spans": [{"text": "good"}], "citation_findings": []}, groundedness_report={"groundedness_findings": []}
        )

def test_internal_invariant_findings_incomplete():
    from scripts.stage18_api_response_serving import validate_api_response
    resp = {
        "status": "SUCCESS",
        "answer": {"response_text": "text", "spans": []},
        "request_id": "12345678-1234-5678-1234-567812345678",
        "pipeline_findings": {
            "retrieval": [{"severity": "INFO", "code": "BAD", "message": "msg"}], # Mismatched finding
            "context_assembly": [], "prompt_construction": [],
            "response_caching": [], "citation_extraction": [], "groundedness_validation": [],
            "answer_quality_evaluation": []
        }
    }
    with pytest.raises(APIResponseInternalError, match="PIPELINE_FINDINGS_INCOMPLETE"):
        validate_api_response(
            response=resp,
            quality_report={"status": "PASS", "findings": []},
            retrieval_result={"findings": [{"severity": "INFO", "code": "GOOD", "message": "msg"}]}, 
            context_package={"findings": []},
            prompt_package={"findings": []}, cached_result={"llm_response": {"response_text": "text"}, "findings": []},
            cited_response={"spans": [], "citation_findings": []}, groundedness_report={"groundedness_findings": []}
        )
