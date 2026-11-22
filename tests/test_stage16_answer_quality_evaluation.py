import pytest
import sys
import copy
from typing import Dict, Any
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage16_answer_quality_evaluation import (
    evaluate_answer_quality,
    validate_groundedness_report,
    compute_lexical_metrics,
    compute_structural_metrics,
    compute_citation_presence_ratio,
    compute_answer_quality_score,
    build_evaluation_report,
    validate_evaluation_report,
    AnswerQualityEvaluationInputError,
    AnswerQualityEvaluationInternalError,
    MIN_ANSWER_LENGTH_CHARS,
    LOW_ANSWER_QUALITY_THRESHOLD,
    LOW_CITATION_PRESENCE_THRESHOLD
)

def get_mock_groundedness_report(status: str = "PASS") -> Dict[str, Any]:
    return {
        "groundedness_report_id": "gr-123",
        "cited_response_id": "cr-123",
        "llm_response_id": "lr-123",
        "prompt_package_id": "pp-123",
        "context_package_id": "cp-123",
        "status": status,
        "response_text": "This is a simple answer. It has multiple words.",
        "span_count": 2,
        "unsupported_span_count": 0,
        "groundedness_score": 1.0,
        "findings": []
    }

# --- Normal Execution & Determinism ---

def test_evaluate_answer_quality_normal():
    report = get_mock_groundedness_report()
    result = evaluate_answer_quality(report)
    
    assert result["status"] == "PASS"
    assert result["answer_quality_report_id"] is not None
    assert result["response_length_chars"] == len("This is a simple answer. It has multiple words.")
    assert result["response_length_words"] == 9
    assert result["lexical_diversity_ratio"] == 1.0  # all 9 words are unique
    assert result["span_count"] == 2
    assert result["average_span_length_chars"] == len("This is a simple answer. It has multiple words.") / 2.0
    assert result["citation_presence_ratio"] == 1.0
    assert result["answer_quality_score"] == 1.0
    assert len(result["findings"]) == 0

def test_determinism_identical_inputs():
    report1 = get_mock_groundedness_report()
    report2 = get_mock_groundedness_report()
    
    out1 = evaluate_answer_quality(report1)
    out2 = evaluate_answer_quality(report2)
    
    out1["evaluated_at"] = ""
    out2["evaluated_at"] = ""
    
    assert out1 == out2

def test_immutability():
    report = get_mock_groundedness_report()
    report_copy = copy.deepcopy(report)
    evaluate_answer_quality(report)
    assert report == report_copy

# --- Lexical & Word Extraction Logic ---

def test_lexical_word_extraction_empty():
    res = compute_lexical_metrics("")
    assert res["response_length_chars"] == 0
    assert res["response_length_words"] == 0
    assert res["lexical_diversity_ratio"] == 0.0

def test_lexical_word_extraction_whitespace_only():
    res = compute_lexical_metrics("   \n\t  ")
    assert res["response_length_chars"] == 7
    assert res["response_length_words"] == 0
    assert res["lexical_diversity_ratio"] == 0.0

def test_lexical_word_extraction_punctuation():
    text = "Isn't it well-known? Yes, it is."
    res = compute_lexical_metrics(text)
    # Words should be: ["Isn't", "it", "well-known?", "Yes,", "it", "is."]
    # Unique folded: {"isn't", "it", "well-known?", "yes,", "is."} -> 5 unique out of 6
    assert res["response_length_words"] == 6
    assert res["lexical_diversity_ratio"] == 5.0 / 6.0

def test_lexical_word_extraction_nfc_normalization():
    # 'e' + combining acute accent vs precomposed 'é'
    text_nfd = "cafe\u0301 cafe\u0301"
    text_nfc = "caf\u00e9 caf\u00e9"
    
    res_nfd = compute_lexical_metrics(text_nfd)
    res_nfc = compute_lexical_metrics(text_nfc)
    
    assert res_nfd["response_length_words"] == 2
    assert res_nfd["lexical_diversity_ratio"] == 0.5  # 1 unique / 2 total
    assert res_nfc["response_length_words"] == 2
    assert res_nfc["lexical_diversity_ratio"] == 0.5

# --- Status Passthrough & Empty / Vacuous Paths ---

def test_status_passthrough():
    for status in ["PASS", "PARTIAL", "FAIL", "SKIPPED"]:
        report = get_mock_groundedness_report(status)
        if status in ["FAIL", "SKIPPED"]:
            report["response_text"] = ""
            report["span_count"] = 0
            report["unsupported_span_count"] = 0
            # vacuously 1.0 in Stage 15
            report["groundedness_score"] = 1.0
            
        result = evaluate_answer_quality(report)
        assert result["status"] == status
        
        if status in ["FAIL", "SKIPPED"]:
            assert result["response_length_chars"] == 0
            assert result["response_length_words"] == 0
            assert result["lexical_diversity_ratio"] == 0.0
            assert result["average_span_length_chars"] == 0.0
            assert result["citation_presence_ratio"] == 1.0
            assert result["answer_quality_score"] == 1.0
            
            codes = [f["code"] for f in result["findings"]]
            assert "RESPONSE_EMPTY" in codes

# --- Threshold Boundaries & Findings ---

def test_finding_answer_below_min_length():
    report = get_mock_groundedness_report()
    report["response_text"] = "Short."
    report["span_count"] = 1
    
    result = evaluate_answer_quality(report)
    assert 0 < result["response_length_chars"] < MIN_ANSWER_LENGTH_CHARS
    
    codes = [f["code"] for f in result["findings"]]
    assert "ANSWER_BELOW_MIN_LENGTH" in codes

def test_finding_zero_answer_quality_score():
    report = get_mock_groundedness_report()
    report["groundedness_score"] = 0.0
    report["unsupported_span_count"] = report["span_count"]  # presence ratio = 0.0
    
    result = evaluate_answer_quality(report)
    assert result["answer_quality_score"] == 0.0
    
    codes = [f["code"] for f in result["findings"]]
    assert "ZERO_ANSWER_QUALITY_SCORE" in codes

def test_finding_low_answer_quality_score():
    report = get_mock_groundedness_report()
    report["groundedness_score"] = 0.2
    report["unsupported_span_count"] = report["span_count"]  # presence ratio = 0.0
    
    result = evaluate_answer_quality(report)
    assert 0.0 < result["answer_quality_score"] < LOW_ANSWER_QUALITY_THRESHOLD
    
    codes = [f["code"] for f in result["findings"]]
    assert "LOW_ANSWER_QUALITY_SCORE" in codes

def test_finding_low_citation_presence():
    report = get_mock_groundedness_report()
    report["span_count"] = 10
    report["unsupported_span_count"] = 8  # ratio = 0.2
    report["groundedness_score"] = 1.0    # high groundedness so score > 0
    
    result = evaluate_answer_quality(report)
    assert 0.0 < result["citation_presence_ratio"] < LOW_CITATION_PRESENCE_THRESHOLD
    
    codes = [f["code"] for f in result["findings"]]
    assert "LOW_CITATION_PRESENCE" in codes

# --- Input Validation ---

def test_input_validation_missing_key():
    report = get_mock_groundedness_report()
    del report["span_count"]
    with pytest.raises(AnswerQualityEvaluationInputError, match="GROUNDEDNESS_REPORT_MALFORMED"):
        evaluate_answer_quality(report)

def test_input_validation_wrong_type():
    report = get_mock_groundedness_report()
    report["groundedness_score"] = "1.0"
    with pytest.raises(AnswerQualityEvaluationInputError, match="GROUNDEDNESS_REPORT_MALFORMED"):
        evaluate_answer_quality(report)

# --- Internal Invariant Validation ---

def test_invariant_response_length_chars_mismatch():
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["response_length_chars"] = 999
    with pytest.raises(AnswerQualityEvaluationInternalError, match="RESPONSE_LENGTH_CHARS_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_response_length_words_mismatch():
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["response_length_words"] = 999
    with pytest.raises(AnswerQualityEvaluationInternalError, match="RESPONSE_LENGTH_WORDS_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_lexical_diversity_mismatch():
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["lexical_diversity_ratio"] = 0.5
    with pytest.raises(AnswerQualityEvaluationInternalError, match="LEXICAL_DIVERSITY_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_average_span_length_mismatch():
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["average_span_length_chars"] = 0.5
    with pytest.raises(AnswerQualityEvaluationInternalError, match="AVERAGE_SPAN_LENGTH_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_citation_presence_computation_mismatch():
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["citation_presence_ratio"] = 0.5
    with pytest.raises(AnswerQualityEvaluationInternalError, match="CITATION_PRESENCE_COMPUTATION_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_answer_quality_score_computation_mismatch():
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["answer_quality_score"] = 0.5
    with pytest.raises(AnswerQualityEvaluationInternalError, match="ANSWER_QUALITY_SCORE_COMPUTATION_MISMATCH"):
        validate_evaluation_report(out, report)
        
    out["answer_quality_score"] = 1.5
    with pytest.raises(AnswerQualityEvaluationInternalError, match="ANSWER_QUALITY_SCORE_COMPUTATION_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_groundedness_report_id_mismatch():
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    
    out["groundedness_report_id"] = "wrong"
    with pytest.raises(AnswerQualityEvaluationInternalError, match="GROUNDEDNESS_REPORT_ID_MISMATCH"):
        validate_evaluation_report(out, report)
        
    out = evaluate_answer_quality(report)
    out["cited_response_id"] = "wrong"
    with pytest.raises(AnswerQualityEvaluationInternalError, match="GROUNDEDNESS_REPORT_ID_MISMATCH"):
        validate_evaluation_report(out, report)

# ---------------------------------------------------------------------------
# Fix 1 — GROUNDEDNESS_REPORT_ID_MISMATCH: remaining three identity fields
# ---------------------------------------------------------------------------

def test_invariant_groundedness_report_id_mismatch_llm_response_id():
    """llm_response_id mismatch alone must raise GROUNDEDNESS_REPORT_ID_MISMATCH."""
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["llm_response_id"] = "tampered-llm-id"
    with pytest.raises(AnswerQualityEvaluationInternalError, match="GROUNDEDNESS_REPORT_ID_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_groundedness_report_id_mismatch_prompt_package_id():
    """prompt_package_id mismatch alone must raise GROUNDEDNESS_REPORT_ID_MISMATCH."""
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["prompt_package_id"] = "tampered-prompt-id"
    with pytest.raises(AnswerQualityEvaluationInternalError, match="GROUNDEDNESS_REPORT_ID_MISMATCH"):
        validate_evaluation_report(out, report)

def test_invariant_groundedness_report_id_mismatch_context_package_id():
    """context_package_id mismatch alone must raise GROUNDEDNESS_REPORT_ID_MISMATCH."""
    report = get_mock_groundedness_report()
    out = evaluate_answer_quality(report)
    out["context_package_id"] = "tampered-context-id"
    with pytest.raises(AnswerQualityEvaluationInternalError, match="GROUNDEDNESS_REPORT_ID_MISMATCH"):
        validate_evaluation_report(out, report)

# ---------------------------------------------------------------------------
# Fix 2 — ANSWER_BELOW_MIN_LENGTH exact boundary
# Architecture: 0 < response_length_chars < MIN_ANSWER_LENGTH_CHARS
# ---------------------------------------------------------------------------

def test_finding_answer_below_min_length_boundary_fires():
    """response_length_chars == MIN_ANSWER_LENGTH_CHARS - 1 must trigger ANSWER_BELOW_MIN_LENGTH."""
    report = get_mock_groundedness_report()
    # Construct a response of exactly MIN_ANSWER_LENGTH_CHARS - 1 = 19 characters.
    target_len = MIN_ANSWER_LENGTH_CHARS - 1  # 19
    report["response_text"] = "A" * target_len
    report["span_count"] = 1
    report["unsupported_span_count"] = 0

    result = evaluate_answer_quality(report)

    assert result["response_length_chars"] == target_len
    codes = [f["code"] for f in result["findings"]]
    assert "ANSWER_BELOW_MIN_LENGTH" in codes

def test_finding_answer_below_min_length_boundary_does_not_fire():
    """response_length_chars == MIN_ANSWER_LENGTH_CHARS must NOT trigger ANSWER_BELOW_MIN_LENGTH
    (condition is strictly less-than, not less-than-or-equal)."""
    report = get_mock_groundedness_report()
    # Construct a response of exactly MIN_ANSWER_LENGTH_CHARS = 20 characters.
    target_len = MIN_ANSWER_LENGTH_CHARS  # 20
    report["response_text"] = "A" * target_len
    report["span_count"] = 1
    report["unsupported_span_count"] = 0

    result = evaluate_answer_quality(report)

    assert result["response_length_chars"] == target_len
    codes = [f["code"] for f in result["findings"]]
    assert "ANSWER_BELOW_MIN_LENGTH" not in codes

# ---------------------------------------------------------------------------
# Fix 3 — LOW_ANSWER_QUALITY_SCORE exact boundary
# Architecture: 0.0 < answer_quality_score < LOW_ANSWER_QUALITY_THRESHOLD
# ---------------------------------------------------------------------------

def test_finding_low_answer_quality_score_at_threshold_does_not_fire():
    """answer_quality_score == LOW_ANSWER_QUALITY_THRESHOLD (0.5) must NOT trigger
    LOW_ANSWER_QUALITY_SCORE (condition is strictly less-than)."""
    # Construct inputs that produce answer_quality_score == exactly 0.5.
    # score = groundedness_score * 0.7 + citation_presence_ratio * 0.3
    # With citation_presence_ratio = 1.0 (no unsupported spans):
    #   0.5 = gs * 0.7 + 1.0 * 0.3  =>  gs = (0.5 - 0.3) / 0.7 = 2/7
    # But gs must be readable from the report without Stage 16 computing it.
    # Simpler: use span_count=0 path is vacuous. Use cited spans instead.
    # citation_presence_ratio = 0 (all unsupported), gs driving the score:
    #   0.5 = gs * 0.7 + 0.0 * 0.3  =>  gs = 5/7 (irrational in float)
    # Cleanest approach: gs = 0.5, citation_presence_ratio = 0.5
    #   score = 0.5 * 0.7 + 0.5 * 0.3 = 0.35 + 0.15 = 0.5 exactly
    report = get_mock_groundedness_report()
    report["span_count"] = 2
    report["unsupported_span_count"] = 1   # citation_presence_ratio = (2-1)/2 = 0.5
    report["groundedness_score"] = 0.5

    result = evaluate_answer_quality(report)

    assert result["answer_quality_score"] == LOW_ANSWER_QUALITY_THRESHOLD
    codes = [f["code"] for f in result["findings"]]
    assert "LOW_ANSWER_QUALITY_SCORE" not in codes

def test_finding_low_answer_quality_score_just_below_threshold_fires():
    """answer_quality_score strictly below LOW_ANSWER_QUALITY_THRESHOLD must trigger
    LOW_ANSWER_QUALITY_SCORE."""
    # score = gs * 0.7 + cpr * 0.3; use gs=0.4, cpr=0.5 => 0.28 + 0.15 = 0.43 < 0.5
    report = get_mock_groundedness_report()
    report["span_count"] = 2
    report["unsupported_span_count"] = 1   # citation_presence_ratio = 0.5
    report["groundedness_score"] = 0.4

    result = evaluate_answer_quality(report)

    assert 0.0 < result["answer_quality_score"] < LOW_ANSWER_QUALITY_THRESHOLD
    codes = [f["code"] for f in result["findings"]]
    assert "LOW_ANSWER_QUALITY_SCORE" in codes

# ---------------------------------------------------------------------------
# Fix 4 — Co-occurrence: LOW_CITATION_PRESENCE and LOW_ANSWER_QUALITY_SCORE
# Architecture Failure Handling: these "may co-occur"
# ---------------------------------------------------------------------------

def test_finding_low_citation_presence_and_low_answer_quality_score_cooccur():
    """LOW_CITATION_PRESENCE and LOW_ANSWER_QUALITY_SCORE must both appear when both
    conditions are met simultaneously; neither suppresses the other."""
    # citation_presence_ratio = (10 - 8) / 10 = 0.2  =>  LOW_CITATION_PRESENCE fires
    # answer_quality_score = 0.3 * 0.7 + 0.2 * 0.3 = 0.21 + 0.06 = 0.27  => LOW_ANSWER_QUALITY_SCORE fires
    report = get_mock_groundedness_report()
    report["span_count"] = 10
    report["unsupported_span_count"] = 8    # citation_presence_ratio = 0.2
    report["groundedness_score"] = 0.3     # answer_quality_score = 0.27

    result = evaluate_answer_quality(report)

    assert 0.0 < result["citation_presence_ratio"] < LOW_CITATION_PRESENCE_THRESHOLD
    assert 0.0 < result["answer_quality_score"] < LOW_ANSWER_QUALITY_THRESHOLD

    codes = [f["code"] for f in result["findings"]]
    assert "LOW_CITATION_PRESENCE" in codes
    assert "LOW_ANSWER_QUALITY_SCORE" in codes

    # Verify severities match the architecture (both must be WARNING)
    for finding in result["findings"]:
        if finding["code"] in ("LOW_CITATION_PRESENCE", "LOW_ANSWER_QUALITY_SCORE"):
            assert finding["severity"] == "WARNING"

    # Verify no unrelated findings are emitted (response_text is long enough)
    assert "RESPONSE_EMPTY" not in codes
    assert "ANSWER_BELOW_MIN_LENGTH" not in codes
    assert "ZERO_ANSWER_QUALITY_SCORE" not in codes

