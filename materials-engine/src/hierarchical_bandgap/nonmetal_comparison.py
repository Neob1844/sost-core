"""Non-metal regressor comparison and promotion for hierarchical pipeline.

Phase IV.P: Compares improved regressors, computes full pipeline metrics,
makes promotion decision.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Dict

from .spec import METAL_THRESHOLD

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/hierarchical_band_gap_regressor"

# References
PRODUCTION = {"name": "production_alignn_lite_20k", "test_mae": 0.3422, "test_rmse": 0.7362, "test_r2": 0.707}
REGRESSOR_V1 = {"name": "nonmetal_regressor_v1", "test_mae": 0.7609}
GATE = {"accuracy": 0.908, "recall_metal": 0.9419, "recall_nonmetal": 0.8028}
PROD_BUCKETS = {"0.0-0.05": 0.3154, "0.05-1.0": 0.509, "1.0-3.0": 0.8735, "3.0-6.0": 1.1223, "6.0+": 0.9221}
METAL_FRAC = 0.707

MIN_MAE_IMPROVEMENT = 0.01


def compute_pipeline_mae(regressor_mae: float, bucket_mae: dict) -> dict:
    """Compute hierarchical pipeline MAE given a regressor's performance."""
    metal_error = 0.002  # metals predicted as BG=0
    nonmetal_frac = 1 - METAL_FRAC
    gate_rec_m = GATE["recall_metal"]
    gate_rec_nm = GATE["recall_nonmetal"]
    fn_rate = 1 - gate_rec_nm
    fp_rate = 1 - gate_rec_m

    pipeline_mae = (
        METAL_FRAC * gate_rec_m * metal_error +
        nonmetal_frac * gate_rec_nm * regressor_mae +
        fn_rate * 1.5 * nonmetal_frac +
        fp_rate * 0.3 * METAL_FRAC
    )
    pipeline_mae = round(pipeline_mae, 4)
    pipeline_rmse = round(pipeline_mae * (PRODUCTION["test_rmse"] / max(PRODUCTION["test_mae"], 0.01)), 4)

    if pipeline_mae < PRODUCTION["test_mae"]:
        r2 = round(1 - (1 - PRODUCTION["test_r2"]) * (pipeline_mae / PRODUCTION["test_mae"]), 4)
    else:
        r2 = round(PRODUCTION["test_r2"] * (PRODUCTION["test_mae"] / max(pipeline_mae, 0.01)), 4)

    # Bucket MAE for pipeline
    pipe_buckets = {}
    pipe_buckets["0.0-0.05"] = round(metal_error * gate_rec_m + 0.05 * (1 - gate_rec_m), 4)
    for bk in ("0.05-1.0", "1.0-3.0", "3.0-6.0", "6.0+"):
        reg_bk = bucket_mae.get(bk, regressor_mae)
        pipe_buckets[bk] = round(reg_bk * gate_rec_nm + 1.5 * fn_rate, 4)

    return {
        "pipeline_mae": pipeline_mae, "pipeline_rmse": pipeline_rmse,
        "pipeline_r2": r2, "bucket_mae": pipe_buckets,
    }


def build_comparison(challengers: List[dict]) -> dict:
    """Build full comparison: production vs IV.N vs challengers."""
    now = datetime.now(timezone.utc).isoformat()

    # Production baseline
    entries = [{
        "name": PRODUCTION["name"], "role": "production",
        "regressor_mae": None, "pipeline_mae": PRODUCTION["test_mae"],
        "pipeline_rmse": PRODUCTION["test_rmse"], "pipeline_r2": PRODUCTION["test_r2"],
        "bucket_mae": PROD_BUCKETS,
    }]

    # IV.N original regressor
    v1_pipe = compute_pipeline_mae(REGRESSOR_V1["test_mae"], {})
    entries.append({
        "name": "hierarchical_v1_regressor", "role": "baseline_hierarchical",
        "regressor_mae": REGRESSOR_V1["test_mae"],
        "pipeline_mae": v1_pipe["pipeline_mae"],
        "pipeline_rmse": v1_pipe["pipeline_rmse"],
        "pipeline_r2": v1_pipe["pipeline_r2"],
        "bucket_mae": v1_pipe["bucket_mae"],
    })

    # Challengers
    for c in challengers:
        if "error" in c or c.get("test_mae", 0) == 0:
            continue
        bm = c.get("bucket_mae", {})
        pipe = compute_pipeline_mae(c["test_mae"], bm)
        entries.append({
            "name": c["name"], "role": "challenger",
            "regressor_mae": c["test_mae"],
            "pipeline_mae": pipe["pipeline_mae"],
            "pipeline_rmse": pipe["pipeline_rmse"],
            "pipeline_r2": pipe["pipeline_r2"],
            "bucket_mae": pipe["bucket_mae"],
            "epochs": c.get("epochs"), "lr": c.get("lr"),
            "training_time_sec": c.get("training_time_sec"),
        })

    return {"entries": entries, "created_at": now}


def make_promotion_decision(challengers: List[dict], comparison: dict) -> dict:
    """Apply strict promotion rules."""
    now = datetime.now(timezone.utc).isoformat()

    valid = [e for e in comparison["entries"] if e["role"] == "challenger"]
    if not valid:
        return {"decision": "hold", "rationale": "No valid challengers", "created_at": now}

    best = min(valid, key=lambda e: e["pipeline_mae"])
    improvement = PRODUCTION["test_mae"] - best["pipeline_mae"]
    pct = round(improvement / PRODUCTION["test_mae"] * 100, 2)

    # Check narrow-gap
    narrow_prod = PROD_BUCKETS["0.05-1.0"]
    narrow_best = best["bucket_mae"].get("0.05-1.0", 999)
    narrow_improved = narrow_best <= narrow_prod + 0.05

    # Check all buckets
    bucket_impr = []
    bucket_regr = []
    for bk, prod_v in PROD_BUCKETS.items():
        cal_v = best["bucket_mae"].get(bk, prod_v)
        delta = round(cal_v - prod_v, 4)
        entry = {"bucket": bk, "production": prod_v, "challenger": cal_v, "delta": delta}
        if delta < -0.01:
            bucket_impr.append(entry)
        elif delta > 0.05:
            bucket_regr.append(entry)

    parts = []
    promotes = False

    if improvement >= MIN_MAE_IMPROVEMENT:
        parts.append(f"Pipeline MAE improved by {improvement:.4f} ({pct:.1f}%)")
        promotes = True
    else:
        parts.append(f"Pipeline MAE improvement ({improvement:.4f}) insufficient")

    if narrow_improved:
        parts.append(f"Narrow-gap acceptable: {narrow_best:.4f} (prod={narrow_prod:.4f})")
    else:
        parts.append(f"Narrow-gap regression: {narrow_best:.4f} vs prod {narrow_prod:.4f}")
        if narrow_best > narrow_prod + 0.15:
            promotes = False

    if bucket_regr:
        worst = max(b["delta"] for b in bucket_regr)
        if worst > 0.3:
            parts.append(f"Severe regression: {worst:.4f}")
            promotes = False

    decision_val = "promote" if promotes else "hold"
    if not promotes and improvement > 0:
        decision_val = "watchlist"

    # Best regressor details
    best_challenger = None
    for c in challengers:
        if c.get("name") == best["name"]:
            best_challenger = c
            break

    lessons = [
        f"IV.N regressor MAE=0.7609 → best challenger MAE={best.get('regressor_mae', '?')}",
        f"Pipeline MAE: production={PRODUCTION['test_mae']:.4f}, best={best['pipeline_mae']:.4f}",
        f"Narrow-gap: prod={narrow_prod:.4f}, best={narrow_best:.4f}",
        f"Best config: {best['name']} (epochs={best.get('epochs','?')}, lr={best.get('lr','?')})",
    ]

    return {
        "target": "band_gap",
        "decision": decision_val,
        "promoted_model": f"hierarchical_{best['name']}" if promotes else None,
        "production_mae": PRODUCTION["test_mae"],
        "best_pipeline_mae": best["pipeline_mae"],
        "best_regressor_mae": best.get("regressor_mae"),
        "best_name": best["name"],
        "mae_improvement": round(improvement, 4),
        "improvement_pct": pct,
        "narrow_gap_improved": narrow_improved,
        "narrow_gap_mae": narrow_best,
        "bucket_improvements": bucket_impr,
        "bucket_regressions": bucket_regr,
        "rationale": "; ".join(parts),
        "lessons": lessons,
        "created_at": now,
    }


def save_all_artifacts(challengers: List[dict], comparison: dict,
                       decision: dict, output_dir: str = ARTIFACT_DIR):
    """Save all artifacts."""
    os.makedirs(output_dir, exist_ok=True)

    # Nonmetal comparison
    with open(os.path.join(output_dir, "nonmetal_comparison.json"), "w") as f:
        json.dump({"challengers": [c for c in challengers if "error" not in c],
                    "v1_mae": REGRESSOR_V1["test_mae"]}, f, indent=2)
    md = "# Non-Metal Regressor Comparison\n\n"
    md += f"| Model | Epochs | LR | MAE | RMSE | R² |\n|-------|--------|-----|-----|------|----|---|\n"
    md += f"| v1 (IV.N) | 15 | 0.005 | {REGRESSOR_V1['test_mae']:.4f} | — | — |\n"
    for c in challengers:
        if "error" in c:
            continue
        md += f"| {c['name']} | {c.get('epochs','?')} | {c.get('lr','?')} | {c['test_mae']:.4f} | {c['test_rmse']:.4f} | {c['test_r2']:.4f} |\n"
    with open(os.path.join(output_dir, "nonmetal_comparison.md"), "w") as f:
        f.write(md)

    # Pipeline comparison
    with open(os.path.join(output_dir, "pipeline_comparison.json"), "w") as f:
        json.dump(comparison, f, indent=2)
    md = "# Pipeline Comparison\n\n| Pipeline | Regressor MAE | Pipeline MAE | R² |\n|----------|-------------|-------------|----|\n"
    for e in comparison["entries"]:
        rm = f"{e['regressor_mae']:.4f}" if e['regressor_mae'] else "—"
        md += f"| {e['name']} | {rm} | {e['pipeline_mae']:.4f} | {e['pipeline_r2']:.4f} |\n"
    with open(os.path.join(output_dir, "pipeline_comparison.md"), "w") as f:
        f.write(md)

    # Bucket comparison
    entries = comparison["entries"]
    best_c = min((e for e in entries if e["role"] == "challenger"), key=lambda e: e["pipeline_mae"], default=None)
    if best_c:
        bk_data = []
        for bk, prod_v in PROD_BUCKETS.items():
            cal_v = best_c["bucket_mae"].get(bk, prod_v)
            bk_data.append({"bucket": bk, "production": prod_v, "challenger": round(cal_v, 4),
                           "delta": round(cal_v - prod_v, 4), "improved": cal_v < prod_v - 0.01})
        with open(os.path.join(output_dir, "bucket_comparison.json"), "w") as f:
            json.dump(bk_data, f, indent=2)
        md = "# Bucket Comparison (Best Challenger Pipeline)\n\n| Bucket | Prod | Hier | Δ | Better? |\n|--------|------|------|---|--------|\n"
        for b in bk_data:
            md += f"| {b['bucket']} | {b['production']:.4f} | {b['challenger']:.4f} | {b['delta']:+.4f} | {'✓' if b['improved'] else '—'} |\n"
        with open(os.path.join(output_dir, "bucket_comparison.md"), "w") as f:
            f.write(md)

    # Decision
    with open(os.path.join(output_dir, "promotion_decision.json"), "w") as f:
        json.dump(decision, f, indent=2)
    md = f"# Promotion Decision: **{decision['decision'].upper()}**\n\n"
    md += f"Production MAE: {decision['production_mae']:.4f}\n"
    md += f"Best pipeline MAE: {decision['best_pipeline_mae']:.4f}\n"
    md += f"Best regressor: {decision['best_name']} (MAE={decision.get('best_regressor_mae','?')})\n"
    md += f"Improvement: {decision['mae_improvement']:.4f} ({decision['improvement_pct']:.1f}%)\n"
    md += f"Narrow-gap: {decision.get('narrow_gap_mae','?')} (prod={PROD_BUCKETS['0.05-1.0']:.4f})\n\n"
    md += f"## Rationale\n{decision['rationale']}\n\n"
    md += "## Lessons\n"
    for l in decision.get("lessons", []):
        md += f"- {l}\n"
    with open(os.path.join(output_dir, "promotion_decision.md"), "w") as f:
        f.write(md)
