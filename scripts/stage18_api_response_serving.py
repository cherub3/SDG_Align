"""Stage 18 — API / Response Serving."""

import uuid
from typing import Dict, Any, List, Optional, Callable, TypedDict
from copy import deepcopy
import json
import logging

from scripts.stage1_integrity import get_now_iso

# Import dependencies from upstream stages
from scripts.stage11_context_assembly import assemble_context
from scripts.stage12_prompt_construction import construct_prompt
from scripts.stage13_llm_execution import LLMAdapter
from scripts.stage17_response_caching import CacheAdapter, execute_with_cache
from scripts.stage14_citation_extraction import extract_citations
from scripts.stage15_groundedness_validation import validate_groundedness
from scripts.stage16_answer_quality_evaluation import evaluate_answer_quality

logger = logging.getLogger("stage18_api_response_serving")

class APIRequestInputError(Exception):
    """Raised when an APIRequest is structurally malformed."""
    pass

class APIResponseInternalError(Exception):
    """Raised when internal invariant self-checks fail for the assembled APIResponse."""
    pass

class PipelineOrchestrationError(Exception):
    """Raised when an internal error occurs during orchestration."""
    pass

class PipelineDependencies(TypedDict):
    """Deployment-level dependencies for Stage 18."""
    retrieve: Callable[[Dict[str, Any]], Dict[str, Any]]
    llm_adapter: LLMAdapter
    cache_adapter: CacheAdapter
    default_model_name: str

API_PIPELINE_VERSION = "1.0.0"

SUPPORTED_FILTER_KEYS = ("category", "doc_type", "doc_ids")
SUPPORTED_PIPELINE_OPTION_KEYS = (
    "top_k", "context_budget_tokens", "template_version", "prompt_budget_tokens",
    "model_name", "temperature", "max_output_tokens", "timeout_seconds", "max_retry_attempts",
    "cache_ttl_seconds", "citation_match_threshold", "groundedness_threshold",
)

_PIPELINE_OPTION_TYPES = {
    "top_k": int,
    "context_budget_tokens": int,
    "template_version": str,
    "prompt_budget_tokens": int,
    "model_name": str,
    "temperature": float,
    "max_output_tokens": int,
    "timeout_seconds": int,
    "max_retry_attempts": int,
    "cache_ttl_seconds": int,
    "citation_match_threshold": float,
    "groundedness_threshold": float
}

def validate_api_request(request: Dict[str, Any]) -> None:
    """Validates the structural shape of the APIRequest."""
    if "query" not in request or not isinstance(request["query"], str):
        raise APIRequestInputError("QUERY_MISSING_OR_INVALID_TYPE")
    
    if "index_fingerprints" not in request or not isinstance(request["index_fingerprints"], list) or len(request["index_fingerprints"]) == 0:
        raise APIRequestInputError("INDEX_FINGERPRINTS_MISSING_OR_EMPTY")
        
    if "filters" in request and request["filters"] is not None:
        if not isinstance(request["filters"], dict):
             raise APIRequestInputError("UNSUPPORTED_OPTION")
        for key in request["filters"].keys():
            if key not in SUPPORTED_FILTER_KEYS:
                raise APIRequestInputError("UNSUPPORTED_OPTION")
                
    if "pipeline_options" in request and request["pipeline_options"] is not None:
        if not isinstance(request["pipeline_options"], dict):
            raise APIRequestInputError("PIPELINE_OPTIONS_MALFORMED")
        for key, value in request["pipeline_options"].items():
            if key not in SUPPORTED_PIPELINE_OPTION_KEYS:
                raise APIRequestInputError("UNSUPPORTED_OPTION")
            if value is not None and not isinstance(value, _PIPELINE_OPTION_TYPES[key]):
                if _PIPELINE_OPTION_TYPES[key] == float and isinstance(value, int):
                    continue
                raise APIRequestInputError("PIPELINE_OPTIONS_MALFORMED")

def assign_request_id() -> str:
    """Generates a fresh, random, per-call request ID."""
    return str(uuid.uuid4())

def build_retrieval_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Constructs a RetrievalRequest from the validated APIRequest."""
    retrieval_req = {
        "query": request["query"],
        "index_fingerprints": request["index_fingerprints"]
    }
    
    if "filters" in request and request["filters"] is not None:
        retrieval_req["filters"] = request["filters"]
        
    opts = request.get("pipeline_options") or {}
    if "top_k" in opts and opts["top_k"] is not None:
        retrieval_req["top_k"] = opts["top_k"]
        
    return retrieval_req

def resolve_execution_config_for_api(request: Dict[str, Any], deps: PipelineDependencies) -> Dict[str, Any]:
    """Resolves pipeline options or fallbacks for Stage 13 LLM execution."""
    opts = request.get("pipeline_options") or {}
    
    config = {}
    
    if "model_name" in opts and opts["model_name"] is not None:
        config["model_name"] = opts["model_name"]
    else:
        config["model_name"] = deps["default_model_name"]
        
    for key in ["temperature", "max_output_tokens", "timeout_seconds", "max_retry_attempts"]:
        if key in opts and opts[key] is not None:
            config[key] = opts[key]
            
    return config

def map_pipeline_status(quality_status: str) -> str:
    """Maps the pipeline terminal status to the transport-agnostic response category."""
    if quality_status == "PASS":
        return "SUCCESS"
    elif quality_status == "PARTIAL":
        return "PARTIAL_SUCCESS"
    elif quality_status in ("FAIL", "SKIPPED"):
        return "PIPELINE_FAILURE"
    else:
        return "PIPELINE_FAILURE"

def build_api_response(
    request_id: str,
    received_at: str,
    resolved_at: str,
    retrieval_result: Dict[str, Any],
    context_package: Dict[str, Any],
    prompt_package: Dict[str, Any],
    cached_result: Dict[str, Any],
    cited_response: Dict[str, Any],
    groundedness_report: Dict[str, Any],
    quality_report: Dict[str, Any],
    response_status: str,
    findings: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Assembles the final APIResponse payload."""
    llm_response = cached_result["llm_response"]
    
    pipeline_findings = {
        "retrieval": retrieval_result.get("findings", []),
        "context_assembly": context_package.get("findings", []),
        "prompt_construction": prompt_package.get("findings", []),
        "response_caching": cached_result.get("findings", []),
        "citation_extraction": cited_response.get("citation_findings", []),
        "groundedness_validation": groundedness_report.get("groundedness_findings", []),
        "answer_quality_evaluation": quality_report.get("findings", [])
    }
    
    provenance = {
        "requested_index_fingerprints": retrieval_result.get("requested_index_fingerprints", []),
        "searched_index_fingerprints": retrieval_result.get("searched_index_fingerprints", []),
        "context_package_id": context_package.get("context_package_id", ""),
        "prompt_package_id": prompt_package.get("prompt_package_id", ""),
        "llm_response_id": llm_response.get("llm_response_id", ""),
        "cited_response_id": cited_response.get("cited_response_id", ""),
        "groundedness_report_id": groundedness_report.get("groundedness_report_id", ""),
        "answer_quality_report_id": quality_report.get("answer_quality_report_id", "")
    }
    
    cache_info = {
        "cache_hit": cached_result.get("cache_hit", False),
        "cache_key": cached_result.get("cache_key", ""),
        "cached_at": cached_result.get("cached_at", ""),
        "cache_backend_name": cached_result.get("cache_backend_name", "")
    }

    answer = {
        "response_text": llm_response.get("response_text", ""),
        "finish_reason": llm_response.get("finish_reason"),
        "spans": cited_response.get("spans", [])
    }
    
    groundedness = {
        "groundedness_score": groundedness_report.get("groundedness_score", 0.0),
        "grounded_span_count": groundedness_report.get("grounded_span_count", 0),
        "weakly_grounded_span_count": groundedness_report.get("weakly_grounded_span_count", 0),
        "unsupported_span_count": groundedness_report.get("unsupported_span_count", 0),
        "span_groundedness": groundedness_report.get("span_groundedness", [])
    }
    
    quality = {
        "answer_quality_score": quality_report.get("answer_quality_score", 0.0),
        "citation_presence_ratio": quality_report.get("citation_presence_ratio", 0.0),
        "response_length_chars": quality_report.get("response_length_chars", 0),
        "response_length_words": quality_report.get("response_length_words", 0),
        "lexical_diversity_ratio": quality_report.get("lexical_diversity_ratio", 0.0),
        "average_span_length_chars": quality_report.get("average_span_length_chars", 0.0),
        "span_count": quality_report.get("span_count", 0)
    }

    return {
        "request_id": request_id,
        "api_pipeline_version": API_PIPELINE_VERSION,
        "received_at": received_at,
        "resolved_at": resolved_at,
        "status": response_status,
        "query": retrieval_result.get("query", ""),
        "answer": answer,
        "groundedness": groundedness,
        "quality": quality,
        "cache": cache_info,
        "provenance": provenance,
        "findings": findings,
        "pipeline_findings": pipeline_findings
    }

def validate_api_response(
    response: Dict[str, Any], 
    quality_report: Dict[str, Any],
    retrieval_result: Dict[str, Any],
    context_package: Dict[str, Any],
    prompt_package: Dict[str, Any],
    cached_result: Dict[str, Any],
    cited_response: Dict[str, Any],
    groundedness_report: Dict[str, Any]
) -> None:
    """Internal invariant self-check of the constructed APIResponse."""
    if response["status"] != map_pipeline_status(quality_report["status"]):
        raise APIResponseInternalError("RESPONSE_STATUS_MAPPING_MISMATCH")
        
    provenance = response.get("provenance", {})
    if provenance.get("context_package_id") != context_package.get("context_package_id"):
        raise APIResponseInternalError("PROVENANCE_ID_CHAIN_BROKEN")
    if provenance.get("prompt_package_id") != prompt_package.get("prompt_package_id"):
        raise APIResponseInternalError("PROVENANCE_ID_CHAIN_BROKEN")
    if provenance.get("llm_response_id") != cached_result.get("llm_response", {}).get("llm_response_id"):
        raise APIResponseInternalError("PROVENANCE_ID_CHAIN_BROKEN")
    if provenance.get("cited_response_id") != cited_response.get("cited_response_id"):
        raise APIResponseInternalError("PROVENANCE_ID_CHAIN_BROKEN")
    if provenance.get("groundedness_report_id") != groundedness_report.get("groundedness_report_id"):
        raise APIResponseInternalError("PROVENANCE_ID_CHAIN_BROKEN")
    if provenance.get("answer_quality_report_id") != quality_report.get("answer_quality_report_id"):
        raise APIResponseInternalError("PROVENANCE_ID_CHAIN_BROKEN")
        
    if response["answer"]["response_text"] != cached_result["llm_response"]["response_text"]:
        raise APIResponseInternalError("ANSWER_TEXT_MISMATCH")
        
    if response["answer"]["spans"] != cited_response["spans"]:
        raise APIResponseInternalError("SPANS_MISMATCH")
        
    request_id = response.get("request_id")
    if not request_id or not isinstance(request_id, str):
         raise APIResponseInternalError("REQUEST_ID_MISSING_OR_MALFORMED")
         
    try:
        uuid.UUID(request_id, version=4)  # raises ValueError if malformed
    except ValueError:
        raise APIResponseInternalError("REQUEST_ID_MISSING_OR_MALFORMED")
        
    pipeline_findings = response.get("pipeline_findings", {})
    expected_keys = {
        "retrieval", "context_assembly", "prompt_construction", 
        "response_caching", "citation_extraction", "groundedness_validation", 
        "answer_quality_evaluation"
    }
    if set(pipeline_findings.keys()) != expected_keys:
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")
        
    if pipeline_findings.get("retrieval") != retrieval_result.get("findings", []):
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")
    if pipeline_findings.get("context_assembly") != context_package.get("findings", []):
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")
    if pipeline_findings.get("prompt_construction") != prompt_package.get("findings", []):
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")
    if pipeline_findings.get("response_caching") != cached_result.get("findings", []):
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")
    if pipeline_findings.get("citation_extraction") != cited_response.get("citation_findings", []):
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")
    if pipeline_findings.get("groundedness_validation") != groundedness_report.get("groundedness_findings", []):
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")
    if pipeline_findings.get("answer_quality_evaluation") != quality_report.get("findings", []):
        raise APIResponseInternalError("PIPELINE_FINDINGS_INCOMPLETE")

def handle_request(request: Dict[str, Any], deps: PipelineDependencies) -> Dict[str, Any]:
    """Sole public entrypoint orchestrating the pipeline sequentially."""
    received_at = get_now_iso()
    
    validate_api_request(request)
    request_id = assign_request_id()
    
    logger.info({
        "stage": "stage18_api_response_serving",
        "doc_id": None,
        "event": f"Handling API request {request_id}",
        "elapsed_ms": 0,
        "severity": "INFO",
        "warning_code": None,
        "exception": None
    })
    
    findings: List[Dict[str, str]] = []
    
    try:
        retrieval_request = build_retrieval_request(request)
        retrieval_result = deps["retrieve"](retrieval_request)
        
        opts = request.get("pipeline_options") or {}
        context_budget_tokens = opts.get("context_budget_tokens")
        context_package = assemble_context(retrieval_result, context_budget_tokens)
        
        template_version = opts.get("template_version")
        prompt_budget_tokens = opts.get("prompt_budget_tokens")
        prompt_package = construct_prompt(context_package, template_version, prompt_budget_tokens)
        
        execution_config = resolve_execution_config_for_api(request, deps)
        
        if execution_config.get("model_name") == deps["default_model_name"] and ("model_name" not in opts or opts["model_name"] is None):
            findings.append({"severity": "INFO", "code": "MODEL_NAME_DEFAULTED", "message": "model_name omitted, using default_model_name"})
        
        cache_ttl_seconds = opts.get("cache_ttl_seconds")
        cached_result = execute_with_cache(
            prompt_package=prompt_package,
            llm_adapter=deps["llm_adapter"],
            cache_adapter=deps["cache_adapter"],
            execution_config=execution_config,
            cache_ttl_seconds=cache_ttl_seconds
        )
        
        citation_match_threshold = opts.get("citation_match_threshold")
        cited_response = extract_citations(
            llm_response=cached_result["llm_response"],
            prompt_package=prompt_package,
            context_package=context_package,
            citation_match_threshold=citation_match_threshold
        )
        
        groundedness_threshold = opts.get("groundedness_threshold")
        groundedness_report = validate_groundedness(
            cited_response=cited_response,
            context_package=context_package,
            groundedness_threshold=groundedness_threshold
        )
        
        quality_report = evaluate_answer_quality(groundedness_report)
        
        if quality_report["status"] == "PARTIAL":
            findings.append({"severity": "WARNING", "code": "PIPELINE_STATUS_PARTIAL", "message": "Pipeline status is PARTIAL"})
        elif quality_report["status"] in ("FAIL", "SKIPPED"):
            findings.append({"severity": "WARNING", "code": "PIPELINE_STATUS_FAILED", "message": f"Pipeline status is {quality_report['status']}"})
        
        response_status = map_pipeline_status(quality_report["status"])
        resolved_at = get_now_iso()
        
        response = build_api_response(
            request_id=request_id,
            received_at=received_at,
            resolved_at=resolved_at,
            retrieval_result=retrieval_result,
            context_package=context_package,
            prompt_package=prompt_package,
            cached_result=cached_result,
            cited_response=cited_response,
            groundedness_report=groundedness_report,
            quality_report=quality_report,
            response_status=response_status,
            findings=findings
        )
        
        validate_api_response(
            response=response,
            quality_report=quality_report,
            retrieval_result=retrieval_result,
            context_package=context_package,
            prompt_package=prompt_package,
            cached_result=cached_result,
            cited_response=cited_response,
            groundedness_report=groundedness_report
        )
        
        return response
        
    except Exception as e:
        if isinstance(e, APIResponseInternalError):
            raise
        raise PipelineOrchestrationError(f"Internal pipeline failure: {str(e)}") from e
