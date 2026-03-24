"""Handoff registry — tracks candidates through validation lifecycle.

Stores candidate records with unique IDs, lifecycle state, handoff packs,
and validation results. Persisted as JSON.
"""
import json, os, time, hashlib
from .lifecycle import can_transition, LIFECYCLE_STATES


def _make_candidate_id(formula, method, parent_a="", timestamp=None):
    """Generate a deterministic candidate ID."""
    ts = timestamp or int(time.time())
    raw = f"{formula}:{method}:{parent_a}:{ts}"
    return "cand_" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _make_job_id(candidate_id):
    """Generate a job ID from candidate ID."""
    return "job_" + hashlib.sha256(f"{candidate_id}:{time.time()}".encode()).hexdigest()[:12]


class HandoffRegistry:
    """Persistent registry of candidates in the validation pipeline."""

    def __init__(self, path=None):
        self.path = path or os.path.expanduser(
            "~/SOST/materials-engine-discovery/validation_registry.json")
        self.records = {}  # candidate_id → record dict
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                self.records = data.get("records", {})
            except Exception:
                self.records = {}

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({"records": self.records, "count": len(self.records),
                        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ")},
                       f, indent=2, default=str)

    def register_candidate(self, formula, method, parent_a="", handoff_pack=None,
                            initial_state="DFT_handoff_ready"):
        """Register a candidate for validation tracking."""
        cid = _make_candidate_id(formula, method, parent_a)
        record = {
            "candidate_id": cid,
            "formula": formula,
            "method": method,
            "parent_a": parent_a,
            "state": initial_state,
            "state_history": [{"state": initial_state, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ")}],
            "handoff_pack": handoff_pack,
            "job_id": None,
            "validation_result": None,
            "reconciliation": None,
            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.records[cid] = record
        return cid

    def transition(self, candidate_id, new_state, notes=""):
        """Transition a candidate to a new lifecycle state."""
        if candidate_id not in self.records:
            return False, f"unknown candidate: {candidate_id}"
        rec = self.records[candidate_id]
        current = rec["state"]
        if not can_transition(current, new_state):
            return False, f"invalid transition: {current} → {new_state}"
        rec["state"] = new_state
        rec["state_history"].append({
            "state": new_state,
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "notes": notes,
        })
        return True, f"{current} → {new_state}"

    def hand_off(self, candidate_id):
        """Mark candidate as handed off for validation."""
        ok, msg = self.transition(candidate_id, "handed_off", "handed off to validation queue")
        if ok:
            self.records[candidate_id]["job_id"] = _make_job_id(candidate_id)
            self.transition(candidate_id, "validation_pending", "awaiting validation result")
        return ok, msg

    def get_record(self, candidate_id):
        return self.records.get(candidate_id)

    def get_by_state(self, state):
        return [r for r in self.records.values() if r["state"] == state]

    def get_pending(self):
        return self.get_by_state("validation_pending")

    def get_all_handoff_ready(self):
        return self.get_by_state("DFT_handoff_ready")

    def count_by_state(self):
        counts = {}
        for r in self.records.values():
            s = r["state"]
            counts[s] = counts.get(s, 0) + 1
        return counts

    def summary(self):
        return {
            "total_records": len(self.records),
            "by_state": self.count_by_state(),
            "pending_count": len(self.get_pending()),
            "handoff_ready_count": len(self.get_all_handoff_ready()),
        }
