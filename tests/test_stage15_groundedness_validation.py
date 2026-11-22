import pytest
import sys
import copy
from unittest.mock import patch, MagicMock
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage15_groundedness_validation import (
    fold,
    lcs_len,
    compute_groundedness_overlap,
    validate_groundedness,
    validate_cited_response,
    validate_context_package,
    verify_context_package_match,
    verify_span_groundedness,
    GroundednessValidationInputError,
    GroundednessValidationInternalError,
    DEFAULT_GROUNDEDNESS_THRESHOLD,
    LOW_GROUNDEDNESS_THRESHOLD,
    build_groundedness_report,
    validate_groundedness_report
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_mock_context_package():
    return {
        "context_package_id": "pkg-1",
        "context_blocks": [
            {
                "context_block_id": "blk-1",
                "chunk_id": "chunk-1",
                "text": "apples are red and delicious."
            },
            {
                "context_block_id": "blk-2",
                "chunk_id": "chunk-2",
                "text": "bananas are yellow."
            },
            {
                "context_block_id": "blk-3",
                "chunk_id": "chunk-3",
                "text": "apples are red and delicious. truly."
            }
        ]
    }

def get_mock_cited_response(status="PASS"):
    return {
        "cited_response_id": "cited-1",
        "llm_response_id": "llm-1",
        "prompt_package_id": "prompt-1",
        "context_package_id": "pkg-1",
        "status": status,
        "response_text": "Apples are red. Bananas are yellow. Oranges.",
        "spans": [
            {
                "span_index": 0,
                "text": "Apples are red.",
                "citations": [
                    {
                        "context_block_id": "blk-1",
                        "chunk_id": "chunk-1",
                        "doc_id": "doc-1",
                        "match_score": 0.9
                    },
                    {
                        "context_block_id": "blk-3",
                        "chunk_id": "chunk-3",
                        "doc_id": "doc-1",
                        "match_score": 0.8
                    }
                ]
            },
            {
                "span_index": 1,
                "text": "Bananas are yellow.",
                "citations": [
                    {
                        "context_block_id": "blk-2",
                        "chunk_id": "chunk-2",
                        "doc_id": "doc-2",
                        "match_score": 0.85
                    }
                ]
            },
            {
                "span_index": 2,
                "text": "Oranges.",
                "citations": []
            }
        ],
        "findings": []
    }

# ---------------------------------------------------------------------------
# LCS & Normalization
# ---------------------------------------------------------------------------

def test_fold_normalization():
    assert fold("Hello World") == "hello world"
    assert fold("  multiple   spaces  \n here ") == "multiple spaces here"
    # Fix 1: \r and CRLF must collapse identically to spaces, not leave stray \r
    assert fold("climate\r\nchange") == "climate change"
    assert fold("bare\rcarriage") == "bare carriage"
    
def test_fold_unicode_nfc():
    """Architecture line 166: Unicode normalization to NFC."""
    # e followed by combining acute accent (NFD) should fold identically to
    # precomposed e-acute (NFC).
    nfd_str = "caf\u0065\u0301"   # e + combining acute
    nfc_str = "caf\u00e9"         # precomposed e-acute
    assert fold(nfd_str) == fold(nfc_str)

def test_lcs_len_basic():
    assert lcs_len("abcdef", "zbcdg") == 3
    assert lcs_len("", "abc") == 0
    assert lcs_len("abc", "") == 0

def test_compute_groundedness_overlap_exact():
    """Short span fully contained in longer block scores 1.0."""
    span = "apples are delicious"
    block = "i think apples are delicious indeed."
    assert compute_groundedness_overlap(span, block) == 1.0

def test_compute_groundedness_overlap_partial():
    span2 = "apples are very delicious"
    block = "i think apples are delicious indeed."
    score = compute_groundedness_overlap(span2, block)
    assert score == 11.0 / 25.0

def test_compute_groundedness_overlap_empty_span():
    """Architecture line 212: returns 0.0 when fold(span_text) is empty."""
    assert compute_groundedness_overlap("", "some block text") == 0.0
    assert compute_groundedness_overlap("   ", "some block text") == 0.0

def test_compute_groundedness_overlap_zero_match():
    """No common substring at all."""
    assert compute_groundedness_overlap("xyz", "abc") == 0.0

# ---------------------------------------------------------------------------
# Public API & Package construction
# ---------------------------------------------------------------------------

def test_validate_groundedness_basic():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    
    rep = validate_groundedness(cited, context)
    
    assert rep["status"] == "PASS"
    assert rep["span_count"] == 3
    assert rep["grounded_span_count"] == 2
    assert rep["weakly_grounded_span_count"] == 0
    assert rep["unsupported_span_count"] == 1
    assert rep["groundedness_score"] == 2.0 / 3.0
    
    # Span 0
    sg0 = rep["span_groundedness"][0]
    assert sg0["groundedness"] == "GROUNDED"
    assert sg0["strongest_grounding"]["chunk_id"] == "chunk-1"
    assert sg0["best_groundedness_score"] > 0.8
    
    # Span 2
    sg2 = rep["span_groundedness"][2]
    assert sg2["groundedness"] == "UNSUPPORTED"
    assert sg2["best_groundedness_score"] is None
    assert sg2["strongest_grounding"] is None

# ---------------------------------------------------------------------------
# Thresholds: exactly equal, below, above
# ---------------------------------------------------------------------------

def test_threshold_exactly_equal():
    """GROUNDED iff best_groundedness_score >= threshold (closed comparison)."""
    # Build a case where the LCS score is exactly 1.0
    context = {
        "context_package_id": "pkg-1",
        "context_blocks": [
            {
                "context_block_id": "blk-1",
                "chunk_id": "chunk-1",
                "text": "i believe apples are red. that is a fact."
            }
        ]
    }
    cited = {
        "cited_response_id": "cited-1",
        "llm_response_id": "llm-1",
        "prompt_package_id": "prompt-1",
        "context_package_id": "pkg-1",
        "status": "PASS",
        "response_text": "Apples are red.",
        "spans": [
            {
                "span_index": 0,
                "text": "Apples are red.",
                "citations": [
                    {"context_block_id": "blk-1", "chunk_id": "chunk-1", "doc_id": "doc-1", "match_score": 0.9}
                ]
            }
        ],
        "findings": []
    }
    # Verify the score is truly 1.0 before testing threshold
    score = compute_groundedness_overlap("Apples are red.", "i believe apples are red. that is a fact.")
    assert score == 1.0
    
    # Set threshold to exactly 1.0 -> should still be GROUNDED (>=)
    rep = validate_groundedness(cited, context, 1.0)
    assert rep["span_groundedness"][0]["groundedness"] == "GROUNDED"

def test_threshold_below():
    """Score below threshold -> WEAKLY_GROUNDED."""
    cited = get_mock_cited_response()
    cited["spans"][0]["text"] = "Apples are red and blue."
    context = get_mock_context_package()
    # folded span len: 24, LCS with block: "apples are red and " len 19
    # score = 19/24 ≈ 0.7917 < 0.8 threshold
    rep = validate_groundedness(cited, context, 0.8)
    assert rep["span_groundedness"][0]["groundedness"] == "WEAKLY_GROUNDED"

def test_threshold_above():
    """Score above threshold -> GROUNDED."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    # span "Apples are red." score 1.0 vs threshold 0.5 -> GROUNDED
    rep = validate_groundedness(cited, context, 0.5)
    assert rep["span_groundedness"][0]["groundedness"] == "GROUNDED"

def test_threshold_clamping():
    """Architecture line 487-489: out-of-range thresholds clamped to [0.0, 1.0]."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    
    rep_high = validate_groundedness(cited, context, 5.0)
    assert rep_high["groundedness_threshold"] == 1.0
    
    rep_low = validate_groundedness(cited, context, -1.0)
    assert rep_low["groundedness_threshold"] == 0.0

# ---------------------------------------------------------------------------
# Status propagation
# ---------------------------------------------------------------------------

def test_status_passthrough_fail():
    cited = get_mock_cited_response("FAIL")
    cited["spans"] = []
    rep = validate_groundedness(cited, get_mock_context_package())
    
    assert rep["status"] == "FAIL"
    assert rep["span_count"] == 0
    assert rep["groundedness_score"] == 1.0
    assert any(f["code"] == "RESPONSE_EMPTY" for f in rep["findings"])

def test_status_passthrough_skipped():
    """Architecture line 386: SKIPPED status passthrough."""
    cited = get_mock_cited_response("SKIPPED")
    cited["spans"] = []
    rep = validate_groundedness(cited, get_mock_context_package())
    
    assert rep["status"] == "SKIPPED"
    assert rep["span_count"] == 0
    assert rep["groundedness_score"] == 1.0
    assert any(f["code"] == "RESPONSE_EMPTY" for f in rep["findings"])

def test_status_passthrough_partial():
    """Architecture line 388: PARTIAL status passthrough."""
    cited = get_mock_cited_response("PARTIAL")
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    
    assert rep["status"] == "PARTIAL"
    assert rep["span_count"] == 3

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def test_finding_zero_grounded_claims():
    """Architecture line 378: ZERO_GROUNDED_CLAIMS when span_count > 0 and score == 0.0."""
    cited = get_mock_cited_response()
    # Make all spans UNSUPPORTED (no citations)
    for span in cited["spans"]:
        span["citations"] = []
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    
    assert rep["span_count"] == 3
    assert rep["groundedness_score"] == 0.0
    findings_codes = [f["code"] for f in rep["findings"]]
    assert "ZERO_GROUNDED_CLAIMS" in findings_codes
    # Verify severity
    zg = [f for f in rep["findings"] if f["code"] == "ZERO_GROUNDED_CLAIMS"][0]
    assert zg["severity"] == "WARNING"
    # Status unchanged
    assert rep["status"] == "PASS"

def test_finding_low_groundedness_score():
    """Architecture line 379: LOW_GROUNDEDNESS_SCORE when 0.0 < score < LOW_GROUNDEDNESS_THRESHOLD."""
    # We need exactly 1 GROUNDED span out of many so score is low but > 0.
    cited = get_mock_cited_response()
    # Add 3 more UNSUPPORTED spans to get grounded_span_count/span_count < 0.5
    cited["spans"].append({"span_index": 3, "text": "No citation here.", "citations": []})
    cited["spans"].append({"span_index": 4, "text": "No citation here either.", "citations": []})
    cited["spans"].append({"span_index": 5, "text": "Another uncited span.", "citations": []})
    # Now: 2 GROUNDED, 1 WEAKLY or GROUNDED (banana), 4 UNSUPPORTED -> 6 total
    # Actually let's be precise: span 0 = GROUNDED, span 1 = GROUNDED, span 2-5 = UNSUPPORTED
    # score = 2/6 = 0.333 < 0.5
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    
    assert 0.0 < rep["groundedness_score"] < LOW_GROUNDEDNESS_THRESHOLD
    findings_codes = [f["code"] for f in rep["findings"]]
    assert "LOW_GROUNDEDNESS_SCORE" in findings_codes
    lg = [f for f in rep["findings"] if f["code"] == "LOW_GROUNDEDNESS_SCORE"][0]
    assert lg["severity"] == "WARNING"
    assert rep["status"] == "PASS"

# ---------------------------------------------------------------------------
# strongest_grounding differs from citations[0]
# ---------------------------------------------------------------------------

def test_strongest_grounding_differs_from_citations_0():
    """Architecture Validation Requirements line 645-648:
    A case where citations[0] (top match_score) is NOT the highest LCS score."""
    context = {
        "context_package_id": "pkg-1",
        "context_blocks": [
            {
                "context_block_id": "blk-A",
                "chunk_id": "chunk-A",
                # Block A shares scattered words but no long contiguous run with the span
                "text": "climate policy framework sustainability development goals agenda"
            },
            {
                "context_block_id": "blk-B",
                "chunk_id": "chunk-B",
                # Block B contains the span nearly verbatim
                "text": "the climate policy framework is essential for sustainability."
            }
        ]
    }
    cited = {
        "cited_response_id": "cited-1",
        "llm_response_id": "llm-1",
        "prompt_package_id": "prompt-1",
        "context_package_id": "pkg-1",
        "status": "PASS",
        "response_text": "Climate policy framework is essential.",
        "spans": [
            {
                "span_index": 0,
                "text": "Climate policy framework is essential.",
                "citations": [
                    # citations[0] has higher match_score (Stage 14's metric) but worse LCS
                    {
                        "context_block_id": "blk-A",
                        "chunk_id": "chunk-A",
                        "doc_id": "doc-1",
                        "match_score": 0.95
                    },
                    # citations[1] has lower match_score but better LCS (contiguous run)
                    {
                        "context_block_id": "blk-B",
                        "chunk_id": "chunk-B",
                        "doc_id": "doc-1",
                        "match_score": 0.7
                    }
                ]
            }
        ],
        "findings": []
    }
    
    rep = validate_groundedness(cited, context, 0.5)
    sg = rep["span_groundedness"][0]
    
    # strongest_grounding should be blk-B (higher LCS), not blk-A (citations[0])
    assert sg["strongest_grounding"]["context_block_id"] == "blk-B"
    assert sg["strongest_grounding"]["chunk_id"] == "chunk-B"

# ---------------------------------------------------------------------------
# UNSUPPORTED spans: no computation
# ---------------------------------------------------------------------------

def test_unsupported_span_no_computation():
    """Architecture Validation Requirements line 641:
    UNSUPPORTED spans make zero calls to compute_groundedness_overlap."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    blocks_by_id = {b["context_block_id"]: b for b in context["context_blocks"]}
    
    unsupported_span = cited["spans"][2]  # citations == []
    
    with patch("scripts.stage15_groundedness_validation.compute_groundedness_overlap") as mock_overlap:
        result = verify_span_groundedness(unsupported_span, blocks_by_id, 0.8)
        mock_overlap.assert_not_called()
    
    assert result["groundedness"] == "UNSUPPORTED"
    assert result["best_groundedness_score"] is None
    assert result["strongest_grounding"] is None

# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

def test_immutability():
    """Architecture Validation Requirements line 662:
    Neither input object is ever mutated."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    
    cited_before = copy.deepcopy(cited)
    context_before = copy.deepcopy(context)
    
    validate_groundedness(cited, context)
    
    assert cited == cited_before
    assert context == context_before

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_input_validation():
    # Bad CitedResponse
    bad_cited = get_mock_cited_response()
    del bad_cited["status"]
    with pytest.raises(GroundednessValidationInputError, match="CITED_RESPONSE_MALFORMED"):
        validate_groundedness(bad_cited, get_mock_context_package())
        
    # Bad ContextPackage
    bad_context = get_mock_context_package()
    del bad_context["context_blocks"]
    with pytest.raises(GroundednessValidationInputError, match="CONTEXT_PACKAGE_MALFORMED"):
        validate_groundedness(get_mock_cited_response(), bad_context)
        
    # ID Mismatch
    bad_cited = get_mock_cited_response()
    bad_cited["context_package_id"] = "wrong"
    with pytest.raises(GroundednessValidationInputError, match="CONTEXT_PACKAGE_ID_MISMATCH"):
        validate_groundedness(bad_cited, get_mock_context_package())

# ---------------------------------------------------------------------------
# Internal invariants
# ---------------------------------------------------------------------------

def test_invariants_span_count():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    rep["span_groundedness"].pop()
    
    with pytest.raises(GroundednessValidationInternalError, match="SPAN_COUNT_MISMATCH"):
        validate_groundedness_report(rep, cited, context)

def test_invariants_span_alignment():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    rep["span_groundedness"][0]["span_index"] = 99
    
    with pytest.raises(GroundednessValidationInternalError, match="SPAN_ALIGNMENT_MISMATCH"):
        validate_groundedness_report(rep, cited, context)
        
def test_invariants_label_invalid():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    rep["span_groundedness"][0]["groundedness"] = "UNSUPPORTED"
    
    with pytest.raises(GroundednessValidationInternalError, match="GROUNDEDNESS_LABEL_INVALID"):
        validate_groundedness_report(rep, cited, context)
        
def test_invariants_strongest_grounding_mismatch():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    # Replace strongest_grounding with wrong citation that IS in the span's list
    # but is NOT the one with the max LCS score
    rep["span_groundedness"][0]["strongest_grounding"] = {
        "context_block_id": "wrong",
        "chunk_id": "wrong",
        "doc_id": "wrong",
        "match_score": 1.0
    }
    
    with pytest.raises(GroundednessValidationInternalError, match="STRONGEST_GROUNDING_MISMATCH"):
        validate_groundedness_report(rep, cited, context)

def test_invariants_computation_mismatch():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    rep["groundedness_score"] = 0.99
    
    with pytest.raises(GroundednessValidationInternalError, match="GROUNDEDNESS_COMPUTATION_MISMATCH"):
        validate_groundedness_report(rep, cited, context)
        
def test_invariants_id_mismatch():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    rep["cited_response_id"] = "wrong"
    
    with pytest.raises(GroundednessValidationInternalError, match="CITED_RESPONSE_ID_MISMATCH"):
        validate_groundedness_report(rep, cited, context)

# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_determinism():
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    
    rep1 = validate_groundedness(copy.deepcopy(cited), copy.deepcopy(context))
    rep2 = validate_groundedness(copy.deepcopy(cited), copy.deepcopy(context))
    
    rep1["validated_at"] = ""
    rep2["validated_at"] = ""
    
    assert rep1 == rep2

# ---------------------------------------------------------------------------
# Fix 1 — STRONGEST_GROUNDING_MISMATCH: guard path (citations == [] but
#          strongest_grounding is not None)
# ---------------------------------------------------------------------------

def test_invariant_strongest_grounding_mismatch_non_null_on_unsupported_span():
    """strongest_grounding != None on a span with citations == [] must raise
    STRONGEST_GROUNDING_MISMATCH, not an incidental TypeError."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)

    # Tamper: inject a non-null strongest_grounding on span 2 which has no citations.
    rep["span_groundedness"][2]["strongest_grounding"] = {
        "context_block_id": "blk-1",
        "chunk_id": "chunk-1",
        "doc_id": "doc-1",
        "match_score": 0.9
    }

    with pytest.raises(GroundednessValidationInternalError, match="STRONGEST_GROUNDING_MISMATCH"):
        validate_groundedness_report(rep, cited, context)

# ---------------------------------------------------------------------------
# Fix 2 — Reference aliasing: strongest_grounding and citation_findings must
#          be independent copies, not aliases of mutable input objects.
# ---------------------------------------------------------------------------

def test_strongest_grounding_is_not_aliased_to_input():
    """Mutating the returned strongest_grounding must not affect the original
    citation dict inside cited_response."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)

    original_match_score = cited["spans"][0]["citations"][0]["match_score"]

    # Mutate the copy on the report.
    rep["span_groundedness"][0]["strongest_grounding"]["match_score"] = 999.0

    # The original citation inside cited_response must be unchanged.
    assert cited["spans"][0]["citations"][0]["match_score"] == original_match_score

def test_citation_findings_is_not_aliased_to_input():
    """Mutating the returned citation_findings list must not affect the original
    findings list inside cited_response."""
    cited = get_mock_cited_response()
    cited["findings"] = [{"severity": "WARNING", "code": "SOME_CODE", "message": "msg"}]
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)

    original_len = len(cited["findings"])

    # Mutate the copy on the report.
    rep["citation_findings"].append({"severity": "WARNING", "code": "EXTRA", "message": "extra"})

    # The original findings list inside cited_response must be unchanged.
    assert len(cited["findings"]) == original_len

# ---------------------------------------------------------------------------
# Fix 3 — GROUNDEDNESS_LABEL_INVALID: remaining branches, each individually.
# ---------------------------------------------------------------------------

def test_invariant_label_invalid_unsupported_but_has_citations_branch():
    """citations != [] but groundedness == UNSUPPORTED must raise GROUNDEDNESS_LABEL_INVALID."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)

    # Span 0 has citations; tamper its label to UNSUPPORTED.
    rep["span_groundedness"][0]["groundedness"] = "UNSUPPORTED"

    with pytest.raises(GroundednessValidationInternalError, match="GROUNDEDNESS_LABEL_INVALID"):
        validate_groundedness_report(rep, cited, context)

def test_invariant_label_invalid_grounded_but_score_below_threshold():
    """groundedness == GROUNDED but best_groundedness_score < groundedness_threshold
    must raise GROUNDEDNESS_LABEL_INVALID."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    # Use threshold 0.8; span 0 will be GROUNDED with a real score.
    rep = validate_groundedness(cited, context, 0.8)

    # Tamper: claim GROUNDED but inject a score below the stored threshold.
    rep["span_groundedness"][0]["groundedness"] = "GROUNDED"
    rep["span_groundedness"][0]["best_groundedness_score"] = 0.1  # below 0.8

    with pytest.raises(GroundednessValidationInternalError, match="GROUNDEDNESS_LABEL_INVALID"):
        validate_groundedness_report(rep, cited, context)

def test_invariant_label_invalid_weakly_grounded_but_score_at_or_above_threshold():
    """groundedness == WEAKLY_GROUNDED but best_groundedness_score >= groundedness_threshold
    must raise GROUNDEDNESS_LABEL_INVALID."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context, 0.8)

    # Tamper: claim WEAKLY_GROUNDED but inject a score that meets the threshold.
    rep["span_groundedness"][0]["groundedness"] = "WEAKLY_GROUNDED"
    rep["span_groundedness"][0]["best_groundedness_score"] = 0.9  # >= 0.8

    with pytest.raises(GroundednessValidationInternalError, match="GROUNDEDNESS_LABEL_INVALID"):
        validate_groundedness_report(rep, cited, context)

# ---------------------------------------------------------------------------
# Fix 3 — CITED_RESPONSE_ID_MISMATCH: each field checked independently.
# ---------------------------------------------------------------------------

def test_invariant_cited_response_id_mismatch_llm_response_id():
    """llm_response_id mismatch alone must raise CITED_RESPONSE_ID_MISMATCH."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    rep["llm_response_id"] = "tampered-llm-id"

    with pytest.raises(GroundednessValidationInternalError, match="CITED_RESPONSE_ID_MISMATCH"):
        validate_groundedness_report(rep, cited, context)

def test_invariant_cited_response_id_mismatch_context_package_id():
    """context_package_id mismatch alone must raise CITED_RESPONSE_ID_MISMATCH."""
    cited = get_mock_cited_response()
    context = get_mock_context_package()
    rep = validate_groundedness(cited, context)
    rep["context_package_id"] = "tampered-pkg-id"

    with pytest.raises(GroundednessValidationInternalError, match="CITED_RESPONSE_ID_MISMATCH"):
        validate_groundedness_report(rep, cited, context)

