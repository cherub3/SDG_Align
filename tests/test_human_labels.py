"""Labelling kit and scorer, on small synthetic data. No network, no model call."""
import csv
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import build_labelling_kit as kit  # noqa: E402
import score_human_labels as sc  # noqa: E402

FIELDS = ["code", "question", "gold_quote", "answer", "label", "note"]


def _write(tmp_path, labels, answers=None, notes=None):
    """6 questions x 2 arms, codes L1..L12 (odd = arm A, even = arm B). labels: dict code -> label."""
    key = {}
    rows = []
    for i in range(6):
        for arm in ("A", "B"):
            code = f"L{len(rows) + 1}"
            key[code] = {"qid": f"Q{i}", "arm": arm}
            rows.append({"code": code, "question": "q", "gold_quote": "g", "answer": (answers or {}).get(code, "some answer"),
                         "label": labels.get(code, ""), "note": (notes or {}).get(code, "")})
    sheet = tmp_path / "s.csv"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    kp = tmp_path / "k.json"
    kp.write_text(json.dumps({"key": key}))
    ai = tmp_path / "ai.json"
    ai.write_text(json.dumps({"labels": {f"Q{i}": {"label": l} for i, l in enumerate(["correct", "correct", "partial", "wrong", "refused", "correct"])}}))
    return sheet, kp, ai


def _labels(a, b):
    out = {}
    for i in range(6):
        out[f"L{2 * i + 1}"], out[f"L{2 * i + 2}"] = a[i], b[i]
    return out


A_LAB = ["correct", "correct", "partial", "wrong", "refused", "correct"]
B_LAB = ["correct", "partial", "correct", "wrong", "refused", "refused"]


def test_wilson_matches_the_project_value():
    assert sc.wilson(31, 44) == [0.558, 0.818]            # eval/results/test_v21_correctness_summary.json


def test_kappa_perfect_and_chance():
    x = ["correct", "partial", "wrong", "refused"]
    assert sc.cohen_kappa(x, x) == 1.0
    assert sc.cohen_kappa(["correct", "correct", "wrong", "wrong"], ["correct", "wrong", "correct", "wrong"]) == 0.0


def test_mcnemar_exact_hand_checked():
    r = sc.mcnemar_exact([True] * 5 + [False] * 3, [False] * 5 + [True] + [False] * 2)
    assert (r["only_A"], r["only_B"], r["discordant"]) == (5, 1, 6) and r["exact_p"] == 0.2188


def test_scores_a_filled_sheet_and_unblinds(tmp_path):
    answers = {"L9": "NOT_IN_CONTEXT", "L10": "NOT_IN_CONTEXT", "L12": "NOT_IN_CONTEXT"}
    sheet, kp, ai = _write(tmp_path, _labels(A_LAB, B_LAB), answers)
    res = sc.score(str(sheet), str(kp), str(ai))
    assert res["arms"]["A"]["counts"] == {"correct": 3, "partial": 1, "wrong": 1, "refused": 1}
    assert res["arms"]["B"]["counts"] == {"correct": 2, "partial": 1, "wrong": 1, "refused": 2}
    m = res["mcnemar_correct_A_vs_B"]
    assert (m["both"], m["only_A"], m["only_B"], m["neither"]) == (1, 2, 1, 2) and m["exact_p"] == 1.0
    assert res["kappa_human_vs_ai_arm_A"]["agree"] == 6 and res["kappa_human_vs_ai_arm_A"]["cohens_kappa"] == 1.0
    assert res["warnings"] == []
    assert res["arms"]["A"]["implicit_refusals"]["count"] == 0


def test_blank_or_invalid_labels_are_refused_not_guessed(tmp_path):
    sheet, kp, ai = _write(tmp_path, {"L1": "correct", "L2": "maybe"})
    with pytest.raises(sc.SheetError):
        sc.score(str(sheet), str(kp), str(ai))


def test_label_refused_with_a_non_sentinel_text_and_no_note_is_warned(tmp_path):
    labels = {f"L{i}": "correct" for i in range(1, 13)}
    labels["L1"] = "refused"
    sheet, kp, ai = _write(tmp_path, labels)
    assert any("L1" in w for w in sc.score(str(sheet), str(kp), str(ai))["warnings"])


def test_implicit_refusal_is_counted_as_refused_reported_separately_and_not_warned(tmp_path):
    labels = _labels(A_LAB, B_LAB)
    answers = {"L9": "NOT_IN_CONTEXT", "L10": "The excerpts do not state this.", "L12": "NOT_IN_CONTEXT"}
    sheet, kp, ai = _write(tmp_path, labels, answers, notes={"L10": "Implicit"})
    res = sc.score(str(sheet), str(kp), str(ai))
    assert res["warnings"] == []
    b = res["arms"]["B"]
    assert b["counts"]["refused"] == 2
    assert b["implicit_refusals"] == {"count": 1, "qids": ["Q4"], "explicit_sentinel_refusals": 1}
    assert res["arms"]["A"]["implicit_refusals"]["count"] == 0


def test_an_exact_sentinel_answer_labelled_something_else_is_still_warned(tmp_path):
    sheet, kp, ai = _write(tmp_path, {f"L{i}": "correct" for i in range(1, 13)}, {"L3": "NOT_IN_CONTEXT"})
    assert any("L3" in w for w in sc.score(str(sheet), str(kp), str(ai))["warnings"])


def test_limitations_record_the_partial_blinding(tmp_path):
    sheet, kp, ai = _write(tmp_path, {f"L{i}": "correct" for i in range(1, 13)})
    lim = " ".join(sc.score(str(sheet), str(kp), str(ai))["limitations"])
    assert "Blinding is partial" in lim and "review report" in lim
    assert "D:" not in lim and "\\" not in lim                      # no local path in a file that is committed


def _relabel_sheet(tmp_path, codes, labels):
    p = tmp_path / "r.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for c in codes:
            w.writerow({"code": c, "question": "q", "gold_quote": "g", "answer": "a", "label": labels.get(c, ""), "note": ""})
    cp = tmp_path / "codes.json"
    cp.write_text(json.dumps({"codes": codes}))
    return str(p), str(cp)


def test_self_agreement_on_the_relabelled_rows(tmp_path):
    first = _labels(A_LAB, B_LAB)
    sheet, kp, ai = _write(tmp_path, first, {"L9": "NOT_IN_CONTEXT", "L10": "NOT_IN_CONTEXT", "L12": "NOT_IN_CONTEXT"})
    codes = ["L1", "L2", "L3", "L4"]
    second = {"L1": "correct", "L2": "partial", "L3": "correct", "L4": "correct"}      # first: correct, correct, correct, partial -> L1 and L3 agree
    rp, cp = _relabel_sheet(tmp_path, codes, second)
    res = sc.score(str(sheet), str(kp), str(ai), rp, cp)["labeller_self_agreement"]
    assert res["status"] == "scored" and res["n"] == 4 and res["agree"] == 2 and res["raw_agreement"] == 0.5
    assert {d["code"] for d in res["disagreements"]} == {"L2", "L4"}


def test_unfilled_relabel_sheet_is_reported_not_scored_and_does_not_block(tmp_path):
    sheet, kp, ai = _write(tmp_path, {f"L{i}": "correct" for i in range(1, 13)})
    rp, cp = _relabel_sheet(tmp_path, ["L1", "L2"], {})
    assert sc.score(str(sheet), str(kp), str(ai), rp, cp)["labeller_self_agreement"]["status"] == "not scored"


def test_real_kit_has_88_blind_rows_a_note_column_and_a_fixed_relabel_set():
    sheet, key = kit.build()
    assert len(sheet) == 88 and len(key) == 88
    assert sum(v["arm"] == "A" for v in key.values()) == 44 and sum(v["arm"] == "B" for v in key.values()) == 44
    assert all(r["label"] == "" and r["note"] == "" for r in sheet)
    assert list(sheet[0]) == ["code", "question", "gold_quote", "answer", "label", "note"]
    assert not any("[doc_" in r["answer"] for r in sheet)                        # no chunk-id markers
    assert kit.build()[1] == key                                                 # deterministic
    for q in {v["qid"] for v in key.values()}:
        assert sorted(v["arm"] for v in key.values() if v["qid"] == q) == ["A", "B"]
    codes = kit.relabel_codes(sheet)
    assert len(codes) == 10 and len(set(codes)) == 10 and codes == kit.relabel_codes(sheet) and set(codes) <= {r["code"] for r in sheet}
