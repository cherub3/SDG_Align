"""Stage 10 — Retrieval.

Given a query string and a set of Stage 9 indexes, returns ranked relevant chunks.
"""

import sys
import json
import unicodedata
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

import pyarrow.parquet as pq
import numpy as np

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest
from scripts.stage1_integrity import get_now_iso
from scripts.stage8_embedding_generation import ProviderAdapter
from scripts.stage9_vector_indexing import IndexAdapter, INDEX_DIR
from src.ingestion_types import ManifestRecord, DocumentStatus

RETRIEVAL_PIPELINE_VERSION = "1.0.0"
DEFAULT_TOP_K = 10
MAX_TOP_K = 100
FULL_SEARCH_K = 10 ** 6    # "search everything": search_index caps this at the index's vector count
OVERFETCH_MULTIPLIER = 3
L2_SCORE_EPSILON = 1e-8

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage10_retrieval")

class EmbeddingModelMismatchError(Exception):
    """Raised by a provider_adapter_factory when an index was built with a different
    (provider, model, version) than the embedding adapter that is wired for queries.
    Searching such an index would compare vectors from different embedding spaces."""


class RetrievalInternalError(Exception):
    pass

class IndexSummary:
    def __init__(self, fingerprint: str, metadata: Dict[str, Any]):
        self.fingerprint = fingerprint
        self.metadata = metadata

class IndexHandle:
    def __init__(self, fingerprint: str, metadata: Dict[str, Any], path: Path, error: Optional[Dict[str, str]] = None):
        self.fingerprint = fingerprint
        self.metadata = metadata
        self.path = path
        self.error = error

def preprocess_query(raw_query: str) -> str:
    """Deterministic strip() + Unicode NFC normalization."""
    stripped = raw_query.strip()
    return unicodedata.normalize('NFC', stripped)

def list_available_indexes(manifest: Dict[str, ManifestRecord]) -> List[IndexSummary]:
    """Enumerates every live vector_index/<fingerprint>/index_metadata.json."""
    summaries = []
    if not INDEX_DIR.exists():
        return summaries
    for d in INDEX_DIR.iterdir():
        if d.is_dir() and not str(d.name).endswith(".building"):
            meta_path = d / "index_metadata.json"
            if meta_path.exists():
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    summaries.append(IndexSummary(d.name, metadata))
                except Exception:
                    pass
    return summaries

def normalize_index_fingerprints(requested: List[str]) -> List[str]:
    """Deduplicates, first-appearance order preserved."""
    if not requested:
        raise ValueError("INDEX_FINGERPRINTS_EMPTY")
    seen = set()
    result = []
    for fp in requested:
        if fp not in seen:
            seen.add(fp)
            result.append(fp)
    return result

def resolve_index_fingerprints(requested: List[str], manifest: Dict[str, ManifestRecord]) -> List[IndexHandle]:
    handles = []
    for fp in requested:
        fp_dir = INDEX_DIR / fp
        meta_path = fp_dir / "index_metadata.json"
        index_path = fp_dir / "index.bin"
        id_map_path = fp_dir / "id_map.parquet"
        
        if not fp_dir.exists() or not meta_path.exists():
            handles.append(IndexHandle(fp, {}, fp_dir, {"severity": "WARNING", "code": "INDEX_NOT_FOUND", "message": "Index not found"}))
            continue
            
        if not index_path.exists() or not id_map_path.exists():
            handles.append(IndexHandle(fp, {}, fp_dir, {"severity": "FAIL", "code": "INDEX_ARTIFACT_READABLE", "message": "Index missing files"}))
            continue
            
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception:
            handles.append(IndexHandle(fp, {}, fp_dir, {"severity": "FAIL", "code": "INDEX_ARTIFACT_READABLE", "message": "Metadata unreadable"}))
            continue
            
        error = None
        # check if outcome was FAIL to attach WARNING INDEX_STALE_VALIDATION
        report_path = fp_dir / "index_validation_report.json"
        if report_path.exists():
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                if report.get("outcome") == "FAIL":
                    error = {"severity": "WARNING", "code": "INDEX_STALE_VALIDATION", "message": "Index validation report indicates FAIL"}
            except Exception:
                pass
                
        handles.append(IndexHandle(fp, metadata, fp_dir, error))
    return handles

def embed_query(query: str, provider_adapter: ProviderAdapter) -> np.ndarray:
    return provider_adapter.embed_batch([query])[0]


def normalize_query_vector(vector) -> np.ndarray:
    """Returns the query vector as a float32, L2-normalised (unit length) 1-D array.

    Stage 9 L2-normalises every stored vector, so the inner-product search is only a true cosine
    similarity if the query is unit length too. Providers usually already return unit vectors, but
    that is a property of the provider, not something this pipeline may assume.
    Raises ValueError for a vector that cannot be normalised (wrong shape, non-finite, zero norm)."""
    arr = np.asarray(vector, dtype=np.float32)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("query vector must be a non-empty 1-D array")
    if not np.all(np.isfinite(arr)):
        raise ValueError("query vector contains NaN or infinity")
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        raise ValueError("query vector has zero norm")
    return (arr / norm).astype(np.float32)

def search_index(index_handle: IndexHandle, query_vector: np.ndarray, k: int, index_adapter_factory: Callable[[str], IndexAdapter]) -> List[Dict]:
    metric = index_handle.metadata.get("metric", "cosine")
    adapter = index_adapter_factory(metric)
    adapter.deserialize(index_handle.path / "index.bin")
    
    ntotal = index_handle.metadata.get("vector_count", adapter.ntotal)
    k_search = min(k, ntotal)
    
    if k_search == 0:
        return []
        
    distances, internal_ids = adapter.search(np.expand_dims(query_vector, axis=0), k_search)
    distances = distances[0]
    internal_ids = internal_ids[0]
    
    # Load id_map
    id_map_df = pq.read_table(index_handle.path / "id_map.parquet").to_pandas()
    
    candidates = []
    for dist, iid in zip(distances, internal_ids):
        if iid == -1:
            continue
        row = id_map_df[id_map_df["adapter_internal_id"] == iid]
        if not row.empty:
            candidates.append({
                "index_fingerprint": index_handle.fingerprint,
                "distance": float(dist),
                "metric": metric,
                "embedding_id": row.iloc[0]["embedding_id"],
                "chunk_id": row.iloc[0]["chunk_id"],
                "doc_id": row.iloc[0]["doc_id"]
            })
    return candidates

def normalize_score(raw_distance: float, metric: str) -> float:
    if metric == "cosine":
        return raw_distance
    elif metric == "l2":
        return 1.0 / (1.0 + raw_distance)
    return raw_distance

def apply_metadata_filters(candidates: List[Dict], filters: Dict[str, Any], chunks_by_doc: Dict[str, Dict]) -> List[Dict]:
    filtered = []
    for c in candidates:
        doc_id = c["doc_id"]
        doc_chunks = chunks_by_doc.get(doc_id, {})
        chunk = doc_chunks.get(c["chunk_id"])
        
        if not chunk:
            continue
            
        match = True
        if "category" in filters and chunk.get("category") != filters["category"]:
            match = False
        if "doc_type" in filters and chunk.get("doc_type") != filters["doc_type"]:
            match = False
        if "doc_ids" in filters and filters["doc_ids"] is not None:
            if doc_id not in filters["doc_ids"]:
                match = False
                
        if match:
            filtered.append(c)
    return filtered

def assemble_results(candidates: List[Dict], chunks_by_doc: Dict[str, Dict], index_fingerprint: str) -> List[Dict]:
    assembled = []
    for c in candidates:
        doc_id = c["doc_id"]
        doc_chunks = chunks_by_doc.get(doc_id, {})
        chunk = doc_chunks.get(c["chunk_id"])
        if not chunk:
            continue
            
        assembled.append({
            "score": c["score"],
            **{k: c[k] for k in ("dense_score", "bm25_score") if k in c},
            "index_fingerprint": c["index_fingerprint"],
            "embedding_id": c["embedding_id"],
            "chunk_id": c["chunk_id"],
            "doc_id": c["doc_id"],
            "text": chunk.get("text", ""),
            "heading_path": chunk.get("heading_path", []),
            "section_ids": chunk.get("section_ids", []),
            "page_start": chunk.get("page_start", 0),
            "page_end": chunk.get("page_end", 0),
            "category": chunk.get("category", ""),
            "doc_type": chunk.get("doc_type", ""),
            "title": chunk.get("title", "")
        })
    return assembled

def select_top_k(assembled: List[Dict], top_k: int) -> List[Dict]:
    # dedup by chunk_id
    deduped = {}
    for c in assembled:
        cid = c["chunk_id"]
        if cid not in deduped or c["score"] > deduped[cid]["score"]:
            deduped[cid] = c
            
    surviving = list(deduped.values())
    
    # Actually, tie-break by chunk_id asc, score desc.
    # Python sort is stable. Sort by chunk_id asc first, then score desc.
    surviving.sort(key=lambda x: x["chunk_id"])
    surviving.sort(key=lambda x: x["score"], reverse=True)
    
    truncated = surviving[:top_k]
    
    for rank, c in enumerate(truncated):
        c["rank"] = rank
    return truncated

def validate_retrieval_result(result: Dict) -> None:
    results = result.get("results", [])
    if len(results) > MAX_TOP_K:
        raise RetrievalInternalError("len(results) > top_k")
        
    seen_chunks = set()
    prev_score = float('inf')
    searched_fps = result.get("searched_index_fingerprints", [])
    for i, c in enumerate(results):
        if c["rank"] != i:
            raise RetrievalInternalError("rank values not contiguous")
        if c["chunk_id"] in seen_chunks:
            raise RetrievalInternalError("duplicate chunk_id")
        seen_chunks.add(c["chunk_id"])
        
        if c["score"] > prev_score + 1e-6:
            raise RetrievalInternalError("score non-increasing violated")
        prev_score = c["score"]
        
        if c["index_fingerprint"] not in searched_fps:
            raise RetrievalInternalError("index_fingerprint not in searched_index_fingerprints")

def retrieve(
    request: Dict[str, Any], 
    manifest: Dict[str, ManifestRecord],
    provider_adapter_factory: Callable[[str, str, str], ProviderAdapter],
    index_adapter_factory: Callable[[str], IndexAdapter]
) -> Dict[str, Any]:
    
    findings = []
    results = []
    status = "PASS"
    searched_fps = []
    zero_results = False
    
    raw_query = request.get("query", "")
    query = preprocess_query(raw_query)
    if not query:
        findings.append({"severity": "FAIL", "code": "QUERY_EMPTY", "message": "Query is empty"})
        return {
            "query": query,
            "retrieval_pipeline_version": RETRIEVAL_PIPELINE_VERSION,
            "retrieved_at": get_now_iso(),
            "status": "FAIL",
            "zero_results": False,
            "requested_index_fingerprints": request.get("index_fingerprints", []),
            "searched_index_fingerprints": [],
            "results": [],
            "findings": findings
        }
        
    requested_fps = request.get("index_fingerprints", [])
    try:
        deduped_fps = normalize_index_fingerprints(requested_fps)
    except ValueError as e:
        if str(e) == "INDEX_FINGERPRINTS_EMPTY":
            findings.append({"severity": "FAIL", "code": "INDEX_FINGERPRINTS_EMPTY", "message": "index_fingerprints list is empty"})
            return {
                "query": query,
                "retrieval_pipeline_version": RETRIEVAL_PIPELINE_VERSION,
                "retrieved_at": get_now_iso(),
                "status": "FAIL",
                "zero_results": False,
                "requested_index_fingerprints": requested_fps,
                "searched_index_fingerprints": [],
                "results": [],
                "findings": findings
            }
        raise
        
    all_handles = resolve_index_fingerprints(deduped_fps, manifest)
    handles = []
    for h in all_handles:
        if h.error:
            findings.append({"severity": h.error["severity"], "code": h.error["code"], "index_fingerprint": h.fingerprint, "message": h.error["message"]})
            if h.error["severity"] == "FAIL" or h.error["code"] == "INDEX_NOT_FOUND":
                continue
        handles.append(h)
    
    top_k = request.get("top_k", DEFAULT_TOP_K)
    top_k = min(max(1, top_k), MAX_TOP_K)
    k_search = top_k * OVERFETCH_MULTIPLIER
    hybrid = request.get("hybrid")          # None/False = dense only; True or a dict of hybrid_search.DEFAULT_PARAMS overrides
    
    # group by provider config
    groups = {}
    for h in handles:
        key = (
            h.metadata.get("provider"),
            h.metadata.get("model_name"),
            h.metadata.get("model_version"),
            h.metadata.get("embedding_dimension")
        )
        if key not in groups:
            groups[key] = []
        groups[key].append(h)
        
    all_candidates = []
    
    for key, group_handles in groups.items():
        prov, mod, ver, dim = key
        
        try:
            adapter = provider_adapter_factory(prov, mod, ver)
            query_vector = embed_query(query, adapter)
            unit_query_vector = normalize_query_vector(query_vector)
        except EmbeddingModelMismatchError as e:
            for h in group_handles:
                findings.append({"severity": "FAIL", "code": "INDEX_EMBEDDING_MODEL_MISMATCH",
                                 "index_fingerprint": h.fingerprint,
                                 "message": f"Refusing to search: {str(e)}"})
            continue
        except Exception as e:
            findings.append({"severity": "FAIL", "code": "QUERY_EMBEDDING_FAILED", "message": f"Embedding failed: {str(e)}"})
            continue
            
        for h in group_handles:
            if h.metadata.get("embedding_dimension") != len(query_vector):
                findings.append({"severity": "FAIL", "code": "EMBEDDING_DIMENSION_MISMATCH", "index_fingerprint": h.fingerprint, "message": "Dimension mismatch"})
                continue
                
            try:
                # Indexes built with L2 normalisation (all of them, today) need a unit-length query.
                search_vector = unit_query_vector if h.metadata.get("normalization") == "l2" else np.asarray(query_vector, dtype=np.float32)
                # Hybrid fusion needs the dense score of every chunk BM25 might surface, so search the whole (flat) index.
                candidates = search_index(h, search_vector, FULL_SEARCH_K if hybrid else k_search, index_adapter_factory)
                for c in candidates:
                    c["score"] = normalize_score(c["distance"], c["metric"])
                    
                    # check manifest
                    doc_id = c["doc_id"]
                    if doc_id in manifest:
                        rec = manifest[doc_id]
                        if "vector_index" in rec.artifact_paths and rec.status != DocumentStatus.QUARANTINED:
                            all_candidates.append(c)
                
                searched_fps.append(h.fingerprint)
            except Exception as e:
                findings.append({"severity": "FAIL", "code": "INDEX_ARTIFACT_READABLE", "index_fingerprint": h.fingerprint, "message": f"Search failed: {str(e)}"})
                
    # Evaluate status
    has_fail = any(f["severity"] == "FAIL" for f in findings)
    if not searched_fps:
        status = "FAIL"
    elif has_fail:
        status = "PARTIAL"
    else:
        status = "PASS"
        
    if status == "FAIL":
        return {
            "query": query,
            "retrieval_pipeline_version": RETRIEVAL_PIPELINE_VERSION,
            "retrieved_at": get_now_iso(),
            "status": "FAIL",
            "zero_results": False,
            "requested_index_fingerprints": requested_fps,
            "searched_index_fingerprints": searched_fps,
            "results": [],
            "findings": findings
        }
        
    # load chunks
    doc_ids_needed = set(c["doc_id"] for c in all_candidates)
    chunks_by_doc = {}
    metadata_by_doc = {}
    
    for doc_id in doc_ids_needed:
        if doc_id in manifest:
            paths = manifest[doc_id].artifact_paths
            if "chunks" in paths:
                chunks_path = Path(paths["chunks"])
                if chunks_path.exists():
                    try:
                        with open(chunks_path, 'r', encoding='utf-8') as f:
                            loaded = json.load(f)
                            # Stage 7 writes {"chunks": [...]} envelopes; accept a bare list too.
                            chunk_list = loaded.get("chunks", []) if isinstance(loaded, dict) else loaded
                            chunks_by_doc[doc_id] = {c["chunk_id"]: c for c in chunk_list}
                    except Exception:
                        pass
                        
    # Need metadata.json for filter validation
    meta_path = Path("data/proposals/metadata.json")
    if meta_path.exists():
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta_arr = json.load(f)
                for m in meta_arr:
                    metadata_by_doc[m["doc_id"]] = m
        except Exception:
            pass

    filters = request.get("filters", {})
    if "category" in filters:
        val = filters["category"]
        if not any(metadata_by_doc.get(c["doc_id"], {}).get("category") == val for c in all_candidates):
            findings.append({"severity": "WARNING", "code": "FILTER_VALUE_UNKNOWN", "message": f"Category filter {val} not found in candidates"})
    if "doc_type" in filters:
        val = filters["doc_type"]
        if not any(metadata_by_doc.get(c["doc_id"], {}).get("doc_type") == val for c in all_candidates):
            findings.append({"severity": "WARNING", "code": "FILTER_VALUE_UNKNOWN", "message": f"Doc type filter {val} not found in candidates"})

    if hybrid:
        from scripts import hybrid_search
        from scripts.stage8_embedding_generation import embedding_text
        pool = [c for d in chunks_by_doc.values() for c in d.values()]
        all_candidates = hybrid_search.fuse_candidates(
            all_candidates, hybrid_search.build_bm25(pool, embedding_text), query, hybrid if isinstance(hybrid, dict) else None)

    filtered_candidates = apply_metadata_filters(all_candidates, filters, chunks_by_doc)
    
    assembled = assemble_results(filtered_candidates, chunks_by_doc, index_fingerprint="")
    results = select_top_k(assembled, top_k)
    
    if not results:
        zero_results = True
        findings.append({"severity": "WARNING", "code": "ZERO_RESULTS", "message": "Zero results after filtering"})
        
    res = {
        "query": query,
        "retrieval_pipeline_version": RETRIEVAL_PIPELINE_VERSION,
        "retrieved_at": get_now_iso(),
        "status": status,
        "zero_results": zero_results,
        "requested_index_fingerprints": requested_fps,
        "searched_index_fingerprints": searched_fps,
        "results": results,
        "findings": findings
    }
    
    validate_retrieval_result(res)
    return res
