"""Final label per item = majority of Judge 1 (frozen), Judge 2 and Judge 3.

Judge 3 only labelled the items on which Judge 1 and Judge 2 disagreed. If all three differ the label is P and the
item is listed as unresolved. Questions 14 and 15 are 0 by the frozen scoring rule.
Usage: python tools/build_final_labels.py   (reads and writes reports/evidence/judging/)
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge_agreement as ja  # noqa: E402

J = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "evidence", "judging")


def decide(l1, l2, l3=None):
    """Returns (label, unresolved, source)."""
    if l1 == l2:
        return l1, False, "J1=J2"
    if l3 is None:
        raise ValueError("a disputed item needs Judge 3")
    c = collections.Counter([l1, l2, l3]).most_common()
    if c[0][1] >= 2:
        return c[0][0], False, "majority"
    return 1, True, "unresolved (all three differ) -> P"


def main():
    j1 = ja.load_labels(os.path.join(J, "labels_judge1_frozen.json"))
    j2 = ja.load_labels(os.path.join(J, "labels_judge2.json"))
    j3 = ja.load_labels(os.path.join(J, "labels_judge3_disputed.json"))
    qmap = ja.question_map(os.path.join(J, "packet.jsonl"))
    out, unresolved = {}, []
    for i in sorted(j1):
        if qmap[i] in (14, 15):
            out[i] = {"label": 0, "source": "frozen rule: Q14/Q15 scored 0", "j1": j1[i], "j2": j2[i]}
            continue
        label, unres, src = decide(j1[i], j2[i], j3.get(i))
        out[i] = {"label": label, "source": src, "j1": j1[i], "j2": j2[i], "j3": j3.get(i)}
        if unres:
            unresolved.append(i)
    json.dump({"rule": "majority of J1 frozen, J2, J3; all differ -> P (unresolved); Q14/Q15 -> 0",
               "unresolved": unresolved, "labels": out},
              open(os.path.join(J, "labels_final.json"), "w", encoding="utf-8"), indent=1)
    print("final labels:", len(out), "unresolved:", unresolved)
    print(dict(collections.Counter(v["source"] for v in out.values())))


if __name__ == "__main__":
    main()
