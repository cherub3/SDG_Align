import sys
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Iterator

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from src.ingestion_types import ManifestRecord, DocumentStatus
from src.stage_summary import StageRun, StageSummary, cli_main

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("manifest_registration")

RAW_DIR = Path("data/proposals/raw")
MANIFEST_PATH = Path("data/proposals/manifest.json")

def load_manifest() -> Dict[str, ManifestRecord]:
    """Loads the manifest.json into a dictionary of ManifestRecords."""
    if not MANIFEST_PATH.exists():
        return {}
    try:
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        manifest = {}
        for doc_id, record_data in data.items():
            manifest[doc_id] = ManifestRecord.from_dict(record_data)
        return manifest
    except Exception as e:
        logger.error(f"Failed to load manifest.json: {e}")
        return {}

def save_manifest(manifest: Dict[str, ManifestRecord]) -> None:
    """Saves the dictionary of ManifestRecords to manifest.json."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    records = {doc_id: record.to_dict() for doc_id, record in manifest.items()}
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2)

def compute_sha256(file_path: Path) -> str:
    """Computes the full SHA-256 digest of a file's bytes."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def discover_documents() -> Iterator[Path]:
    """Yields all PDF documents found in the raw directory."""
    if not RAW_DIR.exists():
        logger.error(f"Directory {RAW_DIR} does not exist.")
        return
    for file_path in RAW_DIR.rglob("*.pdf"):
        if file_path.is_file():
            yield file_path

def register_document(file_path: Path, manifest: Dict[str, ManifestRecord]) -> bool:
    """Registers a single document into the manifest if not already present."""
    logger.info(f"Document discovered: {file_path}")

    # Category is strictly the parent folder name
    category = file_path.parent.name
    logger.info(f"Category detected: {category}")

    try:
        file_hash = compute_sha256(file_path)
        doc_id = f"doc_{file_hash}"
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        return False

    source_path = str(file_path).replace("\\", "/")

    if doc_id in manifest:
        existing = manifest[doc_id]
        if existing.source_path is None:
            existing.source_path = source_path
            logger.info(f"Backfilled source_path for existing record: {doc_id}")
        else:
            logger.warning(f"Duplicate skipped: Document with doc_id {doc_id} is already registered.")
        return True

    # Register document
    record = ManifestRecord(
        doc_id=doc_id,
        category=category,
        status=DocumentStatus.REGISTERED,
        source_path=source_path
    )

    manifest[doc_id] = record
    logger.info(f"Document registered: {doc_id}")
    return True

def register_documents() -> StageSummary:
    """Orchestrates the manifest registration process."""
    manifest = load_manifest()
    run = StageRun("stage0")

    for file_path in discover_documents():
        run.attempt(str(file_path))
        if register_document(file_path, manifest) is False:
            run.fail(f"could not read {file_path}")

    save_manifest(manifest)
    return run.summarize(manifest)

if __name__ == "__main__":
    cli_main(register_documents)
