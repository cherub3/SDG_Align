"""Shared helpers for the Phase 2 gold set: document loading, offsets, paraphrase and hit-rule primitives."""
import hashlib
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTED = os.path.join(REPO, "data", "proposals", "extracted")
CHUNKS = os.path.join(REPO, "data", "proposals", "chunks")
MANIFEST = os.path.join(REPO, "data", "proposals", "manifest.json")


def doc_names():
    """name (file stem) -> doc_id, for documents that have a stage-4 clean text."""
    man = json.load(open(MANIFEST, encoding="utf-8"))
    recs = man if isinstance(man, dict) else {r["doc_id"]: r for r in man}
    out = {}
    for doc, r in recs.items():
        if os.path.exists(os.path.join(EXTRACTED, doc, "clean_text.json")):
            out[os.path.basename(r["source_path"]).replace(".pdf", "")] = doc
    return out


def load_doc(doc_id):
    """Return dict with clean full text, clean page table and raw full text with raw page table."""
    ct = json.load(open(os.path.join(EXTRACTED, doc_id, "clean_text.json"), encoding="utf-8"))
    raw = json.load(open(os.path.join(EXTRACTED, doc_id, "raw_extraction.json"), encoding="utf-8"))
    clean = "".join(p["text"] for p in ct["pages"])
    pages = {p["page_number"]: (p["char_start"], p["char_end"]) for p in ct["pages"]}
    raw_text, raw_pages, pos = [], {}, 0
    for p in raw["pages"]:
        t = p["raw_text"]
        raw_pages[p["page_number"]] = (pos, pos + len(t))
        raw_text.append(t)
        pos += len(t)
    return {"clean": clean, "clean_pages": pages, "raw": "".join(raw_text), "raw_pages": raw_pages}


def chunk_ranges(doc_id):
    ch = json.load(open(os.path.join(CHUNKS, doc_id, "chunks.json"), encoding="utf-8"))["chunks"]
    return [(c["char_start"], c["char_end"]) for c in ch]


def sha256_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def words(t):
    return re.findall(r"[a-z0-9]+", t.lower())


def longest_shared_run(question, quotes):
    """Longest run of consecutive words (case-insensitive, punctuation ignored) shared by the question and any quote."""
    qw = words(question)
    best = 0
    for quote in quotes:
        sw = words(quote)
        grams = {}
        for n in range(1, 13):
            grams[n] = {tuple(sw[i:i + n]) for i in range(len(sw) - n + 1)}
        for n in range(1, 13):
            if any(tuple(qw[i:i + n]) in grams[n] for i in range(len(qw) - n + 1)):
                best = max(best, n)
    return best


def overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def is_hit(chunk_start, chunk_end, gold_start, gold_end):
    """Hit rule (frozen with the gold set): chunk and gold span overlap by at least min(50 chars, 50% of the gold span)."""
    need = min(50, 0.5 * (gold_end - gold_start))
    return overlap(chunk_start, chunk_end, gold_start, gold_end) >= need
