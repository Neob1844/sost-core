"""
GeaSpirit prospectivity bridge — feeds the technical satellite/ML stack
output into the opportunity layer's geological sub-score.

This connector is DISK-ONLY. It never calls the network, never runs a
model, never re-trains anything. The classical GeaSpirit pipeline
(``analyze_custom_aois.py``, ``rank_targets.py``,
``export_target_coordinates.py``) writes its prospectivity / target
scores to its usual output locations; the operator drops a normalised
copy under:

    geaspirit/data/opportunity/prospectivity_manual/

This connector reads everything there and emits Evidence the
orchestrator can score.

Accepted formats (any combination, no external deps required):

  * ``*.json`` — either a top-level list of record dicts, or a dict
    with a top-level ``records`` array. See sample file at
    ``data/opportunity/prospectivity_manual/galicia_wsn_prospectivity_sample.json``.

  * ``*.csv`` — comma-separated, UTF-8, header row required. Same
    field names as the JSON record schema. The ``signals`` column is
    a ``|``- or ``,``-separated list.

Record schema (case-insensitive on JSON keys / CSV headers):

    aoi_name          : str, free text
    lat, lon          : floats (decimal degrees, WGS84)
    radius_km         : float, optional — record's "footprint" radius;
                        if absent the connector treats the record as a
                        point.
    score             : float in [0,1] or [0,100]. Auto-normalised to
                        [0,100]: values <= 1.0 are multiplied by 100.
    score_type        : str — e.g. "heuristic", "model_auc",
                        "geaspirit_phase27". Free text, kept verbatim
                        on Evidence.data.
    confidence        : float in [0,1]; defaults to dataset-level
                        ``default_confidence`` or 0.55.
    model             : str — model / pipeline name, e.g.
                        "GeaSpirit Phase 27 Subsurface-Aware".
    source            : str — originating script / report, e.g.
                        "analyze_custom_aois.py".
    signals           : list[str] OR pipe-separated str. Recognised
                        families: ``spectral``, ``geophysics``,
                        ``thermal``, ``terrain``. Unknown families are
                        kept on data but do not emit signal tags.
    notes             : str, optional, free text.

Emitted Evidence tags (one composite + N signal tags):

    geaspirit_prospectivity_high       max score >= 70
    geaspirit_prospectivity_medium     40 <= max score < 70
    geaspirit_prospectivity_low        1  <= max score < 40

  Plus one of, per signal family present across kept records:

    geaspirit_signal_spectral
    geaspirit_signal_geophysics
    geaspirit_signal_thermal
    geaspirit_signal_terrain

Filtering rule:

    A record is "near" the AOI if the haversine distance between the
    record centroid and the AOI center is <=
        aoi.radius_km + record.radius_km  (when the record provides one)
    otherwise <= aoi.radius_km.

If no files exist (or no records survive the radius filter), the
connector returns status="skipped" — the orchestrator's existing
"no positive bonus when data is missing" policy takes over.

Why this design
---------------
The classical GeaSpirit modules (``dataset.py``, ``model.py``,
``indices.py``, ``spectral.py``, ``ee_download.py``, ``config.py``)
are intentionally **not imported** here. We do not want the
opportunity layer to depend on the satellite / ML stack at runtime —
the bridge is a *file format* contract, not a code contract. That
keeps the opportunity layer fast, offline-runnable and easy to test
without the full GeaSpirit environment.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..contracts import AOI, ConnectorResult, Evidence


CONNECTOR_NAME = "geaspirit_prospectivity"

_HERE = Path(__file__).resolve().parent
_DATA_ROOT = _HERE.parent.parent.parent / "data" / "opportunity" / "prospectivity_manual"

# Score band thresholds (on the normalised 0-100 scale).
_HIGH_THRESHOLD = 70
_MEDIUM_THRESHOLD = 40

# Recognised signal families. Anything else stays on data but does not
# emit a tag — keeps the tag namespace honest.
_KNOWN_SIGNAL_FAMILIES = ("spectral", "geophysics", "thermal", "terrain")


# ─── geo helpers ───────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ─── value coercion ────────────────────────────────────────────────

def _to_float(value, default=None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, bool):
        return default  # belt-and-braces: never coerce bool
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return default
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return default


def _normalise_score(raw) -> Optional[float]:
    """Map any score representation to the 0-100 scale.
    Values <= 1.0 are treated as 0-1 and multiplied by 100.
    Returns None when the value cannot be coerced."""
    v = _to_float(raw)
    if v is None:
        return None
    if v < 0:
        return 0.0
    if v <= 1.0:
        v *= 100.0
    if v > 100.0:
        v = 100.0
    return v


def _split_signals(value) -> List[str]:
    """Accept list, tuple, or string with '|' or ',' separators.
    Returns a lowercased, de-duped list, preserving order."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(x).strip().lower() for x in value]
    else:
        s = str(value).strip()
        if not s:
            return []
        sep = "|" if "|" in s else ","
        items = [x.strip().lower() for x in s.split(sep)]
    out: List[str] = []
    seen = set()
    for it in items:
        if it and it not in seen:
            out.append(it)
            seen.add(it)
    return out


# ─── record loading ────────────────────────────────────────────────

def _normalise_record(raw: Dict, dataset_default_confidence: float) -> Optional[Dict]:
    """Normalise one operator-provided record (JSON dict or CSV row)
    into the canonical shape consumed by score_one(). Returns None
    when the record lacks lat/lon — those are silently dropped."""
    if not isinstance(raw, dict):
        return None
    # Case-insensitive key lookup
    keymap = {k.strip().lower(): k for k in raw.keys() if isinstance(k, str)}

    def g(name):
        k = keymap.get(name)
        if k is None:
            return None
        return raw[k]

    lat = _to_float(g("lat") or g("latitude"))
    lon = _to_float(g("lon") or g("longitude") or g("lng"))
    if lat is None or lon is None:
        return None

    radius = _to_float(g("radius_km"))
    score = _normalise_score(g("score"))
    confidence = _to_float(g("confidence"), default=dataset_default_confidence)
    if confidence is None:
        confidence = dataset_default_confidence
    confidence = max(0.0, min(1.0, confidence))

    return {
        "aoi_name": str(g("aoi_name") or g("name") or "").strip(),
        "lat": lat,
        "lon": lon,
        "radius_km": radius,
        "score": score,
        "score_type": str(g("score_type") or "").strip(),
        "confidence": confidence,
        "model": str(g("model") or "").strip(),
        "source": str(g("source") or "").strip(),
        "signals": _split_signals(g("signals")),
        "notes": str(g("notes") or "").strip(),
    }


def _load_json(path: Path, default_conf_chain: List[float]) -> Tuple[List[Dict], str]:
    """Returns (records, license_notes). Accepts either top-level
    list-of-records or {"records": [...], ...}."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], ""

    license_notes = ""
    file_default_conf = None
    if isinstance(payload, dict):
        raw_records = payload.get("records") or []
        license_notes = str(payload.get("license_notes") or "").strip()
        if "default_confidence" in payload:
            file_default_conf = _to_float(payload["default_confidence"])
    elif isinstance(payload, list):
        raw_records = payload
    else:
        return [], ""

    chain = [file_default_conf, *default_conf_chain]
    eff_default = next((c for c in chain if c is not None), 0.55)

    out: List[Dict] = []
    for raw in raw_records:
        rec = _normalise_record(raw, eff_default)
        if rec is not None:
            out.append(rec)
    return out, license_notes


def _load_csv(path: Path, default_conf: float) -> List[Dict]:
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = [dict(r) for r in reader]
    except Exception:
        return []
    out: List[Dict] = []
    for raw in rows:
        rec = _normalise_record(raw, default_conf)
        if rec is not None:
            out.append(rec)
    return out


def _scan_disk(default_conf_chain: List[float]) -> Tuple[List[Dict], List[Dict]]:
    """Returns (records, file_meta). file_meta is a list of
    {path, format, license_notes, count} per file actually read."""
    records: List[Dict] = []
    meta: List[Dict] = []
    if not _DATA_ROOT.exists():
        return records, meta
    for p in sorted(_DATA_ROOT.iterdir()):
        if not p.is_file():
            continue
        suffix = p.suffix.lower()
        if suffix == ".json":
            recs, lic = _load_json(p, default_conf_chain)
            records.extend(recs)
            meta.append({"path": p.name, "format": "json",
                         "license_notes": lic, "count": len(recs)})
        elif suffix == ".csv":
            file_default = next((c for c in default_conf_chain if c is not None), 0.55)
            recs = _load_csv(p, file_default)
            records.extend(recs)
            meta.append({"path": p.name, "format": "csv",
                         "license_notes": "", "count": len(recs)})
        # Other suffixes intentionally ignored.
    return records, meta


# ─── orchestrator entry point ──────────────────────────────────────

def query(aoi: AOI) -> ConnectorResult:
    fetched_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    records, file_meta = _scan_disk(default_conf_chain=[])

    if not _DATA_ROOT.exists():
        return ConnectorResult(
            connector=CONNECTOR_NAME, status="skipped",
            evidence=(), fetched_at=fetched_at,
            error_message=(f"no prospectivity dropbox at {_DATA_ROOT}. Create the "
                           f"directory and drop normalised GeaSpirit output "
                           f"(JSON or CSV); the connector reads disk only."),
        )

    if not file_meta:
        return ConnectorResult(
            connector=CONNECTOR_NAME, status="skipped",
            evidence=(), fetched_at=fetched_at,
            error_message=(f"prospectivity dropbox is empty at {_DATA_ROOT}. Drop "
                           f"normalised GeaSpirit output (JSON or CSV) to enable "
                           f"the prospectivity sub-score."),
        )

    # Radius filter — keep records that overlap the AOI search radius.
    kept: List[Dict] = []
    for r in records:
        lat = r.get("lat")
        lon = r.get("lon")
        if lat is None or lon is None:
            continue
        d = _haversine_km(aoi.lat, aoi.lon, lat, lon)
        rec_radius = r.get("radius_km") or 0.0
        if d <= float(aoi.radius_km) + float(rec_radius or 0.0):
            r["distance_km"] = round(d, 3)
            kept.append(r)

    if not kept:
        return ConnectorResult(
            connector=CONNECTOR_NAME, status="ok",
            evidence=(), fetched_at=fetched_at,
            error_message=(f"{len(records)} prospectivity records on disk; "
                           f"0 fall within radius {aoi.radius_km} km of "
                           f"({aoi.lat:.4f}, {aoi.lon:.4f})."),
        )

    # Dominant score — drives the band tag.
    scores = [r.get("score") for r in kept if r.get("score") is not None]
    if not scores:
        return ConnectorResult(
            connector=CONNECTOR_NAME, status="ok",
            evidence=(), fetched_at=fetched_at,
            error_message=(f"{len(kept)} prospectivity records within radius; "
                           f"none carried a numeric score."),
        )
    max_score = max(scores)
    if max_score >= _HIGH_THRESHOLD:
        band_tag = "geaspirit_prospectivity_high"
    elif max_score >= _MEDIUM_THRESHOLD:
        band_tag = "geaspirit_prospectivity_medium"
    else:
        band_tag = "geaspirit_prospectivity_low"

    # Signal families — union across kept records, only the four
    # recognised families. The connector deliberately does not invent
    # new tag names from operator-provided strings.
    signal_families = set()
    for r in kept:
        for sig in r.get("signals", []):
            if sig in _KNOWN_SIGNAL_FAMILIES:
                signal_families.add(sig)

    # Aggregate confidence — mean across kept records.
    conf_vals = [r.get("confidence", 0.55) for r in kept]
    agg_confidence = sum(conf_vals) / len(conf_vals) if conf_vals else 0.55

    # Pick the contributing source / model strings (de-duped, short list).
    sources = sorted({r.get("source") for r in kept if r.get("source")})[:5]
    models  = sorted({r.get("model")  for r in kept if r.get("model")})[:5]
    score_types = sorted({r.get("score_type") for r in kept if r.get("score_type")})[:5]

    # Compose the band Evidence.
    license_notes = "; ".join(m["license_notes"] for m in file_meta if m["license_notes"]) \
                    or "Internal GeaSpirit prospectivity output, no public redistribution promised."

    band_ev = Evidence(
        tag=band_tag,
        source="geaspirit_prospectivity_disk",
        fetched_at=fetched_at,
        confidence=round(agg_confidence, 3),
        license=license_notes,
        notes=(f"Dominant prospectivity score {round(max_score,1)} from "
               f"{len(kept)} record(s) within radius. Reflects desk-stage "
               f"signal strength only; subject to verification before any "
               f"physical action."),
        data={
            "max_score":         round(max_score, 3),
            "kept_records":      len(kept),
            "total_records":     len(records),
            "sources":           sources,
            "models":            models,
            "score_types":       score_types,
            "min_distance_km":   round(min(r["distance_km"] for r in kept), 3),
            "signal_families_present": sorted(signal_families),
            "files_read":        [m["path"] for m in file_meta],
        },
    )

    # Signal Evidence — one per recognised family present.
    sig_evs = []
    for fam in sorted(signal_families):
        sig_evs.append(Evidence(
            tag=f"geaspirit_signal_{fam}",
            source="geaspirit_prospectivity_disk",
            fetched_at=fetched_at,
            confidence=round(agg_confidence, 3),
            license=license_notes,
            notes=f"{fam} signal family attested by GeaSpirit-side input.",
            data={"family": fam,
                  "record_count": sum(1 for r in kept if fam in r.get("signals", []))},
        ))

    return ConnectorResult(
        connector=CONNECTOR_NAME, status="ok",
        evidence=tuple([band_ev, *sig_evs]),
        fetched_at=fetched_at,
    )
