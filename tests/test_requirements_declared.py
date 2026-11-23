"""Every third-party package imported by the code that CI runs must be declared in a requirements file.

CI installs only requirements.txt + requirements-dev.txt. A package that is present in a developer's venv only as a
transitive dependency of an optional package (scipy via sentence-transformers) passes locally and fails in CI.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _declared(*files):
    names = set()
    for f in files:
        for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z0-9_.\-]+)\s*==", line)
            if m:
                names.add(m.group(1).lower().replace("_", "-"))
    return names


def test_scipy_is_pinned_in_the_ci_install_set():
    ci = _declared("requirements.txt", "requirements-dev.txt")
    assert "scipy" in ci, "tools/eval_retrieval.py and its test import scipy; CI never installs requirements-local.txt"


def test_scipy_is_not_only_in_the_optional_local_file():
    assert "scipy" not in _declared("requirements-local.txt")


def test_every_requirement_in_the_ci_set_is_pinned_exactly():
    for f in ("requirements.txt", "requirements-dev.txt"):
        for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
            s = line.split("#")[0].strip()
            if s:
                assert "==" in s, f"{f}: {s!r} is not pinned"
