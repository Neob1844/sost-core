"""
OSM logistics connector — distance from AOI center to nearest road,
railway and port via the public Overpass API.

Free, no auth, ODbL-1.0 licensed. We cache responses for 7 days by
default so re-running the orchestrator doesn't hit Overpass on every
invocation.

For sprint 1 we only fetch features in a bounding box around the AOI
center and compute haversine distances in Python. Coarse but enough
to populate logistics evidence.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import urllib.error
import urllib.request
from typing import Optional, Tuple

from ..cache import cache_get, cache_put
from ..contracts import AOI, ConnectorResult, Evidence


CONNECTOR_NAME = "osm_logistics"
OVERPASS_URL   = "https://overpass-api.de/api/interpreter"
DEFAULT_TIMEOUT_S = 25
DEFAULT_CACHE_TTL = 7 * 24 * 3600       # 7 days
USER_AGENT = "SOST-GeaSpirit-opportunity/0.1 (https://sostcore.com)"


# -----------------------------------------------------------------------
# Geo helpers (stdlib only)
# -----------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def _bbox_for(lat: float, lon: float, radius_km: float) -> Tuple[float,float,float,float]:
    """Rough lat/lon bounding box. Good enough for Overpass queries.
    Returns (south, west, north, east)."""
    dlat = radius_km / 111.32
    dlon = radius_km / max(0.0001, 111.32 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


# -----------------------------------------------------------------------
# Overpass call
# -----------------------------------------------------------------------

def _build_overpass_query(bbox: Tuple[float,float,float,float]) -> str:
    s, w, n, e = bbox
    box = f"({s},{w},{n},{e})"
    # Compact QL: major roads, railways, ports/harbours, primary airports.
    return (
        "[out:json][timeout:20];"
        "("
          f"way['highway'~'^(motorway|trunk|primary|secondary)$']{box};"
          f"way['railway'='rail']{box};"
          f"node['harbour'='yes']{box};"
          f"way['harbour'='yes']{box};"
          f"node['aeroway'='aerodrome']{box};"
        ");"
        "out center;"
    )


def _post_overpass(query: str, timeout_s: int) -> dict:
    data = ("data=" + urllib.parse.quote(query)).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={"User-Agent": USER_AGENT,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


# urllib.parse imported lazily to keep cold-start surface small
import urllib.parse                                  # noqa: E402


# -----------------------------------------------------------------------
# Distance reduction from Overpass elements
# -----------------------------------------------------------------------

def _nearest_distance(
    elements: list,
    aoi_lat: float,
    aoi_lon: float,
    predicate,
) -> Optional[float]:
    best: Optional[float] = None
    for el in elements:
        if not predicate(el):
            continue
        # ways come back with `center` (because of "out center")
        if "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        elif "lat" in el and "lon" in el:
            lat, lon = el["lat"], el["lon"]
        else:
            continue
        d = _haversine_km(aoi_lat, aoi_lon, lat, lon)
        if best is None or d < best:
            best = d
    return best


def _is_road(el: dict)    -> bool: return el.get("tags", {}).get("highway") in {"motorway","trunk","primary","secondary"}
def _is_rail(el: dict)    -> bool: return el.get("tags", {}).get("railway") == "rail"
def _is_harbour(el: dict) -> bool: return el.get("tags", {}).get("harbour") == "yes"
def _is_airport(el: dict) -> bool: return el.get("tags", {}).get("aeroway") == "aerodrome"


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

def query(
    aoi: AOI,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    cache_ttl_s: int = DEFAULT_CACHE_TTL,
    use_cache: bool = True,
) -> ConnectorResult:
    """Look up logistics features around `aoi` via Overpass. Returns a
    ConnectorResult with one Evidence per feature class hit."""
    fetched_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache_args = {"lat": round(aoi.lat, 4),
                  "lon": round(aoi.lon, 4),
                  "r":   round(aoi.radius_km, 1)}

    payload = None
    status = "ok"
    if use_cache:
        payload = cache_get(CONNECTOR_NAME, cache_args, cache_ttl_s)
        if payload is not None:
            status = "cache"

    if payload is None:
        bbox = _bbox_for(aoi.lat, aoi.lon, aoi.radius_km)
        try:
            payload = _post_overpass(_build_overpass_query(bbox), timeout_s)
            cache_put(CONNECTOR_NAME, cache_args, payload)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            return ConnectorResult(
                connector=CONNECTOR_NAME,
                status="error",
                fetched_at=fetched_at,
                error_message=f"overpass call failed: {type(e).__name__}: {e}",
            )
        except json.JSONDecodeError as e:
            return ConnectorResult(
                connector=CONNECTOR_NAME,
                status="error",
                fetched_at=fetched_at,
                error_message=f"overpass returned non-JSON: {e}",
            )

    elements = payload.get("elements", []) if isinstance(payload, dict) else []
    road_d    = _nearest_distance(elements, aoi.lat, aoi.lon, _is_road)
    rail_d    = _nearest_distance(elements, aoi.lat, aoi.lon, _is_rail)
    harbour_d = _nearest_distance(elements, aoi.lat, aoi.lon, _is_harbour)
    airport_d = _nearest_distance(elements, aoi.lat, aoi.lon, _is_airport)

    evidence = []
    if road_d is not None:
        evidence.append(Evidence(
            tag="nearby_road_access",
            source="OpenStreetMap (Overpass)",
            fetched_at=fetched_at,
            confidence=0.85,
            license="ODbL-1.0",
            notes=f"Nearest major road ~{road_d:.1f} km from AOI center.",
            data={"distance_km": round(road_d, 2)},
        ))
    if rail_d is not None:
        evidence.append(Evidence(
            tag="nearby_railway",
            source="OpenStreetMap (Overpass)",
            fetched_at=fetched_at,
            confidence=0.85,
            license="ODbL-1.0",
            notes=f"Nearest railway line ~{rail_d:.1f} km from AOI center.",
            data={"distance_km": round(rail_d, 2)},
        ))
    if harbour_d is not None:
        evidence.append(Evidence(
            tag="nearby_port",
            source="OpenStreetMap (Overpass)",
            fetched_at=fetched_at,
            confidence=0.75,
            license="ODbL-1.0",
            notes=f"Nearest harbour ~{harbour_d:.1f} km from AOI center.",
            data={"distance_km": round(harbour_d, 2)},
        ))
    if airport_d is not None:
        evidence.append(Evidence(
            tag="nearby_airport",
            source="OpenStreetMap (Overpass)",
            fetched_at=fetched_at,
            confidence=0.7,
            license="ODbL-1.0",
            notes=f"Nearest airport ~{airport_d:.1f} km from AOI center.",
            data={"distance_km": round(airport_d, 2)},
        ))

    return ConnectorResult(
        connector=CONNECTOR_NAME,
        status=status,
        evidence=tuple(evidence),
        fetched_at=fetched_at,
    )
