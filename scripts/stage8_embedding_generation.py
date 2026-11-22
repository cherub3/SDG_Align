"""Stage 8 — Embedding Generation.

Reads chunks.json (Stage 7 output) and generates embeddings against a
Provider Abstraction Layer. Writes embeddings.parquet and
embedding_validation_report.json per document.

Never reopens PDFs. Never modifies upstream artifacts. Does not implement
any vector database indexing, retrieval, or ranking.
"""

import sys
import json
import logging
import hashlib
import time
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

# Adjust path to import from src
src_path = Path(__file__).parent.parent
sys.path.append(str(src_path))

from scripts.stage0_register import load_manifest, save_manifest
from scripts.stage1_integrity import get_now_iso, PIPELINE_VERSION
from src.ingestion_types import ManifestRecord, DocumentStatus

EMBEDDINGS_DIR = Path("data/proposals/embeddings")
CHUNKS_DIR = Path("data/proposals/chunks")
EMBEDDING_PIPELINE_VERSION = "1.0.0"

BATCH_SIZE = 32
CHECKPOINT_INTERVAL_BATCHES = 5
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("stage8_embedding_generation")

# ---------------------------------------------------------------------------
# Provider Abstraction Layer
# ---------------------------------------------------------------------------

class ProviderAdapter:
    """Contract for any embedding provider (local or hosted API)."""
    @property
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        raise NotImplementedError

    @property
    def model_version(self) -> str:
        raise NotImplementedError

    @property
    def embedding_dimension(self) -> int:
        """Discovered from the provider's actual first returned vector."""
        raise NotImplementedError

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Returns one vector per text in the same order."""
        raise NotImplementedError

    def is_transient_error(self, exception: Exception) -> bool:
        """Classifies retryable failures."""
        raise NotImplementedError

    @property
    def requests_per_minute(self) -> Optional[int]:
        """Optional rate throttle."""
        return None

    @property
    def max_batch_size(self) -> Optional[int]:
        """Optional upper bound on embed_batch input size."""
        return None

    @property
    def config_fingerprint_fields(self) -> Dict[str, Any]:
        """Additional identity fields this specific provider contributes."""
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_id_component(text: str) -> str:
    """Replace any character outside [A-Za-z0-9_.-] with -."""
    return re.sub(r'[^A-Za-z0-9_.-]', '-', text)

def compute_text_checksum(text: str) -> str:
    """sha256 hex digest of the chunk's exact UTF-8 text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def compute_config_fingerprint(provider: ProviderAdapter, dim: int) -> str:
    """sha256 hex digest of the canonical JSON recipe identity."""
    if provider.model_version.lower() == "latest":
        raise ValueError("model_version cannot be 'latest'")
    
    config = {
        "provider": provider.provider_name,
        "model_name": provider.model_name,
        "model_version": provider.model_version,
        "embedding_dimension": dim
    }
    config.update(provider.config_fingerprint_fields)
    
    # Canonical JSON: compact, sorted keys
    canonical = json.dumps(config, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def build_embedding_id(chunk_id: str, provider: ProviderAdapter) -> str:
    """f"{chunk_id}__{provider}__{model_name}__{model_version}" sanitized."""
    parts = [
        chunk_id,
        sanitize_id_component(provider.provider_name),
        sanitize_id_component(provider.model_name),
        sanitize_id_component(provider.model_version)
    ]
    return "__".join(parts)


# ---------------------------------------------------------------------------
# Parquet Schema
# ---------------------------------------------------------------------------

def get_parquet_schema() -> pa.Schema:
    return pa.schema([
        ("embedding_id", pa.string()),
        ("chunk_id", pa.string()),
        ("doc_id", pa.string()),
        ("provider", pa.string()),
        ("model_name", pa.string()),
        ("model_version", pa.string()),
        ("embedding_dimension", pa.int32()),
        ("embedding_vector", pa.list_(pa.float32())),
        ("text_checksum", pa.string()),
        ("config_fingerprint", pa.string()),
        ("created_at", pa.string()),
        ("embedding_pipeline_version", pa.string()),
        ("source_chunk_char_count", pa.int32()),
    ])


# ---------------------------------------------------------------------------
# Workload & Checkpointing
# ---------------------------------------------------------------------------

class CorruptedArtifactError(Exception):
    """Raised when an existing embeddings.parquet is present but unreadable.

    Per the architecture, EMBEDDING_ARTIFACT_READABLE is a Critical finding.
    Corrupted artifacts must never be silently treated as empty — doing so
    would cause the pipeline to regenerate all embeddings without surfacing
    the corruption to the operator.
    """
    pass


def load_existing_embeddings(parquet_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load embeddings.parquet into a lookup keyed by embedding_id -> row dict.

    Returns {} when the file does not exist (first run).
    Raises CorruptedArtifactError when the file exists but cannot be read
    (Finding 3: corrupted artifacts must not be silently treated as empty).
    """
    if not parquet_path.exists():
        return {}
    try:
        table = pq.read_table(parquet_path)
        df = table.to_pylist()
        return {row["embedding_id"]: row for row in df}
    except Exception as exc:
        raise CorruptedArtifactError(
            f"Existing embeddings.parquet is corrupted and unreadable: {parquet_path}: {exc}"
        ) from exc

def determine_workload(
    chunks: List[Dict],
    existing_lookup: Dict[str, Dict[str, Any]],
    provider: ProviderAdapter,
    dim: int
) -> Tuple[List[Dict], List[Dict]]:
    """Returns (reuse_rows, generate_chunks)."""
    reuse_rows = []
    generate_chunks = []
    
    config_fp = compute_config_fingerprint(provider, dim)
    
    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        text_checksum = compute_text_checksum(chunk["text"])
        emb_id = build_embedding_id(chunk_id, provider)
        
        if emb_id in existing_lookup:
            row = existing_lookup[emb_id]
            if row.get("text_checksum") == text_checksum and row.get("config_fingerprint") == config_fp:
                reuse_rows.append(row)
            else:
                logger.info(f"WARNING_EMBEDDING_CHECKSUM_STALE: Chunk {chunk_id} text changed, queueing generation")
                generate_chunks.append(chunk)
        else:
            generate_chunks.append(chunk)
            
    return reuse_rows, generate_chunks

def load_checkpoint(checkpoint_path: Path) -> Dict[str, Dict]:
    """Load completed rows from JSONL checkpoint."""
    completed = {}
    if checkpoint_path.exists():
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    completed[row["embedding_id"]] = row
                except json.JSONDecodeError:
                    # corrupted partial line at EOF is ignored
                    continue
    return completed

def _write_checkpoint_row(checkpoint_path: Path, row: Dict) -> None:
    with open(checkpoint_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row) + "\n")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

def _finding(severity: str, code: str, message: str, detail: Any = None) -> Dict:
    f: Dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if detail is not None:
        f["detail"] = detail
    return f

def validate_embeddings(
    all_rows: List[Dict],
    chunks: List[Dict],
    provider: ProviderAdapter,
    dim: int
) -> List[Dict]:
    """Full validation suite."""
    findings = []
    
    if not all_rows:
        return findings
        
    config_fp = compute_config_fingerprint(provider, dim)
    expected_chunk_ids = {c["chunk_id"]: c for c in chunks}
    
    # 1. EMBEDDING_IDS_UNIQUE
    seen_ids = set()
    dup_ids = set()
    for r in all_rows:
        eid = r.get("embedding_id")
        if eid in seen_ids:
            dup_ids.add(eid)
        seen_ids.add(eid)
    if dup_ids:
        findings.append(_finding(SEVERITY_ERROR, "EMBEDDING_IDS_UNIQUE", "Duplicate embedding_id found", {"duplicates": list(dup_ids)}))

    # Identify rows matching current config
    config_rows = [r for r in all_rows if r.get("config_fingerprint") == config_fp]
    row_chunk_ids = {r.get("chunk_id") for r in config_rows}
    
    # 2. EMBEDDING_COVERAGE_COMPLETE
    missing_chunks = set(expected_chunk_ids.keys()) - row_chunk_ids
    if missing_chunks:
        findings.append(_finding(SEVERITY_ERROR, "EMBEDDING_COVERAGE_COMPLETE", "Not all chunks embedded", {"missing_count": len(missing_chunks)}))

    # 3. EMBEDDING_ORPHAN_CHUNK (Recoverable) — checks all rows, not just current config,
    # because the architecture defines orphan as "chunk_id no longer exists in chunks.json"
    # for any row (including rows from prior configs), not only the current-config rows.
    all_row_chunk_ids = {r.get("chunk_id") for r in all_rows}
    orphan_chunks = all_row_chunk_ids - set(expected_chunk_ids.keys())
    if orphan_chunks:
        findings.append(_finding(SEVERITY_WARNING, "EMBEDDING_ORPHAN_CHUNK", "Orphan chunks found", {"orphan_count": len(orphan_chunks)}))

    for idx, r in enumerate(all_rows):
        cid = r.get("chunk_id")
        eid = r.get("embedding_id", f"<row {idx}>")
        vec = r.get("embedding_vector")
        
        # 4. EMBEDDING_VECTOR_NOT_EMPTY
        if not vec:
            findings.append(_finding(SEVERITY_ERROR, "EMBEDDING_VECTOR_NOT_EMPTY", f"Empty vector for {eid}"))
            continue
            
        # 5. EMBEDDING_DIMENSION_CONSISTENT
        stored_dim = r.get("embedding_dimension")
        if stored_dim != len(vec):
            findings.append(_finding(SEVERITY_ERROR, "EMBEDDING_DIMENSION_CONSISTENT", f"Vector length {len(vec)} != stored dim {stored_dim} for {eid}"))
            
        # 6. EMBEDDING_NO_NAN_INF
        if any(math.isnan(v) or math.isinf(v) for v in vec):
            findings.append(_finding(SEVERITY_ERROR, "EMBEDDING_NO_NAN_INF", f"NaN or Inf in vector for {eid}"))

        # 7. EMBEDDING_PROVIDER_MATCH
        expected_eid_prefix = f"{cid}__{sanitize_id_component(r.get('provider', ''))}__{sanitize_id_component(r.get('model_name', ''))}__{sanitize_id_component(r.get('model_version', ''))}"
        if not eid.startswith(expected_eid_prefix):
            findings.append(_finding(SEVERITY_ERROR, "EMBEDDING_PROVIDER_MATCH", f"ID prefix {expected_eid_prefix} does not match {eid}"))

        # 8. EMBEDDING_CHECKSUM_WELL_FORMED
        chk = r.get("text_checksum")
        if not chk or len(chk) != 64 or not re.match(r'^[0-9a-f]{64}$', chk):
            findings.append(_finding(SEVERITY_ERROR, "EMBEDDING_CHECKSUM_WELL_FORMED", f"Invalid checksum for {eid}"))

        # 9. EMBEDDING_CHECKSUM_STALE (Recoverable)
        if r.get("config_fingerprint") == config_fp and cid in expected_chunk_ids:
            current_chk = compute_text_checksum(expected_chunk_ids[cid]["text"])
            if chk != current_chk:
                findings.append(_finding(SEVERITY_WARNING, "EMBEDDING_CHECKSUM_STALE", f"Stale checksum for {eid}"))
                
    return findings


# ---------------------------------------------------------------------------
# Core Generation
# ---------------------------------------------------------------------------

def persist_embeddings(doc_id: str, all_rows: List[Dict]) -> Path:
    """Atomically writes embeddings.parquet."""
    doc_dir = EMBEDDINGS_DIR / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = doc_dir / "embeddings.parquet"
    tmp_path = doc_dir / "embeddings.parquet.tmp"
    
    schema = get_parquet_schema()
    
    # pyarrow expects dict-of-lists for from_pydict
    if not all_rows:
        # write empty table
        table = pa.Table.from_arrays([pa.array([], type=f.type) for f in schema], schema=schema)
    else:
        # Align rows with schema keys
        aligned_rows = []
        for r in all_rows:
            aligned = {}
            for field in schema:
                aligned[field.name] = r.get(field.name)
            aligned_rows.append(aligned)
            
        columns = {field.name: [r[field.name] for r in aligned_rows] for field in schema}
        table = pa.Table.from_pydict(columns, schema=schema)
        
    pq.write_table(table, tmp_path)
    os.replace(tmp_path, out_path)
    return out_path


def process_document(
    record: ManifestRecord,
    chunks: List[Dict],
    provider: ProviderAdapter,
    dim: int
) -> Tuple[str, List[Dict], int, int, int]:
    """Returns (outcome, findings, total, reused, generated). Outcome: PASS, WARNING, FAIL."""
    doc_id = record.doc_id
    logger.info(f"Stage 8 started for {doc_id}")
    
    doc_dir = EMBEDDINGS_DIR / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = doc_dir / "embeddings.parquet"
    checkpoint_path = doc_dir / "embeddings.checkpoint.jsonl"
    
    # Finding 3: corrupted parquet must surface EMBEDDING_ARTIFACT_READABLE
    # as a Critical finding, never be silently treated as empty.
    try:
        existing_lookup = load_existing_embeddings(parquet_path)
    except CorruptedArtifactError as exc:
        logger.error(f"FATAL_EMBEDDING_FAILED: {exc}")
        return "FAIL", [_finding(SEVERITY_ERROR, "EMBEDDING_ARTIFACT_READABLE", str(exc))], 0, 0, 0

    reuse_rows, generate_chunks = determine_workload(chunks, existing_lookup, provider, dim)
    
    completed_checkpoints = load_checkpoint(checkpoint_path)
    
    # Filter generate_chunks to exclude those already checkpointed in this run
    pending_chunks = []
    for c in generate_chunks:
        emb_id = build_embedding_id(c["chunk_id"], provider)
        if emb_id in completed_checkpoints:
            # check if it matches the current config + text
            chk = compute_text_checksum(c["text"])
            cfg = compute_config_fingerprint(provider, dim)
            cpt = completed_checkpoints[emb_id]
            if cpt.get("text_checksum") == chk and cpt.get("config_fingerprint") == cfg:
                reuse_rows.append(cpt)
            else:
                pending_chunks.append(c)
        else:
            pending_chunks.append(c)
            
    logger.info(f"Doc {doc_id}: {len(reuse_rows)} reused, {len(pending_chunks)} to generate")
    
    batch_size = BATCH_SIZE
    if provider.max_batch_size:
        batch_size = min(BATCH_SIZE, provider.max_batch_size)
        
    generated_rows = []
    config_fp = compute_config_fingerprint(provider, dim)
    
    for i in range(0, len(pending_chunks), batch_size):
        batch = pending_chunks[i:i+batch_size]
        texts = [c["text"] for c in batch]
        
        # Rate limiting
        if provider.requests_per_minute:
            sleep_time = 60.0 / provider.requests_per_minute
            time.sleep(sleep_time)
            logger.info(f"WARNING_EMBEDDING_RATE_LIMITED: Throttled {sleep_time:.2f}s")
            
        success = False
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                vectors = provider.embed_batch(texts)
                if len(vectors) != len(texts):
                    raise RuntimeError("Provider returned mismatched vector count")
                success = True
                if attempt > 0:
                    logger.info("WARNING_EMBEDDING_RETRY: Transient error recovered")
                break
            except Exception as exc:
                last_exc = exc
                if provider.is_transient_error(exc):
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(2 ** (attempt + 1))
                        continue
                else:
                    break
        
        if not success:
            logger.error(f"FATAL_EMBEDDING_FAILED: Batch failed. Last err: {last_exc}")
            return "FAIL", [_finding(SEVERITY_ERROR, "FATAL_EMBEDDING_FAILED", str(last_exc))], 0, 0, 0
            
        # Process success
        for j, c in enumerate(batch):
            row = {
                "embedding_id": build_embedding_id(c["chunk_id"], provider),
                "chunk_id": c["chunk_id"],
                "doc_id": doc_id,
                "provider": provider.provider_name,
                "model_name": provider.model_name,
                "model_version": provider.model_version,
                "embedding_dimension": dim,
                "embedding_vector": vectors[j],
                "text_checksum": compute_text_checksum(c["text"]),
                "config_fingerprint": config_fp,
                "created_at": get_now_iso(),
                "embedding_pipeline_version": EMBEDDING_PIPELINE_VERSION,
                "source_chunk_char_count": len(c["text"])
            }
            generated_rows.append(row)
            _write_checkpoint_row(checkpoint_path, row)
            
    # Finding 2 — Namespace separation (Architecture Decision 9):
    # A model/provider change produces a different embedding_id because
    # build_embedding_id encodes provider+model_name+model_version.
    # Old-config rows persist in the parquet alongside new-config rows;
    # nothing is overwritten. This is the architecture's explicit intent:
    # "new embedding_id namespace → every chunk gets new rows; nothing
    #  overwritten, old rows persist until a future pruning stage."
    final_rows_dict = {}
    for r in existing_lookup.values():
        final_rows_dict[r["embedding_id"]] = r
    for r in reuse_rows:
        final_rows_dict[r["embedding_id"]] = r
    for r in generated_rows:
        final_rows_dict[r["embedding_id"]] = r
        
    final_rows = list(final_rows_dict.values())
    
    findings = validate_embeddings(final_rows, chunks, provider, dim)
    if checkpoint_path.exists():
        findings.append(_finding(SEVERITY_WARNING, "EMBEDDING_CHECKPOINT_LEFTOVER", "Checkpoint not yet cleaned up"))
        
    has_error = any(f["severity"] == SEVERITY_ERROR for f in findings)
    
    if has_error:
        # If Critical findings exist, do not persist to parquet to protect the artifact
        return "FAIL", findings, 0, 0, 0
        
    # Persist and cleanup
    try:
        persist_embeddings(doc_id, final_rows)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            # Remove the LEFTOVER finding since we cleaned it
            findings = [f for f in findings if f["code"] != "EMBEDDING_CHECKPOINT_LEFTOVER"]
    except Exception as exc:
        logger.error(f"FATAL_EMBEDDING_FAILED: Parquet write failed: {exc}")
        return "FAIL", findings + [_finding(SEVERITY_ERROR, "EMBEDDING_ARTIFACT_READABLE", str(exc))], 0, 0, 0
        
    has_warning = any(f["severity"] == SEVERITY_WARNING for f in findings)
    return "WARNING" if has_warning else "PASS", findings, len(final_rows), len(reuse_rows), len(generated_rows)

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def write_validation_report(doc_id: str, findings: List[Dict], outcome: str, total: int, reused: int, generated: int, dim: int, fp: str) -> Path:
    error_count = sum(1 for f in findings if f["severity"] == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f["severity"] == SEVERITY_WARNING)
    
    report = {
        "doc_id": doc_id,
        "embedding_pipeline_version": EMBEDDING_PIPELINE_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "validated_at": get_now_iso(),
        "outcome": outcome,
        "summary": {
            "outcome": outcome,
            "error_count": error_count,
            "warning_count": warning_count,
            "finding_count": len(findings),
        },
        "stats": {
            "total_embeddings": total,
            "reused_count": reused,
            "generated_count": generated,
            "avg_embedding_dimension": dim,
            "distinct_config_fingerprints": 1
        },
        "findings": findings
    }
    
    doc_dir = EMBEDDINGS_DIR / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    out_path = doc_dir / "embedding_validation_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return out_path

def update_manifest(record: ManifestRecord, outcome: str, parquet_path: Optional[Path], report_path: Path):
    record.completed_at = get_now_iso()
    record.pipeline_version = PIPELINE_VERSION
    record.artifact_paths["embedding_validation_report"] = str(report_path).replace("\\", "/")
    
    if outcome in ("PASS", "WARNING"):
        record.error_code = None
        # A successful re-run must lift a quarantine imposed by an earlier failed
        # embedding attempt — otherwise one transient failure excludes the document
        # from retrieval forever.
        if record.status == DocumentStatus.QUARANTINED:
            record.status = DocumentStatus.READY_FOR_CHUNKING
        if parquet_path:
            record.artifact_paths["embeddings"] = str(parquet_path).replace("\\", "/")
    else:
        record.status = DocumentStatus.QUARANTINED
        record.error_code = "FATAL_EMBEDDING_FAILED"


def _discover_dimension_from_parquet(
    manifest: Dict[str, ManifestRecord], provider: ProviderAdapter
) -> Optional[int]:
    """Try to read embedding_dimension from an existing parquet artifact.

    Finding 4: avoid unnecessary provider calls on fully cached reruns.
    If a valid parquet already exists, we can read the dimension from it
    instead of calling the provider.

    Only rows produced by the *current* provider identity are considered —
    a parquet left behind by a different provider/model (e.g. the 4-dim stub)
    must never supply the dimension for this run.
    """
    for record in manifest.values():
        emb_path = record.artifact_paths.get("embeddings")
        if emb_path and Path(emb_path).exists():
            try:
                table = pq.read_table(Path(emb_path))
                for row in table.to_pylist():
                    if (
                        row.get("provider") == provider.provider_name
                        and row.get("model_name") == provider.model_name
                        and row.get("model_version") == provider.model_version
                    ):
                        return row["embedding_dimension"]
            except Exception:
                continue
    return None


def run_stage8(provider: ProviderAdapter) -> None:
    manifest = load_manifest()

    # Finding 4: Defer dimension discovery to avoid unnecessary provider calls.
    # First try to read from an existing parquet; only call the provider when
    # actual generation is needed. This ensures fully cached reruns make zero
    # provider calls while preserving the "discover from first returned vector"
    # contract for actual generation runs.
    dim: Optional[int] = _discover_dimension_from_parquet(manifest, provider)
    dim_discovered_from_provider = False

    for doc_id, record in manifest.items():
        if "chunks" not in record.artifact_paths:
            continue

        chunks_path = Path(record.artifact_paths["chunks"])
        if not chunks_path.exists():
            continue

        # Finding 1: Per-document crash isolation (Architecture Decision 17).
        # Same try/except boundary as every prior stage — one document's
        # failure never blocks the batch.
        try:
            with open(chunks_path, 'r', encoding='utf-8') as f:
                chunks_data = json.load(f)
            chunks = chunks_data.get("chunks", [])
            if not chunks:
                continue

            # Lazy dimension discovery: call provider only when we actually
            # need to generate and haven't discovered dimensions yet.
            if dim is None:
                try:
                    dummy_vec = provider.embed_batch(["dummy"])[0]
                    dim = len(dummy_vec)
                    dim_discovered_from_provider = True
                except Exception as exc:
                    logger.error(f"FATAL_EMBEDDING_PROVIDER_UNAVAILABLE: {exc}")
                    return

            outcome, findings, total, reused, generated = process_document(record, chunks, provider, dim)

            doc_dir = EMBEDDINGS_DIR / doc_id
            parquet_path = doc_dir / "embeddings.parquet"

            fp = compute_config_fingerprint(provider, dim)

            report_path = write_validation_report(doc_id, findings, outcome, total, reused, generated, dim, fp)

            update_manifest(record, outcome, parquet_path if outcome != "FAIL" else None, report_path)

        except Exception as exc:
            logger.error(f"Stage 8 crashed for {doc_id}: {exc}")
            record.status = DocumentStatus.QUARANTINED
            record.error_code = "FATAL_EMBEDDING_FAILED"
            record.completed_at = get_now_iso()
            record.pipeline_version = PIPELINE_VERSION

    save_manifest(manifest)

if __name__ == "__main__":
    # Uses the provider configured in .env (EMBEDDING_PROVIDER + credential), the same
    # composition path the backend itself uses — DEPLOYMENT.md documents this command as
    # the way to build a production index, so it must never silently fall back to a stub.
    from scripts.backend_server import _build_registrations
    from scripts.application_bootstrap import bootstrap_application

    _app = bootstrap_application(registrations=_build_registrations(), env=None, dotenv_path=".env")
    run_stage8(_app["embedding_adapter"])
