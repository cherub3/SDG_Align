"""Stage 17 — Response Caching.

Wraps Stage 13 LLM Execution with a deterministic caching layer.
"""

import sys
import hashlib
import json
import logging
import datetime
from typing import Any, Dict, List, Tuple, Optional
from abc import ABC, abstractmethod
from pathlib import Path

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage1_integrity import get_now_iso
from scripts.stage13_llm_execution import (
    LLMAdapter, 
    execute_prompt, 
    LLMExecutionInputError, 
    LLMExecutionInternalError
)

RESPONSE_CACHING_PIPELINE_VERSION = "1.0.0"
CACHEABLE_STATUSES = ("PASS", "PARTIAL")
DEFAULT_CACHE_TTL_SECONDS = 3600
MAX_CACHE_TTL_SECONDS = 604800

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage17_response_caching")

class ResponseCachingInputError(Exception):
    pass

class ResponseCachingInternalError(Exception):
    pass

class CacheAdapter(ABC):
    @property
    @abstractmethod
    def backend_name(self) -> str:
        pass

    @abstractmethod
    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def put(self, cache_key: str, entry: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def get_statistics(self) -> Dict[str, Any]:
        pass

def canonical_json(data: Any) -> bytes:
    """Serialize data to a stable, deterministic JSON byte string."""
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')

def validate_prompt_package_for_cache(package: Dict[str, Any]) -> None:
    if "prompt_package_id" not in package or not isinstance(package["prompt_package_id"], str):
        raise ResponseCachingInputError("PROMPT_PACKAGE_MALFORMED")
    if "status" not in package or not isinstance(package["status"], str):
        raise ResponseCachingInputError("PROMPT_PACKAGE_MALFORMED")

def resolve_execution_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if config is None or "model_name" not in config or not isinstance(config["model_name"], str):
        raise ResponseCachingInputError("EXECUTION_CONFIG_MALFORMED")
        
    res = {
        "model_name": config["model_name"]
    }
    
    if "temperature" in config:
        res["temperature"] = config["temperature"]
        
    mot = config.get("max_output_tokens", 2000)
    res["max_output_tokens"] = min(max(1, mot), 32000)
    
    return res

def compute_cache_key(prompt_package_id: str, model_name: str, resolved_execution_config: Dict[str, Any]) -> str:
    hash_input = {
        "prompt_package_id": prompt_package_id,
        "model_name": model_name,
        "execution_config": {
            "temperature": resolved_execution_config.get("temperature"),
            "max_output_tokens": resolved_execution_config["max_output_tokens"],
        }
    }
    return hashlib.sha256(canonical_json(hash_input)).hexdigest()

def validate_cache_entry(entry: Dict[str, Any]) -> bool:
    required_keys = ["cache_key", "llm_response", "prompt_package_id", "model_name", "cached_at"]
    if not all(k in entry for k in required_keys):
        return False
        
    llm_resp = entry["llm_response"]
    if not isinstance(llm_resp, dict):
        return False
        
    resp_keys = ["llm_response_id", "status", "prompt_package_id"]
    if not all(k in llm_resp for k in resp_keys):
        return False
        
    return True

def is_cache_entry_expired(entry: Dict[str, Any], cache_ttl_seconds: Optional[int]) -> bool:
    if cache_ttl_seconds is None:
        return False
    if cache_ttl_seconds == 0:
        return True
        
    try:
        cached_at = datetime.datetime.fromisoformat(entry["cached_at"].replace('Z', '+00:00'))
        now = datetime.datetime.fromisoformat(get_now_iso().replace('Z', '+00:00'))
        age_seconds = (now - cached_at).total_seconds()
        return age_seconds > cache_ttl_seconds
    except ValueError:
        return True # Malformed timestamp is treated as expired

def is_cacheable_status(status: str) -> bool:
    return status in CACHEABLE_STATUSES

def lookup_cache(cache_adapter: CacheAdapter, cache_key: str, cache_ttl_seconds: Optional[int]) -> Tuple[bool, Optional[Dict[str, Any]], List[Dict[str, str]]]:
    findings = []
    try:
        entry = cache_adapter.get(cache_key)
    except Exception as e:
        logger.warning(f"CACHE_READ_FAILED: {e}")
        findings.append({"severity": "WARNING", "code": "CACHE_READ_FAILED", "message": str(e)})
        return (False, None, findings)
        
    if entry is None:
        return (False, None, findings)
        
    if not validate_cache_entry(entry):
        findings.append({"severity": "WARNING", "code": "CACHE_ENTRY_MALFORMED", "message": "Cache entry is structurally invalid"})
        return (False, None, findings)
        
    if is_cache_entry_expired(entry, cache_ttl_seconds):
        findings.append({"severity": "WARNING", "code": "CACHE_ENTRY_EXPIRED", "message": "Cache entry is expired"})
        return (False, None, findings)
        
    return (True, entry, findings)

def store_cache_entry(cache_adapter: CacheAdapter, cache_key: str, llm_response: Dict[str, Any], prompt_package_id: str, model_name: str) -> Tuple[bool, List[Dict[str, str]]]:
    findings = []
    if not is_cacheable_status(llm_response["status"]):
        findings.append({
            "severity": "WARNING", 
            "code": "CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS", 
            "message": f"Write skipped for status {llm_response['status']}"
        })
        return False, findings
        
    entry = {
        "cache_key": cache_key,
        "llm_response": llm_response,
        "prompt_package_id": prompt_package_id,
        "model_name": model_name,
        "cached_at": get_now_iso()
    }
    
    try:
        cache_adapter.put(cache_key, entry)
        return True, findings
    except Exception as e:
        logger.warning(f"CACHE_WRITE_FAILED: {e}")
        findings.append({"severity": "WARNING", "code": "CACHE_WRITE_FAILED", "message": str(e)})
        return True, findings

def build_cached_execution_result(llm_response: Dict[str, Any], cache_key: str, cache_hit: bool, cached_at: str, cache_backend_name: str, findings: List[Dict[str, str]]) -> Dict[str, Any]:
    return {
        "response_caching_pipeline_version": RESPONSE_CACHING_PIPELINE_VERSION,
        "resolved_at": get_now_iso(),
        "cache_key": cache_key,
        "cache_hit": cache_hit,
        "status": llm_response["status"],
        "cached_at": cached_at,
        "cache_backend_name": cache_backend_name,
        "llm_response": llm_response,
        "findings": findings
    }

def validate_cached_execution_result(result: Dict[str, Any], prompt_package: Dict[str, Any], resolved_execution_config: Dict[str, Any], retrieved_entry_cache_key: Optional[str] = None) -> None:
    expected_cache_key = compute_cache_key(prompt_package["prompt_package_id"], resolved_execution_config["model_name"], resolved_execution_config)
    
    if result["cache_key"] != expected_cache_key:
        raise ResponseCachingInternalError("CACHE_KEY_FORMULA_MISMATCH")
        
    if result["cache_hit"] and retrieved_entry_cache_key is not None:
        if retrieved_entry_cache_key != result["cache_key"]:
            raise ResponseCachingInternalError("CACHE_KEY_SELF_MISMATCH")
            
    llm_resp = result["llm_response"]
    
    if is_cacheable_status(llm_resp["status"]):
        if llm_resp["llm_response_id"] != result["cache_key"]:
            raise ResponseCachingInternalError("CACHED_LLM_RESPONSE_ID_MISMATCH")
            
    if llm_resp["prompt_package_id"] != prompt_package["prompt_package_id"]:
        raise ResponseCachingInternalError("PROMPT_PACKAGE_ID_MISMATCH")
        
    cache_hit = result["cache_hit"]
    has_hit_finding = any(f["code"] == "CACHE_HIT" for f in result["findings"])
    has_miss_finding = any(f["code"] == "CACHE_MISS" for f in result["findings"])
    
    if cache_hit and not has_hit_finding:
        raise ResponseCachingInternalError("CACHE_HIT_FLAG_INCONSISTENT")
    if not cache_hit and not has_miss_finding:
        raise ResponseCachingInternalError("CACHE_HIT_FLAG_INCONSISTENT")
    if has_hit_finding and has_miss_finding:
        raise ResponseCachingInternalError("CACHE_HIT_FLAG_INCONSISTENT")
        
    if not is_cacheable_status(result["status"]):
        has_skip = any(f["code"] == "CACHE_WRITE_SKIPPED_NON_CACHEABLE_STATUS" for f in result["findings"])
        if not cache_hit and not has_skip:
            raise ResponseCachingInternalError("NON_CACHEABLE_STATUS_WRITTEN")

def execute_with_cache(
    prompt_package: Dict[str, Any], 
    llm_adapter: LLMAdapter, 
    cache_adapter: CacheAdapter, 
    execution_config: Optional[Dict[str, Any]] = None, 
    cache_ttl_seconds: Optional[int] = None
) -> Dict[str, Any]:
    
    validate_prompt_package_for_cache(prompt_package)
    resolved_config = resolve_execution_config(execution_config)
    
    if cache_ttl_seconds is not None:
        cache_ttl_seconds = min(max(0, cache_ttl_seconds), MAX_CACHE_TTL_SECONDS)
    else:
        cache_ttl_seconds = DEFAULT_CACHE_TTL_SECONDS
        
    prompt_package_id = prompt_package["prompt_package_id"]
    model_name = resolved_config["model_name"]
    cache_key = compute_cache_key(prompt_package_id, model_name, resolved_config)
    
    hit, entry, lookup_findings = lookup_cache(cache_adapter, cache_key, cache_ttl_seconds)
    
    findings = lookup_findings.copy()
    
    retrieved_entry_cache_key = None
    if hit and entry is not None:
        retrieved_entry_cache_key = entry["cache_key"]
        findings.append({"severity": "INFO", "code": "CACHE_HIT", "message": "Cache hit"})
        import copy
        llm_response = copy.deepcopy(entry["llm_response"])
        cached_at = entry["cached_at"]
    else:
        findings.append({"severity": "INFO", "code": "CACHE_MISS", "message": "Cache miss"})
        llm_response = execute_prompt(prompt_package, llm_adapter, execution_config)
        cached_at = get_now_iso()
        
        _attempted, store_findings = store_cache_entry(cache_adapter, cache_key, llm_response, prompt_package_id, model_name)
        findings.extend(store_findings)

    result = build_cached_execution_result(
        llm_response, 
        cache_key, 
        hit, 
        cached_at, 
        cache_adapter.backend_name, 
        findings
    )
    
    validate_cached_execution_result(result, prompt_package, resolved_config, retrieved_entry_cache_key)
            
    return result
