"""Stage 16 — Answer Quality Evaluation.

Turns a Stage 15 GroundednessReport into an AnswerQualityReport: a deterministic,
explainable set of response-level quality metrics.
"""

import sys
import hashlib
import json
import logging
import unicodedata
from typing import Any, Dict, List
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage1_integrity import get_now_iso

ANSWER_QUALITY_PIPELINE_VERSION = "1.0.0"
GROUNDEDNESS_WEIGHT = 0.7
CITATION_PRESENCE_WEIGHT = 0.3
MIN_ANSWER_LENGTH_CHARS = 20
LOW_ANSWER_QUALITY_THRESHOLD = 0.5
LOW_CITATION_PRESENCE_THRESHOLD = 0.5

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage16_answer_quality_evaluation")

class AnswerQualityEvaluationInputError(Exception):
    pass

class AnswerQualityEvaluationInternalError(Exception):
    pass

def validate_groundedness_report(report: Dict[str, Any]) -> None:
    required_string_keys = [
        "groundedness_report_id", "cited_response_id", "llm_response_id", 
        "prompt_package_id", "context_package_id", "status", "response_text"
    ]
    for k in required_string_keys:
        if k not in report:
            raise AnswerQualityEvaluationInputError(f"GROUNDEDNESS_REPORT_MALFORMED: missing {k}")
        if not isinstance(report[k], str):
            raise AnswerQualityEvaluationInputError(f"GROUNDEDNESS_REPORT_MALFORMED: {k} must be str")

    required_int_keys = ["span_count", "unsupported_span_count"]
    for k in required_int_keys:
        if k not in report:
            raise AnswerQualityEvaluationInputError(f"GROUNDEDNESS_REPORT_MALFORMED: missing {k}")
        if not isinstance(report[k], int):
            raise AnswerQualityEvaluationInputError(f"GROUNDEDNESS_REPORT_MALFORMED: {k} must be int")

    if "groundedness_score" not in report:
        raise AnswerQualityEvaluationInputError("GROUNDEDNESS_REPORT_MALFORMED: missing groundedness_score")
    if not isinstance(report["groundedness_score"], (float, int)):
        raise AnswerQualityEvaluationInputError("GROUNDEDNESS_REPORT_MALFORMED: groundedness_score must be float")

    if "findings" not in report:
        raise AnswerQualityEvaluationInputError("GROUNDEDNESS_REPORT_MALFORMED: missing findings")
    if not isinstance(report["findings"], list):
        raise AnswerQualityEvaluationInputError("GROUNDEDNESS_REPORT_MALFORMED: findings must be list")

def compute_lexical_metrics(response_text: str) -> Dict[str, Any]:
    response_length_chars = len(response_text)
    
    if response_text == "":
        words = []
    else:
        # Normalize to NFC and split on maximal Unicode-whitespace runs.
        # Python's str.split() inherently handles all unicode whitespace and stripping.
        normalized = unicodedata.normalize('NFC', response_text)
        words = normalized.split()
        
    response_length_words = len(words)
    
    if response_length_words > 0:
        unique_folded = {w.lower() for w in words}
        lexical_diversity_ratio = float(len(unique_folded)) / float(response_length_words)
    else:
        lexical_diversity_ratio = 0.0
        
    return {
        "response_length_chars": response_length_chars,
        "response_length_words": response_length_words,
        "lexical_diversity_ratio": lexical_diversity_ratio
    }

def compute_structural_metrics(response_length_chars: int, span_count: int) -> Dict[str, Any]:
    if span_count > 0:
        avg = float(response_length_chars) / float(span_count)
    else:
        avg = 0.0
    return {
        "average_span_length_chars": avg
    }

def compute_citation_presence_ratio(span_count: int, unsupported_span_count: int) -> float:
    if span_count > 0:
        return float(span_count - unsupported_span_count) / float(span_count)
    return 1.0

def compute_answer_quality_score(groundedness_score: float, citation_presence_ratio: float) -> float:
    return (float(groundedness_score) * GROUNDEDNESS_WEIGHT) + (float(citation_presence_ratio) * CITATION_PRESENCE_WEIGHT)

def build_evaluation_report(
    groundedness_report: Dict[str, Any], 
    lexical_metrics: Dict[str, Any], 
    structural_metrics: Dict[str, Any], 
    citation_presence_ratio: float, 
    answer_quality_score: float
) -> Dict[str, Any]:
    
    hash_input = {
        "groundedness_report_id": groundedness_report["groundedness_report_id"]
    }
    canonical_json = json.dumps(hash_input, separators=(',', ':'), sort_keys=True)
    report_id = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    findings = []
    
    rlc = lexical_metrics["response_length_chars"]
    if rlc == 0:
        findings.append({
            "severity": "WARNING",
            "code": "RESPONSE_EMPTY",
            "message": "response_length_chars is 0"
        })
    elif 0 < rlc < MIN_ANSWER_LENGTH_CHARS:
        findings.append({
            "severity": "WARNING",
            "code": "ANSWER_BELOW_MIN_LENGTH",
            "message": f"response_length_chars {rlc} is below {MIN_ANSWER_LENGTH_CHARS}"
        })
        
    span_count = groundedness_report["span_count"]
    if span_count > 0 and answer_quality_score == 0.0:
        findings.append({
            "severity": "WARNING",
            "code": "ZERO_ANSWER_QUALITY_SCORE",
            "message": "answer_quality_score is 0.0"
        })
    elif 0.0 < answer_quality_score < LOW_ANSWER_QUALITY_THRESHOLD:
        findings.append({
            "severity": "WARNING",
            "code": "LOW_ANSWER_QUALITY_SCORE",
            "message": f"answer_quality_score {answer_quality_score} is below {LOW_ANSWER_QUALITY_THRESHOLD}"
        })
        
    if 0.0 < citation_presence_ratio < LOW_CITATION_PRESENCE_THRESHOLD:
        findings.append({
            "severity": "WARNING",
            "code": "LOW_CITATION_PRESENCE",
            "message": f"citation_presence_ratio {citation_presence_ratio} is below {LOW_CITATION_PRESENCE_THRESHOLD}"
        })
        
    return {
        "answer_quality_report_id": report_id,
        "answer_quality_pipeline_version": ANSWER_QUALITY_PIPELINE_VERSION,
        "evaluated_at": get_now_iso(),
        "groundedness_report_id": groundedness_report["groundedness_report_id"],
        "cited_response_id": groundedness_report["cited_response_id"],
        "llm_response_id": groundedness_report["llm_response_id"],
        "prompt_package_id": groundedness_report["prompt_package_id"],
        "context_package_id": groundedness_report["context_package_id"],
        "status": groundedness_report["status"],
        "response_length_chars": rlc,
        "response_length_words": lexical_metrics["response_length_words"],
        "lexical_diversity_ratio": lexical_metrics["lexical_diversity_ratio"],
        "span_count": span_count,
        "average_span_length_chars": structural_metrics["average_span_length_chars"],
        "citation_presence_ratio": citation_presence_ratio,
        "answer_quality_score": answer_quality_score,
        "findings": findings,
        "groundedness_findings": list(groundedness_report["findings"])
    }

def validate_evaluation_report(report: Dict[str, Any], groundedness_report: Dict[str, Any]) -> None:
    rt = groundedness_report["response_text"]
    
    # RESPONSE_LENGTH_CHARS_MISMATCH
    if report["response_length_chars"] != len(rt):
        raise AnswerQualityEvaluationInternalError("RESPONSE_LENGTH_CHARS_MISMATCH")
        
    # Re-extract words
    if rt == "":
        words = []
    else:
        words = unicodedata.normalize('NFC', rt).split()
        
    # RESPONSE_LENGTH_WORDS_MISMATCH
    if report["response_length_words"] != len(words):
        raise AnswerQualityEvaluationInternalError("RESPONSE_LENGTH_WORDS_MISMATCH")
        
    # LEXICAL_DIVERSITY_MISMATCH
    if len(words) > 0:
        expected_ld = float(len({w.lower() for w in words})) / float(len(words))
    else:
        expected_ld = 0.0
    if report["lexical_diversity_ratio"] != expected_ld:
        raise AnswerQualityEvaluationInternalError("LEXICAL_DIVERSITY_MISMATCH")
        
    # AVERAGE_SPAN_LENGTH_MISMATCH
    sc = groundedness_report["span_count"]
    if sc > 0:
        expected_avg = float(len(rt)) / float(sc)
    else:
        expected_avg = 0.0
    if report["average_span_length_chars"] != expected_avg:
        raise AnswerQualityEvaluationInternalError("AVERAGE_SPAN_LENGTH_MISMATCH")
        
    # CITATION_PRESENCE_COMPUTATION_MISMATCH
    usc = groundedness_report["unsupported_span_count"]
    if sc > 0:
        expected_cpr = float(sc - usc) / float(sc)
    else:
        expected_cpr = 1.0
    if report["citation_presence_ratio"] != expected_cpr:
        raise AnswerQualityEvaluationInternalError("CITATION_PRESENCE_COMPUTATION_MISMATCH")
        
    # ANSWER_QUALITY_SCORE_COMPUTATION_MISMATCH
    expected_aqs = (float(groundedness_report["groundedness_score"]) * GROUNDEDNESS_WEIGHT) + (expected_cpr * CITATION_PRESENCE_WEIGHT)
    if report["answer_quality_score"] != expected_aqs:
        raise AnswerQualityEvaluationInternalError("ANSWER_QUALITY_SCORE_COMPUTATION_MISMATCH")
    if not (0.0 <= report["answer_quality_score"] <= 1.0):
        raise AnswerQualityEvaluationInternalError("ANSWER_QUALITY_SCORE_COMPUTATION_MISMATCH")
        
    # GROUNDEDNESS_REPORT_ID_MISMATCH
    for field in ["groundedness_report_id", "cited_response_id", "llm_response_id", "prompt_package_id", "context_package_id"]:
        if report[field] != groundedness_report[field]:
            raise AnswerQualityEvaluationInternalError("GROUNDEDNESS_REPORT_ID_MISMATCH")

def evaluate_answer_quality(groundedness_report: Dict[str, Any]) -> Dict[str, Any]:
    validate_groundedness_report(groundedness_report)
    
    lex = compute_lexical_metrics(groundedness_report["response_text"])
    
    struct = compute_structural_metrics(
        lex["response_length_chars"], 
        groundedness_report["span_count"]
    )
    
    cpr = compute_citation_presence_ratio(
        groundedness_report["span_count"], 
        groundedness_report["unsupported_span_count"]
    )
    
    aqs = compute_answer_quality_score(
        groundedness_report["groundedness_score"], 
        cpr
    )
    
    report = build_evaluation_report(
        groundedness_report,
        lex,
        struct,
        cpr,
        aqs
    )
    
    validate_evaluation_report(report, groundedness_report)
    
    return report
