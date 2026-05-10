#!/usr/bin/env python3
"""Trinity Useful Compute Plan — entrypoint.

Reads a Trinity dossier JSON (the output of `aoi_to_dossier.py`) and
produces a structured Useful Compute Plan that classifies each
candidate Heavy Task family as `candidate_reward_worthy`,
`not_reward_worthy`, or `deferred`. Also simulates a worker queue.

DRY-RUN ONLY. This script never:
  - activates Useful Compute rewards,
  - publishes tasks to the public Useful Compute API,
  - enqueues anything on a real worker,
  - touches the worker, the task server, the consensus rules, the
    miner, the SOST RPC schema, or any wallet,
  - emits network calls.

Usage
-----
    python3 scripts/trinity/useful_compute_plan.py <dossier.json>
    python3 scripts/trinity/useful_compute_plan.py <dossier.json> \\
            --workers 16 --out-md plan.md --out-json plan.json

Env vars
--------
    TRINITY_MATERIALS_ENGINE_PATH    where materials-engine-private lives,
                                      so the planner import resolves on a
                                      VPS without depending on the WSL
                                      layout (same convention as
                                      aoi_to_dossier.py).
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
_REPO_ROOT = _THIS_FILE.parents[2]            # sost-core/
_REPO_PARENT = _REPO_ROOT.parent.parent


def _resolve_materials_engine_root() -> Optional[Path]:
    """Same resolution logic as aoi_to_dossier.py but copied here so
    this script is independent and works even if the operator only
    deployed `scripts/trinity/useful_compute_plan.py` to the VPS."""
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


def _ensure_planner_importable() -> None:
    root = _resolve_materials_engine_root()
    if root is None:
        return
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)


_ensure_planner_importable()

from src.trinity.useful_compute_planner import (   # noqa: E402
    UsefulComputePlan,
    plan_from_dossier,
)


# ---------------------------------------------------------------------------
# Canonical serialisation — same convention as aoi_to_dossier.py
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _md_escape(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown(plan_dict: Dict[str, Any],
                     plan_sha256: str,
                     source_dossier_path: Optional[Path] = None,
                     generated_at_utc: Optional[str] = None) -> str:
    aoi = plan_dict["source_dossier_aoi"]
    queue = plan_dict["queue"]
    candidates = plan_dict["candidates"]
    reports = plan_dict["reward_reports"]
    safety = plan_dict["safety_notice"]

    lines: List[str] = []
    lines.append(f"# Trinity Useful Compute Plan — AOI `{aoi}`")
    lines.append("")
    lines.append("> **DRY-RUN ONLY.** This document is a design artefact "
                 "describing what Heavy Tasks *would* look like if the "
                 "operator later activated Useful Compute rewards. No "
                 "rewards are active. No tasks have been published. The "
                 "public Useful Compute API is unaffected.")
    lines.append("")
    lines.append(f"- **Schema**: `trinity-useful-compute-plan/v0`")
    if generated_at_utc:
        lines.append(f"- **Generated (UTC)**: {generated_at_utc}")
    if source_dossier_path:
        lines.append(f"- **Source dossier**: `{source_dossier_path}`")
    lines.append(f"- **Reviews considered**: {plan_dict['n_reviews_considered']}")
    lines.append(f"- **Candidate tasks emitted**: {len(candidates)}")
    lines.append(f"- **Workers simulated**: {queue['n_workers']}")
    lines.append("")

    lines.append("## Reward-worthiness summary")
    lines.append("")
    counts: Dict[str, int] = {}
    for r in reports:
        counts[r["reward_status"]] = counts.get(r["reward_status"], 0) + 1
    if counts:
        lines.append("| Status | Count |")
        lines.append("| --- | --- |")
        for k in ("candidate_reward_worthy", "deferred", "not_reward_worthy"):
            lines.append(f"| `{k}` | {counts.get(k, 0)} |")
    else:
        lines.append("_(no candidates emitted; nothing to classify)_")
    lines.append("")

    lines.append("## Candidate Heavy Task families")
    lines.append("")
    by_id = {r["family_id"]: r for r in reports}
    for i, c in enumerate(candidates, start=1):
        rep = by_id.get(c["family_id"], {})
        status = rep.get("reward_status", "unknown")
        lines.append(f"### {i}. {_md_escape(c['family_name'])}")
        lines.append("")
        lines.append(f"- **Family id**: `{c['family_id']}`")
        lines.append(f"- **Project**: `{c['project']}`")
        lines.append(f"- **Reward status (v0 classification)**: "
                     f"`{status}`")
        if c.get("source_hypothesis_hash"):
            lines.append(f"- **Derived from review**: "
                         f"`{c['source_hypothesis_subject']}` "
                         f"(hypothesis hash `{c['source_hypothesis_hash']}`)")
        lines.append(f"- **Estimated runtime per task**: "
                     f"{c['estimated_runtime_seconds']:.0f} s "
                     f"({c['estimated_memory_mb']:.0f} MB)")
        lines.append(f"- **Requires N workers for verification**: "
                     f"{c['requires_n_workers']}")
        lines.append(f"- **Declared deterministic**: "
                     f"`{c['deterministic']}`")
        lines.append(f"- **Declared auditable**: "
                     f"`{c['auditable']}`")
        if c.get("dependencies"):
            lines.append(f"- **Dependencies**: "
                         + ", ".join(f"`{d}`" for d in c['dependencies']))
        if c.get("notes"):
            lines.append(f"- **Notes**: {_md_escape(c['notes'])}")
        lines.append("")
        lines.append(f"**Description for classifier:**")
        lines.append("")
        lines.append(f"> {_md_escape(c['description'])}")
        lines.append("")
        # Reasoning block.
        if rep:
            lines.append(f"**Why this reward status:**")
            lines.append("")
            lines.append(f"> {_md_escape(rep.get('why'))}")
            lines.append("")
            cls = rep.get("classification") or {}
            lines.append(
                f"Classifier axes: useful=`{cls.get('is_useful')}` "
                f"determ=`{cls.get('is_deterministic')}` "
                f"auditable=`{cls.get('is_auditable')}` "
                f"heavy=`{cls.get('is_heavy_enough')}` "
                f"verifiable=`{cls.get('is_safe_to_verify')}` "
                f"overall=`{cls.get('overall_accept')}`"
            )
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Simulated worker queue")
    lines.append("")
    lines.append(f"- **Workers**: {queue['n_workers']}")
    lines.append(f"- **Tasks**: {queue['n_tasks']}")
    lines.append(f"- **Total serial work**: {queue['total_serial_seconds']:.1f} s")
    lines.append(f"- **Estimated wallclock**: "
                 f"{queue['estimated_wallclock_seconds']:.1f} s "
                 f"(longest-processing-time-first heuristic)")
    if queue.get("per_worker_seconds"):
        lines.append("- **Per-worker seconds**:")
        for w, s in enumerate(queue['per_worker_seconds']):
            lines.append(f"    - worker {w}: {s:.1f} s")
    lines.append("")

    lines.append("## Safety notice")
    lines.append("")
    for chunk in safety.split("DRY-RUN ONLY."):
        chunk = chunk.strip()
        if chunk:
            lines.append(f"DRY-RUN ONLY. {_md_escape(chunk)}")
    lines.append("")

    lines.append("## Integrity")
    lines.append("")
    lines.append(f"- **Canonical JSON SHA-256**: `{plan_sha256}`")
    lines.append("- This SHA-256 is computed over the sorted, no-spaces, "
                 "ASCII JSON serialisation of the plan object.")
    lines.append("- The operator can register the SHA-256 on the SOST "
                 "chain as a `DOC_REF_OPEN` or `OPEN_NOTE_INLINE` "
                 "capsule, identically to a Trinity dossier hash.")
    lines.append("")
    lines.append("## What this document is NOT")
    lines.append("")
    lines.append("- This is **not** a list of currently rewarded tasks.")
    lines.append("- This is **not** an announcement of an open Useful "
                 "Compute paid queue.")
    lines.append("- This is **not** a guarantee that any of the "
                 "`candidate_reward_worthy` families will ever become "
                 "active. Activation requires a separate consensus + "
                 "governance procedure that has not shipped.")
    lines.append("- This is **not** input to the existing public Useful "
                 "Compute worker; the worker is unchanged.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_plan",
        description=(
            "Generate a Trinity Useful Compute Plan from a Trinity "
            "dossier JSON. DRY-RUN only; never activates rewards."
        ),
    )
    p.add_argument("dossier", help="Path to a Trinity dossier JSON.")
    p.add_argument("--workers", type=int, default=8,
                   help="Number of simulated workers (default 8).")
    p.add_argument("--out-md", type=str, default=None,
                   help="Output Markdown path.")
    p.add_argument("--out-json", type=str, default=None,
                   help="Output JSON path.")
    p.add_argument("--pinned-time", type=str, default=None,
                   help="Pin the document's generated_at_utc for "
                        "deterministic SHA-256 (used by tests).")
    args = p.parse_args(argv)

    dossier_path = Path(args.dossier).resolve()
    if not dossier_path.exists():
        print(f"error: dossier not found at {dossier_path}",
              file=sys.stderr)
        return 1

    try:
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: dossier is not valid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(dossier, dict):
        print("error: dossier JSON must be an object", file=sys.stderr)
        return 1

    plan: UsefulComputePlan = plan_from_dossier(dossier, workers=args.workers)
    plan_dict = plan.to_dict()

    canonical = _canonical_json(plan_dict)
    plan_sha256 = _sha256_hex(canonical)

    generated_at_utc = args.pinned_time or \
        datetime.now(timezone.utc).isoformat(timespec="seconds")
    md_text = _render_markdown(plan_dict, plan_sha256,
                                source_dossier_path=dossier_path,
                                generated_at_utc=generated_at_utc)

    # Default output paths sit next to the dossier with a parallel name.
    aoi = plan.source_dossier_aoi
    if args.out_md:
        md_path = Path(args.out_md)
    else:
        md_path = dossier_path.parent / f"TRINITY_USEFUL_COMPUTE_PLAN_{aoi}.md"
    if args.out_json:
        js_path = Path(args.out_json)
    else:
        js_path = dossier_path.parent / f"TRINITY_USEFUL_COMPUTE_PLAN_{aoi}.json"

    md_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    js_path.write_bytes(canonical)

    print(f"[trinity-ucp] dossier:     {dossier_path}")
    print(f"[trinity-ucp] wrote MD:    {md_path}")
    print(f"[trinity-ucp] wrote JSON:  {js_path}")
    print(f"[trinity-ucp] sha256:      {plan_sha256}")
    print(f"[trinity-ucp] candidates:  {len(plan_dict['candidates'])}")
    counts: Dict[str, int] = {}
    for r in plan_dict["reward_reports"]:
        counts[r["reward_status"]] = counts.get(r["reward_status"], 0) + 1
    for k in ("candidate_reward_worthy", "deferred", "not_reward_worthy"):
        if counts.get(k, 0) > 0:
            print(f"[trinity-ucp]   {k}: {counts[k]}")
    print(f"[trinity-ucp] dry_run:     True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
