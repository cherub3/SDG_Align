import pytest
import sys
import copy
from pathlib import Path

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage14_citation_extraction import (
    segment_response_text,
    compute_ngram_overlap,
    extract_citations,
    validate_llm_response,
    validate_prompt_package,
    validate_context_package,
    verify_id_chain,
    CitationExtractionInputError,
    CitationExtractionInternalError,
    DEFAULT_CITATION_MATCH_THRESHOLD,
    LOW_CITATION_COVERAGE_THRESHOLD,
    NGRAM_SIZE,
    assemble_cited_response,
    validate_cited_response,
    match_span_to_blocks,
)

def test_segment_response_text_empty():
    assert segment_response_text("") == []

def test_segment_response_text_basic():
    text = "Hello world. This is a test! Wait, what? Yes."
    spans = segment_response_text(text)
    
    assert len(spans) == 4
    assert spans[0]["text"] == "Hello world."
    assert spans[1]["text"] == " This is a test!"
    assert spans[2]["text"] == " Wait, what?"
    assert spans[3]["text"] == " Yes."
    
    assert sum(len(s["text"]) for s in spans) == len(text)

def test_segment_response_text_tricky_boundaries():
    text = "Dr. Smith said pi is 3.14! Right?! Done.\n\nEnd."
    spans = segment_response_text(text)
    
    assert len(spans) == 5
    assert spans[0]["text"] == "Dr."
    assert spans[1]["text"] == " Smith said pi is 3.14!"
    assert spans[2]["text"] == " Right?!"
    assert spans[3]["text"] == " Done.\n\n"
    assert spans[4]["text"] == "End."
    
def test_segment_response_text_quotes():
    text = 'He said "Hello!" Then left.'
    spans = segment_response_text(text)
    assert len(spans) == 2
    assert spans[0]["text"] == 'He said "Hello!"'
    assert spans[1]["text"] == " Then left."

def test_compute_ngram_overlap_basic():
    span = "This is exactly a test."
    block = "this is exactly a test. with more words."
    
    score = compute_ngram_overlap(span, block)
    assert score == 1.0 # full containment

def test_compute_ngram_overlap_symmetry():
    # Containment is NOT symmetric
    short = "hello"
    long = "hello world"
    # long contains short
    score1 = compute_ngram_overlap(short, long)
    assert score1 == 1.0
    
    score2 = compute_ngram_overlap(long, short)
    assert score2 < 1.0

def test_compute_ngram_overlap_short():
    short = "hi"
    assert len(short) < NGRAM_SIZE
    assert compute_ngram_overlap(short, "hi there") == 0.0

def test_compute_ngram_overlap_folding():
    s1 = "  HELLO   \nWorld  "
    s2 = "hello world"
    assert compute_ngram_overlap(s1, s2) == 1.0
    
def get_mock_context_package():
    return {
        "context_package_id": "pkg-1",
        "context_blocks": [
            {
                "context_block_id": "blk-1",
                "chunk_id": "chunk-1",
                "doc_id": "doc-1",
                "text": "apples are red and delicious."
            },
            {
                "context_block_id": "blk-2",
                "chunk_id": "chunk-2",
                "doc_id": "doc-2",
                "text": "bananas are yellow."
            },
            {
                "context_block_id": "blk-3",
                "chunk_id": "chunk-3",
                "doc_id": "doc-1",
                "text": "apples are red and delicious. truly."
            }
        ]
    }

def get_mock_prompt_package():
    return {
        "prompt_package_id": "prompt-1",
        "context_package_id": "pkg-1"
    }

def get_mock_llm_response(text=""):
    return {
        "llm_response_id": "resp-1",
        "prompt_package_id": "prompt-1",
        "status": "PASS",
        "response_text": text,
        "findings": []
    }

def test_extract_citations_basic():
    llm = get_mock_llm_response("Apples are red and delicious. Also, bananas are yellow.")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()
    
    res = extract_citations(llm, prompt, context)
    
    assert res["status"] == "PASS"
    assert res["span_count"] == 2
    assert res["cited_span_count"] == 2
    assert res["uncited_span_count"] == 0
    assert res["citation_coverage"] == 1.0
    
    # Span 1 citations
    span1_cits = res["spans"][0]["citations"]
    assert len(span1_cits) == 2 # matches both blk-1 and blk-3 since both contain the text
    # Ordering: score descending, chunk_id ascending
    # Both probably have score 1.0. chunk-1 < chunk-3.
    assert span1_cits[0]["chunk_id"] == "chunk-1"
    assert span1_cits[1]["chunk_id"] == "chunk-3"
    
    # Span 2 citations
    span2_cits = res["spans"][1]["citations"]
    assert len(span2_cits) == 1
    assert span2_cits[0]["chunk_id"] == "chunk-2"

def test_extract_citations_zero_matches():
    llm = get_mock_llm_response("Oranges are orange.")
    res = extract_citations(llm, get_mock_prompt_package(), get_mock_context_package())
    
    assert res["cited_span_count"] == 0
    assert res["uncited_span_count"] == 1
    assert res["citation_coverage"] == 0.0
    assert any(f["code"] == "ZERO_CITATIONS" for f in res["findings"])

def test_extract_citations_status_passthrough():
    llm = get_mock_llm_response("")
    llm["status"] = "FAIL"
    
    res = extract_citations(llm, get_mock_prompt_package(), get_mock_context_package())
    
    assert res["status"] == "FAIL"
    assert res["span_count"] == 0
    assert res["citation_coverage"] == 1.0
    assert any(f["code"] == "RESPONSE_EMPTY" for f in res["findings"])

def test_input_validation():
    # Bad LLM
    bad_llm = get_mock_llm_response()
    del bad_llm["status"]
    with pytest.raises(CitationExtractionInputError, match="LLM_RESPONSE_MALFORMED"):
        extract_citations(bad_llm, get_mock_prompt_package(), get_mock_context_package())
        
    # Bad Prompt
    bad_prompt = get_mock_prompt_package()
    del bad_prompt["context_package_id"]
    with pytest.raises(CitationExtractionInputError, match="PROMPT_PACKAGE_MALFORMED"):
        extract_citations(get_mock_llm_response(), bad_prompt, get_mock_context_package())
        
    # Bad Context
    bad_context = get_mock_context_package()
    del bad_context["context_blocks"]
    with pytest.raises(CitationExtractionInputError, match="CONTEXT_PACKAGE_MALFORMED"):
        extract_citations(get_mock_llm_response(), get_mock_prompt_package(), bad_context)
        
    # Mismatch IDs
    bad_llm = get_mock_llm_response()
    bad_llm["prompt_package_id"] = "wrong"
    with pytest.raises(CitationExtractionInputError, match="ID_CHAIN_MISMATCH"):
        extract_citations(bad_llm, get_mock_prompt_package(), get_mock_context_package())

def test_invariants_span_text_mismatch():
    llm = get_mock_llm_response("Text")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()
    
    spans = segment_response_text(llm["response_text"])
    spans[0]["text"] = "tampered"
    
    res = assemble_cited_response(llm, prompt, context, spans, 0.6)
    with pytest.raises(CitationExtractionInternalError, match="SPAN_TEXT_MISMATCH"):
        validate_cited_response(res, context, llm)
        
def test_invariants_span_offset_discontinuous():
    llm = get_mock_llm_response("Test")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()
    
    spans = segment_response_text(llm["response_text"])
    spans[0]["start_offset"] = 1 # tampered
    
    res = assemble_cited_response(llm, prompt, context, spans, 0.6)
    with pytest.raises(CitationExtractionInternalError, match="SPAN_OFFSET_DISCONTINUOUS"):
        validate_cited_response(res, context, llm)

def test_invariants_unknown_block():
    llm = get_mock_llm_response("Test")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()
    
    spans = segment_response_text(llm["response_text"])
    spans[0]["citations"].append({
        "context_block_id": "unknown",
        "chunk_id": "chunk",
        "doc_id": "doc",
        "match_score": 1.0
    })
    
    res = assemble_cited_response(llm, prompt, context, spans, 0.6)
    with pytest.raises(CitationExtractionInternalError, match="CITATION_REFERENCES_UNKNOWN_BLOCK"):
        validate_cited_response(res, context, llm)

def test_invariants_duplicate_citation():
    llm = get_mock_llm_response("Test")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()
    
    spans = segment_response_text(llm["response_text"])
    c = {
        "context_block_id": "blk-1",
        "chunk_id": "chunk",
        "doc_id": "doc",
        "match_score": 1.0
    }
    spans[0]["citations"].extend([c, c]) # duplicate
    
    res = assemble_cited_response(llm, prompt, context, spans, 0.6)
    with pytest.raises(CitationExtractionInternalError, match="DUPLICATE_CITATION_IN_SPAN"):
        validate_cited_response(res, context, llm)

def test_invariants_coverage_mismatch():
    llm = get_mock_llm_response("Test")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()
    
    spans = segment_response_text(llm["response_text"])
    res = assemble_cited_response(llm, prompt, context, spans, 0.6)
    res["citation_coverage"] = 9.9 # tampered
    
    with pytest.raises(CitationExtractionInternalError, match="COVERAGE_COMPUTATION_MISMATCH"):
        validate_cited_response(res, context, llm)

def test_determinism():
    llm = get_mock_llm_response("Apples are red and delicious. Also, bananas are yellow.")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()

    res1 = extract_citations(copy.deepcopy(llm), copy.deepcopy(prompt), copy.deepcopy(context))
    res2 = extract_citations(copy.deepcopy(llm), copy.deepcopy(prompt), copy.deepcopy(context))

    # extracted_at will differ, so blank them out before comparing
    res1["extracted_at"] = ""
    res2["extracted_at"] = ""

    assert res1 == res2

def test_invariants_llm_response_id_mismatch():
    llm = get_mock_llm_response("Test")
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()

    spans = segment_response_text(llm["response_text"])
    res = assemble_cited_response(llm, prompt, context, spans, 0.6)
    # Tamper the llm_response_id on the assembled response to trigger the invariant
    res["llm_response_id"] = "tampered-id"

    with pytest.raises(CitationExtractionInternalError, match="LLM_RESPONSE_ID_MISMATCH"):
        validate_cited_response(res, context, llm)

def test_extract_citations_low_coverage():
    # context has 3 blocks; we need a response where only 1 of N spans is cited
    # "Oranges are orange." has no overlap with any block → uncited
    # "Apples are red and delicious." matches blk-1/blk-3 → cited
    # So 1 cited out of 2 spans = 0.5, but we need strictly < LOW_CITATION_COVERAGE_THRESHOLD (0.5)
    # Use 3 spans where only 1 matches: construct a response with 3 spans, 1 cited
    llm = get_mock_llm_response(
        "Apples are red and delicious. Oranges are orange. Grapes are purple."
    )
    prompt = get_mock_prompt_package()
    context = get_mock_context_package()

    res = extract_citations(llm, prompt, context)

    # Exactly 1 of 3 spans should match (the apple one), coverage = 0.333... < 0.5
    assert res["span_count"] == 3
    assert res["cited_span_count"] == 1
    assert res["citation_coverage"] < LOW_CITATION_COVERAGE_THRESHOLD
    assert res["citation_coverage"] > 0.0
    assert any(f["code"] == "LOW_CITATION_COVERAGE" for f in res["findings"])
    low_cov_findings = [f for f in res["findings"] if f["code"] == "LOW_CITATION_COVERAGE"]
    assert len(low_cov_findings) == 1
    assert low_cov_findings[0]["severity"] == "WARNING"
    # Must not also fire ZERO_CITATIONS
    assert not any(f["code"] == "ZERO_CITATIONS" for f in res["findings"])

def test_extract_citations_status_skipped():
    llm = get_mock_llm_response("")
    llm["status"] = "SKIPPED"

    res = extract_citations(llm, get_mock_prompt_package(), get_mock_context_package())

    assert res["status"] == "SKIPPED"
    assert res["span_count"] == 0
    assert res["spans"] == []
    assert res["citation_coverage"] == 1.0
    assert any(f["code"] == "RESPONSE_EMPTY" for f in res["findings"])

def test_match_span_to_blocks_unit():
    # Verify ordering: descending match_score, ascending chunk_id on ties.
    # blk-1 text "apples are red and delicious." and blk-3 text "apples are red and delicious. truly."
    # A span of "apples are red and delicious." should score 1.0 against blk-1 and < 1.0 against blk-3
    # because blk-3 is longer (containment ratio = span ngrams / span ngrams = 1.0 for blk-1,
    # but blk-3 also contains all span ngrams so also 1.0 → tie broken by chunk_id ascending)
    context = get_mock_context_package()
    blocks = context["context_blocks"]

    span = {"text": "apples are red and delicious.", "citations": []}

    citations = match_span_to_blocks(span, blocks, DEFAULT_CITATION_MATCH_THRESHOLD)

    # Both blk-1 and blk-3 contain the full span text, so both should cite at score 1.0
    cited_ids = [c["context_block_id"] for c in citations]
    assert "blk-1" in cited_ids
    assert "blk-3" in cited_ids
    # blk-2 text is "bananas are yellow." — no n-gram overlap with apple text
    assert "blk-2" not in cited_ids

    # Ordering: both at 1.0, so tie-break by ascending chunk_id: chunk-1 before chunk-3
    assert citations[0]["chunk_id"] == "chunk-1"
    assert citations[1]["chunk_id"] == "chunk-3"

    # All match_scores must be >= threshold
    for c in citations:
        assert c["match_score"] >= DEFAULT_CITATION_MATCH_THRESHOLD

    # Threshold boundary: a span that exactly meets the threshold is included (closed comparison).
    # Test with a threshold of exactly 1.0 — only perfect-overlap spans qualify.
    citations_strict = match_span_to_blocks(span, blocks, 1.0)
    assert len(citations_strict) >= 1  # blk-1 is an exact match at 1.0
    for c in citations_strict:
        assert c["match_score"] >= 1.0

    # A span with no overlap against any block returns empty list.
    no_match_span = {"text": "completely unrelated zebra sentence.", "citations": []}
    assert match_span_to_blocks(no_match_span, blocks, DEFAULT_CITATION_MATCH_THRESHOLD) == []
