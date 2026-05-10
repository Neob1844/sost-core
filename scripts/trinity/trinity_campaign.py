#!/usr/bin/env python3
"""Trinity Autonomous Campaign Engine — CLI entrypoint.

Reads a Trinity dossier JSON and its companion Useful Compute Plan
JSON. Produces a Campaign Manifest that ties both together into a
single reproducible proof bundle with a SHA-256 the operator can
later register on chain.

DRY-RUN ONLY. The script never:
  - activates Useful Compute rewards,
  - publishes tasks to any public API,
  - broadcasts a SOST capsule,
  - touches the wallet / miner / node / RPC,
  - moves funds,
  - enqueues anything to a real worker.

Inputs are required to be on-disk JSON files because the manifest
embeds their SHA-256 (computed from raw file bytes, identical to
`sha256sum`). That gives the proof bundle a cryptographic chain:
scorecard SHA → dossier SHA → plan SHA → campaign SHA.

Usage
-----
    python3 scripts/trinity/trinity_campaign.py \\
            --dossier TRINITY_DEMO_DOSSIER_kalgoorlie.json \\
            --useful-compute-plan TRINITY_USEFUL_COMPUTE_PLAN_kalgoorlie.json \\
            --campaign-name kalgoorlie_phase1 \\
            --pinned-time 2026-05-10T00:00:00+00:00

Env vars
--------
    TRINITY_MATERIALS_ENGINE_PATH  same convention as the other Trinity
                                    scripts; tells the engine where the
                                    `src.trinity.campaign_engine` module
                                    lives when the host has no WSL layout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[2]
_REPO_PARENT = _REPO_ROOT.parent.parent


def _resolve_materials_engine_root() -> Optional[Path]:
    env = os.environ.get("TRINITY_MATERIALS_ENGINE_PATH", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p
    candidate = _REPO_PARENT / "materials-engine-private"
    if candidate.exists():
        return candidate
    home = Path(os.path.expanduser("~"))
    home_candidate = home / "SOST" / "materials-engine-private"
    if home_candidate.exists():
        return home_candidate
    return None


def _ensure_engine_importable() -> None:
    root = _resolve_materials_engine_root()
    if root is None:
        return
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)


_ensure_engine_importable()

from src.trinity.campaign_engine import (   # noqa: E402
    CampaignManifest,
    ProofBundle,
    build_campaign_from_dossier,
    canonical_bytes,
    generate_proof_bundle,
    sha256_hex,
)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _md_escape(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown(manifest: Dict[str, Any], proof: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Trinity Campaign — `{manifest['campaign_name']}`")
    lines.append("")
    lines.append(
        "> **DRY-RUN ONLY.** This campaign is a design + provenance "
        "artefact. No Useful Compute rewards are active. No tasks "
        "have been published. No SOST capsule has been broadcast. "
        "The proof bundle below is marked `ready_to_register=true` "
        "and `registered=false`; broadcasting is a manual operator "
        "step that lives outside this engine."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{manifest['schema']}`")
    if manifest.get("generated_at_utc"):
        lines.append(f"- **Generated (UTC)**: {manifest['generated_at_utc']}")
    lines.append(f"- **AOI**: `{manifest['aoi']}`")
    lines.append("")

    lines.append("## Proof bundle")
    lines.append("")
    lines.append("| Anchor | SHA-256 |")
    lines.append("| --- | --- |")
    lines.append(
        f"| scorecard | `{proof.get('scorecard_sha256') or '<missing>'}` |"
    )
    lines.append(f"| dossier   | `{proof['dossier_sha256']}` |")
    lines.append(
        f"| useful compute plan | `{proof['useful_compute_plan_sha256']}` |"
    )
    lines.append(f"| **campaign**          | `{proof['campaign_sha256']}` |")
    lines.append("")
    lines.append(
        f"- **ready_to_register**: `{proof['ready_to_register']}`"
    )
    lines.append(f"- **registered**: `{proof['registered']}`")
    lines.append(f"- **dry_run**: `{proof['dry_run']}`")
    lines.append("")

    lines.append("## Objectives")
    lines.append("")
    for o in manifest.get("objectives") or []:
        lines.append(f"- **{_md_escape(o.get('title'))}** "
                     f"(`{o.get('objective_id')}`)")
        if o.get("description"):
            lines.append(f"    - {_md_escape(o['description'])}")
    lines.append("")

    lines.append("## Evidence gaps")
    lines.append("")
    if manifest.get("evidence_gaps"):
        lines.append("| Severity | Gap ID | Source | Description |")
        lines.append("| --- | --- | --- | --- |")
        for g in manifest["evidence_gaps"]:
            lines.append(
                f"| {_md_escape(g.get('severity'))} | "
                f"`{g.get('gap_id')}` | "
                f"{_md_escape(g.get('source'))} | "
                f"{_md_escape(g.get('description'))} |"
            )
    else:
        lines.append("_(no evidence gaps detected — unexpected for v0)_")
    lines.append("")

    lines.append("## Next actions (ranked)")
    lines.append("")
    if manifest.get("next_actions"):
        for i, a in enumerate(manifest["next_actions"], start=1):
            lines.append(
                f"### {i}. {_md_escape(a.get('title'))}"
            )
            lines.append("")
            lines.append(f"- **Action id**: `{a.get('action_id')}`")
            lines.append(f"- **Bucket**: `{a.get('bucket')}`")
            lines.append(f"- **Impact**: `{a.get('impact')}` · "
                         f"**Safety**: `{a.get('safety')}`")
            if a.get("forbidden_reason"):
                lines.append(
                    f"- **Forbidden reason**: "
                    f"{_md_escape(a['forbidden_reason'])}"
                )
            if a.get("estimated_cost"):
                lines.append(
                    f"- **Estimated cost**: "
                    f"{_md_escape(a['estimated_cost'])}"
                )
            if a.get("addresses_gaps"):
                lines.append(
                    f"- **Addresses gaps**: "
                    + ", ".join(f"`{g}`" for g in a["addresses_gaps"])
                )
            if a.get("prerequisites"):
                lines.append(
                    f"- **Prerequisites**: "
                    + ", ".join(f"`{p}`" for p in a["prerequisites"])
                )
            lines.append("")
            lines.append(f"> {_md_escape(a.get('description'))}")
            lines.append("")
    lines.append("")

    lines.append("## Useful Compute candidate queue (mirrored, dry-run)")
    lines.append("")
    queue = manifest.get("useful_compute_candidate_queue") or []
    if queue:
        lines.append("| Family | Project | Runtime (s) | Memory (MB) | N workers |")
        lines.append("| --- | --- | --- | --- | --- |")
        for q in queue:
            lines.append(
                f"| `{q.get('family_id')}` | `{q.get('project')}` | "
                f"{q.get('estimated_runtime_seconds')} | "
                f"{q.get('estimated_memory_mb')} | "
                f"{q.get('requires_n_workers')} |"
            )
    else:
        lines.append(
            "_(no candidate_reward_worthy families in the source plan)_"
        )
    lines.append("")
    lines.append(
        "_All entries above are dry-run; no task is enqueued, no "
        "reward is active, the public Useful Compute API is "
        "untouched._"
    )
    lines.append("")

    lines.append("## Safety status")
    lines.append("")
    for k, v in sorted((manifest.get("safety_status") or {}).items()):
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")

    lines.append("## What this document is NOT")
    lines.append("")
    lines.append("- This is **not** an announcement of active Useful "
                 "Compute rewards.")
    lines.append("- This is **not** a published task list on the "
                 "public Useful Compute API.")
    lines.append("- This is **not** a broadcasted SOST capsule. The "
                 "campaign SHA-256 is ready to register; broadcasting "
                 "it is a manual operator step.")
    lines.append("- This is **not** a geological conclusion. Every "
                 "evidence gap and every next action sits behind "
                 "human review.")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_json_with_hash(path: Path) -> tuple[Dict[str, Any], str]:
    raw = path.read_bytes()
    return (json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest())


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="trinity_campaign",
        description=(
            "Build a Trinity Campaign Manifest from a dossier + "
            "Useful Compute Plan. DRY-RUN only; never broadcasts."
        ),
    )
    p.add_argument("--dossier", required=True, type=str,
                   help="Path to TRINITY_DEMO_DOSSIER_<aoi>.json.")
    p.add_argument("--useful-compute-plan", required=True, type=str,
                   help="Path to TRINITY_USEFUL_COMPUTE_PLAN_<aoi>.json.")
    p.add_argument("--campaign-name", required=True, type=str,
                   help="Short identifier for this campaign.")
    p.add_argument("--pinned-time", type=str, default=None,
                   help="ISO-8601 UTC timestamp for deterministic SHA.")
    p.add_argument("--out-md", type=str, default=None)
    p.add_argument("--out-json", type=str, default=None)
    args = p.parse_args(argv)

    dossier_path = Path(args.dossier).resolve()
    plan_path = Path(args.useful_compute_plan).resolve()
    if not dossier_path.exists():
        print(f"error: dossier not found at {dossier_path}", file=sys.stderr)
        return 1
    if not plan_path.exists():
        print(f"error: plan not found at {plan_path}", file=sys.stderr)
        return 1

    try:
        dossier, dossier_sha = _read_json_with_hash(dossier_path)
        plan, plan_sha = _read_json_with_hash(plan_path)
    except (json.JSONDecodeError, OSError) as e:
        print(f"error: failed to read inputs: {e}", file=sys.stderr)
        return 1

    generated_at = args.pinned_time or \
        datetime.now(timezone.utc).isoformat(timespec="seconds")

    manifest: CampaignManifest = build_campaign_from_dossier(
        dossier, plan,
        campaign_name=args.campaign_name,
        dossier_sha256=dossier_sha,
        useful_compute_plan_sha256=plan_sha,
        generated_at_utc=generated_at,
    )
    manifest_dict = manifest.to_dict()
    canonical = canonical_bytes(manifest_dict)
    campaign_sha = sha256_hex(canonical)

    proof: ProofBundle = generate_proof_bundle(
        manifest, campaign_sha256=campaign_sha,
    )

    md_text = _render_markdown(manifest_dict, proof.to_dict())

    aoi = manifest.aoi
    name = args.campaign_name
    md_path = Path(args.out_md) if args.out_md else \
        dossier_path.parent / f"TRINITY_CAMPAIGN_{name}.md"
    js_path = Path(args.out_json) if args.out_json else \
        dossier_path.parent / f"TRINITY_CAMPAIGN_{name}.json"

    md_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    js_path.write_bytes(canonical)

    print(f"[trinity-cmp] dossier:        {dossier_path}")
    print(f"[trinity-cmp] plan:           {plan_path}")
    print(f"[trinity-cmp] wrote MD:       {md_path}")
    print(f"[trinity-cmp] wrote JSON:     {js_path}")
    print(f"[trinity-cmp] scorecard_sha:  "
          f"{proof.scorecard_sha256 or '<missing>'}")
    print(f"[trinity-cmp] dossier_sha:    {proof.dossier_sha256}")
    print(f"[trinity-cmp] plan_sha:       {proof.useful_compute_plan_sha256}")
    print(f"[trinity-cmp] campaign_sha:   {proof.campaign_sha256}")
    print(f"[trinity-cmp] aoi:            {aoi}")
    print(f"[trinity-cmp] evidence_gaps:  {len(manifest.evidence_gaps)}")
    print(f"[trinity-cmp] next_actions:   {len(manifest.next_actions)}")
    print(f"[trinity-cmp] uc_queue:       "
          f"{len(manifest.useful_compute_candidate_queue)}")
    print(f"[trinity-cmp] ready_to_register: {proof.ready_to_register}")
    print(f"[trinity-cmp] registered:        {proof.registered}")
    print(f"[trinity-cmp] dry_run:           True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
