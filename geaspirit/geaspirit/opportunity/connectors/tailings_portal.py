"""
Tailings facility connector — Global Tailings Portal (GRID-Arendal).

The Portal allows free CONSULTATION online but full-database download
requires contacting GRID-Arendal. Scraping the web UI is fragile AND
arguably against their terms, so this connector is a deliberately
SIMPLE CSV importer:

  1. Operator requests the dataset from GRID-Arendal (one email).
  2. Operator drops the CSV under
     geaspirit/data/opportunity/tailings_manual/
  3. This connector loads it and looks up TSFs within `aoi.radius_km`
     of the AOI center.

Expected CSV columns (case-insensitive, comma-separated, UTF-8):
  name, latitude, longitude, country, status,
  mined_commodity_primary, mined_commodity_secondary,
  tailings_storage_facility_volume_m3, dam_height_m, year_built

Extra columns are kept verbatim in Evidence.data['raw'].

If no CSV is present we return status="skipped" with the install
instruction — orchestrator applies a data-uncertainty penalty.
"""
from __future__ import annotations

import csv
import datetime as _dt
import math
from pathlib import Path
from typing import Dict, List, Optional

from ..contracts import AOI, ConnectorResult, Evidence


CONNECTOR_NAME = "tailings_portal"
_HERE = Path(__file__).resolve().parent
_DATA_ROOT = _HERE.parent.parent.parent / "data" / "opportunity" / "tailings_manual"


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def _find_csv() -> Optional[Path]:
    if not _DATA_ROOT.exists():
        return None
    for p in sorted(_DATA_ROOT.glob("*.csv")):
        if p.is_file():
            return p
    return None


def _parse_float(s: str) -> Optional[float]:
    if s is None: return None
    s = s.strip()
    if not s: return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _row_to_dict(row: Dict[str, str]) -> Dict[str, object]:
    # Case-insensitive lookup helper.
    norm = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
    lat = _parse_float(norm.get("latitude") or norm.get("lat"))
    lon = _parse_float(norm.get("longitude") or norm.get("lon") or norm.get("lng"))
    return {
        "name": norm.get("name", ""),
        "lat": lat,
        "lon": lon,
        "country": norm.get("country", ""),
        "status": norm.get("status", ""),
        "primary_metal":   norm.get("mined_commodity_primary", ""),
        "secondary_metal": norm.get("mined_commodity_secondary", ""),
        "volume_m3": _parse_float(norm.get("tailings_storage_facility_volume_m3")
                                  or norm.get("volume_m3")),
        "dam_height_m": _parse_float(norm.get("dam_height_m") or norm.get("height_m")),
        "year_built": norm.get("year_built", ""),
    }


def _load_csv(path: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            d = _row_to_dict(row)
            if d["lat"] is None or d["lon"] is None:
                continue
            rows.append(d)
    return rows


def query(aoi: AOI) -> ConnectorResult:
    fetched_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    csv_path = _find_csv()
    if csv_path is None:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="skipped",
            fetched_at=fetched_at,
            error_message=(
                "no tailings CSV found under "
                f"{_DATA_ROOT}. Request the dataset from GRID-Arendal "
                "(https://tailing.grida.no/about) and drop the CSV in "
                "this directory to enable nearby-TSF evidence."
            ),
        )

    try:
        rows = _load_csv(csv_path)
    except (OSError, csv.Error) as e:
        return ConnectorResult(
            connector=CONNECTOR_NAME,
            status="error",
            fetched_at=fetched_at,
            error_message=f"could not read {csv_path.name}: {e}",
        )

    hits: List[Dict[str, object]] = []
    for r in rows:
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
                tag="no_known_tailings_in_radius",
                source=f"local CSV: {csv_path.name}",
                fetched_at=fetched_at,
                confidence=0.5,
                license="GRID-Arendal Global Tailings Portal — operator-imported subset",
                notes=(
                    f"No TSF in the supplied CSV falls within {aoi.radius_km} km "
                    "of AOI center. Absence here does not mean absence on the "
                    "ground — abandoned dumps & non-portal facilities exist."
                ),
            ),),
            fetched_at=fetched_at,
        )

    # Sort by distance, keep top 8 in evidence payload.
    hits.sort(key=lambda h: h["distance_km"])
    biggest_vol = max((h["volume_m3"] or 0.0) for h in hits)
    return ConnectorResult(
        connector=CONNECTOR_NAME,
        status="ok",
        evidence=(Evidence(
            tag="nearby_tailings_facility",
            source=f"local CSV: {csv_path.name}",
            fetched_at=fetched_at,
            confidence=0.85,
            license="GRID-Arendal Global Tailings Portal — operator-imported subset",
            notes=(
                f"{len(hits)} tailings facility hit(s) within {aoi.radius_km} km. "
                f"Largest volume ~{biggest_vol:,.0f} m³. "
                "Each hit merits desk validation before any field action."
            ),
            data={
                "count": len(hits),
                "largest_volume_m3": biggest_vol,
                "hits": hits[:8],
            },
        ),),
        fetched_at=fetched_at,
    )
