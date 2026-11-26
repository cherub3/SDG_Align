"""Fail-fast startup (fix 3) and RETRIEVAL_MODE validation in every configuration (fix 4)."""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.composition_root import compose_application
from scripts.startup_checks import StartupCheckError, verify_serving_data
from src.ingestion_types import DocumentStatus, ManifestRecord

ROOT = Path(__file__).resolve().parent.parent
WIRED = ("local", "BAAI/bge-small-en-v1.5", "v1.5")


class _Emb:
    provider_name, model_name, model_version = WIRED


def _corpus(tmp_path, provider=WIRED, chunks=2, vector_count=2, write_index=True, write_chunks=True, quarantined=False):
    """A minimal on-disk corpus: one manifest record, its chunks file and one index folder."""
    idx = tmp_path / "vector_index" / "fp1"
    idx.mkdir(parents=True)
    (idx / "index_metadata.json").write_text(json.dumps({
        "index_fingerprint": "fp1", "provider": provider[0], "model_name": provider[1], "model_version": provider[2],
        "vector_count": vector_count}), encoding="utf-8")
    if write_index:
        (idx / "index.bin").write_bytes(b"x" * 10)
        (idx / "id_map.parquet").write_bytes(b"x")
    cpath = tmp_path / "chunks.json"
    if write_chunks:
        cpath.write_text(json.dumps({"chunks": [{"chunk_id": f"c{i}"} for i in range(chunks)]}), encoding="utf-8")
    rec = ManifestRecord(doc_id="d1", category="c",
                         status=DocumentStatus.QUARANTINED if quarantined else DocumentStatus.READY_FOR_CHUNKING,
                         artifact_paths={"vector_index": str(idx), "chunks": str(cpath)})
    return {"d1": rec}, tmp_path / "vector_index"


def test_a_complete_corpus_passes(tmp_path):
    manifest, root = _corpus(tmp_path)
    out = verify_serving_data(_Emb(), manifest, root)
    assert out == {"documents": 1, "chunks": 2, "indexes": ["fp1"]}


def test_no_embedding_provider_refuses(tmp_path):
    manifest, root = _corpus(tmp_path)
    with pytest.raises(StartupCheckError, match="EMBEDDING_PROVIDER"):
        verify_serving_data(None, manifest, root)


def test_empty_manifest_refuses(tmp_path):
    _, root = _corpus(tmp_path)
    with pytest.raises(StartupCheckError, match="no servable documents"):
        verify_serving_data(_Emb(), {}, root)


def test_only_quarantined_documents_refuses(tmp_path):
    manifest, root = _corpus(tmp_path, quarantined=True)
    with pytest.raises(StartupCheckError, match="no servable documents"):
        verify_serving_data(_Emb(), manifest, root)


def test_missing_chunks_file_refuses(tmp_path):
    manifest, root = _corpus(tmp_path, write_chunks=False)
    with pytest.raises(StartupCheckError, match="chunks file missing"):
        verify_serving_data(_Emb(), manifest, root)


def test_empty_chunks_file_refuses(tmp_path):
    manifest, root = _corpus(tmp_path, chunks=0)
    with pytest.raises(StartupCheckError, match="empty"):
        verify_serving_data(_Emb(), manifest, root)


def test_missing_index_folder_refuses(tmp_path):
    manifest, _ = _corpus(tmp_path)
    with pytest.raises(StartupCheckError, match="no vector index"):
        verify_serving_data(_Emb(), manifest, tmp_path / "does_not_exist")


def test_index_built_by_another_embedding_model_refuses(tmp_path):
    manifest, root = _corpus(tmp_path, provider=("huggingface", "BAAI/bge-small-en-v1.5", "v1.5"))
    with pytest.raises(StartupCheckError, match="INDEX_EMBEDDING_MODEL_MISMATCH") as e:
        verify_serving_data(_Emb(), manifest, root)
    assert "huggingface" in str(e.value) and "local" in str(e.value)


def test_a_different_model_version_also_refuses(tmp_path):
    manifest, root = _corpus(tmp_path, provider=("local", "BAAI/bge-small-en-v1.5", "v1.4"))
    with pytest.raises(StartupCheckError, match="MISMATCH"):
        verify_serving_data(_Emb(), manifest, root)


def test_empty_index_bin_refuses(tmp_path):
    manifest, root = _corpus(tmp_path)
    (root / "fp1" / "index.bin").write_bytes(b"")
    with pytest.raises(StartupCheckError, match="missing or empty"):
        verify_serving_data(_Emb(), manifest, root)


def test_missing_id_map_refuses(tmp_path):
    manifest, root = _corpus(tmp_path)
    (root / "fp1" / "id_map.parquet").unlink()
    with pytest.raises(StartupCheckError, match="id map"):
        verify_serving_data(_Emb(), manifest, root)


def test_zero_vector_count_refuses(tmp_path):
    manifest, root = _corpus(tmp_path, vector_count=0)
    with pytest.raises(StartupCheckError, match="no vectors"):
        verify_serving_data(_Emb(), manifest, root)


def test_invalid_retrieval_mode_refuses_at_the_same_stage(tmp_path, monkeypatch):
    manifest, root = _corpus(tmp_path)
    monkeypatch.setenv("RETRIEVAL_MODE", "typo")
    with pytest.raises(ValueError, match="RETRIEVAL_MODE"):
        verify_serving_data(_Emb(), manifest, root)


# ---- fix 4: RETRIEVAL_MODE is validated in EVERY configuration, not only when an LLM and an embedder are wired ----

def test_compose_rejects_a_bad_mode_even_with_no_llm_and_no_embedder():
    with pytest.raises(ValueError, match="RETRIEVAL_MODE"):
        compose_application([], env={"RETRIEVAL_MODE": "hybird"})


def test_compose_rejects_a_bad_mode_with_only_a_planner_wired():
    reg = {"seam": "PLANNER_LLM_PROVIDER", "provider_name": "p", "network_dependent": False, "factory": Mock()}
    env = {"PLANNER_LLM_PROVIDER": "p", "PLANNER_LLM_PROVIDER_CREDENTIAL_REF": "env:K", "K": "x", "RETRIEVAL_MODE": "nope"}
    with pytest.raises(ValueError, match="RETRIEVAL_MODE"):
        compose_application([reg], env=env)


def test_compose_accepts_hybrid_dense_and_unset_with_nothing_wired():
    for env in ({}, {"RETRIEVAL_MODE": "hybrid"}, {"RETRIEVAL_MODE": "DENSE "}):
        assert compose_application([], env=env)["llm_adapter"] is None


# ---- the real process: the server must exit non-zero with a clear message, not start "healthy" ----

EXPECTED_STARTUP_MESSAGE = "no servable documents"
# Output of a child that was killed by the machine running out of memory while importing numpy / BLAS, before the server code ran.
ALLOCATION_FAILURE_MARKERS = ("Memory allocation still failed", "paging file is too small", "os error 1455", "MemoryError")


def child_died_from_allocation_failure(output):
    """True only when the child's output shows a memory-allocation failure AND does not contain the message the test is about.
    Any other failure (wrong message, crash, timeout) must still fail the test."""
    return EXPECTED_STARTUP_MESSAGE not in output and any(m in output for m in ALLOCATION_FAILURE_MARKERS)


def test_allocation_failure_detector_skips_only_real_allocation_failures():
    openblas = "OpenBLAS error: Memory allocation still failed after 10 retries, giving up.\n"
    assert child_died_from_allocation_failure(openblas)
    assert child_died_from_allocation_failure("OSError: The paging file is too small for this operation to complete. (os error 1455)")
    assert not child_died_from_allocation_failure("")                                   # silent death is a failure, not a skip
    assert not child_died_from_allocation_failure("Traceback ... ImportError: no module named x")
    assert not child_died_from_allocation_failure(openblas + "StartupCheckError: no servable documents")   # the real message wins


def test_server_process_exits_nonzero_when_the_corpus_is_missing(tmp_path):
    # Strip pytest-cov's child-process hooks: the child measures no branches and would make coverage combine fail in CI.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("LLM_", "PLANNER_", "EMBEDDING_", "COV_CORE", "COVERAGE", "HCA_"))
           and not k.endswith(("_PROVIDER", "_BACKEND", "_STORE", "_REGISTRY", "_ADAPTER"))}
    env.update(PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1", EMBEDDING_PROVIDER="local",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               # One BLAS thread: OpenBLAS reserves memory per thread, and in a full suite run the machine can be short of memory.
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    proc = subprocess.run([sys.executable, "-m", "uvicorn", "scripts.backend_server:app", "--port", "8791"],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=90)
    output = proc.stdout + proc.stderr
    if proc.returncode != 0 and child_died_from_allocation_failure(output):
        pytest.skip("the server child process could not allocate memory (machine out of memory, not a startup-check result): "
                    + output.strip().splitlines()[-1][:200])
    assert proc.returncode != 0
    assert EXPECTED_STARTUP_MESSAGE in output


# ---- the server's own startup function runs the checks and the model warm-up, and never swallows their failure ----

def _instance(adapter):
    return {"embedding_adapter": adapter, "agent_dependencies": object()}


def test_create_application_instance_verifies_data_then_warms_the_embedder(monkeypatch):
    from scripts import backend_server
    order = []
    adapter = Mock()
    monkeypatch.setattr(backend_server, "bootstrap_application", lambda **kw: _instance(adapter))
    monkeypatch.setattr(backend_server, "verify_serving_data", lambda a: order.append("verify") or {"documents": 1})
    adapter.warm_up.side_effect = lambda: order.append("warm")
    assert backend_server._create_application_instance()["embedding_adapter"] is adapter
    assert order == ["verify", "warm"]


def test_create_application_instance_propagates_a_failed_check_and_does_not_warm_up(monkeypatch):
    from scripts import backend_server
    adapter = Mock()
    monkeypatch.setattr(backend_server, "bootstrap_application", lambda **kw: _instance(adapter))

    def refuse(a):
        raise StartupCheckError("no servable documents")
    monkeypatch.setattr(backend_server, "verify_serving_data", refuse)
    with pytest.raises(StartupCheckError):
        backend_server._create_application_instance()
    adapter.warm_up.assert_not_called()


def test_create_application_instance_propagates_a_missing_model(monkeypatch):
    from scripts import backend_server
    adapter = Mock()
    adapter.warm_up.side_effect = RuntimeError("local embedding model is not in the local cache")
    monkeypatch.setattr(backend_server, "bootstrap_application", lambda **kw: _instance(adapter))
    monkeypatch.setattr(backend_server, "verify_serving_data", lambda a: {})
    with pytest.raises(RuntimeError, match="not in the local cache"):
        backend_server._create_application_instance()
