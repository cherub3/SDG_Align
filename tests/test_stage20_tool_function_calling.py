import pytest
import datetime
import json
from copy import deepcopy
from typing import Dict, Any, Optional, List

from scripts.stage20_tool_function_calling import (
    ToolDefinition,
    ToolRequest,
    RawToolResult,
    ToolExecutionRecord,
    ToolRegistry,
    ToolAdapter,
    ToolInvocationInputError,
    ToolExecutionError,
    ToolInvocationInternalError,
    execute_tool,
    validate_tool_request,
    resolve_tool,
    validate_arguments,
    verify_execution_policy,
    validate_tool_result,
    build_tool_execution_record,
    validate_tool_execution_record,
    _compute_record_id,
    MAX_ARGUMENT_DEPTH,
    MAX_ARGUMENT_SIZE_BYTES,
    MAX_OUTPUT_SIZE_BYTES
)

# --- Test Doubles ---

class DummyRegistry(ToolRegistry):
    def __init__(self, tools: Dict[str, ToolDefinition]):
        self.tools = tools
        self.call_count = 0

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        self.call_count += 1
        if tool_name == "error_tool":
             raise Exception("Simulated registry failure")
        return self.tools.get(tool_name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self.tools.values())

class DummyAdapter(ToolAdapter):
    def __init__(self):
        self.responses: Dict[str, RawToolResult] = {}
        self.errors: Dict[str, Exception] = {}

    def set_response(self, tool_name: str, response: RawToolResult):
        self.responses[tool_name] = response

    def set_error(self, tool_name: str, error: Exception):
        self.errors[tool_name] = error

    def invoke(self, tool_name: str, arguments: Dict[str, Any], tool_definition: ToolDefinition) -> RawToolResult:
        if tool_name in self.errors:
            raise self.errors[tool_name]
        return self.responses.get(tool_name, {
            "output": {"default": "output"},
            "execution_metadata": {"latency_ms": 100, "adapter_status": "success"}
        })


# --- Fixtures ---

@pytest.fixture
def sample_tool_definition() -> ToolDefinition:
    return {
        "tool_name": "search_docs",
        "tool_version": "1.0.0",
        "description": "Searches docs",
        "parameter_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100}
            },
            "required": ["query"]
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array"}
            }
        },
        "execution_policy": {
            "max_timeout_seconds": 30,
            "idempotent": True,
            "side_effects": False
        }
    }

@pytest.fixture
def sample_tool_request() -> ToolRequest:
    return {
        "tool_name": "search_docs",
        "arguments": {
            "query": "test query",
            "limit": 10
        },
        "request_context": {
            "request_id": "req_123"
        }
    }

@pytest.fixture
def registry(sample_tool_definition) -> DummyRegistry:
    return DummyRegistry({"search_docs": sample_tool_definition})

@pytest.fixture
def adapter() -> DummyAdapter:
    adapter = DummyAdapter()
    adapter.set_response("search_docs", {
        "output": {"results": ["doc1", "doc2"]},
        "execution_metadata": {"latency_ms": 150, "adapter_status": "success"}
    })
    return adapter

# --- Registry Tests ---

def test_registry_lookup_success(registry):
    tool = resolve_tool("search_docs", registry)
    assert tool["tool_name"] == "search_docs"
    assert registry.call_count == 1

def test_registry_unknown_tool(registry):
    with pytest.raises(ToolInvocationInputError) as exc:
        resolve_tool("unknown_tool", registry)
    assert exc.value.code == "TOOL_NOT_FOUND"

def test_registry_exception(registry):
    with pytest.raises(ToolInvocationInternalError) as exc:
        resolve_tool("error_tool", registry)
    assert exc.value.code == "TOOL_REGISTRY_ERROR"

def test_registry_immutable_consumption(registry):
    original_def = deepcopy(registry.get_tool("search_docs"))
    resolve_tool("search_docs", registry)
    assert registry.get_tool("search_docs") == original_def

# --- Tool Invocation Tests ---

def test_execute_tool_success(sample_tool_request, registry, adapter):
    record = execute_tool(sample_tool_request, registry, adapter)
    
    assert record["status"] == "PASS"
    assert record["tool_name"] == "search_docs"
    assert record["arguments"] == {"query": "test query", "limit": 10}
    assert record["output"] == {"results": ["doc1", "doc2"]}
    assert record["latency_ms"] == 150
    assert record["request_context"] == {"request_id": "req_123"}
    assert record["tool_execution_record_id"].startswith("ter_")
    
    # Should have informational findings from policy
    assert any(f["code"] == "TOOL_IDEMPOTENT" for f in record["tool_findings"])

def test_execute_tool_adapter_failure(sample_tool_request, registry, adapter):
    adapter.set_error("search_docs", ToolExecutionError("API_ERROR", "Remote server error"))
    record = execute_tool(sample_tool_request, registry, adapter)
    
    assert record["status"] == "FAIL"
    assert record["output"] is None
    assert any(f["code"] == "TOOL_INVOCATION_FAILED" and "API_ERROR" in f["message"] for f in record["findings"])

def test_execute_tool_unexpected_adapter_error(sample_tool_request, registry, adapter):
    adapter.set_error("search_docs", ValueError("Something broke inside adapter"))
    record = execute_tool(sample_tool_request, registry, adapter)
    
    assert record["status"] == "FAIL"
    assert record["output"] is None
    assert any(f["code"] == "TOOL_INVOCATION_FAILED" and "UNEXPECTED_ADAPTER_ERROR" in f["message"] for f in record["findings"])

def test_execute_tool_malformed_output(sample_tool_request, registry, adapter):
    adapter.set_response("search_docs", {
        "output": {"results": "not an array"}, # violates schema (results should be array)
        "execution_metadata": {"latency_ms": 150, "adapter_status": "success"}
    })
    record = execute_tool(sample_tool_request, registry, adapter)
    
    assert record["status"] == "PASS" # WARNINGs don't change PASS to FAIL
    assert record["output"] == {"results": "not an array"}
    assert any(f["code"] == "TOOL_OUTPUT_SCHEMA_VIOLATION" for f in record["findings"])

# --- Validation Tests ---

def test_validation_malformed_request():
    with pytest.raises(ToolInvocationInputError) as exc:
        validate_tool_request({"arguments": {}})
    assert exc.value.code == "TOOL_REQUEST_MALFORMED"

def test_validation_invalid_arguments(sample_tool_definition):
    with pytest.raises(ToolInvocationInputError) as exc:
        validate_arguments({"query": 123}, sample_tool_definition["parameter_schema"]) # query must be string
    assert exc.value.code == "TOOL_ARGUMENTS_INVALID"

    with pytest.raises(ToolInvocationInputError) as exc:
        validate_arguments({"limit": 10}, sample_tool_definition["parameter_schema"]) # missing required query
    assert exc.value.code == "TOOL_ARGUMENTS_INVALID"
    
    with pytest.raises(ToolInvocationInputError) as exc:
        validate_arguments({"query": "q", "limit": 200}, sample_tool_definition["parameter_schema"]) # limit max is 100
    assert exc.value.code == "TOOL_ARGUMENTS_INVALID"

def test_validation_policy_malformed():
    with pytest.raises(ToolInvocationInputError) as exc:
        verify_execution_policy({"max_timeout_seconds": "30"}) # must be int
    assert exc.value.code == "TOOL_POLICY_MALFORMED"

def test_validation_invariant_failures(sample_tool_request, sample_tool_definition):
    raw_result = {"output": {"results": []}, "execution_metadata": {"latency_ms": 100, "adapter_status": "success"}}
    record = build_tool_execution_record(sample_tool_request, sample_tool_definition, raw_result, None, 100)
    
    # Intentionally corrupt record
    record_corrupted = deepcopy(record)
    record_corrupted["status"] = "FAIL" # output is not none, should raise
    with pytest.raises(ToolInvocationInternalError) as exc:
        validate_tool_execution_record(record_corrupted)
    assert exc.value.code == "RECORD_STATUS_OUTPUT_MISMATCH"

    record_corrupted = deepcopy(record)
    record_corrupted["latency_ms"] = -5
    with pytest.raises(ToolInvocationInternalError) as exc:
        validate_tool_execution_record(record_corrupted)
    assert exc.value.code == "RECORD_LATENCY_INVALID"

    record_corrupted = deepcopy(record)
    record_corrupted["arguments"] = {"query": "modified"}
    # This alters the canonical content, making the ID mismatch
    with pytest.raises(ToolInvocationInternalError) as exc:
        validate_tool_execution_record(record_corrupted)
    assert exc.value.code == "RECORD_ID_MISMATCH"

# --- Serialization & Determinism Tests ---

def test_serialization_deterministic_ordering(sample_tool_request, sample_tool_definition):
    # Two requests with keys in different orders should produce identical IDs
    args1 = {"query": "test", "limit": 10}
    args2 = {"limit": 10, "query": "test"}
    
    id1 = _compute_record_id("search", "1.0", args1)
    id2 = _compute_record_id("search", "1.0", args2)
    assert id1 == id2

def test_serialization_unicode_utf8(sample_tool_request, sample_tool_definition, registry, adapter):
    sample_tool_request["arguments"]["query"] = "tést \u2022"
    record = execute_tool(sample_tool_request, registry, adapter)
    assert record["arguments"]["query"] == "tést \u2022"

def test_determinism_repeated_execution(sample_tool_request, registry, adapter):
    record1 = execute_tool(sample_tool_request, registry, adapter)
    record2 = execute_tool(sample_tool_request, registry, adapter)
    
    assert record1["tool_execution_record_id"] == record2["tool_execution_record_id"]

def test_argument_depth_and_size(sample_tool_definition):
    # Create deeply nested argument
    args = {"query": "test"}
    curr = args
    for _ in range(MAX_ARGUMENT_DEPTH + 1):
        curr["nest"] = {}
        curr = curr["nest"]
        
    with pytest.raises(ToolInvocationInputError) as exc:
        validate_arguments(args, sample_tool_definition["parameter_schema"])
    assert exc.value.code == "TOOL_ARGUMENTS_INVALID"
    assert "nesting depth" in exc.value.args[0]
    
    # Create too large argument
    large_str = "x" * (MAX_ARGUMENT_SIZE_BYTES + 10)
    with pytest.raises(ToolInvocationInputError) as exc:
         validate_arguments({"query": large_str}, sample_tool_definition["parameter_schema"])
    assert exc.value.code == "TOOL_ARGUMENTS_INVALID"
    assert "exceed max size" in exc.value.args[0]

def test_output_size_violation(sample_tool_request, registry, adapter):
    large_str = "x" * (MAX_OUTPUT_SIZE_BYTES + 10)
    adapter.set_response("search_docs", {
        "output": {"results": [large_str]},
        "execution_metadata": {"latency_ms": 150, "adapter_status": "success"}
    })
    record = execute_tool(sample_tool_request, registry, adapter)
    
    assert record["status"] == "PASS"
    assert any(f["code"] == "TOOL_OUTPUT_SCHEMA_VIOLATION" and "exceeds" in f["message"] for f in record["findings"])

def test_latency_exceeded(sample_tool_request, registry, adapter):
    adapter.set_response("search_docs", {
        "output": {"results": []},
        "execution_metadata": {"latency_ms": 35000, "adapter_status": "success"}
    })
    record = execute_tool(sample_tool_request, registry, adapter)
    
    assert record["status"] == "PASS"
    assert any(f["code"] == "TOOL_LATENCY_EXCEEDED" for f in record["findings"])
    assert not any(f["code"] == "TOOL_OUTPUT_SCHEMA_VIOLATION" for f in record["findings"]) # should be valid

from unittest.mock import patch

def test_invariant_tool_name_mismatch(sample_tool_request, sample_tool_definition, registry, adapter):
    # build a valid record then corrupt the tool_name
    valid_record = build_tool_execution_record(
        sample_tool_request, sample_tool_definition, adapter.invoke("search_docs", sample_tool_request["arguments"], sample_tool_definition), None, 100
    )
    valid_record["tool_name"] = "corrupted_name"
    
    with patch("scripts.stage20_tool_function_calling.build_tool_execution_record", return_value=valid_record):
        with pytest.raises(ToolInvocationInternalError) as exc:
            execute_tool(sample_tool_request, registry, adapter)
        assert exc.value.code == "RECORD_TOOL_NAME_MISMATCH"

def test_invariant_tool_version_mismatch(sample_tool_request, sample_tool_definition, registry, adapter):
    valid_record = build_tool_execution_record(
        sample_tool_request, sample_tool_definition, adapter.invoke("search_docs", sample_tool_request["arguments"], sample_tool_definition), None, 100
    )
    valid_record["tool_version"] = "9.9.9"
    
    with patch("scripts.stage20_tool_function_calling.build_tool_execution_record", return_value=valid_record):
        with pytest.raises(ToolInvocationInternalError) as exc:
            execute_tool(sample_tool_request, registry, adapter)
        assert exc.value.code == "RECORD_TOOL_VERSION_MISMATCH"

def test_invariant_arguments_mismatch(sample_tool_request, sample_tool_definition, registry, adapter):
    valid_record = build_tool_execution_record(
        sample_tool_request, sample_tool_definition, adapter.invoke("search_docs", sample_tool_request["arguments"], sample_tool_definition), None, 100
    )
    valid_record["arguments"] = {"corrupted": True}
    
    with patch("scripts.stage20_tool_function_calling.build_tool_execution_record", return_value=valid_record):
        with pytest.raises(ToolInvocationInternalError) as exc:
            execute_tool(sample_tool_request, registry, adapter)
        assert exc.value.code == "RECORD_ARGUMENTS_MISMATCH"

def test_record_immutability_is_documented_not_enforced(sample_tool_request, registry, adapter):
    # The architecture states the record is immutable after validation.
    # We verify this is a documented contract, not a runtime stricture (Python dicts are mutable).
    record = execute_tool(sample_tool_request, registry, adapter)
    
    record["status"] = "FAIL"
    assert record["status"] == "FAIL"  # Mutation succeeds, confirming it's not enforced natively
