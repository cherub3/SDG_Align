"""Paired per-type arm comparison (tools/compare_arms.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import compare_arms as ca  # noqa: E402


def _row(qid, typ, text, calls=1, lat=100):
    return {"qid": qid, "type": typ, "response_text": text, "total_calls": calls, "latency_ms": lat, "prompt_tokens": 10}


def _arm(refusals, calls=1):
    rows = {}
    for i in range(10):
        rows[f"c{i}"] = _row(f"c{i}", "cross_document", "NOT_IN_CONTEXT" if i in refusals else "an answer", calls)
    rows["u0"] = _row("u0", "unanswerable", "NOT_IN_CONTEXT", calls)
    return rows


def test_arm_stats_counts_refusals_calls_and_latency():
    s = ca.arm_stats(_arm({0, 1, 2}, calls=3))
    assert s["false_refusal_cross_document"] == "3/10" and s["unanswerable_refused"] == "1/1"
    assert s["gemini_calls_per_request"] == {"mean": 3.0, "max": 3, "total": 33} and s["latency_ms_per_request"]["p50"] == 100


def test_paired_comparison_counts_flips_and_uses_an_exact_test():
    base, other = _arm(set(range(9))), _arm({0, 1, 2})
    c = ca.compare({"A": base, "B": other}, "A")["paired_vs_base"]["B vs A"]["cross_document"]
    assert (c["refused_base"], c["refused_other"], c["no_longer_refused"], c["newly_refused"]) == (9, 3, 6, 0)
    assert c["delta_rate"] == -0.6 and c["mcnemar_exact_p"] == 0.0312


def test_identical_arms_have_no_flips_and_p_one():
    c = ca.compare({"A": _arm({1}), "B": _arm({1})}, "A")["paired_vs_base"]["B vs A"]["answerable_all"]
    assert c["no_longer_refused"] == c["newly_refused"] == 0 and c["mcnemar_exact_p"] == 1.0
