#!/usr/bin/env python3
"""
SOST Useful Compute Worker — public miner-side daemon for the trial.

Voluntary participation. Runs alongside your SOST miner. Uses ONLY your
public miner address. Does NOT touch your wallet, keys, or signed messages.

Trial: blocks 7,000 → 8,000.
Server: https://sostcore.com/api/useful-compute/

How it works:
    1. The worker requests tasks from the SOST task server.
    2. Each task names a chemical formula and a mission profile.
    3. The worker computes a deterministic result (formula parsing,
       elemental abundance, simple scoring).
    4. The worker submits the result hash. The server cross-verifies
       your hash against another miner who computed the same task.
    5. If your hash matches the other miner's hash, the task is VERIFIED
       and counts toward your contribution score.

No external dependencies — Python 3.6+ standard library only.

Usage:
    python3 scripts/useful_compute_worker.py \\
        --server https://sostcore.com/api/useful-compute \\
        --miner-address sost1YOURADDRESS \\
        --mode trial

Stop any time with Ctrl-C. Your already-submitted contributions stay on
the public ranking.
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_SERVER       = "https://sostcore.com/api/useful-compute"
DEFAULT_POLL_INTERVAL = 30
DEFAULT_BATCH_SIZE   = 10
MAX_BACKOFF          = 300
DEFAULT_TIMEOUT      = 10


# ────────────────────────────────────────────────────────────────────────────
# Public element data (CRUSTAL ABUNDANCE, RELATIVE COST INDEX)
# Source: standard geochemistry references. Values are public knowledge.
# ────────────────────────────────────────────────────────────────────────────

# Abundance: log10(crustal abundance in ppm). Higher = more abundant.
# Cost index: 0.0 (cheap) → 1.0 (extremely expensive).
ELEMENTS: Dict[str, Tuple[float, float]] = {
    "H":  (3.16, 0.05), "Li": (1.20, 0.40), "Be": (0.46, 0.55),
    "B":  (1.00, 0.35), "C":  (2.30, 0.10), "N":  (1.30, 0.05),
    "O":  (5.67, 0.02), "F":  (2.70, 0.20), "Na": (4.38, 0.15),
    "Mg": (4.38, 0.10), "Al": (4.91, 0.08), "Si": (5.45, 0.05),
    "P":  (3.00, 0.20), "S":  (2.40, 0.10), "Cl": (2.20, 0.15),
    "K":  (4.32, 0.20), "Ca": (4.62, 0.05), "Sc": (1.32, 0.45),
    "Ti": (3.76, 0.25), "V":  (2.06, 0.30), "Cr": (2.04, 0.25),
    "Mn": (2.99, 0.15), "Fe": (4.71, 0.05), "Co": (1.46, 0.40),
    "Ni": (1.92, 0.30), "Cu": (1.84, 0.25), "Zn": (1.85, 0.20),
    "Ga": (1.23, 0.45), "Ge": (0.18, 0.55), "As": (0.30, 0.40),
    "Se": (-0.30, 0.50), "Br": (0.40, 0.35), "Rb": (1.95, 0.40),
    "Sr": (2.59, 0.20), "Y":  (1.52, 0.45), "Zr": (2.23, 0.30),
    "Nb": (1.30, 0.45), "Mo": (0.18, 0.50), "Ru": (-3.00, 0.92),
    "Rh": (-3.00, 0.97), "Pd": (-2.20, 0.94), "Ag": (-1.10, 0.70),
    "Cd": (-0.80, 0.55), "In": (-0.60, 0.65), "Sn": (0.30, 0.40),
    "Sb": (-0.70, 0.45), "Te": (-2.00, 0.70), "I":  (-0.40, 0.45),
    "Cs": (0.46, 0.60), "Ba": (2.62, 0.30), "La": (1.51, 0.55),
    "Ce": (1.83, 0.50), "Pr": (0.92, 0.60), "Nd": (1.62, 0.55),
    "Sm": (0.86, 0.65), "Eu": (0.20, 0.85), "Gd": (0.83, 0.65),
    "Tb": (0.07, 0.80), "Dy": (0.79, 0.70), "Ho": (-0.06, 0.80),
    "Er": (0.55, 0.70), "Tm": (-0.30, 0.85), "Yb": (0.51, 0.70),
    "Lu": (-0.20, 0.85), "Hf": (0.54, 0.55), "Ta": (0.30, 0.65),
    "W":  (0.18, 0.40), "Re": (-3.00, 0.95), "Os": (-3.00, 0.96),
    "Ir": (-3.00, 0.97), "Pt": (-2.40, 0.96), "Au": (-2.40, 0.93),
    "Hg": (-1.10, 0.55), "Tl": (-0.30, 0.65), "Pb": (1.10, 0.25),
    "Bi": (-1.20, 0.55),
}

# Mission scoring weights (deterministic, public)
MISSIONS: Dict[str, Dict[str, float]] = {
    "pgm_free_catalyst_v1": {
        "abundance_weight": 0.6,
        "cost_penalty":     0.4,
        "pgm_block":        1.0,    # PGM presence rejects the candidate
    },
    "photovoltaic_absorber": {
        "abundance_weight": 0.5,
        "cost_penalty":     0.3,
        "pgm_block":        0.0,
    },
    "lithium_extraction": {
        "abundance_weight": 0.5,
        "cost_penalty":     0.3,
        "pgm_block":        0.0,
    },
    "hydrogen_storage": {
        "abundance_weight": 0.5,
        "cost_penalty":     0.3,
        "pgm_block":        0.0,
    },
    "co2_capture": {
        "abundance_weight": 0.5,
        "cost_penalty":     0.3,
        "pgm_block":        0.0,
    },
    "desalination_membrane": {
        "abundance_weight": 0.5,
        "cost_penalty":     0.3,
        "pgm_block":        0.0,
    },
}
DEFAULT_MISSION = {"abundance_weight": 0.5, "cost_penalty": 0.3, "pgm_block": 0.0}

PGM_ELEMENTS = {"Pt", "Pd", "Rh", "Ru", "Os", "Ir"}

FORMULA_RE = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")


# ────────────────────────────────────────────────────────────────────────────
# Deterministic compute primitives
# ────────────────────────────────────────────────────────────────────────────


def parse_formula(formula: str) -> Dict[str, float]:
    """Parse a chemical formula into a sorted element-count dict."""
    counts: Dict[str, float] = {}
    if not formula:
        return counts
    for sym, n in FORMULA_RE.findall(formula):
        if not sym or sym not in ELEMENTS:
            continue
        amount = float(n) if n else 1.0
        counts[sym] = counts.get(sym, 0.0) + amount
    return dict(sorted(counts.items()))


def abundance_score(counts: Dict[str, float]) -> float:
    """Weighted average crustal abundance (log10 ppm) — higher is better."""
    if not counts:
        return 0.0
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return round(
        sum(ELEMENTS[e][0] * c for e, c in counts.items()) / total, 6
    )


def cost_index(counts: Dict[str, float]) -> float:
    """Weighted average relative cost index — lower is better (0–1)."""
    if not counts:
        return 0.0
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return round(
        sum(ELEMENTS[e][1] * c for e, c in counts.items()) / total, 6
    )


def has_pgm(counts: Dict[str, float]) -> bool:
    return any(e in PGM_ELEMENTS for e in counts)


def mission_score(counts: Dict[str, float], mission: str) -> Dict:
    cfg = MISSIONS.get(mission, DEFAULT_MISSION)
    if cfg.get("pgm_block", 0.0) > 0 and has_pgm(counts):
        return {"score": 0.0, "rejected": True, "reason": "pgm_present"}
    a = abundance_score(counts)
    c = cost_index(counts)
    score = cfg["abundance_weight"] * a - cfg["cost_penalty"] * (c - 0.2)
    return {
        "score":           round(score, 6),
        "abundance_score": a,
        "cost_index":      c,
        "rejected":        False,
    }


def compute_task(task: Dict) -> Dict:
    """Execute a task deterministically. Same input → same output."""
    formula = task.get("formula", "")
    mission = task.get("mission", "")
    task_type = task.get("task_type", "abundance_score")

    counts = parse_formula(formula)
    elements = sorted(counts.keys())

    if task_type in ("formula_parse", "reject_check"):
        out = {
            "elements":  elements,
            "counts":    counts,
            "has_pgm":   has_pgm(counts),
            "valid":     bool(counts),
        }
    elif task_type == "abundance_cost_score":
        out = {
            "elements":         elements,
            "abundance_score":  abundance_score(counts),
            "cost_index":       cost_index(counts),
            "has_pgm":          has_pgm(counts),
        }
    elif task_type == "pgm_check":
        out = {
            "has_pgm":   has_pgm(counts),
            "pgm_count": sum(1 for e in counts if e in PGM_ELEMENTS),
        }
    elif task_type in ("mission_score", "full_pipeline"):
        out = mission_score(counts, mission)
        out["elements"] = elements
        out["has_pgm"]  = has_pgm(counts)
    else:
        # Unknown type — still produce a deterministic output so the server
        # gets *something* hashable rather than nothing.
        out = {
            "elements":  elements,
            "task_type": task_type,
            "noop":      True,
        }
    return out


def canonical_hash(task: Dict, result: Dict) -> str:
    """Deterministic hash of (task identity + result). Same input → same hash."""
    payload = {
        "task_id":   task.get("task_id", ""),
        "task_type": task.get("task_type", ""),
        "formula":   task.get("formula", ""),
        "mission":   task.get("mission", ""),
        "result":    result,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# ────────────────────────────────────────────────────────────────────────────
# Daemon
# ────────────────────────────────────────────────────────────────────────────


class Worker:
    def __init__(self, server: str, miner_address: str,
                 poll_interval: int = DEFAULT_POLL_INTERVAL,
                 batch_size: int = DEFAULT_BATCH_SIZE,
                 mode: str = "trial",
                 timeout: int = DEFAULT_TIMEOUT):
        self.server        = server.rstrip("/")
        self.miner_address = miner_address
        self.poll_interval = max(5, int(poll_interval))
        self.batch_size    = max(1, min(int(batch_size), 50))
        self.mode          = mode
        self.timeout       = timeout
        self.running       = True
        self.tasks_done    = 0
        self.submitted     = 0
        self.accepted      = 0
        self.consecutive_failures = 0

    # ── HTTP plumbing ───────────────────────────────────────────────────────

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

    # ── API ────────────────────────────────────────────────────────────────

    def get_tasks(self) -> List[Dict]:
        r = self._request("POST", "/get_tasks", {
            "miner_address": self.miner_address,
            "batch_size":    self.batch_size,
        })
        if not r:
            return []
        return r.get("tasks", [])

    def submit(self, task: Dict, result: Dict, result_hash: str) -> bool:
        score = result.get("score") or result.get("abundance_score") or 0
        r = self._request("POST", "/submit_result", {
            "miner_address": self.miner_address,
            "task_id":       task["task_id"],
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

    # ── Main loop ──────────────────────────────────────────────────────────

    def run(self):
        log.info("=" * 60)
        log.info("SOST Useful Compute Worker — voluntary participation")
        log.info(f"Server:        {self.server}")
        log.info(f"Miner:         {self.miner_address}")
        log.info(f"Mode:          {self.mode}")
        log.info(f"Poll interval: {self.poll_interval}s · batch: {self.batch_size}")
        log.info("=" * 60)
        log.info("This worker uses ONLY your public miner address.")
        log.info("It does NOT touch your wallet, keys, or signed messages.")
        log.info("Stop any time with Ctrl-C.")

        while self.running:
            try:
                self._tick()
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                log.warning(f"Loop error: {e}")
                time.sleep(self._backoff_seconds())
                continue
            time.sleep(self.poll_interval)

        log.info(f"Stopped. tasks_done={self.tasks_done} "
                 f"submitted={self.submitted} accepted={self.accepted}")

    def _tick(self):
        tasks = self.get_tasks()
        if not tasks:
            if self.consecutive_failures > 0:
                wait = self._backoff_seconds()
                log.info(f"Server unreachable ({self.consecutive_failures}× failures). "
                         f"Waiting {wait}s before retry.")
                time.sleep(wait)
            else:
                log.debug("No tasks available right now.")
            return

        for task in tasks:
            if not self.running:
                break
            try:
                result = compute_task(task)
                rh     = canonical_hash(task, result)
                self.tasks_done += 1
                if self.submit(task, result, rh):
                    self.accepted += 1
                self.submitted += 1
            except Exception as e:
                log.warning(f"Task {task.get('task_id')} failed locally: {e}")
                continue

        info = self.status()
        log.info(
            f"local_done={self.tasks_done} "
            f"submitted={self.submitted} accepted={self.accepted} "
            f"verified={info.get('verified_tasks', 0)} "
            f"disputed={info.get('disputed_tasks', 0)} "
            f"score={info.get('weighted_score', 0):.1f} "
            f"eligible={info.get('eligible', False)}"
        )


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="SOST Useful Compute Worker (public, voluntary)"
    )
    p.add_argument("--server", default=DEFAULT_SERVER,
                   help="Task server URL (default: %(default)s)")
    p.add_argument("--miner-address", required=True,
                   help="Your SOST miner address (sost1...) — public only, "
                        "never your private key.")
    p.add_argument("--mode", default="trial",
                   choices=["trial", "test", "dryrun"])
    p.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL,
                   help="Seconds between task fetches (default: %(default)s)")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                   help="Tasks per request (default: %(default)s, max 50)")
    p.add_argument("--once", action="store_true",
                   help="Run a single tick and exit (for testing).")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.miner_address.startswith("sost1"):
        log.warning("Miner address does not start with 'sost1' — double-check it.")

    w = Worker(
        server=args.server, miner_address=args.miner_address,
        poll_interval=args.poll_interval, batch_size=args.batch_size,
        mode=args.mode,
    )
    if args.once:
        w._tick()
        log.info(f"Once-shot complete: tasks_done={w.tasks_done} "
                 f"submitted={w.submitted} accepted={w.accepted}")
        return 0
    w.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
