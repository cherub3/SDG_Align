"""
Production ToolRegistry and ToolAdapter implementations for Stage 20.

InMemoryToolRegistry — dict-backed, accepts ToolDefinition objects via register().
CallableToolAdapter  — dispatches to Python callables keyed by tool_name.

Both are demo-grade: no persistence, no plugin loading, no dynamic discovery.
"""

import time
from typing import Callable, Dict, Any, List, Optional

from scripts.stage20_tool_function_calling import (
    ToolRegistry,
    ToolAdapter,
    ToolDefinition,
    RawToolResult,
    ExecutionMetadata,
    ToolExecutionError,
)


class InMemoryToolRegistry(ToolRegistry):
    """Dict-backed ToolRegistry.

    Duplicate registration silently replaces the previous definition — the
    last registered version of a given tool_name wins.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool_definition: ToolDefinition) -> None:
        self._tools[tool_definition["tool_name"]] = tool_definition

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        return self._tools.get(tool_name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())


class CallableToolAdapter(ToolAdapter):
    """ToolAdapter that dispatches each tool_name to a Python callable.

    handlers: mapping of tool_name -> callable(arguments) -> Dict[str, Any]
      The callable receives the validated arguments dict and must return a
      plain dict that becomes the RawToolResult output. Any exception other
      than ToolExecutionError is re-raised as ToolExecutionError with code
      TOOL_HANDLER_ERROR so Stage 20's execute_tool() can record it cleanly.
    """

    def __init__(self, handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]) -> None:
        self._handlers = handlers

    def invoke(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tool_definition: ToolDefinition,
    ) -> RawToolResult:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ToolExecutionError(
                "TOOL_HANDLER_NOT_FOUND",
                f"No callable handler registered for tool '{tool_name}'.",
            )

        start = time.monotonic()
        try:
            output = handler(arguments)
            latency_ms = int((time.monotonic() - start) * 1000)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(
                "TOOL_HANDLER_ERROR",
                f"Handler for '{tool_name}' raised an unexpected exception: {exc}",
            ) from exc

        return RawToolResult(
            output=output,
            execution_metadata=ExecutionMetadata(
                latency_ms=latency_ms,
                adapter_status="success",
            ),
        )
