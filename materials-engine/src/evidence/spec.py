"""Evidence record specification.

Phase III.H: Structured evidence import — manual, CSV, JSON, literature notes.
All evidence must declare its source type and confidence level.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List

log = logging.getLogger(__name__)

EVIDENCE_DIR = "artifacts/evidence"
REGISTRY_FILE = "evidence_registry.json"

SOURCE_TYPES = [
    "manual_entry",
    "csv_import",
    "json_import",
    "literature_note",
    "external_db_note",
    "benchmark_known",
]

EVIDENCE_LEVELS = [
    "known_external",
    "manual_unverified",
    "manual_verified",
    "literature_reported",
    "benchmark_known",
]


class EvidenceValidationError(ValueError):
    pass


@dataclass
class EvidenceRecord:
    """A single piece of external evidence for a material property."""
    evidence_id: str = ""
    source_type: str = "manual_entry"
    source_ref: str = ""
    formula: str = ""
    spacegroup: Optional[int] = None
    material_id: Optional[str] = None
    linked_validation_id: Optional[str] = None
    linked_candidate_id: Optional[str] = None

    property_name: str = ""
    observed_value: Optional[float] = None
    observed_unit: str = ""
    observed_condition_temperature_K: Optional[float] = None
    observed_condition_pressure_GPa: Optional[float] = None

    evidence_level: str = "manual_unverified"
    reviewer: str = ""
    source_note: str = ""
    provenance_note: str = ""
    created_at: str = ""
    tags: List[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.formula:
            raise EvidenceValidationError("formula required")
        if not self.property_name:
            raise EvidenceValidationError("property_name required")
        if self.source_type not in SOURCE_TYPES:
            raise EvidenceValidationError(f"Unknown source_type: {self.source_type}")
        if self.evidence_level not in EVIDENCE_LEVELS:
            raise EvidenceValidationError(f"Unknown evidence_level: {self.evidence_level}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceRecord":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


class EvidenceRegistry:
    """Persistent registry of imported evidence."""

    def __init__(self, output_dir: str = EVIDENCE_DIR):
        self.output_dir = output_dir
        self._records: List[EvidenceRecord] = []

    @property
    def size(self) -> int:
        return len(self._records)

    def add(self, record: EvidenceRecord) -> str:
        now = datetime.now(timezone.utc).isoformat()
        if not record.evidence_id:
            record.evidence_id = hashlib.sha256(
                f"ev|{record.formula}|{record.property_name}|{now}".encode()
            ).hexdigest()[:12]
        if not record.created_at:
            record.created_at = now
        record.validate()
        self._records.append(record)
        return record.evidence_id

    def get(self, evidence_id: str) -> Optional[EvidenceRecord]:
        for r in self._records:
            if r.evidence_id == evidence_id:
                return r
        return None

    def find_by_formula(self, formula: str) -> List[EvidenceRecord]:
        return [r for r in self._records if r.formula == formula]

    def find_by_property(self, prop: str) -> List[EvidenceRecord]:
        return [r for r in self._records if r.property_name == prop]

    def status(self) -> dict:
        from collections import Counter
        by_type = Counter(r.source_type for r in self._records)
        by_level = Counter(r.evidence_level for r in self._records)
        by_prop = Counter(r.property_name for r in self._records)
        return {
            "total": self.size,
            "by_source_type": dict(by_type),
            "by_evidence_level": dict(by_level),
            "by_property": dict(by_prop),
        }

    def import_json(self, data: list) -> dict:
        """Import evidence records from a list of dicts."""
        added = 0
        errors = 0
        for d in data:
            try:
                r = EvidenceRecord.from_dict(d)
                r.source_type = r.source_type or "json_import"
                self.add(r)
                added += 1
            except Exception as e:
                log.warning("Evidence import error: %s", e)
                errors += 1
        return {"added": added, "errors": errors}

    def import_csv_rows(self, rows: List[dict]) -> dict:
        """Import from CSV-like dicts (formula, property_name, observed_value, ...)."""
        added = 0
        errors = 0
        for row in rows:
            try:
                r = EvidenceRecord(
                    formula=str(row.get("formula", "")),
                    property_name=str(row.get("property_name", "")),
                    observed_value=float(row["observed_value"]) if row.get("observed_value") is not None else None,
                    observed_unit=str(row.get("observed_unit", "")),
                    source_type="csv_import",
                    evidence_level=str(row.get("evidence_level", "manual_unverified")),
                    reviewer=str(row.get("reviewer", "")),
                    source_note=str(row.get("source_note", "")),
                )
                self.add(r)
                added += 1
            except Exception as e:
                log.warning("CSV import error: %s", e)
                errors += 1
        return {"added": added, "errors": errors}

    def save(self) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, REGISTRY_FILE)
        with open(path, "w") as f:
            json.dump([r.to_dict() for r in self._records], f, indent=2)
        return path

    def load(self) -> bool:
        path = os.path.join(self.output_dir, REGISTRY_FILE)
        if not os.path.exists(path):
            return False
        with open(path) as f:
            data = json.load(f)
        self._records = [EvidenceRecord.from_dict(d) for d in data]
        return True
