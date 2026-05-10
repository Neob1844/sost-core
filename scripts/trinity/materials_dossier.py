#!/usr/bin/env python3
"""Trinity / Materials Track — materials dossier builder (mock-first).

Reads a ``TRINITY_MATERIALS_SCORECARD_<campaign>.json`` and runs each
candidate through a deterministic mock AI Council of three members:
``validator`` (final-word reject/hold), ``materials_expert`` (synthesis /
characterization realism) and ``novelty_judge`` (frontier-proximity vs.
novelty score). Emits ``TRINITY_MATERIALS_DOSSIER_<campaign>.json`` and a
Markdown sidecar.

Combine rule
------------
Strictest-member-wins:

- Any ``reject`` → final decision is ``reject``.
- Else any ``hold`` → final decision is ``hold``.
- Else all three ``accept`` → final decision is ``accept``.

``veto_applied`` is ``true`` iff the validator's vote alone forced a
non-accept outcome that the other members would not have produced.

Invariants
----------
- DRY-RUN. No network, no RPC, no subprocess, no wallet.
- Canonical JSON. Byte-identical given the same pinned time and inputs.
- Cross-machine reproducibility. ``source.scorecard_sha256`` +
  ``scorecard_basename`` instead of an absolute host path.
- ``--live-materials-engine`` is a v0 stub: logs a not-yet message and
  falls back to the mock council.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCHEMA = "trinity-materials-dossier/v0"
_SCORECARD_SCHEMA = "trinity-materials-scorecard/v0"
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")

_VALIDATOR_FRONTIER_ACCEPT = 0.70
_VALIDATOR_NOVELTY_ACCEPT = 0.60
_VALIDATOR_FRONTIER_REJECT = 0.50
_VALIDATOR_NOVELTY_REJECT = 0.35
_EXPERT_MAX_OPEN_QUESTIONS = 2
_NOVELTY_ACCEPT = 0.55
_NOVELTY_HOLD = 0.40


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit dossier: host-path markers leaked into "
            f"canonical JSON: {leaked}"
        )


def _review_validator(c: Dict[str, Any]) -> Dict[str, Any]:
    fp = float(c["seed_frontier_proximity"])
    nv = float(c["seed_novelty"])
    if fp < _VALIDATOR_FRONTIER_REJECT or nv < _VALIDATOR_NOVELTY_REJECT:
        return {
            "member": "validator",
            "decision": "reject",
            "rationale": (
                f"frontier_proximity {fp:.2f} and/or novelty {nv:.2f} "
                f"below calibration floor "
                f"({_VALIDATOR_FRONTIER_REJECT:.2f} / "
                f"{_VALIDATOR_NOVELTY_REJECT:.2f})"
            ),
        }
    if fp >= _VALIDATOR_FRONTIER_ACCEPT and nv >= _VALIDATOR_NOVELTY_ACCEPT:
        return {
            "member": "validator",
            "decision": "accept",
            "rationale": (
                f"frontier_proximity {fp:.2f} and novelty {nv:.2f} both "
                f"clear validator thresholds "
                f"({_VALIDATOR_FRONTIER_ACCEPT:.2f} / "
                f"{_VALIDATOR_NOVELTY_ACCEPT:.2f})"
            ),
        }
    return {
        "member": "validator",
        "decision": "hold",
        "rationale": (
            f"insufficient baseline; frontier_proximity {fp:.2f} or "
            f"novelty {nv:.2f} below accept thresholds but above the "
            f"reject floor"
        ),
    }


def _review_materials_expert(c: Dict[str, Any]) -> Dict[str, Any]:
    family = c.get("family", "")
    n_q = len(c.get("open_questions") or [])
    if "reference" in family.lower():
        return {
            "member": "materials_expert",
            "decision": "hold",
            "rationale": (
                f"family {family!r} marked as reference / calibration "
                f"anchor; not advanced past hold without an explicit "
                f"campaign goal"
            ),
        }
    if n_q > _EXPERT_MAX_OPEN_QUESTIONS:
        return {
            "member": "materials_expert",
            "decision": "hold",
            "rationale": (
                f"{n_q} open synthesis / characterization questions; "
                f"more than the {_EXPERT_MAX_OPEN_QUESTIONS} a v0 mock "
                f"reviewer is willing to advance past hold"
            ),
        }
    return {
        "member": "materials_expert",
        "decision": "accept",
        "rationale": (
            "open-question count is manageable and family is not a "
            "reference anchor; expert sees no blocker for further work"
        ),
    }


def _review_novelty_judge(c: Dict[str, Any]) -> Dict[str, Any]:
    nv = float(c["seed_novelty"])
    if nv >= _NOVELTY_ACCEPT:
        return {
            "member": "novelty_judge",
            "decision": "accept",
            "rationale": (
                f"seed_novelty {nv:.2f} >= {_NOVELTY_ACCEPT:.2f}; "
                f"frontier-worthy in the v0 mock scale"
            ),
        }
    if nv >= _NOVELTY_HOLD:
        return {
            "member": "novelty_judge",
            "decision": "hold",
            "rationale": (
                f"seed_novelty {nv:.2f} in [{_NOVELTY_HOLD:.2f}, "
                f"{_NOVELTY_ACCEPT:.2f}); not enough novelty to advance "
                f"in v0 mock"
            ),
        }
    return {
        "member": "novelty_judge",
        "decision": "reject",
        "rationale": (
            f"seed_novelty {nv:.2f} < {_NOVELTY_HOLD:.2f}; treated as "
            f"calibration / reference, not a discovery candidate"
        ),
    }


def _combine_decisions(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Strictest-member-wins. Returns dict with final decision +
    veto_applied flag (true iff validator alone forced non-accept)."""
    decisions = [r["decision"] for r in reviews]
    if "reject" in decisions:
        final = "reject"
    elif "hold" in decisions:
        final = "hold"
    else:
        final = "accept"
    validator = next(r for r in reviews if r["member"] == "validator")
    others = [r["decision"] for r in reviews if r["member"] != "validator"]
    veto_applied = False
    if validator["decision"] != "accept":
        # If every non-validator member would have accepted but the
        # validator did not, mark veto_applied.
        if all(d == "accept" for d in others):
            veto_applied = True
    return {"decision": final, "veto_applied": veto_applied}


def _evidence_gaps(c: Dict[str, Any]) -> List[str]:
    return list(c.get("open_questions") or [])


def build_dossier(
    *,
    campaign: str,
    generated_at_utc: str,
    scorecard_path: Path,
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
    if not scorecard_path.exists():
        raise FileNotFoundError(
            f"materials scorecard not found at {scorecard_path}"
        )

    if live_mode:
        print(
            "[materials_dossier] --live-materials-engine: live AI "
            "Council import not yet implemented in v0; using mock council.",
            file=sys.stderr,
        )

    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    if scorecard.get("schema") != _SCORECARD_SCHEMA:
        raise ValueError(
            f"scorecard at {scorecard_path.name} does not declare schema "
            f"{_SCORECARD_SCHEMA!r}"
        )
    if scorecard.get("track") != _TRACK:
        raise ValueError(
            f"scorecard at {scorecard_path.name} is not a {_TRACK!r} "
            f"scorecard"
        )

    scorecard_sha = hashlib.sha256(
        scorecard_path.read_bytes()
    ).hexdigest()

    hypotheses: List[Dict[str, Any]] = []
    counts = {"accept": 0, "hold": 0, "reject": 0}
    veto_count = 0

    for c in scorecard.get("candidates", []):
        reviews = [
            _review_validator(c),
            _review_materials_expert(c),
            _review_novelty_judge(c),
        ]
        combined = _combine_decisions(reviews)
        counts[combined["decision"]] = counts.get(combined["decision"], 0) + 1
        if combined["veto_applied"]:
            veto_count += 1
        hypotheses.append({
            "candidate_id": c["id"],
            "formula": c["formula"],
            "family": c["family"],
            "seed_novelty": c["seed_novelty"],
            "seed_frontier_proximity": c["seed_frontier_proximity"],
            "reviews": reviews,
            "decision": combined["decision"],
            "veto_applied": combined["veto_applied"],
            "evidence_gaps": _evidence_gaps(c),
        })

    dossier = {
        "schema": _SCHEMA,
        "campaign": campaign,
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "source": {
            "mode": "mock",
            "scorecard_basename": scorecard_path.name,
            "scorecard_sha256": scorecard_sha,
            "features_available": scorecard.get("features_available", 0),
        },
        "council_members": ["validator", "materials_expert", "novelty_judge"],
        "summary": {
            "candidates_total": len(hypotheses),
            "decisions_accept": counts.get("accept", 0),
            "decisions_hold": counts.get("hold", 0),
            "decisions_reject": counts.get("reject", 0),
            "validator_vetoes_applied": veto_count,
        },
        "hypotheses": hypotheses,
    }

    blob = canonical_dumps(dossier)
    _check_no_host_paths(blob)
    return dossier


def render_markdown(dossier: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Track — Dossier "
        f"`{dossier['campaign']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN dossier.** Mock AI Council reviews of the candidate "
        "set declared in the materials scorecard. Not a materials "
        "discovery claim. Decisions follow strictest-member-wins with "
        "validator-veto tracking."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{dossier['schema']}`")
    lines.append(f"- **Track**: `{dossier['track']}`")
    lines.append(f"- **Generated (UTC)**: {dossier['generated_at_utc']}")
    src = dossier["source"]
    lines.append("- **Source**:")
    for k in sorted(src):
        lines.append(f"  - `{k}`: `{src[k]}`")
    lines.append("")
    s = dossier["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **candidates_total**: `{s['candidates_total']}`")
    lines.append(f"- **decisions_accept**: `{s['decisions_accept']}`")
    lines.append(f"- **decisions_hold**: `{s['decisions_hold']}`")
    lines.append(f"- **decisions_reject**: `{s['decisions_reject']}`")
    lines.append(
        f"- **validator_vetoes_applied**: `{s['validator_vetoes_applied']}`"
    )
    lines.append("")
    lines.append("## Hypotheses")
    lines.append("")
    for h in dossier["hypotheses"]:
        lines.append(
            f"### `{h['candidate_id']}` &mdash; {h['formula']} "
            f"({h['family']}) &mdash; **{h['decision'].upper()}**"
        )
        lines.append("")
        lines.append(
            f"- seed_novelty=`{h['seed_novelty']:.2f}`, "
            f"seed_frontier_proximity=`{h['seed_frontier_proximity']:.2f}`, "
            f"veto_applied=`{h['veto_applied']}`"
        )
        lines.append("- **Reviews**:")
        for r in h["reviews"]:
            lines.append(
                f"  - `{r['member']}`: **{r['decision']}** &mdash; "
                f"{r['rationale']}"
            )
        if h["evidence_gaps"]:
            lines.append("- **Evidence gaps**:")
            for g in h["evidence_gaps"]:
                lines.append(f"  - {g}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_dossier",
        description=(
            "Build a Trinity / Materials Track dossier from a materials "
            "scorecard. Mock-first AI Council; never broadcasts."
        ),
    )
    p.add_argument(
        "--campaign", type=str, default="novel_frontier_phase1",
    )
    p.add_argument(
        "--scorecard", type=str, default=None,
        help=(
            "Path to TRINITY_MATERIALS_SCORECARD_<campaign>.json. "
            "Defaults to TRINITY_MATERIALS_SCORECARD_<campaign>.json in "
            "the current directory."
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
        help="v0 stub: live AI Council import not yet implemented.",
    )
    args = p.parse_args(argv)

    scorecard_path = Path(
        args.scorecard
        or f"TRINITY_MATERIALS_SCORECARD_{args.campaign}.json"
    )
    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_DOSSIER_{args.campaign}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_DOSSIER_{args.campaign}.md"
    )

    dossier = build_dossier(
        campaign=args.campaign,
        generated_at_utc=args.generated_at_utc,
        scorecard_path=scorecard_path,
        live_mode=args.live_materials_engine,
    )

    out_json.write_text(canonical_dumps(dossier), encoding="utf-8")
    out_md.write_text(render_markdown(dossier), encoding="utf-8")

    s = dossier["summary"]
    print(f"[materials_dossier] wrote {out_json}")
    print(f"[materials_dossier] wrote {out_md}")
    print(
        f"[materials_dossier] decisions: "
        f"accept={s['decisions_accept']} "
        f"hold={s['decisions_hold']} "
        f"reject={s['decisions_reject']} "
        f"vetoes={s['validator_vetoes_applied']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
