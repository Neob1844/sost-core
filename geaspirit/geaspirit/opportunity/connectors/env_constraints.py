"""
Environmental constraint connector — checks whether the AOI overlaps a
known protected area (Natura 2000, national park, etc.).

Sprint 1 takes a LOCAL GeoJSON file path. Real Natura 2000 data lives
at the European Environment Agency:
  https://www.eea.europa.eu/en/datahub/datahubitem-view/6fc8ad2d-...
The operator downloads the GeoJSON / shapefile once, drops it under
geaspirit/data/opportunity/natura2000/, and this connector indexes
it on first call.

If no GeoJSON is found we return status="skipped" with a clear note
and the orchestrator applies a "data uncertainty" penalty instead.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path
from typing import List, Optional, Tuple

from ..contracts import AOI, ConnectorResult, Evidence


CONNECTOR_NAME = "env_constraints"
_HERE = Path(__file__).resolve().parent
_DATA_ROOT = _HERE.parent.parent.parent / "data" / "opportunity" / "natura2000"


# -----------------------------------------------------------------------
# Light geo math (no shapely)
# -----------------------------------------------------------------------

def _bbox_of_ring(ring: List[List[float]]) -> Tuple[float, float, float, float]:
    """Return (minlon, minlat, maxlon, maxlat) for a GeoJSON linear ring."""
    minlon = min(p[0] for p in ring); maxlon = max(p[0] for p in ring)
    minlat = min(p[1] for p in ring); maxlat = max(p[1] for p in ring)
    return (minlon, minlat, maxlon, maxlat)


def _bbox_intersects(
    bbox: Tuple[float,float,float,float],
    aoi_lat: float, aoi_lon: float, aoi_radius_km: float,
) -> bool:
    """Does the AOI bounding-box (lat±radius, lon±radius_scaled)
    intersect the protected-area bounding box?"""
    dlat = aoi_radius_km / 111.32
    dlon = aoi_radius_km / max(0.0001, 111.32 * math.cos(math.radians(aoi_lat)))
    aoi_box = (aoi_lon - dlon, aoi_lat - dlat, aoi_lon + dlon, aoi_lat + dlat)
    return not (
        aoi_box[2] < bbox[0] or aoi_box[0] > bbox[2] or
        aoi_box[3] < bbox[1] or aoi_box[1] > bbox[3]
    )


def _point_in_ring(lat: float, lon: float, ring: List[List[float]]) -> bool:
    """Standard ray-casting. ring is GeoJSON [[lon,lat], ...] closed."""
    inside = False
    n = len(ring)
    if n < 4:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersect = ((yi > lat) != (yj > lat)) and \
                    (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-18) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


# -----------------------------------------------------------------------
# Load + query
# -----------------------------------------------------------------------

def _find_geojson() -> Optional[Path]:
    if not _DATA_ROOT.exists():
        return None
    for p in sorted(_DATA_ROOT.glob("*.geojson")) + sorted(_DATA_ROOT.glob("*.json")):
        if p.is_file():
            return p
    return None


def _iter_polygons(features: list):
    """Yield (name, polygon_coords) for every Polygon / MultiPolygon
    feature. polygon_coords is a list of rings — outer ring first."""
    for feat in features:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        name = (props.get("SITENAME") or props.get("name") or
                props.get("NAME") or props.get("site_name") or
                "(unnamed protected area)")
        t = geom.get("type")
        coords = geom.get("coordinates") or []
        if t == "Polygon":
            yield (name, coords)
        elif t == "MultiPolygon":
            for poly in coords:
                yield (name, poly)


def query(aoi: AOI) -> ConnectorResult:
    fetched_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    geojson_path = _find_geojson()
    if geojson_path is None:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="skipped",
            fetched_at=fetched_at,
            error_message=(
                "no Natura 2000 / protected-area GeoJSON found under "
                f"{_DATA_ROOT}. Download from the EEA datahub and place "
                "the file there to enable environmental constraint checks."
            ),
        )

    try:
        with geojson_path.open("r", encoding="utf-8") as fh:
            gj = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="error",
            fetched_at=fetched_at,
            error_message=f"could not parse {geojson_path.name}: {e}",
        )

    features = gj.get("features", []) if isinstance(gj, dict) else []
    hits = []
    for name, rings in _iter_polygons(features):
        if not rings:
            continue
        outer = rings[0]
        bbox = _bbox_of_ring(outer)
        if not _bbox_intersects(bbox, aoi.lat, aoi.lon, aoi.radius_km):
            continue
        inside = _point_in_ring(aoi.lat, aoi.lon, outer)
        hits.append({"name": name, "center_inside_polygon": bool(inside),
                     "bbox": [round(x, 4) for x in bbox]})

    if not hits:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="ok",
            evidence=(Evidence(
                tag="environmental_clear",
                source=f"local GeoJSON: {geojson_path.name}",
                fetched_at=fetched_at,
                confidence=0.6,
                license="see source dataset terms",
                notes="AOI does not intersect any protected-area polygon in "
                      "the supplied GeoJSON. Field verification still required.",
            ),),
            fetched_at=fetched_at,
        )

    # If center is inside any polygon → high risk; otherwise medium.
    center_in = any(h["center_inside_polygon"] for h in hits)
    return ConnectorResult(
        connector=CONNECTOR_NAME,
        status="ok",
        evidence=(Evidence(
            tag=("environmental_risk_high" if center_in
                 else "environmental_risk_medium"),
            source=f"local GeoJSON: {geojson_path.name}",
            fetched_at=fetched_at,
            confidence=0.8 if center_in else 0.6,
            license="see source dataset terms",
            notes=(
                f"AOI intersects {len(hits)} protected-area polygon"
                f"{'s' if len(hits)>1 else ''}. "
                + ("AOI center falls INSIDE at least one polygon — assume "
                   "permitting is restrictive. " if center_in else
                   "AOI center is outside the polygons but the search "
                   "radius overlaps. ")
                + "Legal review required before any field work."
            ),
            data={"hits": hits[:8]},
        ),),
        fetched_at=fetched_at,
    )
