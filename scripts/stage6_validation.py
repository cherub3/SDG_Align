"""Stage 6 — Validation & Metadata Assembly.

Reads clean_text.json (Stage 5 output) and raw_extraction.json (Stage 2/3
output, read-only), validates them via a structured pipeline of validators,
assembles metadata.json when validation gating passes, always writes
validation_report.json, and updates manifest.json via update_manifest() only.

Never reopens PDFs. Never modifies clean_text.json or raw_extraction.json.
Never chunks, embeds, retrieves, or ranks. See docs/architecture/stage6_validation.md
for the pipeline order and field-layout rationale.
"""

import sys
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from src.ingestion_types import ManifestRecord, DocumentStatus, ERROR_FAILED_VALIDATION
from src.stage_summary import StageRun, StageSummary, cli_main

EXTRACTED_DIR = Path("data/proposals/extracted")
VALIDATION_REPORTS_DIR = Path("data/proposals/validation_reports")

VALIDATION_VERSION = "1.0"
SCHEMA_VERSION = "1.0"      # Finding 5: explicit schema_version constant

# Architecture §7: char/page threshold.  A document whose total usable
# character count is below this number is considered effectively empty even
# if individual pages passed Stage 3's per-page check (e.g. many short-but-
# not-empty pages whose sum is still negligible).
MIN_DOC_TOTAL_CHARS = 200

# Regex patterns reused from the architecture doc §10 / Stage 5.
APPENDIX_RE = re.compile(r'^(APPENDIX|APPENDICES|ANNEX|ANNEXES)\b', re.IGNORECASE)
REFERENCES_RE = re.compile(r'^(REFERENCES|BIBLIOGRAPHY|WORKS CITED|LITERATURE)\b', re.IGNORECASE)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage6_validation")

# ---------------------------------------------------------------------------
# Finding severity constants
# ---------------------------------------------------------------------------
SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"


def _finding(
    severity: str,
    code: str,
    message: str,
    detail: Any = None,
    origin_stage: Optional[str] = None,   # Finding 3: source stage attribution
) -> Dict:
    """Builds a structured finding dict, optionally tagged with the stage that owns the invariant."""
    f: Dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if origin_stage is not None:
        f["origin_stage"] = origin_stage
    if detail is not None:
        f["detail"] = detail
    return f


# ===========================================================================
# VALIDATOR 1 — artifact presence
# ===========================================================================

def validate_artifacts(record: ManifestRecord) -> List[Dict]:
    """Checks that the expected clean_text/raw_extraction artifacts exist on disk."""
    findings: List[Dict] = []

    clean_text_path = record.artifact_paths.get("clean_text")
    if not clean_text_path:
        findings.append(_finding(
            SEVERITY_ERROR, "MISSING_ARTIFACT_PATH",
            "clean_text artifact path absent from manifest",
            origin_stage="Stage 4",
        ))
    elif not Path(clean_text_path).exists():
        findings.append(_finding(
            SEVERITY_ERROR, "ARTIFACT_NOT_ON_DISK",
            "clean_text artifact registered in manifest but not found on disk",
            {"path": clean_text_path},
            origin_stage="Stage 4",
        ))

    raw_path = record.artifact_paths.get("raw_extraction")
    if not raw_path:
        findings.append(_finding(
            SEVERITY_WARNING, "MISSING_RAW_EXTRACTION_PATH",
            "raw_extraction artifact path absent from manifest — offset validation will be skipped",
            origin_stage="Stage 2",
        ))
    elif not Path(raw_path).exists():
        findings.append(_finding(
            SEVERITY_WARNING, "RAW_EXTRACTION_NOT_ON_DISK",
            "raw_extraction registered in manifest but not found on disk — offset validation will be skipped",
            {"path": raw_path},
            origin_stage="Stage 2",
        ))

    return findings


# ===========================================================================
# VALIDATOR 2 — manifest field completeness
# ===========================================================================

def validate_manifest(record: ManifestRecord) -> List[Dict]:
    """Checks that required manifest fields (category, page_count, source_path) are populated."""
    findings: List[Dict] = []

    if not record.category:
        findings.append(_finding(
            SEVERITY_ERROR, "MISSING_CATEGORY",
            "category field is empty",
            origin_stage="Stage 0",
        ))

    if record.page_count is None:
        findings.append(_finding(
            SEVERITY_WARNING, "MISSING_PAGE_COUNT",
            "page_count not set in manifest — page-count match check will be skipped",
            origin_stage="Stage 1",
        ))

    if not record.source_path:
        findings.append(_finding(
            SEVERITY_WARNING, "MISSING_SOURCE_PATH",
            "source_path not set in manifest",
            origin_stage="Stage 0",
        ))

    return findings


# ===========================================================================
# VALIDATOR 3 — per-page content
# ===========================================================================

def validate_pages(clean_text: Dict, record: ManifestRecord) -> List[Dict]:
    """Validates clean_text.json's pages list: non-empty, required fields present,
    page_count matches the manifest, and page numbers are unique."""
    findings: List[Dict] = []
    pages = clean_text.get("pages")

    if not pages:
        findings.append(_finding(
            SEVERITY_ERROR, "EMPTY_PAGES",
            "clean_text.json pages list is absent or empty",
            origin_stage="Stage 4",
        ))
        return findings  # further page checks are meaningless

    # page_count match
    if record.page_count is not None and len(pages) != record.page_count:
        findings.append(_finding(
            SEVERITY_WARNING, "PAGE_COUNT_MISMATCH",
            (
                f"manifest page_count ({record.page_count}) does not match "
                f"number of pages in clean_text.json ({len(pages)})"
            ),
            {"manifest_page_count": record.page_count, "extracted_page_count": len(pages)},
            origin_stage="Stage 1",
        ))

    required_fields = {"page_number", "text", "char_start", "char_end", "is_excluded"}
    seen_numbers: List[int] = []

    for page in pages:
        pn = page.get("page_number", "?")
        missing = required_fields - set(page.keys())
        if missing:
            findings.append(_finding(
                SEVERITY_ERROR, "PAGE_MISSING_FIELDS",
                f"page {pn} is missing required fields",
                {"missing": sorted(missing)},
                origin_stage="Stage 4",
            ))

        if isinstance(pn, int):
            seen_numbers.append(pn)

    # duplicate page numbers
    if len(seen_numbers) != len(set(seen_numbers)):
        from collections import Counter
        dupes = [n for n, c in Counter(seen_numbers).items() if c > 1]
        findings.append(_finding(
            SEVERITY_ERROR, "DUPLICATE_PAGE_NUMBERS",
            "duplicate page numbers detected",
            {"duplicates": sorted(dupes)},
            origin_stage="Stage 4",
        ))

    return findings


# ===========================================================================
# VALIDATOR 3b — text volume check (Finding 4: renamed/extracted)
# ===========================================================================

def validate_text_volume(clean_text: Dict) -> List[Dict]:
    """Validates that total non-excluded character count meets MIN_DOC_TOTAL_CHARS."""
    findings: List[Dict] = []
    pages = clean_text.get("pages", [])

    total_usable_chars = 0
    for page in pages:
        if not page.get("is_excluded", False):
            text = page.get("text") or ""
            total_usable_chars += len(text.strip())

    if total_usable_chars == 0:
        findings.append(_finding(
            SEVERITY_ERROR, "FATAL_NO_TEXT",
            "all non-excluded pages have zero usable characters",
            origin_stage="Stage 3",
        ))
    elif total_usable_chars < MIN_DOC_TOTAL_CHARS:
        findings.append(_finding(
            SEVERITY_WARNING, "LOW_TOTAL_CHAR_COUNT",
            f"total usable character count ({total_usable_chars}) is below threshold ({MIN_DOC_TOTAL_CHARS})",
            {"total_usable_chars": total_usable_chars},
            origin_stage="Stage 3",
        ))

    return findings


# ===========================================================================
# VALIDATOR 4 — char_start / char_end offsets
# ===========================================================================

def validate_offsets(clean_text: Dict) -> List[Dict]:
    """Validates that per-page char_start/char_end offsets are non-negative, ordered,
    contiguous across pages, and consistent with full_text_char_count."""
    findings: List[Dict] = []
    pages = clean_text.get("pages", [])
    full_count = clean_text.get("full_text_char_count")

    prev_end: Optional[int] = None
    last_end: Optional[int] = None

    for page in pages:
        pn = page.get("page_number", "?")
        start = page.get("char_start")
        end = page.get("char_end")

        if start is None or end is None:
            continue  # already caught by validate_pages

        if not isinstance(start, int) or start < 0:
            findings.append(_finding(
                SEVERITY_ERROR, "INVALID_CHAR_START",
                f"page {pn}: char_start is invalid ({start!r})",
                origin_stage="Stage 4",
            ))
            prev_end = None
            continue

        if not isinstance(end, int) or end < start:
            findings.append(_finding(
                SEVERITY_ERROR, "INVALID_CHAR_END",
                f"page {pn}: char_end ({end!r}) is less than char_start ({start!r})",
                origin_stage="Stage 4",
            ))
            prev_end = None
            continue

        if prev_end is not None and start != prev_end:
            findings.append(_finding(
                SEVERITY_WARNING, "NON_CONTIGUOUS_OFFSETS",
                f"page {pn}: char_start ({start}) does not follow previous char_end ({prev_end})",
                {"page_number": pn, "expected_char_start": prev_end, "actual_char_start": start},
                origin_stage="Stage 4",
            ))

        prev_end = end
        last_end = end

    if full_count is not None and last_end is not None and full_count != last_end:
        findings.append(_finding(
            SEVERITY_WARNING, "FULL_CHAR_COUNT_MISMATCH",
            (
                f"full_text_char_count ({full_count}) does not match "
                f"char_end of last page ({last_end})"
            ),
            {"full_text_char_count": full_count, "last_page_char_end": last_end},
            origin_stage="Stage 4",
        ))

    return findings


# ===========================================================================
# VALIDATOR 5 — section hierarchy
# ===========================================================================

def validate_sections(clean_text: Dict) -> List[Dict]:
    """Validates section_tree: required fields, duplicate ids, missing/cyclic parent refs."""
    findings: List[Dict] = []
    section_tree = clean_text.get("section_tree", [])

    if not section_tree:
        # A document with no headings is valid; log informational only.
        findings.append(_finding(
            SEVERITY_INFO, "EMPTY_SECTION_TREE",
            "section_tree is absent or empty — document may have no detectable headings",
            origin_stage="Stage 5",
        ))
        return findings

    required_fields = {"section_id", "title", "section_level", "start_page"}
    seen_ids: Dict[str, int] = {}  # id -> first occurrence index

    for i, section in enumerate(section_tree):
        sid = section.get("section_id", f"<missing at index {i}>")
        missing = required_fields - set(section.keys())
        if missing:
            findings.append(_finding(
                SEVERITY_ERROR, "SECTION_MISSING_FIELDS",
                f"section '{sid}' is missing required fields",
                {"missing": sorted(missing)},
                origin_stage="Stage 5",
            ))

        if sid in seen_ids:
            findings.append(_finding(
                SEVERITY_ERROR, "DUPLICATE_SECTION_ID",
                f"section_id '{sid}' appears more than once",
                {"first_index": seen_ids[sid], "duplicate_index": i},
                origin_stage="Stage 5",
            ))
        else:
            seen_ids[sid] = i

    # Missing parents — only check after collecting all ids
    all_ids = set(seen_ids.keys())
    for section in section_tree:
        parent = section.get("parent_section")
        if parent is not None and parent not in all_ids:
            findings.append(_finding(
                SEVERITY_ERROR, "MISSING_PARENT_SECTION",
                f"section '{section.get('section_id')}' references parent '{parent}' which does not exist",
                {"section_id": section.get("section_id"), "missing_parent": parent},
                origin_stage="Stage 5",
            ))

    # Cycle detection via DFS
    children: Dict[str, List[str]] = {s.get("section_id"): [] for s in section_tree}
    for section in section_tree:
        parent = section.get("parent_section")
        sid = section.get("section_id")
        if parent and parent in children:
            children[parent].append(sid)

    def _has_cycle(node: str, visited: set, rec_stack: set) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for child in children.get(node, []):
            if child not in visited:
                if _has_cycle(child, visited, rec_stack):
                    return True
            elif child in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    visited_global: set = set()
    for node in list(children.keys()):
        if node not in visited_global:
            if _has_cycle(node, visited_global, set()):
                findings.append(_finding(
                    SEVERITY_ERROR, "CYCLIC_SECTION_HIERARCHY",
                    "cyclic parent_section reference detected in section_tree",
                    {"root_node": node},
                    origin_stage="Stage 5",
                ))
                break  # one report is enough; the tree is corrupt

    return findings


# ===========================================================================
# METADATA RESOLVER — Finding 1: always runs, may produce WARNING findings
# ===========================================================================

def resolve_metadata(
    record: ManifestRecord,
    clean_text: Dict,
) -> Tuple[Dict, List[Dict]]:
    """Derives the metadata.json fields from the manifest record and clean_text.json,
    returning (metadata_dict, metadata_findings)."""
    meta_findings: List[Dict] = []

    pages = clean_text.get("pages", [])
    section_tree = clean_text.get("section_tree", [])
    page_count = record.page_count if record.page_count is not None else len(pages)
    extracted_page_count = len(pages)
    excluded_pages = [
        p["page_number"] for p in pages if p.get("is_excluded", False)
    ]

    # Table detection: architecture places table_bboxes in raw_extraction.json,
    # not in clean_text. resolve_metadata() reads clean_text only (no I/O),
    # so has_tables_detected cannot be determined here. Set null (unknown).
    has_tables_detected = None

    # Sections flagged (appendix / references) — derived from section_tree.
    sections_flagged: List[Dict] = []
    for section in section_tree:
        title = section.get("title", "")
        if APPENDIX_RE.match(title):
            sections_flagged.append({
                "type": "appendix",
                "start_page": section.get("start_page"),
                "section_id": section.get("section_id"),
            })
        elif REFERENCES_RE.match(title):
            sections_flagged.append({
                "type": "references",
                "start_page": section.get("start_page"),
                "section_id": section.get("section_id"),
            })

    # Title extraction: Finding 1 — emit WARNING when title falls back to
    # a non-level-1 heading or is absent entirely, so it appears in the report.
    title, title_method = _extract_title(section_tree)
    if title_method == "none_found":
        meta_findings.append(_finding(
            SEVERITY_WARNING, "TITLE_NOT_FOUND",
            "no headings found in section_tree; title set to null",
            origin_stage="Stage 5",
        ))
    elif title_method == "largest_heading_fallback":
        meta_findings.append(_finding(
            SEVERITY_WARNING, "TITLE_FALLBACK",
            "no section_level==1 heading found; title extracted from first available heading",
            origin_stage="Stage 5",
        ))

    # doc_type is unresolved at Stage 6; emit WARNING so it's visible in report.
    if record.doc_type is None:
        meta_findings.append(_finding(
            SEVERITY_WARNING, "DOC_TYPE_UNRESOLVED",
            "doc_type not set; classification.doc_type will be null in metadata",
            origin_stage="Stage 0",
        ))

    metadata: Dict[str, Any] = {
        "doc_id": record.doc_id,
        "title": title,
        "title_extraction_method": title_method,
        "provenance": {
            "original_filename": (
                Path(record.source_path).name if record.source_path else None
            ),
            "sha256": record.doc_id.removeprefix("doc_") if record.doc_id.startswith("doc_") else None,
            "source_path": record.source_path,
            "ingested_at": record.started_at,
            "ingestion_pipeline_version": PIPELINE_VERSION,
        },
        "classification": {
            "category": record.category,
            "doc_type": record.doc_type,
            "doc_type_confidence": "unresolved",   # doc_type resolution is Stage 7+
        },
        "structure": {
            "page_count": page_count,
            "extracted_page_count": extracted_page_count,
            "excluded_pages": excluded_pages,
            "has_tables_detected": has_tables_detected,
            "sections_flagged": sections_flagged,
        },
        "validation": {
            "status": "ready_for_chunking",
            "validation_report_path": str(
                VALIDATION_REPORTS_DIR / f"{record.doc_id}_validation.json"
            ).replace("\\", "/"),
        },
        "future_compatibility": {
            "language": "en",
            "ocr_applied": False,
            "schema_version": SCHEMA_VERSION,
        },
    }
    return metadata, meta_findings


def _extract_title(section_tree: List[Dict]) -> Tuple[Optional[str], str]:
    """Extracts the document title from section_tree, preferring the first level-1 heading."""
    if not section_tree:
        return None, "none_found"
    level1 = [s for s in section_tree if s.get("section_level") == 1]
    if level1:
        return level1[0].get("title"), "largest_heading"
    return section_tree[0].get("title"), "largest_heading_fallback"


# ===========================================================================
# VALIDATION REPORT ASSEMBLER
# ===========================================================================

def assemble_validation_report(
    record: ManifestRecord,
    all_findings: List[Dict],
    outcome: str,
) -> Dict:
    """Assembles the validation_report.json dict from collected findings and the outcome."""
    error_count = sum(1 for f in all_findings if f["severity"] == SEVERITY_ERROR)
    warning_count = sum(1 for f in all_findings if f["severity"] == SEVERITY_WARNING)

    return {
        "doc_id": record.doc_id,
        "schema_version": SCHEMA_VERSION,          # Finding 5
        "validation_version": VALIDATION_VERSION,  # Finding 5
        "pipeline_version": PIPELINE_VERSION,      # Finding 5
        "validated_at": get_now_iso(),             # intentionally non-deterministic (wall clock)
        "outcome": outcome,
        "summary": {
            "outcome": outcome,
            "error_count": error_count,
            "warning_count": warning_count,
            "finding_count": len(all_findings),
        },
        "findings": all_findings,
    }


# ===========================================================================
# GATE — Finding 1: decides write, not computation
# ===========================================================================

def gate_metadata_generation(all_findings: List[Dict]) -> Tuple[bool, str]:
    """Determines (should_write_metadata, outcome) from all collected findings:
    any ERROR is FAIL, any WARNING (no errors) is WARNING, else PASS."""
    has_error = any(f["severity"] == SEVERITY_ERROR for f in all_findings)
    has_warning = any(f["severity"] == SEVERITY_WARNING for f in all_findings)

    if has_error:
        return False, "FAIL"
    if has_warning:
        return True, "WARNING"
    return True, "PASS"


# ===========================================================================
# WRITERS (disk I/O — only these functions write to disk, validators do not)
# ===========================================================================

def _write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def write_validation_report(record: ManifestRecord, report: Dict) -> Path:
    """Writes validation_report.json to disk; always called, even on FAIL."""
    VALIDATION_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = VALIDATION_REPORTS_DIR / f"{record.doc_id}_validation.json"
    _write_json(out_path, report)
    return out_path


def write_metadata(record: ManifestRecord, metadata: Dict) -> Path:
    """Writes metadata.json inside the document's extracted/ folder."""
    doc_dir = EXTRACTED_DIR / record.doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    out_path = doc_dir / "metadata.json"
    _write_json(out_path, metadata)
    return out_path


# ===========================================================================
# MANIFEST UPDATER — the ONLY function allowed to modify manifest.json
# ===========================================================================

def update_manifest(
    record: ManifestRecord,
    outcome: str,
    validation_report_path: Path,
    metadata_path: Optional[Path],
    completed_at: str,
) -> None:
    """Updates ManifestRecord fields for Stage 6 (PASS/WARNING -> READY_FOR_CHUNKING, FAIL -> QUARANTINED).
    The only function in this module that modifies manifest state."""
    record.pipeline_version = PIPELINE_VERSION
    record.completed_at = completed_at

    if outcome in ("PASS", "WARNING"):
        record.status = DocumentStatus.READY_FOR_CHUNKING
        record.error_code = None
        record.artifact_paths["validation_report"] = str(validation_report_path).replace("\\", "/")
        if metadata_path:
            record.artifact_paths["metadata"] = str(metadata_path).replace("\\", "/")
    else:
        # FAIL
        record.status = DocumentStatus.QUARANTINED
        record.artifact_paths["validation_report"] = str(validation_report_path).replace("\\", "/")
        # A stage 6 FAIL means "readable but failed validation", so it is FAILED_VALIDATION, not
        # FATAL_UNREADABLE. An error_code already set by an earlier stage is kept.
        if not record.error_code:
            record.error_code = ERROR_FAILED_VALIDATION


# ===========================================================================
# PER-DOCUMENT ORCHESTRATOR — Finding 1: approved pipeline order
# ===========================================================================

def validate_document(record: ManifestRecord) -> None:
    """Runs the full Stage 6 validation and metadata-assembly pipeline for one document."""
    logger.info(f"Stage 6 started for: {record.doc_id}")
    record.started_at = get_now_iso()

    all_findings: List[Dict] = []

    # --- STEP 1: validate_artifacts ---
    all_findings.extend(validate_artifacts(record))

    # --- STEP 2: validate_manifest ---
    all_findings.extend(validate_manifest(record))

    # Attempt to load clean_text.json; if it fails, collect findings and
    # proceed — validation cannot continue without it, but report is still built.
    clean_text: Optional[Dict] = None
    clean_text_path = record.artifact_paths.get("clean_text")
    if clean_text_path and Path(clean_text_path).exists():
        try:
            with open(clean_text_path, "r", encoding="utf-8") as f:
                clean_text = json.load(f)
        except Exception as exc:
            all_findings.append(_finding(
                SEVERITY_ERROR, "ARTIFACT_PARSE_ERROR",
                f"Failed to parse clean_text.json: {exc}",
                origin_stage="Stage 4",
            ))

    if clean_text is not None:
        # --- STEP 3: validate_pages ---
        all_findings.extend(validate_pages(clean_text, record))

        # --- STEP 4: validate_offsets ---
        all_findings.extend(validate_offsets(clean_text))

        # --- STEP 5: validate_sections ---
        all_findings.extend(validate_sections(clean_text))

        # --- STEP 6: validate_text_volume (Finding 4: renamed) ---
        all_findings.extend(validate_text_volume(clean_text))

    # --- STEP 7: resolve_metadata — ALWAYS runs (Finding 1) ---
    # Computation only; may append WARNING findings; never writes files.
    metadata: Optional[Dict] = None
    if clean_text is not None:
        metadata, meta_findings = resolve_metadata(record, clean_text)
        all_findings.extend(meta_findings)
    else:
        metadata = None

    # --- STEP 8: assemble_validation_report — includes ALL findings ---
    # gate has not been called yet; we need all findings first for gating.
    # Gate outcome is determined now, then baked into the report.
    should_write_metadata, outcome = gate_metadata_generation(all_findings)
    report = assemble_validation_report(record, all_findings, outcome)

    # --- STEP 9: write validation report (ALWAYS) ---
    report_path = write_validation_report(record, report)
    logger.info(f"Stage 6 validation report written: {report_path} [outcome={outcome}]")

    # --- STEP 10: write metadata (only on PASS / WARNING) ---
    metadata_path: Optional[Path] = None
    if should_write_metadata and metadata is not None:
        metadata_path = write_metadata(record, metadata)
        logger.info(f"Stage 6 metadata written: {metadata_path}")
    elif not should_write_metadata:
        logger.warning(f"Stage 6 FAIL: metadata NOT written for {record.doc_id}")

    # --- STEP 11: update_manifest (ONLY place manifest is modified) ---
    update_manifest(record, outcome, report_path, metadata_path, get_now_iso())

    logger.info(f"Stage 6 completed for: {record.doc_id} [outcome={outcome}]")


# ===========================================================================
# BATCH ORCHESTRATOR
# ===========================================================================

def run_stage6() -> StageSummary:
    """Orchestrator: validates every non-quarantined document with a clean_text artifact."""
    manifest = load_manifest()
    run = StageRun("stage6")

    for doc_id, record in manifest.items():
        if record.status == DocumentStatus.QUARANTINED:
            logger.info(f"Skipping {doc_id}: quarantined in a prior stage")
            continue
        if not record.artifact_paths.get("clean_text"):
            logger.info(f"Skipping {doc_id}: clean_text artifact missing — Stage 4/5 not completed")
            continue
        run.attempt(doc_id)
        validate_document(record)

    save_manifest(manifest)
    return run.summarize(manifest)


if __name__ == "__main__":
    cli_main(run_stage6)
