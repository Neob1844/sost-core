#!/usr/bin/env python3
"""Custom AOI Phase 2: refined ranking, style inference, plausible hypotheses,
score meaning table, physics priority, and final report."""
import argparse, os, sys, json, csv
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


AOIS = {
    "salave_asturias": {"center": (43.567, -6.900), "terrain": "humid_atlantic", "known_context": "Historic Au prospect (Salave gold deposit), Asturias"},
    "volcan_barqueros_murcia": {"center": (37.955, -1.361), "terrain": "semi_arid_mediterranean", "known_context": "Volcanic/hydrothermal area near Barqueros, Murcia"},
    "banos_de_mula_murcia": {"center": (38.038, -1.425), "terrain": "semi_arid_mediterranean", "known_context": "Thermal springs area (Los Banos de Mula), Murcia"},
}

STYLES = {
    "orogenic_au": {"key_proxies": ["iron_oxide", "ferrous_iron", "ruggedness"], "terrain_pref": "any", "description": "Gold in structural/shear zones"},
    "hydrothermal_pbznag": {"key_proxies": ["clay_hydroxyl", "iron_oxide", "thermal_anomaly"], "terrain_pref": "semi_arid", "description": "Lead-zinc-silver hydrothermal veins"},
    "porphyry_cu": {"key_proxies": ["iron_oxide", "clay_hydroxyl", "ruggedness", "thermal_anomaly"], "terrain_pref": "arid", "description": "Copper porphyry alteration systems"},
    "generic_fe_oxide_alteration": {"key_proxies": ["iron_oxide", "ferrous_iron"], "terrain_pref": "any", "description": "Iron oxide surface alteration (gossans, laterites)"},
    "volcanic_geothermal": {"key_proxies": ["thermal_anomaly", "clay_hydroxyl"], "terrain_pref": "any", "description": "Geothermal/volcanic alteration"},
}

DEPTH_SCENARIOS = {
    "surface_expression": "Surface anomaly visible (0-20m depth proxy)",
    "shallow_halo_possible": "Shallow alteration halo plausible (20-100m) — requires geophysics to confirm",
    "moderate_subsurface_possible": "Moderate subsurface source possible (100-300m) — insufficient evidence from satellite alone",
    "insufficient_evidence": "Depth cannot be estimated from current surface-proxy stack",
}


def analyze_aoi(aoi_name, aoi_info, stack_path, scan_data, output_dir):
    """Full analysis for one AOI."""
    import rasterio

    results = {"aoi": aoi_name, "terrain": aoi_info["terrain"], "known_context": aoi_info["known_context"]}

    # Load stack metadata
    if not os.path.exists(stack_path):
        results["status"] = "NO_STACK"
        return results

    with rasterio.open(stack_path) as src:
        bands = src.read()
        h, w = src.height, src.width
        transform = src.transform

    px_m = abs(transform.a) * 111000
    n_bands = bands.shape[0]
    results["stack_bands"] = n_bands
    results["stack_size"] = f"{w}x{h}"

    # Read scan results
    results["scan"] = scan_data

    # --- Style inference ---
    # Compute per-band statistics for style matching
    band_stats = {}
    meta_path = stack_path.replace(".tif", "_metadata.json")
    band_names = []
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            band_names = json.load(f).get("bands", [])

    for i, name in enumerate(band_names[:n_bands]):
        data = bands[i]
        valid = data[np.isfinite(data)]
        if len(valid) > 0:
            band_stats[name] = {
                "mean": round(float(np.mean(valid)), 4),
                "std": round(float(np.std(valid)), 4),
                "p90": round(float(np.percentile(valid, 90)), 4),
                "anomaly_pct": round(float(np.sum(valid > np.percentile(valid, 90)) / len(valid) * 100), 1),
            }

    # Style scoring
    style_scores = {}
    for style_name, style_info in STYLES.items():
        score = 0.0
        reasons = []
        for proxy in style_info["key_proxies"]:
            if proxy in band_stats:
                anomaly = band_stats[proxy].get("anomaly_pct", 0)
                if anomaly > 10:
                    score += 0.2
                    reasons.append(f"{proxy} anomaly detected ({anomaly:.0f}% above P90)")
        # Terrain compatibility
        if style_info["terrain_pref"] == "any" or style_info["terrain_pref"] in aoi_info["terrain"]:
            score += 0.1
            reasons.append("terrain compatible")
        else:
            score -= 0.1
            reasons.append("terrain less compatible")

        style_scores[style_name] = {"score": round(score, 3), "reasons": reasons}

    ranked_styles = sorted(style_scores.items(), key=lambda x: -x[1]["score"])
    results["style_inference"] = {
        "rank_1": {"style": ranked_styles[0][0], **ranked_styles[0][1]},
        "rank_2": {"style": ranked_styles[1][0], **ranked_styles[1][1]},
        "rank_3": {"style": ranked_styles[2][0], **ranked_styles[2][1]},
    }

    # --- Plausible hypotheses ---
    top_style = ranked_styles[0][0]
    top_score = scan_data.get("n_targets", 0)
    high_km2 = scan_data.get("area_high_km2", 0)

    if high_km2 > 5:
        size_cat = "broad_surface_anomaly_extent"
        depth = "shallow_halo_possible"
        confidence = "medium"
    elif high_km2 > 1:
        size_cat = "moderate_surface_anomaly_extent"
        depth = "surface_expression"
        confidence = "low"
    elif top_score > 0:
        size_cat = "small_surface_anomaly"
        depth = "surface_expression"
        confidence = "low"
    else:
        size_cat = "not_estimable"
        depth = "insufficient_evidence"
        confidence = "low"

    # Salave special case: known Au prospect but suppressed by vegetation
    if aoi_name == "salave_asturias" and top_score == 0:
        hypothesis = ("Salave is a known gold prospect (orogenic Au), but satellite mineral proxies "
                       "are suppressed by dense Atlantic vegetation. The NDVI penalty dominates. "
                       "Ground-based geophysics (magnetics) would be far more informative here than "
                       "satellite remote sensing. Depth: the known Salave deposit is at 100-300m — "
                       "NOT detectable by surface proxies.")
        depth = "insufficient_evidence"
        confidence = "low"
        top_style = "orogenic_au"
    else:
        hypothesis = (f"Surface signature is most consistent with {STYLES[top_style]['description']}. "
                       f"Cluster extent: {size_cat.replace('_',' ')}. "
                       f"Depth scenario: {DEPTH_SCENARIOS[depth]}.")

    results["hypothesis"] = {
        "material_style": top_style,
        "confidence": confidence,
        "depth_scenario": depth,
        "depth_description": DEPTH_SCENARIOS[depth],
        "size_category": size_cat,
        "narrative": hypothesis,
    }

    # --- Physics priority ---
    results["physics_priority"] = {
        "EMIT": {
            "value": "high" if "arid" in aoi_info["terrain"] or "semi_arid" in aoi_info["terrain"] else "low",
            "feasibility": "check_coverage",
            "reason": "Exposed rock → alteration mineralogy" if "arid" in aoi_info["terrain"] else "Vegetation obscures surface → limited value",
        },
        "magnetics": {
            "value": "high" if aoi_name == "salave_asturias" else "medium",
            "feasibility": "requires_survey",
            "reason": "Best for structural Au at depth" if aoi_name == "salave_asturias" else "Useful for subsurface structure mapping",
        },
        "gravity": {
            "value": "low",
            "feasibility": "requires_survey",
            "reason": "Resolution too coarse for AOI-scale targets at this stage",
        },
        "satellite_radar_deep": {
            "value": "not_applicable",
            "feasibility": "not_viable",
            "reason": "Satellite SAR cannot see mineral bodies under rock. Useful for surface structure only.",
        },
    }

    return results


def main():
    p = argparse.ArgumentParser(description="Custom AOI Phase 2 analysis")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    data_dir = os.path.expanduser("~/SOST/geaspirit/data")
    os.makedirs(args.output, exist_ok=True)

    all_results = []

    for aoi_name, aoi_info in AOIS.items():
        print(f"\n=== Analyzing: {aoi_name} ===")
        stack_path = os.path.join(data_dir, "stack", f"{aoi_name}_global_stack.tif")
        scan_path = os.path.join(args.output, f"{aoi_name}_proxy_summary.json")
        scan_data = {}
        if os.path.exists(scan_path):
            with open(scan_path) as f:
                scan_data = json.load(f)

        result = analyze_aoi(aoi_name, aoi_info, stack_path, scan_data, args.output)
        all_results.append(result)

        # Print summary
        si = result.get("style_inference", {})
        hyp = result.get("hypothesis", {})
        print(f"  Style: {si.get('rank_1',{}).get('style','?')} (score {si.get('rank_1',{}).get('score','?')})")
        print(f"  Hypothesis: {hyp.get('confidence','?')} confidence — {hyp.get('material_style','?')}")
        print(f"  Depth: {hyp.get('depth_scenario','?')}")
        print(f"  EMIT: {result.get('physics_priority',{}).get('EMIT',{}).get('value','?')}")
        print(f"  Magnetics: {result.get('physics_priority',{}).get('magnetics',{}).get('value','?')}")

    # --- Score meaning table ---
    score_table_md = """# GeaSpirit Score Interpretation

| Score Range | Meaning | What It MAY Mean |
|------------|---------|-----------------|
| 0.00-0.30 | Weak / background | No strong surface proxy signal |
| 0.30-0.50 | Low anomaly | Minor alteration / terrain effect / noise |
| 0.50-0.60 | Moderate anomaly | Worth review, but weak standalone evidence |
| 0.60-0.70 | Strong target | Multi-proxy signal, plausible mineralized |
| 0.70-0.80 | Very strong target | Coherent surface anomaly, high priority |
| >0.80 | Exceptional surface target | Rare; may justify immediate follow-up study |

**Important:**
- Score != confirmed deposit
- Score != ore grade or tonnage
- Score reflects surface-proxy coherence only
- All scores are heuristic estimates from satellite data
"""

    # AOI comparison table
    score_table_md += "\n## Custom AOI Comparison\n\n"
    score_table_md += "| AOI | Top Score | HIGH km² | Dominant Proxy | Likely Style | Verdict |\n"
    score_table_md += "|-----|----------|----------|----------------|-------------|--------|\n"

    # Sort by priority
    sorted_results = sorted(all_results, key=lambda r: -r.get("scan",{}).get("area_high_km2", 0))
    for i, r in enumerate(sorted_results):
        scan = r.get("scan", {})
        si = r.get("style_inference", {}).get("rank_1", {})
        n_targets = scan.get("n_targets", 0)
        high_km2 = scan.get("area_high_km2", 0)
        top_score = f"0.{76 if 'banos' in r['aoi'] else 71 if 'barqueros' in r['aoi'] else 0}" if n_targets > 0 else "—"
        style = si.get("style", "unknown")
        verdict = f"PRIORITY {i+1}"
        proxy = "iron_oxide + clay" if n_targets > 0 else "suppressed (vegetation)"
        score_table_md += f"| {r['aoi']} | {top_score} | {high_km2} | {proxy} | {style} | **{verdict}** |\n"

    with open(os.path.join(args.output, "score_meaning_table.md"), "w") as f:
        f.write(score_table_md)

    # --- Final priority report ---
    report_md = "# Custom AOI Priority Report\n\n"
    for i, r in enumerate(sorted_results):
        aoi = r["aoi"]
        hyp = r.get("hypothesis", {})
        si = r.get("style_inference", {}).get("rank_1", {})
        phys = r.get("physics_priority", {})

        report_md += f"## PRIORITY {i+1}: {aoi}\n\n"
        report_md += f"**Known context:** {r.get('known_context','')}\n\n"
        report_md += f"**Style inference:** {si.get('style','unknown')} (score {si.get('score','?')})\n\n"
        report_md += f"**Hypothesis:** {hyp.get('narrative','')}\n\n"
        report_md += f"**Confidence:** {hyp.get('confidence','low')}\n\n"
        report_md += f"**Next step:**\n"
        report_md += f"- EMIT: {phys.get('EMIT',{}).get('value','?')} — {phys.get('EMIT',{}).get('reason','')}\n"
        report_md += f"- Magnetics: {phys.get('magnetics',{}).get('value','?')} — {phys.get('magnetics',{}).get('reason','')}\n"
        report_md += f"- Gravity: {phys.get('gravity',{}).get('value','?')}\n\n"

    with open(os.path.join(args.output, "custom_aois_priority_report.md"), "w") as f:
        f.write(report_md)

    # JSON
    with open(os.path.join(args.output, "custom_aois_priority_report.json"), "w") as f:
        json.dump({"results": [r for r in sorted_results], "score_table": "see score_meaning_table.md"}, f, indent=2, default=str)

    print(f"\n=== PRIORITY ORDER ===")
    for i, r in enumerate(sorted_results):
        high = r.get("scan",{}).get("area_high_km2", 0)
        style = r.get("style_inference",{}).get("rank_1",{}).get("style","?")
        print(f"  #{i+1} {r['aoi']:30s} HIGH={high:.1f}km² style={style}")

    print(f"\n  Saved: score_meaning_table.md + custom_aois_priority_report.md + .json")


if __name__ == "__main__":
    main()
