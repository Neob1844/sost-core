#!/usr/bin/env python3
"""Phase V.B Campaign Runner — Direct GNN autonomous campaigns.

Runs the 6 mandatory campaigns with the new direct GNN pipeline:
1. GaAs + AlN (III-V semiconductors)
2. TiO2 + ZnO (oxide semiconductors)
3. Si + Ge (group IV)
4. stable_novel_semiconductors (profile-driven)
5. valuable_unknowns (profile-driven)
6. strategic_materials_search (profile-driven)

Each campaign produces a detailed report with Phase V.B metrics.
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from autonomous_discovery.engine import DiscoveryEngine

OUTPUT_DIR = os.path.expanduser("~/SOST/sostcore/sost-core/materials-engine/artifacts/campaigns_vii")

CAMPAIGNS = [
    {
        "name": "iii_v_semiconductors",
        "profile": "stable_novel_semiconductors",
        "seeds": [("GaAs", "AlN"), ("InP", "GaN"), ("AlAs", "GaP")],
        "iterations": 3,
        "max_candidates": 20,
        "description": "III-V semiconductor space via GaAs+AlN seed",
    },
    {
        "name": "oxide_semiconductors",
        "profile": "stable_novel_semiconductors",
        "seeds": [("TiO2", "ZnO"), ("MgO", "ZrO2"), ("Cu2O", "ZnO")],
        "iterations": 3,
        "max_candidates": 20,
        "description": "Oxide semiconductor space via TiO2+ZnO seed",
    },
    {
        "name": "group_iv",
        "profile": "stable_novel_semiconductors",
        "seeds": [("Si", "Ge"), ("SiC", "BN"), ("Si", "SiC")],
        "iterations": 3,
        "max_candidates": 20,
        "description": "Group IV semiconductor space via Si+Ge seed",
    },
    {
        "name": "stable_novel_semiconductors",
        "profile": "stable_novel_semiconductors",
        "seeds": None,  # use defaults
        "iterations": 3,
        "max_candidates": 25,
        "description": "Broad semiconductor discovery campaign",
    },
    {
        "name": "valuable_unknowns",
        "profile": "valuable_unknowns",
        "seeds": None,
        "iterations": 3,
        "max_candidates": 25,
        "description": "High-value unknown materials campaign",
    },
    {
        "name": "strategic_materials_search",
        "profile": "strategic_materials_search",
        "seeds": None,
        "iterations": 3,
        "max_candidates": 25,
        "description": "Strategic materials discovery campaign",
    },
    {
        "name": "battery_relevant",
        "profile": "battery_relevant",
        "seeds": [("LiCoO2", "NiO"), ("Fe2O3", "Al2O3"), ("MgO", "ZrO2")],
        "iterations": 3,
        "max_candidates": 25,
        "description": "Battery-relevant materials campaign",
    },
    {
        "name": "exploratory_oxides",
        "profile": "exploratory_oxides",
        "seeds": [("TiO2", "ZnO"), ("Fe2O3", "Al2O3"), ("BaTiO3", "SrTiO3")],
        "iterations": 3,
        "max_candidates": 25,
        "description": "Oxide-focused exploratory campaign",
    },
    {
        "name": "high_uncertainty_probe",
        "profile": "high_uncertainty_probe",
        "seeds": None,
        "iterations": 3,
        "max_candidates": 25,
        "description": "High-uncertainty region exploration for corpus expansion",
    },
]


def run_single_campaign(config):
    """Run a single campaign and return results."""
    print(f"\n{'='*70}")
    print(f"CAMPAIGN: {config['name']}")
    print(f"Profile: {config['profile']}")
    print(f"Description: {config['description']}")
    print(f"{'='*70}")

    memory_path = os.path.join(OUTPUT_DIR, f"memory_{config['name']}.json")

    engine = DiscoveryEngine(
        profile_name=config["profile"],
        memory_path=memory_path,
        seeds=config.get("seeds"),
    )

    t0 = time.time()
    campaign = engine.run_campaign(
        n_iterations=config["iterations"],
        max_candidates_per_iter=config["max_candidates"],
    )
    elapsed = round(time.time() - t0, 2)

    # Phase V.B metrics
    metrics = compute_vb_metrics(campaign)

    result = {
        "campaign_name": config["name"],
        "campaign_config": config,
        "elapsed_s": elapsed,
        "campaign_results": campaign,
        "phase_vb_metrics": metrics,
    }

    # Print summary
    print(f"\n--- Campaign {config['name']} Summary ---")
    print(f"  Iterations: {campaign['iterations']}")
    print(f"  Total generated: {campaign['total_generated']}")
    print(f"  Total accepted: {campaign['total_accepted']}")
    print(f"  Accept rate: {campaign['accept_rate']}")
    print(f"  Elapsed: {elapsed}s")
    print(f"\n  Phase V.B Metrics:")
    for k, v in metrics.items():
        print(f"    {k}: {v}")

    if campaign.get("top_candidates_overall"):
        print(f"\n  Top 5 Candidates:")
        for c in campaign["top_candidates_overall"][:5]:
            origin = c.get("prediction_origin", "unknown")
            fe = c.get("direct_fe_value")
            bg = c.get("direct_bg_value")
            fe_str = f"FE={fe:.3f}" if fe is not None else "FE=—"
            bg_str = f"BG={bg:.3f}" if bg is not None else "BG=—"
            print(f"    #{c['rank']}: {c['formula']:12s}  score={c['composite_score']:.4f}  "
                  f"origin={origin:20s}  {fe_str}  {bg_str}  "
                  f"validation={c.get('validation', '?')}")

    return result


def compute_vb_metrics(campaign):
    """Compute Phase V.B quality metrics from campaign results."""
    all_candidates = []
    for r in campaign.get("iteration_reports", []):
        all_candidates.extend(r.get("top_candidates", []))

    if not all_candidates:
        return {"error": "no candidates"}

    total = len(all_candidates)
    top10 = all_candidates[:10] if len(all_candidates) >= 10 else all_candidates

    # Count by prediction origin
    origins = [c.get("prediction_origin", "unavailable") for c in all_candidates]
    direct_gnn_count = sum(1 for o in origins if o == "direct_gnn_lifted")
    known_exact_count = sum(1 for o in origins if o == "known_exact")
    proxy_count = sum(1 for o in origins if o in ("proxy_only", "unavailable"))

    # Count direct inference successes
    fe_success = sum(1 for c in all_candidates
                     if c.get("direct_fe_value") is not None)
    bg_success = sum(1 for c in all_candidates
                     if c.get("direct_bg_value") is not None)

    # Top 10 analysis
    top10_origins = [c.get("prediction_origin", "unavailable") for c in top10]
    top10_known = sum(1 for o in top10_origins if o == "known_exact")
    top10_new = sum(1 for o in top10_origins if o in ("direct_gnn_lifted", "proxy_only"))
    top10_direct_gnn = sum(1 for o in top10_origins if o == "direct_gnn_lifted")

    top10_scores = [c.get("composite_score", 0) for c in top10]
    top10_plaus = [c.get("scores", {}).get("plausibility", 0) if isinstance(c.get("scores"), dict)
                   else 0 for c in top10]

    # Validation tiers
    validations = [c.get("validation", "unknown") for c in all_candidates]
    priority_val = sum(1 for v in validations if v == "priority_validation")
    val_cand = sum(1 for v in validations if v == "validation_candidate")
    known_ref = sum(1 for v in validations if v == "known_reference")

    return {
        "total_candidates": total,
        "direct_fe_inference_rate": round(fe_success / max(total, 1), 4),
        "direct_bg_inference_rate": round(bg_success / max(total, 1), 4),
        "direct_gnn_rate": round(direct_gnn_count / max(total, 1), 4),
        "proxy_dependency_rate": round(proxy_count / max(total, 1), 4),
        "known_material_rate": round(known_exact_count / max(total, 1), 4),
        "known_material_top10_share": round(top10_known / max(len(top10), 1), 4),
        "new_candidate_top10_share": round(top10_new / max(len(top10), 1), 4),
        "direct_gnn_top10_share": round(top10_direct_gnn / max(len(top10), 1), 4),
        "mean_top10_score": round(sum(top10_scores) / max(len(top10_scores), 1), 4),
        "mean_top10_plausibility": round(sum(top10_plaus) / max(len(top10_plaus), 1), 4),
        "priority_validation_count": priority_val,
        "validation_candidate_count": val_cand,
        "known_reference_count": known_ref,
        # Phase VII metrics
        "mean_uncertainty": round(sum(c.get("uncertainty_score", 0.5) for c in all_candidates) / max(total, 1), 4),
        "mean_confidence": round(sum(c.get("confidence_score", 0.5) for c in all_candidates) / max(total, 1), 4),
        "mean_validation_readiness": round(sum(c.get("validation_readiness", 0) for c in all_candidates) / max(total, 1), 4),
        "dft_handoff_ready_count": sum(1 for c in all_candidates if c.get("dft_handoff_ready", False)),
        "mean_top10_uncertainty": round(sum(c.get("uncertainty_score", 0.5) for c in top10) / max(len(top10), 1), 4),
        "mean_top10_confidence": round(sum(c.get("confidence_score", 0.5) for c in top10) / max(len(top10), 1), 4),
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_results = []
    all_metrics = {}

    for config in CAMPAIGNS:
        try:
            result = run_single_campaign(config)
            all_results.append(result)
            all_metrics[config["name"]] = result["phase_vb_metrics"]

            # Save individual campaign
            path = os.path.join(OUTPUT_DIR, f"campaign_{config['name']}.json")
            with open(path, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Saved: {path}")

        except Exception as e:
            print(f"\n  ERROR in campaign {config['name']}: {e}")
            import traceback
            traceback.print_exc()
            all_metrics[config["name"]] = {"error": str(e)}

    # Save aggregate summary
    summary = {
        "phase": "V.B",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "campaigns_run": len(all_results),
        "campaigns_total": len(CAMPAIGNS),
        "metrics_by_campaign": all_metrics,
        "aggregate_metrics": compute_aggregate_metrics(all_metrics),
    }

    summary_path = os.path.join(OUTPUT_DIR, "phase_vb_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"Phase V.B Campaign Run Complete")
    print(f"{'='*70}")
    print(f"Campaigns: {len(all_results)}/{len(CAMPAIGNS)}")
    print(f"Summary: {summary_path}")
    print(f"\nAggregate Metrics:")
    for k, v in summary.get("aggregate_metrics", {}).items():
        print(f"  {k}: {v}")


def compute_aggregate_metrics(metrics_by_campaign):
    """Average metrics across all campaigns."""
    keys = ["direct_fe_inference_rate", "direct_bg_inference_rate",
            "direct_gnn_rate", "proxy_dependency_rate",
            "known_material_top10_share", "new_candidate_top10_share",
            "mean_top10_score", "mean_top10_plausibility"]

    agg = {}
    for key in keys:
        vals = [m.get(key, 0) for m in metrics_by_campaign.values()
                if isinstance(m, dict) and key in m]
        if vals:
            agg[f"avg_{key}"] = round(sum(vals) / len(vals), 4)

    return agg


if __name__ == "__main__":
    main()
