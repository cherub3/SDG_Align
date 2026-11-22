"""tools/judge_agreement.py: kappa and confusion matrix against hand-computed values."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import judge_agreement as ja  # noqa: E402


def test_perfect_and_chance_agreement():
    a = [0, 1, 2, 0, 1, 2]
    assert ja.cohen_kappa(a, a) == pytest.approx(1.0)
    assert ja.cohen_kappa([0, 0, 1, 1], [0, 1, 0, 1]) == pytest.approx(0.0)


def test_unweighted_kappa_matches_hand_computation():
    # 10 items: A = [2]*5+[1]*3+[0]*2, B = same except two 2s labelled 1 and one 0 labelled 1
    a = [2, 2, 2, 2, 2, 1, 1, 1, 0, 0]
    b = [2, 2, 2, 1, 1, 1, 1, 1, 0, 1]
    # observed agreement 7/10; row sums (N,P,U)=(2,3,5), col sums = (1,6,3); expected = (2*1+3*6+5*3)/100 = 0.35
    assert ja.cohen_kappa(a, b) == pytest.approx((0.7 - 0.35) / (1 - 0.35))


def test_linear_weighted_kappa_penalises_two_step_errors_more():
    a = [0, 0, 2, 2]
    near = [1, 0, 2, 1]        # one-step errors only
    far = [2, 0, 0, 2]         # two-step errors only
    assert ja.cohen_kappa(a, near, "linear") > ja.cohen_kappa(a, far, "linear")


def test_confusion_matrix_orientation_and_degenerate_case():
    assert ja.confusion([0, 2], [1, 2]) == [[0, 1, 0], [0, 0, 0], [0, 0, 1]]
    assert ja.cohen_kappa([1, 1, 1], [1, 1, 1]) is None          # no variation: kappa undefined
