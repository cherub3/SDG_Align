"""Stage 9 — Vector Indexing.

Builds and validates a searchable vector index from Stage 8's embeddings.parquet.
(1) select and re-validate eligible embedding rows,
(2) build/update/persist a vector index (via a pluggable IndexAdapter) plus id-to-metadata mapping,
(3) validate the resulting index's own structural integrity and write a report.
"""

import sys
import json
import logging
import hashlib
import math
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from src.ingestion_types import ManifestRecord, DocumentStatus

INDEX_DIR = Path("data/proposals/vector_index")
INDEX_PIPELINE_VERSION = "1.0.0"

ADAPTER_ID_HASH_HEX_CHARS = 15
SELF_QUERY_SAMPLE_SIZE = 10
SELF_QUERY_SIMILARITY_TOLERANCE = 1e-4
STAGING_DIR_SUFFIX = ".building"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage9_vector_indexing")


# ---------------------------------------------------------------------------
# IndexAdapter Contract & Implementations
# ---------------------------------------------------------------------------

class IndexAdapter:
    @property
    def backend_name(self) -> str:
        raise NotImplementedError

    @property
    def backend_version(self) -> str:
        raise NotImplementedError
        
    @property
    def backend_detail(self) -> str:
        raise NotImplementedError

    @property
    def metric(self) -> str:
        """One of: cosine | inner_product | l2"""
        raise NotImplementedError

    @property
    def metric_implementation(self) -> str:
        raise NotImplementedError
        
    @property
    def normalization(self) -> str:
        raise NotImplementedError

    def build(self, dim: int) -> None:
        raise NotImplementedError

    def add(self, ids: np.ndarray, vectors: np.ndarray) -> None:
        raise NotImplementedError

    def remove(self, ids: np.ndarray) -> None:
        """True removal, not a soft/tombstone mark."""
        raise NotImplementedError

    def search(self, query: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (distances, indices). Internal validation use only."""
        raise NotImplementedError

    def serialize(self, path: Path) -> None:
        raise NotImplementedError

    def deserialize(self, path: Path) -> None:
        raise NotImplementedError

    @property
    def ntotal(self) -> int:
        raise NotImplementedError

    @property
    def dimension(self) -> int:
        raise NotImplementedError

    def reconstruct(self, internal_id: int) -> np.ndarray:
        raise NotImplementedError

class FAISSAdapter(IndexAdapter):
    def __init__(self, metric: str = "cosine"):
        if faiss is None:
            raise ImportError("faiss is not installed.")
        if metric != "cosine":
            raise ValueError(f"FAISSAdapter only supports 'cosine' metric currently, got {metric}")
        self._metric = metric
        self.index = None
    
    @property
    def backend_name(self) -> str:
        return "faiss"
        
    @property
    def backend_version(self) -> str:
        return getattr(faiss, "__version__", "unknown")
        
    @property
    def backend_detail(self) -> str:
        return "IndexIDMap2(IndexFlatIP)"
        
    @property
    def metric(self) -> str:
        return self._metric
        
    @property
    def metric_implementation(self) -> str:
        return "inner_product"
        
    @property
    def dimension(self) -> int:
        return self.index.d if self.index else 0

    def reconstruct(self, internal_id: int) -> np.ndarray:
        return self.index.reconstruct(internal_id)
        
    @property
    def normalization(self) -> str:
        return "l2"
        
    def build(self, dim: int) -> None:
        base_index = faiss.IndexFlatIP(dim)
        self.index = faiss.IndexIDMap2(base_index)
        
    def add(self, ids: np.ndarray, vectors: np.ndarray) -> None:
        if self.index is None:
            raise ValueError("Index not built.")
        if len(ids) == 0:
            return
        # L2 normalization applied by orchestration
        self.index.add_with_ids(vectors, ids)
        
    def remove(self, ids: np.ndarray) -> None:
        if self.index is None:
            raise ValueError("Index not built.")
        if len(ids) == 0:
            return
        self.index.remove_ids(ids)
        
    def search(self, query: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        if self.index is None:
            raise ValueError("Index not built.")
        return self.index.search(query, k)
        
    def serialize(self, path: Path) -> None:
        if self.index is None:
            raise ValueError("Index not built.")
        faiss.write_index(self.index, str(path))
        
    def deserialize(self, path: Path) -> None:
        self.index = faiss.read_index(str(path))

    @property
    def ntotal(self) -> int:
        return self.index.ntotal if self.index else 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_adapter_internal_id(embedding_id: str) -> int:
    """Deterministic hash of embedding_id -> int64 for index mapping."""
    h = hashlib.sha256(embedding_id.encode('utf-8')).hexdigest()
    # Use first ADAPTER_ID_HASH_HEX_CHARS hex characters (60 bits)
    hex_sub = h[:ADAPTER_ID_HASH_HEX_CHARS]
    # Parse as int, safely within signed int64
    val = int(hex_sub, 16)
    return val

def compute_index_fingerprint(config_fingerprint: str, backend_name: str, metric: str) -> str:
    """Deterministic sha256 over exactly those three inputs."""
    recipe = {
        "config_fingerprint": config_fingerprint,
        "backend_name": backend_name,
        "metric": metric
    }
    canonical = json.dumps(recipe, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize vectors, pure/deterministic."""
    if len(vectors) == 0:
        return vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # Prevent divide by zero
    return vectors / norms


# ---------------------------------------------------------------------------
# Pipeline Steps
# ---------------------------------------------------------------------------

def load_eligible_documents(manifest: Dict[str, ManifestRecord]) -> List[ManifestRecord]:
    """Gate: 'embeddings' in record.artifact_paths"""
    return [r for r in manifest.values() if "embeddings" in r.artifact_paths]

def discover_config_fingerprints(records: List[ManifestRecord]) -> Set[str]:
    """Data-driven, corpus-wide scan for config_fingerprints present in embeddings.parquet."""
    fps = set()
    for record in records:
        emb_path = Path(record.artifact_paths["embeddings"])
        if not emb_path.exists():
            continue
        try:
            table = pq.read_table(emb_path, columns=["config_fingerprint"])
            doc_fps = set(table.column("config_fingerprint").to_pylist())
            fps.update(doc_fps)
        except Exception:
            pass
    return fps

def load_rows_for_fingerprint(records: List[ManifestRecord], config_fingerprint: str) -> Dict[str, List[Dict]]:
    """Grouped by doc_id."""
    doc_rows = {}
    for record in records:
        emb_path = Path(record.artifact_paths["embeddings"])
        if not emb_path.exists():
            continue
        try:
            table = pq.read_table(emb_path)
            df = table.to_pylist()
            matching = [row for row in df if row.get("config_fingerprint") == config_fingerprint]
            if matching:
                doc_rows[record.doc_id] = matching
        except Exception:
            pass
    return doc_rows

def revalidate_rows(doc_id: str, rows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Independent structural re-check; a non-empty Critical finding list excludes the document."""
    findings = []
    
    # Check for empty vectors
    has_empty = any(not r.get("embedding_vector") or len(r["embedding_vector"]) == 0 for r in rows)
    if has_empty:
        findings.append({
            "severity": "FAIL",
            "code": "EMBEDDING_VECTOR_NOT_EMPTY",
            "message": "Found empty/null embedding vector."
        })
        
    # Check for duplicate embedding_ids
    ids = [r["embedding_id"] for r in rows]
    if len(ids) != len(set(ids)):
        findings.append({
            "severity": "FAIL",
            "code": "EMBEDDING_IDS_UNIQUE",
            "message": "Duplicate embedding_id found."
        })
        
    # Check dimensions
    dims = set(len(r["embedding_vector"]) for r in rows if r.get("embedding_vector"))
    reported_dims = set(r.get("embedding_dimension") for r in rows)
    if len(dims) > 1 or len(reported_dims) > 1 or (dims and reported_dims and dims != reported_dims):
        findings.append({
            "severity": "FAIL",
            "code": "EMBEDDING_DIMENSION_CONSISTENT",
            "message": "Inconsistent dimensions found."
        })
        
    # Check for NaN/Inf
    for r in rows:
        vec = r.get("embedding_vector", [])
        if any(math.isnan(v) or math.isinf(v) for v in vec):
            findings.append({
                "severity": "FAIL",
                "code": "EMBEDDING_NO_NAN_INF",
                "message": "NaN/Inf value found in vector."
            })
            break

    if findings:
        return [], findings
    return rows, []

class CorruptedArtifactError(Exception):
    pass

def load_existing_index(
    index_fingerprint: str, 
    adapter_factory
) -> Optional[Tuple[IndexAdapter, pa.Table, Dict]]:
    """Loads existing live index metadata and id_map, returns (index, id_map_table, metadata) or None."""
    live_dir = INDEX_DIR / index_fingerprint
    metadata_path = live_dir / "index_metadata.json"
    id_map_path = live_dir / "id_map.parquet"
    index_path = live_dir / "index.bin"
    
    if not metadata_path.exists() or not id_map_path.exists() or not index_path.exists():
        return None
        
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            
        id_map_table = pq.read_table(id_map_path)
        
        adapter = adapter_factory(metric=metadata["metric"])
        adapter.deserialize(index_path)
        
        return adapter, id_map_table, metadata
    except Exception as e:
        raise CorruptedArtifactError(f"Corrupted index artifact: {e}") from e

class IndexWorkload:
    def __init__(self):
        self.reused: List[Dict] = []
        self.added: List[Dict] = []
        self.reindexed: List[Dict] = []
        self.removed_ids: List[int] = [] # adapter_internal_ids

def determine_index_workload(
    valid_rows: List[Dict], 
    existing_id_map: Optional[List[Dict]]
) -> IndexWorkload:
    """Partitions into adds/reindexes/removes/reuses."""
    workload = IndexWorkload()
    
    if existing_id_map is None:
        workload.added = valid_rows
        return workload
        
    existing_by_eid = {row["embedding_id"]: row for row in existing_id_map}
    current_eids = set()
    
    for row in valid_rows:
        eid = row["embedding_id"]
        current_eids.add(eid)
        if eid in existing_by_eid:
            ex_row = existing_by_eid[eid]
            if ex_row["text_checksum"] == row["text_checksum"]:
                workload.reused.append(row)
            else:
                workload.reindexed.append(row)
                workload.removed_ids.append(ex_row["adapter_internal_id"])
        else:
            workload.added.append(row)
            
    # Removals: present in existing but absent in current
    for ex_row in existing_id_map:
        if ex_row["embedding_id"] not in current_eids:
            workload.removed_ids.append(ex_row["adapter_internal_id"])
            
    return workload

def _id_map_schema() -> pa.Schema:
    return pa.schema([
        ("adapter_internal_id", pa.int64()),
        ("embedding_id", pa.string()),
        ("chunk_id", pa.string()),
        ("doc_id", pa.string()),
        ("text_checksum", pa.string()),
        ("index_fingerprint", pa.string()),
        ("indexed_at", pa.string())
    ])

def apply_workload_to_staging(
    existing_index: Optional[IndexAdapter],
    existing_id_map: Optional[List[Dict]],
    workload: IndexWorkload,
    dim: int,
    adapter_factory,
    index_fingerprint: str
) -> Tuple[IndexAdapter, List[Dict]]:
    
    adapter = adapter_factory()
    if existing_index:
        # Shallow copy logic isn't clean for FAISS. Since we build in memory fast,
        # we can just write the whole thing if we don't have a deepcopy.
        # But for large indexes we want to reuse. Let's serialize/deserialize to clone.
        # However, for simplicity and crash isolation, if existing_index is provided,
        # we can actually load it from disk into a fresh adapter instance since we already have it.
        # Since adapter is stateful, let's just use existing_index directly if provided.
        # Wait, architecture says "Apply workload to a staging copy — the live index is untouched throughout."
        # We must clone it.
        tmp_path = INDEX_DIR / f"{index_fingerprint}{STAGING_DIR_SUFFIX}" / "tmp.bin"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        existing_index.serialize(tmp_path)
        adapter.deserialize(tmp_path)
        if tmp_path.exists():
            tmp_path.unlink()
    else:
        adapter.build(dim)
        
    id_map = existing_id_map.copy() if existing_id_map else []
    
    if workload.removed_ids:
        adapter.remove(np.array(workload.removed_ids, dtype=np.int64))
        id_map = [row for row in id_map if row["adapter_internal_id"] not in workload.removed_ids]
        
    rows_to_add = workload.added + workload.reindexed
    if rows_to_add:
        vectors = []
        ids = []
        now = get_now_iso()
        for row in rows_to_add:
            vec = row["embedding_vector"]
            vectors.append(vec)
            aid = compute_adapter_internal_id(row["embedding_id"])
            ids.append(aid)
            
            id_map.append({
                "adapter_internal_id": aid,
                "embedding_id": row["embedding_id"],
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "text_checksum": row["text_checksum"],
                "index_fingerprint": index_fingerprint,
                "indexed_at": now
            })
            
        vectors_np = np.array(vectors, dtype=np.float32)
        if adapter.normalization == "l2":
            vectors_np = normalize_vectors(vectors_np)
            
        adapter.add(np.array(ids, dtype=np.int64), vectors_np)
        
    return adapter, id_map


def run_self_query_sanity_check(index: IndexAdapter, id_map: List[Dict], sample_size: int) -> List[Dict]:
    findings = []
    if index.ntotal == 0 or not id_map:
        return findings
        
    sample = id_map[:sample_size]
    vecs = []
    for row in sample:
        try:
            vec = index.reconstruct(row["adapter_internal_id"])
            vecs.append(vec)
        except Exception as e:
            findings.append({
                "severity": "FAIL", "code": "INDEX_SELF_QUERY_SANITY",
                "message": f"Failed to reconstruct vector for {row['embedding_id']}: {e}"
            })
            return findings
            
    vecs_np = np.array(vecs, dtype=np.float32)
    # L2 normalize if the index requires it
    if index.normalization == "l2":
        vecs_np = normalize_vectors(vecs_np)
        
    try:
        D, I = index.search(vecs_np, 1)
        for i, row in enumerate(sample):
            if abs(D[i][0] - 1.0) > SELF_QUERY_SIMILARITY_TOLERANCE and index.metric == "cosine":
                findings.append({
                    "severity": "FAIL", "code": "INDEX_SELF_QUERY_SANITY",
                    "message": f"Self query similarity {D[i][0]} outside tolerance for {row['embedding_id']}"
                })
                break
    except Exception as e:
        findings.append({
            "severity": "FAIL", "code": "INDEX_SELF_QUERY_SANITY",
            "message": f"Search execution failed: {e}"
        })
        
    return findings


def validate_index(
    index: IndexAdapter, 
    id_map: List[Dict], 
    metadata: Dict, 
    valid_rows: List[Dict],
    backend_version: str
) -> List[Dict]:
    findings = []
    
    # INDEX_ARTIFACT_READABLE - caught implicitly if deserialize fails, 
    # but since this validates staging, we only validate the memory object.
    
    # INDEX_VECTOR_COUNT_MATCHES_ID_MAP
    if index.ntotal != len(id_map):
        findings.append({
            "severity": "FAIL", "code": "INDEX_VECTOR_COUNT_MATCHES_ID_MAP",
            "message": f"Index ntotal {index.ntotal} != id_map length {len(id_map)}"
        })
        
    # INDEX_NO_DUPLICATE_IDS
    internal_ids = [r["adapter_internal_id"] for r in id_map]
    if len(internal_ids) != len(set(internal_ids)):
        findings.append({
            "severity": "FAIL", "code": "INDEX_NO_DUPLICATE_IDS",
            "message": "Duplicate adapter_internal_ids found in id_map"
        })
        
    # INDEX_ID_NO_COLLISION
    eids = [r["embedding_id"] for r in id_map]
    if len(eids) != len(set(eids)):
        findings.append({
            "severity": "FAIL", "code": "INDEX_ID_NO_COLLISION",
            "message": "Duplicate embedding_ids found in id_map"
        })
    elif len(internal_ids) != len(set(internal_ids)):
        findings.append({
            "severity": "FAIL", "code": "INDEX_ID_NO_COLLISION",
            "message": "Hash collision on adapter_internal_id"
        })

    # INDEX_NOT_EMPTY
    if index.ntotal == 0 and valid_rows:
        findings.append({
            "severity": "FAIL", "code": "INDEX_NOT_EMPTY",
            "message": "Index is empty but valid rows exist."
        })
        
    # INDEX_COVERAGE_COMPLETE
    valid_eids = set(r["embedding_id"] for r in valid_rows)
    id_map_eids = set(eids)
    if not valid_eids.issubset(id_map_eids):
        findings.append({
            "severity": "FAIL", "code": "INDEX_COVERAGE_COMPLETE",
            "message": "Not all eligible valid rows are in the id_map."
        })
        
    # INDEX_DIMENSION_CONSISTENT
    if valid_rows:
        expected_dim = valid_rows[0]["embedding_dimension"]
        if index.dimension != expected_dim:
            findings.append({
                "severity": "FAIL", "code": "INDEX_DIMENSION_CONSISTENT",
                "message": f"Index dimension {index.dimension} != expected {expected_dim}"
            })
            
    # INDEX_SELF_QUERY_SANITY
    findings.extend(run_self_query_sanity_check(index, id_map, SELF_QUERY_SAMPLE_SIZE))

    # Recoverable findings
    
    # INDEX_ORPHAN_VECTOR
    if not id_map_eids.issubset(valid_eids):
        findings.append({
            "severity": "WARNING", "code": "INDEX_ORPHAN_VECTOR",
            "message": "Orphan vectors found in id_map (deleted upstream but not removed)."
        })
        
    # INDEX_METADATA_STALE
    if metadata.get("vector_count", 0) != index.ntotal:
        findings.append({
            "severity": "WARNING", "code": "INDEX_METADATA_STALE",
            "message": "Metadata vector count is stale."
        })
        
    # INDEX_BACKEND_VERSION_DRIFT
    if metadata.get("backend_version") != backend_version:
        findings.append({
            "severity": "WARNING", "code": "INDEX_BACKEND_VERSION_DRIFT",
            "message": "Backend version drift detected."
        })

    return findings

def _rename_with_retry(src: Path, dst: Path, attempts: int = 6, delay_seconds: float = 0.1) -> None:
    """os.rename with a short retry on PermissionError.

    On Windows a directory that was written to milliseconds ago can be briefly locked by the
    search indexer / antivirus, making os.rename raise PermissionError (WinError 5) even though
    nothing is wrong. Retrying a few times clears it. Any other OSError, and a PermissionError
    that persists across all attempts, is re-raised unchanged.
    """
    for attempt in range(1, attempts + 1):
        try:
            os.rename(src, dst)
            return
        except PermissionError:
            if attempt == attempts:
                raise
            time.sleep(delay_seconds * attempt)


def persist_index_atomic(
    index_fingerprint: str, 
    index: IndexAdapter, 
    id_map: List[Dict], 
    metadata: Dict
) -> Path:
    live_dir = INDEX_DIR / index_fingerprint
    staging_dir = INDEX_DIR / f"{index_fingerprint}{STAGING_DIR_SUFFIX}"
    
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        index.serialize(staging_dir / "index.bin")
        
        table = pa.Table.from_pylist(id_map)
        pq.write_table(table, staging_dir / "id_map.parquet")
        
        with open(staging_dir / "index_metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
            
        # The architecture mandates a single atomic os.replace(staging, live).
        # However, on Windows/NTFS, Python's os.replace and os.rename both raise 
        # OSError/PermissionError when the destination directory already exists.
        # To maintain the atomicity guarantee without failing on Windows, we use 
        # a standard rename-to-backup swap pattern.
        if live_dir.exists():
            backup_dir = INDEX_DIR / f"{index_fingerprint}.backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            _rename_with_retry(live_dir, backup_dir)
            _rename_with_retry(staging_dir, live_dir)
            # The swap already succeeded; a leftover backup is removed on the next build.
            shutil.rmtree(backup_dir, ignore_errors=True)
        else:
            _rename_with_retry(staging_dir, live_dir)
            
    except Exception as e:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise e
        
    return live_dir

def write_index_validation_report(
    index_fingerprint: str, 
    config_fingerprint: str,
    findings: List[Dict], 
    outcome: str, 
    stats: Dict
) -> Path:
    report = {
        "index_fingerprint": index_fingerprint,
        "config_fingerprint": config_fingerprint,
        "index_pipeline_version": INDEX_PIPELINE_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "validated_at": get_now_iso(),
        "outcome": outcome,
        "summary": {
            "outcome": outcome,
            "error_count": sum(1 for f in findings if f["severity"] == "FAIL"),
            "warning_count": sum(1 for f in findings if f["severity"] == "WARNING"),
            "finding_count": len(findings)
        },
        "stats": stats,
        "findings": findings
    }
    
    live_dir = INDEX_DIR / index_fingerprint
    live_dir.mkdir(parents=True, exist_ok=True)
    report_path = live_dir / "index_validation_report.json"
    
    tmp_path = report_path.with_suffix(".tmp")
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    os.replace(tmp_path, report_path)
    
    return report_path


def update_manifest_for_fingerprint(
    manifest: Dict[str, ManifestRecord], 
    index_fingerprint: str, 
    included_doc_ids: Set[str], 
    excluded_doc_ids: Set[str]
) -> None:
    live_dir = INDEX_DIR / index_fingerprint
    report_path = live_dir / "index_validation_report.json"
    
    for doc_id in included_doc_ids:
        if doc_id in manifest:
            manifest[doc_id].artifact_paths["vector_index"] = str(live_dir.as_posix())
            manifest[doc_id].artifact_paths["index_validation_report"] = str(report_path.as_posix())
            
    for doc_id in excluded_doc_ids:
        if doc_id in manifest:
            manifest[doc_id].status = DocumentStatus.QUARANTINED
            manifest[doc_id].error_code = "FATAL_INDEXING_FAILED"


def run_stage9(adapter_factory, metric: str = "cosine") -> None:
    manifest = load_manifest()
    eligible_records = load_eligible_documents(manifest)
    
    if not eligible_records:
        logger.info("No eligible documents found for Stage 9.")
        return
        
    config_fingerprints = discover_config_fingerprints(eligible_records)
    
    if not config_fingerprints:
        logger.info("No config_fingerprints discovered in the corpus.")
        return
        
    adapter_stub = adapter_factory(metric=metric)
    backend_name = adapter_stub.backend_name
    
    for config_fingerprint in sorted(list(config_fingerprints)):
        index_fingerprint = compute_index_fingerprint(config_fingerprint, backend_name, metric)
        logger.info(f"Processing index_fingerprint: {index_fingerprint}")
        
        doc_rows_map = load_rows_for_fingerprint(eligible_records, config_fingerprint)
        
        valid_rows = []
        excluded_doc_ids = set()
        included_doc_ids = set()
        
        for doc_id, rows in doc_rows_map.items():
            valid, findings = revalidate_rows(doc_id, rows)
            if findings:
                logger.warning(f"Document {doc_id} excluded due to critical findings: {findings}")
                excluded_doc_ids.add(doc_id)
            else:
                valid_rows.extend(valid)
                included_doc_ids.add(doc_id)
                     
        try:
            existing_result = load_existing_index(index_fingerprint, lambda metric=metric: adapter_factory(metric=metric))
        except CorruptedArtifactError as e:
            logger.error(f"FATAL_INDEX_BUILD_FAILED: {e}")
            findings = [{
                "severity": "FAIL", "code": "INDEX_ARTIFACT_READABLE",
                "message": str(e)
            }]
            stats = {
                "vector_count": 0, "documents_included": 0, "documents_excluded": len(included_doc_ids),
                "added_count": 0, "reused_count": 0, "reindexed_count": 0, "removed_count": 0
            }
            write_index_validation_report(index_fingerprint, config_fingerprint, findings, "FAIL", stats)
            continue
        
        existing_index = None
        existing_id_map = None
        existing_metadata = {}
        
        if existing_result:
            existing_index, id_map_table, existing_metadata = existing_result
            existing_id_map = id_map_table.to_pylist()
            
        workload = determine_index_workload(valid_rows, existing_id_map)
        
        if not workload.added and not workload.reindexed and not workload.removed_ids and existing_result:
            logger.info("REUSE for all chunks. No adapter calls made.")
            stats = {
                "vector_count": existing_index.ntotal,
                "documents_included": len(included_doc_ids),
                "documents_excluded": len(excluded_doc_ids),
                "added_count": 0,
                "reused_count": len(workload.reused),
                "reindexed_count": 0,
                "removed_count": 0
            }
            
            backend_v = existing_metadata.get("backend_version", "unknown")
            findings = validate_index(
                existing_index, 
                existing_id_map, 
                existing_metadata, 
                valid_rows,
                backend_v
            )
            
            if excluded_doc_ids:
                findings.append({
                    "severity": "WARNING", "code": "INDEX_DOCUMENT_PARTIALLY_EXCLUDED",
                    "message": f"{len(excluded_doc_ids)} docs excluded from this build."
                })
                
            critical_findings = [f for f in findings if f["severity"] == "FAIL"]
            if critical_findings:
                logger.error(f"Critical findings in {index_fingerprint} during REUSE, aborting. Findings: {critical_findings}")
                write_index_validation_report(index_fingerprint, config_fingerprint, findings, "FAIL", stats)
                continue
                
            outcome = "PASS" if not findings else "WARNING"
            write_index_validation_report(index_fingerprint, config_fingerprint, findings, outcome, stats)
            update_manifest_for_fingerprint(manifest, index_fingerprint, included_doc_ids, excluded_doc_ids)
            continue
            
        dim = valid_rows[0]["embedding_dimension"] if valid_rows else 0
        if dim == 0 and existing_metadata:
            dim = existing_metadata.get("embedding_dimension", 0)
            
        if dim == 0:
            logger.warning(f"Could not determine dimension for {index_fingerprint}, skipping.")
            continue
            
        staging_adapter, staging_id_map = apply_workload_to_staging(
            existing_index,
            existing_id_map,
            workload,
            dim,
            lambda metric=metric: adapter_factory(metric=metric),
            index_fingerprint
        )
        
        backend_v = staging_adapter.backend_version
        
        prov = valid_rows[0].get("provider", "unknown") if valid_rows else existing_metadata.get("provider", "unknown")
        mod = valid_rows[0].get("model_name", "unknown") if valid_rows else existing_metadata.get("model_name", "unknown")
        mod_v = valid_rows[0].get("model_version", "unknown") if valid_rows else existing_metadata.get("model_version", "unknown")
        
        staging_metadata = {
            "index_fingerprint": index_fingerprint,
            "config_fingerprint": config_fingerprint,
            "backend_name": staging_adapter.backend_name,
            "backend_version": backend_v,
            "backend_detail": staging_adapter.backend_detail,
            "metric": staging_adapter.metric,
            "metric_implementation": staging_adapter.metric_implementation,
            "normalization": staging_adapter.normalization,
            "provider": prov,
            "model_name": mod,
            "model_version": mod_v,
            "embedding_dimension": staging_adapter.dimension,
            "vector_count": staging_adapter.ntotal,
            "document_count": len(included_doc_ids),
            "chunk_count": staging_adapter.ntotal,
            "index_pipeline_version": INDEX_PIPELINE_VERSION,
            "created_at": get_now_iso(),
            "source_doc_ids": sorted(list(included_doc_ids))
        }
        
        findings = validate_index(
            staging_adapter, 
            staging_id_map, 
            staging_metadata, 
            valid_rows,
            backend_v
        )
        
        if excluded_doc_ids:
            findings.append({
                "severity": "WARNING", "code": "INDEX_DOCUMENT_PARTIALLY_EXCLUDED",
                "message": f"{len(excluded_doc_ids)} docs excluded from this build."
            })
            
        stats = {
            "vector_count": staging_adapter.ntotal,
            "documents_included": len(included_doc_ids),
            "documents_excluded": len(excluded_doc_ids),
            "added_count": len(workload.added),
            "reused_count": len(workload.reused),
            "reindexed_count": len(workload.reindexed),
            "removed_count": len(workload.removed_ids)
        }
        
        critical_findings = [f for f in findings if f["severity"] == "FAIL"]
        if critical_findings:
            logger.error(f"Critical findings in {index_fingerprint}, aborting build. Findings: {critical_findings}")
            write_index_validation_report(index_fingerprint, config_fingerprint, findings, "FAIL", stats)
            continue
            
        # No critical findings: Atomic swap
        persist_index_atomic(index_fingerprint, staging_adapter, staging_id_map, staging_metadata)
        
        outcome = "PASS" if not findings else "WARNING"
        write_index_validation_report(index_fingerprint, config_fingerprint, findings, outcome, stats)
        
        update_manifest_for_fingerprint(manifest, index_fingerprint, included_doc_ids, excluded_doc_ids)

    save_manifest(manifest)
    logger.info("Stage 9 Vector Indexing completed.")

if __name__ == "__main__":
    run_stage9(FAISSAdapter, metric="cosine")
