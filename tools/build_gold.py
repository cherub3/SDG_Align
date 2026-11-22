"""Turn the drafter's JSON (question + doc name + page + quote) into eval/gold_set.jsonl with offsets computed BY SCRIPT.

Usage: python tools/build_gold.py <draft.json> <out.jsonl>
The drafter's numbers are never trusted: offsets come from str.find on the stage-4 clean text and the raw extracted text.
Quotes that cannot be located are written with clean_start = null so verify_gold.py reports them.
Split assignment is NOT done here (it happens once, at freeze time, in tools/freeze_gold.py).
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gold_common as gc  # noqa: E402


def locate(text, quote, page_range):
    """Find quote, preferring the stated page. Returns (start, end, n_occurrences_in_doc) or (None, None, 0)."""
    n = text.count(quote)
    if n == 0:
        return None, None, 0
    if page_range:
        i = text.find(quote, page_range[0])
        if i != -1 and i + len(quote) <= page_range[1]:
            return i, i + len(quote), n
    i = text.find(quote)
    return i, i + len(quote), n


def key_tokens(quote):
    """Digits and long words used to check a 'derived' (table-rewritten) quote against the raw page."""
    return sorted({t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9.,%$]*", quote) if any(c.isdigit() for c in t) or len(t) >= 7})


def main(draft, out):
    names = gc.doc_names()
    docs = {n: gc.load_doc(d) for n, d in names.items()}
    items = json.load(open(draft, encoding="utf-8"))
    rows = []
    for it in items:
        row = {k: v for k, v in it.items() if k != "evidence"}
        if it["type"] != "unanswerable":
            ev_out = []
            for ev in it["evidence"]:
                d = docs[ev["doc"]]
                q = ev["quote"]
                cs, ce, n = locate(d["clean"], q, d["clean_pages"].get(ev["page"]))
                rs, re_, rn = locate(d["raw"], q, d["raw_pages"].get(ev["page"]))
                e = {"doc": ev["doc"], "doc_id": names[ev["doc"]], "page": ev["page"], "answer_quote": q,
                     "clean_start": cs, "clean_end": ce, "clean_occurrences": n}
                if rs is not None:
                    e.update(raw_start=rs, raw_end=re_, raw_match="exact")
                else:
                    pr = d["raw_pages"].get(ev["page"], (None, None))
                    e.update(raw_start=pr[0], raw_end=pr[1], raw_match="derived", raw_key_tokens=key_tokens(q))
                ev_out.append(e)
            row["evidence"] = ev_out
        rows.append(row)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    miss = sum(1 for r in rows for e in r.get("evidence", []) if e["clean_start"] is None)
    print("items:", len(rows), "| evidence spans not found in clean text:", miss)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
