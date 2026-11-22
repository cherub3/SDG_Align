"""Stage 2 — Raw PDF Extraction.

For every document that passed Stage 1 integrity checking, extracts the raw
per-page text and layout representation from the PDF and writes it to
raw_extraction.json. Capture only — no cleaning, interpretation, or semantic
processing. See docs/INGESTION_ARCHITECTURE.md Stage 2 / §3.
"""

import sys
import json
import logging
from pathlib import Path
from typing import List, Dict

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

import fitz
import pymupdf4llm

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from src.ingestion_types import ManifestRecord, DocumentStatus
from src.stage_summary import StageRun, StageSummary, cli_main

EXTRACTED_DIR = Path("data/proposals/extracted")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage2_extraction")


def _extract_line_font_info(text_dict: Dict) -> List[Dict]:
    """Capture font metadata per line (not per raw span). No filtering, no
    classification — Stage 5 decides what's a heading, not Stage 2.

    A single line commonly fragments into several PyMuPDF spans purely from
    font-run boundaries (e.g. one bold word mid-sentence). Aggregating per
    line avoids bloating font_info with near-duplicate fragments while
    losing no information Stage 5 would actually use.

    Takes the page's already-parsed get_text("dict") result rather than the
    page itself, so callers can reuse that same parse for block_count
    instead of parsing the page twice.
    """
    lines_info = []
    for block in text_dict["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            lines_info.append({
                "text": text,
                "max_font_size": max(s["size"] for s in spans),
                "bold_if_any": any(bool(s["flags"] & (1 << 4)) for s in spans),
                "bbox": [x0, y0, x1, y1],
            })
    return lines_info


def _extract_table_bboxes(page: "fitz.Page") -> List[list]:
    """Detect table regions via PyMuPDF's built-in finder. Bbox only, no cell parsing.

    find_tables() can return a degenerate candidate with no cells, whose
    .bbox property raises ValueError (min() of an empty sequence) instead of
    a usable box. Such a candidate carries no usable bbox, so it's skipped
    rather than crashing extraction for the whole page.
    """
    bboxes = []
    for t in page.find_tables().tables:
        try:
            bboxes.append(list(t.bbox))
        except ValueError:
            continue
    return bboxes


def build_raw_extraction(pdf_path: Path, doc_id: str) -> Dict:
    """Build the raw_extraction.json artifact: per-page raw text
    (markdown-preserving) + low-level layout metadata.

    Returns a plain dict matching the raw_extraction.json schema exactly —
    written once, read once, no domain model needed.
    """
    doc = fitz.open(pdf_path)
    try:
        md_pages = pymupdf4llm.to_markdown(doc, page_chunks=True)
        pages = []
        for i in range(doc.page_count):
            page = doc[i]
            raw_text = md_pages[i].get("text", "") if i < len(md_pages) else ""
            text_dict = page.get_text("dict")   # parsed once, reused for font_info + block_count
            pages.append({
                "page_number": i + 1,
                "raw_text": raw_text,
                "font_info": _extract_line_font_info(text_dict),
                "layout_metadata": {
                    "table_bboxes": _extract_table_bboxes(page),
                    "block_count": len(text_dict["blocks"]),
                },
            })
        return {
            "doc_id": doc_id,
            "extractor": {"markdown": "pymupdf4llm", "layout": "PyMuPDF"},
            "pages": pages,
        }
    finally:
        doc.close()


def write_raw_extraction(raw_extraction: Dict) -> Path:
    """Write raw_extraction.json to data/proposals/extracted/<doc_id>/."""
    out_dir = EXTRACTED_DIR / raw_extraction["doc_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "raw_extraction.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw_extraction, f, indent=2)
    return out_path


def extract_document(record: ManifestRecord) -> None:
    """Run Stage 2 extraction for one document, mutating the record in place."""
    logger.info(f"Extraction started: {record.doc_id}")
    record.started_at = get_now_iso()
    record.pipeline_version = PIPELINE_VERSION

    if not record.source_path or not Path(record.source_path).exists():
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        logger.error(f"Extraction failed: {record.doc_id} — source_path missing or not found")
        return

    try:
        raw_extraction = build_raw_extraction(Path(record.source_path), record.doc_id)
        out_path = write_raw_extraction(raw_extraction)
        record.artifact_paths["raw_extraction"] = str(out_path).replace("\\", "/")
        record.completed_at = get_now_iso()
        logger.info(f"Extraction completed: {record.doc_id}")
    except Exception:
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        logger.exception(f"Extraction failed: {record.doc_id}")


def run_stage2() -> StageSummary:
    """Orchestrator: extract every document that passed Stage 1, skip everything else."""
    manifest = load_manifest()
    run = StageRun("stage2")
    for doc_id, record in manifest.items():
        if record.status != DocumentStatus.REGISTERED or record.page_count is None:
            logger.info(f"Skipping {doc_id}: has not passed Stage 1")
            continue
        run.attempt(doc_id)
        extract_document(record)
    save_manifest(manifest)
    return run.summarize(manifest)


if __name__ == "__main__":
    cli_main(run_stage2)
