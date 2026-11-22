"""Agreement between two label files (labels 0/1/2 or U/P/N).

Usage: python tools/judge_agreement.py A.json B.json --name-a J1 --name-b J2 [--questions 1-13] [--out-prefix PATH]
Writes PATH.json and PATH.md: raw agreement, Cohen's kappa (unweighted and linear-weighted), the 3x3 confusion matrix
(rows = A, columns = B, order N,P,U) and per-question agreement. Standard library only.
"""
import argparse
import json
import os
from typing import Dict, List, Optional

LEVELS = (0, 1, 2)
NAMES = {0: "N", 1: "P", 2: "U"}
_CONV = {"U": 2, "P": 1, "N": 0}


def load_labels(path: str) -> Dict[str, int]:
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, dict) and "labels" in d:
        d = d["labels"]
    if isinstance(d, list):                       # raw judge output: [{"id","label","reason"}]
        return {x["id"]: _CONV[x["label"]] if isinstance(x["label"], str) else int(x["label"]) for x in d}
    return {k: (_CONV[v["label"]] if isinstance(v["label"], str) else int(v["label"])) for k, v in d.items()}


def confusion(a: List[int], b: List[int]) -> List[List[int]]:
    m = [[0] * 3 for _ in range(3)]
    for x, y in zip(a, b):
        m[x][y] += 1
    return m


def cohen_kappa(a: List[int], b: List[int], weights: str = "none") -> Optional[float]:
    """weights: 'none' (unweighted) or 'linear'. Returns None when expected disagreement is 0."""
    n = len(a)
    if n == 0:
        return None
    m = confusion(a, b)
    row = [sum(m[i]) for i in range(3)]
    col = [sum(m[i][j] for i in range(3)) for j in range(3)]

    def w(i, j):
        return (0.0 if i == j else 1.0) if weights == "none" else abs(i - j) / 2.0

    observed = sum(w(i, j) * m[i][j] for i in range(3) for j in range(3)) / n
    expected = sum(w(i, j) * row[i] * col[j] for i in range(3) for j in range(3)) / (n * n)
    if expected == 0:
        return None
    return 1.0 - observed / expected


def summarise(la: Dict[str, int], lb: Dict[str, int], qmap: Dict[str, int], qs: Optional[range] = None) -> Dict:
    ids = sorted(i for i in la if i in lb and (qs is None or qmap[i] in qs))
    a, b = [la[i] for i in ids], [lb[i] for i in ids]
    agree = sum(x == y for x, y in zip(a, b))
    per_q = {}
    for q in sorted({qmap[i] for i in ids}):
        qi = [i for i in ids if qmap[i] == q]
        per_q[q] = {"n": len(qi), "agree": sum(la[i] == lb[i] for i in qi),
                    "raw": round(sum(la[i] == lb[i] for i in qi) / len(qi), 4)}
    k = cohen_kappa(a, b)
    kw = cohen_kappa(a, b, "linear")
    return {"n": len(ids), "agree": agree, "raw_agreement": round(agree / len(ids), 4) if ids else None,
            "kappa_unweighted": None if k is None else round(k, 4),
            "kappa_linear_weighted": None if kw is None else round(kw, 4),
            "confusion_rows_A_cols_B_order_N_P_U": confusion(a, b), "per_question": per_q,
            "disputed_ids": [i for i in ids if la[i] != lb[i]]}


def to_markdown(name_a: str, name_b: str, s: Dict) -> str:
    c = s["confusion_rows_A_cols_B_order_N_P_U"]
    lines = [f"# Agreement: {name_a} vs {name_b}", "",
             f"n = {s['n']} items, exact agreement {s['agree']}/{s['n']} = {s['raw_agreement']}",
             f"Cohen's kappa unweighted = {s['kappa_unweighted']}, linear-weighted = {s['kappa_linear_weighted']}", "",
             f"Confusion matrix (rows {name_a}, columns {name_b}):", "",
             f"| {name_a} vs {name_b} | N | P | U |", "|---|---|---|---|"]
    for i, nm in enumerate("NPU"):
        lines.append(f"| {nm} | {c[i][0]} | {c[i][1]} | {c[i][2]} |")
    lines += ["", "Per question:", "", "| Q | n | agree | raw |", "|---|---|---|---|"]
    for q, v in s["per_question"].items():
        lines.append(f"| {q} | {v['n']} | {v['agree']} | {v['raw']} |")
    return "\n".join(lines) + "\n"


def question_map(packet_path: str) -> Dict[str, int]:
    return {json.loads(l)["id"]: json.loads(l)["question_no"] for l in open(packet_path, encoding="utf-8")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--name-a", default="A")
    ap.add_argument("--name-b", default="B")
    ap.add_argument("--questions", default="1-15")
    ap.add_argument("--out-prefix")
    ap.add_argument("--packet", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                    "reports", "evidence", "judging", "packet.jsonl"))
    x = ap.parse_args()
    lo, hi = (int(v) for v in x.questions.split("-"))
    s = summarise(load_labels(x.a), load_labels(x.b), question_map(x.packet), range(lo, hi + 1))
    s["a"], s["b"], s["questions"] = x.name_a, x.name_b, x.questions
    md = to_markdown(x.name_a, x.name_b, s)
    if x.out_prefix:
        json.dump(s, open(x.out_prefix + ".json", "w", encoding="utf-8"), indent=1)
        open(x.out_prefix + ".md", "w", encoding="utf-8", newline="\n").write(md)
    print(md)


if __name__ == "__main__":
    main()
