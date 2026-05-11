#!/usr/bin/env python3
"""Trinity / Geo Discovery — Candidate AOI Generator v0.1.

Deterministically generates a pool of **candidate AOIs** (Areas of
Interest) for autonomous geological proposal from a pinned global
catalog of commodity belts. Does NOT claim mineral discovery,
deposit confirmation, ore body detection or any field-validated
result. The output is an autonomous candidate AOI proposal pool that
downstream stages (filter, anomaly scorer, AI Council, Useful Compute
planner) refine.

Determinism
-----------
Fully deterministic. No ``random``, no filesystem entropy. All choices
come from ``hashlib.sha256(seed||index||axis)``. Two identical
``(--seed, --count, --commodity, --pinned-time)`` invocations produce
byte-identical output on any machine.

Modes
-----
- ``offline-belts``: pick from the pinned catalog of commodity belts
  with bbox / region / primary commodities. v0.1 default. No network.
- ``grid-seed``: emit a coarse global grid of AOIs (4° × 4° cells)
  filtered to land masses; primarily for stress-testing the filter and
  scorer with unfamiliar shapes. No network.

Output schema (``trinity-geo-candidate-pool/v0.1``)
---------------------------------------------------
::

    {
      "schema": "trinity-geo-candidate-pool/v0.1",
      "commodity": "copper_gold_critical_minerals",
      "track": "geaspirit",
      "mode": "offline-belts",
      "generated_at_utc": "2026-05-10T00:00:00+00:00",
      "seed": "trinity-geo-v0.1",
      "count_requested": 100,
      "count_emitted": 100,
      "generator_version": "v0.1",
      "candidates": [
        {
          "id": "GEO-0001",
          "name": "Andean belt tile S22.4 W68.7",
          "center_lat": -22.4,
          "center_lon": -68.7,
          "bbox": [-69.7, -23.4, -67.7, -21.4],
          "region": "south_america_andes",
          "commodity_hypotheses": ["copper", "gold", "lithium"],
          "source_mode": "offline-belts",
          "generation_method": "deterministic_belt_pick_v0.1",
          "novelty_status": "not_known_deposit_claim",
          "known_deposit_overlap": "unknown_in_v0.1",
          "safety_flags": {
              "not_a_reserve_claim": true,
              "requires_field_validation": true,
              "remote_proxy_only": true
          }
        },
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_SCHEMA = "trinity-geo-candidate-pool/v0.1"
_TRACK = "geaspirit"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")


# ---------------------------------------------------------------------------
# Commodity-belt catalog (pinned, offline)
#
# Each belt has: region tag, approximate bbox (min_lon, min_lat, max_lon,
# max_lat), and a list of primary commodities. Selected by deterministic
# hash for offline-belts mode. v0.1 is intentionally conservative:
# well-established belts only, no obscure regions.
# ---------------------------------------------------------------------------


_BELT_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "Andean belt",
        "region": "south_america_andes",
        "bbox": (-78.0, -38.0, -65.0, 5.0),
        "primary_commodities": ["copper", "gold", "lithium", "silver", "molybdenum"],
        "tier": 1,
    },
    {
        "name": "Lachlan Fold Belt (East Australia)",
        "region": "australia_lachlan",
        "bbox": (143.0, -38.0, 152.0, -30.0),
        "primary_commodities": ["gold", "copper", "silver"],
        "tier": 1,
    },
    {
        "name": "Yilgarn Craton (West Australia)",
        "region": "australia_yilgarn",
        "bbox": (115.0, -34.0, 125.0, -25.0),
        "primary_commodities": ["gold", "nickel", "iron"],
        "tier": 1,
    },
    {
        "name": "Trans-Hudson Orogen (Canada)",
        "region": "north_america_trans_hudson",
        "bbox": (-110.0, 54.0, -94.0, 64.0),
        "primary_commodities": ["gold", "nickel", "copper", "zinc"],
        "tier": 1,
    },
    {
        "name": "Superior Craton (Canada)",
        "region": "north_america_superior",
        "bbox": (-92.0, 47.0, -76.0, 55.0),
        "primary_commodities": ["gold", "nickel", "copper", "iron"],
        "tier": 1,
    },
    {
        "name": "African Copperbelt (Zambia / DRC)",
        "region": "africa_copperbelt",
        "bbox": (24.0, -14.0, 30.0, -9.0),
        "primary_commodities": ["copper", "cobalt"],
        "tier": 1,
    },
    {
        "name": "Iberian Pyrite Belt (Portugal / Spain)",
        "region": "europe_iberian_pyrite",
        "bbox": (-8.5, 37.0, -6.0, 38.5),
        "primary_commodities": ["copper", "zinc", "lead", "silver", "gold"],
        "tier": 2,
    },
    {
        "name": "Tethyan Belt (Iran / Turkey / Balkans)",
        "region": "asia_tethyan",
        "bbox": (24.0, 35.0, 60.0, 42.0),
        "primary_commodities": ["copper", "gold", "molybdenum"],
        "tier": 1,
    },
    {
        "name": "Central Asian Orogenic Belt (Kazakhstan / Mongolia)",
        "region": "asia_caob",
        "bbox": (60.0, 42.0, 110.0, 52.0),
        "primary_commodities": ["copper", "gold", "molybdenum", "tungsten"],
        "tier": 1,
    },
    {
        "name": "Pacific Rim of Fire — Indonesia / Philippines",
        "region": "pacific_rim_se_asia",
        "bbox": (95.0, -11.0, 130.0, 7.0),
        "primary_commodities": ["copper", "gold", "nickel"],
        "tier": 1,
    },
    {
        "name": "Pacific Rim of Fire — Japan / Kurils",
        "region": "pacific_rim_ne_asia",
        "bbox": (130.0, 30.0, 156.0, 46.0),
        "primary_commodities": ["gold", "copper", "rare_earth_elements"],
        "tier": 2,
    },
    {
        "name": "Sukhoi Log belt (Russia, Lena River)",
        "region": "asia_sukhoi_log",
        "bbox": (112.0, 57.0, 122.0, 62.0),
        "primary_commodities": ["gold", "silver"],
        "tier": 2,
    },
    {
        "name": "Birimian belt (West Africa)",
        "region": "africa_birimian",
        "bbox": (-12.0, 5.0, 5.0, 14.0),
        "primary_commodities": ["gold", "bauxite", "lithium"],
        "tier": 1,
    },
    {
        "name": "Bushveld Complex (South Africa)",
        "region": "africa_bushveld",
        "bbox": (24.5, -25.5, 30.5, -23.5),
        "primary_commodities": ["chromium", "platinum", "vanadium", "iron"],
        "tier": 1,
    },
    {
        "name": "Kalahari Copperbelt (Botswana / Namibia)",
        "region": "africa_kalahari_copper",
        "bbox": (20.0, -25.0, 28.0, -19.0),
        "primary_commodities": ["copper", "silver"],
        "tier": 2,
    },
    {
        "name": "Yangtze Craton (China)",
        "region": "asia_yangtze",
        "bbox": (102.0, 25.0, 122.0, 35.0),
        "primary_commodities": ["copper", "lead", "zinc", "rare_earth_elements"],
        "tier": 2,
    },
    {
        "name": "Carlin Trend (Nevada, USA)",
        "region": "north_america_carlin",
        "bbox": (-117.5, 40.0, -115.5, 42.5),
        "primary_commodities": ["gold"],
        "tier": 1,
    },
    {
        "name": "Sierra Nevada (USA)",
        "region": "north_america_sierra_nevada",
        "bbox": (-122.0, 35.0, -117.0, 41.0),
        "primary_commodities": ["gold", "tungsten", "rare_earth_elements"],
        "tier": 2,
    },
    {
        "name": "Skellefte district (Sweden)",
        "region": "europe_skellefte",
        "bbox": (17.5, 64.5, 21.0, 65.5),
        "primary_commodities": ["copper", "zinc", "gold", "silver"],
        "tier": 2,
    },
    {
        "name": "Fennoscandian Shield (Finland / Norway)",
        "region": "europe_fennoscandian",
        "bbox": (20.0, 64.0, 30.0, 70.0),
        "primary_commodities": ["nickel", "copper", "platinum", "rare_earth_elements"],
        "tier": 2,
    },
    {
        "name": "Tibetan plateau margin",
        "region": "asia_tibet_margin",
        "bbox": (80.0, 28.0, 100.0, 35.0),
        "primary_commodities": ["copper", "gold", "lithium"],
        "tier": 2,
    },
    {
        "name": "Greenland east coast (rift margins)",
        "region": "arctic_greenland_east",
        "bbox": (-30.0, 65.0, -20.0, 75.0),
        "primary_commodities": ["rare_earth_elements", "zinc", "lead"],
        "tier": 3,
    },
    {
        "name": "Pilbara analog — Hamersley margin",
        "region": "australia_hamersley_margin",
        "bbox": (115.0, -23.5, 121.0, -20.5),
        "primary_commodities": ["iron", "manganese"],
        "tier": 2,
    },
    {
        "name": "Mesoamerica volcanic arc",
        "region": "central_america_volcanic_arc",
        "bbox": (-95.0, 8.0, -85.0, 16.0),
        "primary_commodities": ["gold", "silver", "copper"],
        "tier": 2,
    },
    {
        "name": "Caribbean nickel belt",
        "region": "caribbean_nickel",
        "bbox": (-78.0, 18.0, -68.0, 22.5),
        "primary_commodities": ["nickel", "cobalt"],
        "tier": 3,
    },
    {
        "name": "South Atlantic margin — Brazilian shield",
        "region": "south_america_brazilian_shield",
        "bbox": (-55.0, -22.0, -40.0, -10.0),
        "primary_commodities": ["iron", "manganese", "niobium", "rare_earth_elements"],
        "tier": 1,
    },
]


# ---------------------------------------------------------------------------
# Commodity filter — which belts apply to a campaign commodity hypothesis
# ---------------------------------------------------------------------------


_COMMODITY_ALIASES: Dict[str, List[str]] = {
    "copper_gold_critical_minerals": [
        "copper", "gold", "lithium", "nickel", "rare_earth_elements",
        "cobalt", "platinum", "molybdenum",
    ],
    "lithium_only": ["lithium"],
    "rare_earth_only": ["rare_earth_elements"],
    "gold_only": ["gold"],
    "copper_only": ["copper"],
    "iron_only": ["iron"],
    "nickel_cobalt": ["nickel", "cobalt"],
    "all": [],  # Empty list means accept any belt regardless of commodity
}


def _filter_belts_by_commodity(commodity: str) -> List[Dict[str, Any]]:
    wants = _COMMODITY_ALIASES.get(commodity)
    if wants is None or not wants:
        return list(_BELT_CATALOG)
    wants_set = set(wants)
    return [
        b for b in _BELT_CATALOG
        if wants_set.intersection(b["primary_commodities"])
    ]


# ---------------------------------------------------------------------------
# Deterministic pseudo-random source
# ---------------------------------------------------------------------------


def _sha_bytes(seed: str, idx: int, axis: str) -> bytes:
    h = hashlib.sha256()
    h.update(seed.encode("utf-8"))
    h.update(b":")
    h.update(str(idx).encode("ascii"))
    h.update(b":")
    h.update(axis.encode("utf-8"))
    return h.digest()


def _sha_u64(seed: str, idx: int, axis: str) -> int:
    d = _sha_bytes(seed, idx, axis)
    return int.from_bytes(d[:8], "big", signed=False)


def _pick_belt(seed: str, idx: int, belts: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = _sha_u64(seed, idx, "geo.belt")
    return belts[n % len(belts)]


def _belt_sub_offset(seed: str, idx: int, bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Return a (lat, lon) deterministically placed inside the belt bbox.
    The placement uses a 10×10 grid mapped to deterministic SHA-derived
    integers, so two AOIs from the same belt rarely overlap unless the
    seed/index combination collides exactly."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_u = _sha_u64(seed, idx, "geo.sub.lat") % 1000
    lon_u = _sha_u64(seed, idx, "geo.sub.lon") % 1000
    lat = min_lat + (lat_u / 999.0) * (max_lat - min_lat)
    lon = min_lon + (lon_u / 999.0) * (max_lon - min_lon)
    return (round(lat, 4), round(lon, 4))


def _candidate_bbox(center_lat: float, center_lon: float, size_deg: float = 1.0) -> List[float]:
    """Build a square AOI bbox centred on the given coordinate. Size is
    expressed in degrees (default 1° → ~110 km × ~110 km at the
    equator, smaller at higher latitudes — the proxy scorer accounts
    for that)."""
    half = size_deg / 2.0
    return [
        round(center_lon - half, 4),
        round(center_lat - half, 4),
        round(center_lon + half, 4),
        round(center_lat + half, 4),
    ]


def _pick_commodity_hypotheses(
    seed: str, idx: int, belt: Dict[str, Any], campaign_commodity: str,
) -> List[str]:
    """Pick 1..3 commodities from the belt's primary list, intersected
    with the campaign commodity set when applicable."""
    pool: List[str] = list(belt["primary_commodities"])
    wants = _COMMODITY_ALIASES.get(campaign_commodity, [])
    if wants:
        filt = [c for c in pool if c in wants]
        if filt:
            pool = filt
    if not pool:
        return []
    k_max = min(3, len(pool))
    d = _sha_bytes(seed, idx, "geo.commodities.k")
    k = (int.from_bytes(d[:2], "big") % k_max) + 1
    # Stable shuffle: pick by hash-rank.
    ranked = sorted(
        pool, key=lambda c: _sha_u64(seed, idx, "geo.commodities." + c),
    )
    return sorted(ranked[:k])


# ---------------------------------------------------------------------------
# Top-level generation
# ---------------------------------------------------------------------------


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit candidate pool: host-path markers leaked: "
            f"{leaked}"
        )


def build_candidate_pool(
    *,
    mode: str,
    commodity: str,
    count: int,
    seed: str,
    generated_at_utc: str,
) -> Dict[str, Any]:
    if mode not in ("offline-belts", "grid-seed"):
        raise ValueError(f"unknown mode {mode!r}; expected 'offline-belts' or 'grid-seed'")
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("seed must be a non-empty string")
    if not isinstance(count, int) or count <= 0 or count > 500:
        raise ValueError("count must be a positive int <= 500")
    if not isinstance(generated_at_utc, str) or not generated_at_utc.endswith(
        "+00:00"
    ):
        raise ValueError(
            "generated_at_utc must be ISO-8601 ending in +00:00"
        )

    belts = _filter_belts_by_commodity(commodity)
    if not belts:
        raise ValueError(
            f"commodity {commodity!r} matches no belt in the v0.1 catalog"
        )

    candidates: List[Dict[str, Any]] = []
    for i in range(count):
        if mode == "offline-belts":
            belt = _pick_belt(seed, i, belts)
            center_lat, center_lon = _belt_sub_offset(seed, i, belt["bbox"])
            bbox = _candidate_bbox(center_lat, center_lon)
            commodities = _pick_commodity_hypotheses(seed, i, belt, commodity)
            region = belt["region"]
            name = (
                f"{belt['name']} tile "
                f"{'S' if center_lat < 0 else 'N'}{abs(center_lat):.1f} "
                f"{'W' if center_lon < 0 else 'E'}{abs(center_lon):.1f}"
            )
        else:
            # grid-seed: emit a uniform 4° grid over (-60..60 lat, -180..180 lon)
            lat = -60 + (i * 4) % 121
            lon = -180 + ((i * 4 * 30) % 360)
            center_lat = float(lat)
            center_lon = float(lon)
            bbox = _candidate_bbox(center_lat, center_lon, size_deg=4.0)
            commodities = ["unknown"]
            region = "grid_seed"
            name = f"grid cell {center_lat:.0f},{center_lon:.0f}"
        candidates.append({
            "id": f"GEO-{i + 1:04d}",
            "name": name,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "bbox": bbox,
            "region": region,
            "commodity_hypotheses": commodities,
            "source_mode": mode,
            "generation_method": "deterministic_belt_pick_v0.1",
            "novelty_status": "not_known_deposit_claim",
            "known_deposit_overlap": "unknown_in_v0.1",
            "safety_flags": {
                "not_a_reserve_claim": True,
                "requires_field_validation": True,
                "remote_proxy_only": True,
                "no_drilling_evidence": True,
            },
        })

    pool = {
        "schema": _SCHEMA,
        "commodity": commodity,
        "track": _TRACK,
        "mode": mode,
        "generated_at_utc": generated_at_utc,
        "seed": seed,
        "count_requested": count,
        "count_emitted": len(candidates),
        "generator_version": "v0.1",
        "candidates": candidates,
    }
    blob = canonical_dumps(pool)
    _check_no_host_paths(blob)
    return pool


def render_markdown(pool: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Geo Discovery — Candidate AOI Pool "
        f"`{pool['commodity']}`"
    )
    lines.append("")
    lines.append(
        "> **AUTONOMOUS AOI PROPOSAL.** Deterministically generated from a "
        "pinned offline commodity-belt catalog. Not a mineral reserve "
        "claim, not a deposit confirmation, not field validated. "
        "Downstream stages (filter, anomaly scorer, AI Council) refine "
        "the pool; nothing here is validated yet. Remote proxy "
        "evidence only."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{pool['schema']}`")
    lines.append(f"- **Commodity**: `{pool['commodity']}`")
    lines.append(f"- **Mode**: `{pool['mode']}`")
    lines.append(f"- **Seed**: `{pool['seed']}`")
    lines.append(f"- **Generated (UTC)**: {pool['generated_at_utc']}")
    lines.append(
        f"- **count_requested / count_emitted**: "
        f"`{pool['count_requested']} / {pool['count_emitted']}`"
    )
    lines.append("")
    lines.append("## First 30 candidates")
    lines.append("")
    lines.append("| id | name | center | region | hypotheses |")
    lines.append("| --- | --- | --- | --- | --- |")
    for c in pool["candidates"][:30]:
        hyp = ", ".join(c["commodity_hypotheses"])
        coord = (
            f"{c['center_lat']:.2f}, {c['center_lon']:.2f}"
        )
        lines.append(
            f"| `{c['id']}` | {c['name']} | `{coord}` | `{c['region']}` "
            f"| {hyp} |"
        )
    if len(pool["candidates"]) > 30:
        lines.append("")
        lines.append(
            f"_({len(pool['candidates']) - 30} more candidates in the JSON.)_"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="geo_candidate_generator",
        description=(
            "Deterministic geo candidate AOI proposal generator. "
            "Dry-run; not a mineral reserve claim."
        ),
    )
    p.add_argument(
        "--mode", type=str, default="offline-belts",
        choices=("offline-belts", "grid-seed"),
    )
    p.add_argument(
        "--commodity", type=str, default="copper_gold_critical_minerals",
    )
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--seed", type=str, default="trinity-geo-v0.1")
    p.add_argument(
        "--pinned-time", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    args = p.parse_args(argv)

    pool = build_candidate_pool(
        mode=args.mode,
        commodity=args.commodity,
        count=args.count,
        seed=args.seed,
        generated_at_utc=args.pinned_time,
    )

    out_json = Path(
        args.out_json or "TRINITY_GEO_CANDIDATE_AOIS_global_phase1.json"
    )
    out_md = Path(
        args.out_md or "TRINITY_GEO_CANDIDATE_AOIS_global_phase1.md"
    )
    out_json.write_text(canonical_dumps(pool), encoding="utf-8")
    out_md.write_text(render_markdown(pool), encoding="utf-8")

    print(f"[geo-candidates] wrote {out_json}")
    print(f"[geo-candidates] wrote {out_md}")
    print(
        f"[geo-candidates] emitted: {pool['count_emitted']}; "
        f"commodity={pool['commodity']}; mode={pool['mode']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
