"""Stage 14 — Citation Extraction.

Turns an LLMResponse into a CitedResponse using structural lexical n-gram matching.
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

CITATION_PIPELINE_VERSION = "1.0.0"
SPAN_TERMINATORS = ('.', '!', '?')
SPAN_TRAILING_CLOSERS = ('"', "'", ')', ']', '”', '’', '»')
NGRAM_SIZE = 5
DEFAULT_CITATION_MATCH_THRESHOLD = 0.6
LOW_CITATION_COVERAGE_THRESHOLD = 0.5

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage14_citation_extraction")

class CitationExtractionInputError(Exception):
    pass

class CitationExtractionInternalError(Exception):
    pass

def validate_llm_response(response: Dict[str, Any]) -> None:
    required_keys = ["llm_response_id", "response_text", "status", "prompt_package_id", "findings"]
    for k in required_keys:
        if k not in response:
            raise CitationExtractionInputError(f"LLM_RESPONSE_MALFORMED: missing {k}")
    if not isinstance(response["findings"], list):
        raise CitationExtractionInputError("LLM_RESPONSE_MALFORMED: findings not a list")

def validate_prompt_package(package: Dict[str, Any]) -> None:
    required_keys = ["prompt_package_id", "context_package_id"]
    for k in required_keys:
        if k not in package:
            raise CitationExtractionInputError(f"PROMPT_PACKAGE_MALFORMED: missing {k}")

def validate_context_package(package: Dict[str, Any]) -> None:
    if "context_package_id" not in package or "context_blocks" not in package:
        raise CitationExtractionInputError("CONTEXT_PACKAGE_MALFORMED: missing keys")
    
    if not isinstance(package["context_blocks"], list):
        raise CitationExtractionInputError("CONTEXT_PACKAGE_MALFORMED: context_blocks not a list")
        
    for b in package["context_blocks"]:
        for k in ["context_block_id", "chunk_id", "doc_id", "text"]:
            if k not in b:
                raise CitationExtractionInputError(f"CONTEXT_PACKAGE_MALFORMED: block missing {k}")

def verify_id_chain(llm_response: Dict[str, Any], prompt_package: Dict[str, Any], context_package: Dict[str, Any]) -> None:
    if llm_response["prompt_package_id"] != prompt_package["prompt_package_id"]:
        raise CitationExtractionInputError("ID_CHAIN_MISMATCH")
    if prompt_package["context_package_id"] != context_package["context_package_id"]:
        raise CitationExtractionInputError("ID_CHAIN_MISMATCH")

def segment_response_text(response_text: str) -> List[Dict[str, Any]]:
    if not response_text:
        return []
        
    L = len(response_text)
    active_boundaries = []
    
    i = 0
    while i < L:
        if response_text[i] in SPAN_TERMINATORS:
            start = i
            i += 1
            while i < L and (response_text[i] in SPAN_TERMINATORS or response_text[i] in SPAN_TRAILING_CLOSERS):
                i += 1
            end = i
            
            is_active = False
            if end == L:
                is_active = True
            elif response_text[end] in (' ', '\t', '\n'):
                is_active = True
                
            if is_active:
                active_boundaries.append((start, end))
        else:
            i += 1
            
    i = 0
    while i < L:
        if response_text[i] == '\n':
            start = i
            while i < L and response_text[i] == '\n':
                i += 1
            active_boundaries.append((start, i))
        else:
            i += 1
            
    active_boundaries.sort()
    merged = []
    for b in active_boundaries:
        if not merged:
            merged.append(b)
        else:
            last = merged[-1]
            if b[0] <= last[1]:
                merged[-1] = (last[0], max(last[1], b[1]))
            else:
                merged.append(b)
                
    spans = []
    span_start = 0
    
    for b in merged:
        end_offset = b[1]
        spans.append({
            "span_index": len(spans),
            "text": response_text[span_start:end_offset],
            "start_offset": span_start,
            "end_offset": end_offset,
            "citations": []
        })
        span_start = end_offset
        
    if span_start < L:
        spans.append({
            "span_index": len(spans),
            "text": response_text[span_start:L],
            "start_offset": span_start,
            "end_offset": L,
            "citations": []
        })
        
    return spans

def fold_text(text: str) -> str:
    s = unicodedata.normalize('NFC', text)
    s = s.lower()
    s = re.sub(r'[ \t\n]+', ' ', s).strip()
    return s

def compute_ngram_overlap(span_text: str, block_text: str) -> float:
    folded_span = fold_text(span_text)
    folded_block = fold_text(block_text)
    
    L_span = len(folded_span)
    L_block = len(folded_block)
    
    if L_span < NGRAM_SIZE:
        return 0.0
        
    ngrams_span = set(folded_span[i:i+NGRAM_SIZE] for i in range(L_span - NGRAM_SIZE + 1))
    
    if L_block < NGRAM_SIZE:
        ngrams_block = set()
    else:
        ngrams_block = set(folded_block[i:i+NGRAM_SIZE] for i in range(L_block - NGRAM_SIZE + 1))
        
    overlap = len(ngrams_span.intersection(ngrams_block))
    return float(overlap) / float(len(ngrams_span))

def match_span_to_blocks(span: Dict[str, Any], context_blocks: List[Dict[str, Any]], citation_match_threshold: float) -> List[Dict[str, Any]]:
    citations = []
    
    for block in context_blocks:
        score = compute_ngram_overlap(span["text"], block["text"])
        if score >= citation_match_threshold:
            citations.append({
                "context_block_id": block["context_block_id"],
                "chunk_id": block["chunk_id"],
                "doc_id": block["doc_id"],
                "match_score": score
            })
            
    # sort by descending match_score, ascending chunk_id
    citations.sort(key=lambda c: (-c["match_score"], c["chunk_id"]))
    return citations

def assemble_cited_response(
    llm_response: Dict[str, Any], 
    prompt_package: Dict[str, Any], 
    context_package: Dict[str, Any], 
    spans: List[Dict[str, Any]], 
    citation_match_threshold: float
) -> Dict[str, Any]:
    
    hash_input = {
        "llm_response_id": llm_response["llm_response_id"],
        "context_package_id": context_package["context_package_id"],
        "citation_match_threshold": citation_match_threshold,
        "ngram_size": NGRAM_SIZE
    }
    canonical_json = json.dumps(hash_input, separators=(',', ':'), sort_keys=True)
    cited_response_id = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    span_count = len(spans)
    cited_span_count = sum(1 for s in spans if len(s["citations"]) > 0)
    uncited_span_count = span_count - cited_span_count
    
    if span_count > 0:
        citation_coverage = float(cited_span_count) / float(span_count)
    else:
        citation_coverage = 1.0
        
    findings = []
    if span_count > 0 and citation_coverage == 0.0:
        findings.append({
            "severity": "WARNING",
            "code": "ZERO_CITATIONS",
            "message": "citation_coverage is 0.0"
        })
    elif 0.0 < citation_coverage < LOW_CITATION_COVERAGE_THRESHOLD:
        findings.append({
            "severity": "WARNING",
            "code": "LOW_CITATION_COVERAGE",
            "message": f"citation_coverage {citation_coverage} is below threshold {LOW_CITATION_COVERAGE_THRESHOLD}"
        })
        
    if span_count == 0:
        findings.append({
            "severity": "WARNING",
            "code": "RESPONSE_EMPTY",
            "message": "span_count is 0"
        })
        
    return {
        "cited_response_id": cited_response_id,
        "citation_pipeline_version": CITATION_PIPELINE_VERSION,
        "extracted_at": get_now_iso(),
        "llm_response_id": llm_response["llm_response_id"],
        "prompt_package_id": prompt_package["prompt_package_id"],
        "context_package_id": context_package["context_package_id"],
        "status": llm_response["status"],
        "response_text": llm_response["response_text"],
        "spans": spans,
        "span_count": span_count,
        "cited_span_count": cited_span_count,
        "uncited_span_count": uncited_span_count,
        "citation_coverage": citation_coverage,
        "citation_match_threshold": citation_match_threshold,
        "findings": findings,
        "llm_findings": llm_response.get("findings", [])
    }

def validate_cited_response(response: Dict[str, Any], context_package: Dict[str, Any], llm_response: Dict[str, Any]) -> None:
    # SPAN_TEXT_MISMATCH
    concat_text = "".join(s["text"] for s in response["spans"])
    if concat_text != response["response_text"]:
        raise CitationExtractionInternalError("SPAN_TEXT_MISMATCH")
        
    # SPAN_OFFSET_DISCONTINUOUS
    if response["spans"]:
        if response["spans"][0]["start_offset"] != 0:
            raise CitationExtractionInternalError("SPAN_OFFSET_DISCONTINUOUS")
        for i in range(len(response["spans"]) - 1):
            if response["spans"][i]["end_offset"] != response["spans"][i+1]["start_offset"]:
                raise CitationExtractionInternalError("SPAN_OFFSET_DISCONTINUOUS")
        if response["spans"][-1]["end_offset"] != len(response["response_text"]):
            raise CitationExtractionInternalError("SPAN_OFFSET_DISCONTINUOUS")
            
    valid_blocks = {b["context_block_id"] for b in context_package["context_blocks"]}
    
    for span in response["spans"]:
        seen_blocks = set()
        for cit in span["citations"]:
            if cit["context_block_id"] not in valid_blocks:
                raise CitationExtractionInternalError("CITATION_REFERENCES_UNKNOWN_BLOCK")
            if cit["context_block_id"] in seen_blocks:
                raise CitationExtractionInternalError("DUPLICATE_CITATION_IN_SPAN")
            seen_blocks.add(cit["context_block_id"])
            
    # COVERAGE_COMPUTATION_MISMATCH
    sc = response["span_count"]
    csc = response["cited_span_count"]
    usc = response["uncited_span_count"]
    cov = response["citation_coverage"]
    
    expected_cov = float(csc) / float(sc) if sc > 0 else 1.0
    if cov != expected_cov:
        raise CitationExtractionInternalError("COVERAGE_COMPUTATION_MISMATCH")
    if csc + usc != sc:
        raise CitationExtractionInternalError("COVERAGE_COMPUTATION_MISMATCH")
        
    if response["llm_response_id"] != llm_response["llm_response_id"]:
        raise CitationExtractionInternalError("LLM_RESPONSE_ID_MISMATCH")
    if response["context_package_id"] != context_package["context_package_id"]:
        raise CitationExtractionInternalError("LLM_RESPONSE_ID_MISMATCH")

def extract_citations(
    llm_response: Dict[str, Any], 
    prompt_package: Dict[str, Any], 
    context_package: Dict[str, Any], 
    citation_match_threshold: Optional[float] = None
) -> Dict[str, Any]:
    
    validate_llm_response(llm_response)
    validate_prompt_package(prompt_package)
    validate_context_package(context_package)
    verify_id_chain(llm_response, prompt_package, context_package)
    
    if citation_match_threshold is None:
        threshold = DEFAULT_CITATION_MATCH_THRESHOLD
    else:
        threshold = max(0.0, min(1.0, float(citation_match_threshold)))
        
    spans = segment_response_text(llm_response["response_text"])
    
    for span in spans:
        span["citations"] = match_span_to_blocks(span, context_package["context_blocks"], threshold)
        
    cited_response = assemble_cited_response(
        llm_response, prompt_package, context_package, spans, threshold
    )
    
    validate_cited_response(cited_response, context_package, llm_response)
    
    return cited_response
