#!/usr/bin/env python3
"""Trinity / Geo Discovery — Candidate AOI filter v0.1.

Reads a candidate pool produced by ``geo_candidate_generator.py`` and
removes (or flags) AOIs that fail a closed set of transparent geo
rules. Output is a *filtered* pool with per-AOI ``filter_verdict``
(``accept`` / ``reject`` / ``flag``) and a closed list of
``reason_codes``.

Hard rules
----------
- **Coordinate validity.** Reject if ``lat ∉ [-90, 90]`` or ``lon ∉
  [-180, 180]`` (off-globe).
- **Duplicate / overlapping bboxes.** Reject every candidate whose
  bbox overlaps with a previously-accepted one by more than 50% of
  its own area.
- **Known-demo AOI proximity.** Reject candidates whose center sits
  within ~3° of a known v0 demo AOI (Kalgoorlie, Pilbara, Zambia
  Copperbelt). v0 demo AOIs are reserved for the Earth Track
  reference and excluded from autonomous v0.1.
- **Low evidence.** Reject candidates with zero ``commodity_hypotheses``
  (the campaign commodity filter left them with no plausible
  primary). They have nothing the AI Council could review.
- **Protected / legally-unknown area.** v0.1 ships a small offline
  list of polar / UNESCO / nationally-protected bboxes; candidates
  whose center falls inside one are **flagged** ``needs_operator_
  review`` rather than rejected. The dossier will surface that flag
  so an operator can clear it manually.

The filter is **transparent**: every reject / flag carries the exact
reason code that triggered it.

Invariants
----------
- Deterministic given the same input pool and the same flag set.
- Pure stdlib.
- No network, no subprocess, no broadcast surface.
- Canonical JSON. No host-path leak.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


_INPUT_SCHEMA = "trinity-geo-candidate-pool/v0.1"
_OUTPUT_SCHEMA = "trinity-geo-candidate-filter/v0.1"
_TRACK = "geaspirit"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")


# Demo AOIs reserved for the Earth Track v0 reference. Stored as
# (center_lat, center_lon) so we can do a Haversine-light proximity
# check (we use a degrees-only Euclidean approximation; for v0.1 that
# is enough to keep autonomous candidates clear of known demos).
_KNOWN_DEMO_AOIS: List[Dict[str, Any]] = [
    {
        "name": "Kalgoorlie (Phase 1 demo)",
        "center_lat": -30.75,
        "center_lon": 121.47,
        "exclusion_radius_deg": 3.0,
    },
    {
        "name": "Pilbara (reserved for future demo)",
        "center_lat": -21.0,
        "center_lon": 118.0,
        "exclusion_radius_deg": 3.5,
    },
    {
        "name": "Zambia Copperbelt (reserved for future demo)",
        "center_lat": -12.5,
        "center_lon": 27.5,
        "exclusion_radius_deg": 2.5,
    },
]


# Protected / legally-uncertain regions. v0.1 ships a small pinned
# list; expanding this is on the v0.2 backlog. Each entry is
# (min_lon, min_lat, max_lon, max_lat).
_PROTECTED_BBOXES: List[Dict[str, Any]] = [
    {
        "name": "Antarctica (Antarctic Treaty area)",
        "bbox": (-180.0, -90.0, 180.0, -60.0),
    },
    {
        "name": "High Arctic (legal uncertainty zone)",
        "bbox": (-180.0, 80.0, 180.0, 90.0),
    },
    {
        "name": "Galapagos Marine Reserve",
        "bbox": (-92.0, -2.0, -89.0, 1.5),
    },
    {
        "name": "Yellowstone National Park (USA)",
        "bbox": (-111.2, 44.1, -109.8, 45.1),
    },
    {
        "name": "Banff / Jasper National Parks (Canada)",
        "bbox": (-118.5, 51.0, -114.5, 53.5),
    },
    {
        "name": "Kakadu National Park (Australia)",
        "bbox": (132.0, -13.5, 133.5, -11.8),
    },
    {
        "name": "Serengeti / Maasai Mara (Tanzania / Kenya)",
        "bbox": (33.5, -3.5, 36.5, -1.0),
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
            f"refusing to emit filtered pool: host-path markers leaked: "
            f"{leaked}"
        )


def _bbox_overlap_fraction(a: List[float], b: List[float]) -> float:
    """Return the fraction of bbox ``a``'s area covered by bbox ``b``
    (0.0 = no overlap, 1.0 = a fully inside b). Both bboxes are
    [min_lon, min_lat, max_lon, max_lat]. Degenerate boxes return 0."""
    a_min_lon, a_min_lat, a_max_lon, a_max_lat = a
    b_min_lon, b_min_lat, b_max_lon, b_max_lat = b
    inter_min_lon = max(a_min_lon, b_min_lon)
    inter_min_lat = max(a_min_lat, b_min_lat)
    inter_max_lon = min(a_max_lon, b_max_lon)
    inter_max_lat = min(a_max_lat, b_max_lat)
    if inter_max_lon <= inter_min_lon or inter_max_lat <= inter_min_lat:
        return 0.0
    inter_area = (inter_max_lon - inter_min_lon) * (inter_max_lat - inter_min_lat)
    a_area = max(1e-9, (a_max_lon - a_min_lon) * (a_max_lat - a_min_lat))
    return min(1.0, max(0.0, inter_area / a_area))


def _is_in_protected(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    for p in _PROTECTED_BBOXES:
        min_lon, min_lat, max_lon, max_lat = p["bbox"]
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return p
    return None


def _near_demo_aoi(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    for d in _KNOWN_DEMO_AOIS:
        dlat = abs(lat - d["center_lat"])
        dlon = abs(lon - d["center_lon"])
        # Wrap dlon in [-180, 180] handling
        if dlon > 180:
            dlon = 360 - dlon
        if dlat <= d["exclusion_radius_deg"] and dlon <= d["exclusion_radius_deg"]:
            return d
    return None


def _evaluate_candidate(
    c: Mapping[str, Any],
    accepted_bboxes: List[List[float]],
) -> Dict[str, Any]:
    reasons: List[str] = []
    flags: List[str] = []
    verdict = "accept"

    lat = c.get("center_lat")
    lon = c.get("center_lon")
    bbox = c.get("bbox")
    region = c.get("region", "")
    commodities = list(c.get("commodity_hypotheses") or [])

    # Coordinate validity
    if (
        not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
        or lat < -90 or lat > 90 or lon < -180 or lon > 180
    ):
        verdict = "reject"
        reasons.append(
            f"invalid_coordinates:lat={lat!r},lon={lon!r}"
        )

    # bbox shape validity
    if (
        not isinstance(bbox, list) or len(bbox) != 4
        or any(not isinstance(v, (int, float)) for v in bbox)
        or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]
    ):
        if verdict != "reject":
            verdict = "reject"
        reasons.append(f"invalid_bbox:{bbox!r}")

    # Known-demo proximity (only checked if coords are valid)
    if verdict == "accept" and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        near = _near_demo_aoi(float(lat), float(lon))
        if near is not None:
            verdict = "reject"
            reasons.append(f"near_known_demo_aoi:{near['name']!r}")

    # Low evidence (zero plausible commodities after upstream filtering)
    if verdict == "accept" and not commodities:
        verdict = "reject"
        reasons.append("low_evidence:no_commodity_hypotheses_after_filter")

    # Duplicate / overlap with previously accepted bbox
    if verdict == "accept" and isinstance(bbox, list) and len(bbox) == 4:
        for prev in accepted_bboxes:
            ov = _bbox_overlap_fraction(list(bbox), prev)
            if ov > 0.50:
                verdict = "reject"
                reasons.append(
                    f"overlap_with_previously_accepted:fraction={ov:.2f}"
                )
                break

    # Protected / legally-unknown area → FLAG (not reject)
    if (
        isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        and verdict == "accept"
    ):
        prot = _is_in_protected(float(lat), float(lon))
        if prot is not None:
            flags.append(
                f"needs_operator_review:protected_area:{prot['name']!r}"
            )

    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "center_lat": lat,
        "center_lon": lon,
        "region": region,
        "filter_verdict": verdict,
        "reason_codes": reasons,
        "filter_flags": flags,
    }


def build_filtered_pool(
    *,
    candidate_pool_path: Path,
    generated_at_utc: str,
) -> Dict[str, Any]:
    if not candidate_pool_path.exists():
        raise FileNotFoundError(
            f"candidate pool not found: {candidate_pool_path}"
        )
    raw = candidate_pool_path.read_bytes()
    pool = json.loads(raw.decode("utf-8"))
    if pool.get("schema") != _INPUT_SCHEMA:
        raise ValueError(
            f"input schema must be {_INPUT_SCHEMA!r}; got "
            f"{pool.get('schema')!r}"
        )
    if pool.get("track") != _TRACK:
        raise ValueError("input pool is not a geaspirit-track pool")

    pool_sha = hashlib.sha256(raw).hexdigest()
    decisions: List[Dict[str, Any]] = []
    accepted_bboxes: List[List[float]] = []
    counts = {"accept": 0, "reject": 0, "flag": 0}

    for c in pool.get("candidates", []):
        decision = _evaluate_candidate(c, accepted_bboxes)
        counts[decision["filter_verdict"]] = counts.get(
            decision["filter_verdict"], 0
        ) + 1
        if (
            decision["filter_verdict"] == "accept"
            and decision["filter_flags"]
        ):
            counts["flag"] = counts.get("flag", 0) + 1
        if decision["filter_verdict"] == "accept":
            bb = c.get("bbox")
            if isinstance(bb, list) and len(bb) == 4:
                accepted_bboxes.append(list(bb))
        decisions.append(decision)

    filtered = {
        "schema": _OUTPUT_SCHEMA,
        "commodity": pool.get("commodity"),
        "track": _TRACK,
        "mode": pool.get("mode"),
        "generated_at_utc": generated_at_utc,
        "source": {
            "candidate_pool_basename": candidate_pool_path.name,
            "candidate_pool_sha256": pool_sha,
            "seed": pool.get("seed"),
            "count_input": len(pool.get("candidates", [])),
        },
        "decisions": decisions,
        "summary": {
            "accept": counts.get("accept", 0),
            "reject": counts.get("reject", 0),
            "flag": counts.get("flag", 0),
        },
    }
    blob = canonical_dumps(filtered)
    _check_no_host_paths(blob)
    return filtered


def render_markdown(filtered: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Geo Discovery — AOI Filter "
        f"`{filtered['commodity']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN geo filter.** Closed rules: coordinate validity, "
        "demo-AOI proximity, zero-commodity rejection, bbox-overlap "
        "deduplication, protected-area flag. Not a mineral reserve "
        "claim and not a deposit confirmation."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{filtered['schema']}`")
    lines.append(f"- **Commodity**: `{filtered['commodity']}`")
    lines.append(f"- **Mode**: `{filtered['mode']}`")
    lines.append(f"- **Generated (UTC)**: {filtered['generated_at_utc']}")
    s = filtered["summary"]
    lines.append(
        f"- **Summary**: accept=`{s['accept']}`, reject=`{s['reject']}`,"
        f" flag=`{s['flag']}`"
    )
    lines.append("")
    lines.append("## Decisions (first 30)")
    lines.append("")
    lines.append("| id | name | center | verdict | reasons | flags |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for d in filtered["decisions"][:30]:
        reasons = "; ".join(d["reason_codes"]) or "—"
        flags = "; ".join(d["filter_flags"]) or "—"
        clat = d.get("center_lat")
        clon = d.get("center_lon")
        coord = (
            f"{clat:.2f}, {clon:.2f}"
            if isinstance(clat, (int, float)) and isinstance(clon, (int, float))
            else "—"
        )
        lines.append(
            f"| `{d['id']}` | {d['name']} | `{coord}` | "
            f"**{d['filter_verdict']}** | {reasons} | {flags} |"
        )
    if len(filtered["decisions"]) > 30:
        lines.append("")
        lines.append(
            f"_({len(filtered['decisions']) - 30} more decisions in the JSON.)_"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="geo_candidate_filter",
        description=(
            "Apply transparent geo filter rules to a candidate AOI pool. "
            "Dry-run; deterministic."
        ),
    )
    p.add_argument(
        "--candidate-pool", type=str, default=None,
        help=(
            "Path to TRINITY_GEO_CANDIDATE_AOIS_global_phase1.json"
        ),
    )
    p.add_argument(
        "--pinned-time", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    args = p.parse_args(argv)

    pool_path = Path(
        args.candidate_pool
        or "TRINITY_GEO_CANDIDATE_AOIS_global_phase1.json"
    )
    out_json = Path(args.out_json or "TRINITY_GEO_FILTER_global_phase1.json")
    out_md = Path(args.out_md or "TRINITY_GEO_FILTER_global_phase1.md")

    filtered = build_filtered_pool(
        candidate_pool_path=pool_path,
        generated_at_utc=args.pinned_time,
    )
    out_json.write_text(canonical_dumps(filtered), encoding="utf-8")
    out_md.write_text(render_markdown(filtered), encoding="utf-8")

    s = filtered["summary"]
    print(f"[geo-filter] wrote {out_json}")
    print(f"[geo-filter] wrote {out_md}")
    print(
        f"[geo-filter] accept={s['accept']}, reject={s['reject']}, "
        f"flag={s['flag']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
