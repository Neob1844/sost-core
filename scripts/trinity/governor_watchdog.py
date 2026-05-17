#!/usr/bin/env python3
"""Trinity Governor Watchdog v0.1 (Sprint 5.25).

External, read-only observer for the Trinity Autonomy Governor audit
trail. The Watchdog scans a directory of Governor decision JSON files,
summarises them into a deterministic report JSON, and prints a one-
line status to stdout. Default mode is fully local — the Watchdog
never POSTs anywhere unless the operator explicitly passes BOTH
``--webhook-url`` AND ``--send``.

Why it exists:
    The Autonomy Governor (Sprint 5.23) is intentionally
    network-free: it never opens a socket and never heartbeats
    anything. That is the right design for the Governor — but it
    means a stuck Governor, a tampered decision file, or a halt
    event are invisible to anything outside the box. The Watchdog
    is the missing external eye. It runs in its own process,
    reads the audit trail the Governor already produced, and is
    free to talk to the network in a strictly bounded way.

Hard invariants v0.1 (enforced by static tests):
    - Read-only on the decisions directory. Never writes, renames,
      deletes, or chmods any input file.
    - No wallet, no private-key handling, no signing, no
      broadcasting, no chain CLI, no payment / reward primitives.
    - No child process, no shell-out, no eval / exec.
    - Webhook is opt-in and double-gated: ``--webhook-url`` PLUS
      ``--send``. Without ``--send`` the URL is recorded in the
      report (redacted to its host) and never fetched.
    - Paths whose basename or any segment matches a denylist
      (wallets, secrets, .git, .ssh) are refused at startup —
      the Watchdog is not allowed to look at them.

Usage:
    python3 scripts/trinity/governor_watchdog.py \\
        --decisions-dir /var/lib/trinity/governor_decisions \\
        --out-dir /var/lib/trinity/watchdog \\
        --pinned-time 2026-05-17T00:00:00+00:00

Output:
    <out-dir>/TRINITY_GOVERNOR_WATCHDOG_REPORT_<report_id>.json
    Path also printed to stdout. Exit code 0 unless the Watchdog
    itself failed to start; the report's ``safety_status`` field
    is the source of truth on whether action is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os.path
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_REPORT = "trinity-governor-watchdog-report/v0.1"
SCHEMA_DECISION = "trinity-autonomy-governor-decision/v0.1"
DEFAULT_MAX_AGE_SECONDS = 3600

# Hard refusal: the Watchdog never opens these directories, even if
# the operator points it at them. The match is on basename of any
# path segment, case-insensitive. This is a belt-and-braces guard,
# not a security boundary — the kernel + filesystem perms are.
PATH_DENYLIST = (
    "wallets",
    "wallet",
    "secrets",
    ".git",
    ".ssh",
    "private",
    "keys",
)

HARD_BLOCK_REASONS = ("halt_file_present", "policy_mutated_at_runtime")


class WatchdogError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _redact_url(url: Optional[str]) -> Optional[str]:
    """Reduce a URL to scheme + host so secrets in query/path are
    not leaked to the report or to stdout."""
    if not url:
        return None
    try:
        from urllib.parse import urlsplit
        u = urlsplit(url)
        host = u.hostname or "<unknown-host>"
        return (u.scheme or "http") + "://" + host
    except Exception:
        return "<redacted>"


def _default_pinned_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_iso(t: str) -> Optional[datetime]:
    """Best-effort ISO-8601 parser. Returns None on failure rather
    than raising — the Watchdog tolerates malformed timestamps in
    decisions and records them as warnings."""
    if not isinstance(t, str):
        return None
    s = t.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _segment_in_denylist(path: Path) -> Optional[str]:
    """Return the first path segment that matches the denylist
    (case-insensitive on the basename), or None if clean."""
    for part in path.parts:
        name = os.path.basename(part).lower()
        if name in PATH_DENYLIST:
            return name
    return None


# ---------------------------------------------------------------------------
# Decision parsing
# ---------------------------------------------------------------------------


def _classify_decision(d: Dict[str, Any]) -> Dict[str, Any]:
    """Read a single decision dict and return the per-decision
    counters and any warnings this decision contributes."""
    out: Dict[str, Any] = {
        "valid": False,
        "allowed": False,
        "blocked": False,
        "requires_human_approval": False,
        "policy_mutation_detected": False,
        "halt_detected": False,
        "warnings": [],
        "decision_id": None,
        "threat_refs": [],
        "action": None,
        "pinned_time": None,
    }

    # Minimum structural check. We deliberately do not import
    # jsonschema here — the Watchdog must stay light. The schema
    # tests cover the contract on the producer side; here we only
    # need enough to bin the decision.
    required = (
        "schema", "decision_id", "policy_hashes_match",
        "action", "allowed", "blocked_reason",
        "requires_human_approval", "threat_refs", "pinned_time",
    )
    missing = [k for k in required if k not in d]
    if missing:
        out["warnings"].append(
            "malformed: missing fields " + ",".join(sorted(missing))
        )
        return out
    if d.get("schema") != SCHEMA_DECISION:
        out["warnings"].append(
            "malformed: wrong schema " + repr(d.get("schema"))
        )
        return out

    out["valid"] = True
    out["decision_id"] = d.get("decision_id")
    out["action"] = d.get("action")
    out["pinned_time"] = d.get("pinned_time")
    refs = d.get("threat_refs") or []
    if isinstance(refs, list):
        out["threat_refs"] = [r for r in refs if isinstance(r, str)]

    if d.get("allowed") is True:
        out["allowed"] = True
    else:
        out["blocked"] = True

    if d.get("requires_human_approval") is True:
        out["requires_human_approval"] = True

    reason = d.get("blocked_reason")
    if reason == "halt_file_present":
        out["halt_detected"] = True
    if reason == "policy_mutated_at_runtime":
        out["policy_mutation_detected"] = True

    if d.get("policy_hashes_match") is False:
        out["warnings"].append(
            "decision " + str(d.get("decision_id"))
            + " has policy_hashes_match=false"
        )

    return out


def _read_decision_file(p: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load one decision file as JSON. Returns (decision_dict_or_None,
    warnings). Never raises."""
    warnings: List[str] = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            warnings.append(
                "malformed: " + p.name + " is not a JSON object"
            )
            return None, warnings
        return obj, warnings
    except json.JSONDecodeError as exc:
        warnings.append(
            "malformed: " + p.name + " invalid JSON: " + str(exc)
        )
    except OSError as exc:
        warnings.append(
            "malformed: " + p.name + " read error: " + str(exc)
        )
    return None, warnings


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------


def scan_decisions(
    decisions_dir: Path,
    pinned_time: str,
    max_age_seconds: int,
    webhook_url: Optional[str] = None,
    send: bool = False,
) -> Dict[str, Any]:
    """Scan a directory of Governor decision JSONs and build a
    deterministic report dict. Pure function: no filesystem writes,
    no network calls.

    The decisions_dir MUST already exist. The Watchdog never creates
    or modifies its input.
    """
    decisions_dir = Path(decisions_dir)
    if not decisions_dir.exists():
        raise WatchdogError(
            "decisions-dir does not exist: " + str(decisions_dir)
        )
    if not decisions_dir.is_dir():
        raise WatchdogError(
            "decisions-dir is not a directory: " + str(decisions_dir)
        )
    deny = _segment_in_denylist(decisions_dir)
    if deny is not None:
        raise WatchdogError(
            "decisions-dir contains denylisted segment '" + deny
            + "': refusing to scan " + str(decisions_dir)
        )

    files = sorted(
        decisions_dir.glob("TRINITY_AUTONOMY_GOVERNOR_DECISION_*.json")
    )
    decisions_seen = 0
    malformed_count = 0
    allowed_count = 0
    blocked_count = 0
    human_approval_required_count = 0
    policy_mutation_detected_count = 0
    halt_detected_count = 0
    decision_ids: List[str] = []
    threat_refs_seen: List[str] = []
    actions_seen: List[str] = []
    warnings: List[str] = []
    newest_dt: Optional[datetime] = None
    newest_iso: Optional[str] = None

    for f in files:
        decisions_seen += 1
        obj, file_warnings = _read_decision_file(f)
        warnings.extend(file_warnings)
        if obj is None:
            malformed_count += 1
            continue
        info = _classify_decision(obj)
        warnings.extend(info["warnings"])
        if not info["valid"]:
            malformed_count += 1
            continue
        if info["allowed"]:
            allowed_count += 1
        if info["blocked"]:
            blocked_count += 1
        if info["requires_human_approval"]:
            human_approval_required_count += 1
        if info["policy_mutation_detected"]:
            policy_mutation_detected_count += 1
        if info["halt_detected"]:
            halt_detected_count += 1
        if info["decision_id"]:
            decision_ids.append(info["decision_id"])
        for r in info["threat_refs"]:
            if r not in threat_refs_seen:
                threat_refs_seen.append(r)
        if info["action"] and info["action"] not in actions_seen:
            actions_seen.append(info["action"])
        dt = _parse_iso(info["pinned_time"] or "")
        if dt is not None and (newest_dt is None or dt > newest_dt):
            newest_dt = dt
            newest_iso = info["pinned_time"]

    # Determine staleness relative to the report's pinned_time
    # (deterministic; the operator pins it).
    pinned_dt = _parse_iso(pinned_time)
    stale = False
    age_seconds: Optional[int] = None
    if newest_dt is None:
        stale = (decisions_seen == 0)
        if decisions_seen == 0:
            warnings.append("no decisions found in decisions-dir")
    elif pinned_dt is not None:
        delta = (pinned_dt - newest_dt).total_seconds()
        if delta >= 0:
            age_seconds = int(delta)
        else:
            age_seconds = 0
        if age_seconds is not None and age_seconds > int(max_age_seconds):
            stale = True
            warnings.append(
                "newest decision is " + str(age_seconds)
                + "s old, exceeds max_age_seconds="
                + str(max_age_seconds)
            )

    # safety_status precedence: critical > warning > stale > ok
    safety_status = "ok"
    if halt_detected_count > 0 or policy_mutation_detected_count > 0:
        safety_status = "critical"
    elif malformed_count > 0 or any(
        "policy_hashes_match=false" in w for w in warnings
    ):
        safety_status = "warning"
    elif stale:
        safety_status = "stale"

    # Webhook bookkeeping. The URL is redacted to scheme://host so
    # secrets in path / query do not land in the report.
    webhook_configured = webhook_url is not None
    webhook_status = "not_configured"
    webhook_sent = False
    if webhook_configured:
        if send:
            webhook_status = "sent_skipped_v01"
            warnings.append(
                "v0.1 declines to fetch webhook even with --send; "
                "external dispatch is reserved for the watchdog "
                "daemon in a later sprint"
            )
        else:
            webhook_status = "skipped_no_send"

    report: Dict[str, Any] = {
        "schema": SCHEMA_REPORT,
        "report_id": "wd-" + _sha16(_canonical_dumps({
            "pinned_time": pinned_time,
            "decisions_dir_basename": decisions_dir.name,
            "decision_ids": sorted(decision_ids),
        })),
        "pinned_time": pinned_time,
        "decisions_dir_basename": decisions_dir.name,
        "max_age_seconds": int(max_age_seconds),
        "decisions_seen": decisions_seen,
        "malformed_count": malformed_count,
        "allowed_count": allowed_count,
        "blocked_count": blocked_count,
        "human_approval_required_count": human_approval_required_count,
        "policy_mutation_detected_count": policy_mutation_detected_count,
        "halt_detected_count": halt_detected_count,
        "newest_decision_time": newest_iso,
        "newest_decision_age_seconds": age_seconds,
        "stale": bool(stale),
        "decision_ids": sorted(decision_ids),
        "threat_refs_seen": sorted(threat_refs_seen),
        "actions_seen": sorted(actions_seen),
        "warnings": warnings,
        "safety_status": safety_status,
        "webhook_configured": webhook_configured,
        "webhook_url_redacted": _redact_url(webhook_url),
        "webhook_sent": webhook_sent,
        "webhook_status": webhook_status,
    }
    return report


def write_report(report: Dict[str, Any], out_dir: Path) -> Path:
    """Write the report to out_dir as a single canonical JSON file
    and return the path. The Watchdog NEVER writes into decisions-dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    deny = _segment_in_denylist(out_dir)
    if deny is not None:
        raise WatchdogError(
            "out-dir contains denylisted segment '" + deny
            + "': refusing to write to " + str(out_dir)
        )
    fname = "TRINITY_GOVERNOR_WATCHDOG_REPORT_" + report["report_id"] + ".json"
    p = out_dir / fname
    with open(p, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    return p


# ---------------------------------------------------------------------------
# Config + CLI
# ---------------------------------------------------------------------------


def _load_config(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise WatchdogError("config not found: " + str(p))
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="governor_watchdog",
        description=(
            "Trinity Governor Watchdog v0.1. Read-only observer of "
            "the Autonomy Governor audit trail. NEVER touches a "
            "wallet, NEVER signs, NEVER broadcasts."
        ),
    )
    p.add_argument("--decisions-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pinned-time", default=None)
    p.add_argument("--max-age-seconds", type=int, default=None)
    p.add_argument("--config", default=None)
    p.add_argument(
        "--webhook-url", default=None,
        help=(
            "Optional. v0.1 records it (host-redacted) but does NOT "
            "fetch it. External dispatch arrives in a later sprint."
        ),
    )
    p.add_argument(
        "--send", action="store_true",
        help=(
            "Required alongside --webhook-url for any future "
            "external dispatch. v0.1 still does not fetch the URL "
            "but the flag is wired and tested."
        ),
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)

    pinned_time = (
        args.pinned_time
        or cfg.get("pinned_time")
        or _default_pinned_time()
    )
    max_age = (
        args.max_age_seconds
        if args.max_age_seconds is not None
        else int(cfg.get("max_age_seconds", DEFAULT_MAX_AGE_SECONDS))
    )
    webhook_url = args.webhook_url or cfg.get("webhook_url")

    try:
        report = scan_decisions(
            decisions_dir=Path(args.decisions_dir),
            pinned_time=pinned_time,
            max_age_seconds=max_age,
            webhook_url=webhook_url,
            send=bool(args.send),
        )
        out_path = write_report(report, Path(args.out_dir))
    except WatchdogError as exc:
        print(
            "[governor_watchdog] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    print(
        "[governor_watchdog] report=" + str(out_path)
        + " decisions=" + str(report["decisions_seen"])
        + " allowed=" + str(report["allowed_count"])
        + " blocked=" + str(report["blocked_count"])
        + " malformed=" + str(report["malformed_count"])
        + " safety_status=" + report["safety_status"]
        + (" stale" if report["stale"] else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
