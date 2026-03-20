"""Staging engine — analyze a source before integration.

Phase IV.H: Dry-run analysis of what a source would add to the corpus.
Does NOT modify the database.
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from ..storage.db import MaterialsDB
from .spec import NormalizedCandidate, StagingReport, SOURCE_REGISTRY
from .dedup import batch_dedup

log = logging.getLogger(__name__)

STAGING_DIR = "artifacts/corpus_sources"


def stage_source(source_name: str, candidates: List[NormalizedCandidate],
                 db: MaterialsDB) -> StagingReport:
    """Analyze candidates from a source without modifying the DB."""
    # Normalize counts
    normalized_ok = sum(1 for c in candidates if c.formula)
    norm_errors = len(candidates) - normalized_ok

    # Dedup against corpus
    dedup = batch_dedup([c for c in candidates if c.formula], db)
    summary = dedup["summary"]

    # Find new elements not in corpus
    existing_elements = set()
    for m in db.list_materials(limit=5000):
        existing_elements.update(m.elements)
    candidate_elements = set()
    for c in candidates:
        candidate_elements.update(c.elements)
    new_elements = sorted(candidate_elements - existing_elements)

    # Find new spacegroups
    existing_sgs = set()
    for m in db.list_materials(limit=5000):
        if m.spacegroup:
            existing_sgs.add(m.spacegroup)
    candidate_sgs = set(c.spacegroup for c in candidates if c.spacegroup)
    new_sgs = sorted(candidate_sgs - existing_sgs)

    # Properties added
    props = []
    if any(c.formation_energy is not None for c in candidates):
        props.append("formation_energy")
    if any(c.band_gap is not None for c in candidates):
        props.append("band_gap")
    if any(c.has_structure for c in candidates):
        props.append("crystal_structure")

    # Recommendation
    unique_pct = summary["unique"] / max(1, summary["total"]) * 100
    if unique_pct > 60:
        rec = f"HIGH VALUE — {unique_pct:.0f}% unique materials. Recommend ingestion."
    elif unique_pct > 30:
        rec = f"MODERATE VALUE — {unique_pct:.0f}% unique. Consider selective ingestion."
    else:
        rec = f"LOW VALUE — only {unique_pct:.0f}% unique. High overlap. Defer unless needed."

    return StagingReport(
        source=source_name,
        total_candidates=len(candidates),
        normalized_ok=normalized_ok,
        normalization_errors=norm_errors,
        exact_duplicates=summary["exact"],
        probable_duplicates=summary["probable"] + summary["same_formula_diff"],
        unique_new=summary["unique"],
        new_elements=new_elements,
        new_spacegroups=new_sgs[:20],
        properties_added=props,
        recommendation=rec,
    )


def simulate_mp_staging(db: MaterialsDB, sample_size: int = 200) -> StagingReport:
    """Simulate staging for Materials Project using synthetic sample.

    Since we can't call the MP API without a key, we simulate what MP
    would look like based on known characteristics.
    """
    # Generate representative MP-like candidates
    import numpy as np
    rng = np.random.RandomState(42)

    # MP has ~154K materials, mostly binary/ternary oxides and intermetallics
    common_formulas = [
        "Li2O", "MgO", "CaO", "SrO", "BaO", "TiO2", "ZrO2", "Fe2O3", "Al2O3",
        "SiO2", "NaCl", "KCl", "CsCl", "GaN", "InP", "ZnS", "CdTe",
        "LiCoO2", "LiFePO4", "BaTiO3", "SrTiO3", "PbTiO3",
        "Mg2Si", "Ca3N2", "Li3N", "NbSe2", "MoS2", "WS2",
        "LaFeO3", "YBa2Cu3O7", "SmCo5", "Nd2Fe14B",
        # Some that would be unique (not in JARVIS)
        "RbAuO2", "CsPtCl6", "TlBiSe2", "HfNbP", "ScAgC",
        "OsIrB2", "ReWC", "TaRhGe", "NbPdSn", "VCrSi",
    ]

    candidates = []
    for i in range(sample_size):
        formula = common_formulas[i % len(common_formulas)]
        from ..normalization.chemistry import parse_formula
        try:
            elements, _ = parse_formula(formula)
        except Exception:
            elements = []

        candidates.append(NormalizedCandidate(
            source_name="materials_project",
            source_id=f"mp-{1000+i}",
            formula=formula,
            reduced_formula=formula,
            elements=sorted(elements),
            n_elements=len(elements),
            spacegroup=int(rng.choice([1, 2, 12, 14, 62, 63, 139, 166, 194, 221, 225, 227])),
            has_structure=True,
            formation_energy=round(rng.uniform(-5.0, 1.0), 3),
            band_gap=round(rng.uniform(0.0, 8.0), 3) if rng.random() > 0.3 else None,
            provenance="materials_project_simulated",
        ))

    return stage_source("materials_project", candidates, db)


def generate_expansion_recommendation(staging_reports: List[StagingReport]) -> dict:
    """Generate prioritized expansion recommendation from staging results."""
    recommendations = []
    for sr in staging_reports:
        unique_pct = sr.unique_new / max(1, sr.total_candidates) * 100
        score = unique_pct * 0.6 + len(sr.new_elements) * 2 + len(sr.properties_added) * 10
        recommendations.append({
            "source": sr.source,
            "unique_pct": round(unique_pct, 1),
            "unique_count": sr.unique_new,
            "new_elements": len(sr.new_elements),
            "new_properties": sr.properties_added,
            "score": round(score, 1),
            "recommendation": sr.recommendation,
        })

    recommendations.sort(key=lambda r: -r["score"])

    # Priority assignment
    for i, r in enumerate(recommendations):
        if i == 0 and r["score"] > 50:
            r["action"] = "ingest_next"
        elif r["score"] > 30:
            r["action"] = "ingest_after_top_priority"
        else:
            r["action"] = "defer"

    return {
        "ranked_sources": recommendations,
        "next_action": recommendations[0]["action"] if recommendations else "none",
        "note": "Recommendations based on staging analysis. Actual ingestion requires explicit execution.",
    }


def save_staging(report: StagingReport, output_dir: str = STAGING_DIR) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"staging_report_{report.source}.json")
    with open(path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    md_path = os.path.join(output_dir, f"staging_report_{report.source}.md")
    md = f"# Staging Report: {report.source}\n\n"
    md += f"Total candidates: {report.total_candidates}\n"
    md += f"Normalized OK: {report.normalized_ok}\n"
    md += f"Exact duplicates: {report.exact_duplicates}\n"
    md += f"Probable duplicates: {report.probable_duplicates}\n"
    md += f"**Unique new: {report.unique_new}**\n"
    md += f"New elements: {', '.join(report.new_elements) or 'none'}\n"
    md += f"\n**Recommendation:** {report.recommendation}\n"
    with open(md_path, "w") as f:
        f.write(md)

    return path
