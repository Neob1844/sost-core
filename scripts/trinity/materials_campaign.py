#!/usr/bin/env python3
"""Trinity / Materials Track — Campaign Manifest builder.

Composes a Materials Track dossier and a Materials Track Useful Compute
plan into one canonical campaign manifest:
``TRINITY_MATERIALS_CAMPAIGN_<campaign>.json`` + Markdown sidecar.

The manifest carries:

- A **closed evidence-gap taxonomy** (10 entries) materials-specific,
  mirroring the role of the 11-gap Earth-track taxonomy.
- A **6-bucket NextAction taxonomy**:
  ``immediate_local`` / ``useful_compute_candidate`` /
  ``needs_external_data`` / ``needs_operator_review`` / ``blocked`` /
  ``unsafe_or_forbidden``.
- A **forbidden-substring veto** that routes any action whose title or
  description matches a closed list of disallowed phrases to the
  ``unsafe_or_forbidden`` bucket with the matching substring recorded
  as the reason.
- A **ranking key** ``(safety asc, -impact, prereq_count, bucket,
  action_id)`` that pushes unsafe actions to the end and elevates
  safe + high-impact + low-prereq actions to the top.
- Five anchor ``unsafe_or_forbidden`` entries that document what
  Trinity will never automate (rewards activation, publishing, on-chain
  registration without operator, fund moves, consensus modification).

Invariants
----------
- DRY-RUN. ``safety_status.dry_run = true``,
  ``ready_to_register = true``, ``registered = false``.
- No network, no RPC, no subprocess, no wallet, no public publication.
- Deterministic canonical JSON given the same pinned time and inputs.
- No host-path leak.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_SCHEMA = "trinity-materials-campaign/v0"
_DOSSIER_SCHEMA = "trinity-materials-dossier/v0"
# v0.2 bumped the dossier schema; both are accepted by this stage.
_DOSSIER_SCHEMAS_ACCEPTED = (
    "trinity-materials-dossier/v0",
    "trinity-materials-dossier/v0.2",
)
_PLAN_SCHEMA = "trinity-materials-uc-plan/v0"
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")

_BUCKET_IMMEDIATE = "immediate_local"
_BUCKET_UC = "useful_compute_candidate"
_BUCKET_EXTERNAL = "needs_external_data"
_BUCKET_REVIEW = "needs_operator_review"
_BUCKET_BLOCKED = "blocked"
_BUCKET_UNSAFE = "unsafe_or_forbidden"

_ALL_BUCKETS = (
    _BUCKET_IMMEDIATE,
    _BUCKET_UC,
    _BUCKET_EXTERNAL,
    _BUCKET_REVIEW,
    _BUCKET_BLOCKED,
    _BUCKET_UNSAFE,
)

_BUCKET_ORDER = {b: i for i, b in enumerate(_ALL_BUCKETS)}
_SAFETY_ORDER = {"safe": 0, "unsafe": 1}
_IMPACT_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}

# Closed taxonomy of materials-track evidence gaps. Substrings are
# matched (case-insensitive) against each candidate's open_questions
# string to assign gap_ids deterministically.
_GAP_TAXONOMY: List[Dict[str, str]] = [
    {
        "gap_id": "gap_no_dft_relaxation_baseline",
        "label": "No DFT relaxation baseline",
        "match_substrings": "dft relaxation,dft+u,formation energy",
    },
    {
        "gap_id": "gap_no_mlip_baseline",
        "label": "No MLIP baseline / cross-validation",
        "match_substrings": "mlip,fresh dft relaxation in the current mlip",
    },
    {
        "gap_id": "gap_no_phonon_screening",
        "label": "No phonon ground-state screening",
        "match_substrings": "phonon",
    },
    {
        "gap_id": "gap_no_synthesis_record",
        "label": "No synthesised polymorph / reference sample",
        "match_substrings": "synthesised,synthesized,polymorph",
    },
    {
        "gap_id": "gap_no_calorimetric_reference",
        "label": "No calorimetric / phase-stability reference",
        "match_substrings": "calorimetric,phase stability",
    },
    {
        "gap_id": "gap_unresolved_atomic_ordering",
        "label": "Unresolved site occupancy / atomic ordering",
        "match_substrings": "ordering,occupancy",
    },
    {
        "gap_id": "gap_no_band_edge_alignment",
        "label": "No GW / band-edge alignment",
        "match_substrings": "gw,band-edge,band edge",
    },
    {
        "gap_id": "gap_no_defect_inventory",
        "label": "No Kroger-Vink defect inventory",
        "match_substrings": "kroger-vink,defect inventory",
    },
    {
        "gap_id": "gap_mechanism_debated",
        "label": "Proposed property mechanism still debated",
        "match_substrings": "mechanism still debated,debated",
    },
    {
        "gap_id": "gap_no_spin_orbit_check",
        "label": "No spin-orbit coupling check",
        "match_substrings": "spin-orbit,spin orbit",
    },
]

_FORBIDDEN_SUBSTRINGS = (
    "activate rewards",
    "publish reward",
    "register on chain",
    "broadcast capsule",
    "move funds",
    "modify consensus",
    "change consensus",
    "auto-broadcast",
    "auto register",
)

_ANCHOR_UNSAFE_ACTIONS: List[Dict[str, Any]] = [
    {
        "action_id": "act_no_activate_rewards",
        "title": "Do not activate Useful Compute rewards",
        "description": (
            "Useful Compute rewards stay dry-run until a separate "
            "consensus / governance procedure ships. The engine never "
            "flips that switch."
        ),
        "matched_substring": "activate rewards",
    },
    {
        "action_id": "act_no_publish_reward_tasks",
        "title": "Do not publish reward-bearing tasks",
        "description": (
            "The public Useful Compute worker / API is unchanged. The "
            "engine never enqueues a paid task there."
        ),
        "matched_substring": "publish reward",
    },
    {
        "action_id": "act_no_register_on_chain_without_operator",
        "title": "Do not register on chain without operator decision",
        "description": (
            "Capsule registration is the operator's manual decision. "
            "The engine prepares a ready-to-register bundle and stops; "
            "broadcasting requires an explicit operator step."
        ),
        "matched_substring": "register on chain",
    },
    {
        "action_id": "act_no_move_funds",
        "title": "Do not move funds",
        "description": (
            "The engine touches no wallet, no key, no transaction "
            "broadcast path. Funds never leave the operator's address."
        ),
        "matched_substring": "move funds",
    },
    {
        "action_id": "act_no_modify_consensus",
        "title": "Do not modify consensus",
        "description": (
            "Consensus rules, miner code, node code and the RPC schema "
            "are strictly out of scope. No Trinity script can touch "
            "them."
        ),
        "matched_substring": "modify consensus",
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
            f"refusing to emit campaign: host-path markers leaked into "
            f"canonical JSON: {leaked}"
        )


def _assign_gaps_for_text(text: str) -> List[str]:
    haystack = text.lower()
    matched: List[str] = []
    for g in _GAP_TAXONOMY:
        for needle in g["match_substrings"].split(","):
            needle = needle.strip().lower()
            if needle and needle in haystack:
                if g["gap_id"] not in matched:
                    matched.append(g["gap_id"])
                break
    return matched


def _forbidden_match(title: str, description: str) -> Optional[str]:
    haystack = (title + " " + description).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in haystack:
            return needle
    return None


def _ranking_key(action: Dict[str, Any]) -> Tuple[int, int, int, int, str]:
    return (
        _SAFETY_ORDER.get(action.get("safety", "safe"), 0),
        _IMPACT_ORDER.get(action.get("impact", "none"), 3),
        len(action.get("prereqs", []) or []),
        _BUCKET_ORDER.get(action.get("bucket", _BUCKET_IMMEDIATE), 0),
        action.get("action_id", ""),
    )


def _propose_actions_for_hypothesis(
    h: Dict[str, Any],
    plan_proposals_by_candidate: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Generate candidate-level NextAction entries from one hypothesis."""
    actions: List[Dict[str, Any]] = []
    cid = h["candidate_id"]
    formula = h["formula"]
    decision = h["decision"]

    # Collect the gap_ids that apply to this candidate.
    gap_ids: List[str] = []
    for g in h.get("evidence_gaps", []) or []:
        for gid in _assign_gaps_for_text(g):
            if gid not in gap_ids:
                gap_ids.append(gid)

    # 1) UC actions sourced from the compute plan.
    uc_props = plan_proposals_by_candidate.get(cid, [])
    for pf in uc_props:
        if pf.get("classification") == "candidate_reward_worthy":
            actions.append({
                "action_id": f"{cid}_uc_{pf['family_id']}",
                "candidate_id": cid,
                "title": (
                    f"Useful-Compute candidate task: "
                    f"{pf['human_label']} for {formula}"
                ),
                "description": pf["rationale"],
                "bucket": _BUCKET_UC,
                "safety": "safe",
                "impact": "high" if decision == "hold" else "medium",
                "prereqs": [],
            })

    # 2) Operator-review actions for held candidates that flagged
    # mechanism-debated or atomic-ordering gaps.
    if decision == "hold":
        if "gap_mechanism_debated" in gap_ids:
            actions.append({
                "action_id": f"{cid}_review_mechanism",
                "candidate_id": cid,
                "title": (
                    f"Operator review: mechanism debate for {formula}"
                ),
                "description": (
                    "Literature mechanism for the property of interest "
                    "is debated; operator should pin a working "
                    "hypothesis before further compute is spent."
                ),
                "bucket": _BUCKET_REVIEW,
                "safety": "safe",
                "impact": "medium",
                "prereqs": ["gap_mechanism_debated"],
            })
        if "gap_unresolved_atomic_ordering" in gap_ids:
            actions.append({
                "action_id": f"{cid}_external_ordering",
                "candidate_id": cid,
                "title": (
                    f"Look up atomic ordering data for {formula}"
                ),
                "description": (
                    "Site occupancy / cation ordering should be sourced "
                    "from a public crystallographic database (ICSD, "
                    "Materials Project) before further DFT investment."
                ),
                "bucket": _BUCKET_EXTERNAL,
                "safety": "safe",
                "impact": "medium",
                "prereqs": ["gap_unresolved_atomic_ordering"],
            })

    # 3) For rejects, mark a low-impact calibration use.
    if decision == "reject":
        actions.append({
            "action_id": f"{cid}_calibration_use",
            "candidate_id": cid,
            "title": (
                f"Calibration-only use of {formula}"
            ),
            "description": (
                "Rejected as a discovery candidate; keep on file as a "
                "calibration / benchmark anchor for the MLIP cross-check."
            ),
            "bucket": _BUCKET_REVIEW,
            "safety": "safe",
            "impact": "low",
            "prereqs": [],
        })

    # 4) If the candidate has gaps with no clear next step, surface a
    # generic immediate_local "log gap" action.
    unaddressed_gaps = [
        gid for gid in gap_ids
        if gid not in (
            "gap_mechanism_debated", "gap_unresolved_atomic_ordering"
        )
    ]
    if unaddressed_gaps:
        actions.append({
            "action_id": f"{cid}_log_open_gaps",
            "candidate_id": cid,
            "title": f"Log open evidence gaps for {formula}",
            "description": (
                f"Record the open evidence gaps "
                f"{sorted(unaddressed_gaps)} in the campaign log so "
                f"future iterations can target them explicitly."
            ),
            "bucket": _BUCKET_IMMEDIATE,
            "safety": "safe",
            "impact": "low",
            "prereqs": list(sorted(unaddressed_gaps)),
        })

    return actions


def _apply_safety_veto(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Route any action whose title/description matches a forbidden
    substring into the ``unsafe_or_forbidden`` bucket. This catches
    accidental drift; the v0 generator above does not emit any such
    action by construction, so this veto should be a no-op on the
    canonical path."""
    out: List[Dict[str, Any]] = []
    for a in actions:
        match = _forbidden_match(
            a.get("title", ""), a.get("description", "")
        )
        if match:
            ra = dict(a)
            ra["bucket"] = _BUCKET_UNSAFE
            ra["safety"] = "unsafe"
            ra["forbidden_substring_matched"] = match
            out.append(ra)
        else:
            out.append(a)
    return out


def build_campaign(
    *,
    campaign: str,
    generated_at_utc: str,
    dossier_path: Path,
    plan_path: Path,
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
    if not plan_path.exists():
        raise FileNotFoundError(
            f"materials compute plan not found at {plan_path}"
        )

    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    if dossier.get("schema") not in _DOSSIER_SCHEMAS_ACCEPTED:
        raise ValueError(
            f"dossier {dossier_path.name} schema must be one of "
            f"{_DOSSIER_SCHEMAS_ACCEPTED!r}; got "
            f"{dossier.get('schema')!r}"
        )
    if plan.get("schema") != _PLAN_SCHEMA:
        raise ValueError(
            f"plan {plan_path.name} schema must be {_PLAN_SCHEMA!r}"
        )
    if dossier.get("track") != _TRACK or plan.get("track") != _TRACK:
        raise ValueError(
            f"dossier or plan declares a non-{_TRACK!r} track"
        )

    dossier_sha = hashlib.sha256(dossier_path.read_bytes()).hexdigest()
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()

    # Build per-candidate index of UC proposals.
    proposals_by_candidate: Dict[str, List[Dict[str, Any]]] = {}
    for cp in plan.get("candidate_proposals", []):
        proposals_by_candidate[cp["candidate_id"]] = cp.get(
            "proposed_families", []
        )

    # Aggregate evidence-gap inventory across all candidates.
    seen_gaps: Dict[str, int] = {}
    per_candidate_gaps: Dict[str, List[str]] = {}
    for h in dossier.get("hypotheses", []):
        gids: List[str] = []
        for g in h.get("evidence_gaps", []) or []:
            for gid in _assign_gaps_for_text(g):
                if gid not in gids:
                    gids.append(gid)
                seen_gaps[gid] = seen_gaps.get(gid, 0) + 1
        per_candidate_gaps[h["candidate_id"]] = gids

    # Generate candidate-level NextActions.
    raw_actions: List[Dict[str, Any]] = []
    for h in dossier.get("hypotheses", []):
        raw_actions.extend(
            _propose_actions_for_hypothesis(h, proposals_by_candidate)
        )

    # Anchor the unsafe_or_forbidden bucket.
    for u in _ANCHOR_UNSAFE_ACTIONS:
        raw_actions.append({
            **u,
            "candidate_id": None,
            "bucket": _BUCKET_UNSAFE,
            "safety": "unsafe",
            "impact": "none",
            "prereqs": [],
            "forbidden_substring_matched": u["matched_substring"],
        })

    # Apply the safety veto as a defensive pass.
    veto_actions = _apply_safety_veto(raw_actions)

    # Rank.
    ranked = sorted(veto_actions, key=_ranking_key)

    # Build the gap inventory section in deterministic order.
    gap_inventory: List[Dict[str, Any]] = []
    for g in _GAP_TAXONOMY:
        gap_inventory.append({
            "gap_id": g["gap_id"],
            "label": g["label"],
            "candidate_count": seen_gaps.get(g["gap_id"], 0),
        })

    by_bucket: Dict[str, int] = {b: 0 for b in _ALL_BUCKETS}
    for a in ranked:
        by_bucket[a.get("bucket", _BUCKET_IMMEDIATE)] += 1

    campaign_manifest = {
        "schema": _SCHEMA,
        "campaign": campaign,
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "source": {
            "dossier_basename": dossier_path.name,
            "dossier_sha256": dossier_sha,
            "plan_basename": plan_path.name,
            "plan_sha256": plan_sha,
        },
        "safety_status": {
            "dry_run": True,
            "ready_to_register": True,
            "registered": False,
            "no_rewards_active": True,
            "no_chain_broadcast": True,
            "no_consensus_modification": True,
            "no_public_publication": True,
            "no_wallet_action": True,
        },
        "evidence_gap_inventory": gap_inventory,
        "per_candidate_gap_assignments": [
            {"candidate_id": cid, "gap_ids": per_candidate_gaps[cid]}
            for cid in sorted(per_candidate_gaps)
        ],
        "next_actions": ranked,
        "summary": {
            "candidates_total": len(per_candidate_gaps),
            "actions_total": len(ranked),
            "by_bucket": by_bucket,
            "gaps_observed": sum(
                1 for g in gap_inventory if g["candidate_count"] > 0
            ),
        },
    }

    blob = canonical_dumps(campaign_manifest)
    _check_no_host_paths(blob)
    return campaign_manifest


def render_markdown(m: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Track — Campaign Manifest "
        f"`{m['campaign']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN manifest.** Composes the dossier and the Useful "
        "Compute plan into one campaign with explicit evidence-gap "
        "inventory and 6-bucket next-actions. ``ready_to_register=true``"
        " but ``registered=false``; on-chain anchoring is a separate "
        "operator decision."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{m['schema']}`")
    lines.append(f"- **Track**: `{m['track']}`")
    lines.append(f"- **Generated (UTC)**: {m['generated_at_utc']}")
    src = m["source"]
    lines.append("- **Source**:")
    for k in sorted(src):
        lines.append(f"  - `{k}`: `{src[k]}`")
    lines.append("")
    lines.append("## Safety status")
    lines.append("")
    for k in sorted(m["safety_status"]):
        lines.append(f"- `{k}`: `{m['safety_status'][k]}`")
    lines.append("")
    lines.append("## Evidence-gap inventory (closed taxonomy)")
    lines.append("")
    for g in m["evidence_gap_inventory"]:
        lines.append(
            f"- `{g['gap_id']}` &mdash; {g['label']} "
            f"(observed in {g['candidate_count']} candidate"
            f"{'s' if g['candidate_count']!=1 else ''})"
        )
    lines.append("")
    lines.append("## Next actions, ranked")
    lines.append("")
    for a in m["next_actions"]:
        lines.append(
            f"- **{a['title']}** &mdash; bucket `{a['bucket']}` "
            f"&mdash; safety `{a['safety']}` &mdash; impact "
            f"`{a['impact']}` &mdash; id `{a['action_id']}`"
        )
        lines.append(f"  - {a['description']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_campaign",
        description=(
            "Build the Trinity / Materials Track Campaign Manifest from "
            "a dossier and a Useful Compute plan. Dry-run; never "
            "broadcasts, signs or registers."
        ),
    )
    p.add_argument(
        "--campaign", type=str, default="novel_frontier_phase1",
    )
    p.add_argument(
        "--dossier", type=str, default=None,
    )
    p.add_argument(
        "--plan", type=str, default=None,
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
    args = p.parse_args(argv)

    dossier_path = Path(
        args.dossier
        or f"TRINITY_MATERIALS_DOSSIER_{args.campaign}.json"
    )
    plan_path = Path(
        args.plan
        or f"TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_{args.campaign}.json"
    )
    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_CAMPAIGN_{args.campaign}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_CAMPAIGN_{args.campaign}.md"
    )

    manifest = build_campaign(
        campaign=args.campaign,
        generated_at_utc=args.generated_at_utc,
        dossier_path=dossier_path,
        plan_path=plan_path,
    )

    out_json.write_text(canonical_dumps(manifest), encoding="utf-8")
    out_md.write_text(render_markdown(manifest), encoding="utf-8")

    s = manifest["summary"]
    print(f"[materials_campaign] wrote {out_json}")
    print(f"[materials_campaign] wrote {out_md}")
    print(
        f"[materials_campaign] actions: total={s['actions_total']}, "
        f"by_bucket={s['by_bucket']}, "
        f"gaps_observed={s['gaps_observed']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
