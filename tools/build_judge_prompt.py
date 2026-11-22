"""Build the prompt file for one judge run and save it under reports/evidence/judging/prompts/.

Usage: python tools/build_judge_prompt.py NAME --ids FILE_OR_ALL [--order-seed N] [--questions 1,2,3]
Items are grouped by question (all passages of a question together). The prompt contains the rubric verbatim, the one-line
role instruction, the items, and the output format. It contains nothing else.
"""
import argparse
import json
import os
import random

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = os.path.join(REPO, "reports", "evidence", "judging")

ROLE = "You are rating search results for relevance. Use only the rubric."
FORMAT = """Return a JSON array and nothing else. One object per passage, using exactly these keys:
  {"id": "<the passage id>", "label": "U" or "P" or "N", "reason": "<one line that quotes or points to words in the passage>"}
U = useful (2), P = partial (1), N = not useful (0). Label every passage listed below, exactly once.
Write your answer to the file path given in the task message using the Write tool, as the exact JSON array. Do not read any other file,
do not run any command, and do not use any other tool."""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--ids", default="ALL", help="ALL, or a JSON file with a list of ids")
    ap.add_argument("--order-seed", type=int, default=None, help="shuffle the order of passages inside each question")
    ap.add_argument("--question-order-seed", type=int, default=None)
    ap.add_argument("--packet", default="packet.jsonl", help="packet file name inside reports/evidence/judging/")
    a = ap.parse_args()
    packet = [json.loads(l) for l in open(os.path.join(J, a.packet), encoding="utf-8")]
    if a.ids != "ALL":
        want = set(json.load(open(a.ids, encoding="utf-8")))
        packet = [p for p in packet if p["id"] in want]
    by_q = {}
    for p in packet:
        by_q.setdefault(p["question_no"], []).append(p)
    qs = sorted(by_q)
    if a.question_order_seed is not None:
        random.Random(a.question_order_seed).shuffle(qs)
    rubric = open(os.path.join(J, "rubric.md"), encoding="utf-8").read()
    out = [ROLE, "", "# Rubric", "", rubric, "# Output format", "", FORMAT, "", "# Passages", ""]
    for q in qs:
        items = by_q[q]
        if a.order_seed is not None:
            random.Random(a.order_seed + q).shuffle(items)
        out += [f"## Question: {items[0]['question']}", ""]
        for it in items:
            out += [f"### Passage {it['id']}", "", "```text", it["text"].strip(), "```", ""]
    path = os.path.join(J, "prompts", f"{a.name}.md")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print(path, "items:", sum(len(v) for v in by_q.values()), "questions:", len(qs), "chars:", len("\n".join(out)))


if __name__ == "__main__":
    main()
