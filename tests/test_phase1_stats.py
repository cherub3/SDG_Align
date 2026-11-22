"""Exact sign test and Wilcoxon, and the final-label majority rule."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import build_final_labels as bfl  # noqa: E402
import compute_phase1_results as cpr  # noqa: E402


def test_sign_test_exact_values():
    assert cpr.sign_test_two_sided([1] * 5) == pytest.approx(2 * 0.5 ** 5)
    assert cpr.sign_test_two_sided([1, -1, 1, -1]) == 1.0
    assert cpr.sign_test_two_sided([0, 0]) == 1.0                  # all ties


def test_wilcoxon_exact_all_positive_and_symmetric_cases():
    p, w = cpr.wilcoxon_exact_two_sided([1, 2, 3, 4, 5, 6])
    assert p == pytest.approx(2 / 64) and w == 21
    assert cpr.wilcoxon_exact_two_sided([1, -1])[0] == 1.0
    assert cpr.wilcoxon_exact_two_sided([0, 0]) == (1.0, 0.0)


def test_final_label_rule():
    assert bfl.decide(2, 2) == (2, False, "J1=J2")
    assert bfl.decide(0, 1, 1)[:2] == (1, False)
    assert bfl.decide(0, 2, 1) == (1, True, "unresolved (all three differ) -> P")
    with pytest.raises(ValueError):
        bfl.decide(0, 1)
