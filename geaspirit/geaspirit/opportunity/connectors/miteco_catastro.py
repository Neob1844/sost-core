"""
MITECO Catastro Minero connector — legal title chain for Spanish AOIs.

Three import modes (decreasing robustness, all read from disk):

  1. official_wfs           : a separate one-shot fetcher script
                              (scripts/fetch_miteco_wfs.py) hits the official
                              WFS / download endpoint when it is up and
                              drops a GeoJSON FeatureCollection in this
                              directory. The connector itself only reads
                              files — it never calls the network at scan
                              time. This keeps `score_opportunity()`
                              deterministic and offline-safe.
  2. visor_geojson          : operator opens the MITECO Catastro Minero
                              visor (https://geoportal.minetur.gob.es/
                              CatastroMinero/), draws / selects rights for
                              the AOI, exports as GeoJSON/SHP/KMZ, drops
                              the GeoJSON in this directory. (KMZ/SHP need
                              to be converted first — out of scope for
                              Sprint 2.1; document only.)
  3. operator_pasted_json   : operator manually transcribes a small
                              number of rights from the visor into our
                              own MitecoRecord JSON schema. Lowest
                              throughput, highest control, useful when
                              the operator wants to redact holder
                              identities before any internal sharing.

All three modes converge to a normalised internal Record dict.
The connector emits at most ONE primary Evidence per AOI, tagged with
the most blocking title_status across all in-radius hits, and carries
the full per-hit list in Evidence.data['hits'].

Title-status → Evidence.tag mapping (consumed by orchestrator):

  Internal status         | Evidence.tag                      | legal subscore band
  ------------------------+-----------------------------------+--------------------
  active_clear            | title_clear                       | 80
  active                  | title_active_or_pending           | 70
  cancelled               | title_cancelled                   | 75
  expired                 | title_expired                     | 72  (reactivation)
  pending_request         | title_pending_request             | 55
  active_third_party      | title_active_by_third_party       | 55  (partnership)
  conflicting             | title_conflicting                 | 30  (commercial penalty)
  unknown                 | title_unknown_in_catastro         | 45

If no MITECO file is present at all → status="skipped".
Orchestrator interprets that as 50 (neutral, "no data ≠ good").

Confidence is taken from the record itself (operator-supplied) and
floored at the worst per-hit confidence — we never overstate certainty.

Hard constraints (per project policy):
  * No automated outreach to title holders. Connector only reads data.
  * `holder` field is preserved verbatim from input — operator is
    responsible for redaction before sharing externally.
  * No scraping of the visor HTML. The connector reads files only;
    the optional WFS fetcher (separate script) is the only network
    code, marked as best-effort.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..contracts import AOI, ConnectorResult, Evidence


CONNECTOR_NAME = "miteco_catastro"

_HERE = Path(__file__).resolve().parent
_DATA_ROOT = _HERE.parent.parent.parent / "data" / "opportunity" / "miteco_manual"

# Most-blocking status wins when multiple hits are in radius.
# Higher = more commercially blocking.
_STATUS_PRIORITY: Dict[str, int] = {
    "conflicting":           100,
    "active":                 80,
    "active_third_party":     75,
    "pending_request":        60,
    "expired":                50,
    "cancelled":              45,
    "active_clear":           40,
    "unknown":                10,
}

_STATUS_TO_TAG: Dict[str, str] = {
    "active_clear":       "title_clear",
    "active":             "title_active_or_pending",
    "active_third_party": "title_active_by_third_party",
    "expired":            "title_expired",
    "cancelled":          "title_cancelled",
    "pending_request":    "title_pending_request",
    "conflicting":        "title_conflicting",
    "unknown":            "title_unknown_in_catastro",
}

# Visor / WFS GeoJSON properties → internal status normaliser.
# Spanish + English source labels both handled.
_VISOR_ESTADO_MAP: Dict[str, str] = {
    "vigente":          "active",
    "activo":           "active",
    "active":           "active",
    "otorgado":         "active",
    "en tramite":       "pending_request",
    "en tramitación":   "pending_request",
    "solicitud":        "pending_request",
    "pending":          "pending_request",
    "caducado":         "expired",
    "caducada":         "expired",
    "expired":          "expired",
    "extinguido":       "cancelled",
    "extinguida":       "cancelled",
    "anulado":          "cancelled",
    "cancelado":        "cancelled",
    "cancelled":        "cancelled",
    "conflictivo":      "conflicting",
    "litigio":          "conflicting",
    "conflicting":      "conflicting",
    "disputed":         "conflicting",
}

_VALID_STATUSES = set(_STATUS_PRIORITY.keys())

# Earth radius (km) for haversine — kept consistent with tailings_portal.
_R_EARTH_KM = 6371.0088


# ─── geometry helpers ─────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return _R_EARTH_KM * 2 * math.asin(math.sqrt(a))


def _polygon_centroid(coords: List[List[float]]) -> Optional[Tuple[float, float]]:
    """Coarse centroid: arithmetic mean of vertices. Good enough for
    bbox-style filtering at the radii we work with (≤ 100 km)."""
    if not coords:
        return None
    xs = [c[0] for c in coords if len(c) >= 2]
    ys = [c[1] for c in coords if len(c) >= 2]
    if not xs:
        return None
    return (sum(ys) / len(ys), sum(xs) / len(xs))  # (lat, lon)


def _feature_centroid(feature: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "Point" and len(coords) >= 2:
        return (float(coords[1]), float(coords[0]))
    if gtype == "Polygon" and coords:
        return _polygon_centroid(coords[0])
    if gtype == "MultiPolygon" and coords and coords[0]:
        return _polygon_centroid(coords[0][0])
    return None


# ─── file discovery ──────────────────────────────────────────────────

def _find_files() -> List[Path]:
    if not _DATA_ROOT.exists():
        return []
    out: List[Path] = []
    for ext in ("*.json", "*.geojson"):
        out.extend(sorted(_DATA_ROOT.glob(ext)))
    # Strip README/sample-skipped files; only keep payload-shaped names.
    return [p for p in out if not p.name.lower().startswith("readme")]


# ─── normalisers ─────────────────────────────────────────────────────

def _normalise_status(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    s = str(raw).strip().lower()
    if s in _VALID_STATUSES:
        return s
    return _VISOR_ESTADO_MAP.get(s, "unknown")


def _normalise_pasted(payload: Dict[str, Any], src: Path) -> List[Dict[str, Any]]:
    """Operator-pasted JSON: top-level {"version": "miteco_record.v0",
    "records": [...]} with each record carrying centroid + status."""
    if not isinstance(payload, dict):
        return []
    records = payload.get("records") or []
    if not isinstance(records, list):
        return []
    import_mode = "operator_pasted_json"
    out: List[Dict[str, Any]] = []
    default_conf = float(payload.get("default_confidence", 0.7) or 0.7)
    for raw in records:
        if not isinstance(raw, dict):
            continue
        cent = raw.get("centroid") or {}
        try:
            lat = float(cent.get("lat"))
            lon = float(cent.get("lon"))
        except (TypeError, ValueError):
            continue
        status = _normalise_status(raw.get("status"))
        if status not in _VALID_STATUSES:
            status = "unknown"
        conf = raw.get("confidence")
        try:
            conf = float(conf) if conf is not None else default_conf
        except (TypeError, ValueError):
            conf = default_conf
        out.append({
            "right_id":    str(raw.get("right_id", "")).strip(),
            "name":        str(raw.get("name", "")).strip(),
            "kind":        str(raw.get("kind", "unknown")).strip().lower() or "unknown",
            "section":     str(raw.get("section", "unknown")).strip().upper() or "UNKNOWN",
            "status":      status,
            "holder":      raw.get("holder"),    # may be None / "redacted"
            "lat":         lat,
            "lon":         lon,
            "valid_from":  str(raw.get("valid_from", "")).strip(),
            "expires_at":  str(raw.get("expires_at", "")).strip(),
            "source_url":  str(raw.get("source_url", "")).strip(),
            "imported_at": str(raw.get("imported_at", "")).strip(),
            "confidence":  max(0.0, min(1.0, conf)),
            "operator_note": str(raw.get("operator_note", "")).strip(),
            "import_mode": import_mode,
            "source_file": src.name,
        })
    return out


def _normalise_geojson(payload: Dict[str, Any], src: Path) -> List[Dict[str, Any]]:
    """Visor / WFS GeoJSON FeatureCollection. Properties keys are
    Spanish (EXPEDIENTE / ESTADO / TITULAR / TIPO / SECCION) or English
    fallbacks."""
    if not isinstance(payload, dict):
        return []
    if payload.get("type") != "FeatureCollection":
        return []
    feats = payload.get("features") or []
    if not isinstance(feats, list):
        return []
    # Heuristic: if filename hints at WFS, mark accordingly; else visor.
    fn = src.name.lower()
    import_mode = "official_wfs" if "wfs" in fn else "visor_geojson"
    out: List[Dict[str, Any]] = []
    for feat in feats:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        # Case-insensitive lookup helper.
        ci = {str(k).lower(): v for k, v in props.items() if v is not None}
        cent = _feature_centroid(feat)
        if cent is None:
            continue
        lat, lon = cent
        status_raw = ci.get("estado") or ci.get("status") or ci.get("state")
        status = _normalise_status(status_raw)
        kind = (ci.get("tipo") or ci.get("kind") or "unknown")
        section = (ci.get("seccion") or ci.get("section") or "unknown")
        out.append({
            "right_id":    str(ci.get("expediente") or ci.get("right_id") or "").strip(),
            "name":        str(ci.get("nombre") or ci.get("name") or "").strip(),
            "kind":        str(kind).strip().lower() or "unknown",
            "section":     str(section).strip().upper() or "UNKNOWN",
            "status":      status,
            "holder":      ci.get("titular") or ci.get("holder"),
            "lat":         float(lat),
            "lon":         float(lon),
            "valid_from":  str(ci.get("fecha_inicio") or ci.get("valid_from") or "").strip(),
            "expires_at":  str(ci.get("fecha_fin") or ci.get("expires_at") or "").strip(),
            "source_url":  str(ci.get("source_url") or "").strip(),
            "imported_at": "",
            "confidence":  0.75,   # visor / WFS = authoritative-ish
            "operator_note": "",
            "import_mode": import_mode,
            "source_file": src.name,
        })
    return out


def _load_file(path: Path) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    # GeoJSON FeatureCollection ?
    if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        return _normalise_geojson(payload, path)
    # Operator-pasted JSON ?
    if isinstance(payload, dict) and "records" in payload:
        return _normalise_pasted(payload, path)
    return []


# ─── public API ──────────────────────────────────────────────────────

def query(aoi: AOI) -> ConnectorResult:
    fetched_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    files = _find_files()
    if not files:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="skipped",
            fetched_at=fetched_at,
            error_message=(
                "no MITECO Catastro Minero data found under "
                f"{_DATA_ROOT}. Three import modes are supported:\n"
                "  1. run scripts/fetch_miteco_wfs.py (writes a GeoJSON "
                "via the official WFS when it is up);\n"
                "  2. drop a GeoJSON exported from "
                "https://geoportal.minetur.gob.es/CatastroMinero/ ;\n"
                "  3. drop an operator-curated JSON matching the "
                "miteco_record.v0 schema (see "
                "data/opportunity/samples/galicia_miteco_sample.json).\n"
                "With no data, legal subscore stays at 50 (neutral)."
            ),
        )

    # Aggregate records across all files; restrict to AOI radius.
    all_records: List[Dict[str, Any]] = []
    files_used: List[str] = []
    for f in files:
        recs = _load_file(f)
        if recs:
            files_used.append(f.name)
            all_records.extend(recs)

    if not all_records:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="error",
            fetched_at=fetched_at,
            error_message=(
                f"{len(files)} MITECO file(s) present but none parsed cleanly. "
                "Check that GeoJSON FeatureCollections carry geometries and "
                "that operator-pasted JSON uses the miteco_record.v0 schema."
            ),
        )

    hits: List[Dict[str, Any]] = []
    for r in all_records:
        d = _haversine_km(aoi.lat, aoi.lon, r["lat"], r["lon"])
        if d <= aoi.radius_km:
            r_out = dict(r)
            r_out["distance_km"] = round(d, 2)
            hits.append(r_out)

    if not hits:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="ok",
            evidence=(Evidence(
                tag="no_known_titles_in_radius",
                source=f"MITECO Catastro Minero (local: {', '.join(files_used)})",
                fetched_at=fetched_at,
                confidence=0.55,
                license="MITECO Catastro Minero — operator-imported subset",
                notes=(
                    f"No mining right in the supplied dataset falls within "
                    f"{aoi.radius_km} km of AOI center. Absence here does not "
                    "mean the catastro is empty — re-run after broadening the "
                    "import (WFS or wider visor export) before any commercial "
                    "claim of free-and-clear status."
                ),
                data={"files_scanned": files_used, "records_scanned": len(all_records)},
            ),),
            fetched_at=fetched_at,
        )

    # Pick the most-blocking status. Tie-break by distance (closest wins).
    hits.sort(key=lambda h: (-_STATUS_PRIORITY.get(h["status"], 0), h["distance_km"]))
    dominant = hits[0]
    dominant_status = dominant["status"]
    tag = _STATUS_TO_TAG.get(dominant_status, "title_unknown_in_catastro")

    # Confidence: floor at worst hit (conservative, never overstate).
    worst_conf = min(float(h.get("confidence", 0.5)) for h in hits)

    # Holder redaction: never echo a value that LOOKS like a personal email.
    # Operator is responsible for upstream redaction; we belt-and-braces it.
    for h in hits:
        holder = h.get("holder")
        if isinstance(holder, str) and "@" in holder:
            h["holder"] = "redacted"

    # Cap data payload to keep canonical JSON manageable.
    summary_hits = hits[:8]

    notes = (
        f"{len(hits)} mining right(s) within {aoi.radius_km} km. "
        f"Dominant status: {dominant_status}. "
        "Requires manual legal verification before outreach."
    )

    return ConnectorResult(
        connector=CONNECTOR_NAME,
        status="ok",
        evidence=(Evidence(
            tag=tag,
            source=f"MITECO Catastro Minero (local: {', '.join(files_used)})",
            fetched_at=fetched_at,
            confidence=worst_conf,
            license="MITECO Catastro Minero — operator-imported subset",
            notes=notes,
            data={
                "dominant_status":  dominant_status,
                "dominant_right_id": dominant.get("right_id", ""),
                "dominant_kind":    dominant.get("kind", ""),
                "import_mode":      dominant.get("import_mode", ""),
                "count":            len(hits),
                "files_scanned":    files_used,
                "hits":             summary_hits,
            },
        ),),
        fetched_at=fetched_at,
    )


__all__ = ["query", "CONNECTOR_NAME"]
