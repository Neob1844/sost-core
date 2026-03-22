"""Release manifest and production freeze for Materials Engine.

Phase IV.T: Engine stabilization. No new experiments.
"""

import json
import os
from datetime import datetime, timezone


def generate_release_manifest(db, app) -> dict:
    """Generate the complete release manifest."""
    now = datetime.now(timezone.utc).isoformat()
    audit = db.audit_counts()
    stats = db.stats()

    # Registry
    reg_path = "artifacts/training/model_registry.json"
    registry = []
    if os.path.exists(reg_path):
        with open(reg_path) as f:
            registry = json.load(f)

    production_models = [r for r in registry if r.get("promoted_for_production")]
    research_models = [r for r in registry if not r.get("promoted_for_production")]

    # Count endpoints
    endpoints = []
    for route in app.routes:
        if not hasattr(route, 'methods') or route.path in ('/openapi.json', '/docs', '/redoc', '/docs/oauth2-redirect'):
            continue
        methods = list(route.methods - {'HEAD', 'OPTIONS'})
        if methods:
            endpoints.append({"method": methods[0], "path": route.path, "name": getattr(route, 'name', '')})

    # Classify endpoints
    production_endpoints = []
    research_endpoints = []
    for ep in sorted(endpoints, key=lambda x: x["path"]):
        path = ep["path"]
        if any(path.startswith(p) for p in [
            "/status", "/health", "/stats", "/materials", "/search", "/predict",
            "/similar", "/novelty", "/candidates", "/shortlist", "/campaigns",
            "/generation", "/frontier", "/intelligence", "/corpus-sources",
            "/analytics", "/audit", "/benchmark", "/calibration", "/evidence",
            "/learning", "/orchestrator", "/validation", "/retrieval",
            "/niche", "/triage", "/retraining-prep"
        ]):
            production_endpoints.append(ep)
        else:
            research_endpoints.append(ep)

    manifest = {
        "version": "3.2.0",
        "release_candidate": "RC1",
        "phase": "IV.T — Engine Stabilization",
        "created_at": now,
        "corpus": {
            "total_materials": audit["total"],
            "sources": stats["by_source"],
            "with_formation_energy": audit["with_formation_energy"],
            "with_band_gap": audit["with_band_gap"],
            "with_spacegroup": audit["with_spacegroup"],
            "with_valid_structure": audit["with_valid_structure"],
            "crystal_systems": stats["by_crystal_system"],
        },
        "production_models": [
            {
                "target": m["target"],
                "architecture": m["model"],
                "dataset_size": m.get("dataset_size"),
                "test_mae": m["test_mae"],
                "test_r2": m.get("test_r2"),
                "checkpoint": m.get("checkpoint"),
                "phase": m.get("ladder_phase", ""),
            }
            for m in production_models
        ],
        "research_branches": {
            "hierarchical_band_gap": {
                "status": "watchlist",
                "best_pipeline_mae": 0.2596,
                "blocker": "narrow-gap regression (+0.10 vs production)",
                "phases": "IV.N through IV.S (8 phases, 22+ models)",
                "conclusion": "Architecture proven but gate tradeoff unsolved",
            },
        },
        "api": {
            "total_endpoints": len(endpoints),
            "production_ready": len(production_endpoints),
            "research_internal": len(research_endpoints),
        },
        "tests": {
            "test_files": len([f for f in os.listdir("tests") if f.startswith("test_") and f.endswith(".py")]),
        },
        "artifacts": {
            "total_dirs": len([d for d in os.listdir("artifacts") if os.path.isdir(os.path.join("artifacts", d))]),
        },
        "limitations": [
            "Band gap prediction MAE=0.34 eV — acceptable baseline, not state-of-art",
            "No bulk modulus or shear modulus predictions yet",
            "External data sources (AFLOW, MP, COD) unreachable from current environment",
            "CPU-only training — GPU would improve convergence and allow deeper models",
            "Hierarchical BG pipeline not promoted due to narrow-gap tradeoff",
        ],
        "next_steps": [
            "Deploy API on production VPS",
            "Acquire Materials Project API key for corpus expansion",
            "Consider GPU-accelerated training for deeper architectures",
            "Blockchain proof-of-discovery integration (Phase V)",
        ],
    }
    return manifest


def generate_production_freeze(db) -> dict:
    """Generate production freeze document."""
    now = datetime.now(timezone.utc).isoformat()
    reg_path = "artifacts/training/model_registry.json"
    registry = []
    if os.path.exists(reg_path):
        with open(reg_path) as f:
            registry = json.load(f)

    return {
        "freeze_date": now,
        "version": "3.2.0",
        "production_models": {
            "formation_energy": {
                "model": "cgcnn",
                "dataset": "rung_20k (20,000 materials, random sample)",
                "test_mae": 0.1528,
                "test_rmse": 0.2271,
                "test_r2": 0.9499,
                "checkpoint": "artifacts/training_ladder/rung_20k/cgcnn_formation_energy_best.pt",
                "status": "PRODUCTION — stable, no changes needed",
                "promoted_in": "Phase IV.A",
            },
            "band_gap": {
                "model": "alignn_lite",
                "dataset": "rung_20k (20,000 materials, random sample)",
                "test_mae": 0.3422,
                "test_rmse": 0.7362,
                "test_r2": 0.707,
                "checkpoint": "artifacts/training_ladder_band_gap/rung_20k/alignn_band_gap_best.pt",
                "status": "PRODUCTION — stable after 9 phases of optimization attempts",
                "promoted_in": "Phase IV.B",
                "optimization_history": "IV.L→IV.S: 9 phases, 22+ challengers, none beat production on all criteria",
            },
        },
        "research_watchlist": {
            "hierarchical_band_gap": {
                "status": "WATCHLIST — not promoted",
                "best_overall_mae": 0.2596,
                "improvement_vs_production": "24% overall, but narrow-gap regression",
                "components": [
                    "Metal gate: CGCNN, 90.8% accuracy",
                    "Narrow-gap specialist: ALIGNN-Lite, MAE=0.2221 on 0.05-1.0 eV",
                    "General regressor: ALIGNN-Lite, MAE=0.6654 on non-metals",
                ],
                "blocker": "Gate threshold tradeoff — can't preserve metals AND fix narrow-gap simultaneously",
                "recommendation": "Soft-output gate or external training data needed for next attempt",
            },
        },
        "do_not_change": [
            "Do NOT modify model_registry.json without CTO approval",
            "Do NOT retrain production models without full benchmark validation",
            "Do NOT promote hierarchical pipeline without solving narrow-gap regression",
            "Do NOT delete any checkpoint files — they are the reproducibility chain",
        ],
        "registry": registry,
    }


def generate_api_audit(app) -> list:
    """Classify all API endpoints."""
    production_prefixes = [
        "/status", "/health", "/stats", "/materials", "/search", "/predict",
        "/similar", "/novelty", "/candidates", "/shortlist", "/campaigns",
        "/generation", "/frontier", "/intelligence", "/corpus-sources",
        "/analytics", "/audit", "/benchmark", "/calibration", "/evidence",
        "/learning", "/orchestrator", "/validation", "/retrieval",
        "/niche", "/triage", "/retraining-prep",
    ]
    research_prefixes = [
        "/selective-retraining", "/stratified-retraining",
        "/hierarchical-band-gap", "/three-tier-band-gap",
        "/gate-recall-rescue",
    ]

    entries = []
    for route in app.routes:
        if not hasattr(route, 'methods') or route.path in ('/openapi.json', '/docs', '/redoc', '/docs/oauth2-redirect'):
            continue
        methods = list(route.methods - {'HEAD', 'OPTIONS'})
        if not methods:
            continue
        path = route.path
        if any(path.startswith(p) for p in research_prefixes):
            level = "research"
            safe = False
        elif any(path.startswith(p) for p in production_prefixes):
            level = "production"
            safe = True
        elif path.startswith("/release"):
            level = "production"
            safe = True
        else:
            level = "internal"
            safe = False

        entries.append({
            "method": methods[0], "path": path,
            "stability": level, "safe_for_demo": safe,
        })

    return sorted(entries, key=lambda x: (x["stability"], x["path"]))


def save_all_release_artifacts(manifest, freeze, api_audit, output_dir="artifacts/release"):
    """Save all release artifacts."""
    os.makedirs(output_dir, exist_ok=True)

    # Manifest
    with open(os.path.join(output_dir, "materials_engine_release_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    md = f"# Materials Engine Release Manifest — v{manifest['version']} {manifest['release_candidate']}\n\n"
    md += f"## Corpus\n- Total: {manifest['corpus']['total_materials']:,}\n"
    md += f"- Sources: {manifest['corpus']['sources']}\n"
    md += f"- With FE: {manifest['corpus']['with_formation_energy']:,}\n"
    md += f"- With BG: {manifest['corpus']['with_band_gap']:,}\n\n"
    md += "## Production Models\n"
    for m in manifest["production_models"]:
        md += f"- **{m['target']}**: {m['architecture']} ({m['dataset_size']:,}), MAE={m['test_mae']}\n"
    md += f"\n## API: {manifest['api']['total_endpoints']} endpoints ({manifest['api']['production_ready']} production, {manifest['api']['research_internal']} research)\n"
    md += f"\n## Limitations\n"
    for l in manifest["limitations"]:
        md += f"- {l}\n"
    with open(os.path.join(output_dir, "materials_engine_release_manifest.md"), "w") as f:
        f.write(md)

    # Freeze
    with open(os.path.join(output_dir, "production_freeze.json"), "w") as f:
        json.dump(freeze, f, indent=2)
    md = "# Production Freeze\n\n"
    for target, m in freeze["production_models"].items():
        md += f"## {target}\n- Model: {m['model']}\n- MAE: {m['test_mae']}\n- Status: {m['status']}\n\n"
    md += "## Do NOT Change\n"
    for d in freeze["do_not_change"]:
        md += f"- {d}\n"
    with open(os.path.join(output_dir, "production_freeze.md"), "w") as f:
        f.write(md)

    # API Audit
    with open(os.path.join(output_dir, "api_audit.json"), "w") as f:
        json.dump(api_audit, f, indent=2)
    prod = [e for e in api_audit if e["stability"] == "production"]
    res = [e for e in api_audit if e["stability"] == "research"]
    md = f"# API Audit — {len(api_audit)} endpoints\n\n"
    md += f"## Production ({len(prod)})\n| Method | Path |\n|--------|------|\n"
    for e in prod:
        md += f"| {e['method']} | {e['path']} |\n"
    md += f"\n## Research ({len(res)})\n| Method | Path |\n|--------|------|\n"
    for e in res:
        md += f"| {e['method']} | {e['path']} |\n"
    with open(os.path.join(output_dir, "api_audit.md"), "w") as f:
        f.write(md)
