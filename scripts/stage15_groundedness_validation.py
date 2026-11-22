"""Stage 15 — Groundedness Validation.

Turns a CitedResponse into a GroundednessReport using structural Longest Common Substring matching.
"""

import sys
import hashlib
import json
import logging
import unicodedata
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage1_integrity import get_now_iso

GROUNDEDNESS_PIPELINE_VERSION = "1.0.0"
DEFAULT_GROUNDEDNESS_THRESHOLD = 0.8
LOW_GROUNDEDNESS_THRESHOLD = 0.5

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage15_groundedness_validation")

class GroundednessValidationInputError(Exception):
    pass

class GroundednessValidationInternalError(Exception):
    pass

def validate_cited_response(response: Dict[str, Any]) -> None:
    required_keys = [
        "cited_response_id", "llm_response_id", "prompt_package_id",
        "context_package_id", "status", "response_text", "spans", "findings"
    ]
    for k in required_keys:
        if k not in response:
            raise GroundednessValidationInputError(f"CITED_RESPONSE_MALFORMED: missing {k}")
            
    if not isinstance(response["spans"], list):
        raise GroundednessValidationInputError("CITED_RESPONSE_MALFORMED: spans not a list")
        
    for span in response["spans"]:
        for sk in ["span_index", "text", "citations"]:
            if sk not in span:
                raise GroundednessValidationInputError(f"CITED_RESPONSE_MALFORMED: span missing {sk}")
        if not isinstance(span["citations"], list):
            raise GroundednessValidationInputError("CITED_RESPONSE_MALFORMED: citations not a list")
        for cit in span["citations"]:
            for ck in ["context_block_id", "chunk_id", "doc_id", "match_score"]:
                if ck not in cit:
                    raise GroundednessValidationInputError(f"CITED_RESPONSE_MALFORMED: citation missing {ck}")

def validate_context_package(package: Dict[str, Any]) -> None:
    required_keys = ["context_package_id", "context_blocks"]
    for k in required_keys:
        if k not in package:
            raise GroundednessValidationInputError(f"CONTEXT_PACKAGE_MALFORMED: missing {k}")
            
    if not isinstance(package["context_blocks"], list):
        raise GroundednessValidationInputError("CONTEXT_PACKAGE_MALFORMED: context_blocks not a list")
        
    for block in package["context_blocks"]:
        for bk in ["context_block_id", "chunk_id", "text"]:
            if bk not in block:
                raise GroundednessValidationInputError(f"CONTEXT_PACKAGE_MALFORMED: block missing {bk}")

def verify_context_package_match(cited_response: Dict[str, Any], context_package: Dict[str, Any]) -> None:
    if cited_response["context_package_id"] != context_package["context_package_id"]:
        raise GroundednessValidationInputError("CONTEXT_PACKAGE_ID_MISMATCH")

def fold(text: str) -> str:
    s = unicodedata.normalize('NFC', text)
    s = s.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def lcs_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    max_len = 0
    dp = [0] * (len(b) + 1)
    
    for i in range(1, len(a) + 1):
        prev = 0
        for j in range(1, len(b) + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev + 1
                if dp[j] > max_len:
                    max_len = dp[j]
            else:
                dp[j] = 0
            prev = temp
    return max_len

def compute_groundedness_overlap(span_text: str, block_text: str) -> float:
    folded_span = fold(span_text)
    folded_block = fold(block_text)
    
    if len(folded_span) == 0:
        return 0.0
        
    length = lcs_len(folded_span, folded_block)
    return float(length) / float(len(folded_span))

def verify_span_groundedness(
    span: Dict[str, Any], 
    context_blocks_by_id: Dict[str, Dict[str, Any]], 
    groundedness_threshold: float
) -> Dict[str, Any]:
    
    if not span["citations"]:
        return {
            "span_index": span["span_index"],
            "groundedness": "UNSUPPORTED",
            "best_groundedness_score": None,
            "strongest_grounding": None
        }
        
    best_score = -1.0
    strongest_cit = None
    
    for cit in span["citations"]:
        block = context_blocks_by_id[cit["context_block_id"]]
        score = compute_groundedness_overlap(span["text"], block["text"])
        
        if score > best_score:
            best_score = score
            strongest_cit = cit
        elif score == best_score:
            if strongest_cit is None or cit["chunk_id"] < strongest_cit["chunk_id"]:
                strongest_cit = cit
                
    if best_score >= groundedness_threshold:
        groundedness = "GROUNDED"
    else:
        groundedness = "WEAKLY_GROUNDED"
        
    return {
        "span_index": span["span_index"],
        "groundedness": groundedness,
        "best_groundedness_score": best_score,
        "strongest_grounding": dict(strongest_cit) if strongest_cit is not None else None
    }

def build_groundedness_report(
    cited_response: Dict[str, Any], 
    context_package: Dict[str, Any], 
    span_groundedness_list: List[Dict[str, Any]], 
    groundedness_threshold: float
) -> Dict[str, Any]:
    
    hash_input = {
        "cited_response_id": cited_response["cited_response_id"],
        "groundedness_threshold": groundedness_threshold
    }
    canonical_json = json.dumps(hash_input, separators=(',', ':'), sort_keys=True)
    report_id = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    span_count = len(span_groundedness_list)
    grounded_span_count = sum(1 for s in span_groundedness_list if s["groundedness"] == "GROUNDED")
    weakly_grounded_span_count = sum(1 for s in span_groundedness_list if s["groundedness"] == "WEAKLY_GROUNDED")
    
    # unsupported_span_count is read directly from spans with citations == []
    unsupported_span_count = sum(1 for s in cited_response["spans"] if not s["citations"])
    
    if span_count > 0:
        groundedness_score = float(grounded_span_count) / float(span_count)
    else:
        groundedness_score = 1.0
        
    findings = []
    if span_count > 0 and groundedness_score == 0.0:
        findings.append({
            "severity": "WARNING",
            "code": "ZERO_GROUNDED_CLAIMS",
            "message": "groundedness_score is 0.0"
        })
    elif 0.0 < groundedness_score < LOW_GROUNDEDNESS_THRESHOLD:
        findings.append({
            "severity": "WARNING",
            "code": "LOW_GROUNDEDNESS_SCORE",
            "message": f"groundedness_score {groundedness_score} is below {LOW_GROUNDEDNESS_THRESHOLD}"
        })
        
    if span_count == 0:
        findings.append({
            "severity": "WARNING",
            "code": "RESPONSE_EMPTY",
            "message": "span_count is 0"
        })
        
    return {
        "groundedness_report_id": report_id,
        "groundedness_pipeline_version": GROUNDEDNESS_PIPELINE_VERSION,
        "validated_at": get_now_iso(),
        "cited_response_id": cited_response["cited_response_id"],
        "llm_response_id": cited_response["llm_response_id"],
        "prompt_package_id": cited_response["prompt_package_id"],
        "context_package_id": cited_response["context_package_id"],
        "status": cited_response["status"],
        "response_text": cited_response["response_text"],
        "span_groundedness": span_groundedness_list,
        "span_count": span_count,
        "grounded_span_count": grounded_span_count,
        "weakly_grounded_span_count": weakly_grounded_span_count,
        "unsupported_span_count": unsupported_span_count,
        "groundedness_score": groundedness_score,
        "groundedness_threshold": groundedness_threshold,
        "findings": findings,
        "citation_findings": list(cited_response.get("findings", []))
    }

def validate_groundedness_report(report: Dict[str, Any], cited_response: Dict[str, Any], context_package: Dict[str, Any]) -> None:
    # SPAN_COUNT_MISMATCH
    if len(report["span_groundedness"]) != len(cited_response["spans"]):
        raise GroundednessValidationInternalError("SPAN_COUNT_MISMATCH")
    if report["span_count"] != len(cited_response["spans"]):
        raise GroundednessValidationInternalError("SPAN_COUNT_MISMATCH")
        
    # SPAN_ALIGNMENT_MISMATCH
    for i in range(report["span_count"]):
        if report["span_groundedness"][i]["span_index"] != cited_response["spans"][i]["span_index"]:
            raise GroundednessValidationInternalError("SPAN_ALIGNMENT_MISMATCH")
            
    # GROUNDEDNESS_LABEL_INVALID
    for i in range(report["span_count"]):
        sg = report["span_groundedness"][i]
        span = cited_response["spans"][i]
        
        has_cits = len(span["citations"]) > 0
        if not has_cits:
            if sg["groundedness"] != "UNSUPPORTED":
                raise GroundednessValidationInternalError("GROUNDEDNESS_LABEL_INVALID")
            if sg["best_groundedness_score"] is not None:
                raise GroundednessValidationInternalError("GROUNDEDNESS_LABEL_INVALID")
        else:
            if sg["groundedness"] == "UNSUPPORTED":
                raise GroundednessValidationInternalError("GROUNDEDNESS_LABEL_INVALID")
            
            score = sg["best_groundedness_score"]
            threshold = report["groundedness_threshold"]
            
            if sg["groundedness"] == "GROUNDED" and score < threshold:
                raise GroundednessValidationInternalError("GROUNDEDNESS_LABEL_INVALID")
            if sg["groundedness"] == "WEAKLY_GROUNDED" and score >= threshold:
                raise GroundednessValidationInternalError("GROUNDEDNESS_LABEL_INVALID")
                
    # STRONGEST_GROUNDING_MISMATCH
    blocks_by_id = {b["context_block_id"]: b for b in context_package["context_blocks"]}
    for i in range(report["span_count"]):
        sg = report["span_groundedness"][i]
        span = cited_response["spans"][i]
        
        if sg["strongest_grounding"] is not None:
            # Guard: a non-null strongest_grounding on a span with no citations is
            # always a malformed-report state — raise before attempting recomputation.
            if not span["citations"]:
                raise GroundednessValidationInternalError("STRONGEST_GROUNDING_MISMATCH")
            # Recompute: find the citation achieving the maximum score
            best_score = -1.0
            best_cit = None
            for cit in span["citations"]:
                block = blocks_by_id.get(cit["context_block_id"])
                if block is None:
                    raise GroundednessValidationInternalError("STRONGEST_GROUNDING_MISMATCH")
                score = compute_groundedness_overlap(span["text"], block["text"])
                if score > best_score:
                    best_score = score
                    best_cit = cit
                elif score == best_score:
                    if best_cit is None or cit["chunk_id"] < best_cit["chunk_id"]:
                        best_cit = cit
            if (sg["strongest_grounding"]["context_block_id"] != best_cit["context_block_id"]
                    or sg["strongest_grounding"]["chunk_id"] != best_cit["chunk_id"]):
                raise GroundednessValidationInternalError("STRONGEST_GROUNDING_MISMATCH")

    # GROUNDEDNESS_COMPUTATION_MISMATCH
    sc = report["span_count"]
    gsc = report["grounded_span_count"]
    wgsc = report["weakly_grounded_span_count"]
    usc = report["unsupported_span_count"]
    score = report["groundedness_score"]
    
    expected_score = float(gsc) / float(sc) if sc > 0 else 1.0
    if score != expected_score:
        raise GroundednessValidationInternalError("GROUNDEDNESS_COMPUTATION_MISMATCH")
        
    if gsc + wgsc + usc != sc:
        raise GroundednessValidationInternalError("GROUNDEDNESS_COMPUTATION_MISMATCH")
        
    # CITED_RESPONSE_ID_MISMATCH
    if report["cited_response_id"] != cited_response["cited_response_id"]:
        raise GroundednessValidationInternalError("CITED_RESPONSE_ID_MISMATCH")
    if report["llm_response_id"] != cited_response["llm_response_id"]:
        raise GroundednessValidationInternalError("CITED_RESPONSE_ID_MISMATCH")
    if report["context_package_id"] != cited_response["context_package_id"]:
        raise GroundednessValidationInternalError("CITED_RESPONSE_ID_MISMATCH")

def validate_groundedness(
    cited_response: Dict[str, Any], 
    context_package: Dict[str, Any], 
    groundedness_threshold: Optional[float] = None
) -> Dict[str, Any]:
    
    validate_cited_response(cited_response)
    validate_context_package(context_package)
    verify_context_package_match(cited_response, context_package)
    
    if groundedness_threshold is None:
        threshold = DEFAULT_GROUNDEDNESS_THRESHOLD
    else:
        threshold = max(0.0, min(1.0, float(groundedness_threshold)))
        
    blocks_by_id = {b["context_block_id"]: b for b in context_package["context_blocks"]}
    
    span_groundedness_list = []
    
    for span in cited_response["spans"]:
        sg = verify_span_groundedness(span, blocks_by_id, threshold)
        span_groundedness_list.append(sg)
        
    report = build_groundedness_report(
        cited_response, context_package, span_groundedness_list, threshold
    )
    
    validate_groundedness_report(report, cited_response, context_package)
    
    return report
