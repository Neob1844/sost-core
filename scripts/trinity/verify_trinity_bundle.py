#!/usr/bin/env python3
"""Trinity Proof Bundle verifier.

Reads a `TRINITY_PROOF_BUNDLE_<name>.json` file and runs a closed list
of integrity checks. Exits 0 only if every check passes.

Checks performed
----------------

  C1. The JSON parses, and `schema == "trinity-proof-bundle/v0"`.
  C2. Every anchor SHA is a 64-char lowercase hex string.
  C3. The Merkle root recomputed from the four anchors with the
      documented algorithm equals the value stored in the bundle.
  C4. `safety_status.dry_run == true`.
  C5. `safety_status.registered == false`.
  C6. `safety_status.no_rewards_active == true`.
  C7. `safety_status.ready_to_register == true`.
  C8. The bundle's canonical JSON contains no absolute filesystem
      path prefix ("/home/", "/opt/", "/Users/", "C:/", "C:\\\\").
  C9. The capsule preview reports `execution_status` containing
      "NOT_EXECUTED" — proof that the bundle generator did not
      broadcast anything.
  C10. For every local file whose basename matches a recorded
       anchor basename (`dossier`, `useful_compute_plan`,
       `campaign`), the file's SHA-256 is recomputed and compared
       against the stored anchor. The verifier looks for those
       files alongside the bundle path and in the current working
       directory. Files that are not found locally produce a
       SKIPPED line, never a FAIL.

The verifier never opens a network connection, never calls SOST RPC,
never touches a wallet, never executes `sost-cli`.

Usage
-----
    python3 scripts/trinity/verify_trinity_bundle.py <bundle.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA = "trinity-proof-bundle/v0"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\\\")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _merkle_root_from_hashes(
    sc: str, do: str, pl: str, ca: str,
) -> str:
    leaves = [bytes.fromhex(h) for h in (sc, do, pl, ca)]
    node01 = hashlib.sha256(leaves[0] + leaves[1]).digest()
    node23 = hashlib.sha256(leaves[2] + leaves[3]).digest()
    return hashlib.sha256(node01 + node23).hexdigest()


def _check_hex64(name: str, value: Any) -> Optional[str]:
    if not isinstance(value, str) or not _HEX64_RE.match(value):
        return f"{name}: not a 64-char lowercase hex SHA-256 (got {value!r})"
    return None


def verify_bundle(
    bundle_path: Path,
    *,
    search_paths: Optional[List[Path]] = None,
) -> Tuple[bool, List[str]]:
    """Run every check on the bundle at `bundle_path`.

    Returns `(ok, lines)`. `lines` is a list of human-readable
    `[PASS]` / `[FAIL]` / `[SKIP]` entries. `ok` is True iff there
    are zero FAIL entries.
    """
    lines: List[str] = []
    failures: List[str] = []

    def record_pass(msg: str) -> None:
        lines.append(f"[PASS] {msg}")

    def record_fail(msg: str) -> None:
        lines.append(f"[FAIL] {msg}")
        failures.append(msg)

    def record_skip(msg: str) -> None:
        lines.append(f"[SKIP] {msg}")

    if not bundle_path.exists():
        record_fail(f"bundle file not found: {bundle_path}")
        return (False, lines)

    raw = bundle_path.read_bytes()
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        record_fail(f"C1 bundle is not valid JSON: {e}")
        return (False, lines)

    # C1: schema.
    schema = bundle.get("schema")
    if schema == _SCHEMA:
        record_pass(f"C1 schema = {_SCHEMA!r}")
    else:
        record_fail(f"C1 schema is {schema!r}, expected {_SCHEMA!r}")

    # C2: anchor SHA shapes.
    anchors = bundle.get("anchors") or {}
    anchor_keys = (
        "scorecard_sha256",
        "dossier_sha256",
        "useful_compute_plan_sha256",
        "campaign_sha256",
    )
    bad_shape = []
    for k in anchor_keys:
        # Stored format is lowercase by construction; if uppercase or
        # malformed, we report.
        err = _check_hex64(f"anchors.{k}", anchors.get(k))
        if err:
            bad_shape.append(err)
    if not bad_shape:
        record_pass("C2 anchors: all four are 64-char lowercase hex")
    else:
        for err in bad_shape:
            record_fail(f"C2 {err}")

    # C3: Merkle root.
    merkle = bundle.get("merkle") or {}
    stored_root = merkle.get("root")
    try:
        recomputed = _merkle_root_from_hashes(
            anchors.get("scorecard_sha256"),
            anchors.get("dossier_sha256"),
            anchors.get("useful_compute_plan_sha256"),
            anchors.get("campaign_sha256"),
        )
        if recomputed == stored_root:
            record_pass(f"C3 merkle root matches recomputed value")
        else:
            record_fail(
                f"C3 merkle root mismatch: stored {stored_root!r}, "
                f"recomputed {recomputed!r}"
            )
    except (ValueError, TypeError) as e:
        record_fail(f"C3 merkle recompute failed: {e}")

    # C4 / C5 / C6 / C7: safety_status flags.
    ss = bundle.get("safety_status") or {}
    for code, key, want in (
        ("C4", "dry_run", True),
        ("C5", "registered", False),
        ("C6", "no_rewards_active", True),
        ("C7", "ready_to_register", True),
    ):
        actual = ss.get(key)
        if actual is want:
            record_pass(f"{code} safety_status.{key} = {want}")
        else:
            record_fail(
                f"{code} safety_status.{key} is {actual!r}, expected {want}"
            )

    # C8: no host paths in canonical JSON.
    blob = raw.decode("utf-8", errors="replace")
    leaked_markers = [m for m in _HOST_PREFIXES if m in blob]
    if not leaked_markers:
        record_pass("C8 canonical JSON contains no absolute host path")
    else:
        record_fail(
            f"C8 host path markers leaked into JSON: {leaked_markers}"
        )

    # C9: capsule preview reports NOT_EXECUTED.
    cp = bundle.get("capsule_preview") or {}
    exec_status = str(cp.get("execution_status") or "")
    if "NOT_EXECUTED" in exec_status:
        record_pass(
            "C9 capsule_preview.execution_status reports NOT_EXECUTED"
        )
    else:
        record_fail(
            f"C9 capsule_preview.execution_status is {exec_status!r}; "
            f"missing NOT_EXECUTED marker"
        )

    # C10: local re-hash of any artefact whose basename matches an
    # anchor basename and which exists in a known search path.
    search_paths = list(search_paths or [])
    if not search_paths:
        search_paths = [bundle_path.parent, Path.cwd()]
    basenames = bundle.get("anchor_basenames") or {}
    for label, anchor_key in (
        ("dossier", "dossier_sha256"),
        ("useful_compute_plan", "useful_compute_plan_sha256"),
        ("campaign", "campaign_sha256"),
    ):
        bn = basenames.get(label)
        if not isinstance(bn, str) or not bn or bn.startswith("<"):
            record_skip(
                f"C10 {label}: no local basename recorded "
                f"(value={bn!r})"
            )
            continue
        found_path = None
        for root in search_paths:
            candidate = root / bn
            if candidate.exists():
                found_path = candidate
                break
        if found_path is None:
            record_skip(
                f"C10 {label}: file {bn!r} not found in search paths"
            )
            continue
        local_sha = _file_sha256(found_path)
        anchor_sha = anchors.get(anchor_key)
        if local_sha == anchor_sha:
            record_pass(
                f"C10 {label}: local SHA matches anchor "
                f"({local_sha[:16]}...)"
            )
        else:
            record_fail(
                f"C10 {label}: local SHA {local_sha!r} != anchor "
                f"{anchor_sha!r} (file {found_path})"
            )

    return (not failures, lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="verify_trinity_bundle",
        description=(
            "Verify a Trinity Proof Bundle JSON. Exits 0 on success."
        ),
    )
    p.add_argument("bundle", type=str,
                   help="Path to TRINITY_PROOF_BUNDLE_<name>.json")
    p.add_argument("--search-path", action="append", type=str, default=None,
                   help="Extra directory to search for local artefacts. "
                        "Repeatable. Defaults to the bundle's directory "
                        "plus the current working directory.")
    args = p.parse_args(argv)

    bundle_path = Path(args.bundle).resolve()
    extras = [Path(s).resolve() for s in (args.search_path or [])
              if s and Path(s).exists()]
    search_paths = extras + [bundle_path.parent, Path.cwd()]

    ok, lines = verify_bundle(bundle_path, search_paths=search_paths)

    for line in lines:
        print(line)
    print()
    if ok:
        print(f"[verify] OK — bundle {bundle_path.name} is valid.")
        return 0
    fail_count = sum(1 for line in lines if line.startswith("[FAIL]"))
    print(
        f"[verify] FAILED — {fail_count} check(s) failed on "
        f"{bundle_path.name}."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
