"""Build the blind-judging files from retrieval_before.json and retrieval_after.json.

Outputs (reports/evidence/):
  blind_judging.jsonl      one JSON object per unique (question, text): id, question_no, question, text.
                           No version, document name, rank or score. Globally shuffled with a fixed seed.
  blind_key.json           id -> where each item came from (versions, ranks, documents, scores). NOT opened
                           until labels are saved.
  blind_for_owner.md       5 of the 13 answerable questions (seeded), each with its shuffled passages.
An identical text (whitespace-normalised) that both versions returned for the same question appears once.
"""
import json
import os
import random
import re
import sys

EV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "evidence")
SEED = 20261123
ANSWERABLE = list(range(1, 14))
_WS = re.compile(r"\s+")


def norm(t):
    return _WS.sub(" ", t).strip()


def main():
    before = json.load(open(os.path.join(EV, "retrieval_before.json"), encoding="utf-8"))
    after = json.load(open(os.path.join(EV, "retrieval_after.json"), encoding="utf-8"))
    rng = random.Random(SEED)
    items = {}
    for version, data in (("before", before), ("after", after)):
        for q in data["results"]:
            for t in q["top5"]:
                k = (q["n"], norm(t["text"]))
                it = items.setdefault(k, {"question_no": q["n"], "question": q["question"], "text": t["text"], "sources": []})
                it["sources"].append({"version": version, "rank": t["rank"], "doc": t["doc"],
                                      "score": t["score"], "chunk_id": t["chunk_id"]})
    ordered = sorted(items.values(), key=lambda i: (i["question_no"], i["text"]))   # deterministic base order
    rng.shuffle(ordered)
    used, key = set(), {}
    with open(os.path.join(EV, "blind_judging.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for it in ordered:
            while True:
                bid = "B" + "%05x" % rng.randrange(16 ** 5)
                if bid not in used:
                    used.add(bid)
                    break
            it["id"] = bid
            fh.write(json.dumps({"id": bid, "question_no": it["question_no"], "question": it["question"],
                                 "text": it["text"]}, ensure_ascii=False) + "\n")
            key[bid] = {"question_no": it["question_no"], "sources": it["sources"]}
    json.dump({"seed": SEED, "items": key}, open(os.path.join(EV, "blind_key.json"), "w", encoding="utf-8"), indent=1)

    pick = sorted(random.Random(SEED).sample(ANSWERABLE, 5))
    lines = ["# Blind labelling: 5 questions", "",
             "Label each passage **U** (useful), **P** (partial) or **N** (not useful), with a one-line reason. "
             "Read only the question and the passage text. Rubric: `reports/evidence/metrics_definitions.md` section 5 "
             "(when unsure between two levels, choose the lower one).", "",
             f"Questions chosen with seed {SEED} from the 13 answerable ones.", ""]
    for n in pick:
        qi = [i for i in ordered if i["question_no"] == n]
        lines += [f"## Question {n}: {qi[0]['question']}", ""]
        for i in qi:
            lines += [f"### {i['id']}", "", "```text", i["text"].strip(), "```", "", "Label: ", "Reason: ", ""]
    open(os.path.join(EV, "blind_for_owner.md"), "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    json.dump({"seed": SEED, "questions": pick}, open(os.path.join(EV, "blind_user_selection.json"), "w"))
    print("items", len(ordered), "per question", {n: sum(1 for i in ordered if i["question_no"] == n) for n in range(1, 16)})
    print("user questions", pick)


if __name__ == "__main__":
    main()
