"""Retraining preparation report — save all artifacts.

Phase IV.K: Generates JSON + Markdown artifacts for hard-case mining,
difficulty tiers, selective datasets, and priority ranking.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from ..storage.db import MaterialsDB
from .spec import (
    DifficultyTierSummary, SelectiveDatasetPlan, RetrainingPriorityScore,
    RetrainingPrepReport, DIFF_DESCRIPTIONS,
)
from .mining import mine_hard_cases, _load_calibration
from .datasets import build_dataset_plans, score_dataset_plans

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/retraining_prep"


def generate_full_report(db: MaterialsDB) -> RetrainingPrepReport:
    """Generate the complete retraining preparation report.

    Steps:
    1. Mine hard cases for both targets
    2. Build selective dataset plans
    3. Score and rank datasets
    4. Generate recommendation
    """
    now = datetime.now(timezone.utc).isoformat()

    # 1. Mine hard cases
    bg_summary, bg_cases = mine_hard_cases(db, target="band_gap")
    fe_summary, fe_cases = mine_hard_cases(db, target="formation_energy")

    # 2. Build dataset plans
    plans = build_dataset_plans(db)

    # 3. Score
    bg_calib = _load_calibration("band_gap")
    fe_calib = _load_calibration("formation_energy")
    scored = score_dataset_plans(plans, bg_calib, fe_calib)

    # 4. Recommendation
    top = scored[0] if scored else None
    if top and top.target == "band_gap":
        recommendation = "retrain_band_gap_hotspots_next"
        next_action = (f"Use dataset '{top.dataset_name}' ({top.overall_score:.2f} priority) "
                       f"for next band_gap retraining on rung_20k. "
                       f"Current BG MAE=0.49 → target MAE<0.35.")
    elif top and top.target == "formation_energy":
        recommendation = "retrain_formation_energy_hardcases_next"
        next_action = (f"Use dataset '{top.dataset_name}' for FE retraining. "
                       f"Current FE MAE=0.23 → target MAE<0.15.")
    else:
        recommendation = "wait_for_more_external_labels"
        next_action = "No clear improvement path. Wait for external data."

    do_not = [
        "Do NOT retrain in this phase — datasets are prepared, not executed",
        "Do NOT use structure_only or external_unlabeled tier for training",
        "Do NOT retrain on full 76K corpus — 20K was already optimal in ladder",
        "Do NOT change production models until new training is validated",
        "Do NOT ignore holdout set — reserve for final validation",
    ]

    report = RetrainingPrepReport(
        hardcase_summary={
            "band_gap": {
                "total_classified": bg_summary.total_materials,
                "tier_counts": bg_summary.tier_counts,
                "tier_percentages": bg_summary.tier_percentages,
                "hardest_buckets": bg_summary.hardest_buckets,
                "sparse_elements": bg_summary.sparse_elements[:10],
                "rare_spacegroups": bg_summary.rare_spacegroups[:10],
                "hard_cases_found": len(bg_cases),
            },
            "formation_energy": {
                "total_classified": fe_summary.total_materials,
                "tier_counts": fe_summary.tier_counts,
                "tier_percentages": fe_summary.tier_percentages,
                "hardest_buckets": fe_summary.hardest_buckets,
                "sparse_elements": fe_summary.sparse_elements[:10],
                "rare_spacegroups": fe_summary.rare_spacegroups[:10],
                "hard_cases_found": len(fe_cases),
            },
        },
        difficulty_tiers={
            "band_gap": bg_summary.to_dict(),
            "formation_energy": fe_summary.to_dict(),
        },
        datasets=[p.to_dict() for p in plans],
        priority_ranking=[s.to_dict() for s in scored],
        recommendation=recommendation,
        next_action=next_action,
        do_not=do_not,
        created_at=now,
    )

    return report


def save_report(report: RetrainingPrepReport, output_dir: str = ARTIFACT_DIR):
    """Save all retraining preparation artifacts."""
    os.makedirs(output_dir, exist_ok=True)

    # 1. Hardcase summary
    with open(os.path.join(output_dir, "hardcase_summary.json"), "w") as f:
        json.dump(report.hardcase_summary, f, indent=2)
    _save_hardcase_md(report, output_dir)

    # 2. Difficulty tiers
    with open(os.path.join(output_dir, "difficulty_tiers.json"), "w") as f:
        json.dump(report.difficulty_tiers, f, indent=2)
    _save_tiers_md(report, output_dir)

    # 3. Selective datasets
    with open(os.path.join(output_dir, "selective_datasets.json"), "w") as f:
        json.dump(report.datasets, f, indent=2)
    _save_datasets_md(report, output_dir)

    # 4. Priority ranking
    with open(os.path.join(output_dir, "retraining_priority.json"), "w") as f:
        json.dump({
            "ranking": report.priority_ranking,
            "recommendation": report.recommendation,
            "next_action": report.next_action,
            "do_not": report.do_not,
        }, f, indent=2)
    _save_priority_md(report, output_dir)


def _save_hardcase_md(report, output_dir):
    md = "# Hard-Case Mining Summary\n\n"
    for target in ("band_gap", "formation_energy"):
        data = report.hardcase_summary.get(target, {})
        md += f"## {target}\n\n"
        md += f"- Total classified: {data.get('total_classified', 0):,}\n"
        md += f"- Hard cases found: {data.get('hard_cases_found', 0):,}\n\n"
        md += "| Tier | Count | % |\n|------|-------|---|\n"
        for tier, count in sorted(data.get("tier_counts", {}).items()):
            pct = data.get("tier_percentages", {}).get(tier, 0)
            md += f"| {tier} | {count:,} | {pct}% |\n"
        if data.get("hardest_buckets"):
            md += "\n### Hardest Calibration Buckets\n\n"
            for b in data["hardest_buckets"]:
                md += f"- {b['bucket']}: MAE={b['mae']:.3f} ({b['confidence_band']}, n={b['count']})\n"
        md += "\n"
    with open(os.path.join(output_dir, "hardcase_summary.md"), "w") as f:
        f.write(md)


def _save_tiers_md(report, output_dir):
    md = "# Difficulty Tier Distribution\n\n"
    for target, data in report.difficulty_tiers.items():
        md += f"## {target}\n\n"
        md += f"Total: {data.get('total_materials', 0):,}\n\n"
        md += "| Tier | Count | % |\n|------|-------|---|\n"
        for tier, count in sorted(data.get("tier_counts", {}).items()):
            pct = data.get("tier_percentages", {}).get(tier, 0)
            md += f"| {tier} | {count:,} | {pct}% |\n"
        md += "\n"
    md += "## Tier Definitions\n\n"
    for tier, desc in DIFF_DESCRIPTIONS.items():
        md += f"- **{tier}**: {desc}\n"
    with open(os.path.join(output_dir, "difficulty_tiers.md"), "w") as f:
        f.write(md)


def _save_datasets_md(report, output_dir):
    md = "# Selective Retraining Datasets\n\n"
    md += "**Status: PREPARED — NOT YET TRAINED**\n\n"
    for ds in report.datasets:
        md += f"## {ds['name']}\n\n"
        md += f"- **Target**: {ds['target']}\n"
        md += f"- **Size**: {ds['size']:,}\n"
        md += f"- **Elements**: {ds.get('element_diversity', 0)} unique\n"
        md += f"- **Spacegroups**: {ds.get('sg_diversity', 0)} unique\n"
        md += f"- **Selection**: {ds['selection_logic']}\n"
        md += f"- **Reason**: {ds['reason_for_existence']}\n"
        md += f"- **Expected benefit**: {ds['expected_benefit']}\n"
        md += f"- **Risk**: {ds['risk_note']}\n\n"
    with open(os.path.join(output_dir, "selective_datasets.md"), "w") as f:
        f.write(md)


def _save_priority_md(report, output_dir):
    md = "# Retraining Priority Ranking\n\n"
    md += f"**Recommendation: {report.recommendation}**\n\n"
    md += f"{report.next_action}\n\n"
    md += "## Ranking\n\n"
    md += "| Rank | Dataset | Target | Score | Recommendation |\n"
    md += "|------|---------|--------|-------|----------------|\n"
    for s in report.priority_ranking:
        md += f"| {s['rank']} | {s['dataset_name']} | {s['target']} | {s['overall_score']:.3f} | {s['recommendation']} |\n"
    md += "\n## Score Breakdown (top 3)\n\n"
    for s in report.priority_ranking[:3]:
        md += f"### #{s['rank']} {s['dataset_name']}\n"
        md += f"- Benefit: {s['benefit_score']:.3f}\n"
        md += f"- Difficulty concentration: {s['difficulty_concentration']:.3f}\n"
        md += f"- Diversity: {s['diversity_score']:.3f}\n"
        md += f"- Sparse coverage: {s['sparse_coverage']:.3f}\n"
        md += f"- Exotic value: {s['exotic_value']:.3f}\n"
        md += f"- Overfit risk: {s['overfit_risk']:.3f}\n"
        md += f"- Training cost: {s['training_cost']:.3f}\n\n"
    md += "## Do NOT\n\n"
    for item in report.do_not:
        md += f"- {item}\n"
    with open(os.path.join(output_dir, "retraining_priority.md"), "w") as f:
        f.write(md)
