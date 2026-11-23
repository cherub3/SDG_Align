"""Fail-fast checks the server runs before it accepts traffic.

A server that starts "healthy" with no index answers every query with an error. These checks make a missing or
mismatched corpus a startup failure (clear message, non-zero exit), the same way an invalid RETRIEVAL_MODE is.

Checked, in order, with the first failure raised as StartupCheckError:
  1. RETRIEVAL_MODE is valid (ValueError otherwise) and an embedding provider is configured;
  2. the manifest lists at least one servable document (has a vector index, not quarantined);
  3. every servable document's chunks file exists and holds at least one chunk;
  4. at least one on-disk index exists, and one of them was built by exactly the configured embedding
     provider / model / version (otherwise: INDEX_EMBEDDING_MODEL_MISMATCH, naming both);
  5. that index has a non-empty index.bin, an id_map.parquet and vector_count > 0.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.pipeline_deps_factory import resolve_retrieval_mode
from scripts.stage0_register import load_manifest
from src.ingestion_types import DocumentStatus

INDEX_ROOT = Path("data/proposals/vector_index")


class StartupCheckError(RuntimeError):
    """The server must not start: the data or configuration it needs is missing, empty or inconsistent."""


def _chunk_count(path: Path) -> int:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StartupCheckError(f"chunks file {path} is unreadable: {exc}") from exc
    chunks = loaded.get("chunks", []) if isinstance(loaded, dict) else loaded
    return len(chunks) if isinstance(chunks, list) else 0


def verify_serving_data(embedding_adapter: Any, manifest: Optional[Dict[str, Any]] = None,
                        index_root: Optional[Path] = None) -> Dict[str, Any]:
    """Raises StartupCheckError unless the manifest, chunks and a matching index are present and non-empty."""
    resolve_retrieval_mode()                                   # RETRIEVAL_MODE typo -> ValueError, same stage of startup
    if embedding_adapter is None:
        raise StartupCheckError("EMBEDDING_PROVIDER is not configured: the server cannot embed queries")
    manifest = load_manifest() if manifest is None else manifest
    root = INDEX_ROOT if index_root is None else Path(index_root)

    servable = [r for r in manifest.values()
                if "vector_index" in r.artifact_paths and r.status != DocumentStatus.QUARANTINED]
    if not servable:
        raise StartupCheckError("manifest has no servable documents (missing, empty, or nothing indexed): "
                                "rebuild the corpus (stages 0-9) before starting the server")
    total_chunks = 0
    for r in servable:
        cpath = r.artifact_paths.get("chunks")
        if not cpath or not Path(cpath).is_file():
            raise StartupCheckError(f"chunks file missing for document {r.doc_id}: {cpath}")
        n = _chunk_count(Path(cpath))
        if n == 0:
            raise StartupCheckError(f"chunks file for document {r.doc_id} is empty: {cpath}")
        total_chunks += n

    wired = (embedding_adapter.provider_name, embedding_adapter.model_name, embedding_adapter.model_version)
    found, matching = [], []
    for meta_path in sorted(root.glob("*/index_metadata.json")) if root.is_dir() else []:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ident = (meta.get("provider"), meta.get("model_name"), meta.get("model_version"))
        found.append(ident)
        if ident == wired:
            matching.append((meta_path.parent, meta))
    if not found:
        raise StartupCheckError(f"no vector index found under {root}: rebuild the index (stage 9) before starting")
    if not matching:
        built = ", ".join("/".join(map(str, f)) for f in found)
        raise StartupCheckError(
            f"INDEX_EMBEDDING_MODEL_MISMATCH: configured embedding is {'/'.join(map(str, wired))} but the on-disk "
            f"index was built with {built}. Set EMBEDDING_PROVIDER to match the index or rebuild the index.")
    for folder, meta in matching:
        binf = folder / "index.bin"
        if not binf.is_file() or binf.stat().st_size == 0:
            raise StartupCheckError(f"index file missing or empty: {binf}")
        if not (folder / "id_map.parquet").is_file():
            raise StartupCheckError(f"index id map missing: {folder / 'id_map.parquet'}")
        if int(meta.get("vector_count") or 0) <= 0:
            raise StartupCheckError(f"index {folder.name} holds no vectors")
    return {"documents": len(servable), "chunks": total_chunks, "indexes": [m["index_fingerprint"] for _, m in matching]}
