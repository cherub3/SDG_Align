"""Verify eval/gold_set.jsonl. Exit code 1 if any ERROR. Usage: python tools/verify_gold.py [gold.jsonl]

ERROR checks: schema; quote verbatim at clean offsets; quote verbatim at raw offsets (or, for table-derived quotes,
every key token present in the raw page); quote absent from every OTHER document; no duplicate / near-duplicate
questions; paraphrased=true items share no run of 4+ consecutive words with their quotes; type structure
(multi_passage = 2+ spans in one doc, cross_document = 2+ docs); quote lies inside chunked text.
REVIEW flags (not errors, reported): quote occurs more than once in its own document; unanswerable absence terms
that co-occur on one page (needs a human look); unanswerable terms found at all.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gold_common as gc  # noqa: E402

TYPES = ("single_fact", "numbers_tables", "multi_passage", "cross_document", "unanswerable")
MIN_PARAPHRASED = 25


def norm_q(q):
    return " ".join(gc.words(q))


def jaccard(a, b):
    a, b = set(gc.words(a)), set(gc.words(b))
    return len(a & b) / max(1, len(a | b))


def main(path):
    items = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    names = gc.doc_names()
    docs = {n: gc.load_doc(d) for n, d in names.items()}
    chunks = {n: gc.chunk_ranges(d) for n, d in names.items()}
    errors, review = [], []

    def err(q, m):
        errors.append(f"{q}: {m}")

    seen = {}
    for it in items:
        q = it.get("qid", "?")
        for f in ("qid", "question", "type"):
            if f not in it:
                err(q, f"missing field {f}")
        if it.get("type") not in TYPES:
            err(q, f"bad type {it.get('type')}")
        nq = norm_q(it.get("question", ""))
        if nq in seen:
            err(q, f"duplicate question of {seen[nq]}")
        seen[nq] = q
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if jaccard(a["question"], b["question"]) >= 0.8:
                err(a["qid"], f"near-duplicate question of {b['qid']} (Jaccard >= 0.8)")

    n_par = 0
    per_doc, per_type, per_kind = collections.Counter(), collections.Counter(), collections.Counter()
    for it in items:
        q, t = it["qid"], it["type"]
        per_type[t] += 1
        if t == "unanswerable":
            per_kind[it.get("kind")] += 1
            if it.get("kind") not in ("near_miss", "off_corpus"):
                err(q, "unanswerable item needs kind near_miss|off_corpus")
            terms = [x.lower() for x in it.get("absence_terms", [])]
            if len(terms) < 3:
                err(q, "need >= 3 absence_terms")
            hits = {}
            for n, d in docs.items():
                low = d["clean"].lower()
                for term in terms:
                    if term in low:
                        hits.setdefault(term, []).append(n)
                for pn, (a, b) in d["clean_pages"].items():
                    pg = low[a:b]
                    k = [term for term in terms if term in pg]
                    if len(k) >= 2:
                        review.append(f"{q}: terms co-occur on {n} p.{pn}: {k}")
            it["_term_hits"] = hits
            continue
        ev = it.get("evidence", [])
        if not ev:
            err(q, "answerable item without evidence")
            continue
        if it.get("paraphrased"):
            n_par += 1
        if t == "multi_passage" and not (len(ev) >= 2 and len({e["doc"] for e in ev}) == 1):
            err(q, "multi_passage needs 2+ spans in exactly one document")
        if t == "cross_document" and len({e["doc"] for e in ev}) < 2:
            err(q, "cross_document needs spans from 2+ documents")
        if t in ("single_fact", "numbers_tables") and len(ev) != 1:
            err(q, f"{t} needs exactly 1 span")
        for e in ev:
            per_doc[e["doc"]] += 1
            quote, d = e["answer_quote"], docs.get(e["doc"])
            if d is None:
                err(q, f"unknown doc {e['doc']}")
                continue
            if not (25 <= len(quote) <= 300) or "\n" in quote:
                err(q, f"quote length/newline rule violated ({len(quote)} chars)")
            if e["clean_start"] is None or d["clean"][e["clean_start"]:e["clean_end"]] != quote:
                err(q, f"quote NOT verbatim at clean offsets ({e['doc']} p.{e['page']})")
                continue
            if e["raw_match"] == "exact":
                if d["raw"][e["raw_start"]:e["raw_end"]] != quote:
                    err(q, "quote NOT verbatim at raw offsets")
            else:
                seg = d["raw"][e["raw_start"]:e["raw_end"]]
                missing = [k for k in e.get("raw_key_tokens", []) if k not in seg]
                if missing:
                    err(q, f"derived quote: key tokens missing from raw page: {missing[:5]}")
                review.append(f"{q}: raw_match=derived on {e['doc']} p.{e['page']} (table-rewritten text)")
            if e["clean_occurrences"] > 1:
                review.append(f"{q}: quote occurs {e['clean_occurrences']}x in its own document {e['doc']}")
            for n, dd in docs.items():
                if n != e["doc"] and quote in dd["clean"]:
                    err(q, f"quote also appears in OTHER document {n} (shared template text)")
            cov = sum(gc.overlap(a, b, e["clean_start"], e["clean_end"]) for a, b in chunks[e["doc"]])
            if cov < 0.5 * (e["clean_end"] - e["clean_start"]):
                err(q, f"quote lies outside chunked text (coverage {cov} chars)")
        if it.get("paraphrased"):
            run = gc.longest_shared_run(it["question"], [e["answer_quote"] for e in ev])
            if run >= 4:
                err(q, f"marked paraphrased but shares a run of {run} consecutive words with a quote")
    if n_par < MIN_PARAPHRASED:
        errors.append(f"paraphrased answerable items: {n_par} < required {MIN_PARAPHRASED}")

    out = ["# verify_gold.py report", "", f"items: {len(items)}  | answerable: {len(items) - per_type['unanswerable']}  "
           f"| paraphrased answerable: {n_par}", f"per type: {dict(per_type)}", f"unanswerable kinds: {dict(per_kind)}",
           f"evidence spans per document: {dict(per_doc)}", ""]
    out.append(f"ERRORS: {len(errors)}")
    out += ["  " + e for e in errors]
    out += ["", f"REVIEW flags: {len(review)}"] + ["  " + r for r in review]
    out += ["", "Unanswerable absence-term hits (term -> documents containing it):"]
    for it in items:
        if it["type"] == "unanswerable":
            out.append(f"  {it['qid']} [{it.get('kind')}] {it['question']}")
            for term in it.get("absence_terms", []):
                out.append(f"      {term!r}: {it['_term_hits'].get(term.lower(), [])}")
    print("\n".join(out))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(gc.REPO, "eval", "gold_set.jsonl")))
