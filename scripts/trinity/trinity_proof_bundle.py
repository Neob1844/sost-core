#!/usr/bin/env python3
"""Trinity Proof Bundle v0 — single root artefact.

Aggregates the four reproducible SHAs that anchor a Trinity campaign:

    scorecard_sha256             (sha256sum of the source scorecard JSON)
    dossier_sha256               (sha256sum of TRINITY_DEMO_DOSSIER_<aoi>.json)
    useful_compute_plan_sha256   (sha256sum of TRINITY_USEFUL_COMPUTE_PLAN_<aoi>.json)
    campaign_sha256              (sha256 of canonical(TRINITY_CAMPAIGN_<name>.json))

The bundle also publishes a Merkle root over those four hashes (fixed
order; documented algorithm), a `proof_bundle_sha256` over the canonical
JSON of the bundle itself, and a capsule-registration preview the
operator can run manually to inscribe the bundle on chain.

DRY-RUN ONLY. This script never:
  - touches the wallet,
  - calls the SOST RPC,
  - broadcasts a transaction,
  - executes `sost-cli`,
  - opens any network connection.

The capsule preview is a *template*. The operator is expected to read
it, decide whether to register, and run the command themselves.

Usage
-----
    python3 scripts/trinity/trinity_proof_bundle.py \\
        --scorecard-sha <hex> \\
        --dossier        <path/to/dossier.json> \\
        --useful-compute-plan <path/to/plan.json> \\
        --campaign       <path/to/campaign.json> \\
        --aoi            kalgoorlie \\
        --bundle-name    kalgoorlie_phase1 \\
        --pinned-time    2026-05-10T00:00:00+00:00

If `--scorecard-sha` is omitted, the value is lifted from the dossier's
`source.scorecard_sha256` field (always present after the dossier
reproducibility hotfix).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_SCHEMA = "trinity-proof-bundle/v0"
_MERKLE_ALGO = (
    "sha256-binary-fixed-order: "
    "L0=bytes.fromhex(scorecard_sha256), "
    "L1=bytes.fromhex(dossier_sha256), "
    "L2=bytes.fromhex(useful_compute_plan_sha256), "
    "L3=bytes.fromhex(campaign_sha256). "
    "node01=sha256(L0||L1), node23=sha256(L2||L3), "
    "merkle_root=sha256(node01||node23)."
)
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


# ---------------------------------------------------------------------------
# Canonical / SHA helpers — same convention as the rest of Trinity.
# ---------------------------------------------------------------------------

def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 of the file's raw bytes (matches `sha256sum`)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Merkle root — fixed-order binary tree over the four base hashes.
# ---------------------------------------------------------------------------

def merkle_root_from_hashes(
    scorecard_sha256: str,
    dossier_sha256: str,
    useful_compute_plan_sha256: str,
    campaign_sha256: str,
) -> str:
    """Compute the Merkle root over the four base hashes in the exact
    documented order.

    Algorithm (from `_MERKLE_ALGO` string):

        leaf0 = bytes.fromhex(scorecard_sha256)
        leaf1 = bytes.fromhex(dossier_sha256)
        leaf2 = bytes.fromhex(useful_compute_plan_sha256)
        leaf3 = bytes.fromhex(campaign_sha256)

        node01 = sha256(leaf0 || leaf1)
        node23 = sha256(leaf2 || leaf3)

        merkle_root = sha256(node01 || node23)

    The function rejects any input that is not exactly 64 hex chars.
    Order is fixed; the tree is unbalanced-safe by construction (always
    four leaves).
    """
    for name, value in (
        ("scorecard_sha256", scorecard_sha256),
        ("dossier_sha256", dossier_sha256),
        ("useful_compute_plan_sha256", useful_compute_plan_sha256),
        ("campaign_sha256", campaign_sha256),
    ):
        if not isinstance(value, str) or not _HEX64_RE.match(value):
            raise ValueError(
                f"{name!r} is not a 64-char hex SHA-256: {value!r}"
            )

    leaves = [
        bytes.fromhex(scorecard_sha256),
        bytes.fromhex(dossier_sha256),
        bytes.fromhex(useful_compute_plan_sha256),
        bytes.fromhex(campaign_sha256),
    ]
    node01 = hashlib.sha256(leaves[0] + leaves[1]).digest()
    node23 = hashlib.sha256(leaves[2] + leaves[3]).digest()
    root = hashlib.sha256(node01 + node23).digest()
    return root.hex()


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------

def _extract_scorecard_sha_from_dossier(
    dossier_dict: Dict[str, Any],
) -> Optional[str]:
    src = dossier_dict.get("source") or {}
    val = src.get("scorecard_sha256")
    if isinstance(val, str) and _HEX64_RE.match(val):
        return val
    return None


def build_proof_bundle(
    *,
    scorecard_sha256: str,
    dossier_sha256: str,
    useful_compute_plan_sha256: str,
    campaign_sha256: str,
    aoi: str,
    bundle_name: str,
    dossier_basename: str,
    useful_compute_plan_basename: str,
    campaign_basename: str,
    generated_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the proof bundle dict — content-only, path-independent,
    deterministic when `generated_at_utc` is pinned.
    """
    for name, value in (
        ("scorecard_sha256", scorecard_sha256),
        ("dossier_sha256", dossier_sha256),
        ("useful_compute_plan_sha256", useful_compute_plan_sha256),
        ("campaign_sha256", campaign_sha256),
    ):
        if not isinstance(value, str) or not _HEX64_RE.match(value):
            raise ValueError(
                f"{name!r} is not a 64-char hex SHA-256"
            )
    if not isinstance(aoi, str) or not aoi:
        raise ValueError("aoi must be a non-empty string")
    if not isinstance(bundle_name, str) or not bundle_name:
        raise ValueError("bundle_name must be a non-empty string")

    merkle_root = merkle_root_from_hashes(
        scorecard_sha256, dossier_sha256,
        useful_compute_plan_sha256, campaign_sha256,
    )

    bundle: Dict[str, Any] = {
        "schema": _SCHEMA,
        "bundle_name": bundle_name,
        "aoi": aoi,
        "generated_at_utc": generated_at_utc,
        "anchors": {
            "scorecard_sha256": scorecard_sha256,
            "dossier_sha256": dossier_sha256,
            "useful_compute_plan_sha256": useful_compute_plan_sha256,
            "campaign_sha256": campaign_sha256,
        },
        "anchor_basenames": {
            # Basename-only references so a verifier can find the local
            # files without depending on host paths. Never absolute.
            "dossier": dossier_basename,
            "useful_compute_plan": useful_compute_plan_basename,
            "campaign": campaign_basename,
            "scorecard": "<external; sha256 only>",
        },
        "merkle": {
            "algorithm": _MERKLE_ALGO,
            "leaf_order": [
                "scorecard_sha256",
                "dossier_sha256",
                "useful_compute_plan_sha256",
                "campaign_sha256",
            ],
            "root": merkle_root,
        },
        "safety_status": {
            "dry_run": True,
            "registered": False,
            "ready_to_register": True,
            "no_rewards_active": True,
            "no_public_publication": True,
            "no_chain_broadcast": True,
            "no_consensus_modification": True,
            "no_wallet_action": True,
        },
        "capsule_preview": _capsule_preview(
            bundle_name, aoi, merkle_root,
            scorecard_sha256, dossier_sha256,
            useful_compute_plan_sha256, campaign_sha256,
        ),
        "verification": {
            "verifier_script": "scripts/trinity/verify_trinity_bundle.py",
            "instructions": (
                "Run `python3 scripts/trinity/verify_trinity_bundle.py "
                "<bundle.json>` from the sost-core repo root. The "
                "verifier re-hashes any local artefact whose basename "
                "matches a recorded anchor and reports a non-zero exit "
                "code on any mismatch."
            ),
        },
    }
    return bundle


def _capsule_preview(
    bundle_name: str,
    aoi: str,
    merkle_root: str,
    scorecard_sha: str,
    dossier_sha: str,
    plan_sha: str,
    campaign_sha: str,
) -> Dict[str, Any]:
    """Build the capsule registration template. NEVER executes anything.

    Two registration shapes the operator can use:
      - OPEN_NOTE_INLINE: short 80-byte ASCII label embedded in the
        capsule body. Carries the bundle name plus the first 16 hex
        of the proof_bundle_sha256 (populated lazily by the caller).
      - DOC_REF_OPEN: pointer to a published URL of the bundle JSON,
        with the bundle's SHA-256 inside the capsule's hash field.

    The strings here are TEMPLATES. The caller fills in the
    proof_bundle_sha256 once the canonical bundle is hashed.
    """
    return {
        "open_note_template": (
            f"trinity-proof {bundle_name} sha:<first16hex>"
        ),
        "open_note_max_bytes": 80,
        "doc_ref_open_metadata": {
            "intended_locator": (
                f"https://<your-public-mirror>/proof_bundles/"
                f"{bundle_name}.json"
            ),
            "embedded_hash_field": "<proof_bundle_sha256>",
            "human_label": (
                f"Trinity proof bundle {bundle_name} for AOI {aoi}"
            ),
        },
        "merkle_root": merkle_root,
        "manual_sost_cli_template": (
            "# OPERATOR-DRIVEN. Do NOT automate. Read the bundle "
            "and the campaign manifest before running.\n"
            "./sost-cli --wallet <your-wallet>.json send "
            "<your-address> 0.01 "
            "--capsule-mode open-note "
            "--capsule-text 'trinity-proof "
            f"{bundle_name} <first16hex>'"
        ),
        "execution_status": (
            "NOT_EXECUTED — this script never broadcasts or signs. "
            "The fields above are reference values the operator can "
            "use to compose the capsule manually."
        ),
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _md_escape(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def render_markdown(bundle: Dict[str, Any],
                     proof_bundle_sha256: str) -> str:
    lines: List[str] = []
    lines.append(f"# Trinity Proof Bundle — `{bundle['bundle_name']}`")
    lines.append("")
    lines.append(
        "> **DRY-RUN ONLY.** This document is a cryptographic "
        "binding of the dossier, plan and campaign manifest "
        "produced for one AOI. The bundle is `ready_to_register=true` "
        "and `registered=false`. No transaction has been broadcast, "
        "no rewards are active, no wallet was touched."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{bundle['schema']}`")
    if bundle.get("generated_at_utc"):
        lines.append(
            f"- **Generated (UTC)**: {bundle['generated_at_utc']}"
        )
    lines.append(f"- **AOI**: `{bundle['aoi']}`")
    lines.append(
        f"- **proof_bundle_sha256**: `{proof_bundle_sha256}`"
    )
    lines.append("")

    lines.append("## Anchor hashes")
    lines.append("")
    lines.append("| Anchor | SHA-256 | Basename |")
    lines.append("| --- | --- | --- |")
    anchors = bundle["anchors"]
    basenames = bundle["anchor_basenames"]
    lines.append(
        f"| scorecard | `{anchors['scorecard_sha256']}` | "
        f"`{basenames['scorecard']}` |"
    )
    lines.append(
        f"| dossier | `{anchors['dossier_sha256']}` | "
        f"`{basenames['dossier']}` |"
    )
    lines.append(
        f"| useful_compute_plan | "
        f"`{anchors['useful_compute_plan_sha256']}` | "
        f"`{basenames['useful_compute_plan']}` |"
    )
    lines.append(
        f"| campaign | `{anchors['campaign_sha256']}` | "
        f"`{basenames['campaign']}` |"
    )
    lines.append("")

    lines.append("## Merkle root")
    lines.append("")
    lines.append(f"- **Root**: `{bundle['merkle']['root']}`")
    lines.append(
        f"- **Leaf order**: "
        + ", ".join(f"`{x}`" for x in bundle["merkle"]["leaf_order"])
    )
    lines.append(f"- **Algorithm**: `{bundle['merkle']['algorithm']}`")
    lines.append("")

    lines.append("## Safety status")
    lines.append("")
    for k, v in sorted(bundle["safety_status"].items()):
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")

    lines.append("## Capsule registration preview (manual)")
    lines.append("")
    cp = bundle["capsule_preview"]
    lines.append(
        f"- **OPEN_NOTE_INLINE template** "
        f"(max {cp['open_note_max_bytes']} bytes): "
        f"`{_md_escape(cp['open_note_template'])}`"
    )
    lines.append(
        f"- **DOC_REF_OPEN intended locator**: "
        f"`{cp['doc_ref_open_metadata']['intended_locator']}`"
    )
    lines.append(
        f"- **DOC_REF_OPEN embedded hash field**: "
        f"`{cp['doc_ref_open_metadata']['embedded_hash_field']}`"
    )
    lines.append(
        f"- **Execution status**: `{cp['execution_status']}`"
    )
    lines.append("")
    lines.append("**Manual `sost-cli` command (operator-driven, NOT executed):**")
    lines.append("")
    lines.append("```")
    lines.append(cp["manual_sost_cli_template"])
    lines.append("```")
    lines.append("")

    lines.append("## Verification")
    lines.append("")
    lines.append(
        f"- **Verifier**: `{bundle['verification']['verifier_script']}`"
    )
    lines.append(
        f"- **Instructions**: {_md_escape(bundle['verification']['instructions'])}"
    )
    lines.append("")

    lines.append("## What this document is NOT")
    lines.append("")
    lines.append(
        "- This is **not** a broadcasted SOST capsule. The "
        "`proof_bundle_sha256` is ready to inscribe; doing so is a "
        "manual operator step."
    )
    lines.append(
        "- This is **not** a guarantee of geological or material "
        "content. The campaign manifest carries the upstream "
        "evidence; this document is the cryptographic root only."
    )
    lines.append(
        "- This is **not** an announcement of active Useful "
        "Compute rewards."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="trinity_proof_bundle",
        description=(
            "Build a Trinity proof bundle: scorecard SHA + dossier "
            "SHA + Useful Compute Plan SHA + campaign SHA, plus a "
            "Merkle root and a capsule registration preview. "
            "DRY-RUN only; never broadcasts."
        ),
    )
    p.add_argument("--scorecard-sha", type=str, default=None,
                   help="64-char hex SHA-256 of the source scorecard. "
                        "Defaults to dossier.source.scorecard_sha256.")
    p.add_argument("--dossier", required=True, type=str)
    p.add_argument("--useful-compute-plan", required=True, type=str)
    p.add_argument("--campaign", required=True, type=str)
    p.add_argument("--aoi", required=True, type=str)
    p.add_argument("--bundle-name", required=True, type=str)
    p.add_argument("--pinned-time", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    p.add_argument("--out-json", type=str, default=None)
    args = p.parse_args(argv)

    dossier_path = Path(args.dossier).resolve()
    plan_path = Path(args.useful_compute_plan).resolve()
    campaign_path = Path(args.campaign).resolve()
    for label, pth in (
        ("dossier", dossier_path),
        ("useful_compute_plan", plan_path),
        ("campaign", campaign_path),
    ):
        if not pth.exists():
            print(f"error: {label} not found at {pth}", file=sys.stderr)
            return 1

    dossier_sha = file_sha256(dossier_path)
    plan_sha = file_sha256(plan_path)
    campaign_sha = file_sha256(campaign_path)

    if args.scorecard_sha:
        scorecard_sha = args.scorecard_sha.strip().lower()
    else:
        try:
            dossier_dict = json.loads(
                dossier_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as e:
            print(f"error: dossier is not valid JSON: {e}",
                  file=sys.stderr)
            return 1
        scorecard_sha = _extract_scorecard_sha_from_dossier(dossier_dict)
        if not scorecard_sha:
            print(
                "error: --scorecard-sha not supplied AND dossier has "
                "no source.scorecard_sha256 (pre-hotfix dossier?). "
                "Regenerate the dossier or pass --scorecard-sha.",
                file=sys.stderr,
            )
            return 1

    generated_at = args.pinned_time or \
        datetime.now(timezone.utc).isoformat(timespec="seconds")

    bundle = build_proof_bundle(
        scorecard_sha256=scorecard_sha,
        dossier_sha256=dossier_sha,
        useful_compute_plan_sha256=plan_sha,
        campaign_sha256=campaign_sha,
        aoi=args.aoi,
        bundle_name=args.bundle_name,
        dossier_basename=dossier_path.name,
        useful_compute_plan_basename=plan_path.name,
        campaign_basename=campaign_path.name,
        generated_at_utc=generated_at,
    )

    canonical = canonical_bytes(bundle)
    proof_bundle_sha = sha256_hex(canonical)

    md_text = render_markdown(bundle, proof_bundle_sha)

    name = args.bundle_name
    md_path = Path(args.out_md) if args.out_md else \
        dossier_path.parent / f"TRINITY_PROOF_BUNDLE_{name}.md"
    js_path = Path(args.out_json) if args.out_json else \
        dossier_path.parent / f"TRINITY_PROOF_BUNDLE_{name}.json"

    md_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    js_path.write_bytes(canonical)

    print(f"[trinity-pb] wrote MD:   {md_path}")
    print(f"[trinity-pb] wrote JSON: {js_path}")
    print(f"[trinity-pb] aoi:        {args.aoi}")
    print(f"[trinity-pb] bundle:     {args.bundle_name}")
    print(f"[trinity-pb] scorecard:  {scorecard_sha}")
    print(f"[trinity-pb] dossier:    {dossier_sha}")
    print(f"[trinity-pb] plan:       {plan_sha}")
    print(f"[trinity-pb] campaign:   {campaign_sha}")
    print(f"[trinity-pb] merkle:     {bundle['merkle']['root']}")
    print(f"[trinity-pb] PROOF_SHA:  {proof_bundle_sha}")
    print(f"[trinity-pb] registered: False")
    print(f"[trinity-pb] dry_run:    True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
