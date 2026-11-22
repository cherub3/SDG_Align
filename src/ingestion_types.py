from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional

# Manifest error codes that more than one module needs to name. (Other codes are plain strings.)
# FAILED_VALIDATION: stage 6 ran and found a Critical finding (document is readable but its
# structure/offsets are inconsistent). Distinct from FATAL_UNREADABLE (a file would not open or parse).
ERROR_FAILED_VALIDATION = "FAILED_VALIDATION"


class DocumentStatus(str, Enum):
    REGISTERED = "registered"
    QUARANTINED = "quarantined"
    READY_FOR_CHUNKING = "ready_for_chunking"
    FAILED = "failed"

@dataclass
class ManifestRecord:
    doc_id: str
    category: str
    status: DocumentStatus
    doc_type: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    pipeline_version: Optional[str] = None
    error_code: Optional[str] = None
    page_count: Optional[int] = None
    source_path: Optional[str] = None
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "category": self.category,
            "doc_type": self.doc_type,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "pipeline_version": self.pipeline_version,
            "error_code": self.error_code,
            "page_count": self.page_count,
            "source_path": self.source_path,
            "artifact_paths": self.artifact_paths
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ManifestRecord':
        return cls(
            doc_id=data.get("doc_id", ""),
            category=data.get("category", ""),
            status=DocumentStatus(data.get("status", "registered")),
            doc_type=data.get("doc_type"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            pipeline_version=data.get("pipeline_version"),
            error_code=data.get("error_code"),
            page_count=data.get("page_count"),
            source_path=data.get("source_path"),
            artifact_paths=data.get("artifact_paths", {})
        )
