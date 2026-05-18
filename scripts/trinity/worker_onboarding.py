#!/usr/bin/env python3
"""Trinity Friendly Worker Onboarding v0.1 (Sprint 5.35).

Generates a read-only onboarding bundle that documents what a new
Trinity Useful Compute worker needs to know to run safely. NO
keys, NO wallets, NO secrets, NO payment addresses. The bundle is
a single deterministic JSON file plus a printable safety
checklist.

Hard invariants v0.1 (enforced by static tests):
    - No network. No remote calls. No DNS lookup.
    - No wallet creation. No private-key generation. No seed
      phrase. No signing. No broadcasting.
    - No child process, no shell, no eval / exec.
    - The bundle MUST NOT contain any key, secret, private path,
      mnemonic, or wallet path. Address-map entries are template
      placeholders only (the operator supplies real values
      separately, out of band).

Usage:
    python3 scripts/trinity/worker_onboarding.py \\
        --worker-id worker-C \\
        --out-json /var/lib/trinity/onboarding/worker-C.json \\
        --pinned-time 2026-05-18T00:00:00+00:00

Output:
    trinity-worker-onboarding-bundle/v0.1 JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_BUNDLE = "trinity-worker-onboarding-bundle/v0.1"

# Pinned default backends an operator may run with --backend on
# the worker CLI. These mirror the names registered in
# scripts/trinity/useful_compute_backends.py. Kept here as a
# constant so the onboarding doc is stable across worker host
# upgrades and so we never have to import the backends module
# (which would couple worker hosts to the Trinity Python tree).
SUPPORTED_BACKENDS = (
    {
        "name": "placeholder",
        "kind": "placeholder",
        "experimental": False,
        "note": "auto-routes to placeholder_<task_type> per request",
    },
    {
        "name": "placeholder_scientific_intake",
        "kind": "placeholder",
        "experimental": False,
        "note": "hash-manifest-only output; default for scientific_intake",
    },
    {
        "name": "local_materials_engine_v01",
        "kind": "real_backend",
        "experimental": False,
        "note": (
            "Sprint 5.32 real_backend; auto-routed when "
            "source_tool=materials_engine + classifier metadata"
        ),
    },
    {
        "name": "local_python_numeric_v01",
        "kind": "sandbox_toy",
        "experimental": True,
        "note": "stdlib-only deterministic numeric loop",
    },
    {
        "name": "local_structure_relaxation_toy_v01",
        "kind": "sandbox_toy",
        "experimental": True,
        "note": "stdlib-only deterministic toy relaxation",
    },
    {
        "name": "local_dft_toy_v01",
        "kind": "sandbox_toy",
        "experimental": True,
        "note": "stdlib-only deterministic power-method surrogate",
    },
)

REQUIRED_COMMANDS = (
    {
        "name": "useful_compute_worker",
        "script": "scripts/trinity/useful_compute_worker.py",
        "purpose": "run one local-dry-run compute over a request JSON",
        "example_argv": [
            "--mode", "local-dry-run",
            "--request", "<request.json>",
            "--out-dir", "<worker_out_dir>",
            "--worker-id", "<worker_id>",
            "--pinned-time", "<ISO-8601>",
        ],
        "requires_wallet":     False,
        "requires_private_key": False,
        "requires_network":     False,
    },
    {
        "name": "useful_compute_replay_validator",
        "script": "scripts/trinity/useful_compute_replay_validator.py",
        "purpose": "cross-worker hash agreement check",
        "example_argv": [
            "--worker-out", "<dir>",
            "--out-json", "<validation.json>",
        ],
        "requires_wallet":     False,
        "requires_private_key": False,
        "requires_network":     False,
    },
)

DEFAULT_SAFETY_CHECKLIST = (
    "no wallet on the worker host",
    "no private key on the worker host",
    "no seed phrase on the worker host",
    "no broadcast capability on the worker host",
    "network access required only for fetching the request artifact "
    "and uploading the result artifact (out-of-band; the worker "
    "process itself never opens a socket)",
    "operator-supplied --worker-id is a public label; the bundle "
    "stores both the label and its sha16 hash for audit",
    "the worker host must not run any chain-cli send / "
    "send-raw-transaction / sign-tx / wallet command in the same "
    "shell session",
)

ADDRESS_MAP_TEMPLATE_NOTICE = (
    "Address-map entries below are TEMPLATE PLACEHOLDERS. The "
    "operator must replace <PAYOUT_ADDRESS_FOR_WORKER_ID> with a "
    "real SOST address out-of-band; this bundle never contains a "
    "real address. Distributing the bundle does not distribute "
    "any payout authority."
)


class OnboardingError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _validate_worker_id(worker_id: str) -> None:
    if not isinstance(worker_id, str):
        raise OnboardingError("worker-id must be a string")
    if not (1 <= len(worker_id) <= 64):
        raise OnboardingError(
            "worker-id length must be 1..64; got "
            + str(len(worker_id))
        )
    for ch in worker_id:
        if not (ch.isalnum() or ch in "-_."):
            raise OnboardingError(
                "worker-id may only contain [A-Za-z0-9._-]; "
                "found " + repr(ch)
            )


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------


def build_bundle(
    *,
    worker_id: str,
    pinned_time: str,
    repo_root_basename: str = "sost-core",
) -> Dict[str, Any]:
    """Build the onboarding bundle dict. Deterministic for a fixed
    (worker_id, pinned_time, repo_root_basename) — same inputs
    always produce the same bytes."""
    _validate_worker_id(worker_id)
    worker_id_hash = _sha16(worker_id)

    address_map_template = {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {
                "worker_id_hash": worker_id_hash,
                "payout_address": "<PAYOUT_ADDRESS_FOR_" + worker_id + ">",
                "label": worker_id,
            },
        ],
        "_template_notice": ADDRESS_MAP_TEMPLATE_NOTICE,
    }

    bundle: Dict[str, Any] = {
        "schema":             SCHEMA_BUNDLE,
        "bundle_id":          "twob-" + _sha16(_canonical_dumps({
            "worker_id":   worker_id,
            "pinned_time": pinned_time,
        })),
        "worker_id":          worker_id,
        "worker_id_hash":     worker_id_hash,
        "pinned_time":        pinned_time,
        "repo_root_basename": repo_root_basename,
        "supported_backends": [dict(b) for b in SUPPORTED_BACKENDS],
        "required_commands":  [dict(c) for c in REQUIRED_COMMANDS],
        "sample_paths": {
            "request_json_example":
                "tests/trinity/fixtures/useful_compute/"
                "request_scientific_intake.json",
            "worker_address_map_example":
                "tests/trinity/fixtures/useful_compute/address_map.json",
            "governor_policy_example":
                "config/trinity_autonomy_governor.example.json",
            "queue_dir_example":
                "/var/lib/trinity/queues/main",
        },
        "address_map_template": address_map_template,
        "safety_checklist":   list(DEFAULT_SAFETY_CHECKLIST),
        "safety_status": {
            "no_wallet_required":           True,
            "no_private_key_required":      True,
            "no_seed_phrase_required":      True,
            "no_broadcast_capability":      True,
            "no_network_in_worker_process": True,
            "bundle_carries_no_secrets":    True,
        },
        "notes": [
            "v0.1 onboarding bundle is read-only by design.",
            "Bundle file can be distributed publicly; it contains "
            "no secret material.",
            "The operator must run worker hosts under a Linux user "
            "that does NOT own any wallet file or signing key.",
        ],
    }
    return bundle


# ---------------------------------------------------------------------------
# Bundle writer
# ---------------------------------------------------------------------------
#
# Secret-leak protection is layered:
#   1. The bundle structure is hard-coded in build_bundle() above
#      and only the worker_id is operator-supplied; it is validated
#      to [A-Za-z0-9._-] so no path-traversal or shell-escape gets
#      into the JSON.
#   2. The schema (additionalProperties=false everywhere, plus
#      const-locked safety_status flags and a payout_address
#      pattern that requires the <PAYOUT_ADDRESS_FOR_*> placeholder
#      form) rejects any wrongly-shaped bundle at validate time.
#   3. The unit tests grep the rendered bundle for explicit secret
#      patterns (64-hex private keys, BIP39 mnemonic stems, real
#      sost1 addresses) and assert none are present.
# No defensive in-code substring grep here: the safety_status
# flag names themselves use words like 'private_key' (in
# 'no_private_key_required'), so a plain-substring guard would
# false-positive on its own contract.


def write_bundle(bundle: Dict[str, Any], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _canonical_dumps(bundle) + "\n", encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="worker_onboarding",
        description=(
            "Trinity Friendly Worker Onboarding v0.1. Generates a "
            "deterministic, read-only onboarding bundle for a new "
            "Useful Compute worker. NEVER touches a wallet, NEVER "
            "creates a key, NEVER opens the network."
        ),
    )
    p.add_argument("--worker-id", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--pinned-time", default=None)
    p.add_argument("--repo-root-basename", default="sost-core")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()
    try:
        bundle = build_bundle(
            worker_id=args.worker_id,
            pinned_time=pinned,
            repo_root_basename=args.repo_root_basename,
        )
        out_path = write_bundle(bundle, Path(args.out_json))
    except OnboardingError as exc:
        print(
            "[worker_onboarding] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    print(
        "[worker_onboarding] bundle_id=" + bundle["bundle_id"]
        + " worker_id=" + bundle["worker_id"]
        + " worker_id_hash=" + bundle["worker_id_hash"]
        + " out=" + str(out_path)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
