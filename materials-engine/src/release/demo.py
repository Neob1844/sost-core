"""Public demo surface, golden workflows, operational acceptance.

Phase IV.U: Demo-ready packaging. No new science.
"""

import json
import os
from datetime import datetime, timezone


def generate_demo_surface() -> dict:
    """Define the safe public demo surface."""
    return {
        "version": "3.2.0-RC1",
        "demo_endpoints": [
            {"method": "GET", "path": "/status", "purpose": "Engine health and version", "example": None},
            {"method": "GET", "path": "/stats", "purpose": "Corpus statistics", "example": None},
            {"method": "GET", "path": "/materials?limit=5", "purpose": "Browse materials", "example": None},
            {"method": "GET", "path": "/materials/{id}", "purpose": "Material detail", "example": "materials/e3b0c44298fc1c14"},
            {"method": "GET", "path": "/search?formula=GaAs", "purpose": "Search by formula", "example": "search?formula=GaAs"},
            {"method": "POST", "path": "/predict", "purpose": "Predict properties from CIF", "example": {"cif": "data_...", "target": "band_gap"}},
            {"method": "GET", "path": "/similar/{id}", "purpose": "Find similar materials", "example": None},
            {"method": "GET", "path": "/novelty/material/{id}", "purpose": "Novelty assessment", "example": None},
            {"method": "GET", "path": "/exotic/ranking/10", "purpose": "Top exotic materials", "example": None},
            {"method": "POST", "path": "/shortlist/build", "purpose": "Build ranked shortlist", "example": None},
            {"method": "GET", "path": "/campaigns/presets", "purpose": "Campaign presets", "example": None},
            {"method": "POST", "path": "/campaigns/run", "purpose": "Run discovery campaign", "example": {"campaign_type": "exotic_hunt", "top_k": 5}},
            {"method": "GET", "path": "/frontier/presets", "purpose": "Frontier profiles", "example": None},
            {"method": "GET", "path": "/intelligence/material/{id}", "purpose": "Material intelligence report", "example": None},
            {"method": "GET", "path": "/release/status", "purpose": "Release info", "example": None},
            {"method": "GET", "path": "/release/manifest", "purpose": "Full manifest", "example": None},
        ],
        "do_not_demo": [
            "/selective-retraining/*", "/stratified-retraining/*",
            "/hierarchical-band-gap/*", "/hierarchical-band-gap-calibration/*",
            "/hierarchical-band-gap-regressor/*", "/hierarchical-band-gap-final/*",
            "/three-tier-band-gap/*", "/gate-recall-rescue/*",
            "/retraining-prep/*",
        ],
        "notes": [
            "Demo endpoints are read-only or produce ephemeral results",
            "Research endpoints work but expose unfinished experiments",
            "POST /predict requires valid CIF structure data",
        ],
    }


def generate_golden_workflows() -> list:
    """5 canonical demo workflows."""
    return [
        {
            "name": "Search a Known Material",
            "description": "Find GaAs in the corpus and inspect its properties",
            "steps": [
                {"action": "GET /search?formula=GaAs", "expect": "List of GaAs entries with band_gap, formation_energy"},
                {"action": "GET /materials/{id}", "expect": "Full detail including spacegroup, structure, provenance"},
            ],
            "value": "Demonstrates corpus quality and search capability",
        },
        {
            "name": "Predict Band Gap from Structure",
            "description": "Submit a CIF file and get a band_gap prediction",
            "steps": [
                {"action": "POST /predict", "input": {"cif": "<CIF data>", "target": "band_gap"}, "expect": "Predicted band_gap in eV with model info and confidence"},
            ],
            "value": "Core ML inference — the reason the engine exists",
        },
        {
            "name": "Discover Exotic Materials",
            "description": "Find the most unusual materials in the corpus",
            "steps": [
                {"action": "GET /exotic/ranking/10", "expect": "Top 10 materials by exotic score (rarity + novelty)"},
                {"action": "GET /intelligence/material/{id}", "expect": "Comprehensive report on the most exotic material"},
            ],
            "value": "Shows the engine's ability to surface undiscovered opportunities",
        },
        {
            "name": "Run a Discovery Campaign",
            "description": "Launch a stable_semiconductor_hunt campaign",
            "steps": [
                {"action": "GET /campaigns/presets", "expect": "5 campaign presets with descriptions"},
                {"action": "POST /campaigns/run", "input": {"campaign_type": "stable_semiconductor_hunt", "top_k": 10}, "expect": "Ranked candidates with scores, reasons, and risk flags"},
            ],
            "value": "End-to-end discovery pipeline in one API call",
        },
        {
            "name": "Build a Frontier Shortlist",
            "description": "Multi-objective material selection for dual targets",
            "steps": [
                {"action": "GET /frontier/presets", "expect": "4 frontier profiles (balanced, stable_semi, wide_gap, novelty)"},
                {"action": "POST /frontier/run", "input": {"profile": "balanced_frontier", "top_k": 10}, "expect": "Shortlist with stability, band_gap_fit, novelty, exotic scores"},
            ],
            "value": "Production-grade material selection for research planning",
        },
    ]


def generate_acceptance_checklist(db) -> dict:
    """Operational acceptance verification."""
    checks = []

    # Corpus
    count = db.count()
    checks.append({"check": "Corpus accessible", "status": "PASS" if count > 0 else "FAIL", "detail": f"{count:,} materials"})

    # Models
    import os
    fe_ckpt = "artifacts/training_ladder/rung_20k/cgcnn_formation_energy_best.pt"
    bg_ckpt = "artifacts/training_ladder_band_gap/rung_20k/alignn_band_gap_best.pt"
    checks.append({"check": "FE model checkpoint", "status": "PASS" if os.path.exists(fe_ckpt) else "FAIL", "detail": fe_ckpt})
    checks.append({"check": "BG model checkpoint", "status": "PASS" if os.path.exists(bg_ckpt) else "FAIL", "detail": bg_ckpt})

    # Registry
    reg_path = "artifacts/training/model_registry.json"
    checks.append({"check": "Model registry", "status": "PASS" if os.path.exists(reg_path) else "FAIL", "detail": reg_path})

    # Release artifacts
    for f in ["materials_engine_release_manifest.json", "production_freeze.json", "api_audit.json"]:
        path = os.path.join("artifacts/release", f)
        checks.append({"check": f"Release artifact: {f}", "status": "PASS" if os.path.exists(path) else "FAIL", "detail": path})

    # Benchmark/calibration
    for f in ["benchmark/benchmark_band_gap_42.json", "calibration/calibration_band_gap.json", "calibration/calibration_formation_energy.json"]:
        path = os.path.join("artifacts", f)
        checks.append({"check": f"Artifact: {f}", "status": "PASS" if os.path.exists(path) else "FAIL"})

    all_pass = all(c["status"] == "PASS" for c in checks)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": "ACCEPTED" if all_pass else "CONDITIONAL",
        "checks": checks,
        "pass_count": sum(1 for c in checks if c["status"] == "PASS"),
        "total_checks": len(checks),
    }


def generate_release_notes() -> str:
    """Human-readable release notes."""
    return """# SOST Materials Discovery Engine — Release Notes v3.2.0-RC1

## What It Does
The Materials Discovery Engine is a CPU-friendly ML platform for computational materials science. It ingests crystal structure data, trains GNN models, predicts material properties, and discovers novel materials through automated campaigns.

## Production Models
| Target | Model | MAE | R² | Dataset |
|--------|-------|-----|-----|---------|
| Formation Energy | CGCNN | 0.1528 eV/atom | 0.9499 | 20K materials |
| Band Gap | ALIGNN-Lite | 0.3422 eV | 0.707 | 20K materials |

## Corpus
- **76,193 materials** from JARVIS (75,993) + AFLOW pilot (200)
- 89 elements, 213 spacegroups, 7 crystal systems
- 99.74% have validated crystal structures
- 100% have formation energy, 99.9% have band gap

## Key Capabilities
- **Search**: Formula, element, property range, source filtering
- **Predict**: Band gap and formation energy from CIF structure
- **Discover**: Novelty scoring, exotic ranking, campaign engine
- **Analyze**: Frontier selection, intelligence reports, dossiers
- **Validate**: Benchmark suite, calibration, evidence bridge

## API
- **145 endpoints** (105 production, 40 research)
- FastAPI with OpenAPI docs at /docs
- JSON responses, no authentication required for read

## Research Watchlist
- **Hierarchical band gap pipeline**: 24% better overall MAE but narrow-gap regression blocks promotion
- **9 optimization phases** (IV.L→IV.S): 22+ models trained, gate/specialist/calibration explored
- Architecture proven correct; binary gate threshold tradeoff remains unsolved

## Limitations
- Band gap MAE=0.34 eV — useful baseline, not state-of-art
- No bulk/shear modulus predictions
- External sources (AFLOW, MP, COD) unreachable from current environment
- CPU-only training limits model depth
- Hierarchical pipeline not promoted

## What's Next
- Deploy API on production VPS
- Acquire Materials Project API key
- GeoForge unified platform integration
- Blockchain proof-of-discovery (Phase V)

---
*Built with SOST Protocol. 41 test files. Zero external ML dependencies beyond PyTorch + pymatgen.*
"""


def save_all_demo_artifacts(demo_surface, workflows, acceptance, release_notes,
                            output_dir="artifacts/release"):
    """Save all demo/acceptance artifacts."""
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "public_demo_surface.json"), "w") as f:
        json.dump(demo_surface, f, indent=2)
    md = "# Public Demo Surface\n\n## Recommended Endpoints\n\n| Method | Path | Purpose |\n|--------|------|---------|\n"
    for ep in demo_surface["demo_endpoints"]:
        md += f"| {ep['method']} | `{ep['path']}` | {ep['purpose']} |\n"
    md += "\n## Do NOT Demo\n"
    for p in demo_surface["do_not_demo"]:
        md += f"- `{p}`\n"
    with open(os.path.join(output_dir, "public_demo_surface.md"), "w") as f:
        f.write(md)

    with open(os.path.join(output_dir, "golden_workflows.json"), "w") as f:
        json.dump(workflows, f, indent=2)
    md = "# Golden Workflows\n\n"
    for i, wf in enumerate(workflows, 1):
        md += f"## {i}. {wf['name']}\n{wf['description']}\n\n"
        for step in wf["steps"]:
            md += f"- `{step['action']}`\n"
        md += f"\n**Value**: {wf['value']}\n\n"
    with open(os.path.join(output_dir, "golden_workflows.md"), "w") as f:
        f.write(md)

    with open(os.path.join(output_dir, "operational_acceptance.json"), "w") as f:
        json.dump(acceptance, f, indent=2)
    md = f"# Operational Acceptance: **{acceptance['overall']}**\n\n"
    md += f"Passed: {acceptance['pass_count']}/{acceptance['total_checks']}\n\n"
    md += "| Check | Status |\n|-------|--------|\n"
    for c in acceptance["checks"]:
        md += f"| {c['check']} | {c['status']} |\n"
    with open(os.path.join(output_dir, "operational_acceptance.md"), "w") as f:
        f.write(md)

    with open(os.path.join(output_dir, "release_notes_v3_2_rc1.md"), "w") as f:
        f.write(release_notes)
