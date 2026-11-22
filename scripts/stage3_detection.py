import sys
import json
import logging
from pathlib import Path

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from src.ingestion_types import ManifestRecord, DocumentStatus

EXTRACTED_DIR = Path("data/proposals/extracted")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage3_detection")

# ISSUE 4: Character Density Heuristic Documentation
# Threshold value: 50 characters.
# Why it exists: A page with fewer than 50 visible (non-whitespace) characters is practically empty 
# or contains only artifacts (like a stray page number or a single stray character from a bad scan). 
# This prevents polluting downstream chunks with empty pages.
# How it is computed: len(raw_text.strip()), which excludes whitespace and newlines from the count, 
# measuring only actual content characters.
MIN_CHARS_PER_PAGE = 50

def evaluate_page(page: dict) -> None:
    """Evaluates a single page and determines if it should be excluded."""
    raw_text = page.get("raw_text", "")
    if raw_text is None:
        raw_text = ""
        
    # Computed as length of stripped text, ignoring pure whitespace pages.
    char_count = len(raw_text.strip())
    page["character_count"] = char_count
    
    if char_count == 0:
        page["excluded"] = True
        page["exclusion_reason"] = "EMPTY_PAGE"
    elif char_count < MIN_CHARS_PER_PAGE:
        page["excluded"] = True
        page["exclusion_reason"] = "LOW_CHARACTER_DENSITY"
    else:
        page["excluded"] = False
        page["exclusion_reason"] = None

def process_document(record: ManifestRecord) -> None:
    """Runs Stage 3 for one document."""
    logger.info(f"Stage 3 started for: {record.doc_id}")
    record.started_at = get_now_iso()
    record.pipeline_version = PIPELINE_VERSION
    
    raw_extraction_path = record.artifact_paths.get("raw_extraction")
            
    # ISSUE 3: No fallback filesystem discovery. Rely entirely on the manifest.
    if not raw_extraction_path:
        logger.error(f"Stage 3 failed: {record.doc_id} - raw_extraction artifact path missing in manifest")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        return

    # Check if the path registered in the manifest actually exists
    if not Path(raw_extraction_path).exists():
        logger.error(f"Stage 3 failed: {record.doc_id} - registered raw_extraction file not found on disk")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        return

    try:
        with open(raw_extraction_path, "r", encoding="utf-8") as f:
            raw_extraction = json.load(f)
            
        all_excluded = True
        for page in raw_extraction.get("pages", []):
            evaluate_page(page)
            if not page.get("excluded"):
                all_excluded = False
                
        # ISSUE 1: Preserve Stage 2 Artifact Integrity
        # Exception Documentation: INGESTION_ARCHITECTURE.md does not specify a separate Stage 3 artifact 
        # (e.g., page_classification.json). The exclusion state is only formalized downstream in Stage 4/5 
        # (clean_text.json) and Stage 7 (metadata.json). Because no intermediate Stage 3 artifact is defined, 
        # we intentionally mutate raw_extraction.json in place here. This violates strict ETL immutability 
        # but is required to pass Stage 3 state to Stage 4 given the approved architecture schemas.
        with open(raw_extraction_path, "w", encoding="utf-8") as f:
            json.dump(raw_extraction, f, indent=2)
            
        if all_excluded and raw_extraction.get("pages"):
            record.status = DocumentStatus.QUARANTINED
            record.error_code = "FATAL_NO_TEXT"
            logger.error(f"Stage 3 quarantined: {record.doc_id} - All pages excluded (fully scanned doc)")
        else:
            # We just leave status as is (REGISTERED) for the next stage
            logger.info(f"Stage 3 completed for: {record.doc_id}")
            
        record.completed_at = get_now_iso()
        
    except Exception as e:
        logger.exception(f"Stage 3 failed for: {record.doc_id}: {e}")
        # ISSUE 2: DocumentStatus Consistency
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()

def run_stage3() -> None:
    """Orchestrator: process every document that successfully completed Stage 2."""
    manifest = load_manifest()
    
    for doc_id, record in manifest.items():
        if record.status != DocumentStatus.REGISTERED:
            logger.info(f"Skipping {doc_id}: status is {record.status}, expected registered")
            continue
            
        if not record.artifact_paths.get("raw_extraction"):
            logger.info(f"Skipping {doc_id}: Stage 2 raw_extraction artifact missing in manifest")
            continue
            
        process_document(record)
        
    save_manifest(manifest)

if __name__ == "__main__":
    run_stage3()
