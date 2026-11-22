import json
import hashlib
import datetime
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from typing import TypedDict, Literal

TOOL_EXECUTION_VERSION = "1.0.0"
MAX_ARGUMENT_DEPTH = 10
MAX_ARGUMENT_SIZE_BYTES = 1_000_000
MAX_OUTPUT_SIZE_BYTES = 10_000_000

class Finding(TypedDict):
    severity: Literal["INFO", "WARNING", "FAIL"]
    code: str
    message: str

class ExecutionPolicy(TypedDict):
    max_timeout_seconds: int
    idempotent: bool
    side_effects: bool

class ToolDefinition(TypedDict):
    tool_name: str
    tool_version: str
    description: str
    parameter_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    execution_policy: ExecutionPolicy

class RequestContext(TypedDict, total=False):
    request_id: Optional[str]
    conversation_id: Optional[str]
    planning_step_id: Optional[str]

class ToolRequest(TypedDict):
    tool_name: str
    arguments: Dict[str, Any]
    request_context: RequestContext

class ExecutionMetadata(TypedDict):
    latency_ms: int
    adapter_status: Literal["success", "error"]

class RawToolResult(TypedDict):
    output: Optional[Dict[str, Any]]
    execution_metadata: ExecutionMetadata

class ToolExecutionRecord(TypedDict):
    tool_execution_record_id: str
    tool_execution_version: str
    tool_name: str
    tool_version: str
    arguments: Dict[str, Any]
    output: Optional[Dict[str, Any]]
    status: Literal["PASS", "FAIL"]
    latency_ms: Optional[int]
    request_context: RequestContext
    executed_at: str
    findings: List[Finding]
    tool_findings: List[Finding]

class ToolInvocationInputError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

class ToolExecutionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

class ToolInvocationInternalError(Exception):
    def __init__(self, code: str, message: str, original_exc: Optional[Exception] = None):
        super().__init__(message)
        self.code = code
        self.original_exc = original_exc

class ToolRegistry(ABC):
    @abstractmethod
    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        pass

    @abstractmethod
    def list_tools(self) -> List[ToolDefinition]:
        pass

class ToolAdapter(ABC):
    @abstractmethod
    def invoke(self, tool_name: str, arguments: Dict[str, Any], tool_definition: ToolDefinition) -> RawToolResult:
        pass

def validate_tool_request(tool_request: ToolRequest) -> None:
    if not isinstance(tool_request, dict):
        raise ToolInvocationInputError("TOOL_REQUEST_MALFORMED", "ToolRequest must be a dictionary.")
    if "tool_name" not in tool_request or not isinstance(tool_request["tool_name"], str):
        raise ToolInvocationInputError("TOOL_REQUEST_MALFORMED", "Missing or invalid tool_name.")
    if "arguments" not in tool_request or not isinstance(tool_request["arguments"], dict):
        raise ToolInvocationInputError("TOOL_REQUEST_MALFORMED", "Missing or invalid arguments.")
    if "request_context" in tool_request and not isinstance(tool_request["request_context"], dict):
        raise ToolInvocationInputError("TOOL_REQUEST_MALFORMED", "Invalid request_context.")

def resolve_tool(tool_name: str, registry: ToolRegistry) -> ToolDefinition:
    try:
        tool_def = registry.get_tool(tool_name)
    except Exception as e:
        raise ToolInvocationInternalError("TOOL_REGISTRY_ERROR", f"Registry lookup failed: {e}", original_exc=e) from e
    if tool_def is None:
        raise ToolInvocationInputError("TOOL_NOT_FOUND", f"Tool '{tool_name}' not found in registry.")
    return tool_def

def validate_arguments(arguments: Dict[str, Any], parameter_schema: Dict[str, Any]) -> None:
    if not isinstance(parameter_schema, dict):
        raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", "parameter_schema must be a dict.")
        
    try:
        serialized = json.dumps(arguments, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > MAX_ARGUMENT_SIZE_BYTES:
            raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Arguments exceed max size of {MAX_ARGUMENT_SIZE_BYTES} bytes.")
    except (TypeError, ValueError) as e:
        raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Arguments are not JSON serializable: {e}")
        
    def check_depth(obj: Any, current_depth: int) -> None:
        if current_depth > MAX_ARGUMENT_DEPTH:
            raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Arguments exceed max nesting depth of {MAX_ARGUMENT_DEPTH}.")
        if isinstance(obj, dict):
            for v in obj.values():
                check_depth(v, current_depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                check_depth(v, current_depth + 1)

    check_depth(arguments, 1)

    if parameter_schema.get("type") == "object":
        required = parameter_schema.get("required", [])
        if not isinstance(required, list):
            raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", "Invalid parameter schema: required is not a list")
        for req in required:
            if req not in arguments:
                raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Missing required argument: {req}")
        
        properties = parameter_schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", "Invalid parameter schema: properties is not a dict")
        for key, value in arguments.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type == "string" and not isinstance(value, str):
                    raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Argument {key} must be a string.")
                if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                    raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Argument {key} must be an integer.")
                if expected_type == "boolean" and not isinstance(value, bool):
                    raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Argument {key} must be a boolean.")
                if expected_type == "array" and not isinstance(value, list):
                    raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Argument {key} must be an array.")
                if expected_type == "object" and not isinstance(value, dict):
                    raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Argument {key} must be an object.")
                
                if expected_type == "integer":
                    min_val = properties[key].get("minimum")
                    max_val = properties[key].get("maximum")
                    if min_val is not None and value < min_val:
                        raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Argument {key} must be >= {min_val}.")
                    if max_val is not None and value > max_val:
                        raise ToolInvocationInputError("TOOL_ARGUMENTS_INVALID", f"Argument {key} must be <= {max_val}.")

def verify_execution_policy(execution_policy: Dict[str, Any]) -> None:
    if not isinstance(execution_policy, dict):
        raise ToolInvocationInputError("TOOL_POLICY_MALFORMED", "Execution policy must be a dict.")
    if "max_timeout_seconds" not in execution_policy or not isinstance(execution_policy["max_timeout_seconds"], int) or isinstance(execution_policy["max_timeout_seconds"], bool):
        raise ToolInvocationInputError("TOOL_POLICY_MALFORMED", "Missing or invalid max_timeout_seconds.")
    if "idempotent" not in execution_policy or not isinstance(execution_policy["idempotent"], bool):
        raise ToolInvocationInputError("TOOL_POLICY_MALFORMED", "Missing or invalid idempotent flag.")
    if "side_effects" not in execution_policy or not isinstance(execution_policy["side_effects"], bool):
        raise ToolInvocationInputError("TOOL_POLICY_MALFORMED", "Missing or invalid side_effects flag.")

def validate_tool_result(raw_result: RawToolResult, output_schema: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    
    if "output" not in raw_result:
        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message="Missing output field in raw result."))
        return findings
    
    output = raw_result.get("output")
    if output is None:
        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message="Output is null."))
        return findings
    
    if not isinstance(output, dict):
         findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message="Output is not an object."))
         return findings

    try:
        serialized = json.dumps(output, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > MAX_OUTPUT_SIZE_BYTES:
            findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message=f"Output exceeds {MAX_OUTPUT_SIZE_BYTES} bytes."))
    except (TypeError, ValueError):
        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message="Output is not JSON serializable."))

    if output_schema.get("type") == "object":
        properties = output_schema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in output.items():
                if key in properties:
                    expected_type = properties[key].get("type")
                    if expected_type == "array" and not isinstance(value, list):
                        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message=f"Output {key} is not an array."))
                    elif expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message=f"Output {key} is not an integer."))
                    elif expected_type == "string" and not isinstance(value, str):
                        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message=f"Output {key} is not a string."))
                    elif expected_type == "boolean" and not isinstance(value, bool):
                        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message=f"Output {key} is not a boolean."))
                    elif expected_type == "object" and not isinstance(value, dict):
                        findings.append(Finding(severity="WARNING", code="TOOL_OUTPUT_SCHEMA_VIOLATION", message=f"Output {key} is not an object."))

    return findings

def _compute_record_id(tool_name: str, tool_version: str, arguments: Dict[str, Any]) -> str:
    payload = {
        "tool_name": tool_name,
        "tool_version": tool_version,
        "arguments": arguments
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    hasher = hashlib.sha256(canonical_json.encode("utf-8"))
    return "ter_" + hasher.hexdigest()[:16]

def build_tool_execution_record(
    tool_request: ToolRequest,
    tool_definition: ToolDefinition,
    raw_result: Optional[RawToolResult],
    error_code: Optional[str],
    latency_ms: Optional[int]
) -> ToolExecutionRecord:
    
    findings: List[Finding] = []
    
    tool_findings: List[Finding] = [
        Finding(severity="INFO", code="TOOL_IDEMPOTENT", message=str(tool_definition["execution_policy"]["idempotent"])),
        Finding(severity="INFO", code="TOOL_SIDE_EFFECTS", message=str(tool_definition["execution_policy"]["side_effects"]))
    ]

    status: Literal["PASS", "FAIL"] = "PASS"
    output = None

    if error_code:
        status = "FAIL"
        findings.append(Finding(severity="FAIL", code="TOOL_INVOCATION_FAILED", message=f"Adapter error: {error_code}"))
    elif raw_result:
        if raw_result.get("execution_metadata", {}).get("adapter_status") == "error":
             status = "FAIL"
             output = None
             findings.append(Finding(severity="FAIL", code="TOOL_INVOCATION_FAILED", message="Adapter returned error status"))
        else:
             output = raw_result.get("output")
             schema_findings = validate_tool_result(raw_result, tool_definition["output_schema"])
             findings.extend(schema_findings)
        
        if latency_ms is not None and latency_ms > (tool_definition["execution_policy"]["max_timeout_seconds"] * 1000):
             findings.append(Finding(severity="WARNING", code="TOOL_LATENCY_EXCEEDED", message="Execution latency exceeded timeout."))
    else:
        status = "FAIL"
        findings.append(Finding(severity="FAIL", code="TOOL_INVOCATION_FAILED", message="No result returned"))
        
    record_id = _compute_record_id(tool_request["tool_name"], tool_definition["tool_version"], tool_request["arguments"])

    record: ToolExecutionRecord = {
        "tool_execution_record_id": record_id,
        "tool_execution_version": TOOL_EXECUTION_VERSION,
        "tool_name": tool_request["tool_name"],
        "tool_version": tool_definition["tool_version"],
        "arguments": tool_request["arguments"],
        "output": output,
        "status": status,
        "latency_ms": latency_ms,
        "request_context": tool_request.get("request_context", {}),
        "executed_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "findings": findings,
        "tool_findings": tool_findings
    }
    return record


def validate_tool_execution_record(record: ToolExecutionRecord) -> None:
    if record["status"] == "FAIL" and record["output"] is not None:
        raise ToolInvocationInternalError("RECORD_STATUS_OUTPUT_MISMATCH", "FAIL status must have null output")
    if record["status"] == "PASS" and record["output"] is None:
        raise ToolInvocationInternalError("RECORD_STATUS_OUTPUT_MISMATCH", "PASS status must have non-null output")
        
    if record["latency_ms"] is not None and record["latency_ms"] < 0:
        raise ToolInvocationInternalError("RECORD_LATENCY_INVALID", "latency_ms cannot be negative")
    if record["status"] == "PASS" and record["latency_ms"] is None:
        raise ToolInvocationInternalError("RECORD_LATENCY_INVALID", "PASS status must have non-null latency_ms")

    expected_id = _compute_record_id(record["tool_name"], record["tool_version"], record["arguments"])
    if record["tool_execution_record_id"] != expected_id:
        raise ToolInvocationInternalError("RECORD_ID_MISMATCH", "tool_execution_record_id does not match computed hash")


def execute_tool(tool_request: ToolRequest, tool_registry: ToolRegistry, tool_adapter: ToolAdapter) -> ToolExecutionRecord:
    validate_tool_request(tool_request)
    tool_definition = resolve_tool(tool_request["tool_name"], tool_registry)
    validate_arguments(tool_request["arguments"], tool_definition["parameter_schema"])
    verify_execution_policy(tool_definition["execution_policy"])
    
    raw_result = None
    error_code = None
    latency_ms = None
    
    try:
        raw_result = tool_adapter.invoke(tool_request["tool_name"], tool_request["arguments"], tool_definition)
        latency_ms = raw_result.get("execution_metadata", {}).get("latency_ms")
    except ToolExecutionError as e:
        error_code = e.code
    except Exception:
        error_code = "UNEXPECTED_ADAPTER_ERROR"
        
    record = build_tool_execution_record(tool_request, tool_definition, raw_result, error_code, latency_ms)
    
    if record["tool_name"] != tool_request["tool_name"]:
        raise ToolInvocationInternalError("RECORD_TOOL_NAME_MISMATCH", "Record tool_name differs from request")
    if record["tool_version"] != tool_definition["tool_version"]:
        raise ToolInvocationInternalError("RECORD_TOOL_VERSION_MISMATCH", "Record tool_version differs from definition")
    if record["arguments"] != tool_request["arguments"]:
         raise ToolInvocationInternalError("RECORD_ARGUMENTS_MISMATCH", "Record arguments differ from request")

    validate_tool_execution_record(record)
    
    return record
