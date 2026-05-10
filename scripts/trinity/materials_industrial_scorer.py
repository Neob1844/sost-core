#!/usr/bin/env python3
"""Trinity / Materials Discovery — Industrial scorer v0.1.

Reads a filtered candidate pool (output of
``materials_chemistry_filter.py``) and the original generator pool, and
produces a **v0.1 materials scorecard** with a transparent weighted
score per candidate plus explicit ``reason_codes`` and
``missing_evidence``.

The scorecard is intentionally a **superset** of the v0 scorecard
schema (``trinity-materials-scorecard/v0``): every candidate carries
both the new ``score`` / ``confidence`` / ``evidence_level`` fields
**and** the legacy ``seed_novelty`` / ``seed_frontier_proximity`` /
``open_questions`` fields that the v0 ``materials_dossier.py`` already
understands. That keeps the downstream AI-Council bridge unchanged.

Scoring axes (weights pinned)
-----------------------------
::

    abundance              (0.20)  Higher for earth-abundant elements
    criticality_penalty    (0.20)  Subtracted: PGMs and heavy REEs hurt
    structure_plausibility (0.15)  Spinel/perovskite > layered > interface
    hypothesis_count       (0.10)  More industrial hypotheses → higher
    compute_feasibility    (0.10)  Smaller integer unit cell → higher
    novelty_uncertainty    (0.10)  Subtracted: any candidate is by
                                   definition unvalidated, so we apply
                                   a fixed penalty proportional to the
                                   number of missing evidence layers
    toxicity_cost          (0.15)  Subtracted: toxic / expensive
                                   elements hurt

Each axis is normalised to [0, 1] before weighting. The final ``score``
is the weighted sum, scaled to [0, 100] and rounded to one decimal.

Invariants
----------
- Deterministic. Pure stdlib. Pinned weight table.
- No network, no subprocess, no broadcast surface.
- Canonical JSON. No host-path leak.
- Every candidate carries ``evidence_level = "remote_proxy_only"`` so
  the downstream reader knows the score is **not** DFT-validated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


_FILTER_SCHEMA = "trinity-materials-candidate-filter/v0.1"
_POOL_SCHEMA = "trinity-materials-candidate-pool/v0.1"
_OUTPUT_SCHEMA = "trinity-materials-scorecard/v0.1"
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")


# Crustal abundance (rough ppm in continental crust). Used only for a
# relative abundance score; not a chemistry claim.
_CRUSTAL_PPM: Dict[str, float] = {
    "O": 461000.0, "Si": 282000.0, "Al": 82000.0, "Fe": 56000.0,
    "Ca": 41000.0, "Na": 23000.0, "Mg": 23000.0, "K": 21000.0,
    "Ti": 5700.0, "Mn": 950.0, "Ba": 425.0, "Sr": 370.0,
    "Cr": 102.0, "Zn": 70.0, "Ni": 84.0, "Cu": 60.0, "Co": 25.0,
    "Li": 20.0, "La": 39.0, "Y": 33.0, "Nd": 41.0, "Pr": 9.2,
    "Zr": 165.0, "V": 120.0, "Nb": 20.0, "Hf": 3.0, "Ta": 2.0,
    "Sn": 2.3, "Ga": 19.0, "Ce": 66.5, "Hg": 0.085, "Pb": 14.0,
    "Cd": 0.15, "As": 1.8, "Tl": 0.85, "Be": 2.8,
    "Pt": 0.005, "Pd": 0.015, "Rh": 0.001, "Ir": 0.001,
    "Os": 0.0015, "Ru": 0.001,
    "Sc": 22.0, "Dy": 5.2, "Tb": 1.2,
}

_CRITICAL_ELEMENTS = {
    "Pt", "Pd", "Rh", "Ir", "Os", "Ru",
    "Sc", "Dy", "Tb",
}

_TOXIC_ELEMENTS = {"Pb", "Cd", "Hg", "As", "Tl", "Be"}

_STRUCTURE_PLAUSIBILITY = {
    "spinel": 0.85,
    "perovskite": 0.90,
    "layered_oxide": 0.70,
    "oxide_interface": 0.55,
}

_WEIGHTS = {
    "abundance": 0.20,
    "criticality_penalty": 0.20,
    "structure_plausibility": 0.15,
    "hypothesis_count": 0.10,
    "compute_feasibility": 0.10,
    "novelty_uncertainty_penalty": 0.10,
    "toxicity_cost_penalty": 0.15,
}

# Generic per-family "open questions" template. The dossier downstream
# reads these so the council mock can reason about what is missing.
_FAMILY_OPEN_QUESTIONS = {
    "spinel": [
        "no DFT formation energy on file",
        "no MLIP relaxation baseline",
        "no measured magnetic ordering reference",
    ],
    "perovskite": [
        "no DFT formation energy on file",
        "no phonon screening at the operating temperature",
        "no proton conductivity reference (if relevant)",
    ],
    "layered_oxide": [
        "no DFT formation energy on file",
        "no ion-migration barrier estimate",
        "no synthesis polymorph reference",
    ],
    "oxide_interface": [
        "no interface energy baseline",
        "no band-edge alignment data",
        "no defect inventory at the interface",
    ],
}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit scorecard: host-path markers leaked: "
            f"{leaked}"
        )


def _abundance_score(composition: Mapping[str, int]) -> float:
    """Geometric mean of log10(ppm) of constituent elements, normalised
    to [0, 1] against the most-abundant case (all O)."""
    if not composition:
        return 0.0
    import math
    log_sum = 0.0
    count = 0
    for elem, n in composition.items():
        ppm = _CRUSTAL_PPM.get(elem, 0.0001)
        log_sum += math.log10(max(ppm, 1e-6)) * n
        count += n
    if count == 0:
        return 0.0
    log_mean = log_sum / count
    # Normalise: log10(461000) ≈ 5.66 is the upper anchor (pure O);
    # log10(0.001) = -3.0 is the lower anchor.
    upper, lower = 5.66, -3.0
    norm = (log_mean - lower) / (upper - lower)
    return max(0.0, min(1.0, norm))


def _criticality_penalty(composition: Mapping[str, int]) -> float:
    """1.0 if no critical element, scales down with critical-element
    count. Returned as a *penalty value* in [0, 1] where 0 = no
    penalty and 1 = maximum penalty."""
    crit_count = sum(
        composition[e] for e in composition if e in _CRITICAL_ELEMENTS
    )
    if crit_count == 0:
        return 0.0
    # Each critical atom adds 0.25 of penalty up to a cap of 1.0.
    return min(1.0, 0.25 * crit_count)


def _toxicity_cost_penalty(composition: Mapping[str, int]) -> float:
    tox_count = sum(
        composition[e] for e in composition if e in _TOXIC_ELEMENTS
    )
    return min(1.0, 0.4 * tox_count)


def _hypothesis_count_score(hypotheses: List[str]) -> float:
    n = len(hypotheses or [])
    if n <= 0:
        return 0.0
    return min(1.0, n / 3.0)


def _compute_feasibility(composition: Mapping[str, int]) -> float:
    atoms = sum(composition.values())
    if atoms <= 0:
        return 0.0
    # Smaller integer unit cells are easier to relax with MLIP / DFT.
    # 7 atoms (e.g. NiAl2O4 unit) → ~0.86; 14 atoms → ~0.43.
    return max(0.0, min(1.0, 6.0 / atoms))


def _novelty_uncertainty_penalty(family: str) -> float:
    # Every v0.1 candidate is unvalidated; the penalty proportional to
    # how many evidence layers are missing for this family.
    return min(1.0, 0.10 + 0.05 * len(_FAMILY_OPEN_QUESTIONS.get(family, [])))


def _structure_plausibility(family: str) -> float:
    return _STRUCTURE_PLAUSIBILITY.get(family, 0.50)


def _compute_score(
    composition: Mapping[str, int],
    family: str,
    hypotheses: List[str],
) -> Dict[str, Any]:
    abundance = _abundance_score(composition)
    crit_pen = _criticality_penalty(composition)
    tox_pen = _toxicity_cost_penalty(composition)
    hyp = _hypothesis_count_score(hypotheses)
    feas = _compute_feasibility(composition)
    nov_pen = _novelty_uncertainty_penalty(family)
    struct = _structure_plausibility(family)

    raw = (
        _WEIGHTS["abundance"] * abundance
        + _WEIGHTS["structure_plausibility"] * struct
        + _WEIGHTS["hypothesis_count"] * hyp
        + _WEIGHTS["compute_feasibility"] * feas
        - _WEIGHTS["criticality_penalty"] * crit_pen
        - _WEIGHTS["novelty_uncertainty_penalty"] * nov_pen
        - _WEIGHTS["toxicity_cost_penalty"] * tox_pen
    )
    # raw is in [-sum_penalty_weights, sum_positive_weights]. Shift to
    # a 0..100 display by clamping to a [0, 1] window centred on the
    # positive-weight ceiling. Concretely: positive ceiling = 0.55,
    # negative floor = -0.45. Map [-0.45, 0.55] → [0, 100].
    score_norm = (raw + 0.45) / 1.0
    score = max(0.0, min(100.0, round(score_norm * 100.0, 1)))
    confidence = max(
        0.0,
        min(
            1.0,
            (abundance + struct + (1.0 - crit_pen) + (1.0 - tox_pen))
            / 4.0,
        ),
    )

    return {
        "score": score,
        "confidence": round(confidence, 3),
        "axes": {
            "abundance": round(abundance, 3),
            "structure_plausibility": round(struct, 3),
            "hypothesis_count_score": round(hyp, 3),
            "compute_feasibility": round(feas, 3),
            "criticality_penalty": round(crit_pen, 3),
            "novelty_uncertainty_penalty": round(nov_pen, 3),
            "toxicity_cost_penalty": round(tox_pen, 3),
        },
    }


def build_scorecard(
    *,
    candidate_pool_path: Path,
    filter_path: Path,
    generated_at_utc: str,
) -> Dict[str, Any]:
    if not candidate_pool_path.exists():
        raise FileNotFoundError(
            f"candidate pool not found: {candidate_pool_path}"
        )
    if not filter_path.exists():
        raise FileNotFoundError(
            f"filter output not found: {filter_path}"
        )

    pool = json.loads(candidate_pool_path.read_text(encoding="utf-8"))
    flt = json.loads(filter_path.read_text(encoding="utf-8"))
    if pool.get("schema") != _POOL_SCHEMA:
        raise ValueError(
            f"pool schema must be {_POOL_SCHEMA!r}; got "
            f"{pool.get('schema')!r}"
        )
    if flt.get("schema") != _FILTER_SCHEMA:
        raise ValueError(
            f"filter schema must be {_FILTER_SCHEMA!r}; got "
            f"{flt.get('schema')!r}"
        )

    pool_sha = hashlib.sha256(
        candidate_pool_path.read_bytes()
    ).hexdigest()
    filter_sha = hashlib.sha256(filter_path.read_bytes()).hexdigest()

    # Index pool by id for easy lookup.
    by_id = {c["id"]: c for c in pool.get("candidates", [])}
    accepted_ids = [
        d["id"] for d in flt.get("decisions", [])
        if d.get("filter_verdict") == "accept"
    ]

    scored: List[Dict[str, Any]] = []
    for cid in accepted_ids:
        c = by_id.get(cid)
        if c is None:
            continue
        composition = c.get("composition") or {}
        family = c.get("family") or "unknown"
        hypotheses = c.get("industrial_hypotheses") or []
        s = _compute_score(composition, family, hypotheses)
        # Map the v0.1 score onto v0-compatible fields so the existing
        # materials_dossier.py reads the candidate without modification.
        seed_novelty = round(s["score"] / 100.0, 3)
        seed_frontier_proximity = s["confidence"]
        open_qs = list(_FAMILY_OPEN_QUESTIONS.get(family, []))
        reason_codes: List[str] = []
        for axis, val in sorted(s["axes"].items()):
            reason_codes.append(f"axis:{axis}={val}")
        reason_codes.append(
            f"weights_version=v0.1; positive_ceiling=0.55; "
            f"negative_floor=-0.45"
        )
        scored.append({
            "id": cid,
            "formula": c.get("formula"),
            "family": family,
            "composition": composition,
            "industrial_hypotheses": hypotheses,
            "score": s["score"],
            "confidence": s["confidence"],
            "axes": s["axes"],
            "evidence_level": "remote_proxy_only",
            "reason_codes": reason_codes,
            "missing_evidence": [
                "DFT formation energy",
                "phonon ground-state screening",
                "MLIP relaxation cross-check",
                "synthesis polymorph reference",
            ],
            # v0-compatible fields so the existing dossier reads this
            # without schema-bump work:
            "seed_novelty": seed_novelty,
            "seed_frontier_proximity": seed_frontier_proximity,
            "open_questions": open_qs,
        })

    # Sort by score desc, then by id asc so the output ordering is
    # stable across runs.
    scored.sort(key=lambda x: (-x["score"], x["id"]))

    scorecard = {
        "schema": _OUTPUT_SCHEMA,
        "campaign": "oxide_frontier_v01",
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "features_available": 0,
        "source": {
            "mode": "deterministic_rule_based_v0.1",
            "candidate_pool_basename": candidate_pool_path.name,
            "candidate_pool_sha256": pool_sha,
            "filter_basename": filter_path.name,
            "filter_sha256": filter_sha,
        },
        "honesty_matrix": {
            "candidates_have_synthesis_data": False,
            "candidates_have_dft_relaxation": False,
            "candidates_have_phonon_screening": False,
            "novelty_baseline_locked": False,
            "frontier_scores_are_seeds_not_validations": True,
            "scores_are_remote_proxy_only": True,
        },
        "weights": _WEIGHTS,
        # The dossier expects a "candidates" key. Provide it.
        "candidates": scored,
        "summary": {
            "candidates_scored": len(scored),
            "candidates_pool": len(pool.get("candidates", [])),
        },
    }
    blob = canonical_dumps(scorecard)
    _check_no_host_paths(blob)
    return scorecard


def render_markdown(sc: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Discovery — Scorecard "
        f"`{sc['campaign']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN scorecard.** Weighted industrial-promise score "
        "computed from remote proxy axes (abundance, criticality, "
        "structure, hypothesis count, compute feasibility, novelty "
        "uncertainty, toxicity/cost). Not a DFT result. Not a "
        "synthesis recommendation. Not a performance claim."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{sc['schema']}`")
    lines.append(f"- **Track**: `{sc['track']}`")
    lines.append(f"- **Generated (UTC)**: {sc['generated_at_utc']}")
    src = sc["source"]
    lines.append("- **Source**:")
    for k in sorted(src):
        lines.append(f"  - `{k}`: `{src[k]}`")
    lines.append("")
    lines.append("## Weights")
    lines.append("")
    for k, v in sorted(sc["weights"].items()):
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Top candidates by score")
    lines.append("")
    lines.append(
        "| rank | id | formula | family | score | confidence | "
        "hypotheses |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for rank, c in enumerate(sc["candidates"][:25], start=1):
        hyp = ", ".join(c.get("industrial_hypotheses", []))
        lines.append(
            f"| {rank} | `{c['id']}` | `{c['formula']}` | "
            f"`{c['family']}` | {c['score']} | {c['confidence']} | "
            f"{hyp} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_industrial_scorer",
        description=(
            "Score accepted materials candidates with a transparent "
            "weighted axis system. Dry-run; deterministic."
        ),
    )
    p.add_argument("--family", type=str, default="oxide_frontier")
    p.add_argument("--candidate-pool", type=str, default=None)
    p.add_argument("--filter", type=str, default=None)
    p.add_argument(
        "--pinned-time", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    args = p.parse_args(argv)

    pool_path = Path(
        args.candidate_pool
        or f"TRINITY_MATERIALS_CANDIDATES_{args.family}.json"
    )
    filter_path = Path(
        args.filter
        or f"TRINITY_MATERIALS_FILTER_{args.family}.json"
    )
    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_SCORECARD_{args.family}_v01.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_SCORECARD_{args.family}_v01.md"
    )

    sc = build_scorecard(
        candidate_pool_path=pool_path,
        filter_path=filter_path,
        generated_at_utc=args.pinned_time,
    )
    out_json.write_text(canonical_dumps(sc), encoding="utf-8")
    out_md.write_text(render_markdown(sc), encoding="utf-8")

    print(f"[scorer] wrote {out_json}")
    print(f"[scorer] wrote {out_md}")
    print(
        f"[scorer] scored: {sc['summary']['candidates_scored']}, "
        f"top score: {sc['candidates'][0]['score'] if sc['candidates'] else 'n/a'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
