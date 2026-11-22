"""Stage 4 — Cleaning & Normalization.

Reads raw_extraction.json (Stage 2, annotated by Stage 3) and produces
clean_text.json: deterministic whitespace/dehyphenation/encoding/header-
footer cleanup only. No heading detection, no section hierarchy, no
semantic interpretation — that is Stage 5's job. raw_extraction.json is
never mutated; it stays intact as the fallback artifact. See
docs/INGESTION_ARCHITECTURE.md Stage 4-5 / clean_text.json.
"""

import sys
import json
import logging
import re
from pathlib import Path
from typing import Dict, List

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from scripts.stage2_extraction import EXTRACTED_DIR
from src.ingestion_types import ManifestRecord, DocumentStatus
from src.stage_summary import StageRun, StageSummary, cli_main

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage4_cleaning")

# No numeric threshold for "repeated" header/footer lines is given in
# INGESTION_ARCHITECTURE.md ("repeated-line-frequency heuristic" is named but
# not pinned to a number). These are the documented, testable constants this
# implementation introduces, analogous to Stage 3's MIN_CHARS_PER_PAGE.
HEADER_FOOTER_MIN_OCCURRENCES = 3
HEADER_FOOTER_MIN_PAGE_RATIO = 0.5

# Standard PDF-font ligature codepoints -> their expanded ASCII letters.
# Fixed 1:1 mapping, not a guess.
_LIGATURE_MAP = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

_BLANK_LINE_RUN_RE = re.compile(r"\n{3,}")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")
_REPEATED_SPACE_RE = re.compile(r"[ \t]{2,}")
_DEHYPHENATION_RE = re.compile(r"([a-zA-Z])-\n([a-zA-Z])")


def normalize_whitespace(text: str) -> str:
    """Collapses repeated whitespace, normalizes line endings, and caps blank-line runs to one."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_SPACE_RE.sub("\n", text)
    text = _REPEATED_SPACE_RE.sub(" ", text)
    text = _BLANK_LINE_RUN_RE.sub("\n\n", text)
    return text.rstrip(" \t")


def repair_dehyphenation(text: str) -> str:
    """Joins a hyphenated word split across a line break (letter-\\nletter -> letters)."""
    return _DEHYPHENATION_RE.sub(r"\1\2", text)


def repair_encoding(text: str) -> str:
    """Normalizes NBSP to a regular space and expands PDF ligature codepoints to ASCII."""
    text = text.replace("\xa0", " ")
    for ligature, expansion in _LIGATURE_MAP.items():
        text = text.replace(ligature, expansion)
    return text


def remove_headers_footers(page_texts: List[str], excluded_flags: List[bool]) -> List[str]:
    """Strips lines that repeat as the first or last non-empty line across enough pages."""
    def _first_last_lines(text: str):
        lines = [line for line in text.split("\n") if line.strip()]
        if not lines:
            return None, None
        return lines[0], lines[-1]

    candidates = [_first_last_lines(t) if not excl else (None, None)
                  for t, excl in zip(page_texts, excluded_flags)]
    non_excluded_count = sum(1 for excl in excluded_flags if not excl)

    first_counts: Dict[str, int] = {}
    last_counts: Dict[str, int] = {}
    for first, last in candidates:
        if first is not None:
            first_counts[first] = first_counts.get(first, 0) + 1
        if last is not None:
            last_counts[last] = last_counts.get(last, 0) + 1

    def _is_repeated(line: str, counts: Dict[str, int]) -> bool:
        count = counts.get(line, 0)
        if count < HEADER_FOOTER_MIN_OCCURRENCES:
            return False
        if non_excluded_count == 0:
            return False
        return (count / non_excluded_count) >= HEADER_FOOTER_MIN_PAGE_RATIO

    repeated_first = {line for line in first_counts if _is_repeated(line, first_counts)}
    repeated_last = {line for line in last_counts if _is_repeated(line, last_counts)}

    result = []
    for text, excl in zip(page_texts, excluded_flags):
        if excl:
            result.append(text)
            continue
        lines = text.split("\n")
        non_empty_indices = [i for i, line in enumerate(lines) if line.strip()]
        if non_empty_indices:
            first_idx = non_empty_indices[0]
            if lines[first_idx] in repeated_first:
                lines[first_idx] = ""
            last_idx = non_empty_indices[-1]
            if lines[last_idx] in repeated_last:
                lines[last_idx] = ""
        result.append("\n".join(lines))
    return result


def assemble_clean_text(doc_id: str, pages: List[Dict]) -> Dict:
    """Assigns running char_start/char_end per page and sums full_text_char_count."""
    out_pages = []
    running_offset = 0
    for page in pages:
        text = page["text"]
        is_excluded = page["is_excluded"]
        if is_excluded:
            char_start = running_offset
            char_end = running_offset
        else:
            char_start = running_offset
            char_end = running_offset + len(text)
            running_offset = char_end
        out_pages.append({
            "page_number": page["page_number"],
            "text": text,
            "char_start": char_start,
            "char_end": char_end,
            "is_excluded": is_excluded,
        })
    return {
        "doc_id": doc_id,
        "full_text_char_count": running_offset,
        "pages": out_pages,
    }


def build_clean_text(raw_extraction: Dict) -> Dict:
    """Runs normalize/dehyphenate/repair-encoding per page, strips headers/footers, and assembles the result."""
    raw_pages = raw_extraction.get("pages", [])

    stage_one_texts = []
    excluded_flags = []
    page_numbers = []
    for page in raw_pages:
        text = page.get("raw_text") or ""
        text = normalize_whitespace(text)
        text = repair_dehyphenation(text)
        text = repair_encoding(text)
        stage_one_texts.append(text)
        excluded_flags.append(bool(page.get("excluded", False)))
        page_numbers.append(page["page_number"])

    stripped_texts = remove_headers_footers(stage_one_texts, excluded_flags)

    pages = []
    for page_number, text, is_excluded in zip(page_numbers, stripped_texts, excluded_flags):
        pages.append({
            "page_number": page_number,
            "text": text,
            "is_excluded": is_excluded,
        })

    return assemble_clean_text(raw_extraction["doc_id"], pages)


def write_clean_text(clean_text: Dict) -> Path:
    """Writes clean_text.json to data/proposals/extracted/<doc_id>/."""
    out_dir = EXTRACTED_DIR / clean_text["doc_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "clean_text.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clean_text, f, indent=2)
    return out_path


def clean_document(record: ManifestRecord) -> None:
    """Runs Stage 4 cleaning for one document, mutating the record in place."""
    logger.info(f"Stage 4 started for: {record.doc_id}")
    record.started_at = get_now_iso()
    record.pipeline_version = PIPELINE_VERSION

    raw_extraction_path = record.artifact_paths.get("raw_extraction")

    if not raw_extraction_path:
        logger.error(f"Stage 4 failed: {record.doc_id} - raw_extraction artifact path missing in manifest")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        return

    if not Path(raw_extraction_path).exists():
        logger.error(f"Stage 4 failed: {record.doc_id} - registered raw_extraction file not found on disk")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        return

    try:
        with open(raw_extraction_path, "r", encoding="utf-8") as f:
            raw_extraction = json.load(f)

        clean_text = build_clean_text(raw_extraction)
        out_path = write_clean_text(clean_text)
        record.artifact_paths["clean_text"] = str(out_path).replace("\\", "/")
        record.completed_at = get_now_iso()
        logger.info(f"Stage 4 completed for: {record.doc_id}")
    except Exception:
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        logger.exception(f"Stage 4 failed for: {record.doc_id}")


def run_stage4() -> StageSummary:
    """Orchestrator: clean every document with a Stage 2 raw_extraction artifact, skip everything else."""
    manifest = load_manifest()
    run = StageRun("stage4")
    for doc_id, record in manifest.items():
        if record.status != DocumentStatus.REGISTERED:
            logger.info(f"Skipping {doc_id}: status is {record.status}, expected registered")
            continue
        if not record.artifact_paths.get("raw_extraction"):
            logger.info(f"Skipping {doc_id}: Stage 2 raw_extraction artifact missing in manifest")
            continue
        run.attempt(doc_id)
        clean_document(record)
    save_manifest(manifest)
    return run.summarize(manifest)


if __name__ == "__main__":
    cli_main(run_stage4)


# Clean stage completes the raw textual pipeline. Not implemented here. Stage 4 only cleans text.
