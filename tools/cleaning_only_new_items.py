"""Cleaning-only comparison, step 1: find the passages in retrieval_after_5doc.json that no judge has labelled yet.

retrieval_after_5doc.json is the 'after' pipeline (same chunks, same local embedder) retrieved over an index that holds only
the original 5 documents, so the jaguar document cannot contribute. Passages already in the judging packet keep their
adjudicated labels; the rest are written to judging/packet_cleaning_only_new.jsonl for a fresh isolated judge.
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(REPO, "reports", "evidence")
J = os.path.join(EV, "judging")


def norm(t):
    return " ".join(t.split())


def main():
    known = {}
    for line in open(os.path.join(J, "packet.jsonl"), encoding="utf-8"):
        p = json.loads(line)
        known[(p["question_no"], norm(p["text"]))] = p["id"]
    a5 = json.load(open(os.path.join(EV, "retrieval_after_5doc.json"), encoding="utf-8"))
    new = {}
    for r in a5["results"]:
        for t in r["top5"]:
            k = (r["n"], norm(t["text"]))
            if k not in known and k not in new:
                new[k] = {"id": "C%04d" % (len(new) + 1), "question_no": r["n"], "question": r["question"], "text": t["text"]}
    with open(os.path.join(J, "packet_cleaning_only_new.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for item in new.values():
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print("passages in the 5-doc 'after' top-5:", sum(len(r["top5"]) for r in a5["results"]),
          "| already labelled:", sum(len(r["top5"]) for r in a5["results"]) - len(new), "| new:", len(new))


if __name__ == "__main__":
    main()
