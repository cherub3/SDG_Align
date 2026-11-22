"""Re-open documents so stages 4 onwards can run again on already-extracted text.

Stage 2 (extraction) is slow (minutes for 13 PDFs) and its output does not change when only
stages 4-7 change. This sets every document that is not quarantined for FATAL_NO_TEXT, and has a
raw_extraction.json, back to `registered` and deletes the artifacts of stages 4-9, so
`python -m scripts.stage4_cleaning` ... `stage7_chunking` start from the cleaned text again.

Usage (from the repo root):  python tools/reset_for_rerun.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.stage0_register import load_manifest, save_manifest  # noqa: E402
from src.ingestion_types import DocumentStatus  # noqa: E402

DERIVED_FILES = ("clean_text.json", "metadata.json")
DERIVED_DIRS = ("data/proposals/chunks", "data/proposals/embeddings", "data/proposals/vector_index",
                "data/proposals/validation_reports")


def main() -> int:
    manifest = load_manifest()
    reset = 0
    for rec in manifest.values():
        raw = Path("data/proposals/extracted") / rec.doc_id / "raw_extraction.json"
        if not raw.exists() or rec.error_code == "FATAL_NO_TEXT":
            continue
        for name in DERIVED_FILES:
            (raw.parent / name).unlink(missing_ok=True)
        rec.status = DocumentStatus.REGISTERED
        rec.error_code = None
        rec.artifact_paths = {k: v for k, v in rec.artifact_paths.items() if k in ("raw_extraction",)}
        reset += 1
    save_manifest(manifest)
    for d in DERIVED_DIRS:
        shutil.rmtree(d, ignore_errors=True)
    print(f"reset {reset} documents to 'registered'; removed derived directories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
