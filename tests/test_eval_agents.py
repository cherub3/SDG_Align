"""Guards of tools/eval_agents.py: the daily budget check, the TEST preconditions and the pre-registered keep rule. No network."""
import json
import os
import sys

import pytest

pytest.importorskip("google.adk")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import eval_agents as ev  # noqa: E402


def test_budget_refuses_when_used_today_plus_planned_maximum_exceeds_400():
    assert ev.check_budget(309, 3, 6, 18) == (18, True)
    assert ev.check_budget(309, 14, 6, 80) == (80, True)
    assert ev.check_budget(309, 52, 6, 312) == (312, False)         # 621 > 400: TEST cannot start on a day that already used 309 calls
    assert ev.check_budget(0, 52, 6, 312) == (312, True)
    assert ev.check_budget(80, 52, 6, 400) == (312, True)            # planned is items x cap, not the --max-calls ceiling


def test_ledger_counts_only_the_given_pacific_day(tmp_path):
    p = tmp_path / "l.json"
    p.write_text(json.dumps({"entries": [{"day_pacific": "2026-11-23", "calls": 300}, {"day_pacific": "2026-11-23", "calls": 9},
                                         {"day_pacific": "2026-11-24", "calls": 5}]}))
    assert ev.ledger_used_today(str(p), "2026-11-23") == 309 and ev.ledger_used_today(str(p), "2026-11-24") == 5


def _m(false_ref, wrong, mean_calls):
    return {"false_refusals_answerable": false_ref, "wrong_answers_automatic": wrong, "llm_calls_per_question": {"mean": mean_calls}}


def test_keep_rule_needs_all_three_conditions_exactly_as_pre_registered():
    a = _m(6, 3, 1)
    assert ev.keep_rule(a, _m(4, 3, 4.0))["verdict"].startswith("ELIGIBLE")
    assert ev.keep_rule(a, _m(5, 3, 3.5))["verdict"] == "STAYS_OPTIONAL_AND_OFF"      # only 1 fewer false refusal
    assert ev.keep_rule(a, _m(2, 4, 3.5))["verdict"] == "STAYS_OPTIONAL_AND_OFF"      # wrong answers increased
    assert ev.keep_rule(a, _m(2, 3, 4.01))["verdict"] == "STAYS_OPTIONAL_AND_OFF"     # calls above 4


def test_test_split_refuses_without_the_frozen_hash(monkeypatch):
    args = type("A", (), {"split": "test", "label": "x", "max_calls": 10, "limit": None, "expect_config_hash": None, "fake": False})()
    with pytest.raises(SystemExit, match="expect-config-hash"):
        ev.cmd_run(args)


def test_config_hash_is_stable_and_covers_the_agent_files():
    h1 = ev.current_config_hash()
    assert h1 == ev.current_config_hash() and len(h1) == 64
    assert any(f.endswith("pipeline.py") for f in ev.agent_files())
