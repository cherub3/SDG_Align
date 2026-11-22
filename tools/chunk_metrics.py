"""Chunk-quality metrics, exactly as defined in reports/evidence/metrics_definitions.md.

Usage:  python tools/chunk_metrics.py <chunks_root> [--out FILE]
        <chunks_root> contains <doc_id>/chunks.json files (e.g. data/proposals/chunks)
Pure functions, standard library only, so the same code measures "before" and "after".
"""
import argparse
import collections
import glob
import json
import os
import re
import statistics
import sys
from typing import Dict, Iterable, List

MIN_CHUNK_CHARS = 300  # = MIN_CHUNK_CHARS in scripts/stage7_chunking.py (frozen in the definitions)

_WS = re.compile(r"\s+")
_END_OK = re.compile(r"[.!?][\"')\]*”’]*$")
_HTML = re.compile(r"</?(mark|br|b|u|i|p|span|div|sup|sub|a|strong|em)\b[^>]*>", re.IGNORECASE)
_FOOTER_ANY = re.compile(r"Page \d+ of \d+")
_FOOTER_LINE = re.compile(r"^(Official Use Only\s*)?Page \d+ of \d+$")
_DOTS = re.compile(r"\.{5,}")
_TOC_HEADING = re.compile(r"^[#*|\s]*table of contents[#*|\s]*$", re.IGNORECASE)
_SEPARATOR_ROW = re.compile(r"^\|?[\s:|-]+\|?$")
_LEAD_MARKUP = re.compile(r"^[#*|\s]+|<mark>|</mark>", re.IGNORECASE)
INSTRUCTION_OPENERS = [
    "provide a brief summary",
    "briefly describe the current situation",
    "if so, please describe",
    "for projects aiming to generate biodiversity benefits",
    "(please upload to the portal",
    "describe how the proposed interventions are aligned",
    'describe how any "investment mobilized"',
    "please provide geo-referenced",
    "please provide justification",
    "please refer to separate file",
    "# gef-8 project identification form",
    "gef-8 project identification form",
]


def norm(text: str) -> str:
    return _WS.sub(" ", text).strip()


def is_fragment(text: str) -> bool:
    return len(text.strip()) < MIN_CHUNK_CHARS


def ends_mid_sentence(text: str) -> bool:
    return not _END_OK.search(text.strip())


def is_boilerplate_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _FOOTER_LINE.match(s) or s.lower() == "official use only":
        return True
    if _DOTS.search(s) or _TOC_HEADING.match(s):
        return True
    stripped = _LEAD_MARKUP.sub("", s).strip().lower()
    stripped_hash = s.lower()
    return any(stripped.startswith(o.lstrip("# ")) or stripped_hash.startswith(o) for o in INSTRUCTION_OPENERS)


def is_boilerplate_chunk(text: str) -> bool:
    total = 0
    bad = 0
    for line in text.split("\n"):
        s = line.strip()
        if not s or _SEPARATOR_ROW.match(s):
            continue
        total += len(s)
        if is_boilerplate_line(s):
            bad += len(s)
    return total > 0 and bad * 2 >= total


def has_table_markup(text: str) -> bool:
    return sum(1 for ln in text.split("\n") if ln.strip().startswith("|")) >= 2


def has_html(text: str) -> bool:
    return bool(_HTML.search(text)) or "&nbsp;" in text


def has_footer(text: str) -> bool:
    return bool(_FOOTER_ANY.search(text))


def chunk_metrics(texts: List[str]) -> Dict:
    n = len(texts)
    groups = collections.Counter(norm(t) for t in texts)
    sizes = [len(t) for t in texts] or [0]
    def share(k): return round(k / n, 4) if n else None
    frag = sum(is_fragment(t) for t in texts)
    mid = sum(ends_mid_sentence(t) for t in texts)
    boiler = sum(is_boilerplate_chunk(t) for t in texts)
    return {
        "chunk_count": n,
        "fragments": frag, "fragment_share": share(frag),
        "duplicate_chunks": sum(v - 1 for v in groups.values() if v > 1),
        "duplicated_groups": sum(1 for v in groups.values() if v > 1),
        "mid_sentence_ending": mid, "mid_sentence_ending_rate": share(mid),
        "table_markup_chunks": sum(has_table_markup(t) for t in texts),
        "html_residue_chunks": sum(has_html(t) for t in texts),
        "footer_residue_chunks": sum(has_footer(t) for t in texts),
        "replacement_char_chunks": sum("�" in t for t in texts),
        "boilerplate_chunks": boiler, "boilerplate_share": share(boiler),
        "size_min": min(sizes), "size_median": int(statistics.median(sizes)), "size_max": max(sizes),
    }


def load_chunks(chunks_root: str) -> List[Dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(chunks_root, "*", "chunks.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        out.extend(d["chunks"] if isinstance(d, dict) else d)
    return out


def main(argv: Iterable[str] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks_root")
    ap.add_argument("--out")
    a = ap.parse_args(list(argv) if argv is not None else None)
    chunks = load_chunks(a.chunks_root)
    result = chunk_metrics([c["text"] for c in chunks])
    text = json.dumps(result, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
