"""Tests for scripts/download_corpus.py (the corpus verify helper; no download source is configured)."""
import hashlib
import json

import pytest

from scripts import download_corpus as dc


def _place(raw_dir, category, name, content):
    path = raw_dir / category / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_corpus_list_is_well_formed():
    assert len(dc.CORPUS) == 13
    names = [n for _c, n, _h, _u in dc.CORPUS]
    assert len(set(names)) == len(names)                         # no duplicate filenames
    for category, name, digest, url in dc.CORPUS:
        assert name.endswith(".pdf") and category
        assert len(digest) == 64 and int(digest, 16) >= 0          # a real sha-256 hex digest
        assert url is None                                       # no source URL is configured: none may be invented
    # the ecuador_biodiversity PDF belongs to biodiversity (it was originally filed under climate)
    assert ("biodiversity", "ecuador_biodiversity.pdf") in [(c, n) for c, n, _h, _u in dc.CORPUS]


def test_check_reports_every_missing_file(tmp_path, capsys):
    assert dc.check(tmp_path) == len(dc.CORPUS)
    out = capsys.readouterr().out
    assert out.count("MISSING") == len(dc.CORPUS)


def test_check_accepts_matching_files_and_flags_a_modified_one(tmp_path, monkeypatch, capsys):
    good, bad = b"original pdf bytes", b"a different document"
    monkeypatch.setattr(dc, "CORPUS", [
        ("cat", "a.pdf", hashlib.sha256(good).hexdigest(), None),
        ("cat", "b.pdf", hashlib.sha256(good).hexdigest(), None),
        ("cat", "c.pdf", hashlib.sha256(good).hexdigest(), None),
    ])
    _place(tmp_path, "cat", "a.pdf", good)       # correct
    _place(tmp_path, "cat", "b.pdf", bad)        # wrong content
    # c.pdf is missing
    assert dc.check(tmp_path) == 2
    out = capsys.readouterr().out
    assert "OK        " in out and "a.pdf" in out
    assert "MISMATCH" in out and "b.pdf" in out
    assert "MISSING" in out and "c.pdf" in out


def test_main_check_exit_codes(tmp_path, monkeypatch):
    # RAW_DIR is relative to the working directory, so run inside an isolated temp "project".
    good = b"x"
    monkeypatch.setattr(dc, "CORPUS", [("cat", "a.pdf", hashlib.sha256(good).hexdigest(), None)])
    monkeypatch.chdir(tmp_path)
    assert dc.main(["--check"]) == 1                       # file not placed yet
    _place(tmp_path / "data" / "proposals" / "raw", "cat", "a.pdf", good)
    assert dc.main(["--check"]) == 0                       # placed and hash matches


def test_print_manifest_is_valid_json_without_urls(capsys):
    assert dc.main(["--print-manifest"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 13
    assert all(item["source_url"] is None for item in data)


def test_no_arguments_prints_help_and_signals_not_configured(capsys):
    assert dc.main([]) == 2
    captured = capsys.readouterr()
    assert "No download source is configured" in captured.err
    assert "--check" in captured.out
