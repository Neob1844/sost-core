"""
SOST Gold Exchange — Audit Log

Event-sourced log of every deal action. Append-only.
Used for forensics, dispute resolution, and operational monitoring.
"""

import time
import json
import os
import logging
from dataclasses import dataclass, asdict

log = logging.getLogger("audit")


@dataclass
class AuditEntry:
    timestamp: float
    deal_id: str
    event: str
    detail: str


class AuditLog:
    def __init__(self, log_dir: str = "data/audit"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._entries: list[AuditEntry] = []
        self._file_path = os.path.join(log_dir, "audit.jsonl")

    def log_event(self, deal_id: str, event: str, detail: str = ""):
        entry = AuditEntry(
            timestamp=time.time(),
            deal_id=deal_id,
            event=event,
            detail=detail,
        )
        self._entries.append(entry)
        self._persist(entry)
        log.info("[AUDIT] deal=%s event=%s detail=%s", deal_id, event, detail)

    def _persist(self, entry: AuditEntry):
        try:
            with open(self._file_path, "a") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except IOError as e:
            log.error("Failed to persist audit entry: %s", e)

    def get_deal_history(self, deal_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.deal_id == deal_id]

    def get_all(self) -> list[AuditEntry]:
        return list(self._entries)

    def load(self):
        if not os.path.exists(self._file_path):
            return
        with open(self._file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        d = json.loads(line)
                        self._entries.append(AuditEntry(**d))
                    except (json.JSONDecodeError, TypeError):
                        pass

    def export_deal(self, deal_id: str, path: str):
        history = self.get_deal_history(deal_id)
        with open(path, "w") as f:
            json.dump([asdict(e) for e in history], f, indent=2)
