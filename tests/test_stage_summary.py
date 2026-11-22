"""Tests for the stage CLI outcome summary and exit-code policy (Phase 0, item E)."""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ingestion_types import DocumentStatus, ManifestRecord
from src.stage_summary import StageRun, StageSummary, cli_main, finish

REPO_ROOT = Path(__file__).resolve().parent.parent


def _rec(doc_id, status, code=None):
    return ManifestRecord(doc_id=doc_id, category="c", status=status, error_code=code)


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def _manifest():
    return {
        "ok": _rec("ok", DocumentStatus.READY_FOR_CHUNKING),
        "scan": _rec("scan", DocumentStatus.QUARANTINED, "FATAL_NO_TEXT"),
        "bad": _rec("bad", DocumentStatus.QUARANTINED, "FATAL_UNREADABLE"),
        "failed": _rec("failed", DocumentStatus.FAILED, "FATAL_EMBEDDING_FAILED"),
        "skipped": _rec("skipped", DocumentStatus.QUARANTINED, "FATAL_UNREADABLE"),  # never attempted this run
    }


def test_summarize_classifies_each_attempted_document():
    run = StageRun("stageX")
    for doc_id in ("ok", "scan", "bad", "failed"):
        run.attempt(doc_id)
    s = run.summarize(_manifest())
    assert (s.attempted, s.succeeded) == (4, 1)
    assert s.failed == [("bad", "FATAL_UNREADABLE"), ("failed", "FATAL_EMBEDDING_FAILED")]
    assert s.expected_quarantines == [("scan", "FATAL_NO_TEXT")]


def test_documents_not_attempted_in_this_run_are_ignored():
    run = StageRun("stageX")
    run.attempt("ok")
    s = run.summarize(_manifest())
    assert s.failed == [] and s.exit_code() == 0  # 'skipped' failed in an earlier stage, not this one


def test_any_unexpected_failure_exits_1():
    run = StageRun("stageX")
    run.attempt("bad")
    assert run.summarize(_manifest()).exit_code() == 1


def test_expected_quarantine_exits_0_but_strict_exits_1():
    run = StageRun("stage3")
    run.attempt("scan")
    s = run.summarize(_manifest())
    assert s.exit_code() == 0
    assert s.exit_code(strict=True) == 1


def test_strict_looks_at_the_whole_manifest_not_only_documents_attempted_this_run():
    # A re-run skips documents that are already quarantined; strict must still see them.
    run = StageRun("stage3")
    run.attempt("ok")                      # this run only touched a healthy document
    s = run.summarize(_manifest())         # manifest still contains scan, bad, failed, skipped
    assert s.exit_code() == 0
    assert s.exit_code(strict=True) == 1
    assert {d for d, _ in s.manifest_quarantined} == {"scan", "bad", "failed", "skipped"}
    assert "FAILED (strict, in manifest) skipped" in s.render(strict=True)


def test_strict_is_clean_when_nothing_in_the_manifest_is_quarantined():
    manifest = {"a": _rec("a", DocumentStatus.READY_FOR_CHUNKING), "b": _rec("b", DocumentStatus.REGISTERED)}
    run = StageRun("stageX")
    run.attempt("a")
    assert run.summarize(manifest).exit_code(strict=True) == 0


def test_stage_level_failure_exits_1_even_with_no_failed_documents():
    run = StageRun("stage8")
    run.fail("FATAL_EMBEDDING_PROVIDER_UNAVAILABLE: boom")
    s = run.summarize(_manifest())
    assert s.failed == [] and s.exit_code() == 1


def test_clean_run_exits_0_and_attempting_twice_counts_once():
    clean = {"ok": _rec("ok", DocumentStatus.READY_FOR_CHUNKING)}
    run = StageRun("stageX")
    run.attempt("ok")
    run.attempt("ok")
    s = run.summarize(clean)
    assert (s.attempted, s.succeeded, s.exit_code(), s.exit_code(strict=True)) == (1, 1, 0, 0)


def test_unknown_document_ids_count_as_succeeded():
    run = StageRun("stage0")
    run.attempt("data/proposals/raw/x/a.pdf")  # stage 0 attempts file paths, which are not manifest keys
    assert run.summarize({}).succeeded == 1


def test_render_lists_every_problem(capsys):
    run = StageRun("stage3")
    for d in ("bad", "scan"):
        run.attempt(d)
    run.fail("index abc: corrupt")
    s = run.summarize(_manifest())
    text = s.render()
    assert "FAILED       bad (FATAL_UNREADABLE)" in text
    assert "quarantined   scan (FATAL_NO_TEXT)" in text
    assert "STAGE FAILURE: index abc: corrupt" in text
    assert "FAILED (strict, in manifest) scan (FATAL_NO_TEXT)" in s.render(strict=True)
    assert finish(s) == 1
    assert "[stage3] attempted=2" in capsys.readouterr().out


def test_cli_main_exits_with_the_summary_code_and_honours_strict():
    ok_but_scanned = lambda: StageSummary(  # noqa: E731
        stage="s", expected_quarantines=[("d", "FATAL_NO_TEXT")], manifest_quarantined=[("d", "FATAL_NO_TEXT")])
    with pytest.raises(SystemExit) as plain:
        cli_main(ok_but_scanned, argv=[])
    assert plain.value.code == 0
    with pytest.raises(SystemExit) as strict:
        cli_main(ok_but_scanned, argv=["--strict"])
    assert strict.value.code == 1


# ---------------------------------------------------------------------------
# Per-stage wiring
# ---------------------------------------------------------------------------

def test_stage3_reports_scanned_documents_as_expected_quarantines():
    import scripts.stage3_detection as s3
    manifest = {"scan": _rec("scan", DocumentStatus.REGISTERED), "ok": _rec("ok", DocumentStatus.REGISTERED)}
    for r in manifest.values():
        r.artifact_paths = {"raw_extraction": "x"}

    def fake_process(record):
        if record.doc_id == "scan":
            record.status, record.error_code = DocumentStatus.QUARANTINED, "FATAL_NO_TEXT"

    with patch.object(s3, "load_manifest", return_value=manifest), patch.object(s3, "save_manifest"), \
         patch.object(s3, "process_document", side_effect=fake_process):
        summary = s3.run_stage3()
    assert summary.expected_quarantines == [("scan", "FATAL_NO_TEXT")]
    assert summary.exit_code() == 0 and summary.exit_code(strict=True) == 1


def test_stage3_reports_an_unreadable_document_as_a_failure():
    import scripts.stage3_detection as s3
    manifest = {"bad": _rec("bad", DocumentStatus.REGISTERED)}
    manifest["bad"].artifact_paths = {"raw_extraction": "x"}

    def fake_process(record):
        record.status, record.error_code = DocumentStatus.QUARANTINED, "FATAL_UNREADABLE"

    with patch.object(s3, "load_manifest", return_value=manifest), patch.object(s3, "save_manifest"), \
         patch.object(s3, "process_document", side_effect=fake_process):
        summary = s3.run_stage3()
    assert summary.failed == [("bad", "FATAL_UNREADABLE")] and summary.exit_code() == 1


def test_stage0_unreadable_file_is_a_stage_failure(tmp_path):
    import scripts.stage0_register as s0
    pdf = tmp_path / "cat" / "a.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"x")
    with patch.object(s0, "load_manifest", return_value={}), patch.object(s0, "save_manifest"), \
         patch.object(s0, "discover_documents", return_value=[pdf]), \
         patch.object(s0, "compute_sha256", side_effect=OSError("denied")):
        summary = s0.register_documents()
    assert summary.exit_code() == 1
    assert "could not read" in summary.stage_failures[0]


def test_stage8_provider_unavailable_is_a_stage_failure(tmp_path):
    import scripts.stage8_embedding_generation as s8
    chunks = tmp_path / "chunks.json"
    chunks.write_text(json.dumps({"chunks": [{"chunk_id": "c1", "text": "hello"}]}), encoding="utf-8")
    record = _rec("d1", DocumentStatus.READY_FOR_CHUNKING)
    record.artifact_paths = {"chunks": str(chunks)}

    class DeadProvider(s8.ProviderAdapter):
        def embed_batch(self, texts):
            raise RuntimeError("provider down")

    with patch.object(s8, "load_manifest", return_value={"d1": record}), patch.object(s8, "save_manifest"), \
         patch.object(s8, "_discover_dimension_from_parquet", return_value=None):
        summary = s8.run_stage8(DeadProvider())
    assert summary.exit_code() == 1
    assert "FATAL_EMBEDDING_PROVIDER_UNAVAILABLE" in summary.stage_failures[0]


def test_stage9_with_nothing_to_index_is_a_clean_run():
    import scripts.stage9_vector_indexing as s9
    with patch.object(s9, "load_manifest", return_value={}):
        summary = s9.run_stage9(s9.FAISSAdapter)
    assert summary.exit_code() == 0 and summary.attempted == 0


# ---------------------------------------------------------------------------
# Real process exit codes (subprocess, isolated temp project, no network)
# ---------------------------------------------------------------------------

def _run_stage(module, cwd, *args):
    # The child process must not be measured by pytest-cov: it runs in a temp cwd without the
    # repo's coverage config, so its data would be non-branch and break coverage combination.
    env = {k: v for k, v in os.environ.items() if not k.startswith("COV_CORE")}
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run([sys.executable, "-m", module, *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=120)


def _make_project(tmp_path, with_corrupt):
    import fitz
    raw = tmp_path / "data" / "proposals" / "raw" / "cat"
    raw.mkdir(parents=True)
    doc = fitz.open()
    doc.new_page().insert_text((50, 60), "A perfectly readable page of text. " * 5, fontsize=11)
    doc.save(raw / "good.pdf")
    if with_corrupt:
        (raw / "corrupt.pdf").write_bytes((raw / "good.pdf").read_bytes()[:40])
        (raw / "empty.pdf").write_bytes(b"")
    return tmp_path


def test_stage1_process_exit_code_is_1_when_a_document_is_unreadable(tmp_path):
    project = _make_project(tmp_path, with_corrupt=True)
    assert _run_stage("scripts.stage0_register", project).returncode == 0
    result = _run_stage("scripts.stage1_integrity", project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count("FATAL_UNREADABLE") == 2
    assert "failed=2" in result.stdout


def test_stage1_process_exit_code_is_0_when_every_document_is_readable(tmp_path):
    project = _make_project(tmp_path, with_corrupt=False)
    assert _run_stage("scripts.stage0_register", project).returncode == 0
    result = _run_stage("scripts.stage1_integrity", project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "attempted=1 succeeded=1 failed=0" in result.stdout


def test_failed_validation_is_a_failure_not_an_expected_quarantine():
    run = StageRun("stage6")
    run.attempt("doc")
    s = run.summarize({"doc": _rec("doc", DocumentStatus.QUARANTINED, "FAILED_VALIDATION")})
    assert s.failed == [("doc", "FAILED_VALIDATION")] and s.expected_quarantines == []
    assert s.exit_code() == 1
