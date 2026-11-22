"""
Unit and Stage 20 integration tests for InMemoryToolRegistry and CallableToolAdapter.
"""

import pytest
from scripts.tool_registry import InMemoryToolRegistry, CallableToolAdapter
from scripts.stage20_tool_function_calling import (
    ToolDefinition,
    ToolRequest,
    ToolExecutionError,
    ToolInvocationInputError,
    execute_tool,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _make_def(name: str = "echo", version: str = "1.0.0") -> ToolDefinition:
    return ToolDefinition(
        tool_name=name,
        tool_version=version,
        description="Echoes the input string.",
        parameter_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        output_schema={
            "type": "object",
            "properties": {"echo": {"type": "string"}},
        },
        execution_policy={
            "max_timeout_seconds": 5,
            "idempotent": True,
            "side_effects": False,
        },
    )


def _echo_handler(arguments: dict) -> dict:
    return {"echo": arguments["message"]}


def _make_request(name: str = "echo", args: dict | None = None) -> ToolRequest:
    return ToolRequest(
        tool_name=name,
        arguments=args if args is not None else {"message": "hello"},
        request_context={"request_id": "req-test-1"},
    )


# ── InMemoryToolRegistry ───────────────────────────────────────────────────────

class TestInMemoryToolRegistry:
    def test_empty_registry_get_returns_none(self):
        registry = InMemoryToolRegistry()
        assert registry.get_tool("anything") is None

    def test_empty_registry_list_returns_empty(self):
        registry = InMemoryToolRegistry()
        assert registry.list_tools() == []

    def test_register_and_get(self):
        registry = InMemoryToolRegistry()
        defn = _make_def()
        registry.register(defn)
        assert registry.get_tool("echo") is defn

    def test_list_tools_returns_all(self):
        registry = InMemoryToolRegistry()
        d1 = _make_def("tool_a")
        d2 = _make_def("tool_b")
        registry.register(d1)
        registry.register(d2)
        names = {t["tool_name"] for t in registry.list_tools()}
        assert names == {"tool_a", "tool_b"}

    def test_duplicate_registration_replaces(self):
        registry = InMemoryToolRegistry()
        registry.register(_make_def("echo", "1.0.0"))
        registry.register(_make_def("echo", "2.0.0"))
        assert registry.get_tool("echo")["tool_version"] == "2.0.0"
        assert len(registry.list_tools()) == 1

    def test_unknown_tool_returns_none(self):
        registry = InMemoryToolRegistry()
        registry.register(_make_def())
        assert registry.get_tool("nonexistent") is None


# ── CallableToolAdapter ────────────────────────────────────────────────────────

class TestCallableToolAdapter:
    def test_successful_invocation(self):
        adapter = CallableToolAdapter({"echo": _echo_handler})
        result = adapter.invoke("echo", {"message": "hello"}, _make_def())
        assert result["output"] == {"echo": "hello"}
        assert result["execution_metadata"]["adapter_status"] == "success"
        assert result["execution_metadata"]["latency_ms"] >= 0

    def test_missing_handler_raises_tool_execution_error(self):
        adapter = CallableToolAdapter({})
        with pytest.raises(ToolExecutionError) as exc_info:
            adapter.invoke("echo", {"message": "hi"}, _make_def())
        assert exc_info.value.code == "TOOL_HANDLER_NOT_FOUND"

    def test_handler_exception_raises_tool_execution_error(self):
        def bad_handler(args: dict) -> dict:
            raise RuntimeError("something went wrong")

        adapter = CallableToolAdapter({"echo": bad_handler})
        with pytest.raises(ToolExecutionError) as exc_info:
            adapter.invoke("echo", {"message": "hi"}, _make_def())
        assert exc_info.value.code == "TOOL_HANDLER_ERROR"

    def test_handler_tool_execution_error_propagates_unchanged(self):
        def failing_handler(args: dict) -> dict:
            raise ToolExecutionError("CUSTOM_CODE", "custom failure")

        adapter = CallableToolAdapter({"echo": failing_handler})
        with pytest.raises(ToolExecutionError) as exc_info:
            adapter.invoke("echo", {}, _make_def())
        assert exc_info.value.code == "CUSTOM_CODE"

    def test_latency_is_measured(self):
        adapter = CallableToolAdapter({"echo": _echo_handler})
        result = adapter.invoke("echo", {"message": "x"}, _make_def())
        assert isinstance(result["execution_metadata"]["latency_ms"], int)


# ── Stage 20 execute_tool integration ─────────────────────────────────────────

class TestStage20Integration:
    def _setup(self):
        registry = InMemoryToolRegistry()
        registry.register(_make_def())
        adapter = CallableToolAdapter({"echo": _echo_handler})
        return registry, adapter

    def test_successful_execution_returns_pass_record(self):
        registry, adapter = self._setup()
        record = execute_tool(_make_request(), registry, adapter)
        assert record["status"] == "PASS"
        assert record["output"] == {"echo": "hello"}
        assert record["tool_name"] == "echo"

    def test_unknown_tool_raises_input_error(self):
        registry, adapter = self._setup()
        with pytest.raises(ToolInvocationInputError) as exc_info:
            execute_tool(_make_request("no_such_tool"), registry, adapter)
        assert exc_info.value.code == "TOOL_NOT_FOUND"

    def test_missing_required_argument_raises_input_error(self):
        registry, adapter = self._setup()
        with pytest.raises(ToolInvocationInputError) as exc_info:
            execute_tool(_make_request(args={}), registry, adapter)
        assert exc_info.value.code == "TOOL_ARGUMENTS_INVALID"

    def test_handler_failure_produces_fail_record(self):
        registry = InMemoryToolRegistry()
        registry.register(_make_def())
        adapter = CallableToolAdapter({})  # no handler for "echo"
        record = execute_tool(_make_request(), registry, adapter)
        assert record["status"] == "FAIL"
        assert record["output"] is None

    def test_record_id_is_deterministic(self):
        registry, adapter = self._setup()
        r1 = execute_tool(_make_request(), registry, adapter)
        r2 = execute_tool(_make_request(), registry, adapter)
        assert r1["tool_execution_record_id"] == r2["tool_execution_record_id"]
