#!/usr/bin/env python3
"""
One-shot fetcher: pulls Natura 2000 polygons from OpenStreetMap via
the Overpass API and writes a GeoJSON FeatureCollection to
geaspirit/data/opportunity/natura2000/.

OSM has rich coverage of Natura 2000 sites in Spain, Portugal, France
and most of the EU, tagged either:
    boundary=protected_area + protect_title="Natura 2000"
    boundary=national_park
    leisure=nature_reserve  (sometimes)

This script asks Overpass for `boundary=protected_area` ways/relations
inside the bbox you pass (defaults to Galicia + N Portugal) and
converts the OSM 'out geom;' response into GeoJSON the
env_constraints connector can read on the next opportunity_scan run.

USE
---
    # default: Galicia + N Portugal corridor
    python3 scripts/fetch_natura2000_overpass.py

    # custom bbox: south, west, north, east
    python3 scripts/fetch_natura2000_overpass.py \\
        --bbox 36.0,-9.5,38.5,-6.0 --label faja_piritica

LICENCE
-------
OSM data → ODbL-1.0. Attribute "© OpenStreetMap contributors" when
publishing any derived material.

NOT a substitute for the official Natura 2000 dataset from the EEA or
MITECO. Use this for sprint-1 demo coverage; for any commercial report
re-validate against the authoritative source.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT   = "SOST-GeaSpirit-opportunity/0.2 (Natura2000 OSM fetcher)"
_HERE        = Path(__file__).resolve().parent
_OUT_DIR     = _HERE.parent / "data" / "opportunity" / "natura2000"


def _build_query(s, w, n, e):
    """Overpass QL: protected areas in the bbox.
    `out geom` returns inline coordinates so we don't have to resolve
    node refs ourselves. We accept any protect_title that contains
    the case-insensitive substring "natura" — covers "Natura 2000",
    "Red Natura 2000", "Natura 2000 — LIC", "Rede Natura 2000" (PT)."""
    return (
        "[out:json][timeout:120];"
        "("
        f"  way[boundary=protected_area][protect_title~'natura',i]({s},{w},{n},{e});"
        f"  relation[boundary=protected_area][protect_title~'natura',i]({s},{w},{n},{e});"
        # Also pick up parks/reserves which usually overlap with N2000
        f"  way[boundary=national_park]({s},{w},{n},{e});"
        f"  relation[boundary=national_park]({s},{w},{n},{e});"
        ");"
        "out geom;"
    )


def _post(query, timeout_s):
    data = ("data=" + urllib.parse.quote(query)).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL, data=data,
        headers={"User-Agent": USER_AGENT,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _osm_to_geojson(osm_json):
    """Convert Overpass `out geom` payload to a GeoJSON
    FeatureCollection. Each `way` becomes a Polygon; each `relation`
    with role outer/inner members becomes a MultiPolygon (very basic
    handling, not topologically perfect — enough for bbox + ray-cast
    point-in-polygon used by env_constraints)."""
    features = []
    for el in osm_json.get("elements", []):
        tags  = el.get("tags") or {}
        name  = tags.get("name") or tags.get("ref") or tags.get("protect_title") or "unnamed"
        if el["type"] == "way":
            geom = el.get("geometry") or []
            if len(geom) < 3:
                continue
            ring = [[g["lon"], g["lat"]] for g in geom]
            # close ring if open
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            features.append({
                "type": "Feature",
                "properties": {"name": name, "osm_id": el["id"], "osm_type": "way",
                               "protect_title": tags.get("protect_title", ""),
                               "boundary": tags.get("boundary", "")},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            })
        elif el["type"] == "relation":
            polys = []
            for m in el.get("members") or []:
                if m.get("type") != "way":
                    continue
                geom = m.get("geometry") or []
                if len(geom) < 3:
                    continue
                ring = [[g["lon"], g["lat"]] for g in geom]
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                polys.append([ring])
            if not polys:
                continue
            features.append({
                "type": "Feature",
                "properties": {"name": name, "osm_id": el["id"], "osm_type": "relation",
                               "protect_title": tags.get("protect_title", ""),
                               "boundary": tags.get("boundary", "")},
                "geometry": {"type": "MultiPolygon", "coordinates": polys},
            })
    return {"type": "FeatureCollection", "features": features}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Fetch Natura 2000 polygons from OSM via Overpass.")
    p.add_argument(
        "--bbox", default="41.8,-9.4,43.9,-6.7",
        help="south,west,north,east (default: Galicia + N Portugal)",
    )
    p.add_argument("--label", default="galicia_n_portugal",
                   help="short label used in the output filename.")
    p.add_argument("--timeout", type=int, default=120, help="HTTP timeout s.")
    args = p.parse_args(argv)

    try:
        s, w, n, e = (float(x) for x in args.bbox.split(","))
    except ValueError:
        print(f"ERROR: bad --bbox {args.bbox!r}", file=sys.stderr)
        return 2

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[fetch_natura2000] querying Overpass bbox=({s},{w},{n},{e}) ...")
    query = _build_query(s, w, n, e)
    try:
        osm = _post(query, args.timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        print(f"ERROR: Overpass failed: {type(err).__name__}: {err}",
              file=sys.stderr)
        return 1

    print(f"[fetch_natura2000] elements: {len(osm.get('elements', []))}")
    fc = _osm_to_geojson(osm)
    print(f"[fetch_natura2000] features: {len(fc['features'])}")

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = _OUT_DIR / f"{args.label}__{stamp}.geojson"
    out.write_text(
        json.dumps(fc, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"[fetch_natura2000] wrote {out}")
    print(f"[fetch_natura2000] LICENCE: ODbL-1.0 (OpenStreetMap contributors)")
    print(f"[fetch_natura2000] OSM coverage is not authoritative — "
          f"re-validate against EEA / MITECO before any commercial use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
