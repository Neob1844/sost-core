#!/usr/bin/env python3
"""
opportunity_scan — CLI entry for the GeaSpirit opportunity pipeline.

Two ways to specify the AOI:

    # 1) Pass an AOI JSON file (see geaspirit/data/opportunity/samples/)
    python3 scripts/opportunity_scan.py \
        --aoi-file geaspirit/data/opportunity/samples/galicia_wsn_aoi.json

    # 2) Pass the fields directly on the command line
    python3 scripts/opportunity_scan.py \
        --name "Galicia W-Sn" --lat 42.6364 --lon -8.3486 \
        --radius-km 30 --country ES --metals W,Sn

The CLI:
  * runs every default connector (osm_logistics, env_constraints,
    tailings_portal) against the AOI
  * prints a short human summary to stdout
  * writes the full canonical-JSON scorecard to
    geaspirit/data/opportunity/results/<aoi-slug>__<UTC>.json
  * prints the SHA-256 of the canonical form — that's the hex digest
    you'd anchor on chain via the SOST Protocol Registry

NEVER touches the SOST consensus code. NEVER contacts a concession
holder. Output is a desk-validation candidate, NOT a resource estimate.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

# Make the geaspirit/ package importable when invoked from the scripts/
# directory (mirrors the pattern used by the other scripts in this dir).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geaspirit.opportunity import (
    AOI, score_opportunity, canonical_json, sha256_of_canonical,
)
from geaspirit.opportunity.canonical import pretty_json


_RESULTS_DIR = (Path(__file__).resolve().parent.parent
                / "data" / "opportunity" / "results")


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "aoi"


def _load_aoi_from_file(path: Path) -> AOI:
    with path.open("r", encoding="utf-8") as fh:
        d = json.load(fh)
    metals = d.get("metals_of_interest") or []
    return AOI(
        name=d["name"],
        lat=float(d["lat"]),
        lon=float(d["lon"]),
        radius_km=float(d["radius_km"]),
        country=d.get("country", ""),
        metals_of_interest=tuple(str(m) for m in metals),
        notes=d.get("notes", ""),
    )


def _aoi_from_args(a: argparse.Namespace) -> AOI:
    if a.aoi_file:
        return _load_aoi_from_file(Path(a.aoi_file))
    if a.name is None or a.lat is None or a.lon is None or a.radius_km is None:
        raise SystemExit(
            "ERROR: either --aoi-file OR (--name --lat --lon --radius-km) are required"
        )
    metals = tuple(m.strip() for m in (a.metals or "").split(",") if m.strip())
    return AOI(
        name=a.name, lat=a.lat, lon=a.lon, radius_km=a.radius_km,
        country=a.country or "", metals_of_interest=metals, notes=a.notes or "",
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="GeaSpirit opportunity scan — Sprint 1 CLI")
    p.add_argument("--aoi-file", help="Path to an AOI JSON file.")
    p.add_argument("--name", help="AOI display name.")
    p.add_argument("--lat", type=float, help="AOI centre latitude (WGS84).")
    p.add_argument("--lon", type=float, help="AOI centre longitude (WGS84).")
    p.add_argument("--radius-km", type=float, help="AOI search radius in km.")
    p.add_argument("--country", help="ISO 3166-1 alpha-2 (optional).")
    p.add_argument("--metals", help="Comma-separated metals, e.g. W,Sn,Cu.")
    p.add_argument("--notes", help="Free-text AOI note (avoid forbidden terms).")
    p.add_argument("--out-dir", help="Override results output directory.")
    p.add_argument("--no-write", action="store_true",
                   help="Print only; do not write JSON file.")
    args = p.parse_args(argv)

    aoi = _aoi_from_args(args)

    print(f"[opportunity_scan] AOI: {aoi.name} "
          f"({aoi.lat:.4f}, {aoi.lon:.4f}) r={aoi.radius_km} km "
          f"metals={','.join(aoi.metals_of_interest) or '-'}")
    print(f"[opportunity_scan] running connectors ...")

    sc = score_opportunity(aoi)

    print()
    print(f"  SCORE:        {sc.score} / 100   ({sc.class_grade})")
    print(f"  EVIDENCE:     {', '.join(sc.evidence_tags) or '(none)'}")
    print()
    print(f"  THESIS:       {sc.thesis}")
    print()
    print(f"  NEXT STEP:    {sc.next_step}")
    print()
    print(f"  CONNECTORS:")
    for r in sc.connector_results:
        head = f"    - {r.connector:24s} {r.status:8s}"
        if r.status in ("error", "skipped") and r.error_message:
            head += f"   ({r.error_message[:80]})"
        print(head)

    digest = sha256_of_canonical(sc)
    print()
    print(f"  CANONICAL SHA-256:  {digest}")
    print(f"  → use this digest in a Protocol Registry capsule to anchor "
          f"this scorecard on chain.")

    if not args.no_write:
        out_dir = Path(args.out_dir) if args.out_dir else _RESULTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"{_slug(aoi.name)}__{stamp}.json"
        path.write_bytes(canonical_json(sc))
        # Also drop a pretty version for human reading.
        pretty_path = path.with_suffix(".pretty.json")
        pretty_path.write_text(pretty_json(sc), encoding="utf-8")
        print()
        print(f"  WROTE canonical:    {path}")
        print(f"  WROTE pretty:       {pretty_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
