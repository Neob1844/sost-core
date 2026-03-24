"""Batch validation workflows — group candidates for systematic validation.

Manages batches of candidates through the validation lifecycle together,
tracking batch-level status, progress, and results.
"""
import time, hashlib, json, os


BATCH_STATES = ("created", "queued", "partially_processed", "complete", "failed", "cancelled")


def _make_batch_id(name=""):
    return "batch_" + hashlib.sha256(f"{name}:{time.time()}".encode()).hexdigest()[:12]


class ValidationBatch:
    """A group of candidates submitted for validation together."""

    def __init__(self, name="", backend="dry_run", priority=3):
        self.batch_id = _make_batch_id(name)
        self.name = name
        self.backend = backend
        self.priority = priority
        self.state = "created"
        self.candidate_ids = []
        self.results = {}  # candidate_id → result summary
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.completed_at = None

    def add_candidate(self, candidate_id):
        if candidate_id not in self.candidate_ids:
            self.candidate_ids.append(candidate_id)

    def record_result(self, candidate_id, result_summary):
        self.results[candidate_id] = result_summary
        # Update state
        done = len(self.results)
        total = len(self.candidate_ids)
        if done == 0:
            pass  # still created/queued
        elif done < total:
            self.state = "partially_processed"
        else:
            self.state = "complete"
            self.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    def progress(self):
        total = len(self.candidate_ids)
        done = len(self.results)
        return {"total": total, "done": done, "pct": round(done / max(total, 1) * 100, 1)}

    def to_dict(self):
        return {
            "batch_id": self.batch_id, "name": self.name, "backend": self.backend,
            "priority": self.priority, "state": self.state,
            "candidate_ids": self.candidate_ids, "results": self.results,
            "progress": self.progress(),
            "created_at": self.created_at, "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d):
        b = cls(d.get("name", ""), d.get("backend", "dry_run"), d.get("priority", 3))
        b.batch_id = d["batch_id"]
        b.state = d.get("state", "created")
        b.candidate_ids = d.get("candidate_ids", [])
        b.results = d.get("results", {})
        b.created_at = d.get("created_at", "")
        b.completed_at = d.get("completed_at")
        return b


class BatchManager:
    """Manages validation batches with persistence."""

    def __init__(self, path=None):
        self.path = path or os.path.expanduser(
            "~/SOST/materials-engine-discovery/validation_batches.json")
        self.batches = {}  # batch_id → ValidationBatch
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                for d in data.get("batches", []):
                    b = ValidationBatch.from_dict(d)
                    self.batches[b.batch_id] = b
            except Exception:
                pass

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({
                "batches": [b.to_dict() for b in self.batches.values()],
                "count": len(self.batches),
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, f, indent=2, default=str)

    def create_batch(self, name, candidate_ids, backend="dry_run", priority=3):
        batch = ValidationBatch(name, backend, priority)
        for cid in candidate_ids:
            batch.add_candidate(cid)
        batch.state = "queued"
        self.batches[batch.batch_id] = batch
        return batch

    def get_batch(self, batch_id):
        return self.batches.get(batch_id)

    def get_by_state(self, state):
        return [b for b in self.batches.values() if b.state == state]

    def summary(self):
        by_state = {}
        for b in self.batches.values():
            by_state[b.state] = by_state.get(b.state, 0) + 1
        return {
            "total_batches": len(self.batches),
            "total_candidates": sum(len(b.candidate_ids) for b in self.batches.values()),
            "by_state": by_state,
        }
