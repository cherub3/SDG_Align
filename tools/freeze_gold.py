"""Freeze the gold set: seeded stratified 20/80 dev/test split + SHA-256 of the gold file, the split file and the
stage-4 clean text of every document. `python tools/freeze_gold.py` writes eval/gold_split.json and eval/GOLD_FROZEN.txt.
`check_frozen()` is called by tools/eval_retrieval.py, which refuses to run on any mismatch.

NOTE: Step 3a (Q3 heading fix) must NOT change the stage-4 clean text; the clean-text hashes below enforce that.
"""
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gold_common as gc  # noqa: E402

SEED = 20261123
DEV_FRACTION = 0.2
GOLD = os.path.join(gc.REPO, "eval", "gold_set.jsonl")
SPLIT = os.path.join(gc.REPO, "eval", "gold_split.json")
FROZEN = os.path.join(gc.REPO, "eval", "GOLD_FROZEN.txt")


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def stratum(it):
    return it["kind"] if it["type"] == "unanswerable" else it["type"]


def make_split(items, seed=SEED, frac=DEV_FRACTION):
    groups = {}
    for it in sorted(items, key=lambda x: x["qid"]):
        groups.setdefault(stratum(it), []).append(it["qid"])
    rng = random.Random(seed)
    split = {}
    for s in sorted(groups):
        ids = groups[s][:]
        rng.shuffle(ids)
        n_dev = max(1, round(frac * len(ids)))
        for i, q in enumerate(ids):
            split[q] = "dev" if i < n_dev else "test"
    return split


def clean_hashes():
    return {n: gc.sha256_text(gc.load_doc(d)["clean"]) for n, d in sorted(gc.doc_names().items())}


def write_frozen():
    items = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    split = make_split(items)
    json.dump({"seed": SEED, "dev_fraction": DEV_FRACTION, "stratified_by": "type (unanswerable by kind)",
               "split": dict(sorted(split.items()))}, open(SPLIT, "w", encoding="utf-8", newline="\n"), indent=1)
    lines = [f"seed={SEED}", f"dev_fraction={DEV_FRACTION}", f"gold_set.jsonl={sha_file(GOLD)}",
             f"gold_split.json={sha_file(SPLIT)}"]
    lines += [f"clean_text:{n}={h}" for n, h in clean_hashes().items()]
    lines += ["hit_rule=same doc_id; chunk [char_start,char_end) in stage-4 clean text overlaps a gold span by >= min(50 chars, 50% of span length)",
              "note=Step 3a (Q3 heading fix) must not change stage-4 clean text; eval_retrieval.py refuses to run if any hash differs."]
    open(FROZEN, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    return split


def check_frozen():
    """Return list of mismatch messages (empty = OK)."""
    exp = dict(l.rstrip("\n").split("=", 1) for l in open(FROZEN, encoding="utf-8") if "=" in l)
    bad = []
    if sha_file(GOLD) != exp["gold_set.jsonl"]:
        bad.append("gold_set.jsonl changed")
    if sha_file(SPLIT) != exp["gold_split.json"]:
        bad.append("gold_split.json changed")
    for n, h in clean_hashes().items():
        if exp.get(f"clean_text:{n}") != h:
            bad.append(f"clean text changed: {n}")
    return bad


if __name__ == "__main__":
    s = write_frozen()
    from collections import Counter
    print(Counter(s.values()))
    print(open(FROZEN, encoding="utf-8").read())
