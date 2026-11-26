"""Scores the filled human labelling sheet. Un-blinds with eval/human_labels/arm_key.json. No model call.

Reports per arm: counts of correct / partial / wrong / refused (implicit refusals counted as refused and also reported separately) with Wilson 95% intervals;
exact McNemar on correctness (correct vs not correct, paired by question) between the arms; Cohen's kappa between the human labels and the existing AI
labels for arm A (eval/test_v21_correctness_final.json); optionally the labeller's own agreement on the re-labelled rows (--relabel).
Writes eval/results/human_label_results.json unless --out is given.

    python tools/score_human_labels.py [--sheet PATH] [--key PATH] [--ai PATH] [--relabel PATH] [--out PATH]
"""
import argparse
import collections
import csv
import json
import math
import os

from scipy.stats import binomtest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HL = os.path.join(REPO, "eval", "human_labels")
LABELS = ("correct", "partial", "wrong", "refused")
SENTINEL = "NOT_IN_CONTEXT"
IMPLICIT = "implicit"
LIMITATIONS = [
    "Blinding is partial: before labelling, the labeller had read the project review report (a document outside this repository), which names the outcomes of some items "
    "(for example items that arm B refused or got wrong by the automatic check). Arm identity is hidden in the sheet, but the labeller may recall some item outcomes.",
    "One labeller; labels follow the frozen Phase 3.5 rubric plus Amendment 1 (free-text refusals are labelled refused with note 'implicit').",
    "Judged against gold quotes, not the source PDFs.",
]


class SheetError(Exception):
    pass


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def cohen_kappa(x, y, categories=LABELS):
    n = len(x)
    if n == 0 or n != len(y):
        raise ValueError("need two label lists of the same non-zero length")
    po = sum(a == b for a, b in zip(x, y)) / n
    cx, cy = collections.Counter(x), collections.Counter(y)
    pe = sum((cx[c] / n) * (cy[c] / n) for c in categories)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def mcnemar_exact(a, b):
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    only_b = sum(1 for x, y in zip(a, b) if y and not x)
    d = only_a + only_b
    return {"both": sum(1 for x, y in zip(a, b) if x and y), "only_A": only_a, "only_B": only_b,
            "neither": sum(1 for x, y in zip(a, b) if not x and not y), "discordant": d,
            "exact_p": round(float(binomtest(min(only_a, only_b), d, 0.5).pvalue), 4) if d else 1.0}


def load_sheet(path):
    """Returns (rows, labels, notes). Every row needs a valid label; the note column is optional."""
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
    labels, notes, problems = {}, {}, []
    for r in rows:
        v = (r.get("label") or "").strip().lower()
        if v not in LABELS:
            problems.append(f"{r.get('code')}: label {r.get('label')!r} is not one of {', '.join(LABELS)}")
        labels[r["code"]] = v
        notes[r["code"]] = (r.get("note") or "").strip().lower()
    if problems:
        raise SheetError(f"{len(problems)} row(s) unlabelled or invalid, e.g. " + "; ".join(problems[:5]))
    return rows, labels, notes


def self_agreement(first_labels, relabel_path, codes_path=None):
    """The labeller's own agreement on the re-labelled rows. Returns None if the relabel sheet is not filled in yet."""
    try:
        _, second, _ = load_sheet(relabel_path)
    except SheetError as e:
        return {"status": "not scored", "reason": str(e)}
    if codes_path:
        expected = set(json.load(open(codes_path, encoding="utf-8"))["codes"])
        if set(second) != expected:
            raise SheetError("relabel sheet codes differ from relabel_codes.json")
    shared = sorted(c for c in second if c in first_labels)
    x, y = [first_labels[c] for c in shared], [second[c] for c in shared]
    agree = sum(a == b for a, b in zip(x, y))
    return {"status": "scored", "n": len(shared), "agree": agree, "raw_agreement": round(agree / len(shared), 3) if shared else None,
            "cohens_kappa": round(cohen_kappa(x, y), 4) if shared else None,
            "note": "n is small (10); kappa is unstable at this size, read raw agreement first.",
            "disagreements": [{"code": c, "first": a, "second": b} for c, a, b in zip(shared, x, y) if a != b]}


def score(sheet_path, key_path, ai_path, relabel_path=None, relabel_codes_path=None):
    rows, labels, notes = load_sheet(sheet_path)
    key = json.load(open(key_path, encoding="utf-8"))["key"]
    if set(key) != set(labels):
        raise SheetError("sheet codes and key codes differ")
    per_arm = {"A": {}, "B": {}}
    implicit = {"A": [], "B": []}
    warnings = []
    for r in rows:
        k = key[r["code"]]
        lab = labels[r["code"]]
        per_arm[k["arm"]][k["qid"]] = lab
        exact = r["answer"].strip() == SENTINEL
        is_implicit = lab == "refused" and not exact and notes[r["code"]] == IMPLICIT
        if is_implicit:
            implicit[k["arm"]].append(k["qid"])
        elif lab == "refused" and not exact:
            warnings.append(f"{r['code']} ({k['qid']}): labelled refused but the answer is not exactly {SENTINEL} and the note is not '{IMPLICIT}'")
        elif exact and lab != "refused":
            warnings.append(f"{r['code']} ({k['qid']}): the answer is exactly {SENTINEL} but the label is {lab!r}")
    qids = sorted(per_arm["A"])
    if qids != sorted(per_arm["B"]):
        raise SheetError("arms do not cover the same questions")
    out = {"n_questions": len(qids), "limitations": LIMITATIONS, "warnings": warnings, "arms": {}}
    for arm in ("A", "B"):
        c = collections.Counter(per_arm[arm].values())
        n = len(qids)
        answered = n - c["refused"]
        out["arms"][arm] = {
            "counts": {l: c[l] for l in LABELS},
            "implicit_refusals": {"count": len(implicit[arm]), "qids": sorted(implicit[arm]), "explicit_sentinel_refusals": c["refused"] - len(implicit[arm])},
            "correct_of_all": {"k": c["correct"], "n": n, "rate": round(c["correct"] / n, 3), "wilson95": wilson(c["correct"], n)},
            "correct_or_partial_of_all": {"k": c["correct"] + c["partial"], "n": n, "wilson95": wilson(c["correct"] + c["partial"], n)},
            "wrong_of_answered": {"k": c["wrong"], "n": answered, "wilson95": wilson(c["wrong"], answered)},
            "refused_of_all": {"k": c["refused"], "n": n, "wilson95": wilson(c["refused"], n)}}
    ca = [per_arm["A"][q] == "correct" for q in qids]
    cb = [per_arm["B"][q] == "correct" for q in qids]
    out["mcnemar_correct_A_vs_B"] = mcnemar_exact(ca, cb)
    ai = json.load(open(ai_path, encoding="utf-8"))["labels"]
    shared = [q for q in qids if q in ai]
    k = cohen_kappa([per_arm["A"][q] for q in shared], [ai[q]["label"] for q in shared])
    agree = sum(per_arm["A"][q] == ai[q]["label"] for q in shared)
    out["kappa_human_vs_ai_arm_A"] = {"n": len(shared), "agree": agree, "cohens_kappa": round(k, 4),
                                       "disagreements": [{"qid": q, "human": per_arm["A"][q], "ai": ai[q]["label"]} for q in shared if per_arm["A"][q] != ai[q]["label"]]}
    out["labeller_self_agreement"] = self_agreement(labels, relabel_path, relabel_codes_path) if relabel_path else {"status": "not requested"}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=os.path.join(HL, "labelling_sheet.csv"))
    ap.add_argument("--key", default=os.path.join(HL, "arm_key.json"))
    ap.add_argument("--ai", default=os.path.join(REPO, "eval", "test_v21_correctness_final.json"))
    ap.add_argument("--relabel", default=None, help="filled relabel_sheet.csv (10 rows labelled a second time)")
    ap.add_argument("--relabel-codes", default=os.path.join(HL, "relabel_codes.json"))
    ap.add_argument("--out", default=os.path.join(REPO, "eval", "results", "human_label_results.json"))
    a = ap.parse_args()
    try:
        res = score(a.sheet, a.key, a.ai, a.relabel, a.relabel_codes if a.relabel else None)
    except SheetError as e:
        raise SystemExit(f"cannot score: {e}")
    json.dump(res, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
