"""Asserts the judge packet is clean: no key/score/version fields, no duplicate ids, complete."""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(REPO, "reports", "evidence")
ALLOWED = {"id", "question_no", "question", "text"}
FORBIDDEN_SUBSTR = ("score", "rank", "version", "before", "after", "doc", "chunk_id", "source")


def main() -> int:
    packet = [json.loads(l) for l in open(os.path.join(EV, "judging", "packet.jsonl"), encoding="utf-8")]
    blind = [json.loads(l) for l in open(os.path.join(EV, "blind_judging.jsonl"), encoding="utf-8")]
    ids = [p["id"] for p in packet]
    problems = []
    for p in packet:
        extra = set(p) - ALLOWED
        if extra:
            problems.append(f"{p['id']}: unexpected fields {sorted(extra)}")
        for k in p:
            if any(s in k.lower() for s in FORBIDDEN_SUBSTR):
                problems.append(f"{p['id']}: forbidden field name {k}")
    if len(ids) != len(set(ids)):
        problems.append("duplicate ids in packet")
    missing = {b["id"] for b in blind} - set(ids)
    if missing:
        problems.append(f"ids missing from packet: {sorted(missing)[:5]}")
    unexpected = set(ids) - {b["id"] for b in blind}
    if unexpected:
        problems.append(f"packet ids not in blind_judging.jsonl: {sorted(unexpected)[:5]}")
    same_text = all(p["text"] == next(b["text"] for b in blind if b["id"] == p["id"]) for p in packet)
    if not same_text:
        problems.append("packet text differs from blind_judging.jsonl")
    order_differs = ids != [b["id"] for b in blind]
    if not order_differs:
        problems.append("packet order equals Judge 1's order (shuffle did not change it)")
    print(f"items: {len(packet)}  unique ids: {len(set(ids))}  fields: {sorted(ALLOWED)}")
    print(f"all {len(blind)} ids of blind_judging.jsonl present: {not missing}")
    print(f"order differs from blind_judging.jsonl: {order_differs}")
    for p in problems:
        print("PROBLEM:", p)
    print("RESULT:", "PASS" if not problems else "FAIL")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
