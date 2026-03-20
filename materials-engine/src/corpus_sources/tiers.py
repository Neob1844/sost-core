"""Corpus tier classification — labeled vs unlabeled material tiers.

Phase IV.J: Classify every material in the corpus by its training readiness
and utility tier. Enables clean separation between:
  - Materials ready for ML training (have FE/BG labels)
  - Materials useful only for structure/search/reference
  - Generated candidates not yet validated
  - External unlabeled materials from structure-only sources
"""

import json
import logging
import os
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ..storage.db import MaterialsDB

log = logging.getLogger(__name__)

# --- Tier constants ---
TIER_TRAINING_READY = "training_ready"
TIER_STRUCTURE_ONLY = "structure_only"
TIER_REFERENCE_ONLY = "reference_only"
TIER_GENERATED_CANDIDATE = "generated_candidate"
TIER_EXTERNAL_UNLABELED = "external_unlabeled"

ALL_TIERS = [
    TIER_TRAINING_READY,
    TIER_STRUCTURE_ONLY,
    TIER_REFERENCE_ONLY,
    TIER_GENERATED_CANDIDATE,
    TIER_EXTERNAL_UNLABELED,
]

TIER_DESCRIPTIONS = {
    TIER_TRAINING_READY: "Has formation_energy and/or band_gap. Can enter ML training pipelines.",
    TIER_STRUCTURE_ONLY: "Has valid crystal structure but no computed properties. Useful for structural search, novelty, exotic ranking.",
    TIER_REFERENCE_ONLY: "Has formula/composition but no structure or properties. Reference for dedup and coverage mapping.",
    TIER_GENERATED_CANDIDATE: "Computationally generated candidate. Not validated by DFT or experiment. Do NOT train on.",
    TIER_EXTERNAL_UNLABELED: "Ingested from external source without computed labels. Useful for search space expansion.",
}

# Sources known to produce structure-only data (no FE/BG)
STRUCTURE_ONLY_SOURCES = {"cod"}
# Sources known to produce training-ready data
TRAINING_READY_SOURCES = {"jarvis", "materials_project", "aflow", "oqmd"}
# Sources that are generated/hypothetical
GENERATED_SOURCES = {"generated", "hypothetical", "candidate"}


@dataclass
class TieredMaterialRecord:
    """A material annotated with its corpus tier."""
    canonical_id: str = ""
    formula: str = ""
    source: str = ""
    tier: str = TIER_REFERENCE_ONLY
    has_formation_energy: bool = False
    has_band_gap: bool = False
    has_structure: bool = False
    has_spacegroup: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CorpusTierSummary:
    """Summary of corpus tier distribution."""
    total_materials: int = 0
    tier_counts: Dict[str, int] = field(default_factory=dict)
    tier_percentages: Dict[str, float] = field(default_factory=dict)
    by_source: Dict[str, Dict[str, int]] = field(default_factory=dict)
    training_ready_with_fe: int = 0
    training_ready_with_bg: int = 0
    training_ready_with_both: int = 0
    structure_coverage: float = 0.0
    spacegroup_coverage: float = 0.0
    element_coverage: int = 0
    unique_spacegroups: int = 0
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def classify_material_tier(source: str, has_fe: bool, has_bg: bool,
                           has_structure: bool, has_spacegroup: bool) -> tuple:
    """Classify a single material into a tier.

    Returns (tier, reason).
    """
    if source in GENERATED_SOURCES:
        return TIER_GENERATED_CANDIDATE, f"source={source} is generated/hypothetical"

    if has_fe or has_bg:
        return TIER_TRAINING_READY, "has computed properties (FE and/or BG)"

    if source in STRUCTURE_ONLY_SOURCES:
        if has_structure or has_spacegroup:
            return TIER_STRUCTURE_ONLY, f"source={source} provides structures only"
        return TIER_EXTERNAL_UNLABELED, f"source={source} without structure data"

    if has_structure or has_spacegroup:
        return TIER_STRUCTURE_ONLY, "has structure but no computed properties"

    if source not in TRAINING_READY_SOURCES:
        return TIER_EXTERNAL_UNLABELED, f"external source={source} without labels"

    return TIER_REFERENCE_ONLY, "no structure, no properties"


def compute_tier_summary(db: MaterialsDB) -> CorpusTierSummary:
    """Compute tier distribution for the entire corpus."""
    now = datetime.now(timezone.utc).isoformat()

    tier_counts = Counter()
    source_tier = {}  # source -> {tier: count}
    fe_count = 0
    bg_count = 0
    both_count = 0
    struct_count = 0
    sg_count = 0
    all_elements = set()
    all_sgs = set()

    total = db.count()
    batch_size = 5000
    offset = 0

    while offset < total:
        materials = db.list_materials(limit=batch_size, offset=offset)
        if not materials:
            break
        for m in materials:
            has_fe = m.formation_energy is not None
            has_bg = m.band_gap is not None
            has_struct = bool(m.has_valid_structure)
            has_sg = m.spacegroup is not None

            tier, _ = classify_material_tier(
                m.source, has_fe, has_bg, has_struct, has_sg)
            tier_counts[tier] += 1

            if m.source not in source_tier:
                source_tier[m.source] = Counter()
            source_tier[m.source][tier] += 1

            if has_fe:
                fe_count += 1
            if has_bg:
                bg_count += 1
            if has_fe and has_bg:
                both_count += 1
            if has_struct:
                struct_count += 1
            if has_sg:
                sg_count += 1
                all_sgs.add(m.spacegroup)
            if m.elements:
                all_elements.update(m.elements)

        offset += batch_size

    pcts = {}
    for t in ALL_TIERS:
        pcts[t] = round(tier_counts.get(t, 0) / max(total, 1) * 100, 2)

    return CorpusTierSummary(
        total_materials=total,
        tier_counts=dict(tier_counts),
        tier_percentages=pcts,
        by_source={s: dict(v) for s, v in source_tier.items()},
        training_ready_with_fe=fe_count,
        training_ready_with_bg=bg_count,
        training_ready_with_both=both_count,
        structure_coverage=round(struct_count / max(total, 1) * 100, 2),
        spacegroup_coverage=round(sg_count / max(total, 1) * 100, 2),
        element_coverage=len(all_elements),
        unique_spacegroups=len(all_sgs),
        created_at=now,
    )


def save_tier_summary(summary: CorpusTierSummary,
                      output_dir: str = "artifacts/corpus_sources"):
    """Save tier summary as JSON + Markdown."""
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "tiers_summary.json"), "w") as f:
        json.dump(summary.to_dict(), f, indent=2)

    md = "# Corpus Tier Summary\n\n"
    md += f"**Total materials:** {summary.total_materials}\n\n"
    md += "## Tier Distribution\n\n"
    md += "| Tier | Count | % |\n|------|-------|---|\n"
    for t in ALL_TIERS:
        c = summary.tier_counts.get(t, 0)
        p = summary.tier_percentages.get(t, 0.0)
        md += f"| {t} | {c:,} | {p}% |\n"

    md += f"\n## Training Readiness\n\n"
    md += f"- With formation_energy: {summary.training_ready_with_fe:,}\n"
    md += f"- With band_gap: {summary.training_ready_with_bg:,}\n"
    md += f"- With both FE + BG: {summary.training_ready_with_both:,}\n"
    md += f"- Structure coverage: {summary.structure_coverage}%\n"
    md += f"- Spacegroup coverage: {summary.spacegroup_coverage}%\n"
    md += f"- Unique elements: {summary.element_coverage}\n"
    md += f"- Unique spacegroups: {summary.unique_spacegroups}\n"

    md += f"\n## By Source\n\n"
    for src, tiers in sorted(summary.by_source.items()):
        md += f"### {src}\n"
        for t, c in sorted(tiers.items()):
            md += f"- {t}: {c:,}\n"

    md += f"\n## Tier Definitions\n\n"
    for t, desc in TIER_DESCRIPTIONS.items():
        md += f"- **{t}**: {desc}\n"

    md += f"\n---\nGenerated: {summary.created_at}\n"

    with open(os.path.join(output_dir, "tiers_summary.md"), "w") as f:
        f.write(md)
