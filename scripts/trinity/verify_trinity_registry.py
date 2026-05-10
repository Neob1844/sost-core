#!/usr/bin/env python3
"""Trinity Proof Registry verifier.

Reads a ``TRINITY_PROOF_REGISTRY.json`` file and runs a closed list of
integrity checks. Exits 0 only if every check passes. Output mirrors
``verify_trinity_bundle.py``: each check prints ``[PASS]`` / ``[FAIL]``
/ ``[SKIP]``.

Checks performed
----------------

  R1.  The JSON parses, and ``schema == "trinity-proof-registry/v0"``.
  R2.  ``registry_generated_at_utc`` is a non-empty string ending in
       ``+00:00``.
  R3.  ``network`` is a non-empty string.
  R4.  ``entries`` is a non-empty list of dicts.
  R5.  All ``entry.id`` are unique.
  R6.  Every entry has 64-char lowercase hex ``txid``,
       ``proof_bundle_sha256`` and ``merkle_root``.
  R7.  Every entry's ``proof_bundle_sha16`` equals the first 16 chars of
       its ``proof_bundle_sha256``.
  R8.  Every entry's ``capsule_text`` contains ``proof_bundle_sha16``.
  R9.  Every entry's ``status`` and ``capsule_mode`` are in their
       allowed sets, and ``block_height`` is a positive int.
  R10. Every entry's ``safety_status`` carries the five required
       Trinity flags, all set to ``True``.
  R11. The registry's canonical JSON contains no absolute filesystem
       path prefix (``/home/``, ``/opt/``, ``/Users/``, ``C:/``,
       ``C:\\``).
  R12. For every anchor file basename present in an entry, if the file
       exists in a search path, its SHA-256 is recomputed. The
       ``proof_bundle`` basename's hash must equal
       ``proof_bundle_sha256``. Other anchor files (when present) are
       reported as ``[INFO]`` lines and never as ``[FAIL]``.
  R13. If the proof bundle is found locally and
       ``verify_trinity_bundle.verify_bundle`` is importable, the
       bundle is re-verified offline. A FAIL there is propagated as
       ``[FAIL]`` here.

The verifier never opens a network connection, never calls SOST RPC,
never touches a wallet, never executes ``sost-cli``.

Usage
-----
    python3 scripts/trinity/verify_trinity_registry.py \\
        TRINITY_PROOF_REGISTRY.json
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
_SCHEMA = "trinity-proof-registry/v0"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")
_ALLOWED_STATUS = ("registered", "ready_to_register", "draft")
_ALLOWED_CAPSULE_MODES = ("open-note", "doc-ref")
_ALLOWED_TRACKS = ("earth", "materials")
_DEFAULT_TRACK = "earth"
_REQUIRED_SAFETY_FIELDS = (
    "not_a_mineral_reserve_claim",
    "not_a_geological_conclusion",
    "no_active_useful_compute_rewards",
    "no_auto_broadcast",
    "no_consensus_change",
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64_RE.match(value))


def _try_offline_bundle_verification(
    bundle_path: Path,
    *,
    search_paths: List[Path],
) -> Optional[bool]:
    """Try to call ``verify_trinity_bundle.verify_bundle`` if importable."""
    repo_scripts = Path(__file__).resolve().parent
    inserted = False
    if str(repo_scripts) not in sys.path:
        sys.path.insert(0, str(repo_scripts))
        inserted = True
    try:
        try:
            import verify_trinity_bundle  # type: ignore[import-not-found]
        except ImportError:
            return None
        ok, _ = verify_trinity_bundle.verify_bundle(
            bundle_path, search_paths=search_paths,
        )
        return bool(ok)
    finally:
        if inserted:
            try:
                sys.path.remove(str(repo_scripts))
            except ValueError:
                pass


def verify_registry(
    registry_path: Path,
    *,
    search_paths: Optional[List[Path]] = None,
) -> Tuple[bool, List[str]]:
    """Run every check on the registry at ``registry_path``."""
    lines: List[str] = []
    failures: List[str] = []

    def record_pass(msg: str) -> None:
        lines.append(f"[PASS] {msg}")

    def record_fail(msg: str) -> None:
        lines.append(f"[FAIL] {msg}")
        failures.append(msg)

    def record_skip(msg: str) -> None:
        lines.append(f"[SKIP] {msg}")

    def record_info(msg: str) -> None:
        lines.append(f"[INFO] {msg}")

    if not registry_path.exists():
        record_fail(f"registry file not found: {registry_path}")
        return (False, lines)

    raw = registry_path.read_bytes()
    try:
        registry = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        record_fail(f"R1 registry is not valid JSON: {e}")
        return (False, lines)

    schema = registry.get("schema")
    if schema == _SCHEMA:
        record_pass(f"R1 schema = {_SCHEMA!r}")
    else:
        record_fail(
            f"R1 schema is {schema!r}, expected {_SCHEMA!r}"
        )

    gen = registry.get("registry_generated_at_utc")
    if (
        isinstance(gen, str)
        and gen.endswith("+00:00")
        and len(gen) >= len("YYYY-MM-DDTHH:MM:SS+00:00")
    ):
        record_pass(f"R2 registry_generated_at_utc = {gen!r}")
    else:
        record_fail(
            f"R2 registry_generated_at_utc must end in +00:00 "
            f"(got {gen!r})"
        )

    net = registry.get("network")
    if isinstance(net, str) and net.strip():
        record_pass(f"R3 network = {net!r}")
    else:
        record_fail(
            f"R3 network must be a non-empty string (got {net!r})"
        )

    entries = registry.get("entries")
    if (
        not isinstance(entries, list)
        or not entries
        or not all(isinstance(e, dict) for e in entries)
    ):
        record_fail(
            f"R4 entries must be a non-empty list of dicts "
            f"(got {type(entries).__name__})"
        )
        # Without entries, later checks are pointless.
        return (False, lines)
    record_pass(f"R4 entries: {len(entries)} entry/entries present")

    seen_ids = set()
    duplicate_ids: List[str] = []
    for e in entries:
        eid = e.get("id")
        if isinstance(eid, str) and eid:
            if eid in seen_ids:
                duplicate_ids.append(eid)
            seen_ids.add(eid)
        else:
            duplicate_ids.append(repr(eid))
    if duplicate_ids:
        record_fail(
            f"R5 duplicate or missing entry ids: {duplicate_ids}"
        )
    else:
        record_pass(f"R5 entry ids unique: {sorted(seen_ids)}")

    search_paths = list(search_paths or [])
    if not search_paths:
        search_paths = [registry_path.parent, Path.cwd()]

    for idx, e in enumerate(entries):
        prefix = f"entries[{idx}] (id={e.get('id')!r})"

        # R6: hex shapes.
        bad_hex: List[str] = []
        for k in ("txid", "proof_bundle_sha256", "merkle_root"):
            if not _is_hex64(e.get(k)):
                bad_hex.append(f"{k}={e.get(k)!r}")
        if bad_hex:
            record_fail(f"R6 {prefix}: invalid hex64 fields: {bad_hex}")
        else:
            record_pass(
                f"R6 {prefix}: txid + proof_bundle_sha256 + merkle_root "
                f"are 64-char lowercase hex"
            )

        # R7: sha16 prefix.
        full_sha = e.get("proof_bundle_sha256")
        sha16 = e.get("proof_bundle_sha16")
        if (
            isinstance(full_sha, str)
            and isinstance(sha16, str)
            and len(sha16) == 16
            and sha16 == full_sha[:16]
        ):
            record_pass(
                f"R7 {prefix}: proof_bundle_sha16 = first 16 hex of "
                f"proof_bundle_sha256"
            )
        else:
            record_fail(
                f"R7 {prefix}: proof_bundle_sha16 must equal first 16 "
                f"chars of proof_bundle_sha256 (sha16={sha16!r}, "
                f"full_sha={full_sha!r})"
            )

        # R8: capsule_text contains sha16.
        capsule_text = e.get("capsule_text")
        if (
            isinstance(capsule_text, str)
            and isinstance(sha16, str)
            and sha16 in capsule_text
        ):
            record_pass(
                f"R8 {prefix}: capsule_text contains "
                f"proof_bundle_sha16"
            )
        else:
            record_fail(
                f"R8 {prefix}: capsule_text {capsule_text!r} must "
                f"contain proof_bundle_sha16 {sha16!r}"
            )

        # R9: status / capsule_mode / block_height / track.
        status = e.get("status")
        capsule_mode = e.get("capsule_mode")
        block_height = e.get("block_height")
        track = e.get("track", _DEFAULT_TRACK)
        r9_errors: List[str] = []
        if status not in _ALLOWED_STATUS:
            r9_errors.append(
                f"status {status!r} not in {_ALLOWED_STATUS}"
            )
        if capsule_mode not in _ALLOWED_CAPSULE_MODES:
            r9_errors.append(
                f"capsule_mode {capsule_mode!r} not in "
                f"{_ALLOWED_CAPSULE_MODES}"
            )
        if (
            not isinstance(block_height, int)
            or isinstance(block_height, bool)
            or block_height <= 0
        ):
            r9_errors.append(
                f"block_height must be a positive int (got "
                f"{block_height!r})"
            )
        if track not in _ALLOWED_TRACKS:
            r9_errors.append(
                f"track {track!r} not in {_ALLOWED_TRACKS}"
            )
        if r9_errors:
            record_fail(f"R9 {prefix}: {'; '.join(r9_errors)}")
        else:
            record_pass(
                f"R9 {prefix}: status={status!r}, "
                f"capsule_mode={capsule_mode!r}, "
                f"track={track!r}, "
                f"block_height={block_height}"
            )

        # R10: safety_status.
        safety = e.get("safety_status") or {}
        missing = [
            k for k in _REQUIRED_SAFETY_FIELDS
            if safety.get(k) is not True
        ]
        if missing:
            record_fail(
                f"R10 {prefix}: required safety fields missing or not "
                f"True: {missing}"
            )
        else:
            record_pass(
                f"R10 {prefix}: all five required safety_status flags "
                f"are True"
            )

        # R12: anchor file rehash where present.
        anchor_files = e.get("anchor_files") or {}
        if not isinstance(anchor_files, dict) or not anchor_files:
            record_skip(
                f"R12 {prefix}: no anchor_files block present"
            )
        else:
            for label, basename in sorted(anchor_files.items()):
                if not isinstance(basename, str) or not basename:
                    record_skip(
                        f"R12 {prefix}: {label} basename missing"
                    )
                    continue
                found_path: Optional[Path] = None
                for root in search_paths:
                    cand = root / basename
                    if cand.exists():
                        found_path = cand
                        break
                if found_path is None:
                    record_skip(
                        f"R12 {prefix}: {label} ({basename}) not "
                        f"found in search paths"
                    )
                    continue
                local = _file_sha256(found_path)
                if label == "proof_bundle":
                    if local == full_sha:
                        record_pass(
                            f"R12 {prefix}: proof_bundle local SHA "
                            f"matches recorded value "
                            f"({local[:16]}...)"
                        )
                    else:
                        record_fail(
                            f"R12 {prefix}: proof_bundle local SHA "
                            f"{local!r} != recorded "
                            f"proof_bundle_sha256 {full_sha!r} "
                            f"(file {found_path})"
                        )
                else:
                    record_info(
                        f"R12 {prefix}: {label} present, local "
                        f"SHA={local[:16]}... (file {found_path})"
                    )

            # R13: optional offline bundle verification.
            bundle_basename = anchor_files.get("proof_bundle")
            if isinstance(bundle_basename, str) and bundle_basename:
                bundle_path: Optional[Path] = None
                for root in search_paths:
                    cand = root / bundle_basename
                    if cand.exists():
                        bundle_path = cand
                        break
                if bundle_path is None:
                    record_skip(
                        f"R13 {prefix}: proof bundle not present, "
                        f"skipping offline verify_trinity_bundle"
                    )
                else:
                    ok = _try_offline_bundle_verification(
                        bundle_path, search_paths=search_paths,
                    )
                    if ok is None:
                        record_skip(
                            f"R13 {prefix}: verify_trinity_bundle "
                            f"helper not importable"
                        )
                    elif ok:
                        record_pass(
                            f"R13 {prefix}: offline "
                            f"verify_trinity_bundle reports OK"
                        )
                    else:
                        record_fail(
                            f"R13 {prefix}: offline "
                            f"verify_trinity_bundle reports FAIL "
                            f"for {bundle_basename}"
                        )

    # R11: no host paths in canonical JSON of the registry. We do this
    # last so the report shows it after per-entry checks.
    blob = raw.decode("utf-8", errors="replace")
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        record_fail(
            f"R11 host path markers leaked into registry JSON: {leaked}"
        )
    else:
        record_pass("R11 registry JSON contains no absolute host path")

    return (not failures, lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="verify_trinity_registry",
        description=(
            "Verify a Trinity Proof Registry JSON. Exits 0 on success."
        ),
    )
    p.add_argument(
        "registry", type=str,
        help="Path to TRINITY_PROOF_REGISTRY.json",
    )
    p.add_argument(
        "--search-path", action="append", type=str, default=None,
        help=(
            "Extra directory to search for anchor files. Repeatable. "
            "Defaults to the registry's directory plus the current "
            "working directory."
        ),
    )
    args = p.parse_args(argv)

    registry_path = Path(args.registry).resolve()
    extras = [
        Path(s).resolve() for s in (args.search_path or [])
        if s and Path(s).exists()
    ]
    search_paths = extras + [registry_path.parent, Path.cwd()]

    ok, lines = verify_registry(registry_path, search_paths=search_paths)

    for line in lines:
        print(line)
    print()
    if ok:
        print(
            f"[verify] OK — registry {registry_path.name} is valid."
        )
        return 0
    fail_count = sum(1 for line in lines if line.startswith("[FAIL]"))
    print(
        f"[verify] FAILED — {fail_count} check(s) failed on "
        f"{registry_path.name}."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
