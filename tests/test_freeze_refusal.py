"""The evaluator must refuse to run when the frozen gold set or any frozen clean text differs."""
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import eval_retrieval as ev  # noqa: E402
import freeze_gold as fg  # noqa: E402
import gold_common as gc  # noqa: E402


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    """A tiny self-contained frozen setup (no corpus needed): gold file, split file, FROZEN file, fake clean-text hashes."""
    gold = tmp_path / "gold_set.jsonl"
    split = tmp_path / "gold_split.json"
    frozen = tmp_path / "GOLD_FROZEN.txt"
    gold.write_text(json.dumps({"qid": "Q1", "type": "single_fact", "question": "q?", "evidence": []}) + "\n", encoding="utf-8")
    split.write_text(json.dumps({"split": {"Q1": "test"}}), encoding="utf-8")
    clean = {"docA": "alpha text", "docB": "beta text"}
    monkeypatch.setattr(fg, "GOLD", str(gold))
    monkeypatch.setattr(fg, "SPLIT", str(split))
    monkeypatch.setattr(fg, "FROZEN", str(frozen))
    monkeypatch.setattr(fg, "clean_hashes", lambda: {n: gc.sha256_text(t) for n, t in clean.items()})
    frozen.write_text("\n".join([f"gold_set.jsonl={fg.sha_file(str(gold))}", f"gold_split.json={fg.sha_file(str(split))}"] +
                                [f"clean_text:{n}={gc.sha256_text(t)}" for n, t in clean.items()]) + "\n", encoding="utf-8")
    return gold, clean, monkeypatch


def test_untouched_passes(synthetic):
    assert fg.check_frozen() == []


def test_tampered_gold_is_refused(synthetic):
    gold, _, _ = synthetic
    gold.write_text(gold.read_text(encoding="utf-8").replace("q?", "q!"), encoding="utf-8")
    assert "gold_set.jsonl changed" in fg.check_frozen()
    with pytest.raises(SystemExit) as e:
        ev.evaluate("test", lambda q: [], "x")
    assert "REFUSING TO RUN" in str(e.value)


def test_tampered_clean_text_is_refused(synthetic):
    _, clean, mp = synthetic
    clean["docB"] += " edited"
    mp.setattr(fg, "clean_hashes", lambda: {n: gc.sha256_text(t) for n, t in clean.items()})
    assert fg.check_frozen() == ["clean text changed: docB"]
    with pytest.raises(SystemExit) as e:
        ev.evaluate("test", lambda q: [], "x")
    assert "docB" in str(e.value)


@pytest.mark.skipif(not os.path.exists(fg.FROZEN) or not gc.doc_names(), reason="needs the real corpus")
def test_real_frozen_files_tampered_copy(tmp_path, monkeypatch):
    assert fg.check_frozen() == []                      # the real, untouched files pass
    copy = tmp_path / "gold_set.jsonl"
    shutil.copy(fg.GOLD, copy)
    copy.write_text(copy.read_text(encoding="utf-8").replace("Q001", "Q999", 1), encoding="utf-8")
    monkeypatch.setattr(fg, "GOLD", str(copy))
    assert "gold_set.jsonl changed" in fg.check_frozen()
    monkeypatch.undo()
    real_load = gc.load_doc
    name, doc = sorted(gc.doc_names().items())[0]

    def tampered(d):
        r = real_load(d)
        if d == doc:
            r = dict(r, clean=r["clean"] + " ")
        return r
    monkeypatch.setattr(gc, "load_doc", tampered)
    assert fg.check_frozen() == [f"clean text changed: {name}"]
