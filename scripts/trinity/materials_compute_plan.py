#!/usr/bin/env python3
"""Trinity / Materials Track — Useful Compute plan builder (dry-run).

Reads a ``TRINITY_MATERIALS_DOSSIER_<campaign>.json`` and proposes heavy
compute tasks per candidate, classified as
``candidate_reward_worthy`` / ``deferred`` / ``not_reward_worthy``.
Emits ``TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_<campaign>.json`` and a
Markdown sidecar.

Invariants
----------
- DRY-RUN. No rewards active. No public publication. No consensus
  modification. No network, no wallet, no subprocess.
- Hard-signal substring veto: any proposed family whose label or
  rationale contains a forbidden token (e.g. ``symbolic``,
  ``fake_heavy``, ``trivial busy``, ``non-deterministic``) is downgraded
  to ``not_reward_worthy`` regardless of soft signals.
- The plan never enqueues to the public Useful Compute API. The
  ``safety_status`` block re-states this in every output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCHEMA = "trinity-materials-uc-plan/v0"
_DOSSIER_SCHEMA = "trinity-materials-dossier/v0"
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")

_FORBIDDEN_SUBSTRINGS = (
    "symbolic", "fake_heavy", "trivial busy", "non-deterministic",
    "below 60.0s", "below 256.0", "verification protocol stub",
)

_CLASS_REWARD_WORTHY = "candidate_reward_worthy"
_CLASS_DEFERRED = "deferred"
_CLASS_NOT = "not_reward_worthy"

# Family catalog. Each family is intentionally aligned with what
# Materials Engine + Useful Compute would actually require for a
# materials-track candidate. Hard signals (deterministic, heavy enough,
# safe to verify) are explicit; soft signals are recorded for the
# reviewer.
_FAMILY_CATALOG: List[Dict[str, Any]] = [
    {
        "family_id": "mlip_relaxation",
        "human_label": "MLIP geometry relaxation",
        "purpose": (
            "Relax a candidate cell with a machine-learned interatomic "
            "potential to obtain a low-energy reference geometry without "
            "running full DFT yet."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 30,
    },
    {
        "family_id": "dft_input_preparation",
        "human_label": "DFT input preparation",
        "purpose": (
            "Generate canonical DFT input files (k-points, basis, "
            "smearing, pseudopotentials) from a relaxed cell, ready for "
            "a follow-up run on a real cluster."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": False,
        "safe_to_verify": True,
        "typical_minutes": 5,
    },
    {
        "family_id": "dft_phonon_screening",
        "human_label": "DFT phonon ground-state screening",
        "purpose": (
            "Confirm the relaxed cell has no imaginary phonon modes at "
            "the operating temperature window; flag potential dynamic "
            "instabilities."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 180,
    },
    {
        "family_id": "mlip_force_field_validation",
        "human_label": "MLIP vs DFT cross-check on benchmark set",
        "purpose": (
            "Cross-validate a chosen MLIP against a fixed DFT reference "
            "set so subsequent MLIP-driven runs report a meaningful "
            "error envelope."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": False,
        "safe_to_verify": True,
        "typical_minutes": 25,
    },
    {
        "family_id": "quantum_chemistry_toy_benchmark",
        "human_label": "Quantum-chemistry toy benchmark",
        "purpose": (
            "Run a small, well-known quantum-chemistry benchmark to "
            "anchor the campaign's compute pipeline against a published "
            "reference number."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 90,
    },
]


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit plan: host-path markers leaked into "
            f"canonical JSON: {leaked}"
        )


def _hard_signal_veto(family: Dict[str, Any], rationale: str) -> Optional[str]:
    """Return the matching forbidden substring if any soft text trips
    the hard-signal veto, else None."""
    haystack = " ".join([
        family.get("human_label", ""),
        family.get("purpose", ""),
        rationale,
    ]).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in haystack:
            return needle
    return None


def _classify(family: Dict[str, Any], rationale: str) -> Dict[str, Any]:
    veto = _hard_signal_veto(family, rationale)
    if veto:
        return {
            "classification": _CLASS_NOT,
            "rationale": (
                f"hard-signal veto matched substring {veto!r}; downgraded "
                f"to {_CLASS_NOT}"
            ),
        }
    required_hard = (
        family.get("useful"),
        family.get("deterministic"),
        family.get("auditable"),
        family.get("safe_to_verify"),
    )
    if not all(required_hard):
        return {
            "classification": _CLASS_NOT,
            "rationale": (
                "one of the four hard signals (useful, deterministic, "
                "auditable, safe_to_verify) is False"
            ),
        }
    if family.get("heavy_enough"):
        return {
            "classification": _CLASS_REWARD_WORTHY,
            "rationale": rationale,
        }
    # Hard signals OK but not heavy enough → deferred.
    return {
        "classification": _CLASS_DEFERRED,
        "rationale": (
            f"{rationale} (deferred: family marked heavy_enough=False; "
            "not large enough to be reward-worthy in v0)"
        ),
    }


def _propose_for_hold(c_id: str, formula: str) -> List[Dict[str, Any]]:
    """A hold candidate's open questions usually map to a geometry +
    DFT-input pair: relax with MLIP, then prepare DFT inputs for a
    follow-up real run."""
    return [
        {
            "family_id": "mlip_relaxation",
            "rationale": (
                f"{c_id} ({formula}) is on hold pending a low-energy "
                f"reference geometry; an MLIP relaxation is the cheapest "
                f"and most informative first step"
            ),
        },
        {
            "family_id": "dft_input_preparation",
            "rationale": (
                f"{c_id} ({formula}) needs canonical DFT input files for "
                f"the follow-up real-DFT run that would resolve the hold"
            ),
        },
    ]


def _propose_for_reject(c_id: str, formula: str) -> List[Dict[str, Any]]:
    """A reject candidate is treated as calibration / reference; the only
    work proposed is benchmark-validation, kept deferred."""
    return [
        {
            "family_id": "mlip_force_field_validation",
            "rationale": (
                f"{c_id} ({formula}) was rejected as a discovery target "
                f"but is still useful as a benchmark anchor for the "
                f"MLIP cross-check; classified deferred, not reward-worthy"
            ),
        },
    ]


def _propose_for_accept(c_id: str, formula: str) -> List[Dict[str, Any]]:
    """Accept candidates earn a phonon screening + a QC benchmark to
    harden the accept before any further investment."""
    return [
        {
            "family_id": "dft_phonon_screening",
            "rationale": (
                f"{c_id} ({formula}) was accepted; phonon screening at "
                f"the operating temperature confirms dynamic stability "
                f"before any further investment"
            ),
        },
        {
            "family_id": "quantum_chemistry_toy_benchmark",
            "rationale": (
                f"{c_id} ({formula}) anchored to a published QC "
                f"benchmark so the campaign's compute pipeline carries "
                f"a verifiable reference number"
            ),
        },
    ]


def build_plan(
    *,
    campaign: str,
    generated_at_utc: str,
    dossier_path: Path,
    live_mode: bool = False,
) -> Dict[str, Any]:
    if not isinstance(campaign, str) or not campaign.strip():
        raise ValueError("campaign must be a non-empty string")
    if not isinstance(generated_at_utc, str) or not generated_at_utc.endswith(
        "+00:00"
    ):
        raise ValueError(
            "generated_at_utc must be an ISO-8601 string ending in +00:00"
        )
    if not dossier_path.exists():
        raise FileNotFoundError(
            f"materials dossier not found at {dossier_path}"
        )

    if live_mode:
        print(
            "[materials_compute_plan] --live-materials-engine: live "
            "classifier import not yet implemented in v0; using mock "
            "classifier.",
            file=sys.stderr,
        )

    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    if dossier.get("schema") != _DOSSIER_SCHEMA:
        raise ValueError(
            f"dossier at {dossier_path.name} does not declare schema "
            f"{_DOSSIER_SCHEMA!r}"
        )
    if dossier.get("track") != _TRACK:
        raise ValueError(
            f"dossier at {dossier_path.name} is not a {_TRACK!r} dossier"
        )

    dossier_sha = hashlib.sha256(dossier_path.read_bytes()).hexdigest()

    family_lookup = {f["family_id"]: f for f in _FAMILY_CATALOG}
    candidate_proposals: List[Dict[str, Any]] = []
    class_counts: Dict[str, int] = {
        _CLASS_REWARD_WORTHY: 0,
        _CLASS_DEFERRED: 0,
        _CLASS_NOT: 0,
    }
    total_tasks = 0

    for h in dossier.get("hypotheses", []):
        decision = h.get("decision")
        if decision == "hold":
            seed_props = _propose_for_hold(h["candidate_id"], h["formula"])
        elif decision == "reject":
            seed_props = _propose_for_reject(h["candidate_id"], h["formula"])
        elif decision == "accept":
            seed_props = _propose_for_accept(h["candidate_id"], h["formula"])
        else:
            continue
        materialised: List[Dict[str, Any]] = []
        for sp in seed_props:
            family = family_lookup.get(sp["family_id"])
            if family is None:
                continue
            cls = _classify(family, sp["rationale"])
            class_counts[cls["classification"]] = (
                class_counts.get(cls["classification"], 0) + 1
            )
            total_tasks += 1
            materialised.append({
                "family_id": sp["family_id"],
                "human_label": family["human_label"],
                "classification": cls["classification"],
                "rationale": cls["rationale"],
                "typical_minutes": family["typical_minutes"],
            })
        candidate_proposals.append({
            "candidate_id": h["candidate_id"],
            "formula": h["formula"],
            "decision_from_dossier": decision,
            "proposed_families": materialised,
        })

    plan = {
        "schema": _SCHEMA,
        "campaign": campaign,
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "source": {
            "dossier_basename": dossier_path.name,
            "dossier_sha256": dossier_sha,
        },
        "safety_status": {
            "dry_run": True,
            "no_rewards_active": True,
            "no_chain_broadcast": True,
            "no_auto_publish": True,
            "no_consensus_modification": True,
        },
        "family_catalog": _FAMILY_CATALOG,
        "candidate_proposals": candidate_proposals,
        "summary": {
            "candidates_total": len(candidate_proposals),
            "tasks_total": total_tasks,
            "by_classification": class_counts,
        },
    }

    blob = canonical_dumps(plan)
    _check_no_host_paths(blob)
    return plan


def render_markdown(plan: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Track — Useful Compute Plan "
        f"`{plan['campaign']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN plan.** Proposes heavy compute tasks per candidate "
        "for the next campaign iteration. Useful Compute rewards are "
        "**not** active; no task in this document is enqueued, paid or "
        "published."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{plan['schema']}`")
    lines.append(f"- **Track**: `{plan['track']}`")
    lines.append(f"- **Generated (UTC)**: {plan['generated_at_utc']}")
    src = plan["source"]
    lines.append("- **Source**:")
    for k in sorted(src):
        lines.append(f"  - `{k}`: `{src[k]}`")
    lines.append("")
    lines.append("## Safety status")
    lines.append("")
    for k in sorted(plan["safety_status"]):
        lines.append(f"- `{k}`: `{plan['safety_status'][k]}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    s = plan["summary"]
    lines.append(f"- **candidates_total**: `{s['candidates_total']}`")
    lines.append(f"- **tasks_total**: `{s['tasks_total']}`")
    lines.append("- **by_classification**:")
    for k in sorted(s["by_classification"]):
        lines.append(f"  - `{k}`: `{s['by_classification'][k]}`")
    lines.append("")
    lines.append("## Per-candidate proposals")
    lines.append("")
    for cp in plan["candidate_proposals"]:
        lines.append(
            f"### `{cp['candidate_id']}` &mdash; {cp['formula']} "
            f"(dossier: {cp['decision_from_dossier'].upper()})"
        )
        lines.append("")
        for pf in cp["proposed_families"]:
            lines.append(
                f"- `{pf['family_id']}` &mdash; **{pf['classification']}** "
                f"(~{pf['typical_minutes']} min)"
            )
            lines.append(f"  - {pf['rationale']}")
        if not cp["proposed_families"]:
            lines.append("- (no families proposed)")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_compute_plan",
        description=(
            "Build the Trinity / Materials Track Useful Compute plan. "
            "Dry-run; rewards not active."
        ),
    )
    p.add_argument(
        "--campaign", type=str, default="novel_frontier_phase1",
    )
    p.add_argument(
        "--dossier", type=str, default=None,
        help=(
            "Path to TRINITY_MATERIALS_DOSSIER_<campaign>.json"
        ),
    )
    p.add_argument(
        "--generated-at-utc", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument(
        "--out-json", type=str, default=None,
    )
    p.add_argument(
        "--out-md", type=str, default=None,
    )
    p.add_argument(
        "--live-materials-engine", action="store_true",
        help="v0 stub: live classifier import not yet implemented.",
    )
    args = p.parse_args(argv)

    dossier_path = Path(
        args.dossier
        or f"TRINITY_MATERIALS_DOSSIER_{args.campaign}.json"
    )
    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_{args.campaign}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_{args.campaign}.md"
    )

    plan = build_plan(
        campaign=args.campaign,
        generated_at_utc=args.generated_at_utc,
        dossier_path=dossier_path,
        live_mode=args.live_materials_engine,
    )

    out_json.write_text(canonical_dumps(plan), encoding="utf-8")
    out_md.write_text(render_markdown(plan), encoding="utf-8")

    s = plan["summary"]
    print(f"[materials_compute_plan] wrote {out_json}")
    print(f"[materials_compute_plan] wrote {out_md}")
    print(
        f"[materials_compute_plan] tasks: total={s['tasks_total']}, "
        f"by_class={s['by_classification']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
