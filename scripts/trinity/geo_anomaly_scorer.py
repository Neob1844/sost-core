#!/usr/bin/env python3
"""Trinity / Geo Discovery — Anomaly scorer v0.1.

Reads a filtered candidate AOI pool (output of
``geo_candidate_filter.py``) and the original candidate pool, and
produces a **v0.1 geo scorecard** with a transparent weighted score
per AOI plus explicit ``reason_codes``, ``missing_evidence`` and
``recommended_next_data_layers``.

The scorecard mirrors the role of the materials scorecard but uses
geo-domain proxy axes. Every entry carries
``evidence_level = "remote_proxy_only"`` so the downstream reader
knows the score is **not** field-validated, not drilled, not
geophysically confirmed.

Scoring axes (weights pinned)
-----------------------------
::

    tectonic_belt_prior         (0.20)  Tier-1 belt > Tier-2 > Tier-3
    commodity_belt_compatibility(0.15)  AOI hypotheses ∩ belt primaries
    aridity_proxy               (0.10)  Arid → easier surface mapping
    terrain_ruggedness_proxy    (0.10)  Some ruggedness helps prospecting
    data_availability           (0.20)  Developed region public data
    novelty_penalty             (0.10)  Subtracted: too close to demos
    uncertainty_penalty         (0.15)  Subtracted: always present

Each axis is normalised to [0, 1] before weighting. The final
``score`` is the weighted sum, scaled to [0, 100] and rounded.

Invariants
----------
- Deterministic. Pure stdlib. Pinned weight + lookup tables.
- No network, no subprocess, no broadcast surface.
- Canonical JSON. No host-path leak.
- Every candidate carries ``evidence_level = "remote_proxy_only"``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


_FILTER_SCHEMA = "trinity-geo-candidate-filter/v0.1"
_POOL_SCHEMA = "trinity-geo-candidate-pool/v0.1"
_OUTPUT_SCHEMA = "trinity-geo-scorecard/v0.1"
_TRACK = "geaspirit"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")


# Region tag → (tier, aridity_proxy, ruggedness_proxy, data_availability)
# Aridity: 1.0 = very arid, 0.0 = very wet.
# Ruggedness: 1.0 = high relief, 0.0 = flat.
# Data: 1.0 = abundant public data, 0.0 = essentially none.
_REGION_PROXY: Dict[str, Dict[str, Any]] = {
    "south_america_andes":           {"tier": 1, "arid": 0.85, "rug": 0.95, "data": 0.75},
    "australia_lachlan":             {"tier": 1, "arid": 0.55, "rug": 0.55, "data": 0.95},
    "australia_yilgarn":             {"tier": 1, "arid": 0.90, "rug": 0.40, "data": 0.95},
    "australia_hamersley_margin":    {"tier": 2, "arid": 0.85, "rug": 0.65, "data": 0.90},
    "north_america_trans_hudson":    {"tier": 1, "arid": 0.30, "rug": 0.45, "data": 0.85},
    "north_america_superior":        {"tier": 1, "arid": 0.30, "rug": 0.40, "data": 0.85},
    "north_america_carlin":          {"tier": 1, "arid": 0.80, "rug": 0.70, "data": 0.95},
    "north_america_sierra_nevada":   {"tier": 2, "arid": 0.55, "rug": 0.95, "data": 0.95},
    "africa_copperbelt":             {"tier": 1, "arid": 0.50, "rug": 0.30, "data": 0.55},
    "africa_birimian":               {"tier": 1, "arid": 0.55, "rug": 0.40, "data": 0.50},
    "africa_bushveld":               {"tier": 1, "arid": 0.55, "rug": 0.45, "data": 0.75},
    "africa_kalahari_copper":        {"tier": 2, "arid": 0.85, "rug": 0.20, "data": 0.55},
    "europe_iberian_pyrite":         {"tier": 2, "arid": 0.55, "rug": 0.55, "data": 0.90},
    "europe_skellefte":              {"tier": 2, "arid": 0.35, "rug": 0.45, "data": 0.85},
    "europe_fennoscandian":          {"tier": 2, "arid": 0.30, "rug": 0.50, "data": 0.80},
    "asia_tethyan":                  {"tier": 1, "arid": 0.70, "rug": 0.80, "data": 0.55},
    "asia_caob":                     {"tier": 1, "arid": 0.75, "rug": 0.60, "data": 0.45},
    "asia_sukhoi_log":               {"tier": 2, "arid": 0.40, "rug": 0.70, "data": 0.40},
    "asia_yangtze":                  {"tier": 2, "arid": 0.45, "rug": 0.65, "data": 0.60},
    "asia_tibet_margin":             {"tier": 2, "arid": 0.85, "rug": 0.95, "data": 0.35},
    "pacific_rim_se_asia":           {"tier": 1, "arid": 0.30, "rug": 0.85, "data": 0.55},
    "pacific_rim_ne_asia":           {"tier": 2, "arid": 0.35, "rug": 0.80, "data": 0.80},
    "arctic_greenland_east":         {"tier": 3, "arid": 0.40, "rug": 0.80, "data": 0.40},
    "central_america_volcanic_arc":  {"tier": 2, "arid": 0.35, "rug": 0.85, "data": 0.50},
    "caribbean_nickel":              {"tier": 3, "arid": 0.40, "rug": 0.55, "data": 0.50},
    "south_america_brazilian_shield":{"tier": 1, "arid": 0.45, "rug": 0.45, "data": 0.55},
    "grid_seed":                     {"tier": 3, "arid": 0.50, "rug": 0.50, "data": 0.40},
}

_TIER_SCORE = {1: 1.0, 2: 0.65, 3: 0.30}


# Belt commodity primaries used to compute commodity-compatibility.
# Mirrors the generator's catalog so the scorer can be run standalone.
_REGION_COMMODITIES: Dict[str, List[str]] = {
    "south_america_andes":           ["copper", "gold", "lithium", "silver", "molybdenum"],
    "australia_lachlan":             ["gold", "copper", "silver"],
    "australia_yilgarn":             ["gold", "nickel", "iron"],
    "australia_hamersley_margin":    ["iron", "manganese"],
    "north_america_trans_hudson":    ["gold", "nickel", "copper", "zinc"],
    "north_america_superior":        ["gold", "nickel", "copper", "iron"],
    "north_america_carlin":          ["gold"],
    "north_america_sierra_nevada":   ["gold", "tungsten", "rare_earth_elements"],
    "africa_copperbelt":             ["copper", "cobalt"],
    "africa_birimian":               ["gold", "bauxite", "lithium"],
    "africa_bushveld":               ["chromium", "platinum", "vanadium", "iron"],
    "africa_kalahari_copper":        ["copper", "silver"],
    "europe_iberian_pyrite":         ["copper", "zinc", "lead", "silver", "gold"],
    "europe_skellefte":              ["copper", "zinc", "gold", "silver"],
    "europe_fennoscandian":          ["nickel", "copper", "platinum", "rare_earth_elements"],
    "asia_tethyan":                  ["copper", "gold", "molybdenum"],
    "asia_caob":                     ["copper", "gold", "molybdenum", "tungsten"],
    "asia_sukhoi_log":               ["gold", "silver"],
    "asia_yangtze":                  ["copper", "lead", "zinc", "rare_earth_elements"],
    "asia_tibet_margin":             ["copper", "gold", "lithium"],
    "pacific_rim_se_asia":           ["copper", "gold", "nickel"],
    "pacific_rim_ne_asia":           ["gold", "copper", "rare_earth_elements"],
    "arctic_greenland_east":         ["rare_earth_elements", "zinc", "lead"],
    "central_america_volcanic_arc":  ["gold", "silver", "copper"],
    "caribbean_nickel":              ["nickel", "cobalt"],
    "south_america_brazilian_shield":["iron", "manganese", "niobium", "rare_earth_elements"],
}


_KNOWN_DEMO_CENTERS = [
    (-30.75, 121.47),  # Kalgoorlie
    (-21.0, 118.0),    # Pilbara
    (-12.5, 27.5),     # Zambia Copperbelt
]


_WEIGHTS = {
    "tectonic_belt_prior":          0.20,
    "commodity_belt_compatibility": 0.15,
    "aridity_proxy":                0.10,
    "terrain_ruggedness_proxy":     0.10,
    "data_availability":            0.20,
    "novelty_penalty":              0.10,
    "uncertainty_penalty":          0.15,
}


# Recommended next data layers per axis (used in missing_evidence)
_RECOMMENDED_NEXT_LAYERS = [
    "Sentinel-1/2 monthly mosaic over the AOI",
    "Landsat-8/9 surface reflectance + thermal",
    "SRTM 30m DEM + derived slope / roughness",
    "Gravity (WGM2012) and magnetic (EMAG2) global grids",
    "Local geological survey 1:250k mapping",
    "Public airborne EM / IP survey lines if available",
    "Soil geochemistry transects",
]


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


def _tectonic_score(region: str) -> float:
    proxy = _REGION_PROXY.get(region) or {}
    tier = int(proxy.get("tier") or 3)
    return _TIER_SCORE.get(tier, 0.3)


def _commodity_compat(region: str, hyp: List[str]) -> float:
    primaries = set(_REGION_COMMODITIES.get(region) or [])
    if not primaries or not hyp:
        return 0.0
    inter = primaries.intersection(hyp)
    if not inter:
        return 0.0
    # Score: fraction of the AOI's hypotheses that match belt primaries.
    return round(len(inter) / max(1, len(hyp)), 3)


def _aridity_proxy(region: str) -> float:
    return float((_REGION_PROXY.get(region) or {}).get("arid", 0.5))


def _ruggedness_proxy(region: str) -> float:
    return float((_REGION_PROXY.get(region) or {}).get("rug", 0.5))


def _data_availability(region: str) -> float:
    return float((_REGION_PROXY.get(region) or {}).get("data", 0.5))


def _novelty_penalty(lat: float, lon: float) -> float:
    """Higher penalty when the AOI is too close to a known demo AOI.
    Within 5° of any demo: 0.5–1.0 penalty proportional to closeness.
    Beyond 10°: zero penalty."""
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return 0.5
    closest = 999.0
    for dlat, dlon in _KNOWN_DEMO_CENTERS:
        d = max(abs(lat - dlat), abs(lon - dlon))
        if d < closest:
            closest = d
    if closest >= 10.0:
        return 0.0
    if closest <= 3.0:
        return 1.0
    # Linear ramp from 1.0 at 3° to 0.0 at 10°
    return round(1.0 - (closest - 3.0) / 7.0, 3)


def _uncertainty_penalty(data_avail: float, hyp_count: int) -> float:
    base = 0.3
    data_short = max(0.0, 1.0 - data_avail) * 0.4
    hyp_short = 0.0 if hyp_count >= 2 else 0.2
    return round(min(1.0, base + data_short + hyp_short), 3)


def _compute_score(
    region: str,
    lat: float,
    lon: float,
    hyp: List[str],
) -> Dict[str, Any]:
    tec = _tectonic_score(region)
    cmt = _commodity_compat(region, hyp)
    arid = _aridity_proxy(region)
    rug = _ruggedness_proxy(region)
    data = _data_availability(region)
    nov = _novelty_penalty(lat, lon)
    unc = _uncertainty_penalty(data, len(hyp))

    raw = (
        _WEIGHTS["tectonic_belt_prior"]          * tec
      + _WEIGHTS["commodity_belt_compatibility"] * cmt
      + _WEIGHTS["aridity_proxy"]                * arid
      + _WEIGHTS["terrain_ruggedness_proxy"]     * rug
      + _WEIGHTS["data_availability"]            * data
      - _WEIGHTS["novelty_penalty"]              * nov
      - _WEIGHTS["uncertainty_penalty"]          * unc
    )
    # raw ∈ [−0.25, +0.75]. Map to [0, 100].
    score_norm = (raw + 0.25) / 1.0
    score = max(0.0, min(100.0, round(score_norm * 100.0, 1)))
    confidence = round(
        max(
            0.0,
            min(
                1.0,
                (tec + cmt + data + (1.0 - unc)) / 4.0,
            ),
        ),
        3,
    )
    return {
        "score": score,
        "confidence": confidence,
        "axes": {
            "tectonic_belt_prior": round(tec, 3),
            "commodity_belt_compatibility": round(cmt, 3),
            "aridity_proxy": round(arid, 3),
            "terrain_ruggedness_proxy": round(rug, 3),
            "data_availability": round(data, 3),
            "novelty_penalty": round(nov, 3),
            "uncertainty_penalty": round(unc, 3),
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

    by_id = {c["id"]: c for c in pool.get("candidates", [])}
    accepted_ids = [
        d["id"] for d in flt.get("decisions", [])
        if d.get("filter_verdict") == "accept"
    ]
    flagged_ids = {
        d["id"]
        for d in flt.get("decisions", [])
        if d.get("filter_flags")
    }

    scored: List[Dict[str, Any]] = []
    for aid in accepted_ids:
        c = by_id.get(aid)
        if c is None:
            continue
        region = c.get("region", "grid_seed")
        lat = float(c.get("center_lat") or 0.0)
        lon = float(c.get("center_lon") or 0.0)
        hyp = list(c.get("commodity_hypotheses") or [])
        s = _compute_score(region, lat, lon, hyp)

        # Materials-compatible projection: seed_novelty / seed_frontier_
        # proximity are required by the dossier's AICouncil bridge.
        seed_novelty = round(s["score"] / 100.0, 3)
        seed_frontier_proximity = s["confidence"]

        open_qs = [
            "no field validation on file",
            "no drilling evidence on file",
            "no geophysics survey lines on file",
            "no soil geochemistry transect on file",
        ]
        if aid in flagged_ids:
            open_qs.append("protected-area / legal status needs operator review")

        reason_codes: List[str] = []
        for axis, val in sorted(s["axes"].items()):
            reason_codes.append(f"axis:{axis}={val}")
        reason_codes.append(
            f"weights_version=v0.1; positive_ceiling=0.75; "
            f"negative_floor=-0.25"
        )

        scored.append({
            "id": aid,
            "name": c.get("name"),
            "center_lat": lat,
            "center_lon": lon,
            "bbox": c.get("bbox"),
            "region": region,
            "commodity_hypotheses": hyp,
            "score": s["score"],
            "confidence": s["confidence"],
            "axes": s["axes"],
            "evidence_level": "remote_proxy_only",
            "reason_codes": reason_codes,
            "missing_evidence": [
                "field geological mapping",
                "drilling at AOI center",
                "depth-aware geophysics (gravity, magnetics, AEM)",
                "soil-geochemistry sampling",
            ],
            "recommended_next_data_layers": list(_RECOMMENDED_NEXT_LAYERS),
            # v0-compatible dossier projection
            "seed_novelty": seed_novelty,
            "seed_frontier_proximity": seed_frontier_proximity,
            "open_questions": open_qs,
        })

    scored.sort(key=lambda x: (-x["score"], x["id"]))

    scorecard = {
        "schema": _OUTPUT_SCHEMA,
        "campaign": "global_phase1",
        "commodity": pool.get("commodity"),
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
            "candidates_have_field_validation": False,
            "candidates_have_drilling_evidence": False,
            "candidates_have_geophysics_baseline": False,
            "evidence_is_remote_proxy_only": True,
            "scores_are_seed_signals_not_validations": True,
        },
        "weights": _WEIGHTS,
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
        f"# Trinity / Geo Discovery — Scorecard `{sc['campaign']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN scorecard.** Weighted prospectivity score computed "
        "from remote proxy axes (tectonic belt prior, commodity "
        "compatibility, aridity, terrain ruggedness, data availability, "
        "novelty penalty, uncertainty penalty). Not a deposit "
        "confirmation. Not a mineral reserve claim. Remote proxy "
        "evidence only — requires field validation before any public "
        "claim."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{sc['schema']}`")
    lines.append(f"- **Commodity**: `{sc['commodity']}`")
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
    lines.append("## Top AOIs by score")
    lines.append("")
    lines.append("| rank | id | name | region | score | confidence | hypotheses |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for rank, c in enumerate(sc["candidates"][:25], start=1):
        hyp = ", ".join(c.get("commodity_hypotheses", []))
        lines.append(
            f"| {rank} | `{c['id']}` | {c['name']} | `{c['region']}` | "
            f"{c['score']} | {c['confidence']} | {hyp} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="geo_anomaly_scorer",
        description=(
            "Score accepted geo candidate AOIs with a transparent "
            "weighted axis system. Dry-run; deterministic."
        ),
    )
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
        args.candidate_pool or "TRINITY_GEO_CANDIDATE_AOIS_global_phase1.json"
    )
    filter_path = Path(
        args.filter or "TRINITY_GEO_FILTER_global_phase1.json"
    )
    out_json = Path(args.out_json or "TRINITY_GEO_SCORECARD_global_phase1.json")
    out_md = Path(args.out_md or "TRINITY_GEO_SCORECARD_global_phase1.md")

    sc = build_scorecard(
        candidate_pool_path=pool_path,
        filter_path=filter_path,
        generated_at_utc=args.pinned_time,
    )
    out_json.write_text(canonical_dumps(sc), encoding="utf-8")
    out_md.write_text(render_markdown(sc), encoding="utf-8")

    print(f"[geo-scorer] wrote {out_json}")
    print(f"[geo-scorer] wrote {out_md}")
    print(
        f"[geo-scorer] scored: {sc['summary']['candidates_scored']}, "
        f"top score: "
        f"{sc['candidates'][0]['score'] if sc['candidates'] else 'n/a'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
