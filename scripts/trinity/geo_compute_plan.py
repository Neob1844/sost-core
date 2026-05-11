#!/usr/bin/env python3
"""Trinity / Geo Discovery — Useful Compute plan builder v0.1 (dry-run).

Reads a ``TRINITY_GEO_DOSSIER_<campaign>.json`` and proposes heavy
compute tasks per AOI, classified as ``candidate_reward_worthy`` /
``deferred`` / ``not_reward_worthy``. Emits
``TRINITY_GEO_USEFUL_COMPUTE_PLAN_<campaign>.json`` + Markdown sidecar.

The geo family catalog covers the data layers that the
``recommended_next_data_layers`` field of the scorecard talks about:
satellite tiles, spectral anomalies, DEM derivatives, geophysics
fusion, uncertainty estimation, cross-worker descriptor validation.

Invariants
----------
- DRY-RUN. No rewards active. No public publication. No subprocess.
- Hard-signal substring veto: any proposed family whose label or
  rationale contains a forbidden token is downgraded to
  ``not_reward_worthy``.
- The plan never enqueues to the public Useful Compute API. The
  ``safety_status`` block restates this in every output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCHEMA = "trinity-geo-uc-plan/v0.1"
_DOSSIER_SCHEMA = "trinity-geo-dossier/v0.1"
_TRACK = "geaspirit"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")

_FORBIDDEN_SUBSTRINGS = (
    "symbolic", "fake_heavy", "trivial busy", "non-deterministic",
    "below 60.0s", "below 256.0", "verification protocol stub",
)

_CLASS_REWARD_WORTHY = "candidate_reward_worthy"
_CLASS_DEFERRED = "deferred"
_CLASS_NOT = "not_reward_worthy"


_FAMILY_CATALOG: List[Dict[str, Any]] = [
    {
        "family_id": "satellite_tile_preprocessing",
        "human_label": "Sentinel / Landsat tile preprocessing",
        "purpose": (
            "Download (offline-cached for v0.1), atmospheric-correct and "
            "co-register Sentinel-2 / Landsat-8 tiles covering the AOI "
            "for downstream spectral and change-detection analysis."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 45,
    },
    {
        "family_id": "spectral_anomaly_scoring",
        "human_label": "Spectral anomaly scoring on AOI tiles",
        "purpose": (
            "Run pinned ASTER / Sentinel-2 spectral indices (clay, iron "
            "oxide, kaolinite, sericite) over the AOI tiles and rank "
            "pixels by anomaly intensity vs. regional background."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 60,
    },
    {
        "family_id": "dem_terrain_derivatives",
        "human_label": "DEM-derived terrain layers",
        "purpose": (
            "From SRTM 30m DEM compute slope, aspect, curvature, "
            "ruggedness index and structural lineaments. Light heavy: "
            "raster derivatives, no DEM inversion."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": False,
        "safe_to_verify": True,
        "typical_minutes": 10,
    },
    {
        "family_id": "geophysics_layer_fusion",
        "human_label": "Geophysics layer fusion (gravity, magnetics)",
        "purpose": (
            "Co-register global gravity (WGM2012) and magnetic (EMAG2) "
            "anomaly grids with the AOI bbox, derive a local "
            "depth-sensitive signature, and produce a fused signal map."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 90,
    },
    {
        "family_id": "uncertainty_estimation",
        "human_label": "Uncertainty estimation across data layers",
        "purpose": (
            "Aggregate the per-layer confidence into an AOI uncertainty "
            "map. Surfaces which AOIs are 'high score but high "
            "uncertainty' vs. 'high score and tight uncertainty'."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": False,
        "safe_to_verify": True,
        "typical_minutes": 15,
    },
    {
        "family_id": "cross_worker_descriptor_validation",
        "human_label": "Cross-worker descriptor validation",
        "purpose": (
            "Re-run the spectral / DEM descriptors on a second worker "
            "and compare; flag AOIs where descriptor outputs diverge "
            "more than the consensus threshold."
        ),
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 40,
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
                f"hard-signal veto matched substring {veto!r}; "
                f"downgraded to {_CLASS_NOT}"
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
                "one of the four hard signals is False"
            ),
        }
    if family.get("heavy_enough"):
        return {
            "classification": _CLASS_REWARD_WORTHY,
            "rationale": rationale,
        }
    return {
        "classification": _CLASS_DEFERRED,
        "rationale": (
            f"{rationale} (deferred: family marked heavy_enough=False)"
        ),
    }


def _propose_for_accept(aoi_id: str, region: str) -> List[Dict[str, Any]]:
    """Accept-decision AOIs earn the full preprocessing stack."""
    return [
        {
            "family_id": "satellite_tile_preprocessing",
            "rationale": (
                f"{aoi_id} ({region}) accepted by council; the first "
                f"useful work is to preprocess the AOI's Sentinel / "
                f"Landsat tiles so every downstream layer can run."
            ),
        },
        {
            "family_id": "spectral_anomaly_scoring",
            "rationale": (
                f"{aoi_id} ({region}) accepted; spectral anomaly "
                f"scoring is the cheapest first-pass evidence-strength "
                f"booster on top of preprocessed tiles."
            ),
        },
        {
            "family_id": "dem_terrain_derivatives",
            "rationale": (
                f"{aoi_id} ({region}): DEM-derived layers contextualise "
                f"the spectral anomalies against structural / "
                f"topographic features."
            ),
        },
        {
            "family_id": "geophysics_layer_fusion",
            "rationale": (
                f"{aoi_id} ({region}): geophysics fusion provides "
                f"depth-sensitive evidence beyond the surface-only "
                f"satellite signals."
            ),
        },
    ]


def _propose_for_hold(aoi_id: str, region: str) -> List[Dict[str, Any]]:
    """Hold-decision AOIs get cheaper layers first so the operator can
    decide whether to invest in heavy preprocessing later."""
    return [
        {
            "family_id": "dem_terrain_derivatives",
            "rationale": (
                f"{aoi_id} ({region}) on hold; DEM derivatives are the "
                f"cheapest layer that adds independent structural "
                f"context for the next council pass."
            ),
        },
        {
            "family_id": "uncertainty_estimation",
            "rationale": (
                f"{aoi_id} ({region}) on hold; surfacing per-layer "
                f"uncertainty helps the operator decide whether to "
                f"invest in heavier preprocessing."
            ),
        },
    ]


def _propose_for_reject(aoi_id: str, region: str) -> List[Dict[str, Any]]:
    """Reject-decision AOIs get a cross-worker validation task — they
    stay archived as benchmark anchors only."""
    return [
        {
            "family_id": "cross_worker_descriptor_validation",
            "rationale": (
                f"{aoi_id} ({region}) rejected by council; keep as a "
                f"calibration anchor in the descriptor cross-check pool "
                f"(deferred work, not reward-worthy on its own)."
            ),
        },
    ]


def build_plan(
    *,
    campaign: str,
    generated_at_utc: str,
    dossier_path: Path,
) -> Dict[str, Any]:
    if not isinstance(campaign, str) or not campaign.strip():
        raise ValueError("campaign must be a non-empty string")
    if not isinstance(generated_at_utc, str) or not generated_at_utc.endswith(
        "+00:00"
    ):
        raise ValueError(
            "generated_at_utc must be ISO-8601 ending in +00:00"
        )
    if not dossier_path.exists():
        raise FileNotFoundError(
            f"geo dossier not found at {dossier_path}"
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

    aoi_proposals: List[Dict[str, Any]] = []
    class_counts: Dict[str, int] = {
        _CLASS_REWARD_WORTHY: 0,
        _CLASS_DEFERRED: 0,
        _CLASS_NOT: 0,
    }
    total_tasks = 0

    for a in dossier.get("aois", []):
        decision = a.get("decision")
        aid = a.get("aoi_id") or "?"
        region = a.get("region") or "unknown"
        if decision == "accept":
            seed = _propose_for_accept(aid, region)
        elif decision == "hold":
            seed = _propose_for_hold(aid, region)
        elif decision == "reject":
            seed = _propose_for_reject(aid, region)
        else:
            continue
        materialised: List[Dict[str, Any]] = []
        for sp in seed:
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
        aoi_proposals.append({
            "aoi_id": aid,
            "region": region,
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
        "aoi_proposals": aoi_proposals,
        "summary": {
            "aois_total": len(aoi_proposals),
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
        f"# Trinity / Geo Discovery — Useful Compute Plan "
        f"`{plan['campaign']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN plan.** Proposes heavy compute / data tasks per "
        "AOI for the next campaign iteration. Useful Compute rewards "
        "are **not** active; no task in this document is enqueued, "
        "paid or published. Remote proxy evidence only; not a mineral "
        "reserve claim."
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
    lines.append(f"- **aois_total**: `{s['aois_total']}`")
    lines.append(f"- **tasks_total**: `{s['tasks_total']}`")
    lines.append("- **by_classification**:")
    for k in sorted(s["by_classification"]):
        lines.append(f"  - `{k}`: `{s['by_classification'][k]}`")
    lines.append("")
    lines.append("## Per-AOI proposals (first 30)")
    lines.append("")
    for ap in plan["aoi_proposals"][:30]:
        lines.append(
            f"### `{ap['aoi_id']}` &mdash; region `{ap['region']}` "
            f"&mdash; dossier {ap['decision_from_dossier'].upper()}"
        )
        lines.append("")
        for pf in ap["proposed_families"]:
            lines.append(
                f"- `{pf['family_id']}` &mdash; "
                f"**{pf['classification']}** "
                f"(~{pf['typical_minutes']} min)"
            )
            lines.append(f"  - {pf['rationale']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="geo_compute_plan",
        description=(
            "Build the Trinity / Geo Discovery Useful Compute plan. "
            "Dry-run; rewards not active."
        ),
    )
    p.add_argument(
        "--campaign", type=str, default="global_phase1",
    )
    p.add_argument(
        "--dossier", type=str, default=None,
    )
    p.add_argument(
        "--generated-at-utc", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    args = p.parse_args(argv)

    dossier_path = Path(
        args.dossier
        or f"TRINITY_GEO_DOSSIER_{args.campaign}.json"
    )
    out_json = Path(
        args.out_json
        or f"TRINITY_GEO_USEFUL_COMPUTE_PLAN_{args.campaign}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_GEO_USEFUL_COMPUTE_PLAN_{args.campaign}.md"
    )

    plan = build_plan(
        campaign=args.campaign,
        generated_at_utc=args.generated_at_utc,
        dossier_path=dossier_path,
    )
    out_json.write_text(canonical_dumps(plan), encoding="utf-8")
    out_md.write_text(render_markdown(plan), encoding="utf-8")

    s = plan["summary"]
    print(f"[geo-plan] wrote {out_json}")
    print(f"[geo-plan] wrote {out_md}")
    print(
        f"[geo-plan] tasks: total={s['tasks_total']}, "
        f"by_class={s['by_classification']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
