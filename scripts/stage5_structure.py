"""Stage 5 — Structural Tagging.

Reads clean_text.json (Stage 4's output) and adds structural information —
top-level section_tree and per-page headings — in place. Never modifies
page text, char_start/char_end, is_excluded, or page_number. Never reopens
a PDF. Reads raw_extraction.json read-only, for font metadata only (the
font-emphasis heading signal); never mutates it, never re-reads raw_text
from it. No semantic interpretation, no chunking, no embeddings.
See docs/INGESTION_ARCHITECTURE.md Stage 5, and the frozen Stage 5 design.
"""

import sys
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from src.ingestion_types import ManifestRecord, DocumentStatus
from src.stage_summary import StageRun, StageSummary, cli_main

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage5_structure")

# Undocumented-in-the-architecture-doc thresholds this implementation
# introduces, analogous to Stage 3's MIN_CHARS_PER_PAGE and Stage 4's
# HEADER_FOOTER_MIN_OCCURRENCES.
HEADING_MAX_LENGTH = 120
CAPS_HEADING_MIN_LENGTH = 3
CAPS_HEADING_MAX_LENGTH = 80
FONT_EMPHASIS_SIZE_RATIO = 1.15

# APPENDIX -> APPENDICES is an irregular plural (not a simple suffix, unlike
# ANNEX -> ANNEXES), so both forms are listed explicitly rather than derived
# with a suffix pattern.
APPENDIX_RE = re.compile(r'^(APPENDIX|APPENDICES|ANNEX|ANNEXES)\b', re.IGNORECASE)
REFERENCES_RE = re.compile(r'^(REFERENCES|BIBLIOGRAPHY|WORKS CITED|LITERATURE)\b', re.IGNORECASE)

_BULLET_RE = re.compile(r'^[-*•]\s')
_MARKDOWN_RE = re.compile(r'^(#{1,6})\s+(.+)$')
# Numbering group + a separately-captured optional trailing dot. A bare
# integer with neither an internal dot nor a trailing dot (e.g. "20 people
# attended...") is NOT accepted as numbering -- see _try_numeric below for
# why this guard exists.
_NUMERIC_RE = re.compile(r'^(\d+(?:\.\d+)*)(\.?)\s+(.+)$')
_ROMAN_RE = re.compile(r'^([IVXLCDM]+)\.\s+(.+)$')
_ALPHA_RE = re.compile(r'^([A-Z])\.\s+(.+)$')
_ROMAN_VALID_RE = re.compile(r'^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$')
_WHITESPACE_RE = re.compile(r'\s+')


def _normalize_for_match(text: str) -> str:
    """Collapses whitespace and strips text, for font_info correlation matching only."""
    return _WHITESPACE_RE.sub(' ', text).strip()


def _is_bullet_line(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _is_table_row(line: str) -> bool:
    """Returns True if the line contains a pipe character, marking it as a markdown table row."""
    return '|' in line


def _is_roman_numeral(token: str) -> bool:
    return bool(token) and bool(_ROMAN_VALID_RE.match(token.upper()))


def _try_numeric(stripped: str) -> Optional[Dict]:
    """Matches a numeric heading numbering token (requires an internal or trailing dot)."""
    m = _NUMERIC_RE.match(stripped)
    if not m:
        return None
    numbering, trailing_dot, title = m.groups()
    if '.' not in numbering and not trailing_dot:
        return None
    return {"style": "numeric", "numbering": numbering, "title": title.strip()}


def _correlate_font_info(cleaned_lines: List[str], font_info: List[Dict]) -> Dict[int, Dict]:
    """Maps each cleaned line's index to its originating font_info entry, by text and order."""
    result: Dict[int, Dict] = {}
    pointer = 0
    for i, line in enumerate(cleaned_lines):
        target = _normalize_for_match(line)
        if not target:
            continue
        for j in range(pointer, len(font_info)):
            if _normalize_for_match(font_info[j].get("text", "")) == target:
                result[i] = font_info[j]
                pointer = j + 1
                break
    return result


def _compute_modal_body_size(font_info_by_page: Dict[int, List[Dict]]) -> Optional[float]:
    """Returns the most frequent max_font_size (rounded to 0.5pt) across all pages."""
    sizes = []
    for entries in font_info_by_page.values():
        for entry in entries:
            size = entry.get("max_font_size")
            if size is not None:
                sizes.append(round(size * 2) / 2)
    if not sizes:
        return None
    return Counter(sizes).most_common(1)[0][0]


def _classify_line(line: str, font_entry: Optional[Dict], modal_body_size: Optional[float]) -> Optional[Dict]:
    """Classifies a line as a heading candidate (markdown/numeric/roman/alpha/font-emphasis/
    caps-unnumbered, first match wins) or returns None."""
    stripped = line.strip()
    if not stripped:
        return None
    if _is_bullet_line(stripped):
        return None
    if _is_table_row(stripped):
        return None
    if len(stripped) > HEADING_MAX_LENGTH:
        return None

    m = _MARKDOWN_RE.match(stripped)
    if m:
        hashes, title = m.groups()
        return {"style": "markdown", "numbering": hashes, "title": title.strip()}

    numeric = _try_numeric(stripped)
    if numeric:
        return numeric

    m = _ROMAN_RE.match(stripped)
    if m and _is_roman_numeral(m.group(1)):
        numbering, title = m.groups()
        return {"style": "roman", "numbering": numbering.upper(), "title": title.strip()}

    m = _ALPHA_RE.match(stripped)
    if m:
        numbering, title = m.groups()
        return {"style": "alpha", "numbering": numbering.upper(), "title": title.strip()}

    if font_entry is not None:
        size = font_entry.get("max_font_size")
        bold = bool(font_entry.get("bold_if_any", False))
        size_trigger = (
            size is not None and modal_body_size is not None
            and size >= FONT_EMPHASIS_SIZE_RATIO * modal_body_size
        )
        if size_trigger or bold:
            return {"style": "font_emphasis", "numbering": None, "title": stripped}

    letters_only = re.sub(r'[^A-Za-z]', '', stripped)
    if (letters_only and letters_only.isupper()
            and CAPS_HEADING_MIN_LENGTH <= len(stripped) <= CAPS_HEADING_MAX_LENGTH
            and not stripped.endswith('.')):
        return {"style": "caps_unnumbered", "numbering": None, "title": stripped}

    return None


def detect_headings(clean_text: Dict, font_info_by_page: Dict[int, List[Dict]]) -> List[Dict]:
    """Scans every non-excluded page and returns a page-ordered list of raw heading detections."""
    modal_body_size = _compute_modal_body_size(font_info_by_page)
    headings: List[Dict] = []
    for page in clean_text.get("pages", []):
        if page.get("is_excluded"):
            continue
        page_number = page["page_number"]
        lines = page["text"].split("\n")
        page_font_info = font_info_by_page.get(page_number, [])
        correlation = _correlate_font_info(lines, page_font_info)
        for i, line in enumerate(lines):
            classified = _classify_line(line, correlation.get(i), modal_body_size)
            if classified is not None:
                classified["page_number"] = page_number
                headings.append(classified)
    return headings


def assign_heading_levels(headings: List[Dict]) -> List[Dict]:
    """Adds section_level to each heading entry in place, based on its numbering style."""
    for h in headings:
        style = h["style"]
        if style == "markdown":
            h["section_level"] = len(h["numbering"])
        elif style == "numeric":
            h["section_level"] = h["numbering"].count(".") + 1
        elif style == "roman":
            h["section_level"] = 1
        elif style == "alpha":
            h["section_level"] = 2
        else:  # font_emphasis, caps_unnumbered
            h["section_level"] = 1
    return headings


def generate_section_ids(headings: List[Dict]) -> List[Dict]:
    """Walks the leveled heading list with a level-indexed stack, assigning section_id and
    parent_section to each entry (numeric numbering used directly, roman/alpha dot-joined to
    parent, unnumbered headings get a synthetic id)."""
    stack: List[tuple] = []  # (level, section_id), outermost first
    synthetic_counters: Dict[Optional[str], int] = {}

    for h in headings:
        level = h["section_level"]
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1] if stack else None

        style = h["style"]
        if style == "numeric":
            section_id = h["numbering"]
        elif style in ("roman", "alpha"):
            token = h["numbering"]
            section_id = f"{parent_id}.{token}" if parent_id else token
        else:
            synthetic_counters[parent_id] = synthetic_counters.get(parent_id, 0) + 1
            n = synthetic_counters[parent_id]
            if parent_id is None:
                section_id = f"s{n}"
            else:
                letter = chr(ord('a') + n - 1)
                section_id = f"{parent_id}{letter}"

        h["section_id"] = section_id
        h["parent_section"] = parent_id
        stack.append((level, section_id))

    return headings


def build_section_tree(headings: List[Dict]) -> List[Dict]:
    """Maps the leveled, id-tagged heading list to the final section_tree schema,
    asserting parent_section references are always resolvable."""
    section_tree: List[Dict] = []
    seen_ids = set()
    for h in headings:
        parent = h["parent_section"]
        assert parent is None or parent in seen_ids, (
            f"Internal consistency error: parent_section {parent!r} for "
            f"section_id {h['section_id']!r} was not seen earlier in the "
            f"list -- indicates a bug in generate_section_ids."
        )
        section_tree.append({
            "section_id": h["section_id"],
            "section_level": h["section_level"],
            "parent_section": parent,
            "title": h["title"],
            "start_page": h["page_number"],
        })
        seen_ids.add(h["section_id"])
    return section_tree


def detect_appendices(section_tree: List[Dict]) -> List[str]:
    """Returns section_ids whose heading title matches APPENDIX_RE."""
    return [s["section_id"] for s in section_tree if APPENDIX_RE.match(s["title"])]


def detect_reference_sections(section_tree: List[Dict]) -> List[str]:
    """Returns section_ids whose heading title matches REFERENCES_RE."""
    return [s["section_id"] for s in section_tree if REFERENCES_RE.match(s["title"])]


def update_clean_text(clean_text: Dict, section_tree: List[Dict]) -> Dict:
    """Sets clean_text['section_tree'] and populates each page's 'headings' list."""
    clean_text["section_tree"] = section_tree
    headings_by_page: Dict[int, List[Dict]] = {}
    for s in section_tree:
        headings_by_page.setdefault(s["start_page"], []).append(
            {"section_id": s["section_id"], "title": s["title"]}
        )
    for page in clean_text.get("pages", []):
        page["headings"] = headings_by_page.get(page["page_number"], [])
    return clean_text


def load_font_info_by_page(record: ManifestRecord) -> Dict[int, List[Dict]]:
    """Reads raw_extraction.json read-only and returns {page_number: font_info_list},
    or {} with a logged warning if unavailable."""
    raw_path = record.artifact_paths.get("raw_extraction")
    if not raw_path or not Path(raw_path).exists():
        logger.warning(
            f"Stage 5: raw_extraction missing for {record.doc_id} -- "
            f"proceeding without the font-emphasis signal"
        )
        return {}
    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_extraction = json.load(f)
        return {
            page["page_number"]: page.get("font_info", [])
            for page in raw_extraction.get("pages", [])
        }
    except Exception:
        logger.warning(
            f"Stage 5: failed to read raw_extraction for {record.doc_id} -- "
            f"proceeding without the font-emphasis signal"
        )
        return {}


def tag_document(record: ManifestRecord) -> None:
    """Runs Stage 5 structural tagging for one document, mutating clean_text.json in place."""
    logger.info(f"Stage 5 started for: {record.doc_id}")
    record.started_at = get_now_iso()
    record.pipeline_version = PIPELINE_VERSION

    clean_text_path = record.artifact_paths.get("clean_text")

    if not clean_text_path:
        logger.error(f"Stage 5 failed: {record.doc_id} - clean_text artifact path missing in manifest")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        return

    if not Path(clean_text_path).exists():
        logger.error(f"Stage 5 failed: {record.doc_id} - registered clean_text file not found on disk")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        return

    try:
        with open(clean_text_path, "r", encoding="utf-8") as f:
            clean_text = json.load(f)

        font_info_by_page = load_font_info_by_page(record)

        headings = detect_headings(clean_text, font_info_by_page)
        headings = assign_heading_levels(headings)
        headings = generate_section_ids(headings)
        section_tree = build_section_tree(headings)

        appendix_ids = detect_appendices(section_tree)
        reference_ids = detect_reference_sections(section_tree)
        if appendix_ids:
            logger.warning(f"Stage 5: {record.doc_id} - appendix sections detected: {appendix_ids}")
        if reference_ids:
            logger.warning(f"Stage 5: {record.doc_id} - reference sections detected: {reference_ids}")

        clean_text = update_clean_text(clean_text, section_tree)

        with open(clean_text_path, "w", encoding="utf-8") as f:
            json.dump(clean_text, f, indent=2)

        record.completed_at = get_now_iso()
        logger.info(f"Stage 5 completed for: {record.doc_id}")
    except Exception:
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        logger.exception(f"Stage 5 failed for: {record.doc_id}")


def run_stage5() -> StageSummary:
    """Orchestrator: tag every document with a Stage 4 clean_text artifact, skip everything else."""
    manifest = load_manifest()
    run = StageRun("stage5")
    for doc_id, record in manifest.items():
        if record.status != DocumentStatus.REGISTERED:
            logger.info(f"Skipping {doc_id}: status is {record.status}, expected registered")
            continue
        if not record.artifact_paths.get("clean_text"):
            logger.info(f"Skipping {doc_id}: Stage 4 clean_text artifact missing in manifest")
            continue
        run.attempt(doc_id)
        tag_document(record)
    save_manifest(manifest)
    return run.summarize(manifest)


if __name__ == "__main__":
    cli_main(run_stage5)
