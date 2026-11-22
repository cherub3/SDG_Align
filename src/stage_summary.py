"""Shared outcome reporting and exit codes for the ingestion stage CLIs (stages 0-9).

Before this module every stage logged per-document failures and still exited 0, so a pipeline run
(or CI) could not tell "everything worked" from "documents were lost". Each ``run_stageN()`` now
records which documents it attempted and returns a :class:`StageSummary`; the ``__main__`` block of
each stage turns that into a process exit code.

Policy
------
* A document the stage **attempted** and that ended QUARANTINED / FAILED is a *failure* (exit 1),
  except for codes listed in ``EXPECTED_QUARANTINE_CODES`` (currently only ``FATAL_NO_TEXT``: a
  scanned PDF with no OCR path is an expected, documented outcome, not a malfunction).
* Stage-level failures that are not tied to one document (embedding provider unavailable, an index
  build that aborted) are always failures.
* ``--strict`` turns expected quarantines into failures as well.
* Exit codes: 0 = no failures, 1 = at least one failure.
"""
import argparse
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from src.ingestion_types import DocumentStatus, ManifestRecord

# Quarantine reasons that are an expected, documented outcome rather than a malfunction.
EXPECTED_QUARANTINE_CODES = frozenset({"FATAL_NO_TEXT"})

_FAILED_STATUSES = (DocumentStatus.QUARANTINED, DocumentStatus.FAILED)


@dataclass
class StageSummary:
    stage: str
    attempted: int = 0
    succeeded: int = 0
    failed: List[Tuple[str, Optional[str]]] = field(default_factory=list)               # (doc_id, error_code)
    expected_quarantines: List[Tuple[str, Optional[str]]] = field(default_factory=list)  # (doc_id, error_code)
    stage_failures: List[str] = field(default_factory=list)                              # not tied to one document

    def failure_count(self, strict: bool = False) -> int:
        count = len(self.failed) + len(self.stage_failures)
        if strict:
            count += len(self.expected_quarantines)
        return count

    def exit_code(self, strict: bool = False) -> int:
        return 1 if self.failure_count(strict) else 0

    def render(self, strict: bool = False) -> str:
        lines = [
            f"[{self.stage}] attempted={self.attempted} succeeded={self.succeeded} "
            f"failed={len(self.failed)} expected_quarantine={len(self.expected_quarantines)} "
            f"stage_failures={len(self.stage_failures)}"
        ]
        for doc_id, code in self.failed:
            lines.append(f"  FAILED       {doc_id} ({code})")
        for doc_id, code in self.expected_quarantines:
            label = "FAILED (strict)" if strict else "quarantined  "
            lines.append(f"  {label} {doc_id} ({code})")
        for reason in self.stage_failures:
            lines.append(f"  STAGE FAILURE: {reason}")
        lines.append(f"[{self.stage}] exit code {self.exit_code(strict)}" + (" (--strict)" if strict else ""))
        return "\n".join(lines)


class StageRun:
    """Collects what a stage did while it runs. Usage inside ``run_stageN``::

        run = StageRun("stage4")
        ...
        run.attempt(doc_id)          # just before processing a document
        run.fail("reason")           # a stage-level failure not tied to a document
        ...
        return run.summarize(manifest)
    """

    def __init__(self, stage: str):
        self.stage = stage
        self._attempted: List[str] = []
        self._stage_failures: List[str] = []

    def attempt(self, doc_id: str) -> None:
        if doc_id not in self._attempted:
            self._attempted.append(doc_id)

    def fail(self, reason: str) -> None:
        self._stage_failures.append(reason)

    def summarize(self, manifest: Dict[str, ManifestRecord]) -> StageSummary:
        summary = StageSummary(stage=self.stage, attempted=len(self._attempted),
                               stage_failures=list(self._stage_failures))
        for doc_id in self._attempted:
            record = manifest.get(doc_id)
            if record is not None and record.status in _FAILED_STATUSES:
                bucket = summary.expected_quarantines if record.error_code in EXPECTED_QUARANTINE_CODES else summary.failed
                bucket.append((doc_id, record.error_code))
            else:
                summary.succeeded += 1
        return summary


def finish(summary: StageSummary, strict: bool = False) -> int:
    """Prints the summary and returns the process exit code."""
    print(summary.render(strict))
    return summary.exit_code(strict)


def parse_strict(argv: Optional[Iterable[str]] = None) -> bool:
    parser = argparse.ArgumentParser(description="Run this ingestion stage over data/proposals/.")
    parser.add_argument("--strict", action="store_true",
                        help="also exit non-zero when a document is quarantined for an expected reason "
                             "(e.g. FATAL_NO_TEXT for scanned PDFs)")
    return parser.parse_args(list(argv) if argv is not None else None).strict


def cli_main(run_fn: Callable[[], StageSummary], argv: Optional[Iterable[str]] = None) -> None:
    """Entry point for a stage's ``if __name__ == "__main__"`` block."""
    strict = parse_strict(argv)
    sys.exit(finish(run_fn(), strict))
