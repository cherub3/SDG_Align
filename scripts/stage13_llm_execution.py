"""Stage 13 — LLM Execution.

Turns a Stage 12 PromptPackage into an LLMResponse.
"""

import sys
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
from abc import ABC, abstractmethod

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage1_integrity import get_now_iso

LLM_EXECUTION_PIPELINE_VERSION = "1.0.0"
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 300
DEFAULT_MAX_OUTPUT_TOKENS = 2000
MAX_OUTPUT_TOKENS_CEILING = 32000
DEFAULT_MAX_RETRY_ATTEMPTS = 3
MAX_RETRY_ATTEMPTS_CEILING = 5
RETRY_BACKOFF_BASE_SECONDS = 1.0
RETRY_BACKOFF_MULTIPLIER = 2.0
FINISH_REASONS = ("complete", "length", "content_filter", "other")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage13_llm_execution")

class LLMExecutionInputError(Exception):
    pass

class LLMExecutionInternalError(Exception):
    pass

# Adapter Exceptions
class LLMTransientError(Exception):
    pass

class LLMAuthError(Exception):
    pass

class LLMContentPolicyError(Exception):
    pass

class LLMInvalidRequestError(Exception):
    pass

class LLMQuotaExhaustedError(LLMInvalidRequestError):
    """HTTP 429 / daily cap: the quota is spent. Never retried (a retry only burns more quota); callers stop the run."""


class RawLLMResult:
    def __init__(self, response_text: str, finish_reason: str, prompt_tokens: Optional[int], completion_tokens: Optional[int], total_tokens: Optional[int], provider_request_id: Optional[str]):
        self.response_text = response_text
        self.finish_reason = finish_reason
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.provider_request_id = provider_request_id

class LLMAdapter(ABC):
    provider_name: str
    model_version_reported: Optional[str]
    
    @abstractmethod
    def invoke(self, system_prompt: str, user_prompt: str, config: Dict[str, Any]) -> RawLLMResult:
        pass

def validate_prompt_package(package: Dict[str, Any]) -> None:
    required_keys = ["prompt_package_id", "status", "system_prompt", "user_prompt", "findings"]
    for k in required_keys:
        if k not in package:
            raise LLMExecutionInputError(f"PROMPT_PACKAGE_MALFORMED: missing key {k}")
            
    if not isinstance(package["findings"], list):
        raise LLMExecutionInputError("PROMPT_PACKAGE_MALFORMED: findings is not a list")

def resolve_execution_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if config is None:
        raise LLMExecutionInputError("LLMExecutionConfig must be provided and contain model_name")
        
    if "model_name" not in config or not config["model_name"]:
        raise LLMExecutionInputError("LLMExecutionConfig must contain model_name")
        
    res = {
        "model_name": config["model_name"]
    }
    
    if "temperature" in config:
        res["temperature"] = config["temperature"]
        
    mot = config.get("max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS)
    res["max_output_tokens"] = min(max(1, mot), MAX_OUTPUT_TOKENS_CEILING)
    
    ts = config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    res["timeout_seconds"] = min(max(1, ts), MAX_TIMEOUT_SECONDS)
    
    mra = config.get("max_retry_attempts", DEFAULT_MAX_RETRY_ATTEMPTS)
    res["max_retry_attempts"] = min(max(1, mra), MAX_RETRY_ATTEMPTS_CEILING)
    
    return res

def map_adapter_error(exception: Exception) -> str:
    if isinstance(exception, LLMQuotaExhaustedError):
        return "LLM_INVOCATION_QUOTA_EXHAUSTED"
    if isinstance(exception, LLMTransientError):
        # We don't distinguish rate-limit vs timeout cleanly here since both are LLMTransientError. 
        # But per Error Mapping table, timeout -> LLM_INVOCATION_TIMEOUT, rate/5xx -> LLM_INVOCATION_TRANSIENT_ERROR.
        # Without examining the message, we can just return LLM_INVOCATION_TRANSIENT_ERROR as a safe fallback 
        # or if the adapter subclassed it, we could. The architecture says "never inspects a message string 
        # or provider-specific type beyond the five-way closed vocabulary." Since LLMTransientError maps to 
        # either TIMEOUT or TRANSIENT_ERROR based on "timeout" vs "rate limit / 5xx", we will just emit 
        # LLM_INVOCATION_TRANSIENT_ERROR for simplicity unless we attach a flag.
        # Wait, the spec says "LLMTransientError (timeout) -> LLM_INVOCATION_TIMEOUT". So we must be able to tell.
        # Let's inspect `str(exception)` specifically for "timeout" as the only concession?
        # "never inspects a message string... entirely the adapter's own responsibility to classify correctly"
        # If the adapter classified it as LLMTransientError, it's one exception class. 
        # Let's look for a `is_timeout` property on the exception.
        if getattr(exception, "is_timeout", False):
            return "LLM_INVOCATION_TIMEOUT"
        return "LLM_INVOCATION_TRANSIENT_ERROR"
    if isinstance(exception, LLMAuthError):
        return "LLM_INVOCATION_AUTH_ERROR"
    if isinstance(exception, LLMContentPolicyError):
        return "LLM_INVOCATION_CONTENT_POLICY_ERROR"
    if isinstance(exception, LLMInvalidRequestError):
        return "LLM_INVOCATION_INVALID_REQUEST_ERROR"
    # Fallback for unexpected bugs in adapter
    return "LLM_INVOCATION_TRANSIENT_ERROR"

def invoke_with_retry(
    system_prompt: str, 
    user_prompt: str, 
    adapter: LLMAdapter, 
    config: Dict[str, Any]
) -> Tuple[Optional[RawLLMResult], Optional[Exception], int, int]:
    
    max_attempts = config["max_retry_attempts"]
    attempt = 1
    
    start_time = time.time()
    transient_errors = []
    
    while attempt <= max_attempts:
        try:
            res = adapter.invoke(system_prompt, user_prompt, config)
            latency_ms = int((time.time() - start_time) * 1000)
            res._transient_errors = transient_errors
            return res, None, attempt, latency_ms
        except Exception as e:
            if isinstance(e, LLMTransientError):
                if attempt == max_attempts:
                    latency_ms = int((time.time() - start_time) * 1000)
                    e._transient_errors = transient_errors
                    return None, e, attempt, latency_ms
                transient_errors.append(e)
                backoff = RETRY_BACKOFF_BASE_SECONDS * (RETRY_BACKOFF_MULTIPLIER ** (attempt - 1))
                time.sleep(backoff)
                attempt += 1
            else:
                latency_ms = int((time.time() - start_time) * 1000)
                e._transient_errors = transient_errors
                return None, e, attempt, latency_ms
                
    latency_ms = int((time.time() - start_time) * 1000)
    err = Exception("Unexpected Exhaustion")
    err._transient_errors = transient_errors
    return None, err, max_attempts, latency_ms

def build_llm_response(
    prompt_package: Dict[str, Any], 
    execution_config: Dict[str, Any],
    raw_result: Optional[RawLLMResult], 
    terminal_error_code: Optional[str], 
    attempt_count: int, 
    latency_ms: Optional[int]
) -> Dict[str, Any]:
    
    # Hash input
    hash_input = {
        "prompt_package_id": prompt_package["prompt_package_id"],
        "model_name": execution_config["model_name"],
        "execution_config": {
            "temperature": execution_config.get("temperature", None),
            "max_output_tokens": execution_config["max_output_tokens"]
        }
    }
        
    canonical_json = json.dumps(hash_input, separators=(',', ':'), sort_keys=True)
    pkg_id = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    # Determine status
    if prompt_package["status"] == "FAIL":
        status = "SKIPPED"
    elif terminal_error_code is not None:
        status = "FAIL"
    elif raw_result and raw_result.finish_reason == "length":
        status = "PARTIAL"
    else:
        status = "PASS"
        
    findings = []
    if raw_result and raw_result.finish_reason == "length":
        findings.append({
            "severity": "WARNING",
            "code": "LLM_RESPONSE_TRUNCATED",
            "message": "LLM response truncated due to length."
        })
        
    if raw_result and raw_result.finish_reason == "complete" and not raw_result.response_text:
        findings.append({
            "severity": "WARNING",
            "code": "LLM_RESPONSE_EMPTY",
            "message": "LLM returned empty response text."
        })
        
    # Build package
    res = {
        "llm_response_id": pkg_id,
        "llm_execution_pipeline_version": LLM_EXECUTION_PIPELINE_VERSION,
        "executed_at": get_now_iso(),
        "prompt_package_id": prompt_package["prompt_package_id"],
        "status": status,
        "provider_name": "unknown", # will be patched by execute_prompt
        "model_name": execution_config["model_name"],
        "model_version": None,
        "response_text": raw_result.response_text if raw_result else "",
        "finish_reason": raw_result.finish_reason if raw_result else None,
        "prompt_tokens": raw_result.prompt_tokens if raw_result else None,
        "completion_tokens": raw_result.completion_tokens if raw_result else None,
        "total_tokens": raw_result.total_tokens if raw_result else None,
        "latency_ms": latency_ms,
        "attempt_count": attempt_count,
        "provider_request_id": raw_result.provider_request_id if raw_result else None,
        "prompt_budget_tokens": prompt_package.get("prompt_budget_tokens"),
        "prompt_utilization": prompt_package.get("prompt_utilization"),
        "findings": findings,
        "prompt_findings": prompt_package.get("findings", [])
    }
    
    return res

def validate_llm_response(response: Dict[str, Any]) -> None:
    if response["status"] in ("SKIPPED", "FAIL") and response["response_text"] != "":
        raise LLMExecutionInternalError("RESPONSE_STATUS_TEXT_MISMATCH")
        
    if response["status"] in ("PASS", "PARTIAL") and response["response_text"] == "":
        has_empty = any(f["code"] == "LLM_RESPONSE_EMPTY" for f in response["findings"])
        if not has_empty:
            raise LLMExecutionInternalError("RESPONSE_STATUS_TEXT_MISMATCH")
            
    if response["status"] == "PASS" and response["finish_reason"] == "length":
        raise LLMExecutionInternalError("FINISH_REASON_STATUS_MISMATCH")
        
    if response["status"] == "PARTIAL" and response["finish_reason"] != "length":
        raise LLMExecutionInternalError("FINISH_REASON_STATUS_MISMATCH")
        
    pt = response["prompt_tokens"]
    ct = response["completion_tokens"]
    tt = response["total_tokens"]
    if pt is not None and ct is not None and tt is not None:
        if tt != pt + ct:
            raise LLMExecutionInternalError("TOKEN_COUNT_MISMATCH")
            
    ac = response["attempt_count"]
    if ac < 1 and response["status"] != "SKIPPED": # wait, SKIPPED attempt count should be 0
        raise LLMExecutionInternalError("ATTEMPT_COUNT_INVALID")
    
    if response["status"] == "SKIPPED" and ac != 0:
        raise LLMExecutionInternalError("ATTEMPT_COUNT_INVALID")

def execute_prompt(
    prompt_package: Dict[str, Any], 
    llm_adapter: LLMAdapter, 
    execution_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    
    validate_prompt_package(prompt_package)
    config = resolve_execution_config(execution_config)
    
    if prompt_package["status"] == "FAIL":
        res = build_llm_response(prompt_package, config, None, None, 0, None)
        res["findings"].append({
            "severity": "WARNING",
            "code": "LLM_INVOCATION_SKIPPED_UPSTREAM_FAIL",
            "message": "PromptPackage status was FAIL; skipping execution."
        })
        res["provider_name"] = llm_adapter.provider_name
        res["model_version"] = llm_adapter.model_version_reported
        validate_llm_response(res)
        if res["prompt_package_id"] != prompt_package["prompt_package_id"]:
            raise LLMExecutionInternalError("PROMPT_PACKAGE_ID_MISMATCH")
        return res
        
    raw_res, err, attempt_count, latency = invoke_with_retry(
        prompt_package["system_prompt"], 
        prompt_package["user_prompt"], 
        llm_adapter, 
        config
    )
    
    transient_errors = getattr(raw_res, '_transient_errors', []) if raw_res else getattr(err, '_transient_errors', [])
    
    terminal_code = None
    original_terminal_code = None
    if err:
        original_terminal_code = map_adapter_error(err)
        if original_terminal_code in ("LLM_INVOCATION_TIMEOUT", "LLM_INVOCATION_TRANSIENT_ERROR"):
            terminal_code = "LLM_RETRY_EXHAUSTED"
        else:
            terminal_code = original_terminal_code
            
    res = build_llm_response(prompt_package, config, raw_res, terminal_code, attempt_count, latency)
    
    for te in transient_errors:
        res["findings"].append({
            "severity": "WARNING",
            "code": map_adapter_error(te),
            "message": str(te)
        })
        
    if err:
        if original_terminal_code in ("LLM_INVOCATION_TIMEOUT", "LLM_INVOCATION_TRANSIENT_ERROR"):
            res["findings"].append({
                "severity": "WARNING",
                "code": original_terminal_code,
                "message": str(err)
            })
        res["findings"].append({
            "severity": "FAIL",
            "code": terminal_code,
            "message": str(err)
        })
        
    res["provider_name"] = llm_adapter.provider_name
    res["model_version"] = llm_adapter.model_version_reported
    
    # Check max bounds
    if res["status"] != "SKIPPED":
        if res["attempt_count"] > config["max_retry_attempts"]:
            raise LLMExecutionInternalError("ATTEMPT_COUNT_INVALID")
            
    validate_llm_response(res)
    if res["prompt_package_id"] != prompt_package["prompt_package_id"]:
        raise LLMExecutionInternalError("PROMPT_PACKAGE_ID_MISMATCH")
        
    return res
