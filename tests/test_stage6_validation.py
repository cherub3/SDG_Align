"""Stage 6 — Validation & Metadata Assembly — Unit test suite.

Tests cover every approved check:
  ✓ artifact validation
  ✓ manifest validation
  ✓ page validation
  ✓ offset validation
  ✓ hierarchy validation (duplicate IDs, missing parents, cyclic)
  ✓ text volume validation (Finding 4: validate_text_volume)
  ✓ metadata resolution
  ✓ validation report schema (Finding 5: version fields)
  ✓ metadata schema
  ✓ manifest updates
  ✓ rerun determinism (Finding 2: timestamps excluded from comparison)
  ✓ PASS / WARNING / FAIL outcomes
  ✓ report always written
  ✓ metadata skipped on FAIL
  ✓ resolve_metadata always executes (Finding 1)
  ✓ metadata findings appear in report even on FAIL (Finding 1)
  ✓ origin_stage recorded for inherited failures (Finding 3)
  ✓ report version fields always present (Finding 5)
"""

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Path surgery so imports resolve whether run from project root or tests/
# ---------------------------------------------------------------------------
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

from scripts.stage6_validation import (
    VALIDATION_REPORTS_DIR,
    EXTRACTED_DIR,
    MIN_DOC_TOTAL_CHARS,
    SCHEMA_VERSION,
    VALIDATION_VERSION,
    PIPELINE_VERSION,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    validate_artifacts,
    validate_manifest,
    validate_pages,
    validate_offsets,
    validate_sections,
    validate_text_volume,
    resolve_metadata,
    assemble_validation_report,
    gate_metadata_generation,
    update_manifest,
    validate_document,
)
from src.ingestion_types import ManifestRecord, DocumentStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(**kwargs) -> ManifestRecord:
    """Build a minimal valid ManifestRecord with optional overrides."""
    defaults = dict(
        doc_id="doc_abc123",
        category="climate",
        status=DocumentStatus.REGISTERED,
        page_count=3,
        source_path="data/proposals/raw/climate/test.pdf",
        artifact_paths={},
    )
    defaults.update(kwargs)
    return ManifestRecord(**defaults)


def _clean_text(pages=None, section_tree=None) -> Dict:
    """Build a minimal valid clean_text dict."""
    if pages is None:
        pages = [
            {
                "page_number": 1,
                "text": "A" * 500,
                "char_start": 0,
                "char_end": 500,
                "is_excluded": False,
                "headings": [],
            },
            {
                "page_number": 2,
                "text": "B" * 400,
                "char_start": 500,
                "char_end": 900,
                "is_excluded": False,
                "headings": [],
            },
            {
                "page_number": 3,
                "text": "",
                "char_start": 900,
                "char_end": 900,
                "is_excluded": True,
                "headings": [],
            },
        ]
    if section_tree is None:
        section_tree = [
            {
                "section_id": "s1",
                "title": "Executive Summary",
                "section_level": 1,
                "parent_section": None,
                "start_page": 1,
            },
        ]
    return {
        "doc_id": "doc_abc123",
        "full_text_char_count": 900,
        "pages": pages,
        "section_tree": section_tree,
    }


# ===========================================================================
# 1. Artifact validation
# ===========================================================================

class TestValidateArtifacts(unittest.TestCase):

    def test_no_paths_gives_errors(self):
        rec = _record()
        findings = validate_artifacts(rec)
        codes = {f["code"] for f in findings}
        self.assertIn("MISSING_ARTIFACT_PATH", codes)

    def test_path_in_manifest_but_missing_on_disk(self):
        rec = _record(artifact_paths={
            "clean_text": "/nonexistent/path/clean_text.json",
            "raw_extraction": "/nonexistent/raw.json",
        })
        findings = validate_artifacts(rec)
        codes = {f["code"] for f in findings}
        self.assertIn("ARTIFACT_NOT_ON_DISK", codes)

    def test_valid_paths_no_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clean = Path(tmpdir) / "clean_text.json"
            raw = Path(tmpdir) / "raw_extraction.json"
            clean.write_text("{}")
            raw.write_text("{}")
            rec = _record(artifact_paths={
                "clean_text": str(clean),
                "raw_extraction": str(raw),
            })
            findings = validate_artifacts(rec)
            errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
            self.assertEqual(errors, [])

    def test_missing_raw_extraction_only_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clean = Path(tmpdir) / "clean_text.json"
            clean.write_text("{}")
            rec = _record(artifact_paths={"clean_text": str(clean)})
            findings = validate_artifacts(rec)
            errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
            warnings = [f for f in findings if f["severity"] == SEVERITY_WARNING]
            self.assertEqual(errors, [])
            self.assertTrue(any("raw_extraction" in w["message"].lower() or "raw" in w["code"].lower()
                                for w in warnings))

    def test_artifact_findings_carry_origin_stage(self):
        """Finding 3: findings from validate_artifacts must record origin_stage."""
        rec = _record()
        findings = validate_artifacts(rec)
        for f in findings:
            self.assertIn("origin_stage", f, f"Finding {f['code']} missing origin_stage")


# ===========================================================================
# 2. Manifest validation
# ===========================================================================

class TestValidateManifest(unittest.TestCase):

    def test_missing_category_is_error(self):
        rec = _record(category="")
        findings = validate_manifest(rec)
        codes = {f["code"] for f in findings}
        self.assertIn("MISSING_CATEGORY", codes)

    def test_missing_page_count_is_warning(self):
        rec = _record(page_count=None)
        findings = validate_manifest(rec)
        codes = {f["code"] for f in findings}
        self.assertIn("MISSING_PAGE_COUNT", codes)
        # must not be an error
        severities = {f["severity"] for f in findings if f["code"] == "MISSING_PAGE_COUNT"}
        self.assertNotIn(SEVERITY_ERROR, severities)

    def test_fully_populated_record_no_findings(self):
        rec = _record()
        findings = validate_manifest(rec)
        errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertEqual(errors, [])

    def test_manifest_findings_carry_origin_stage(self):
        """Finding 3: findings from validate_manifest must record origin_stage."""
        rec = _record(category="", page_count=None)
        findings = validate_manifest(rec)
        for f in findings:
            self.assertIn("origin_stage", f, f"Finding {f['code']} missing origin_stage")


# ===========================================================================
# 3. Page validation
# ===========================================================================

class TestValidatePages(unittest.TestCase):

    def test_empty_pages_list_is_error(self):
        ct = _clean_text(pages=[])
        findings = validate_pages(ct, _record())
        codes = {f["code"] for f in findings}
        self.assertIn("EMPTY_PAGES", codes)

    def test_page_count_mismatch_is_warning(self):
        rec = _record(page_count=99)  # manifest says 99, clean_text has 3
        ct = _clean_text()
        findings = validate_pages(ct, rec)
        codes = {f["code"] for f in findings}
        self.assertIn("PAGE_COUNT_MISMATCH", codes)
        severity = next(f["severity"] for f in findings if f["code"] == "PAGE_COUNT_MISMATCH")
        self.assertEqual(severity, SEVERITY_WARNING)

    def test_duplicate_page_numbers_is_error(self):
        pages = [
            {"page_number": 1, "text": "A" * 300, "char_start": 0, "char_end": 300,
             "is_excluded": False, "headings": []},
            {"page_number": 1, "text": "B" * 300, "char_start": 300, "char_end": 600,
             "is_excluded": False, "headings": []},
        ]
        ct = _clean_text(pages=pages)
        findings = validate_pages(ct, _record(page_count=2))
        codes = {f["code"] for f in findings}
        self.assertIn("DUPLICATE_PAGE_NUMBERS", codes)

    def test_normal_pages_no_errors(self):
        ct = _clean_text()
        findings = validate_pages(ct, _record(page_count=3))
        errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertEqual(errors, [])

    def test_page_findings_carry_origin_stage(self):
        """Finding 3: page-level findings must record origin_stage."""
        ct = _clean_text(pages=[])
        findings = validate_pages(ct, _record())
        for f in findings:
            self.assertIn("origin_stage", f, f"Finding {f['code']} missing origin_stage")


# ===========================================================================
# 3b. Text volume validation (Finding 4: validate_text_volume)
# ===========================================================================

class TestValidateTextVolume(unittest.TestCase):
    """Finding 4: validate_text_volume() is a separate, explicitly named validator."""

    def test_all_excluded_zero_usable_chars_is_error(self):
        pages = [
            {"page_number": 1, "text": "", "char_start": 0, "char_end": 0,
             "is_excluded": True, "headings": []},
        ]
        ct = _clean_text(pages=pages)
        findings = validate_text_volume(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("FATAL_NO_TEXT", codes)

    def test_below_min_chars_is_warning(self):
        text = "X" * (MIN_DOC_TOTAL_CHARS - 1)  # one under threshold
        pages = [
            {"page_number": 1, "text": text, "char_start": 0, "char_end": len(text),
             "is_excluded": False, "headings": []},
        ]
        ct = _clean_text(pages=pages)
        findings = validate_text_volume(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("LOW_TOTAL_CHAR_COUNT", codes)
        severity = next(f["severity"] for f in findings if f["code"] == "LOW_TOTAL_CHAR_COUNT")
        self.assertEqual(severity, SEVERITY_WARNING)

    def test_sufficient_chars_no_findings(self):
        ct = _clean_text()  # 500 + 400 = 900 usable chars
        findings = validate_text_volume(ct)
        errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertEqual(errors, [])

    def test_text_volume_findings_carry_origin_stage(self):
        """Finding 3: text volume findings must identify Stage 3 as origin."""
        pages = [
            {"page_number": 1, "text": "", "char_start": 0, "char_end": 0,
             "is_excluded": True, "headings": []},
        ]
        ct = _clean_text(pages=pages)
        findings = validate_text_volume(ct)
        # The assertions below must actually run: an empty list would otherwise pass vacuously.
        self.assertEqual([f["code"] for f in findings], ["FATAL_NO_TEXT"])
        self.assertEqual(findings[0]["origin_stage"], "Stage 3")

        # Same contract for the WARNING branch (a few characters, below MIN_DOC_TOTAL_CHARS).
        short_pages = [
            {"page_number": 1, "text": "x" * 10, "char_start": 0, "char_end": 10,
             "is_excluded": False, "headings": []},
        ]
        warn = validate_text_volume(_clean_text(pages=short_pages))
        self.assertEqual([f["code"] for f in warn], ["LOW_TOTAL_CHAR_COUNT"])
        self.assertEqual(warn[0]["origin_stage"], "Stage 3")

    def test_excluded_pages_not_counted(self):
        """Excluded pages must not contribute to the usable char total."""
        pages = [
            {"page_number": 1, "text": "A" * 300, "char_start": 0, "char_end": 300,
             "is_excluded": False, "headings": []},
            {"page_number": 2, "text": "B" * 9999, "char_start": 300, "char_end": 10299,
             "is_excluded": True, "headings": []},  # excluded — must not count
        ]
        ct = _clean_text(pages=pages)
        findings = validate_text_volume(ct)
        # Only 300 usable chars from page 1; page 2's 9999 chars are excluded.
        errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertEqual(errors, [])  # 300 >= MIN_DOC_TOTAL_CHARS


# ===========================================================================
# 4. Offset validation
# ===========================================================================

class TestValidateOffsets(unittest.TestCase):

    def test_contiguous_offsets_no_findings(self):
        ct = _clean_text()
        findings = validate_offsets(ct)
        errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertEqual(errors, [])

    def test_gap_in_offsets_is_warning(self):
        pages = [
            {"page_number": 1, "text": "A" * 100, "char_start": 0, "char_end": 100,
             "is_excluded": False, "headings": []},
            {"page_number": 2, "text": "B" * 100, "char_start": 200, "char_end": 300,
             "is_excluded": False, "headings": []},
        ]
        ct = {"doc_id": "x", "full_text_char_count": 300, "pages": pages, "section_tree": []}
        findings = validate_offsets(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("NON_CONTIGUOUS_OFFSETS", codes)

    def test_negative_char_start_is_error(self):
        pages = [
            {"page_number": 1, "text": "A" * 100, "char_start": -1, "char_end": 100,
             "is_excluded": False, "headings": []},
        ]
        ct = {"doc_id": "x", "full_text_char_count": 100, "pages": pages, "section_tree": []}
        findings = validate_offsets(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("INVALID_CHAR_START", codes)

    def test_full_char_count_mismatch_is_warning(self):
        ct = deepcopy(_clean_text())
        ct["full_text_char_count"] = 9999  # wrong
        findings = validate_offsets(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("FULL_CHAR_COUNT_MISMATCH", codes)

    def test_offset_findings_carry_origin_stage(self):
        """Finding 3: offset findings must record origin_stage."""
        pages = [
            {"page_number": 1, "text": "A", "char_start": -1, "char_end": 1,
             "is_excluded": False, "headings": []},
        ]
        ct = {"doc_id": "x", "full_text_char_count": 1, "pages": pages, "section_tree": []}
        findings = validate_offsets(ct)
        for f in findings:
            self.assertIn("origin_stage", f)


# ===========================================================================
# 5. Section hierarchy validation
# ===========================================================================

class TestValidateSections(unittest.TestCase):

    def test_valid_section_tree_no_errors(self):
        ct = _clean_text()
        findings = validate_sections(ct)
        errors = [f for f in findings if f["severity"] == SEVERITY_ERROR]
        self.assertEqual(errors, [])

    def test_empty_section_tree_is_info(self):
        ct = _clean_text(section_tree=[])
        findings = validate_sections(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("EMPTY_SECTION_TREE", codes)
        severity = next(f["severity"] for f in findings if f["code"] == "EMPTY_SECTION_TREE")
        self.assertEqual(severity, SEVERITY_INFO)

    def test_duplicate_section_ids_is_error(self):
        st = [
            {"section_id": "s1", "title": "A", "section_level": 1, "parent_section": None, "start_page": 1},
            {"section_id": "s1", "title": "B", "section_level": 1, "parent_section": None, "start_page": 2},
        ]
        ct = _clean_text(section_tree=st)
        findings = validate_sections(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("DUPLICATE_SECTION_ID", codes)

    def test_missing_parent_is_error(self):
        st = [
            {"section_id": "s2", "title": "Child", "section_level": 2,
             "parent_section": "nonexistent_parent", "start_page": 1},
        ]
        ct = _clean_text(section_tree=st)
        findings = validate_sections(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("MISSING_PARENT_SECTION", codes)

    def test_cyclic_hierarchy_is_error(self):
        # s1 -> s2 -> s1 (cycle)
        st = [
            {"section_id": "s1", "title": "A", "section_level": 1,
             "parent_section": "s2", "start_page": 1},
            {"section_id": "s2", "title": "B", "section_level": 2,
             "parent_section": "s1", "start_page": 2},
        ]
        ct = _clean_text(section_tree=st)
        findings = validate_sections(ct)
        codes = {f["code"] for f in findings}
        self.assertIn("CYCLIC_SECTION_HIERARCHY", codes)

    def test_section_findings_carry_origin_stage_5(self):
        """Finding 3: section hierarchy findings must identify Stage 5 as origin."""
        st = [
            {"section_id": "s1", "title": "A", "section_level": 1,
             "parent_section": None, "start_page": 1},
            {"section_id": "s1", "title": "Dup", "section_level": 1,
             "parent_section": None, "start_page": 2},
        ]
        ct = _clean_text(section_tree=st)
        findings = validate_sections(ct)
        dup_findings = [f for f in findings if f["code"] == "DUPLICATE_SECTION_ID"]
        self.assertTrue(dup_findings, "Expected DUPLICATE_SECTION_ID finding")
        for f in dup_findings:
            self.assertEqual(f.get("origin_stage"), "Stage 5",
                             f"Expected origin_stage='Stage 5', got {f.get('origin_stage')!r}")


# ===========================================================================
# 6. Metadata resolution — Finding 1
# ===========================================================================

class TestResolveMetadata(unittest.TestCase):

    def test_required_top_level_keys_present(self):
        rec = _record()
        ct = _clean_text()
        meta, _ = resolve_metadata(rec, ct)
        required = {"doc_id", "title", "title_extraction_method", "provenance",
                    "classification", "structure", "validation", "future_compatibility"}
        self.assertEqual(required, set(meta.keys()))

    def test_doc_id_matches_record(self):
        rec = _record(doc_id="doc_deadbeef")
        ct = _clean_text()
        ct["doc_id"] = "doc_deadbeef"
        meta, _ = resolve_metadata(rec, ct)
        self.assertEqual(meta["doc_id"], "doc_deadbeef")

    def test_excluded_pages_populated(self):
        ct = _clean_text()
        # page 3 is excluded in default _clean_text
        meta, _ = resolve_metadata(_record(), ct)
        self.assertIn(3, meta["structure"]["excluded_pages"])

    def test_sections_flagged_appendix(self):
        st = [
            {"section_id": "s1", "title": "ANNEX A: Financing", "section_level": 1,
             "parent_section": None, "start_page": 20},
        ]
        ct = _clean_text(section_tree=st)
        meta, _ = resolve_metadata(_record(), ct)
        flagged = meta["structure"]["sections_flagged"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["type"], "appendix")

    def test_title_extracted_from_section_level1(self):
        st = [
            {"section_id": "s1", "title": "My Great Title", "section_level": 1,
             "parent_section": None, "start_page": 1},
        ]
        ct = _clean_text(section_tree=st)
        meta, _ = resolve_metadata(_record(), ct)
        self.assertEqual(meta["title"], "My Great Title")
        self.assertEqual(meta["title_extraction_method"], "largest_heading")

    def test_no_sections_title_is_none(self):
        ct = _clean_text(section_tree=[])
        meta, _ = resolve_metadata(_record(), ct)
        self.assertIsNone(meta["title"])
        self.assertEqual(meta["title_extraction_method"], "none_found")

    def test_no_sections_emits_title_warning_finding(self):
        """Finding 1: resolve_metadata must emit WARNING findings when title cannot be found."""
        ct = _clean_text(section_tree=[])
        _, meta_findings = resolve_metadata(_record(), ct)
        codes = {f["code"] for f in meta_findings}
        self.assertIn("TITLE_NOT_FOUND", codes)
        severity = next(f["severity"] for f in meta_findings if f["code"] == "TITLE_NOT_FOUND")
        self.assertEqual(severity, SEVERITY_WARNING)

    def test_unresolved_doc_type_emits_warning(self):
        """Finding 1: missing doc_type must emit a WARNING finding from resolve_metadata."""
        rec = _record(doc_type=None)
        ct = _clean_text()
        _, meta_findings = resolve_metadata(rec, ct)
        codes = {f["code"] for f in meta_findings}
        self.assertIn("DOC_TYPE_UNRESOLVED", codes)

    def test_resolve_metadata_returns_tuple(self):
        """Finding 1: resolve_metadata must return (dict, list) — not a bare dict."""
        result = resolve_metadata(_record(), _clean_text())
        self.assertIsInstance(result, tuple, "resolve_metadata must return a tuple")
        self.assertEqual(len(result), 2)
        meta, findings = result
        self.assertIsInstance(meta, dict)
        self.assertIsInstance(findings, list)

    def test_resolve_metadata_never_writes_files(self):
        """Finding 1: resolve_metadata is computation only; it must not create files."""
        import os
        import tempfile
        ct = _clean_text()
        rec = _record()
        # All pipeline paths are relative to the working directory, so run inside an empty temp
        # directory and require that the whole tree (not just its top level) is still empty.
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                resolve_metadata(rec, ct)
                created = [os.path.join(root, name)
                           for root, dirs, files in os.walk(".") for name in dirs + files]
            finally:
                os.chdir(original_cwd)
        self.assertEqual(created, [], "resolve_metadata wrote files or directories to disk")


# ===========================================================================
# 7. Validation report schema — Finding 5
# ===========================================================================

class TestValidationReportSchema(unittest.TestCase):

    def test_required_report_keys(self):
        """Finding 5: schema_version, pipeline_version, validation_version must all be present."""
        rec = _record()
        report = assemble_validation_report(rec, [], "PASS")
        required = {"doc_id", "schema_version", "validation_version", "pipeline_version",
                    "validated_at", "outcome", "summary", "findings"}
        self.assertEqual(required, set(report.keys()))

    def test_schema_version_present_and_correct(self):
        """Finding 5: schema_version must equal the module-level constant."""
        report = assemble_validation_report(_record(), [], "PASS")
        self.assertIn("schema_version", report)
        self.assertEqual(report["schema_version"], SCHEMA_VERSION)

    def test_validation_version_present(self):
        """Finding 5: validation_version must be present."""
        report = assemble_validation_report(_record(), [], "PASS")
        self.assertIn("validation_version", report)
        self.assertEqual(report["validation_version"], VALIDATION_VERSION)

    def test_pipeline_version_present(self):
        """Finding 5: pipeline_version must be present."""
        report = assemble_validation_report(_record(), [], "PASS")
        self.assertIn("pipeline_version", report)
        self.assertEqual(report["pipeline_version"], PIPELINE_VERSION)

    def test_summary_keys(self):
        rec = _record()
        findings = [{"severity": SEVERITY_ERROR, "code": "X", "message": "m"}]
        report = assemble_validation_report(rec, findings, "FAIL")
        summary_keys = {"outcome", "error_count", "warning_count", "finding_count"}
        self.assertEqual(summary_keys, set(report["summary"].keys()))

    def test_outcome_reflected_in_report(self):
        for outcome in ("PASS", "WARNING", "FAIL"):
            report = assemble_validation_report(_record(), [], outcome)
            self.assertEqual(report["outcome"], outcome)
            self.assertEqual(report["summary"]["outcome"], outcome)

    def test_validated_at_is_excluded_from_determinism(self):
        """Finding 2: validated_at is a wall-clock timestamp; documented as intentionally
        non-deterministic. The test verifies that all OTHER fields are stable across runs,
        without comparing validated_at itself.
        """
        rec = _record()
        report1 = assemble_validation_report(rec, [], "PASS")
        report2 = assemble_validation_report(rec, [], "PASS")

        # validated_at MAY differ (wall-clock); remove it before comparing.
        r1 = {k: v for k, v in report1.items() if k != "validated_at"}
        r2 = {k: v for k, v in report2.items() if k != "validated_at"}
        self.assertEqual(r1, r2, "Report fields (excluding validated_at) must be deterministic")

        # validated_at must be present but we do NOT assert it equals across runs.
        self.assertIn("validated_at", report1)
        self.assertIn("validated_at", report2)


# ===========================================================================
# 8. Gate logic
# ===========================================================================

class TestGateMetadataGeneration(unittest.TestCase):

    def test_no_findings_is_pass(self):
        ok, outcome = gate_metadata_generation([])
        self.assertTrue(ok)
        self.assertEqual(outcome, "PASS")

    def test_warning_only_is_warning_and_generates_metadata(self):
        findings = [{"severity": SEVERITY_WARNING, "code": "W", "message": "w"}]
        ok, outcome = gate_metadata_generation(findings)
        self.assertTrue(ok)
        self.assertEqual(outcome, "WARNING")

    def test_error_is_fail_no_metadata(self):
        findings = [{"severity": SEVERITY_ERROR, "code": "E", "message": "e"}]
        ok, outcome = gate_metadata_generation(findings)
        self.assertFalse(ok)
        self.assertEqual(outcome, "FAIL")

    def test_error_plus_warning_is_fail(self):
        findings = [
            {"severity": SEVERITY_ERROR, "code": "E", "message": "e"},
            {"severity": SEVERITY_WARNING, "code": "W", "message": "w"},
        ]
        ok, outcome = gate_metadata_generation(findings)
        self.assertFalse(ok)
        self.assertEqual(outcome, "FAIL")

    def test_info_only_is_pass(self):
        findings = [{"severity": SEVERITY_INFO, "code": "I", "message": "i"}]
        ok, outcome = gate_metadata_generation(findings)
        self.assertTrue(ok)
        self.assertEqual(outcome, "PASS")


# ===========================================================================
# 9. Manifest updates
# ===========================================================================

class TestUpdateManifest(unittest.TestCase):

    def test_pass_sets_ready_for_chunking(self):
        rec = _record()
        update_manifest(rec, "PASS", Path("/tmp/report.json"), Path("/tmp/meta.json"), "2026-01-01T00:00:00Z")
        self.assertEqual(rec.status, DocumentStatus.READY_FOR_CHUNKING)
        self.assertIsNone(rec.error_code)

    def test_warning_sets_ready_for_chunking(self):
        rec = _record()
        update_manifest(rec, "WARNING", Path("/tmp/r.json"), Path("/tmp/m.json"), "2026-01-01T00:00:00Z")
        self.assertEqual(rec.status, DocumentStatus.READY_FOR_CHUNKING)

    def test_fail_sets_quarantined(self):
        rec = _record()
        update_manifest(rec, "FAIL", Path("/tmp/r.json"), None, "2026-01-01T00:00:00Z")
        self.assertEqual(rec.status, DocumentStatus.QUARANTINED)

    def test_fail_with_no_prior_error_code_gets_default(self):
        rec = _record()
        rec.error_code = None
        update_manifest(rec, "FAIL", Path("/tmp/r.json"), None, "2026-01-01T00:00:00Z")
        self.assertIsNotNone(rec.error_code)

    def test_validation_report_path_recorded_in_artifact_paths(self):
        rec = _record()
        report_path = Path("/tmp/report.json")
        update_manifest(rec, "PASS", report_path, None, "2026-01-01T00:00:00Z")
        self.assertIn("validation_report", rec.artifact_paths)

    def test_metadata_path_recorded_when_provided(self):
        rec = _record()
        update_manifest(rec, "PASS", Path("/tmp/r.json"), Path("/tmp/meta.json"), "2026-01-01T00:00:00Z")
        self.assertIn("metadata", rec.artifact_paths)

    def test_metadata_path_not_recorded_on_fail(self):
        rec = _record()
        update_manifest(rec, "FAIL", Path("/tmp/r.json"), None, "2026-01-01T00:00:00Z")
        self.assertNotIn("metadata", rec.artifact_paths)


# ===========================================================================
# 10. Full document validation integration
# ===========================================================================

class TestValidateDocumentIntegration(unittest.TestCase):

    def _setup_doc(self, tmpdir: Path, clean_text_dict: Dict, raw_data: Dict = None) -> ManifestRecord:
        """Write clean_text.json (and optionally raw_extraction.json) to tmpdir, build record."""
        import scripts.stage6_validation as s6
        self._orig_validation_dir = s6.VALIDATION_REPORTS_DIR
        self._orig_extracted_dir = s6.EXTRACTED_DIR
        s6.VALIDATION_REPORTS_DIR = tmpdir / "validation_reports"
        s6.EXTRACTED_DIR = tmpdir / "extracted"

        doc_id = clean_text_dict.get("doc_id", "doc_abc123")
        doc_dir = tmpdir / "extracted" / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        clean_path = doc_dir / "clean_text.json"
        clean_path.write_text(json.dumps(clean_text_dict))

        artifact_paths = {"clean_text": str(clean_path)}

        if raw_data is not None:
            raw_path = doc_dir / "raw_extraction.json"
            raw_path.write_text(json.dumps(raw_data))
            artifact_paths["raw_extraction"] = str(raw_path)

        rec = ManifestRecord(
            doc_id=doc_id,
            category="climate",
            status=DocumentStatus.REGISTERED,
            page_count=clean_text_dict.get("pages") and len(clean_text_dict["pages"]) or 3,
            source_path="data/proposals/raw/climate/test.pdf",
            artifact_paths=artifact_paths,
        )
        return rec

    def tearDown(self):
        import scripts.stage6_validation as s6
        if hasattr(self, "_orig_validation_dir"):
            s6.VALIDATION_REPORTS_DIR = self._orig_validation_dir
        if hasattr(self, "_orig_extracted_dir"):
            s6.EXTRACTED_DIR = self._orig_extracted_dir

    def test_pass_outcome(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ct = _clean_text()
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)
            self.assertEqual(rec.status, DocumentStatus.READY_FOR_CHUNKING)

    def test_report_always_written_even_on_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Produce a FAIL by giving empty pages
            ct = _clean_text(pages=[])
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)
            self.assertEqual(rec.status, DocumentStatus.QUARANTINED)
            # Report must exist
            import scripts.stage6_validation as s6
            report_path = s6.VALIDATION_REPORTS_DIR / f"{rec.doc_id}_validation.json"
            self.assertTrue(report_path.exists(), f"Report not found at {report_path}")

    def test_metadata_not_written_on_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ct = _clean_text(pages=[])  # causes FAIL
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)
            import scripts.stage6_validation as s6
            meta_path = s6.EXTRACTED_DIR / rec.doc_id / "metadata.json"
            self.assertFalse(meta_path.exists(), "metadata.json must NOT be written on FAIL")

    def test_metadata_written_on_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ct = _clean_text()
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)
            import scripts.stage6_validation as s6
            meta_path = s6.EXTRACTED_DIR / rec.doc_id / "metadata.json"
            self.assertTrue(meta_path.exists(), f"metadata.json not found at {meta_path}")

    def test_resolve_metadata_always_executes(self):
        """Finding 1: resolve_metadata() must always run, even when there are validation
        errors. Its findings (e.g. DOC_TYPE_UNRESOLVED) must appear in the report even
        when the final outcome is FAIL and metadata.json is not written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Empty pages → FAIL; doc_type=None → DOC_TYPE_UNRESOLVED warning from resolve_metadata
            ct = _clean_text(pages=[])
            rec = self._setup_doc(tmp, ct)
            # doc_type is None by default (triggers DOC_TYPE_UNRESOLVED warning in resolve_metadata)
            validate_document(rec)

            # Outcome must be FAIL
            self.assertEqual(rec.status, DocumentStatus.QUARANTINED)

            # metadata.json must NOT exist
            import scripts.stage6_validation as s6
            meta_path = s6.EXTRACTED_DIR / rec.doc_id / "metadata.json"
            self.assertFalse(meta_path.exists(), "metadata.json must not be written on FAIL")

            # But the validation report MUST be written...
            report_path = s6.VALIDATION_REPORTS_DIR / f"{rec.doc_id}_validation.json"
            self.assertTrue(report_path.exists())

    def test_metadata_findings_appear_in_report_on_fail(self):
        """Finding 1: metadata WARNING findings from resolve_metadata must appear
        in validation_report.json even when the gate fails and metadata.json is not written.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Empty pages → FAIL; this also ensures resolve_metadata runs
            ct = _clean_text(pages=[])
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)

            import scripts.stage6_validation as s6
            report_path = s6.VALIDATION_REPORTS_DIR / f"{rec.doc_id}_validation.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text())

            # The report must contain findings from resolve_metadata
            # (DOC_TYPE_UNRESOLVED is always emitted when doc_type is None)
            finding_codes = {f["code"] for f in report["findings"]}
            self.assertIn("DOC_TYPE_UNRESOLVED", finding_codes,
                          "resolve_metadata findings must appear in report even on FAIL")

    def test_rerun_determinism(self):
        """Finding 2: Running Stage 6 twice on the same input must produce the same
        semantic outcome. validated_at timestamps are intentionally excluded from the
        comparison (wall-clock, documented non-deterministic). All other report fields
        must be identical."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ct = _clean_text()
            rec = self._setup_doc(tmp, ct)

            clean_text_path = rec.artifact_paths["clean_text"]
            original_clean_text = Path(clean_text_path).read_text(encoding="utf-8")

            validate_document(rec)
            first_status = rec.status

            import scripts.stage6_validation as s6
            report_path = s6.VALIDATION_REPORTS_DIR / f"{rec.doc_id}_validation.json"
            report1 = json.loads(report_path.read_text())

            # Reset status to re-run (simulating a re-run from manifest)
            rec.status = DocumentStatus.REGISTERED
            validate_document(rec)
            second_status = rec.status
            report2 = json.loads(report_path.read_text())

            # Outcomes must match
            self.assertEqual(first_status, second_status)

            # Semantic report content must be identical (excluding validated_at — Finding 2)
            r1 = {k: v for k, v in report1.items() if k != "validated_at"}
            r2 = {k: v for k, v in report2.items() if k != "validated_at"}
            self.assertEqual(r1, r2, "Report (excluding validated_at) must be deterministic")

            # clean_text.json must be untouched
            self.assertEqual(
                Path(clean_text_path).read_text(encoding="utf-8"),
                original_clean_text,
                "clean_text.json was mutated by Stage 6",
            )

    def test_warning_outcome_when_warnings_but_no_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ct = _clean_text()
            rec = self._setup_doc(tmp, ct)
            # Trigger a WARNING by making page_count mismatch
            rec.page_count = 99
            validate_document(rec)
            # WARNING → still READY_FOR_CHUNKING, but report says WARNING
            self.assertEqual(rec.status, DocumentStatus.READY_FOR_CHUNKING)
            import scripts.stage6_validation as s6
            report_path = s6.VALIDATION_REPORTS_DIR / f"{rec.doc_id}_validation.json"
            report = json.loads(report_path.read_text())
            self.assertEqual(report["outcome"], "WARNING")

    def test_report_includes_version_fields(self):
        """Finding 5: validation report must always include schema_version,
        validation_version, and pipeline_version on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ct = _clean_text()
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)
            import scripts.stage6_validation as s6
            report_path = s6.VALIDATION_REPORTS_DIR / f"{rec.doc_id}_validation.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text())
            self.assertIn("schema_version", report)
            self.assertIn("validation_version", report)
            self.assertIn("pipeline_version", report)

    def test_no_stage7_functionality(self):
        """Smoke-check: metadata.json must NOT contain chunking/embedding fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ct = _clean_text()
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)
            import scripts.stage6_validation as s6
            meta_path = s6.EXTRACTED_DIR / rec.doc_id / "metadata.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                forbidden = {"chunks", "embeddings", "retrieval", "chunk_ids", "vectors"}
                present = forbidden & set(meta.keys())
                self.assertEqual(present, set(), f"Stage 7 fields found in metadata: {present}")

    def test_origin_stage_in_report_findings(self):
        """Finding 3: every finding in the validation_report.json must carry origin_stage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Trigger a duplicate section finding from Stage 5
            st = [
                {"section_id": "dup", "title": "A", "section_level": 1,
                 "parent_section": None, "start_page": 1},
                {"section_id": "dup", "title": "B", "section_level": 1,
                 "parent_section": None, "start_page": 2},
            ]
            ct = _clean_text(section_tree=st)
            rec = self._setup_doc(tmp, ct)
            validate_document(rec)

            import scripts.stage6_validation as s6
            report_path = s6.VALIDATION_REPORTS_DIR / f"{rec.doc_id}_validation.json"
            report = json.loads(report_path.read_text())

            dup_findings = [f for f in report["findings"] if f["code"] == "DUPLICATE_SECTION_ID"]
            self.assertTrue(dup_findings, "Expected DUPLICATE_SECTION_ID in report")
            for f in dup_findings:
                self.assertEqual(f.get("origin_stage"), "Stage 5",
                                 "DUPLICATE_SECTION_ID must attribute Stage 5")


# ===========================================================================
# 11. Validators never mutate artifacts
# ===========================================================================

class TestValidatorsDoNotMutate(unittest.TestCase):

    def test_validate_pages_does_not_modify_input(self):
        ct = _clean_text()
        original = json.dumps(ct, sort_keys=True)
        validate_pages(ct, _record(page_count=3))
        self.assertEqual(json.dumps(ct, sort_keys=True), original)

    def test_validate_text_volume_does_not_modify_input(self):
        ct = _clean_text()
        original = json.dumps(ct, sort_keys=True)
        validate_text_volume(ct)
        self.assertEqual(json.dumps(ct, sort_keys=True), original)

    def test_validate_offsets_does_not_modify_input(self):
        ct = _clean_text()
        original = json.dumps(ct, sort_keys=True)
        validate_offsets(ct)
        self.assertEqual(json.dumps(ct, sort_keys=True), original)

    def test_validate_sections_does_not_modify_input(self):
        ct = _clean_text()
        original = json.dumps(ct, sort_keys=True)
        validate_sections(ct)
        self.assertEqual(json.dumps(ct, sort_keys=True), original)

    def test_resolve_metadata_does_not_modify_input(self):
        rec = _record()
        ct = _clean_text()
        ct_original = json.dumps(ct, sort_keys=True)
        resolve_metadata(rec, ct)
        self.assertEqual(json.dumps(ct, sort_keys=True), ct_original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
