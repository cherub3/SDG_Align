import sys
import datetime
import logging
from pathlib import Path
from typing import Dict
import fitz

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from src.ingestion_types import ManifestRecord, DocumentStatus
from src.stage_summary import StageRun, StageSummary, cli_main
from scripts.stage0_register import load_manifest, save_manifest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage1_integrity")

RAW_DIR = Path("data/proposals/raw")
PIPELINE_VERSION = "0.1.0"

def get_now_iso() -> str:
    """Returns current UTC timestamp in ISO format."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def verify_document_integrity(record: ManifestRecord) -> None:
    """Opens a single PDF and verifies its integrity, updating the record."""
    logger.info(f"Checking integrity for {record.doc_id}")
    
    record.started_at = get_now_iso()
    record.pipeline_version = PIPELINE_VERSION
    
    # Locate the PDF file for this document. It is stored in RAW_DIR / category / <filename>.pdf
    # Since we only have the category and doc_id, we can find it by globbing in the category dir.
    category_dir = RAW_DIR / record.category
    pdf_paths = list(category_dir.glob("*.pdf"))
    
    target_path = None
    for path in pdf_paths:
        import hashlib
        hasher = hashlib.sha256()
        with open(path, 'rb') as f:
            hasher.update(f.read())
        if f"doc_{hasher.hexdigest()}" == record.doc_id:
            target_path = path
            break
            
    if not target_path:
        logger.error(f"Could not find source PDF for {record.doc_id} in {category_dir}")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()
        return

    try:
        doc = fitz.open(target_path)
        page_count = doc.page_count
        doc.close()
        
        record.page_count = page_count
        logger.info(f"Integrity check passed for {record.doc_id} (Pages: {page_count})")
        record.completed_at = get_now_iso()
        
    except Exception as e:
        logger.warning(f"Integrity check failed for {record.doc_id}: {e}")
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_UNREADABLE"
        record.completed_at = get_now_iso()

def run_stage1() -> StageSummary:
    """Orchestrates Stage 1 integrity check."""
    manifest = load_manifest()
    run = StageRun("stage1")
    
    for doc_id, record in manifest.items():
        if record.status != DocumentStatus.REGISTERED:
            continue
            
        run.attempt(doc_id)
        verify_document_integrity(record)

    save_manifest(manifest)
    return run.summarize(manifest)

if __name__ == "__main__":
    cli_main(run_stage1)
