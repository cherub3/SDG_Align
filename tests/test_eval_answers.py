"""Safety behaviour of the answer-evaluation runner (tools/eval_answers.py): stop on failure, resume, hard call limit, hashes."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import eval_answers as ea  # noqa: E402


def _items(n):
    return [{"qid": f"Q{i}", "type": "single_fact", "question": "q?", "evidence": [{"answer_quote": "alpha beta gamma 1,000"}]} for i in range(n)]


def _row(it, text="alpha beta gamma 1,000"):
    return {"qid": it["qid"], "type": it["type"], "kind": None, "response_text": text, "latency_ms": 5, "prompt_tokens": 10,
            "completion_tokens": 2, "total_tokens": 12, "groundedness_score": 1.0, "gold_in_context": True}


def test_run_items_writes_one_row_per_item_and_flushes_each(tmp_path):
    out, seen = tmp_path / "r.jsonl", []
    info = ea.run_items(_items(3), lambda it: seen.append(it["qid"]) or _row(it), str(out), 10)
    assert info == {"calls_this_run": 3, "stopped": None}
    assert [json.loads(x)["qid"] for x in out.read_text().splitlines()] == ["Q0", "Q1", "Q2"]


def test_max_calls_is_a_hard_limit(tmp_path):
    out = tmp_path / "r.jsonl"
    calls = []
    info = ea.run_items(_items(5), lambda it: calls.append(it["qid"]) or _row(it), str(out), 2)
    assert len(calls) == 2 and info["stopped"].startswith("MAX_CALLS_REACHED")
    assert len(ea.read_rows(str(out))) == 2


def test_a_stop_keeps_finished_rows_and_makes_no_further_call(tmp_path):
    out = tmp_path / "r.jsonl"
    calls = []

    def ask(it):
        calls.append(it["qid"])
        if it["qid"] == "Q2":
            raise ea.StopRun("LLM_ERROR at Q2: LLMQuotaExhaustedError (429 / quota)")
        return _row(it)
    info = ea.run_items(_items(5), ask, str(out), 10)
    assert calls == ["Q0", "Q1", "Q2"] and "429" in info["stopped"]
    assert [r["qid"] for r in ea.read_rows(str(out))] == ["Q0", "Q1"]          # Q2 is NOT recorded as an answer


def test_resume_skips_finished_items_and_does_not_recall_the_model(tmp_path):
    out = tmp_path / "r.jsonl"
    ea.run_items(_items(2), _row, str(out), 10)
    calls = []
    info = ea.run_items(_items(4), lambda it: calls.append(it["qid"]) or _row(it), str(out), 10)
    assert calls == ["Q2", "Q3"] and info["calls_this_run"] == 2 and info["stopped"] is None


def test_summarize_rows_reports_refusals_context_and_tokens():
    items = _items(2) + [{"qid": "U1", "type": "unanswerable", "kind": "near_miss", "question": "salary?", "absence_terms": ["salary"]}]
    by = {i["qid"]: i for i in items}
    rows = [_row(items[0]), _row(items[1], "NOT_IN_CONTEXT"), {**_row(items[2], "NOT_IN_CONTEXT"), "gold_in_context": None}]
    s, checks = ea.summarize_rows(rows, by)
    assert s["false_refusal_rate_answerable"]["k"] == 1 and s["refusal_rate_unanswerable"]["k"] == 1
    assert s["false_refusals_with_gold_in_context"] == 1 and s["false_refusals_gold_not_in_context"] == 0
    assert s["tokens"]["total_tokens"] == 36 and len(checks) == 3


def test_prompt_hash_is_stable_and_differs_between_templates():
    a, b = ea.prompt_sha256("2.0.0"), ea.prompt_sha256("1.0.0")
    assert a == ea.prompt_sha256("2.0.0") and a != b and len(a) == 64


def test_load_items_splits_match_the_frozen_split():
    dev, test = ea.load_items("dev"), ea.load_items("test")
    assert (len(dev), len(test)) == (14, 52) and not {i["qid"] for i in dev} & {i["qid"] for i in test}


def test_test_split_refuses_without_the_frozen_prompt_hash(monkeypatch):
    monkeypatch.setattr(ea.fg, "check_frozen", lambda: [])
    monkeypatch.setattr(sys, "argv", ["x", "--split", "test", "--template", "2.0.0", "--label", "t", "--max-calls", "1"])
    with pytest.raises(SystemExit, match="expect-prompt-sha256"):
        ea.main()


def test_a_wrong_prompt_hash_refuses(monkeypatch):
    monkeypatch.setattr(ea.fg, "check_frozen", lambda: [])
    monkeypatch.setattr(sys, "argv", ["x", "--split", "dev", "--template", "2.0.0", "--label", "t", "--max-calls", "1", "--expect-prompt-sha256", "0" * 64])
    with pytest.raises(SystemExit, match="hash"):
        ea.main()
