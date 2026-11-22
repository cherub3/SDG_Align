import pytest
import math
from scripts.stage11_context_assembly import (
    validate_retrieval_result,
    estimate_tokens,
    build_context_blocks,
    enforce_budget,
    assemble_context_package,
    validate_context_package,
    assemble_context,
    ContextAssemblyInputError,
    ContextAssemblyInternalError,
    CHARS_PER_TOKEN_ESTIMATE,
    DEFAULT_CONTEXT_BUDGET_TOKENS
)

def get_mock_retrieval_result():
    return {
        "query": "test query",
        "status": "PASS",
        "requested_index_fingerprints": ["fp1"],
        "searched_index_fingerprints": ["fp1"],
        "findings": [],
        "results": [
            {
                "rank": 0,
                "score": 0.9,
                "index_fingerprint": "fp1",
                "embedding_id": "emb1",
                "chunk_id": "c1",
                "doc_id": "d1",
                "text": "Hello world"
            },
            {
                "rank": 1,
                "score": 0.8,
                "index_fingerprint": "fp1",
                "embedding_id": "emb2",
                "chunk_id": "c2",
                "doc_id": "d1",
                "text": "This is a longer text to take up more tokens in the budget enforcement step."
            }
        ]
    }

def test_validate_retrieval_result_success():
    validate_retrieval_result(get_mock_retrieval_result())

def test_validate_retrieval_result_malformed():
    res = get_mock_retrieval_result()
    del res["query"]
    with pytest.raises(ContextAssemblyInputError, match="RETRIEVAL_RESULT_MALFORMED"):
        validate_retrieval_result(res)
        
    res = get_mock_retrieval_result()
    del res["results"][0]["text"]
    with pytest.raises(ContextAssemblyInputError, match="RETRIEVAL_RESULT_MALFORMED"):
        validate_retrieval_result(res)

def test_estimate_tokens():
    text = "12345678"
    assert estimate_tokens(text) == math.ceil(8 / 4.0)
    assert estimate_tokens("1") == 1
    assert estimate_tokens("") == 0

def test_build_context_blocks():
    res = get_mock_retrieval_result()
    blocks = build_context_blocks(res["results"])
    assert len(blocks) == 2
    assert blocks[0]["chunk_id"] == "c1"
    assert "estimated_tokens" in blocks[0]
    assert blocks[0]["estimated_tokens"] == estimate_tokens("Hello world")

def test_enforce_budget():
    blocks = [
        {"chunk_id": "c1", "estimated_tokens": 10},
        {"chunk_id": "c2", "estimated_tokens": 20},
        {"chunk_id": "c3", "estimated_tokens": 5}
    ]
    # Includes c1 (10), excludes c2 (20), excludes c3 (5) due to truncation
    included, excluded = enforce_budget(blocks, 15)
    assert len(included) == 1
    assert included[0]["chunk_id"] == "c1"
    assert len(excluded) == 2
    assert excluded[0]["chunk_id"] == "c2"

def test_assemble_context_package():
    res = get_mock_retrieval_result()
    blocks = build_context_blocks(res["results"])
    included, excluded = enforce_budget(blocks, 1000)
    pkg = assemble_context_package(res, included, excluded, 1000)
    
    assert "context_package_id" in pkg
    assert len(pkg["context_blocks"]) == 2
    assert pkg["context_blocks"][0]["context_block_id"].startswith(pkg["context_package_id"])
    assert pkg["budget_utilization"] <= 1.0

def test_validate_context_package_invariants():
    res = get_mock_retrieval_result()
    blocks = build_context_blocks(res["results"])
    pkg = assemble_context_package(res, blocks, [], 1000)
    validate_context_package(pkg)
    
    # Duplicate block
    pkg_duplicate = pkg.copy()
    pkg_duplicate["context_blocks"] = [pkg["context_blocks"][0], pkg["context_blocks"][0]]
    with pytest.raises(ContextAssemblyInternalError, match="DUPLICATE_CONTEXT_BLOCK"):
        validate_context_package(pkg_duplicate)
        
    # Rank not contiguous
    pkg_rank = pkg.copy()
    b1 = pkg["context_blocks"][0].copy()
    b2 = pkg["context_blocks"][1].copy()
    b1["rank"] = 0
    b2["rank"] = 2
    pkg_rank["context_blocks"] = [b1, b2]
    with pytest.raises(ContextAssemblyInternalError, match="RANK_NOT_CONTIGUOUS"):
        validate_context_package(pkg_rank)
        
    # Token sum mismatch
    pkg_tokens = pkg.copy()
    pkg_tokens["total_estimated_tokens"] = 9999
    with pytest.raises(ContextAssemblyInternalError, match="TOKEN_ESTIMATE_SUM_MISMATCH"):
        validate_context_package(pkg_tokens)
        
    # Budget invariant
    pkg_budget = pkg.copy()
    pkg_budget["context_budget_tokens"] = 1
    with pytest.raises(ContextAssemblyInternalError, match="BUDGET_INVARIANT_VIOLATED"):
        validate_context_package(pkg_budget)
        
    # Excluded count mismatch
    pkg_excluded = pkg.copy()
    pkg_excluded["excluded_block_count"] = 999
    # Ensure this mismatch fires EXCLUDED_COUNT_MISMATCH
    with pytest.raises(ContextAssemblyInternalError, match="EXCLUDED_COUNT_MISMATCH"):
        validate_context_package(pkg_excluded)

def test_assemble_context():
    res = get_mock_retrieval_result()
    pkg = assemble_context(res, context_budget_tokens=10)
    
    # Text lengths: "Hello world" -> 11 chars -> 3 tokens. 
    # "This is a longer text..." -> 76 chars -> 19 tokens.
    # Total budget = 10 tokens.
    # Included: c1 (3 tokens).
    # Excluded: c2 (19 tokens).
    
    assert pkg["included_block_count"] == 1
    assert pkg["excluded_block_count"] == 1
    assert pkg["is_empty"] is False
    assert pkg["total_estimated_tokens"] == 3
    assert pkg["budget_utilization"] == 3 / 10.0
    assert any(f["code"] == "CONTEXT_BUDGET_EXCEEDED" for f in pkg["findings"])
    
def test_assemble_context_status_fail():
    res = get_mock_retrieval_result()
    res["status"] = "FAIL"
    pkg = assemble_context(res)
    
    assert pkg["status"] == "FAIL"
    assert pkg["is_empty"] is True
    assert pkg["included_block_count"] == 0
    assert any(f["code"] == "RETRIEVAL_STATUS_FAIL" and f["severity"] == "FAIL" for f in pkg["findings"])
    assert not any(f["code"] == "CONTEXT_EMPTY" for f in pkg["findings"])
    
def test_assemble_context_empty_results():
    res = get_mock_retrieval_result()
    res["results"] = []
    pkg = assemble_context(res)
    
    assert pkg["status"] == "PASS"
    assert len(pkg["context_blocks"]) == 0
    assert pkg["is_empty"] is True
    assert any(f["code"] == "CONTEXT_EMPTY" and f["severity"] == "WARNING" for f in pkg["findings"])
    assert not any(f["code"] == "RETRIEVAL_STATUS_FAIL" for f in pkg["findings"])
    
def test_determinism():
    res1 = get_mock_retrieval_result()
    res2 = get_mock_retrieval_result()
    
    pkg1 = assemble_context(res1, 20)
    pkg2 = assemble_context(res2, 20)
    
    # assembled_at will differ, pop it out
    pkg1.pop("assembled_at")
    pkg2.pop("assembled_at")
    
    assert pkg1 == pkg2
    
    # Determinism for FAIL path
    res_fail1 = get_mock_retrieval_result()
    res_fail1["status"] = "FAIL"
    res_fail2 = get_mock_retrieval_result()
    res_fail2["status"] = "FAIL"
    
    pkg_fail1 = assemble_context(res_fail1, 20)
    pkg_fail2 = assemble_context(res_fail2, 20)
    
    pkg_fail1.pop("assembled_at")
    pkg_fail2.pop("assembled_at")
    
    assert pkg_fail1 == pkg_fail2
    assert pkg_fail1["context_package_id"] == pkg_fail2["context_package_id"]
