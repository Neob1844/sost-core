"""Orchestrator report — unified active learning summary.

Phase IV.G: Combines coverage, hotspots, proposals, and expansion plan
into a single actionable report.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from ..storage.db import MaterialsDB
from .coverage import analyze_coverage, identify_exotic_niches
from .learning import detect_error_hotspots, generate_retraining_proposals, plan_corpus_expansion

log = logging.getLogger(__name__)

ORCH_DIR = "artifacts/orchestrator"


def generate_orchestrator_report(db: MaterialsDB,
                                 output_dir: str = ORCH_DIR) -> dict:
    """Generate the complete orchestrator report."""
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # Coverage
    coverage = analyze_coverage(db)
    exotic_niches = identify_exotic_niches(coverage)

    # Error hotspots
    hotspots = detect_error_hotspots()

    # Retraining proposals
    proposals = generate_retraining_proposals(hotspots)

    # Expansion plan
    expansion = plan_corpus_expansion()

    # Action summary
    actions = _build_action_summary(coverage, hotspots, proposals, expansion, exotic_niches)

    report = {
        "created_at": now,
        "coverage": coverage.to_dict(),
        "exotic_niches": exotic_niches,
        "error_hotspots": [h.to_dict() for h in hotspots],
        "retraining_proposals": [p.to_dict() for p in proposals],
        "corpus_expansion_plan": [e.to_dict() for e in expansion],
        "action_summary": actions,
        "disclaimer": (
            "This report analyzes the current state of the engine and proposes improvements. "
            "It does NOT retrain models, ingest data, or execute any changes. "
            "All proposals require explicit approval and execution."
        ),
    }

    # Save JSON
    with open(os.path.join(output_dir, "orchestrator_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # Save coverage
    with open(os.path.join(output_dir, "coverage_summary.json"), "w") as f:
        json.dump(coverage.to_dict(), f, indent=2)

    # Save proposals
    with open(os.path.join(output_dir, "retraining_proposals.json"), "w") as f:
        json.dump([p.to_dict() for p in proposals], f, indent=2)

    # Markdown
    _save_markdown(report, output_dir)

    return report


def _build_action_summary(coverage, hotspots, proposals, expansion, niches) -> dict:
    """Build the actionable summary."""
    improve_now = []
    dont_touch = []
    data_to_seek = []
    campaigns_to_repeat = []
    target_attention = []

    # What to improve
    if hotspots:
        improve_now.append(f"Address {len(hotspots)} error hotspot(s) — "
                           f"targets: {', '.join(set(h.target for h in hotspots))}")
    for exp in expansion:
        if exp.priority == "high":
            improve_now.append(f"Ingest {exp.source} (~{exp.estimated_materials} materials, {exp.cost})")

    # What not to touch
    dont_touch.append("Production models (CGCNN FE, ALIGNN-Lite BG) — stable and promoted")
    dont_touch.append("Existing corpus (75,993 JARVIS materials) — do not delete or recreate")

    # Data to seek
    for exp in expansion:
        if exp.priority in ("high", "medium"):
            data_to_seek.append(f"{exp.source}: {exp.estimated_materials} materials ({exp.cost}, {exp.difficulty})")

    # Campaigns to repeat
    for niche in niches:
        if niche.get("coverage") == "sparse":
            campaigns_to_repeat.append(f"Run niche campaign for {niche['niche']} — sparse coverage, high exotic potential")

    # Target attention
    bg_hotspots = sum(1 for h in hotspots if h.target == "band_gap")
    fe_hotspots = sum(1 for h in hotspots if h.target == "formation_energy")
    if bg_hotspots > fe_hotspots:
        target_attention.append("band_gap needs more attention — more error hotspots")
    elif fe_hotspots > bg_hotspots:
        target_attention.append("formation_energy needs more attention")
    else:
        target_attention.append("Both targets are comparable — prioritize by business value")

    return {
        "improve_now": improve_now,
        "dont_touch": dont_touch,
        "data_to_seek": data_to_seek,
        "campaigns_to_repeat": campaigns_to_repeat,
        "target_attention": target_attention,
    }


def _save_markdown(report, output_dir):
    """Save human-readable markdown reports."""
    cov = report["coverage"]
    md = "# Orchestrator Report\n\n"
    md += f"**Corpus:** {cov['total_materials']:,} materials | {cov['total_elements_seen']} elements | {cov['total_spacegroups_seen']} spacegroups\n\n"

    md += "## Chemical Space Coverage\n\n"
    md += f"Dense regions (>5K): {', '.join(cov.get('dense_regions', []))}\n\n"
    md += f"Sparse regions (<50): {', '.join(cov.get('sparse_regions', []))}\n\n"
    md += "### Element count distribution\n| Elements | Count |\n|---|---|\n"
    for k, v in cov.get("n_element_distribution", {}).items():
        md += f"| {k} | {v:,} |\n"

    md += "\n## Exotic Niches\n\n"
    for n in report.get("exotic_niches", []):
        md += f"- **{n['niche']}**: {n['coverage']} coverage, {n['exotic_potential']} potential — {n['recommendation']}\n"

    md += "\n## Error Hotspots\n\n"
    for h in report.get("error_hotspots", []):
        md += f"- **{h['target']}** {h['bucket_type']} '{h['bucket_label']}': MAE={h['mae']:.4f} ({h['sample_count']} samples) — {h['severity']}\n"
    if not report.get("error_hotspots"):
        md += "No significant error hotspots detected.\n"

    md += "\n## Retraining Proposals\n\n"
    for p in report.get("retraining_proposals", []):
        md += f"### {p['proposal_id']} [{p['priority']}]\n"
        md += f"Target: {p['target']} | Reason: {p['reason']}\n"
        md += f"Expected benefit: {p['expected_benefit']}\n"
        md += f"Recommended rung: {p['recommended_rung']}\n\n"

    md += "## Corpus Expansion Plan\n\n"
    md += "| Source | Materials | Cost | Priority | Exotic Value | Status |\n|---|---|---|---|---|---|\n"
    for e in report.get("corpus_expansion_plan", []):
        md += f"| {e['source']} | {e['estimated_materials']} | {e['cost']} | {e['priority']} | {e['value_for_exotic']} | {e['status']} |\n"

    md += "\n## Action Summary\n\n"
    actions = report.get("action_summary", {})
    md += "### Improve Now\n" + "\n".join(f"- {a}" for a in actions.get("improve_now", [])) + "\n\n"
    md += "### Don't Touch\n" + "\n".join(f"- {a}" for a in actions.get("dont_touch", [])) + "\n\n"
    md += "### Data to Seek\n" + "\n".join(f"- {a}" for a in actions.get("data_to_seek", [])) + "\n\n"
    md += "### Target Attention\n" + "\n".join(f"- {a}" for a in actions.get("target_attention", [])) + "\n"

    with open(os.path.join(output_dir, "orchestrator_report.md"), "w") as f:
        f.write(md)

    # Coverage markdown
    cov_md = "# Coverage Summary\n\n"
    cov_md += f"Total: {cov['total_materials']:,} | Elements: {cov['total_elements_seen']} | Spacegroups: {cov['total_spacegroups_seen']}\n\n"
    cov_md += "## Top Elements\n| Element | Count |\n|---|---|\n"
    for el, cnt in list(cov.get("element_counts", {}).items())[:20]:
        cov_md += f"| {el} | {cnt:,} |\n"
    with open(os.path.join(output_dir, "coverage_summary.md"), "w") as f:
        f.write(cov_md)

    # Proposals markdown
    prop_md = "# Retraining Proposals\n\n"
    for p in report.get("retraining_proposals", []):
        prop_md += f"## {p['proposal_id']} [{p['priority']}]\n"
        prop_md += f"- **Target:** {p['target']}\n- **Reason:** {p['reason']}\n"
        prop_md += f"- **Benefit:** {p['expected_benefit']}\n- **Rung:** {p['recommended_rung']}\n\n"
    with open(os.path.join(output_dir, "retraining_proposals.md"), "w") as f:
        f.write(prop_md)
