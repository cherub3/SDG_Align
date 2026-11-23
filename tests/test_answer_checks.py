"""Script checks for answer-level abstention (tools/answer_checks.py): proxies, summaries, the pre-stated keep rule."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import answer_checks as ac  # noqa: E402

ANS = {"qid": "Q1", "type": "numbers_tables", "question": "How many hectares are conceded?",
       "evidence": [{"answer_quote": "Three logging companies (STBK, SIM) hold concessions totaling 453,511 ha"}]}
UN = {"qid": "Q2", "type": "unanswerable", "kind": "near_miss", "question": "What salary?", "absence_terms": ["salary", "XAF per month"]}


def test_numbers_are_normalised_so_commas_and_trailing_zeros_match():
    assert ac.tokens("24,000.00 people and 12,000 men, 10% share") >= {"24000", "12000", "10%"}
    assert "453511" in ac.tokens("totaling 453,511 ha")


def test_support_recall_counts_only_facts_not_already_in_the_question():
    full = ac.support_recall("STBK and SIM hold 453,511 ha in concessions of logging by three companies.", ANS["question"],
                             [ANS["evidence"][0]["answer_quote"]])
    part = ac.support_recall("Three companies.", ANS["question"], [ANS["evidence"][0]["answer_quote"]])
    assert full > 0.8 > 0.5 > part
    assert ac.support_recall("x", "q", []) is None


def test_implicit_refusal_detection():
    assert ac.implicit_refusal("The excerpts do not state a monthly salary.")
    assert ac.implicit_refusal("No information is given about this.")
    assert ac.implicit_refusal("I cannot find the figure in the context.")
    assert not ac.implicit_refusal("Ecoguards earn a monthly salary of 90 000 francs.")


def test_check_item_answerable_paths():
    ok = ac.check_item(ANS, "STBK and SIM hold 453,511 ha in concessions.")
    assert ok["decision"] == "ANSWERED" and ok["correct_proxy"] is True
    bad = ac.check_item(ANS, "Three companies.")
    assert bad["correct_proxy"] is False
    ref = ac.check_item(ANS, "NOT_IN_CONTEXT")
    assert ref["decision"] == "NOT_IN_CONTEXT" and ref["correct_proxy"] is False
    imp = ac.check_item(ANS, "The context does not mention the area of 453,511 ha.")
    assert imp["implicit_refusal"] is True and imp["correct_proxy"] is False


def test_check_item_unanswerable_paths():
    assert ac.check_item(UN, "The monthly salary is 90,000 francs.")["term_in_answer"] is True
    assert ac.check_item(UN, "NOT_IN_CONTEXT")["term_in_answer"] is False
    assert ac.check_item(UN, "The excerpts do not state a salary.")["term_in_answer"] is False   # a refusal that names the term is not an invention
    assert ac.check_item(UN, "Around 90,000 francs.")["term_in_answer"] is False                 # known false negative: no listed term


def _checks(refused_un, n_un, refused_ans, n_ans):
    rows = [{"qid": f"u{i}", "type": "unanswerable", "kind": "near_miss" if i % 2 else "off_corpus",
             "decision": "NOT_IN_CONTEXT" if i < refused_un else "ANSWERED", "implicit_refusal": False, "term_in_answer": False} for i in range(n_un)]
    rows += [{"qid": f"a{i}", "type": "single_fact", "kind": None, "decision": "NOT_IN_CONTEXT" if i < refused_ans else "ANSWERED",
              "implicit_refusal": False, "correct_proxy": i >= refused_ans} for i in range(n_ans)]
    return rows


def test_summarize_counts_and_cis():
    s = ac.summarize(_checks(6, 8, 2, 44))
    assert (s["refusal_rate_unanswerable"]["k"], s["refusal_rate_unanswerable"]["n"]) == (6, 8)
    assert (s["false_refusal_rate_answerable"]["k"], s["false_refusal_rate_answerable"]["n"]) == (2, 44)
    lo, hi = s["refusal_rate_unanswerable"]["ci95"]
    assert lo <= 0.75 <= hi
    assert s["answered_correct_proxy_rate_answerable"]["k"] == 42
    assert ac.summarize(_checks(6, 8, 2, 44)) == s          # deterministic (seeded bootstrap)


@pytest.mark.parametrize("ru,fr,keep", [(5, 4, True), (4, 0, False), (8, 5, False), (8, 4, True), (0, 0, False)])
def test_keep_rule_is_strictly_more_than_half_and_at_most_ten_percent_false_refusal(ru, fr, keep):
    r = ac.keep_rule(ac.summarize(_checks(ru, 8, fr, 44)))
    assert r["KEEP"] is keep


def test_fpfn_runs_on_the_shipped_hand_labelled_cases():
    gold = {r["qid"]: r for r in (json.loads(x) for x in open(ROOT / "eval" / "gold_set.jsonl", encoding="utf-8") if x.strip())}
    res = ac.fpfn(ROOT / "eval" / "step4_checker_cases.json", gold)
    c = res["confusion"]
    assert c["refused"]["fp"] == c["refused"]["fn"] == 0 and c["implicit_refusal"]["fp"] == c["implicit_refusal"]["fn"] == 0
    assert c["correct_proxy"]["fp"] == 0
    assert sum(r["n"] for r in c.values()) == 10 + 10 + 6 + 4


def test_compare_real_counts_checker_against_hand_labels():
    rows = [{"qid": "Q1", "response_text": "STBK and SIM hold 453,511 ha in concessions."}, {"qid": "Q1b", "response_text": "NOT_IN_CONTEXT"},
            {"qid": "Q1c", "response_text": "Three."}]
    items = {"Q1": ANS, "Q1b": {**ANS, "qid": "Q1b"}, "Q1c": {**ANS, "qid": "Q1c"}}
    out = ac.compare_real(rows, {"Q1": True, "Q1b": False, "Q1c": True}, items)
    assert out["confusion"]["correct_proxy"] == {"tp": 1, "fp": 0, "fn": 1, "tn": 1}      # "Three." is a correct-by-label reply the proxy misses
    assert out["confusion"]["refused"] == {"tp": 1, "fp": 0, "fn": 0, "tn": 2}
