"""
Campaign engine — score and rank many AOIs in one shot.

A *campaign* is a small JSON file that defines:

  * a name + description + version metadata,
  * a list of AOIs (the same dict shape ``opportunity_scan.py`` already
    accepts: ``name, lat, lon, radius_km, country, metals_of_interest``).

The engine:

  1. Builds an :class:`AOI` for each entry.
  2. Runs :func:`score_opportunity` against the default connector set
     (which in Sprint 2.3 includes the GeaSpirit prospectivity bridge).
  3. Sorts the resulting scorecards by ``subscores.commercial`` desc,
     with ``aoi.name`` as a stable tiebreaker.
  4. Exports the run as:

       * one canonical JSON + one pretty JSON per AOI (each carries
         its own SHA-256 in the filename for tamper-evidence),
       * one ``campaign_summary.canonical.json`` carrying the full
         ranking plus the campaign metadata,
       * one ``campaign_summary.pretty.json`` for humans,
       * one ``ranking.csv`` for spreadsheets.

There is intentionally no live network call inside this module — the
connectors do their own I/O and the engine just orchestrates. The
output directory layout is the contract.

Anti-confusion guarantees
-------------------------
* The campaign summary stores each AOI's canonical SHA-256 alongside
  its ranking line. Anyone can re-run the per-AOI canonical hash and
  check it matches.
* The pretty form is *never* hashed and is for humans only.
* No promotional language can sneak in: every scorecard goes through
  the language guardrail in :mod:`geaspirit.opportunity.contracts`.
"""
from __future__ import annotations

import csv
import dataclasses
import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .contracts import AOI, ConnectorResult, OpportunityScorecard
from .canonical import canonical_json, sha256_of_canonical, pretty_json
from .orchestrator import score_opportunity, DefaultConnectors


CAMPAIGN_SCHEMA_VERSION = "opportunity_campaign.v1"


# ─── input parsing ─────────────────────────────────────────────────

def _coerce_aoi(raw: Dict[str, Any]) -> AOI:
    """Accept the same dict shape opportunity_scan.py reads — but also
    tolerate either 'name' or 'aoi_name' and either tuple or list for
    metals_of_interest."""
    name = str(raw.get("name") or raw.get("aoi_name") or "").strip()
    if not name:
        raise ValueError("campaign AOI is missing 'name' / 'aoi_name'")
    metals = raw.get("metals_of_interest") or raw.get("metals") or []
    if isinstance(metals, str):
        metals = [m.strip() for m in re.split(r"[|,]", metals) if m.strip()]
    return AOI(
        name=name,
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        radius_km=float(raw["radius_km"]),
        country=str(raw.get("country") or "").strip(),
        metals_of_interest=tuple(metals),
    )


def parse_campaign_file(path: Path) -> Dict[str, Any]:
    """Read the campaign JSON file and return a dict with at least:
    ``name, description, version, generated_at, aois (List[AOI])``."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"campaign file {path} must be a JSON object")
    raw_aois = payload.get("aois") or payload.get("areas") or []
    if not isinstance(raw_aois, list) or not raw_aois:
        raise ValueError(f"campaign file {path} has no 'aois' list")
    aois = [_coerce_aoi(r) for r in raw_aois]
    return {
        "name": str(payload.get("name") or path.stem).strip(),
        "description": str(payload.get("description") or "").strip(),
        "version": str(payload.get("version") or "1").strip(),
        "source_path": str(path),
        "aois": aois,
    }


# ─── execution ─────────────────────────────────────────────────────

def run_campaign(
    campaign: Dict[str, Any],
    connectors: Optional[Tuple[Callable[[AOI], ConnectorResult], ...]] = None,
    limit: Optional[int] = None,
) -> List[OpportunityScorecard]:
    """Score every AOI in the campaign and return a list sorted by
    commercial subscore descending (with name as the tiebreaker).

    `limit` truncates the AOI input *before* scoring — useful for
    fast smoke runs."""
    aois = campaign["aois"]
    if limit is not None and limit > 0:
        aois = aois[:limit]
    connectors = connectors if connectors is not None else DefaultConnectors
    scorecards: List[OpportunityScorecard] = []
    for aoi in aois:
        sc = score_opportunity(aoi, connectors=connectors)
        scorecards.append(sc)
    scorecards.sort(
        key=lambda s: (-s.subscores.commercial, s.aoi.name)
    )
    return scorecards


# ─── ranking & export ──────────────────────────────────────────────

_FNAME_SANITISE = re.compile(r"[^a-z0-9._-]+")

def _slug(name: str) -> str:
    return _FNAME_SANITISE.sub("-", name.lower()).strip("-") or "aoi"


def _redact_aoi(aoi_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Strip exact coordinates from a serialised AOI for a public
    teaser. Country, name, metals and radius are preserved."""
    out = dict(aoi_dict)
    out.pop("lat", None)
    out.pop("lon", None)
    out["coordinates_redacted"] = True
    return out


def _aoi_to_dict(aoi: AOI) -> Dict[str, Any]:
    return dataclasses.asdict(aoi)


def ranking_rows(scorecards: Iterable[OpportunityScorecard]) -> List[Dict[str, Any]]:
    rows = []
    for i, sc in enumerate(scorecards, start=1):
        cj = canonical_json(sc)
        rows.append({
            "rank": i,
            "aoi_name": sc.aoi.name,
            "country": sc.aoi.country,
            "metals": "|".join(sc.aoi.metals_of_interest),
            "opportunity_class": sc.opportunity_class,
            "class_grade": sc.class_grade,
            "score": sc.score,
            "geological": sc.subscores.geological,
            "logistics": sc.subscores.logistics,
            "environmental": sc.subscores.environmental,
            "legal": sc.subscores.legal,
            "commercial": sc.subscores.commercial,
            "canonical_sha256":
                sha256_of_canonical(sc),
            "_canonical_size_bytes": len(cj),
        })
    return rows


def export_campaign(
    scorecards: List[OpportunityScorecard],
    campaign_meta: Dict[str, Any],
    out_dir: Path,
    redact_coordinates: bool = False,
) -> Dict[str, Path]:
    """Write the per-AOI canonical + pretty JSON, the campaign summary
    (canonical + pretty) and the ranking CSV. Returns the written
    paths keyed by short label."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    generated_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Per-AOI canonical + pretty.
    per_aoi_records = []
    for sc in scorecards:
        slug = _slug(sc.aoi.name)
        cj = canonical_json(sc)
        sha = sha256_of_canonical(sc)
        short_sha = sha[:12]
        canonical_name = f"{slug}__{short_sha}.canonical.json"
        pretty_name    = f"{slug}__{short_sha}.pretty.json"
        (out_dir / canonical_name).write_bytes(cj)
        (out_dir / pretty_name).write_text(
            pretty_json(sc), encoding="utf-8"
        )
        written[f"aoi:{slug}:canonical"] = out_dir / canonical_name
        written[f"aoi:{slug}:pretty"]    = out_dir / pretty_name
        aoi_dict = _aoi_to_dict(sc.aoi)
        if redact_coordinates:
            aoi_dict = _redact_aoi(aoi_dict)
        per_aoi_records.append({
            "aoi": aoi_dict,
            "opportunity_class": sc.opportunity_class,
            "class_grade": sc.class_grade,
            "score": sc.score,
            "subscores": dataclasses.asdict(sc.subscores),
            "canonical_sha256": sha,
            "canonical_file": canonical_name,
            "pretty_file": pretty_name,
        })

    rows = ranking_rows(scorecards)
    summary = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_name": campaign_meta.get("name", ""),
        "campaign_description": campaign_meta.get("description", ""),
        "campaign_version": campaign_meta.get("version", "1"),
        "campaign_source_path":
            campaign_meta.get("source_path", "") if not redact_coordinates else "redacted",
        "generated_at": generated_at,
        "redact_coordinates": redact_coordinates,
        "aoi_count": len(scorecards),
        "ranking": [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in rows
        ],
        "scorecards": per_aoi_records,
        "not_a_resource_estimate": True,
    }

    sum_canonical_path = out_dir / "campaign_summary.canonical.json"
    sum_pretty_path    = out_dir / "campaign_summary.pretty.json"
    sum_canonical_path.write_bytes(canonical_json(summary))
    sum_pretty_path.write_text(pretty_json(summary), encoding="utf-8")
    written["campaign:canonical"] = sum_canonical_path
    written["campaign:pretty"]    = sum_pretty_path

    # Ranking CSV.
    csv_path = out_dir / "ranking.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "rank", "aoi_name", "country", "metals", "opportunity_class",
            "class_grade", "score", "geological", "logistics",
            "environmental", "legal", "commercial", "canonical_sha256",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row[k] for k in fieldnames})
    written["campaign:csv"] = csv_path

    return written


# ─── convenience top-level call ────────────────────────────────────

def run_and_export(
    campaign_file: Path,
    out_dir: Path,
    *,
    limit: Optional[int] = None,
    redact_coordinates: bool = False,
    connectors: Optional[Tuple[Callable[[AOI], ConnectorResult], ...]] = None,
) -> Tuple[List[OpportunityScorecard], Dict[str, Path]]:
    """One-shot helper used by both the CLI and the tests."""
    campaign = parse_campaign_file(Path(campaign_file))
    scorecards = run_campaign(campaign, connectors=connectors, limit=limit)
    written = export_campaign(
        scorecards, campaign, Path(out_dir),
        redact_coordinates=redact_coordinates,
    )
    return scorecards, written
