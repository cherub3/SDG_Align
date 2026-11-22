"""Stage 7 — Semantic Chunking.

Reads clean_text.json (Stage 4/5 output) and metadata.json (Stage 6 output),
both read-only, and produces a deterministic chunk corpus: chunks.json (one
entry per chunk, structural chunk_ids) and chunk_validation_report.json
(always written, even on FAIL).

Never reopens PDFs. Never reads raw_extraction.json. Never modifies
clean_text.json or metadata.json. No AI, no embeddings, no retrieval,
no ranking — purely deterministic segmentation of already-structured text.
has_table_content is always False (no table-region signal is available at
this stage). See docs/architecture/stage7_chunking.md for the pipeline
order and design rationale.
"""

import sys
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from src.ingestion_types import ManifestRecord, DocumentStatus
from src.stage_summary import StageRun, StageSummary, cli_main

EXTRACTED_DIR = Path("data/proposals/extracted")
CHUNKS_DIR = Path("data/proposals/chunks")

CHUNKING_PIPELINE_VERSION = "1.0.0"   # independent of the general PIPELINE_VERSION

MIN_CHUNK_CHARS = 300
TARGET_CHUNK_CHARS = 1500
MAX_CHUNK_CHARS = 3000

HEADING_LINE_PREFIX_TOLERANCE = 20

APPENDIX_RE = re.compile(r'^(APPENDIX|APPENDICES|ANNEX|ANNEXES)\b', re.IGNORECASE)
REFERENCES_RE = re.compile(r'^(REFERENCES|BIBLIOGRAPHY|WORKS CITED|LITERATURE)\b', re.IGNORECASE)

PARAGRAPH_RE = re.compile(r'\n\n+')
SUBHEADING_RE = re.compile(r'^#{1,6}\s+.+$', re.MULTILINE)
LIST_ITEM_RE = re.compile(r'^(?:[-*]\s+|\d+\.\s+)', re.MULTILINE)
SENTENCE_RE = re.compile(r'[.!?]\s+')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage7_chunking")

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"


def _finding(severity: str, code: str, message: str, detail: Any = None) -> Dict:
    f: Dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if detail is not None:
        f["detail"] = detail
    return f


# ===========================================================================
# STEP 1 — deterministic intra-page heading offset recovery
# ===========================================================================

def resolve_heading_offsets(clean_text: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Locates each section_tree heading's exact absolute char offset within its start_page
    via str.find(), falling back to the page's char_start when no match is found. Returns
    (resolved, findings) with resolved offsets clamped to be non-decreasing."""
    pages_by_number = {p["page_number"]: p for p in clean_text.get("pages", [])}
    section_tree = clean_text.get("section_tree", [])
    cursor_by_page: Dict[int, int] = {}
    resolved: List[Dict] = []
    findings: List[Dict] = []
    prev_start = 0

    def _append(candidate: int, recovered: bool) -> None:
        nonlocal prev_start
        clamped = max(candidate, prev_start)
        resolved.append({"absolute_start": clamped, "recovered": recovered})
        prev_start = clamped

    for section in section_tree:
        start_page = section.get("start_page")
        title = section.get("title") or ""
        page = pages_by_number.get(start_page)

        if page is None:
            _append(prev_start, False)
            findings.append(_finding(
                SEVERITY_WARNING, "WARNING_HEADING_OFFSET_NOT_RECOVERED",
                f"section '{section.get('section_id')}': start_page {start_page} not found in clean_text",
                {"section_id": section.get("section_id")},
            ))
            continue

        fallback_start = page["char_start"]
        if not title:
            _append(fallback_start, False)
            continue

        page_text = page.get("text", "")
        cursor = cursor_by_page.get(start_page, 0)
        idx = page_text.find(title, cursor)

        if idx == -1:
            _append(fallback_start, False)
            findings.append(_finding(
                SEVERITY_WARNING, "WARNING_HEADING_OFFSET_NOT_RECOVERED",
                f"section '{section.get('section_id')}': title not found verbatim on page {start_page}",
                {"section_id": section.get("section_id")},
            ))
            continue

        line_start = page_text.rfind("\n", 0, idx) + 1
        line_end = page_text.find("\n", idx)
        if line_end == -1:
            line_end = len(page_text)
        line_len = line_end - line_start

        if line_len > len(title) + HEADING_LINE_PREFIX_TOLERANCE:
            _append(fallback_start, False)
            findings.append(_finding(
                SEVERITY_WARNING, "WARNING_HEADING_OFFSET_NOT_RECOVERED",
                f"section '{section.get('section_id')}': matched line implausibly long, treated as false positive",
                {"section_id": section.get("section_id")},
            ))
            continue

        absolute_start = page["char_start"] + line_start
        _append(absolute_start, True)
        cursor_by_page[start_page] = idx + len(title)

    return resolved, findings


# ===========================================================================
# STEP 2 — connected-chain span construction
# ===========================================================================

def _offset_to_page(pages_sorted: List[Dict], offset: int) -> int:
    """Maps an absolute char offset to the page_number containing it."""
    for p in pages_sorted:
        if p["char_start"] <= offset < p["char_end"]:
            return p["page_number"]
    if not pages_sorted:
        return 1
    if offset <= pages_sorted[0]["char_start"]:
        return pages_sorted[0]["page_number"]
    return pages_sorted[-1]["page_number"]


def _walk_ancestors(section: Dict, by_id: Dict[str, Dict]) -> List[str]:
    """Returns the root-to-leaf section_id chain via parent_section, cycle-guarded."""
    chain: List[str] = []
    seen: set = set()
    cur: Optional[Dict] = section
    while cur is not None:
        sid = cur.get("section_id")
        if sid in seen:
            break
        seen.add(sid)
        chain.append(sid)
        parent_id = cur.get("parent_section")
        cur = by_id.get(parent_id) if parent_id else None
    chain.reverse()
    return chain


def build_section_spans(clean_text: Dict, resolved: List[Dict]) -> List[Dict]:
    """Builds one span per section_tree entry (plus a preamble span), chaining each span's
    char_end to the next span's resolved char_start for exact coverage. Disambiguates
    duplicate section_ids into distinct anchor_section_ids."""
    section_tree = clean_text.get("section_tree", [])
    full_len = clean_text.get("full_text_char_count", 0)
    pages_sorted = sorted(clean_text.get("pages", []), key=lambda p: p["page_number"])

    if full_len == 0:
        return []

    by_id = {s["section_id"]: s for s in section_tree}
    anchor_seen: Dict[str, int] = defaultdict(int)

    spans: List[Dict] = []

    first_start = resolved[0]["absolute_start"] if section_tree else full_len
    if first_start > 0:
        spans.append({
            "char_start": 0,
            "char_end": first_start,
            "section_ids": [],
            "anchor_section_id": "preamble",
            "ancestor_section_ids": [],
            "heading_path": [],
            "degenerate": first_start <= 0,
        })

    for i, section in enumerate(section_tree):
        start = resolved[i]["absolute_start"]
        end = resolved[i + 1]["absolute_start"] if i + 1 < len(section_tree) else full_len
        degenerate = end <= start
        if degenerate:
            end = start

        sid = section.get("section_id")
        anchor_seen[sid] += 1
        n = anchor_seen[sid]
        anchor = sid if n == 1 else f"{sid}-dup{n}"

        ancestor_ids = _walk_ancestors(section, by_id)
        heading_path = [by_id[a]["title"] for a in ancestor_ids if a in by_id]

        spans.append({
            "char_start": start,
            "char_end": end,
            "section_ids": [sid],
            "anchor_section_id": anchor,
            "ancestor_section_ids": ancestor_ids,
            "heading_path": heading_path,
            "degenerate": degenerate,
        })

    for span in spans:
        span["is_appendix"] = any(APPENDIX_RE.match(t or "") for t in span["heading_path"])
        span["is_references"] = any(REFERENCES_RE.match(t or "") for t in span["heading_path"])
        span["page_start"] = _offset_to_page(pages_sorted, span["char_start"])
        end_probe = max(span["char_start"], span["char_end"] - 1)
        span["page_end"] = _offset_to_page(pages_sorted, end_probe)

    return spans


# ===========================================================================
# STEP 3 — oversized span splitting
# ===========================================================================

_SENTENCE_END_RE = re.compile(r"[.!?][\"')\]*”’]*\s*$")
LINE_RE = re.compile(r"\n")


def _ends_sentence(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text[-12:]))


def _split_text_at_boundaries(text: str, max_len: int, target_len: int) -> List[Tuple[int, int]]:
    """Splits text into (start, end) offset pairs <= max_len. A cut is chosen, in order, at a
    paragraph / sub-heading / list-item / sentence boundary where the text before it ends on
    a sentence terminator and the piece is at least MIN_CHUNK_CHARS; else at any such boundary
    with a piece of that size; else at any such boundary; else at a line break; else at
    max_len. Within a tier the cut is as close below target_len as possible."""
    if len(text) <= max_len:
        return [(0, len(text))]

    tiers = [
        [m.end() for m in PARAGRAPH_RE.finditer(text)],
        [m.start() for m in SUBHEADING_RE.finditer(text)],
        [m.start() for m in LIST_ITEM_RE.finditer(text)],
        [m.end() for m in SENTENCE_RE.finditer(text)],
    ]
    line_points = [m.end() for m in LINE_RE.finditer(text)]

    def pick(candidates: List[int], pos: int) -> Optional[int]:
        if not candidates:
            return None
        under_target = [p for p in candidates if p - pos <= target_len]
        return max(under_target) if under_target else min(candidates, key=lambda p: abs((p - pos) - target_len))

    offsets: List[Tuple[int, int]] = []
    pos = 0
    n = len(text)
    while pos < n:
        remaining = n - pos
        if remaining <= max_len:
            offsets.append((pos, n))
            break

        window_end = pos + max_len
        in_window = [[p for p in pts if pos < p <= window_end] for pts in tiers]
        # 1. a boundary after which the text so far ends on a sentence terminator, and the piece
        #    is not itself a fragment; 2. any tier boundary, piece not a fragment; 3. any tier
        #    boundary; 4. a line break (keeps a table row whole); 5. fixed length.
        attempts = (
            [[p for p in c if p - pos >= MIN_CHUNK_CHARS and _ends_sentence(text[max(0, p - 12):p])] for c in in_window],
            [[p for p in c if p - pos >= MIN_CHUNK_CHARS] for c in in_window],
            in_window,
        )
        cut = None
        for tier_candidates in attempts:
            for candidates in tier_candidates:
                cut = pick(candidates, pos)
                if cut is not None:
                    break
            if cut is not None:
                break
        if cut is None:
            cut = pick([p for p in line_points if pos < p <= window_end], pos)
        if cut is None:
            cut = window_end

        offsets.append((pos, cut))
        pos = cut

    return offsets


def split_oversized_spans(spans: List[Dict], full_text: str) -> List[Dict]:
    """Splits any span exceeding MAX_CHUNK_CHARS via _split_text_at_boundaries; pieces
    inherit their originating span's metadata and never cross a section boundary."""
    result: List[Dict] = []

    for span in spans:
        text = full_text[span["char_start"]:span["char_end"]]
        if len(text) <= MAX_CHUNK_CHARS:
            result.append(dict(span))
            continue

        pieces = _split_text_at_boundaries(text, MAX_CHUNK_CHARS, TARGET_CHUNK_CHARS)
        for (s, e) in pieces:
            new_span = dict(span)
            new_span["char_start"] = span["char_start"] + s
            new_span["char_end"] = span["char_start"] + e
            new_span["degenerate"] = False
            result.append(new_span)

    return result


def _recompute_page_range(span: Dict, pages_sorted: List[Dict]) -> None:
    span["page_start"] = _offset_to_page(pages_sorted, span["char_start"])
    end_probe = max(span["char_start"], span["char_end"] - 1)
    span["page_end"] = _offset_to_page(pages_sorted, end_probe)


# ===========================================================================
# STEP 4 — undersized span merging
# ===========================================================================

def _span_len(span: Dict) -> int:
    return span["char_end"] - span["char_start"]


def _same_branch(a: Dict, b: Dict) -> bool:
    a_top = a["ancestor_section_ids"][0] if a["ancestor_section_ids"] else None
    b_top = b["ancestor_section_ids"][0] if b["ancestor_section_ids"] else None
    return a_top == b_top


def _crosses_appendix_boundary(a: Dict, b: Dict) -> bool:
    return a.get("is_appendix") != b.get("is_appendix") or a.get("is_references") != b.get("is_references")


def _combine(a: Dict, b: Dict) -> Dict:
    combined_ids = list(a["section_ids"])
    lead = {"lead_end": a["lead_end"]} if a.get("lead_end") else {}
    for sid in b["section_ids"]:
        if sid not in combined_ids:
            combined_ids.append(sid)
    return {
        "char_start": a["char_start"],
        "char_end": b["char_end"],
        "section_ids": combined_ids,
        "anchor_section_id": a["anchor_section_id"],
        "ancestor_section_ids": a["ancestor_section_ids"],
        "heading_path": a["heading_path"],
        "degenerate": a.get("degenerate", False) and b.get("degenerate", False),
        "is_appendix": a.get("is_appendix", False) or b.get("is_appendix", False),
        "is_references": a.get("is_references", False) or b.get("is_references", False),
        "page_start": a.get("page_start"),
        "page_end": b.get("page_end"),
        **lead,
    }


def _is_heading_only(span: Dict, full_text: str) -> bool:
    """True if the span holds only heading lines (Markdown '#' lines or ALL-CAPS titles): a
    heading with no body belongs with the content that follows it, not with the text before."""
    lines = [ln.strip() for ln in full_text[span["char_start"]:span["char_end"]].splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith("#") or ln.isupper() for ln in lines)


def _combine_into_next(a: Dict, b: Dict) -> Dict:
    """Merges a body-less heading span `a` into the span `b` that follows it. The result is
    labelled (anchor, ancestors, heading path) as `b`, because `b` holds the content."""
    combined = _combine(b, b)
    combined["char_start"] = a["char_start"]
    combined["section_ids"] = list(a["section_ids"]) + [s for s in b["section_ids"] if s not in a["section_ids"]]
    combined["degenerate"] = a.get("degenerate", False) and b.get("degenerate", False)
    combined["page_start"] = a.get("page_start")
    combined["page_end"] = b.get("page_end")
    combined["lead_end"] = a["char_end"]   # [char_start, lead_end) is merged-in heading text: metadata, not embedded
    return combined


def merge_undersized_spans(spans: List[Dict], full_text: Optional[str] = None) -> List[Dict]:
    """Merges spans below MIN_CHUNK_CHARS into a neighbour, never exceeding MAX_CHUNK_CHARS and
    never crossing an appendix/references boundary.

    1. With `full_text`: a body-less heading span merges forward into the content that follows
       it, even across a top-level branch (a heading must stay with its own content).
    2. The first span merges forward; any other undersized span merges backward into the
       previous span of the same top-level branch.
    3. Anything still undersized merges forward into the next span of the same branch.
    The pass in 3 runs until nothing changes."""
    if not spans:
        return spans

    work = [dict(s) for s in spans]

    if full_text is not None:
        i = 0
        while i < len(work) - 1:
            a, b = work[i], work[i + 1]
            if (_span_len(a) < MIN_CHUNK_CHARS and _is_heading_only(a, full_text)
                    and _span_len(a) + _span_len(b) <= MAX_CHUNK_CHARS
                    and not _crosses_appendix_boundary(a, b)):
                work[i:i + 2] = [_combine_into_next(a, b)]
            else:
                i += 1

    # First-span-forward exception: the very first span has no predecessor to
    # merge backward into, so it merges forward instead. Not gated on _same_branch: a
    # preamble span (no section of its own) merging into the document's
    # first real section is not a branch crossing in any meaningful sense.
    if len(work) >= 2 and _span_len(work[0]) < MIN_CHUNK_CHARS:
        a, b = work[0], work[1]
        combined_len = _span_len(a) + _span_len(b)
        if combined_len <= MAX_CHUNK_CHARS and not _crosses_appendix_boundary(a, b):
            work[1] = _combine(a, b)
            work.pop(0)

    if not work:
        return work

    result: List[Dict] = [work[0]]
    for span in work[1:]:
        if _span_len(span) < MIN_CHUNK_CHARS and result:
            prev = result[-1]
            combined_len = _span_len(prev) + _span_len(span)
            eligible = prev.get("degenerate") or span.get("degenerate") or _same_branch(prev, span)
            if combined_len <= MAX_CHUNK_CHARS and eligible and not _crosses_appendix_boundary(prev, span):
                result[-1] = _combine(prev, span)
                continue
        result.append(span)

    changed = True
    while changed:
        changed = False
        for i in range(len(result) - 1):
            a, b = result[i], result[i + 1]
            if _span_len(a) >= MIN_CHUNK_CHARS:
                continue
            eligible = a.get("degenerate") or b.get("degenerate") or _same_branch(a, b)
            if (eligible and _span_len(a) + _span_len(b) <= MAX_CHUNK_CHARS
                    and not _crosses_appendix_boundary(a, b)):
                result[i:i + 2] = [_combine(a, b)]
                changed = True
                break

    return result


def _norm_text(text: str) -> str:
    return " ".join(text.split())


def drop_duplicate_spans(spans: List[Dict], full_text: str) -> Tuple[List[Dict], List[Tuple[int, int]]]:
    """Drops a span whose text (whitespace-normalised, case kept) equals an earlier span's text
    in the same document; the first occurrence stays. Returns (kept spans, dropped (start, end)
    ranges). The ranges are reported so chunk validation can still prove that every character
    of the document is either in a chunk or in a recorded duplicate."""
    seen = set()
    kept: List[Dict] = []
    dropped: List[Tuple[int, int]] = []
    for s in spans:
        key = _norm_text(full_text[s["char_start"]:s["char_end"]])
        if key and key in seen:
            dropped.append((s["char_start"], s["char_end"]))
            continue
        seen.add(key)
        kept.append(s)
    return kept, dropped


# ===========================================================================
# STEP 5 — structural chunk identity
# ===========================================================================

def _is_markdown_heading_only(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith("#") for ln in lines)


def drop_heading_only_spans(spans: List[Dict], full_text: str) -> Tuple[List[Dict], List[Tuple[int, int]]]:
    """Drops a span below MIN_CHUNK_CHARS whose every non-empty line is a Markdown heading (for
    example '#### ANNEX A: FINANCING TABLES' with nothing after it). Such a span holds no body
    text, so it can never answer a question. It survives the merge pass only when merging it
    forward would cross an appendix boundary or the size limit. A span with any body line is kept.
    Returns (kept spans, dropped (start, end) ranges) for coverage validation."""
    kept: List[Dict] = []
    dropped: List[Tuple[int, int]] = []
    for s in spans:
        text = full_text[s["char_start"]:s["char_end"]]
        if _span_len(s) < MIN_CHUNK_CHARS and _is_markdown_heading_only(text):
            dropped.append((s["char_start"], s["char_end"]))
        else:
            kept.append(s)
    return kept, dropped


def assign_chunk_ids(spans: List[Dict], doc_id: str) -> List[Dict]:
    """Assigns structural chunk_id, chunk_index_within_section, and section_chunk_count
    over the final (post split+merge) span set."""
    totals: Dict[str, int] = defaultdict(int)
    for s in spans:
        totals[s["anchor_section_id"]] += 1

    seen: Dict[str, int] = defaultdict(int)
    for s in spans:
        anchor = s["anchor_section_id"]
        idx = seen[anchor]
        seen[anchor] += 1
        s["chunk_index_within_section"] = idx
        s["section_chunk_count"] = totals[anchor]
        s["chunk_id"] = f"{doc_id}_{anchor}_{idx}"

    return spans


# ===========================================================================
# STEP 6 — chunk record assembly
# ===========================================================================

# ---------------------------------------------------------------------------
# Phase 2 step 3a: text a chunk starts with that is NOT embedded (heading lines merged in front of the content, and
# the form's own prompt sentences). The prompts are the paragraphs the GEF PIF template prints in every proposal
# (found verbatim in all 6 corpus documents); the list is explicit so each rule is reviewable. It was read from the
# same 6 documents it is measured on, so it can overfit; a new template needs a new list.
# ---------------------------------------------------------------------------
EMBED_STRIP_MODE = os.environ.get("SDG_EMBED_STRIP", "merged+template")   # off | merged | merged+template | headings+template
TEMPLATE_PROMPT_OPENERS = (
    "this section asks for a theory of change",
    "does the gef agency expect to play an execution role",
    "confirm if any country policies that might contradict",
    "we confirm that",
    "and if so, has its role been described",
    "**indicative trust fund resources requested by agency",
    "**(pif level) attach agency safeguard screen form",
)
MIN_EMBED_CHARS = 100
_LINE_RE = re.compile(chr(91) + "^" + chr(92) + "n]+" + chr(92) + "n*")   # a non-empty line plus its trailing newlines


def _is_template_prompt(line: str) -> bool:
    low = line.strip().lower()
    return any(low.startswith(o) for o in TEMPLATE_PROMPT_OPENERS)


def _is_heading_line(line: str) -> bool:
    line = line.strip()
    return line.startswith("#") or (0 < len(line) <= 120 and line.isupper())


def embed_prefix_end(text: str, lead_rel: int, mode: Optional[str] = None) -> int:
    """Character index in `text` where the embedded text starts (0 = embed everything)."""
    mode = mode or EMBED_STRIP_MODE
    if mode == "off":
        return 0
    cut = lead_rel if lead_rel < len(text) else 0
    if mode != "merged":
        pos = cut
        for m in re.finditer(_LINE_RE, text[cut:]):
            line, end = m.group().strip(), cut + m.end()
            if _is_template_prompt(line):
                cut = pos = end
            elif _is_heading_line(line):
                if mode == "headings+template":
                    cut = pos = end
            else:
                break
    if len(text[cut:].strip()) < MIN_EMBED_CHARS:           # never strip a chunk down to (almost) nothing
        cut = lead_rel if len(text[lead_rel:].strip()) >= MIN_EMBED_CHARS else 0
    return cut


def assemble_chunk_records(
    spans: List[Dict],
    doc_id: str,
    full_text: str,
    metadata: Dict,
) -> List[Dict]:
    """Builds the final chunks.json chunk records per the chunk schema.
    has_table_content is always False (no table-region signal is available at this stage)."""
    classification = metadata.get("classification", {})
    chunks: List[Dict] = []
    for s in spans:
        text = full_text[s["char_start"]:s["char_end"]]
        lead_rel = max(0, (s.get("lead_end") or s["char_start"]) - s["char_start"])
        cut = embed_prefix_end(text, lead_rel)
        extra: Dict = {}
        if cut:
            # The leading heading / form-prompt lines stay in `text` (display, citations, offsets) but are not embedded.
            extra = {"unembedded_prefix": text[:cut].strip(), "embed_text": text[cut:]}
        chunks.append({
            **extra,
            "chunk_id": s["chunk_id"],
            "doc_id": doc_id,
            "text": full_text[s["char_start"]:s["char_end"]],
            "char_start": s["char_start"],
            "char_end": s["char_end"],
            "page_start": s["page_start"],
            "page_end": s["page_end"],
            "section_ids": s["section_ids"],
            "ancestor_section_ids": s["ancestor_section_ids"],
            "heading_path": s["heading_path"],
            "chunk_index_within_section": s["chunk_index_within_section"],
            "section_chunk_count": s["section_chunk_count"],
            "is_appendix": s["is_appendix"],
            "is_references": s["is_references"],
            "has_table_content": False,
            "category": classification.get("category"),
            "doc_type": classification.get("doc_type"),
            "title": metadata.get("title"),
        })
    return chunks


# ===========================================================================
# STEP 7 — chunk-set validation
# ===========================================================================

def validate_chunks(chunks: List[Dict], clean_text: Dict,
                    dropped_ranges: Sequence[Tuple[int, int]] = ()) -> Tuple[List[Dict], str]:
    """Runs the full chunk-set validation suite (no fail-fast) and returns
    (findings, outcome), where outcome is FAIL/WARNING/PASS by finding severity."""
    findings: List[Dict] = []
    full_len = clean_text.get("full_text_char_count", 0)
    section_ids_known = {s.get("section_id") for s in clean_text.get("section_tree", [])}

    # CHUNK_NON_EMPTY (Critical)
    for c in chunks:
        if not (c["text"] or "").strip():
            findings.append(_finding(SEVERITY_ERROR, "CHUNK_NON_EMPTY",
                                      f"chunk {c['chunk_id']} has empty text"))

    # CHUNK_OFFSETS_VALID (Critical)
    for c in chunks:
        offsets_in_range = 0 <= c["char_start"] <= c["char_end"] <= full_len
        text_matches_offsets = len(c["text"]) == (c["char_end"] - c["char_start"])
        if not (offsets_in_range and text_matches_offsets):
            findings.append(_finding(SEVERITY_ERROR, "CHUNK_OFFSETS_VALID",
                                      f"chunk {c['chunk_id']} has invalid offsets",
                                      {"char_start": c["char_start"], "char_end": c["char_end"],
                                       "text_length": len(c["text"])}))

    # CHUNK_IDS_UNIQUE (Critical)
    ids = [c["chunk_id"] for c in chunks]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        findings.append(_finding(SEVERITY_ERROR, "CHUNK_IDS_UNIQUE",
                                  "duplicate chunk_id detected", {"duplicates": dupes}))

    # CHUNK_NO_OVERLAP + CHUNK_COVERAGE_EXACT (Critical)
    ordered = sorted(chunks, key=lambda c: c["char_start"])
    overlap_found = False
    for prev, cur in zip(ordered, ordered[1:]):
        if cur["char_start"] < prev["char_end"]:
            overlap_found = True
            findings.append(_finding(SEVERITY_ERROR, "CHUNK_NO_OVERLAP",
                                      f"chunks {prev['chunk_id']} and {cur['chunk_id']} overlap"))

    if not overlap_found:
        skip = {}
        for s_, e_ in dropped_ranges:
            skip[s_] = e_
        def _skip_dropped(pos: int) -> int:
            while pos in skip:
                pos = skip.pop(pos)
            return pos
        cursor = 0
        gap_or_mismatch = False
        for c in ordered:
            cursor = _skip_dropped(cursor)
            if c["char_start"] != cursor:
                gap_or_mismatch = True
                break
            cursor = c["char_end"]
        cursor = _skip_dropped(cursor)
        if cursor != full_len:
            gap_or_mismatch = True
        if gap_or_mismatch:
            findings.append(_finding(SEVERITY_ERROR, "CHUNK_COVERAGE_EXACT",
                                      "chunk ranges do not exactly cover [0, full_text_char_count)"))
    else:
        findings.append(_finding(SEVERITY_ERROR, "CHUNK_COVERAGE_EXACT",
                                  "coverage cannot be verified while overlaps are present"))

    # CHUNK_PAGE_RANGE_VALID (Critical)
    valid_pages = {p["page_number"] for p in clean_text.get("pages", [])}
    for c in chunks:
        if c["page_start"] > c["page_end"] or c["page_start"] not in valid_pages or c["page_end"] not in valid_pages:
            findings.append(_finding(SEVERITY_ERROR, "CHUNK_PAGE_RANGE_VALID",
                                      f"chunk {c['chunk_id']} has an invalid page range",
                                      {"page_start": c["page_start"], "page_end": c["page_end"]}))

    # CHUNK_SIZE_WITHIN_MAX (Critical)
    for c in chunks:
        if len(c["text"]) > MAX_CHUNK_CHARS:
            findings.append(_finding(SEVERITY_ERROR, "CHUNK_SIZE_WITHIN_MAX",
                                      f"chunk {c['chunk_id']} exceeds MAX_CHUNK_CHARS",
                                      {"length": len(c["text"])}))

    # CHUNK_SIZE_ABOVE_MIN (Recoverable)
    for c in chunks:
        if len(c["text"]) < MIN_CHUNK_CHARS:
            findings.append(_finding(SEVERITY_WARNING, "CHUNK_SIZE_ABOVE_MIN",
                                      f"chunk {c['chunk_id']} is below MIN_CHUNK_CHARS and had no eligible merge target",
                                      {"length": len(c["text"])}))

    # CHUNK_HEADING_PATH_VALID (Recoverable)
    for c in chunks:
        for sid in c["section_ids"]:
            if sid not in section_ids_known:
                findings.append(_finding(SEVERITY_WARNING, "CHUNK_HEADING_PATH_VALID",
                                          f"chunk {c['chunk_id']} references unknown section_id '{sid}'"))
                break

    has_error = any(f["severity"] == SEVERITY_ERROR for f in findings)
    has_warning = any(f["severity"] == SEVERITY_WARNING for f in findings)
    outcome = "FAIL" if has_error else ("WARNING" if has_warning else "PASS")
    return findings, outcome


def _compute_stats(chunks: List[Dict]) -> Dict:
    if not chunks:
        return {
            "coverage_percent": 100.0,
            "avg_chunk_chars": 0,
            "largest_chunk_chars": 0,
            "smallest_chunk_chars": 0,
            "chunks_per_section": {},
        }
    lengths = [len(c["text"]) for c in chunks]
    chunks_per_section: Dict[str, int] = defaultdict(int)
    for c in chunks:
        # anchor is not stored directly on the chunk record; recover it from section_ids/preamble
        key = c["section_ids"][0] if c["section_ids"] else "preamble"
        chunks_per_section[key] += 1
    return {
        "coverage_percent": 100.0,
        "avg_chunk_chars": sum(lengths) / len(lengths),
        "largest_chunk_chars": max(lengths),
        "smallest_chunk_chars": min(lengths),
        "chunks_per_section": dict(chunks_per_section),
    }


# ===========================================================================
# WRITERS
# ===========================================================================

def _write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def write_chunks(doc_id: str, chunks: List[Dict]) -> Path:
    out_path = CHUNKS_DIR / doc_id / "chunks.json"
    _write_json(out_path, {
        "doc_id": doc_id,
        "chunking_pipeline_version": CHUNKING_PIPELINE_VERSION,
        "generated_at": get_now_iso(),
        "chunk_count": len(chunks),
        "chunks": chunks,
    })
    return out_path


def write_chunk_validation_report(doc_id: str, findings: List[Dict], outcome: str, chunks: List[Dict],
                                  dropped_ranges: Sequence[Tuple[int, int]] = ()) -> Path:
    error_count = sum(1 for f in findings if f["severity"] == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f["severity"] == SEVERITY_WARNING)
    out_path = CHUNKS_DIR / doc_id / "chunk_validation_report.json"
    _write_json(out_path, {
        "doc_id": doc_id,
        "chunking_pipeline_version": CHUNKING_PIPELINE_VERSION,
        "generated_at": get_now_iso(),
        "overall_status": outcome,
        "summary": {
            "pass": len(findings) - error_count - warning_count if not findings else max(0, 0),
            "warning": warning_count,
            "fail": error_count,
        },
        "findings": findings,
        "dropped_duplicate_ranges": [list(r) for r in dropped_ranges],
        "stats": _compute_stats(chunks),
    })
    return out_path


# ===========================================================================
# MANIFEST UPDATER — the ONLY function allowed to modify manifest.json
# ===========================================================================

def update_manifest(
    record: ManifestRecord,
    outcome: str,
    chunk_validation_report_path: Path,
    chunks_path: Optional[Path],
    completed_at: str,
) -> None:
    """Updates ManifestRecord fields for Stage 7 (FAIL -> QUARANTINED with
    FATAL_CHUNKING_FAILED; otherwise status is left unchanged). The only function
    in this module that modifies manifest state."""
    record.pipeline_version = PIPELINE_VERSION
    record.completed_at = completed_at
    record.artifact_paths["chunk_validation_report"] = str(chunk_validation_report_path).replace("\\", "/")

    if outcome in ("PASS", "WARNING"):
        record.error_code = None
        if chunks_path:
            record.artifact_paths["chunks"] = str(chunks_path).replace("\\", "/")
    else:
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_CHUNKING_FAILED"


# ===========================================================================
# PER-DOCUMENT ORCHESTRATOR
# ===========================================================================

def chunk_document(record: ManifestRecord, clean_text: Dict, metadata: Dict) -> None:
    """Runs the full Stage 7 chunking pipeline for one document given its already-loaded
    clean_text.json and metadata.json (read-only)."""
    logger.info(f"Stage 7 started for: {record.doc_id}")
    record.started_at = get_now_iso()

    pages_sorted = sorted(clean_text.get("pages", []), key=lambda p: p["page_number"])
    full_text = "".join(p.get("text", "") for p in pages_sorted)

    resolved, offset_findings = resolve_heading_offsets(clean_text)
    spans = build_section_spans(clean_text, resolved)
    spans = split_oversized_spans(spans, full_text)
    for s in spans:
        _recompute_page_range(s, pages_sorted)
    spans = merge_undersized_spans(spans, full_text)
    spans, dropped_ranges = drop_duplicate_spans(spans, full_text)
    spans, heading_only = drop_heading_only_spans(spans, full_text)
    dropped_ranges = sorted(dropped_ranges + heading_only)
    for s in spans:
        _recompute_page_range(s, pages_sorted)
    spans = assign_chunk_ids(spans, record.doc_id)

    chunks = assemble_chunk_records(spans, record.doc_id, full_text, metadata)

    chunk_findings, outcome = validate_chunks(chunks, clean_text, dropped_ranges)
    all_findings = offset_findings + chunk_findings
    has_error = any(f["severity"] == SEVERITY_ERROR for f in all_findings)
    has_warning = any(f["severity"] == SEVERITY_WARNING for f in all_findings)
    outcome = "FAIL" if has_error else ("WARNING" if has_warning else "PASS")

    report_path = write_chunk_validation_report(record.doc_id, all_findings, outcome, chunks, dropped_ranges)
    logger.info(f"Stage 7 validation report written: {report_path} [outcome={outcome}]")

    chunks_path: Optional[Path] = None
    if outcome in ("PASS", "WARNING"):
        chunks_path = write_chunks(record.doc_id, chunks)
        logger.info(f"Stage 7 chunks written: {chunks_path} [count={len(chunks)}]")
    else:
        logger.warning(f"Stage 7 FAIL: chunks NOT written for {record.doc_id}")

    update_manifest(record, outcome, report_path, chunks_path, get_now_iso())
    logger.info(f"Stage 7 completed for: {record.doc_id} [outcome={outcome}]")


# ===========================================================================
# BATCH ORCHESTRATOR
# ===========================================================================

def run_stage7() -> StageSummary:
    """Orchestrator: chunks every document marked READY_FOR_CHUNKING with both
    clean_text and metadata artifacts registered."""
    manifest = load_manifest()
    run = StageRun("stage7")

    for doc_id, record in manifest.items():
        if record.status != DocumentStatus.READY_FOR_CHUNKING:
            continue
        if "clean_text" not in record.artifact_paths or "metadata" not in record.artifact_paths:
            logger.info(f"Skipping {doc_id}: clean_text/metadata artifact missing")
            continue

        run.attempt(doc_id)
        try:
            with open(record.artifact_paths["clean_text"], "r", encoding="utf-8") as f:
                clean_text = json.load(f)
            with open(record.artifact_paths["metadata"], "r", encoding="utf-8") as f:
                metadata = json.load(f)
            chunk_document(record, clean_text, metadata)
        except Exception as exc:
            logger.error(f"Stage 7 crashed for {doc_id}: {exc}")
            record.status = DocumentStatus.QUARANTINED
            record.error_code = "FATAL_CHUNKING_FAILED"
            record.completed_at = get_now_iso()
            record.pipeline_version = PIPELINE_VERSION

    save_manifest(manifest)
    return run.summarize(manifest)


if __name__ == "__main__":
    cli_main(run_stage7)
