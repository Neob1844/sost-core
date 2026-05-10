#!/usr/bin/env python3
"""Trinity Proof Registry v0 builder.

Builds a canonical, deterministic registry JSON + Markdown sidecar
documenting public on-chain anchors for Trinity proof bundles.

Core invariants
---------------
- DRY-RUN. The builder never opens a network connection, never calls
  SOST RPC, never touches a wallet, never invokes ``sost-cli``. It does
  not broadcast, send, sign, register, or activate anything. It only
  composes a JSON and a Markdown describing operator-driven work that
  happened manually.
- Canonical JSON. ``sort_keys=True``, ``separators=(",", ":")``,
  ``ensure_ascii=True``, no trailing newline. Any reproducible-time
  argument produces a byte-identical output.
- No host-path leak. The output JSON contains no ``/home/``, ``/opt/``,
  ``/Users/``, ``C:/`` or ``C:\\`` substring.
- Validation only — never relaxes a constraint.

Validation performed before writing
-----------------------------------
- ``txid`` is 64-char lowercase hex.
- ``proof_bundle_sha256`` is 64-char lowercase hex.
- ``proof_bundle_sha16`` equals the first 16 chars of
  ``proof_bundle_sha256``.
- ``capsule_text`` contains ``proof_bundle_sha16`` as a substring.
- ``merkle_root`` is 64-char lowercase hex.
- ``status`` is in {"registered", "ready_to_register", "draft"}.
- ``capsule_mode`` is in {"open-note", "doc-ref"}.
- ``block_height`` is a positive ``int``.
- All required ``safety_status`` flags are ``True``.
- If the proof bundle file is found locally, its SHA-256 must match
  ``proof_bundle_sha256``.
- If ``scripts/trinity/verify_trinity_bundle.py`` is importable and
  the bundle is found locally, the bundle is also re-verified offline.

Usage
-----
    python3 scripts/trinity/trinity_proof_registry.py \\
        --out-json TRINITY_PROOF_REGISTRY.json \\
        --out-md   TRINITY_PROOF_REGISTRY.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


_SCHEMA = "trinity-proof-registry/v0"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")
_ALLOWED_STATUS = ("registered", "ready_to_register", "draft")
_ALLOWED_CAPSULE_MODES = ("open-note", "doc-ref")
# track ∈ {earth, materials}. Optional on legacy entries (defaults to
# "earth" for backward compat with the original Kalgoorlie record);
# new entries set the field explicitly.
_ALLOWED_TRACKS = ("earth", "materials")
_DEFAULT_TRACK = "earth"
_REQUIRED_SAFETY_FIELDS = (
    "not_a_mineral_reserve_claim",
    "not_a_geological_conclusion",
    "no_active_useful_compute_rewards",
    "no_auto_broadcast",
    "no_consensus_change",
)


class RegistryError(ValueError):
    """Raised when an entry or registry fails validation."""


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_hex64(name: str, value: Any) -> None:
    if not isinstance(value, str) or not _HEX64_RE.match(value):
        raise RegistryError(
            f"{name} must be a 64-char lowercase hex SHA-256 "
            f"(got {value!r})"
        )


def validate_entry(
    entry: Mapping[str, Any],
    *,
    repo_root: Optional[Path] = None,
    require_bundle_match: bool = True,
) -> None:
    """Validate one registry entry. Raises ``RegistryError`` on failure."""
    txid = entry.get("txid")
    _check_hex64("entry.txid", txid)

    full_sha = entry.get("proof_bundle_sha256")
    _check_hex64("entry.proof_bundle_sha256", full_sha)

    sha16 = entry.get("proof_bundle_sha16")
    if (
        not isinstance(sha16, str)
        or len(sha16) != 16
        or sha16 != full_sha[:16]
    ):
        raise RegistryError(
            f"entry.proof_bundle_sha16 must equal first 16 chars of "
            f"proof_bundle_sha256 (got sha16={sha16!r}, "
            f"full_sha={full_sha!r})"
        )

    capsule_text = entry.get("capsule_text")
    if not isinstance(capsule_text, str) or sha16 not in capsule_text:
        raise RegistryError(
            f"entry.capsule_text must contain proof_bundle_sha16 "
            f"{sha16!r} (got {capsule_text!r})"
        )

    _check_hex64("entry.merkle_root", entry.get("merkle_root"))

    track = entry.get("track", _DEFAULT_TRACK)
    if track not in _ALLOWED_TRACKS:
        raise RegistryError(
            f"entry.track must be one of {_ALLOWED_TRACKS} "
            f"(got {track!r})"
        )

    status = entry.get("status")
    if status not in _ALLOWED_STATUS:
        raise RegistryError(
            f"entry.status must be one of {_ALLOWED_STATUS} "
            f"(got {status!r})"
        )

    capsule_mode = entry.get("capsule_mode")
    if capsule_mode not in _ALLOWED_CAPSULE_MODES:
        raise RegistryError(
            f"entry.capsule_mode must be one of {_ALLOWED_CAPSULE_MODES} "
            f"(got {capsule_mode!r})"
        )

    block_height = entry.get("block_height")
    if (
        not isinstance(block_height, int)
        or isinstance(block_height, bool)
        or block_height <= 0
    ):
        raise RegistryError(
            f"entry.block_height must be a positive int "
            f"(got {block_height!r})"
        )

    safety = entry.get("safety_status") or {}
    for k in _REQUIRED_SAFETY_FIELDS:
        if safety.get(k) is not True:
            raise RegistryError(
                f"entry.safety_status.{k} must be True "
                f"(got {safety.get(k)!r})"
            )

    anchor_files = entry.get("anchor_files") or {}
    bundle_basename = anchor_files.get("proof_bundle")
    if (
        require_bundle_match
        and isinstance(bundle_basename, str)
        and bundle_basename
    ):
        roots: List[Path] = []
        if repo_root is not None:
            roots.append(repo_root)
        roots.append(Path.cwd())
        for root in roots:
            candidate = root / bundle_basename
            if candidate.exists():
                local = file_sha256(candidate)
                if local != full_sha:
                    raise RegistryError(
                        f"local file {bundle_basename} SHA-256 "
                        f"{local!r} does not match recorded "
                        f"proof_bundle_sha256 {full_sha!r}"
                    )
                break


def build_registry(
    *,
    generated_at_utc: str,
    network: str,
    entries: List[Mapping[str, Any]],
    repo_root: Optional[Path] = None,
    require_bundle_match: bool = True,
) -> Dict[str, Any]:
    """Build and validate a registry dict from validated entries."""
    if (
        not isinstance(generated_at_utc, str)
        or not generated_at_utc.endswith("+00:00")
    ):
        raise RegistryError(
            "generated_at_utc must be an ISO-8601 string ending in +00:00"
        )
    if not isinstance(network, str) or not network.strip():
        raise RegistryError("network must be a non-empty string")
    if not isinstance(entries, list) or not entries:
        raise RegistryError("entries must be a non-empty list")

    seen_ids = set()
    materialised: List[Dict[str, Any]] = []
    for e in entries:
        if not isinstance(e, dict):
            raise RegistryError("each entry must be a dict")
        eid = e.get("id")
        if not isinstance(eid, str) or not eid:
            raise RegistryError("entry.id must be a non-empty string")
        if eid in seen_ids:
            raise RegistryError(f"duplicate entry id: {eid!r}")
        seen_ids.add(eid)
        validate_entry(
            e,
            repo_root=repo_root,
            require_bundle_match=require_bundle_match,
        )
        materialised.append(dict(e))

    registry = {
        "schema": _SCHEMA,
        "registry_generated_at_utc": generated_at_utc,
        "network": network,
        "entries": materialised,
    }

    blob = canonical_dumps(registry)
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise RegistryError(
            f"refusing to emit registry: host-path markers leaked into "
            f"canonical JSON: {leaked}"
        )

    return registry


def render_markdown(registry: Mapping[str, Any]) -> str:
    """Render a Markdown sidecar from a validated registry."""
    lines: List[str] = []
    lines.append("# Trinity Proof Registry — v0")
    lines.append("")
    lines.append(
        "> **Public registry document.** This file records on-chain Trinity"
        " proof-bundle anchors. It does not broadcast, sign or register"
        " anything. Each entry is the cryptographic record of an"
        " operator-driven manual capsule registration that already happened"
        " on the SOST chain."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{registry.get('schema')}`")
    lines.append(
        f"- **Generated (UTC)**: {registry.get('registry_generated_at_utc')}"
    )
    lines.append(f"- **Network**: {registry.get('network')}")
    lines.append("")

    for e in registry.get("entries", []):
        lines.append(f"## {e.get('title') or e.get('id')}")
        lines.append("")
        lines.append(f"- **id**: `{e.get('id')}`")
        lines.append(f"- **Track**: `{e.get('track', _DEFAULT_TRACK)}`")
        lines.append(f"- **AOI**: `{e.get('aoi')}`")
        lines.append(f"- **Status**: `{e.get('status')}`")
        lines.append(
            f"- **Registration method**: `{e.get('registration_method')}`"
        )
        lines.append(f"- **Operator**: {e.get('operator')}")
        lines.append(f"- **Block height**: `{e.get('block_height')}`")
        lines.append(f"- **TXID**: `{e.get('txid')}`")
        lines.append(f"- **Capsule mode**: `{e.get('capsule_mode')}`")
        lines.append(f"- **Capsule text**: `{e.get('capsule_text')}`")
        lines.append(
            f"- **proof_bundle_sha256**: `{e.get('proof_bundle_sha256')}`"
        )
        lines.append(
            f"- **proof_bundle_sha16**: `{e.get('proof_bundle_sha16')}`"
        )
        lines.append(f"- **Merkle root**: `{e.get('merkle_root')}`")
        anchor_files = e.get("anchor_files") or {}
        if anchor_files:
            lines.append("- **Anchor files**:")
            for k in sorted(anchor_files):
                lines.append(f"  - `{k}`: `{anchor_files[k]}`")
        safety = e.get("safety_status") or {}
        if safety:
            lines.append("- **Safety status**:")
            for k in sorted(safety):
                lines.append(f"  - `{k}`: `{safety[k]}`")
        lines.append("")

    lines.append("## What this document is NOT")
    lines.append("")
    lines.append(
        "- **Not** a mineral reserve claim. Each entry records cryptographic"
        " priority over a Trinity scientific workflow output, not over a"
        " deposit."
    )
    lines.append(
        "- **Not** an announcement of active Useful Compute rewards. The"
        " Useful Compute layer is dry-run by design."
    )
    lines.append(
        "- **Not** an automated broadcaster. The registry only documents"
        " operator-driven manual registrations after the fact."
    )
    lines.append(
        "- **Not** a consensus, RPC, node or wallet change. Building or"
        " verifying the registry never touches any of those layers."
    )
    return "\n".join(lines) + "\n"


# Canonical Kalgoorlie Phase 1 entry. Single source of truth for the
# first Trinity bundle anchored on chain.
KALGOORLIE_PHASE1_ENTRY: Dict[str, Any] = {
    "id": "kalgoorlie_phase1",
    "track": "earth",
    "aoi": "kalgoorlie",
    "title": "Kalgoorlie Phase 1",
    "status": "registered",
    "registration_method": "manual-cli",
    "operator": "NeoB",
    "block_height": 8085,
    "txid": (
        "d68678b5d15ca8a60b70a7aa17647bfa12271d342eef066e1b4a832f4624f3db"
    ),
    "capsule_mode": "open-note",
    "capsule_text": "trinity-proof kalgoorlie_phase1 3a28a4b112fe95df",
    "proof_bundle_sha256": (
        "3a28a4b112fe95df85ab2ab91deb7698ebeb1d9182297f06635fd12fd4053a02"
    ),
    "proof_bundle_sha16": "3a28a4b112fe95df",
    "merkle_root": (
        "a818a1e4799ec34fd5a65b17d180a9534f791d4cd49f54c97b21c11d7b0e28b4"
    ),
    "anchor_files": {
        "campaign": "TRINITY_CAMPAIGN_kalgoorlie_phase1.json",
        "dossier": "TRINITY_DEMO_DOSSIER_kalgoorlie.json",
        "proof_bundle": "TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json",
        "useful_compute_plan": "TRINITY_USEFUL_COMPUTE_PLAN_kalgoorlie.json",
    },
    "safety_status": {
        "not_a_mineral_reserve_claim": True,
        "not_a_geological_conclusion": True,
        "no_active_useful_compute_rewards": True,
        "no_auto_broadcast": True,
        "no_consensus_change": True,
    },
}


def _try_offline_bundle_verification(
    bundle_path: Path,
    *,
    search_paths: List[Path],
) -> Optional[bool]:
    """Try to call ``verify_trinity_bundle.verify_bundle`` if importable.

    Returns ``True`` / ``False`` on a real verification result, or
    ``None`` if the helper module is not available.
    """
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


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="trinity_proof_registry",
        description=(
            "Build the Trinity Proof Registry JSON + Markdown for v0. "
            "Registry-only; never broadcasts, signs or registers."
        ),
    )
    p.add_argument(
        "--out-json", type=str, default="TRINITY_PROOF_REGISTRY.json",
        help="Output JSON path (default: TRINITY_PROOF_REGISTRY.json)",
    )
    p.add_argument(
        "--out-md", type=str, default="TRINITY_PROOF_REGISTRY.md",
        help="Output Markdown path (default: TRINITY_PROOF_REGISTRY.md)",
    )
    p.add_argument(
        "--generated-at-utc", type=str,
        default="2026-05-10T00:00:00+00:00",
        help="Pinned UTC timestamp for deterministic output",
    )
    p.add_argument(
        "--network", type=str, default="SOST mainnet",
    )
    p.add_argument(
        "--repo-root", type=str, default=str(Path.cwd()),
        help=(
            "Repo root used to locate anchor files for hash verification."
        ),
    )
    p.add_argument(
        "--no-bundle-match", action="store_true",
        help="Skip the local proof_bundle SHA-256 cross-check.",
    )
    p.add_argument(
        "--no-verify-bundle", action="store_true",
        help="Skip the offline verify_trinity_bundle.py reuse step.",
    )
    args = p.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    registry = build_registry(
        generated_at_utc=args.generated_at_utc,
        network=args.network,
        entries=[KALGOORLIE_PHASE1_ENTRY],
        repo_root=repo_root,
        require_bundle_match=not args.no_bundle_match,
    )

    if not args.no_verify_bundle:
        for entry in registry["entries"]:
            bundle_basename = (
                entry.get("anchor_files") or {}
            ).get("proof_bundle")
            if not bundle_basename:
                continue
            for root in (repo_root, Path.cwd()):
                candidate = root / bundle_basename
                if candidate.exists():
                    ok = _try_offline_bundle_verification(
                        candidate, search_paths=[root, Path.cwd()],
                    )
                    if ok is False:
                        raise RegistryError(
                            f"offline verify_trinity_bundle reported FAIL "
                            f"for {bundle_basename}"
                        )
                    break

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.write_text(canonical_dumps(registry), encoding="utf-8")
    out_md.write_text(render_markdown(registry), encoding="utf-8")

    print(f"[registry] wrote {out_json}")
    print(f"[registry] wrote {out_md}")
    print(
        f"[registry] entries: {len(registry['entries'])}; "
        f"network: {registry['network']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
