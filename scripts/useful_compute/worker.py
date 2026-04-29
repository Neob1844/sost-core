#!/usr/bin/env python3
"""
SOST Useful Compute Worker (Phase 4-B, multi-file).

Public miner-side daemon for the Useful Compute Trial (blocks
7000-8000). Voluntary participation. Uses ONLY your public miner
address. Does NOT touch your wallet, keys, or signed messages.

This is the multi-file v2 worker. It runs alongside (or replaces) the
legacy single-file `scripts/useful_compute_worker.py`. The legacy
worker keeps working for light tasks. The v2 worker adds three Heavy
task families:

  - heavy_mission_consensus_screen   (M3)
  - heavy_pgm_replacement_screen     (M4)
  - heavy_mission_pipeline_screen    (MCOMB)

Stdlib only. No numpy. No torch. No third-party deps.

Run:
    python3 scripts/useful_compute/worker.py \\
        --server https://sostcore.com/api/useful-compute \\
        --miner-address sost1YOURADDRESS \\
        --worker-mode heavy
or:
    python3 -m sostcore.sost-core.scripts.useful_compute.worker ...

Compatibility: the legacy single-file worker
(`scripts/useful_compute_worker.py`) is unchanged and still handles all
light task types. Miners running it do not need to upgrade unless they
opt into Heavy.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# Allow `python3 worker.py` (script invocation) to import sibling
# packages without requiring the user to set PYTHONPATH.
_THIS_DIR = Path(__file__).resolve().parent
_PARENT_DIR = _THIS_DIR.parent
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))

from useful_compute.handlers import (  # noqa: E402
    heavy_mission_consensus_screen,
    heavy_pgm_replacement_screen,
    heavy_mission_pipeline_screen,
)
from useful_compute.utils.canonical_hash import canonical_sha256  # noqa: E402


log = logging.getLogger(__name__)

DEFAULT_SERVER = "https://sostcore.com/api/useful-compute"
DEFAULT_POLL_INTERVAL = 30
DEFAULT_BATCH_SIZE = 5
DEFAULT_TIMEOUT = 10
MAX_BACKOFF = 300

WORKER_MODE_LIGHT = "light"
WORKER_MODE_HEAVY = "heavy"
WORKER_MODE_BOTH = "both"

# Pool data files. Lives next to the worker module so a single git pull
# updates both code and pinned pool atomically.
DATA_DIR = _THIS_DIR / "data"
POOL_FILE = DATA_DIR / "formula_pool_v1.txt"
POOL_SHA_FILE = DATA_DIR / "formula_pool_v1.sha256"


HEAVY_HANDLERS = {
    "heavy_mission_consensus_screen": heavy_mission_consensus_screen.run,
    "heavy_pgm_replacement_screen":   heavy_pgm_replacement_screen.run,
    "heavy_mission_pipeline_screen":  heavy_mission_pipeline_screen.run,
}


def load_formula_pool() -> List[str]:
    """Load and verify the pinned formula pool.

    Returns the in-memory pool list. Raises RuntimeError on sha256
    mismatch or missing files; caller should treat that as fatal for
    Heavy mode.
    """
    if not POOL_FILE.exists():
        raise RuntimeError(
            f"formula pool missing: {POOL_FILE} — refusing to run Heavy"
        )
    if not POOL_SHA_FILE.exists():
        raise RuntimeError(
            f"formula pool sha256 manifest missing: {POOL_SHA_FILE}"
        )

    with open(POOL_FILE, "rb") as f:
        content = f.read()
    actual = hashlib.sha256(content).hexdigest()

    with open(POOL_SHA_FILE, "r", encoding="utf-8") as f:
        expected = f.read().strip()

    if actual != expected:
        raise RuntimeError(
            "formula_pool_v1.txt sha256 mismatch — "
            f"expected {expected}, got {actual}. Refusing to run Heavy."
        )

    pool = [line for line in content.decode("utf-8").split("\n") if line]
    return pool


def compute_heavy_task(task: Dict, pool: List[str], pool_sha: str) -> Dict:
    """Dispatch a heavy task to the right handler. Returns the handler
    result dict (which already contains result_hash)."""
    ttype = task.get("task_type", "")
    handler = HEAVY_HANDLERS.get(ttype)
    if handler is None:
        return {
            "task_type": ttype,
            "error": "unknown_heavy_task_type",
            "result_hash": canonical_sha256({"task_type": ttype,
                                              "error": "unknown_heavy_task_type"}),
        }
    payload = task.get("payload") or task
    # Cross-check the pool sha in the payload — refuse if they differ
    # (different pool version → different formula list → wrong result).
    payload_sha = payload.get("formula_pool_sha256")
    if payload_sha and payload_sha != pool_sha:
        return {
            "task_type": ttype,
            "error": "formula_pool_sha256_mismatch",
            "expected": payload_sha,
            "actual": pool_sha,
            "result_hash": canonical_sha256({
                "task_type": ttype,
                "error": "formula_pool_sha256_mismatch",
                "expected": payload_sha,
                "actual": pool_sha,
            }),
        }
    return handler(payload, pool)


# ────────────────────────────────────────────────────────────────────────
# Light task fallback — delegate to the legacy single-file worker
# ────────────────────────────────────────────────────────────────────────
#
# Heavy + light dual-mode workers should still process light tasks. We
# import the legacy worker module lazily to avoid a hard dependency in
# heavy-only deployments.


def _legacy_compute_light(task: Dict) -> Dict:
    """Try to compute a light task via the legacy worker. If the import
    fails (heavy-only deployment), return a no-op marker so we don't
    submit garbage."""
    try:
        # Add the parent scripts dir to sys.path so we can import
        # useful_compute_worker as a sibling module.
        scripts_dir = _THIS_DIR.parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import useful_compute_worker as legacy  # noqa: WPS433
        return legacy.compute_task(task)
    except Exception as e:
        log.debug(f"legacy light compute unavailable: {e}")
        return {"noop": True, "reason": "legacy_light_compute_unavailable"}


# ────────────────────────────────────────────────────────────────────────
# Result hashing for the wire protocol
# ────────────────────────────────────────────────────────────────────────


def task_result_hash(task: Dict, result: Dict) -> str:
    """Compute the cross-worker verification hash submitted to the
    server. For Heavy results we already have a `result_hash` from the
    handler — we still wrap it with the task identity so a different
    task with the same body can't collide.

    For light results we mirror the legacy worker's canonical_hash
    shape (16 hex chars) for backwards compatibility.
    """
    payload = {
        "task_id":   task.get("task_id", ""),
        "task_type": task.get("task_type", ""),
        "formula":   task.get("formula", ""),
        "mission":   task.get("mission", ""),
        "result":    result,
    }
    return canonical_sha256(payload)[:16]


# ────────────────────────────────────────────────────────────────────────
# Worker daemon
# ────────────────────────────────────────────────────────────────────────


class Worker:
    def __init__(self, server: str, miner_address: str,
                 worker_mode: str, capabilities: List[str],
                 poll_interval: int = DEFAULT_POLL_INTERVAL,
                 batch_size: int = DEFAULT_BATCH_SIZE,
                 timeout: int = DEFAULT_TIMEOUT):
        self.server        = server.rstrip("/")
        self.miner_address = miner_address
        self.worker_mode   = worker_mode
        self.capabilities  = capabilities
        self.poll_interval = max(5, int(poll_interval))
        self.batch_size    = max(1, min(int(batch_size), 50))
        self.timeout       = timeout
        self.running       = True
        self.tasks_done    = 0
        self.submitted     = 0
        self.accepted      = 0
        self.consecutive_failures = 0

        self.pool: List[str] = []
        self.pool_sha: str = ""
        if self.worker_mode in (WORKER_MODE_HEAVY, WORKER_MODE_BOTH):
            self.pool = load_formula_pool()
            with open(POOL_SHA_FILE, "r", encoding="utf-8") as f:
                self.pool_sha = f.read().strip()
            log.info(f"Heavy mode: loaded formula pool ({len(self.pool)} "
                     f"formulas, sha256={self.pool_sha[:16]}...)")

    # ── HTTP plumbing ───────────────────────────────────────────────────

    def _request(self, method: str, route: str,
                 payload: Optional[Dict]) -> Optional[Dict]:
        url = self.server + route
        try:
            data = json.dumps(payload).encode() if payload else None
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"} if data else {},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self.consecutive_failures = 0
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            log.debug(f"{method} {url} -> HTTP {e.code}")
        except Exception as e:
            log.debug(f"{method} {url} -> {e}")
        self.consecutive_failures += 1
        return None

    def _backoff_seconds(self) -> int:
        return min(MAX_BACKOFF,
                   self.poll_interval * (2 ** min(6, self.consecutive_failures)))

    # ── API ────────────────────────────────────────────────────────────

    def get_tasks(self) -> List[Dict]:
        r = self._request("POST", "/get_tasks", {
            "miner_address": self.miner_address,
            "batch_size":    self.batch_size,
            "worker_mode":   self.worker_mode,
            "capabilities":  self.capabilities,
        })
        if not r:
            return []
        return r.get("tasks", [])

    def submit(self, task: Dict, result: Dict, result_hash: str) -> bool:
        score = (
            result.get("composite_score")
            or result.get("score")
            or result.get("replacement_score")
            or 0
        )
        r = self._request("POST", "/submit_result", {
            "miner_address": self.miner_address,
            "task_id":       task.get("task_id"),
            "task_type":     task.get("task_type", ""),
            "formula":       task.get("formula", ""),
            "mission":       task.get("mission", ""),
            "weight":        task.get("weight"),
            "result_hash":   result_hash,
            "score":         score,
        })
        return bool(r and r.get("accepted"))

    def status(self) -> Dict:
        r = self._request("POST", "/check_eligible",
                          {"miner_address": self.miner_address})
        return r or {}

    # ── Compute dispatch ───────────────────────────────────────────────

    def compute(self, task: Dict) -> Dict:
        ttype = task.get("task_type", "")
        if ttype in HEAVY_HANDLERS:
            return compute_heavy_task(task, self.pool, self.pool_sha)
        return _legacy_compute_light(task)

    # ── Loop ───────────────────────────────────────────────────────────

    def run(self):
        log.info("=" * 60)
        log.info("SOST Useful Compute Worker (Phase 4-B, multi-file)")
        log.info(f"Server:        {self.server}")
        log.info(f"Miner:         {self.miner_address}")
        log.info(f"Worker mode:   {self.worker_mode}")
        log.info(f"Capabilities:  {','.join(self.capabilities)}")
        log.info(f"Heavy pool:    {len(self.pool)} formulas")
        log.info("=" * 60)

        while self.running:
            try:
                self._tick()
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                log.warning(f"loop error: {e}")
                time.sleep(self._backoff_seconds())
                continue
            time.sleep(self.poll_interval)

        log.info(f"stopped. tasks_done={self.tasks_done} "
                 f"submitted={self.submitted} accepted={self.accepted}")

    def _tick(self):
        tasks = self.get_tasks()
        if not tasks:
            if self.consecutive_failures > 0:
                wait = self._backoff_seconds()
                log.info(f"server unreachable ({self.consecutive_failures}× "
                         f"failures). waiting {wait}s.")
                time.sleep(wait)
            return

        for task in tasks:
            if not self.running:
                break
            ttype = task.get("task_type", "")
            if ttype.startswith("heavy_") and self.worker_mode == WORKER_MODE_LIGHT:
                continue
            if (not ttype.startswith("heavy_")
                    and self.worker_mode == WORKER_MODE_HEAVY):
                continue
            try:
                result = self.compute(task)
                rh = task_result_hash(task, result)
                self.tasks_done += 1
                if self.submit(task, result, rh):
                    self.accepted += 1
                self.submitted += 1
            except Exception as e:
                log.warning(f"task {task.get('task_id')} failed: {e}")
                continue

        info = self.status()
        log.info(
            f"local_done={self.tasks_done} "
            f"submitted={self.submitted} accepted={self.accepted} "
            f"verified={info.get('verified_tasks', 0)} "
            f"disputed={info.get('disputed_tasks', 0)}"
        )


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="SOST Useful Compute Worker — Phase 4-B (multi-file)"
    )
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--miner-address", required=False, default="sost1unset",
                   help="Your public miner address (sost1...). Required for "
                        "production runs; default 'sost1unset' is for self-tests.")
    p.add_argument("--worker-mode",
                   choices=[WORKER_MODE_LIGHT, WORKER_MODE_HEAVY, WORKER_MODE_BOTH],
                   default=WORKER_MODE_HEAVY,
                   help="light = legacy stdlib light tasks. "
                        "heavy = M3/M4/MCOMB only. "
                        "both = light + heavy.")
    p.add_argument("--capabilities", default="stdlib,cpu",
                   help="Comma-separated capability tags announced to the server.")
    p.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--once", action="store_true",
                   help="Run a single tick and exit (for testing).")
    p.add_argument("--self-check", action="store_true",
                   help="Verify the formula pool sha256 and exit 0/2.")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.self_check:
        try:
            pool = load_formula_pool()
            log.info(f"self-check OK: {len(pool)} formulas, sha256 verified")
            return 0
        except Exception as e:
            log.error(f"self-check FAILED: {e}")
            return 2

    capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]
    w = Worker(
        server=args.server,
        miner_address=args.miner_address,
        worker_mode=args.worker_mode,
        capabilities=capabilities,
        poll_interval=args.poll_interval,
        batch_size=args.batch_size,
    )
    if args.once:
        w._tick()
        return 0
    w.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
