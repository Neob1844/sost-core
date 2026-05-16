#!/usr/bin/env python3
"""Trinity Autonomy Governor v0.1 (Sprint 5.23).

Constitutional layer for any future autonomous action Trinity might
take. The Governor LOADS a policy file, EVALUATES whether a proposed
action would be allowed under that policy, and EMITS a deterministic
decision JSON. v0.1 is OBSERVE ONLY: the Governor never executes the
action it evaluates, never opens the network, never spawns a
subprocess, never touches a wallet, never signs, never broadcasts.

The Governor is intentionally narrow: it is a pure function of
``(policy, action, action_params, pinned_time, halt_file_state)``.
Anything that wants to do real work (run a worker, sign a transaction,
broadcast) is layered on top in later sprints, and only after a human
has reviewed and signed off on each integration.

The decisions emitted by the Governor reference threats T01-T20 from
SECURITY.md (Trinity threat model v0.1). See
``docs/TRINITY_AUTONOMY_GOVERNOR_V01.md`` for the full design.

Usage:
    python3 scripts/trinity/autonomy_governor.py \\
        --policy config/trinity_autonomy_governor.example.json \\
        --action create_request \\
        --action-param source_tool=trinity_scientific_prompt_intake \\
        --action-param estimated_worker_minutes=5 \\
        --out-dir /tmp/governor-decisions \\
        --pinned-time 2026-05-16T00:00:00+00:00

Output:
    <out-dir>/TRINITY_AUTONOMY_GOVERNOR_DECISION_<decision_id>.json
    Path also printed to stdout.

Exit code:
    0 always when the evaluation ran to completion. The decision JSON
    is the source of truth on whether the action was allowed. Use the
    file's ``allowed`` / ``blocked_reason`` / ``requires_human_approval``
    fields to drive any subsequent control flow.

Hard invariants v0.1 (enforced by tests):
    - No network imports anywhere in this file.
    - No subprocess / shell.
    - No wallet / signing / broadcast / private-key handling.
    - No eval / exec dynamic code execution.
    - mode != 'observe' rejected at policy load.
    - caps_per_day.autonomous_sost_stocks != 0 rejected (SECURITY.md T08).
    - Policy hash pinned at boot. Mutation between load and decision
      blocks the decision with policy_mutated_at_runtime.
    - Presence of kill_switch.halt_file blocks every action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os.path
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_POLICY = "trinity-autonomy-governor-policy/v0.1"
SCHEMA_DECISION = "trinity-autonomy-governor-decision/v0.1"

# v0.1 ships only the observation mode. The other two values exist in
# the schema for future sprints but the code rejects them here.
SHIPPED_MODES = ("observe",)

# Recognised action names. v0.1 evaluates these but never performs them.
KNOWN_ACTIONS = (
    "create_request",
    "launch_worker",
    "call_rpc",
    "real_sign",
    "broadcast_signed_transaction",
    "wallet_access",
    "filesystem_read",
    "filesystem_write",
    "constitution_change",
    "register_new_source_tool",
)

# Actions that ALWAYS require a human, never autonomous, regardless of
# what the policy says. These are belt-and-tirantes against a policy
# that is accidentally too permissive.
ALWAYS_REQUIRE_HUMAN_APPROVAL = (
    "real_sign",
    "broadcast_signed_transaction",
    "wallet_access",
    "constitution_change",
    "register_new_source_tool",
)

# Per-action references into SECURITY.md (Trinity threat model v0.1).
# Every decision carries the relevant threat_refs so the audit log
# trivially maps to the threat model.
THREAT_REFS = {
    "create_request":               ["T01", "T05", "T09"],
    "launch_worker":                ["T02", "T03", "T05"],
    "call_rpc":                     ["T12"],
    "real_sign":                    ["T06", "T07", "T08"],
    "broadcast_signed_transaction": ["T07", "T08"],
    "wallet_access":                ["T06", "T08", "T11"],
    "filesystem_read":              ["T09", "T15"],
    "filesystem_write":             ["T09", "T15"],
    "constitution_change":          ["T13", "T15"],
    "register_new_source_tool":     ["T01", "T13", "T14"],
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class GovernorError(RuntimeError):
    """Raised for unrecoverable governor errors (bad policy, bad CLI).
    Distinct from a normal 'allowed=false' decision: a GovernorError
    means the Governor itself could not run."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """SHA-256 of a file, hex-encoded, computed in 64 KiB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_policy(path: Path) -> dict:
    if not path.is_file():
        raise GovernorError("policy file not found: " + str(path))
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise GovernorError("policy is not valid JSON: " + str(e)) from e
    if not isinstance(data, dict):
        raise GovernorError("policy must be a JSON object")
    return data


def _validate_policy_v01(policy: dict) -> None:
    """Hard invariants enforced at policy load. Anything beyond these
    is structural validation handled by JSON schema in tests."""
    if policy.get("schema") != SCHEMA_POLICY:
        raise GovernorError(
            "policy.schema must be " + repr(SCHEMA_POLICY)
            + ", got " + repr(policy.get("schema"))
        )
    mode = policy.get("mode")
    if mode not in SHIPPED_MODES:
        raise GovernorError(
            "v0.1 ships only mode in " + repr(SHIPPED_MODES)
            + "; got mode=" + repr(mode) + ". The other modes "
            "(propose, execute_bounded) are documented in the schema "
            "but require a sprint upgrade to enable in code."
        )
    caps_per_day = policy.get("caps_per_day") or {}
    asost = caps_per_day.get("autonomous_sost_stocks", 0)
    if asost != 0:
        raise GovernorError(
            "v0.1 hardcodes caps_per_day.autonomous_sost_stocks=0 "
            "(SECURITY.md T08 — autonomous payment abuse). Got "
            "autonomous_sost_stocks=" + repr(asost) + ". Enabling "
            "autonomous spending is a sprint upgrade, not a config "
            "edit."
        )
    # Lightweight required-keys check so error messages are friendlier
    # than the schema validator's. The schema test is the source of
    # truth.
    for required_key in ("allowlists", "require_human_approval",
                          "kill_switch", "audit", "caps_per_day",
                          "caps_per_hour", "version"):
        if required_key not in policy:
            raise GovernorError("policy missing required key: " + required_key)


def _check_halt(policy: dict) -> bool:
    halt_file = (policy.get("kill_switch") or {}).get("halt_file")
    if not halt_file:
        return False
    return Path(halt_file).exists()


def _path_starts_with_any(path: str, prefixes) -> bool:
    """True when ``path`` starts with any of the prefixes. Treats
    prefixes ending in '/' as directory prefixes; exact file names match
    when the prefix equals the path exactly."""
    p = (path or "").strip()
    for prefix in prefixes or []:
        if not prefix:
            continue
        if p == prefix:
            return True
        if prefix.endswith("/") and p.startswith(prefix):
            return True
        if not prefix.endswith("/") and (p == prefix or p.startswith(prefix + "/")):
            return True
    return False


def _make_decision_id(action: str, action_params: dict, pinned_time: str) -> str:
    """Deterministic decision id from (action, action_params, pinned_time).
    Two identical inputs ⇒ same decision_id. 32 hex chars."""
    blob = json.dumps(
        {"action": action, "action_params": action_params, "pinned_time": pinned_time},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


# ---------------------------------------------------------------------------
# The core: evaluate one (action, params) pair against the policy.
# ---------------------------------------------------------------------------

def decide(
    policy,
    policy_path,
    boot_policy_sha256,
    action,
    action_params,
    pinned_time,
):
    """Return the decision dict. Never executes the action."""
    if action_params is None:
        action_params = {}

    # Recompute the policy hash NOW. This protects against the YAML
    # being rewritten between boot and decision (T15 log tampering /
    # T13 supply-chain mutation).
    runtime_sha = _sha256_file(policy_path)
    policy_hashes_match = (runtime_sha == boot_policy_sha256)

    caps_checked = {}
    allowlists_checked = {}
    blocked_reason = None
    allowed = True

    # Halt switch check happens first so the kill_switch_checked field
    # is always populated even when other checks would have blocked.
    halt_present = _check_halt(policy)
    kill_switch_checked = {"halt_file": bool(halt_present)}

    if not policy_hashes_match:
        allowed = False
        blocked_reason = "policy_mutated_at_runtime"

    if halt_present and blocked_reason is None:
        allowed = False
        blocked_reason = "halt_file_present"

    # Unknown action ⇒ refuse. We still emit a decision so the call is
    # auditable; we just block.
    if action not in KNOWN_ACTIONS and blocked_reason is None:
        allowed = False
        blocked_reason = "unknown_action:" + action

    # The require-human-approval list is policy-driven AND backed by a
    # hardcoded fallback so a permissive policy can never bypass it.
    policy_human_required = set(policy.get("require_human_approval") or [])
    requires_human_approval = (
        action in ALWAYS_REQUIRE_HUMAN_APPROVAL
        or action in policy_human_required
    )
    if requires_human_approval and blocked_reason is None:
        allowed = False
        blocked_reason = "requires_human_approval"

    allowlists = policy.get("allowlists") or {}
    caps_per_day = policy.get("caps_per_day") or {}

    # -------------------------------------------------------------------
    # Per-action checks. Each populates caps_checked / allowlists_checked
    # and may set allowed=False with a blocked_reason. They run even when
    # a prior check has already blocked (so the audit log shows what
    # ELSE would have failed); but the first blocked_reason wins.
    # -------------------------------------------------------------------
    if action == "create_request":
        st = action_params.get("source_tool")
        st_allowed = st in (allowlists.get("source_tools") or [])
        allowlists_checked["source_tools"] = {
            "value": st,
            "allowed": bool(st_allowed),
        }
        if not st_allowed and blocked_reason is None:
            allowed = False
            blocked_reason = "source_tool_not_in_allowlist"

        cap = int(caps_per_day.get("requests_created", 0))
        # v0.1 has no persistent counter. The caller may pass an explicit
        # usage hint via action_params for tests / future runtime; default 0.
        usage = int(action_params.get("requests_created_today", 0))
        caps_checked["requests_created"] = {"cap": cap, "usage": usage}
        if usage >= cap and blocked_reason is None:
            allowed = False
            blocked_reason = "cap.requests_created_exceeded"

    elif action == "launch_worker":
        cap = int(caps_per_day.get("workers_launched", 0))
        usage = int(action_params.get("workers_launched_today", 0))
        caps_checked["workers_launched"] = {"cap": cap, "usage": usage}
        if usage >= cap and blocked_reason is None:
            allowed = False
            blocked_reason = "cap.workers_launched_exceeded"

    elif action == "call_rpc":
        method = action_params.get("rpc_method")
        method_allowed = method in (allowlists.get("rpc_methods") or [])
        allowlists_checked["rpc_methods"] = {
            "value": method,
            "allowed": bool(method_allowed),
        }
        if not method_allowed and blocked_reason is None:
            allowed = False
            blocked_reason = "rpc_method_not_in_allowlist"

    elif action == "filesystem_read":
        path = action_params.get("path", "")
        forbidden = allowlists.get("filesystem_forbidden") or []
        readable = allowlists.get("filesystem_read") or []
        is_forbidden = _path_starts_with_any(path, forbidden)
        is_readable = _path_starts_with_any(path, readable)
        allowlists_checked["filesystem_read"] = {
            "value": path,
            "allowed": (not is_forbidden) and is_readable,
        }
        if is_forbidden and blocked_reason is None:
            allowed = False
            blocked_reason = "filesystem_path_forbidden"
        elif not is_readable and blocked_reason is None:
            allowed = False
            blocked_reason = "filesystem_path_not_in_allowlist"

    elif action == "filesystem_write":
        path = action_params.get("path", "")
        forbidden = allowlists.get("filesystem_forbidden") or []
        writable = allowlists.get("filesystem_write") or []
        is_forbidden = _path_starts_with_any(path, forbidden)
        # Belt-and-tirantes: never allow writing the policy file itself,
        # even if the operator forgot to put it in filesystem_forbidden.
        policy_basename = policy_path.name
        is_policy = (path == str(policy_path)) or (path.endswith(policy_basename))
        is_writable = _path_starts_with_any(path, writable)
        allowlists_checked["filesystem_write"] = {
            "value": path,
            "allowed": (not is_forbidden) and (not is_policy) and is_writable,
        }
        if is_policy and blocked_reason is None:
            allowed = False
            blocked_reason = "cannot_write_constitution"
        elif is_forbidden and blocked_reason is None:
            allowed = False
            blocked_reason = "filesystem_path_forbidden"
        elif not is_writable and blocked_reason is None:
            allowed = False
            blocked_reason = "filesystem_path_not_in_allowlist"

    # The five always-human actions (real_sign, broadcast_signed_transaction,
    # wallet_access, constitution_change, register_new_source_tool) don't
    # need per-action allowlist/cap logic: they were already blocked above
    # by the always-require-human-approval rule.

    decision_id = _make_decision_id(action, action_params, pinned_time)

    decision = {
        "schema":                  SCHEMA_DECISION,
        "decision_id":             decision_id,
        "policy_sha256":           boot_policy_sha256,
        "policy_runtime_sha256":   runtime_sha,
        "policy_hashes_match":     bool(policy_hashes_match),
        "policy_path_basename":    policy_path.name,
        "action":                  action,
        "action_params":           dict(action_params),
        "mode":                    policy.get("mode"),
        "allowed":                 bool(allowed),
        "blocked_reason":          blocked_reason,
        "requires_human_approval": bool(requires_human_approval),
        "caps_checked":            caps_checked,
        "allowlists_checked":      allowlists_checked,
        "kill_switch_checked":     kill_switch_checked,
        "safety_status":           "ok",
        "threat_refs":             list(THREAT_REFS.get(action, [])),
        "pinned_time":             pinned_time,
    }
    return decision


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_action_param(s):
    if "=" not in s:
        raise GovernorError(
            "--action-param must be key=value, got " + repr(s)
        )
    k, v = s.split("=", 1)
    k = k.strip()
    v = v.strip()
    # Coerce ints when possible so usage thresholds are integers.
    try:
        v_int = int(v)
        return k, v_int
    except ValueError:
        pass
    # Coerce simple booleans for symmetry.
    if v.lower() in ("true", "false"):
        return k, (v.lower() == "true")
    return k, v


def _default_pinned_time():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Trinity Autonomy Governor v0.1 (observe-only)."
    )
    parser.add_argument("--policy", required=True, type=Path,
                        help="Path to trinity_autonomy_governor JSON policy.")
    parser.add_argument("--action", required=True,
                        help="Action name to evaluate (see KNOWN_ACTIONS).")
    parser.add_argument("--action-param", action="append", default=[],
                        metavar="KEY=VALUE",
                        help="Repeatable. Action parameters as key=value.")
    parser.add_argument("--out-dir", required=True, type=Path,
                        help="Directory where the decision JSON is written.")
    parser.add_argument("--pinned-time", default=None,
                        help="ISO-8601 timestamp. Defaults to now-UTC. "
                             "Pin it for deterministic decision_id.")
    args = parser.parse_args(argv)

    pinned_time = args.pinned_time or _default_pinned_time()

    try:
        action_params = {}
        for raw in args.action_param:
            k, v = _parse_action_param(raw)
            action_params[k] = v

        boot_sha = _sha256_file(args.policy)
        policy = _read_policy(args.policy)
        _validate_policy_v01(policy)

        decision = decide(
            policy=policy,
            policy_path=args.policy,
            boot_policy_sha256=boot_sha,
            action=args.action,
            action_params=action_params,
            pinned_time=pinned_time,
        )
    except GovernorError as e:
        sys.stderr.write("[autonomy_governor] ERROR: " + str(e) + "\n")
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / (
        "TRINITY_AUTONOMY_GOVERNOR_DECISION_" + decision["decision_id"] + ".json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(decision, f, indent=2, sort_keys=True)
        f.write("\n")

    sys.stdout.write(str(out_path) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
