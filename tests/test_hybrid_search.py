"""Hybrid (BM25 + dense, reciprocal rank fusion) retrieval, step 3b. Pure functions, no corpus needed."""
import math

import pytest

from scripts import hybrid_search as hs


def test_tokenizer_lowercases_and_keeps_numbers_whole():
    assert hs.tokenize("Budget: USD 1,250,000 (3.5% of GEF-8)") == ["budget", "usd", "1,250,000", "3.5", "of", "gef", "8"]
    assert hs.tokenize("2026-2030") == ["2026", "2030"]
    assert hs.tokenize("") == [] and hs.tokenize(None) == []


def test_tokenizer_keeps_a_trailing_sentence_period_out_of_the_number():
    assert hs.tokenize("It cost 300. Then") == ["it", "cost", "300", "then"]


def _index():
    return hs.BM25Index([("a", "jaguar corridor in Ecuador"), ("b", "gold mining mercury Mozambique"),
                         ("c", "jaguar jaguar jaguar habitat"), ("d", "budget 1,250,000 USD co-financing")])


def test_bm25_ranks_the_matching_chunk_first_and_ignores_unmatched():
    s = _index().scores("mercury in gold mining")
    assert hs.rank_by_score(s)[0] == "b"
    assert "d" not in s


def test_bm25_numbers_are_searchable():
    assert hs.rank_by_score(_index().scores("1,250,000"))[0] == "d"


def test_bm25_term_frequency_saturates():
    s = _index().scores("jaguar")
    assert s["c"] > s["a"] > 0
    assert s["c"] < 3 * s["a"]          # three mentions are worth far less than 3x one mention


def test_bm25_idf_is_never_negative_even_for_a_term_in_every_chunk():
    idx = hs.BM25Index([("a", "the cat"), ("b", "the dog")])
    assert idx.idf["the"] > 0


def test_bm25_empty_query_and_empty_index():
    assert _index().scores("zzz unknown") == {}
    assert hs.BM25Index([]).scores("x") == {}


def test_rank_by_score_breaks_ties_on_chunk_id():
    assert hs.rank_by_score({"b": 1.0, "a": 1.0, "c": 2.0}) == ["c", "a", "b"]


def test_rrf_formula_and_weights():
    f = hs.rrf_fuse([(["x", "y"], 1.0), (["y", "z"], 2.0)], rrf_k=10, depth=50)
    assert f["x"] == pytest.approx(1 / 11)
    assert f["y"] == pytest.approx(1 / 12 + 2 / 11)
    assert f["z"] == pytest.approx(2 / 12)


def test_rrf_depth_cuts_each_list():
    f = hs.rrf_fuse([(["x", "y", "z"], 1.0)], rrf_k=60, depth=2)
    assert set(f) == {"x", "y"}


def _cand(cid, score):
    return {"chunk_id": cid, "doc_id": "d", "score": score, "embedding_id": "e" + cid, "index_fingerprint": "f"}


def test_fusion_lifts_a_lexical_hit_the_dense_ranking_buried():
    idx = hs.BM25Index([("a", "alpha"), ("b", "beta"), ("c", "unique rare token")])
    dense = [_cand("a", 0.9), _cand("b", 0.8), _cand("c", 0.1)]
    out = hs.fuse_candidates(dense, idx, "unique rare token", {"rrf_k": 1, "w_bm25": 2.0, "depth": 10})
    best = max(out, key=lambda c: c["score"])
    assert best["chunk_id"] == "c"
    assert best["dense_score"] == 0.1 and best["bm25_score"] > 0     # the cosine survives for abstention


def test_fusion_is_dense_ordered_when_bm25_finds_nothing():
    idx = hs.BM25Index([("a", "alpha"), ("b", "beta")])
    out = hs.fuse_candidates([_cand("a", 0.9), _cand("b", 0.8)], idx, "nothing matches")
    assert [c["chunk_id"] for c in sorted(out, key=lambda c: -c["score"])] == ["a", "b"]


def test_fusion_never_returns_a_chunk_that_has_no_dense_candidate():
    idx = hs.BM25Index([("a", "alpha"), ("ghost", "alpha alpha alpha")])
    out = hs.fuse_candidates([_cand("a", 0.5)], idx, "alpha")
    assert [c["chunk_id"] for c in out] == ["a"]


def test_fusion_does_not_mutate_its_input_and_is_deterministic():
    idx = hs.BM25Index([("a", "alpha"), ("b", "alpha")])
    dense = [_cand("a", 0.5), _cand("b", 0.5)]
    first = hs.fuse_candidates(dense, idx, "alpha")
    assert dense[0]["score"] == 0.5 and "dense_score" not in dense[0]
    assert first == hs.fuse_candidates(dense, idx, "alpha")


def test_build_bm25_is_cached_on_content_and_rebuilt_on_change():
    chunks = [{"chunk_id": "a", "text": "alpha"}, {"chunk_id": "b", "text": "beta"}]
    t = lambda c: c["text"]  # noqa: E731
    assert hs.build_bm25(chunks, t) is hs.build_bm25(list(reversed(chunks)), t)
    changed = [{"chunk_id": "a", "text": "alpha"}, {"chunk_id": "b", "text": "gamma"}]
    assert hs.build_bm25(changed, t).scores("gamma")


def test_default_params_are_the_documented_ones():
    assert hs.DEFAULT_PARAMS == {"rrf_k": 60, "w_bm25": 1.0, "w_dense": 1.0, "depth": 50}
    assert math.isclose(hs.K1, 1.5) and math.isclose(hs.B, 0.75)


def _naive_bm25(docs, query, k1=1.5, b=0.75):
    """Textbook BM25 straight from the definition, as an independent check of the vectorised implementation."""
    toks = {cid: hs.tokenize(t) for cid, t in docs}
    n = len(docs)
    avg = sum(len(t) for t in toks.values()) / n
    out = {}
    for cid, t in toks.items():
        s = 0.0
        for q in hs.tokenize(query):
            df = sum(q in x for x in toks.values())
            if df == 0:
                continue
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            f = t.count(q)
            s += idf * f * (k1 + 1.0) / (f + k1 * (1.0 - b + b * len(t) / avg))
        if s > 0:
            out[cid] = s
    return out


def test_vectorised_bm25_matches_the_textbook_formula():
    docs = [("a", "jaguar corridor in Ecuador 2026"), ("b", "gold mining mercury Mozambique gold"),
            ("c", "jaguar jaguar jaguar habitat 1,250,000"), ("d", "budget 1,250,000 USD co-financing in Ecuador")]
    idx = hs.BM25Index(docs)
    for q in ("jaguar in ecuador", "gold gold mercury", "1,250,000 budget", "ecuador"):
        got, want = idx.scores(q), _naive_bm25(docs, q)
        assert got.keys() == want.keys()
        for k in want:
            assert got[k] == pytest.approx(want[k], rel=1e-12)


def test_fuse_candidates_uses_the_given_k_and_bm25_weight_exactly():
    idx = hs.BM25Index([("a", "alpha"), ("b", "beta"), ("c", "unique rare token")])
    dense = [_cand("a", 0.9), _cand("b", 0.8), _cand("c", 0.1)]
    out = {c["chunk_id"]: c["score"] for c in hs.fuse_candidates(dense, idx, "unique rare token", {"rrf_k": 10, "w_bm25": 2.0, "depth": 50})}
    assert out["a"] == pytest.approx(1 / 11) and out["b"] == pytest.approx(1 / 12)
    assert out["c"] == pytest.approx(1 / 13 + 2 / 11)           # dense rank 3, BM25 rank 1 weighted 2
