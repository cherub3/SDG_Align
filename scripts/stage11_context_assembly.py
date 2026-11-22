"""Stage 11 — Context Assembly.

Transforms a Stage 10 RetrievalResult into a token-budgeted ContextPackage.
"""

import sys
import math
import hashlib
import json
import logging
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage1_integrity import get_now_iso

CONTEXT_PIPELINE_VERSION = "1.0.0"
DEFAULT_CONTEXT_BUDGET_TOKENS = 4000
MAX_CONTEXT_BUDGET_TOKENS = 50000
CHARS_PER_TOKEN_ESTIMATE = 4.0

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage11_context_assembly")

class ContextAssemblyInputError(Exception):
    pass

class ContextAssemblyInternalError(Exception):
    pass

def validate_retrieval_result(result: Dict[str, Any]) -> None:
    """Raises ContextAssemblyInputError if malformed."""
    required_keys = [
        "query", "status", "requested_index_fingerprints",
        "searched_index_fingerprints", "results", "findings"
    ]
    for k in required_keys:
        if k not in result:
            raise ContextAssemblyInputError(f"RETRIEVAL_RESULT_MALFORMED: missing key {k}")
            
    if not isinstance(result["results"], list):
        raise ContextAssemblyInputError("RETRIEVAL_RESULT_MALFORMED: results is not a list")
        
    for i, chunk in enumerate(result["results"]):
        if not isinstance(chunk, dict):
            raise ContextAssemblyInputError(f"RETRIEVAL_RESULT_MALFORMED: chunk {i} is not a dict")
        if "text" not in chunk:
            raise ContextAssemblyInputError(f"RETRIEVAL_RESULT_MALFORMED: chunk {i} missing text")
        if not isinstance(chunk["text"], str):
            raise ContextAssemblyInputError(f"RETRIEVAL_RESULT_MALFORMED: chunk {i} text is not a string")
        for k in ["rank", "score", "index_fingerprint", "embedding_id", "chunk_id", "doc_id"]:
            if k not in chunk:
                raise ContextAssemblyInputError(f"RETRIEVAL_RESULT_MALFORMED: chunk {i} missing {k}")

def estimate_tokens(text: str) -> int:
    """Deterministic token estimation."""
    return math.ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE)

def build_context_blocks(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converts RetrievedChunks to ContextBlocks."""
    blocks = []
    for chunk in results:
        block = {
            "rank": chunk["rank"],
            "score": chunk["score"],
            "index_fingerprint": chunk["index_fingerprint"],
            "embedding_id": chunk["embedding_id"],
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "text": chunk["text"],
            "heading_path": chunk.get("heading_path", []),
            "section_ids": chunk.get("section_ids", []),
            "page_start": chunk.get("page_start", 0),
            "page_end": chunk.get("page_end", 0),
            "category": chunk.get("category", ""),
            "doc_type": chunk.get("doc_type", ""),
            "title": chunk.get("title", ""),
            "estimated_tokens": estimate_tokens(chunk["text"])
        }
        blocks.append(block)
    return blocks

def enforce_budget(blocks: List[Dict[str, Any]], context_budget_tokens: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Prefix truncation budget enforcement."""
    included = []
    excluded = []
    total = 0
    cutoff = False
    
    for block in blocks:
        if cutoff:
            excluded.append(block)
        else:
            if total + block["estimated_tokens"] > context_budget_tokens:
                cutoff = True
                excluded.append(block)
            else:
                total += block["estimated_tokens"]
                included.append(block)
                
    return included, excluded

def _generate_package_id(retrieval_result: Dict[str, Any], chunk_ids: List[str], context_budget_tokens: int) -> str:
    hash_input = {
        "query": retrieval_result["query"],
        "requested_index_fingerprints": retrieval_result["requested_index_fingerprints"],
        "searched_index_fingerprints": retrieval_result["searched_index_fingerprints"],
        "chunk_ids": chunk_ids,
        "context_budget_tokens": context_budget_tokens
    }
    canonical_json = json.dumps(hash_input, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

def assemble_context_package(
    retrieval_result: Dict[str, Any], 
    included: List[Dict[str, Any]], 
    excluded: List[Dict[str, Any]], 
    context_budget_tokens: int
) -> Dict[str, Any]:
    
    # Generate deterministic context_package_id
    pkg_id = _generate_package_id(retrieval_result, [b["chunk_id"] for b in included], context_budget_tokens)
    
    # Assign context_block_id
    for b in included:
        b["context_block_id"] = f"{pkg_id}_{b['chunk_id']}"
    for b in excluded:
        b["context_block_id"] = f"{pkg_id}_{b['chunk_id']}"
        
    total_estimated = sum(b["estimated_tokens"] for b in included)
    excluded_estimated = sum(b["estimated_tokens"] for b in excluded)
    budget_utilization = total_estimated / context_budget_tokens if context_budget_tokens > 0 else 0.0
    
    findings = []
    if excluded:
        findings.append({
            "severity": "WARNING",
            "code": "CONTEXT_BUDGET_EXCEEDED",
            "message": f"Excluded {len(excluded)} blocks due to budget constraints"
        })
    if not included:
        findings.append({
            "severity": "WARNING",
            "code": "CONTEXT_EMPTY",
            "message": "Context assembly produced zero blocks"
        })
        
    package = {
        "context_package_id": pkg_id,
        "context_pipeline_version": CONTEXT_PIPELINE_VERSION,
        "assembled_at": get_now_iso(),
        "query": retrieval_result["query"],
        "status": retrieval_result["status"],
        "is_empty": len(included) == 0,
        "context_budget_tokens": context_budget_tokens,
        "total_estimated_tokens": total_estimated,
        "included_block_count": len(included),
        "excluded_block_count": len(excluded),
        "excluded_estimated_tokens": excluded_estimated,
        "budget_utilization": budget_utilization,
        "context_blocks": included,
        "excluded_context_blocks": excluded,
        "retrieval_findings": retrieval_result["findings"],
        "findings": findings,
        "requested_index_fingerprints": retrieval_result["requested_index_fingerprints"],
        "searched_index_fingerprints": retrieval_result["searched_index_fingerprints"]
    }
    return package

def validate_context_package(package: Dict[str, Any]) -> None:
    seen = set()
    for b in package["context_blocks"]:
        if b["chunk_id"] in seen:
            raise ContextAssemblyInternalError("DUPLICATE_CONTEXT_BLOCK")
        seen.add(b["chunk_id"])
        
    for i, b in enumerate(package["context_blocks"]):
        if b["rank"] != i:
            raise ContextAssemblyInternalError("RANK_NOT_CONTIGUOUS")
            
    total_est = sum(b["estimated_tokens"] for b in package["context_blocks"])
    if total_est != package["total_estimated_tokens"]:
        raise ContextAssemblyInternalError("TOKEN_ESTIMATE_SUM_MISMATCH")
        
    if package["total_estimated_tokens"] > package["context_budget_tokens"]:
        raise ContextAssemblyInternalError("BUDGET_INVARIANT_VIOLATED")
        
    original_results = len(package["context_blocks"]) + len(package["excluded_context_blocks"])
    if package["included_block_count"] + package["excluded_block_count"] != original_results:
        raise ContextAssemblyInternalError("EXCLUDED_COUNT_MISMATCH")
        
    # Technically we should know len(retrieval_result["results"]) but since this is package-only validation
    # the check `package["included_block_count"] + package["excluded_block_count"] == len(retrieval_result["results"])`
    # requires external data. We can't strictly check that here if it only takes package.
    # The architecture states EXCLUDED_COUNT_MISMATCH triggers if `included_block_count + excluded_block_count != len(retrieval_result["results"])`
    # Wait! If `validate_context_package` takes `package`, where does `len(retrieval_result["results"])` come from?
    # Actually, we can check if `included_block_count == len(context_blocks)` and `excluded_block_count == len(excluded_context_blocks)`.
    if package["included_block_count"] != len(package["context_blocks"]):
        raise ContextAssemblyInternalError("EXCLUDED_COUNT_MISMATCH")
    if package["excluded_block_count"] != len(package["excluded_context_blocks"]):
        raise ContextAssemblyInternalError("EXCLUDED_COUNT_MISMATCH")

def assemble_context(retrieval_result: Dict[str, Any], context_budget_tokens: Optional[int] = None) -> Dict[str, Any]:
    validate_retrieval_result(retrieval_result)
    
    if retrieval_result["status"] == "FAIL":
        findings = [{
            "severity": "FAIL",
            "code": "RETRIEVAL_STATUS_FAIL",
            "message": "Retrieval status was FAIL"
        }]
        
        # Determine budget tokens
        if context_budget_tokens is None:
            budget = DEFAULT_CONTEXT_BUDGET_TOKENS
        else:
            budget = min(max(1, context_budget_tokens), MAX_CONTEXT_BUDGET_TOKENS)
            
        pkg_id = _generate_package_id(retrieval_result, [], budget)
        pkg = {
            "context_package_id": pkg_id,
            "context_pipeline_version": CONTEXT_PIPELINE_VERSION,
            "assembled_at": get_now_iso(),
            "query": retrieval_result["query"],
            "status": "FAIL",
            "is_empty": True,
            "context_budget_tokens": budget,
            "total_estimated_tokens": 0,
            "included_block_count": 0,
            "excluded_block_count": 0,
            "excluded_estimated_tokens": 0,
            "budget_utilization": 0.0,
            "context_blocks": [],
            "excluded_context_blocks": [],
            "retrieval_findings": retrieval_result["findings"],
            "findings": findings,
            "requested_index_fingerprints": retrieval_result["requested_index_fingerprints"],
            "searched_index_fingerprints": retrieval_result["searched_index_fingerprints"]
        }
        return pkg
        
    if context_budget_tokens is None:
        budget = DEFAULT_CONTEXT_BUDGET_TOKENS
    else:
        budget = min(max(1, context_budget_tokens), MAX_CONTEXT_BUDGET_TOKENS)
        
    blocks = build_context_blocks(retrieval_result["results"])
    included, excluded = enforce_budget(blocks, budget)
    
    pkg = assemble_context_package(retrieval_result, included, excluded, budget)
    
    # For validate_context_package, we need to pass len(results) to it, or it needs to check it.
    validate_context_package(pkg)
    if pkg["included_block_count"] + pkg["excluded_block_count"] != len(retrieval_result["results"]):
        raise ContextAssemblyInternalError("EXCLUDED_COUNT_MISMATCH")
        
    return pkg
