"""The post hoc Phase 4 McNemar numbers are recomputed from the row files; the stored JSON must match. No network, no model call."""
import json
import os
import sys

import pytest

pytest.importorskip("google.adk")
pytest.importorskip("scipy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import gold_common as gc  # noqa: E402
import phase4_posthoc as ph  # noqa: E402

needs_corpus = pytest.mark.skipif(not os.path.isdir(gc.CHUNKS), reason="needs the real corpus")


def test_mcnemar_exact_on_a_hand_checked_table():
    a = [True] * 6 + [False] * 4
    b = [False] * 5 + [True, True] + [False] * 3        # 1 both, 5 only-A, 1 only-B, 3 neither
    r = ph.mcnemar(a, b)
    assert r["table"] == {"both": 1, "only_A": 5, "only_B": 1, "neither": 3}
    assert r["discordant"] == 6 and r["mcnemar_exact_p"] == 0.2188     # exact two-sided: 2 x P(X <= 1 | n=6, 0.5) = 0.21875


def test_no_discordant_pairs_gives_p_one():
    assert ph.mcnemar([True, False], [True, False])["mcnemar_exact_p"] == 1.0


@needs_corpus
def test_stored_result_matches_a_fresh_recomputation_from_the_row_files():
    res, flags = ph.compute()
    stored = json.load(open(ph.OUT, encoding="utf-8"))
    for k in ("false_refusal_answerable_44", "automatic_wrong_all_52", "automatic_wrong_answerable_44"):
        assert res[k] == stored[k]
    assert len(flags) == 52 and sum(x["answerable"] for x in flags) == 44


@needs_corpus
def test_counts_agree_with_the_pre_registered_summary():
    res, _ = ph.compute()
    summ = json.load(open(os.path.join(ph.RESULTS, "test_agents_v1_summary.json"), encoding="utf-8"))
    fr, w = res["false_refusal_answerable_44"], res["automatic_wrong_all_52"]
    assert (fr["events_A"], fr["events_B"]) == (summ["A"]["false_refusals_answerable"], summ["B"]["false_refusals_answerable"])
    assert (w["events_A"], w["events_B"]) == (summ["A"]["wrong_answers_automatic"], summ["B"]["wrong_answers_automatic"])
