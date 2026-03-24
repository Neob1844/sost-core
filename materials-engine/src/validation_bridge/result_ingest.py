"""Result ingestion — import validation results and link to candidates.

Supports JSON, CSV, and manual entry. Each result links back to a candidate_id
and triggers reconciliation + calibration update.
"""
import json, csv, os, time


class ValidationResult:
    """A single validation observation for a candidate."""

    def __init__(self, candidate_id, job_id=None, **kwargs):
        self.candidate_id = candidate_id
        self.job_id = job_id
        self.validation_source = kwargs.get("validation_source", "unknown")
        self.validation_type = kwargs.get("validation_type", "unknown")
        self.observed_fe = kwargs.get("observed_fe")
        self.observed_bg = kwargs.get("observed_bg")
        self.structure_status = kwargs.get("structure_status", "unknown")
        self.convergence_notes = kwargs.get("convergence_notes", "")
        self.result_confidence = kwargs.get("result_confidence", "medium")
        self.human_notes = kwargs.get("human_notes", "")
        self.timestamp = kwargs.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.provenance = kwargs.get("provenance", "")

    def to_dict(self):
        return {
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "validation_source": self.validation_source,
            "validation_type": self.validation_type,
            "observed_fe": self.observed_fe,
            "observed_bg": self.observed_bg,
            "structure_status": self.structure_status,
            "convergence_notes": self.convergence_notes,
            "result_confidence": self.result_confidence,
            "human_notes": self.human_notes,
            "timestamp": self.timestamp,
            "provenance": self.provenance,
        }


def ingest_json(path):
    """Import validation results from a JSON file.

    Expected format: {"results": [{"candidate_id": "...", "observed_fe": ..., ...}]}
    """
    with open(path) as f:
        data = json.load(f)
    results = []
    for entry in data.get("results", []):
        cid = entry.get("candidate_id")
        if not cid:
            continue
        filtered = {k: v for k, v in entry.items() if k not in ("candidate_id", "job_id")}
        results.append(ValidationResult(cid, entry.get("job_id"), **filtered))
    return results


def ingest_csv(path):
    """Import validation results from a CSV file.

    Required columns: candidate_id. Optional: observed_fe, observed_bg, etc.
    """
    results = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("candidate_id")
            if not cid:
                continue
            kwargs = {}
            if row.get("observed_fe"):
                try:
                    kwargs["observed_fe"] = float(row["observed_fe"])
                except ValueError:
                    pass
            if row.get("observed_bg"):
                try:
                    kwargs["observed_bg"] = float(row["observed_bg"])
                except ValueError:
                    pass
            for field in ("validation_source", "validation_type", "structure_status",
                          "convergence_notes", "result_confidence", "human_notes", "provenance"):
                if row.get(field):
                    kwargs[field] = row[field]
            results.append(ValidationResult(cid, row.get("job_id"), **kwargs))
    return results


def ingest_manual(candidate_id, observed_fe=None, observed_bg=None,
                   validation_source="manual", validation_type="manual_review",
                   notes="", confidence="low"):
    """Create a single manual validation result."""
    return ValidationResult(
        candidate_id,
        validation_source=validation_source,
        validation_type=validation_type,
        observed_fe=observed_fe,
        observed_bg=observed_bg,
        result_confidence=confidence,
        human_notes=notes,
    )
