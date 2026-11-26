"""Builds the blind human-labelling kit for the 44 answerable TEST items, both arms (A: single call 2.1.0, B: ADK multi-agent).

Writes eval/human_labels/labelling_sheet.csv (what the labeller sees), eval/human_labels/arm_key.json (code -> arm, kept apart),
eval/human_labels/RUBRIC.txt, and a 10-row relabel sheet (relabel_sheet.csv, relabel_codes.json) for a later self-agreement check.
No model call. Existing result files are only read.

    python tools/build_labelling_kit.py
"""
import csv
import json
import os
import random

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "eval", "human_labels")
SEED = 20261125
RELABEL_N, RELABEL_SEED = 10, 20261126
FIELDS = ["code", "question", "gold_quote", "answer", "label", "note"]
ROWS = {"A": "test_noplanner_v21.jsonl", "B": "test_agents_v1.jsonl"}
LABELS = ("correct", "partial", "wrong", "refused")

# Copied verbatim from reports/PHASE_3_5_REPORT.md section 3 ("Rubric: ...").
RUBRIC = ("correct = all gold-required facts stated correctly; partial = some right, rest missing or declared missing, nothing contradicting gold; "
          "wrong = contradicts gold; refused = exactly NOT_IN_CONTEXT.")


def read_jsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def answer_text(row, arm):
    # For B the stored plain text has the [chunk_id] markers removed, so markers do not reveal the arm.
    return row["response_text_plain"] if arm == "B" else row["response_text"]


def build(seed=SEED):
    gold = {g["qid"]: g for g in read_jsonl(os.path.join(REPO, "eval", "gold_set.jsonl"))}
    split = json.load(open(os.path.join(REPO, "eval", "gold_split.json"), encoding="utf-8"))["split"]
    rows = {arm: {r["qid"]: r for r in read_jsonl(os.path.join(REPO, "eval", "results", f))} for arm, f in ROWS.items()}
    qids = sorted(q for q, g in gold.items() if split[q] == "test" and g["type"] != "unanswerable")
    assert len(qids) == 44 and all(q in rows["A"] and q in rows["B"] for q in qids)
    entries = [(q, arm) for q in qids for arm in ("A", "B")]
    random.Random(seed).shuffle(entries)
    sheet, key = [], {}
    for i, (q, arm) in enumerate(entries, 1):
        code = f"L{i:03d}"
        g = gold[q]
        quote = " || ".join(e["answer_quote"] for e in g["evidence"])
        sheet.append({"code": code, "question": g["question"], "gold_quote": quote, "answer": answer_text(rows[arm][q], arm), "label": "", "note": ""})
        key[code] = {"qid": q, "arm": arm}
    return sheet, key


def relabel_codes(sheet, n=RELABEL_N, seed=RELABEL_SEED):
    """n random codes (fixed seed) to be labelled a second time, later, to measure the labeller's own agreement."""
    return sorted(random.Random(seed).sample([r["code"] for r in sheet], n))


def write_sheet(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    sheet, key = build()
    write_sheet(os.path.join(OUT, "labelling_sheet.csv"), sheet)
    codes = relabel_codes(sheet)
    write_sheet(os.path.join(OUT, "relabel_sheet.csv"), [r for r in sheet if r["code"] in codes])
    json.dump({"seed": RELABEL_SEED, "n": RELABEL_N, "codes": codes,
               "note": "Re-label these rows later, in relabel_sheet.csv, without looking at your first labels."},
              open(os.path.join(OUT, "relabel_codes.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    json.dump({"seed": SEED, "note": "Do not open this file until all 88 labels are filled in. It maps each code to the arm that produced the answer.", "key": key},
              open(os.path.join(OUT, "arm_key.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    open(os.path.join(OUT, "RUBRIC.txt"), "w", encoding="utf-8", newline="\n").write(
        "Label scale (frozen; copied from reports/PHASE_3_5_REPORT.md):\n\n" + RUBRIC + "\n\n"
        "Fill the `label` column of labelling_sheet.csv with exactly one of: " + ", ".join(LABELS) + ". The `note` column is optional and may stay empty.\n"
        "Judge each answer against the gold_quote only (several quotes are separated by ' || '). The same question appears twice with different codes; judge each answer on its own.\n"
        "Do not open arm_key.json until you are finished.\n\n"
        "Amendment 1 (dated 2026-11-25, written before any label was entered):\n"
        "An answer that refuses in free text instead of replying with the exact NOT_IN_CONTEXT is labelled `refused`, with the word `implicit` in the `note` column.\n"
        "Scoring counts it as refused and reports implicit refusals separately. The original definitions above are unchanged.\n\n"
        "Re-labelling: relabel_sheet.csv holds 10 randomly chosen rows (fixed seed, see relabel_codes.json). "
        "Label them again later, without looking at your first labels; the scorer reports your self-agreement.\n")
    print(f"wrote {len(sheet)} rows")


if __name__ == "__main__":
    main()
