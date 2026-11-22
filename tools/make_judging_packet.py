"""Step 1 of the AI-judge evaluation: build the judge packet and the verbatim rubric.

packet.jsonl: one object per item {id, question_no, question, text}. IDs and passages come from
blind_judging.jsonl (the same 144 items Judge 1 labelled); the order is re-shuffled with a NEW seed.
No score, rank, version or document field exists in the packet.
rubric.md: the judge-facing part of metrics_definitions.md section 5, copied verbatim, except that the
bullet about the two NOT INDEXED questions is left out (it is a scoring rule that would tell the judge
which questions have no answer in the index). Those two questions are scored 0 by the frozen rule.
"""
import json
import os
import random
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(REPO, "reports", "evidence")
OUT = os.path.join(EV, "judging")
SEED = 77012          # Judge 1's blind file used 20261123


def build_rubric() -> str:
    t = open(os.path.join(EV, "metrics_definitions.md"), encoding="utf-8").read()
    start = t.index("Every retrieved chunk, for every question")
    end = t.index("Metrics from the judgements")
    block = t[start:end].rstrip() + "\n"
    lines = [ln for ln in block.split("\n")
             if not ln.startswith("* For the two NOT INDEXED questions")]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    items = [json.loads(l) for l in open(os.path.join(EV, "blind_judging.jsonl"), encoding="utf-8")]
    items.sort(key=lambda i: i["id"])                    # canonical order first, then the seeded shuffle
    random.Random(SEED).shuffle(items)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "packet.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for it in items:
            fh.write(json.dumps({"id": it["id"], "question_no": it["question_no"],
                                 "question": it["question"], "text": it["text"]}, ensure_ascii=False) + "\n")
    open(os.path.join(OUT, "rubric.md"), "w", encoding="utf-8", newline="\n").write(build_rubric())
    print("packet items:", len(items), "seed:", SEED)


if __name__ == "__main__":
    main()
