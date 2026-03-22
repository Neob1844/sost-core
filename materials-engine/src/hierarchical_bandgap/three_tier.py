"""Three-tier band_gap pipeline — metal gate + narrow-gap specialist + general regressor.

Phase IV.R: Direct end-to-end benchmark with three routing tiers.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

import numpy as np
import torch

from ..storage.db import MaterialsDB
from ..normalization.structure import load_structure
from ..features.crystal_graph import structure_to_graph
from ..models.cgcnn import CGCNN
from .spec import METAL_THRESHOLD
from .narrow_gap import NARROW_LOW, NARROW_HIGH

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/three_tier_band_gap"

BUCKET_RANGES = [
    ("0.0-0.05", 0.0, 0.05),
    ("0.05-1.0", 0.05, 1.0),
    ("1.0-3.0", 1.0, 3.0),
    ("3.0-6.0", 3.0, 6.0),
    ("6.0+", 6.0, 100.0),
]

PRODUCTION = {"test_mae": 0.3407, "test_rmse": 0.6806, "test_r2": 0.7661}
TWO_TIER = {"test_mae": 0.2628, "test_rmse": 0.6690, "test_r2": 0.7740}


@dataclass
class ThreeTierResult:
    """End-to-end three-tier benchmark result."""
    name: str = ""
    overall_mae: float = 0.0
    overall_rmse: float = 0.0
    overall_r2: float = 0.0
    bucket_mae: Dict[str, float] = field(default_factory=dict)
    bucket_counts: Dict[str, int] = field(default_factory=dict)
    gate_metals: int = 0
    gate_narrow: int = 0
    gate_general: int = 0
    sample_size: int = 0
    elapsed_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionScorecard:
    overall_improvement: float = 0.0
    overall_improvement_pct: float = 0.0
    narrow_gap_acceptable: bool = False
    narrow_gap_delta: float = 0.0
    metals_preserved: bool = False
    metals_delta: float = 0.0
    wide_gap_preserved: bool = False
    wide_gap_delta: float = 0.0
    complexity_justified: bool = False
    promote: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinalDecision:
    decision: str = ""
    production_mae: float = 0.0
    two_tier_mae: float = 0.0
    three_tier_mae: float = 0.0
    improvement_vs_production: float = 0.0
    improvement_pct: float = 0.0
    narrow_gap_rescued: bool = False
    scorecard: Dict = field(default_factory=dict)
    rationale: str = ""
    registry_updated: bool = False
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def run_three_tier_benchmark(db: MaterialsDB, sample_size: int = 2000,
                             seed: int = 42) -> Dict:
    """Run direct end-to-end benchmark: production vs 2-tier vs 3-tier."""
    now = datetime.now(timezone.utc).isoformat()

    # Load test set
    materials = db.search_training_candidates(["band_gap"], limit=sample_size * 3)
    rng = np.random.RandomState(seed)
    samples = []
    for m in materials:
        if not m.structure_data or not m.has_valid_structure or m.band_gap is None:
            continue
        struct = load_structure(m.structure_data)
        if struct is None:
            continue
        graph = structure_to_graph(struct)
        if graph is None:
            continue
        samples.append({"formula": m.formula, "band_gap": float(m.band_gap), "graph": graph})
    rng.shuffle(samples)
    samples = samples[:sample_size]
    actuals = np.array([s["band_gap"] for s in samples])
    log.info("Loaded %d test samples", len(samples))

    results = {}

    # --- Production single-stage ---
    prod_path = "artifacts/training_ladder_band_gap/rung_20k/alignn_band_gap_best.pt"
    if not os.path.exists(prod_path):
        prod_path = "artifacts/training/alignn_band_gap_best.pt"
    from ..models.alignn_lite import ALIGNNLite
    prod_model = ALIGNNLite()
    prod_model.load_state_dict(torch.load(prod_path, weights_only=True))
    prod_model.eval()

    log.info("Benchmarking production...")
    t0 = time.time()
    prod_preds = []
    with torch.no_grad():
        for s in samples:
            g = s["graph"]
            p = prod_model(torch.tensor(g["atom_features"]), torch.tensor(g["bond_distances"]),
                           torch.tensor(g["neighbor_indices"]))
            prod_preds.append(p.item())
    prod_preds = np.array(prod_preds)
    results["production"] = _compute_entry("production", actuals, prod_preds, time.time() - t0)

    # --- 2-tier hierarchical ---
    gate_path = "artifacts/hierarchical_band_gap/metal_gate_best.pt"
    reg2_path = "artifacts/hierarchical_band_gap_regressor/challenger_nonmetal_lower_lr/alignn_band_gap_best.pt"
    gate_model = CGCNN()
    gate_model.load_state_dict(torch.load(gate_path, weights_only=True))
    gate_model.eval()
    reg2_model = ALIGNNLite()
    reg2_model.load_state_dict(torch.load(reg2_path, weights_only=True))
    reg2_model.eval()

    log.info("Benchmarking 2-tier...")
    t0 = time.time()
    two_preds = []
    with torch.no_grad():
        for s in samples:
            g = s["graph"]
            af = torch.tensor(g["atom_features"])
            bd = torch.tensor(g["bond_distances"])
            ni = torch.tensor(g["neighbor_indices"])
            is_nm = torch.sigmoid(gate_model(af, bd, ni)).item() >= 0.5
            if is_nm:
                two_preds.append(max(0.0, reg2_model(af, bd, ni).item()))
            else:
                two_preds.append(0.0)
    two_preds = np.array(two_preds)
    results["two_tier"] = _compute_entry("two_tier_hierarchical", actuals, two_preds, time.time() - t0)

    # --- 3-tier: gate → narrow specialist OR general regressor ---
    narrow_path = "artifacts/three_tier_band_gap/narrow_gap_specialist/alignn_band_gap_best.pt"
    if os.path.exists(narrow_path):
        narrow_model = ALIGNNLite()
        narrow_model.load_state_dict(torch.load(narrow_path, weights_only=True))
        narrow_model.eval()
    else:
        narrow_model = None
        log.warning("No narrow-gap specialist found — using general regressor for all non-metals")

    log.info("Benchmarking 3-tier...")
    t0 = time.time()
    three_preds = []
    gate_metals = gate_narrow = gate_general = 0
    with torch.no_grad():
        for s in samples:
            g = s["graph"]
            af = torch.tensor(g["atom_features"])
            bd = torch.tensor(g["bond_distances"])
            ni = torch.tensor(g["neighbor_indices"])
            sig = torch.sigmoid(gate_model(af, bd, ni)).item()

            if sig < 0.5:
                # Tier 1: metal
                three_preds.append(0.0)
                gate_metals += 1
            else:
                # Non-metal: use general regressor first for initial estimate
                general_pred = max(0.0, reg2_model(af, bd, ni).item())
                if narrow_model and general_pred < NARROW_HIGH:
                    # Tier 2: narrow-gap specialist
                    narrow_pred = max(0.0, narrow_model(af, bd, ni).item())
                    three_preds.append(narrow_pred)
                    gate_narrow += 1
                else:
                    # Tier 3: general regressor
                    three_preds.append(general_pred)
                    gate_general += 1

    three_preds = np.array(three_preds)
    three_entry = _compute_entry("three_tier_pipeline", actuals, three_preds, time.time() - t0)
    three_entry["gate_metals"] = gate_metals
    three_entry["gate_narrow"] = gate_narrow
    three_entry["gate_general"] = gate_general
    results["three_tier"] = three_entry

    log.info("Production:  MAE=%.4f", results["production"]["overall_mae"])
    log.info("2-tier:      MAE=%.4f", results["two_tier"]["overall_mae"])
    log.info("3-tier:      MAE=%.4f  (metals=%d, narrow=%d, general=%d)",
             results["three_tier"]["overall_mae"], gate_metals, gate_narrow, gate_general)

    return {"entries": results, "sample_size": len(samples), "seed": seed, "created_at": now}


def _compute_entry(name, actuals, predictions, elapsed):
    errors = np.abs(actuals - predictions)
    mae = float(np.mean(errors))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    ss_res = np.sum((actuals - predictions) ** 2)
    ss_tot = np.sum((actuals - actuals.mean()) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    bucket_mae = {}
    bucket_counts = {}
    for label, lo, hi in BUCKET_RANGES:
        mask = (actuals >= lo) & (actuals < hi)
        cnt = int(mask.sum())
        bucket_counts[label] = cnt
        bucket_mae[label] = round(float(np.mean(errors[mask])), 4) if cnt > 0 else 0.0
    return {"name": name, "overall_mae": round(mae, 4), "overall_rmse": round(rmse, 4),
            "overall_r2": round(r2, 4), "bucket_mae": bucket_mae, "bucket_counts": bucket_counts,
            "sample_size": len(actuals), "elapsed_sec": round(elapsed, 1)}


def build_scorecard(benchmark: Dict) -> PromotionScorecard:
    prod = benchmark["entries"]["production"]
    three = benchmark["entries"]["three_tier"]
    improvement = prod["overall_mae"] - three["overall_mae"]
    pct = round(improvement / max(prod["overall_mae"], 0.001) * 100, 2)

    narrow_prod = prod["bucket_mae"].get("0.05-1.0", 999)
    narrow_three = three["bucket_mae"].get("0.05-1.0", 999)
    narrow_delta = round(narrow_three - narrow_prod, 4)
    narrow_ok = narrow_delta <= 0.10

    metal_prod = prod["bucket_mae"].get("0.0-0.05", 999)
    metal_three = three["bucket_mae"].get("0.0-0.05", 999)
    metal_delta = round(metal_three - metal_prod, 4)
    metals_ok = metal_delta <= 0.05

    wide_prod = prod["bucket_mae"].get("3.0-6.0", 999)
    wide_three = three["bucket_mae"].get("3.0-6.0", 999)
    wide_delta = round(wide_three - wide_prod, 4)
    wide_ok = wide_delta <= 0.10

    complexity_ok = improvement >= 0.02
    promote = improvement >= 0.01 and narrow_ok and metals_ok and wide_ok and complexity_ok

    return PromotionScorecard(
        overall_improvement=round(improvement, 4), overall_improvement_pct=pct,
        narrow_gap_acceptable=narrow_ok, narrow_gap_delta=narrow_delta,
        metals_preserved=metals_ok, metals_delta=metal_delta,
        wide_gap_preserved=wide_ok, wide_gap_delta=wide_delta,
        complexity_justified=complexity_ok, promote=promote)


def make_final_decision(scorecard: PromotionScorecard, benchmark: Dict) -> FinalDecision:
    now = datetime.now(timezone.utc).isoformat()
    prod = benchmark["entries"]["production"]
    two = benchmark["entries"]["two_tier"]
    three = benchmark["entries"]["three_tier"]

    if scorecard.promote:
        decision = "PROMOTE_THREE_TIER_BG"
        rationale = (f"3-tier pipeline improves MAE by {scorecard.overall_improvement:.4f} "
                     f"({scorecard.overall_improvement_pct:.1f}%). "
                     f"Narrow-gap delta={scorecard.narrow_gap_delta:+.4f} (within tolerance). "
                     f"Metals delta={scorecard.metals_delta:+.4f} (preserved). "
                     f"Wide-gap delta={scorecard.wide_gap_delta:+.4f} (preserved).")
    else:
        reasons = []
        if scorecard.overall_improvement < 0.01:
            reasons.append(f"insufficient improvement ({scorecard.overall_improvement:.4f})")
        if not scorecard.narrow_gap_acceptable:
            reasons.append(f"narrow-gap still regressed ({scorecard.narrow_gap_delta:+.4f})")
        if not scorecard.metals_preserved:
            reasons.append(f"metals regressed ({scorecard.metals_delta:+.4f})")
        if not scorecard.wide_gap_preserved:
            reasons.append(f"wide-gap regressed ({scorecard.wide_gap_delta:+.4f})")
        decision = "HOLD_SINGLE_STAGE_BG"
        rationale = "Blocked by: " + "; ".join(reasons) if reasons else "No clear improvement"

    return FinalDecision(
        decision=decision,
        production_mae=prod["overall_mae"], two_tier_mae=two["overall_mae"],
        three_tier_mae=three["overall_mae"],
        improvement_vs_production=scorecard.overall_improvement,
        improvement_pct=scorecard.overall_improvement_pct,
        narrow_gap_rescued=scorecard.narrow_gap_acceptable,
        scorecard=scorecard.to_dict(), rationale=rationale,
        registry_updated=scorecard.promote, created_at=now)


def update_registry_if_promoted(decision: FinalDecision):
    if not decision.registry_updated:
        return
    registry_path = "artifacts/training/model_registry.json"
    with open(registry_path) as f:
        registry = json.load(f)
    for entry in registry:
        if entry.get("target") == "band_gap" and entry.get("promoted_for_production"):
            entry["promoted_for_production"] = False
            entry["superseded_by"] = "three_tier_bg_pipeline"
            entry["superseded_at"] = decision.created_at
    registry.append({
        "model": "three_tier_bg_pipeline",
        "target": "band_gap",
        "architecture": "cgcnn_gate + alignn_lite_narrow + alignn_lite_general",
        "gate_checkpoint": "artifacts/hierarchical_band_gap/metal_gate_best.pt",
        "narrow_checkpoint": "artifacts/three_tier_band_gap/narrow_gap_specialist/alignn_band_gap_best.pt",
        "general_checkpoint": "artifacts/hierarchical_band_gap_regressor/challenger_nonmetal_lower_lr/alignn_band_gap_best.pt",
        "test_mae": decision.three_tier_mae,
        "promoted_for_production": True,
        "promotion_phase": "IV.R",
        "promotion_rationale": decision.rationale,
        "created_at": decision.created_at,
    })
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)
    log.info("Registry updated: three_tier_bg_pipeline promoted")


def save_all_artifacts(specialist, benchmark, scorecard, decision, output_dir=ARTIFACT_DIR):
    os.makedirs(output_dir, exist_ok=True)
    entries = benchmark["entries"]

    # Pipeline comparison
    with open(os.path.join(output_dir, "three_tier_pipeline.json"), "w") as f:
        json.dump(benchmark, f, indent=2)
    md = "# Three-Tier Pipeline Benchmark\n\n"
    md += f"Sample size: {benchmark['sample_size']}\n\n"
    md += "| Pipeline | MAE | RMSE | R² |\n|----------|-----|------|----|---|\n"
    for k in ("production", "two_tier", "three_tier"):
        e = entries[k]
        md += f"| {e['name']} | {e['overall_mae']:.4f} | {e['overall_rmse']:.4f} | {e['overall_r2']:.4f} |\n"
    md += "\n## Per-Bucket MAE\n\n| Bucket | Production | 2-Tier | 3-Tier |\n|--------|-----------|--------|--------|\n"
    for label, _, _ in BUCKET_RANGES:
        p = entries["production"]["bucket_mae"].get(label, 0)
        t2 = entries["two_tier"]["bucket_mae"].get(label, 0)
        t3 = entries["three_tier"]["bucket_mae"].get(label, 0)
        n = entries["production"]["bucket_counts"].get(label, 0)
        md += f"| {label} (n={n}) | {p:.4f} | {t2:.4f} | {t3:.4f} |\n"
    with open(os.path.join(output_dir, "three_tier_pipeline.md"), "w") as f:
        f.write(md)

    # Bucket scorecard
    with open(os.path.join(output_dir, "bucket_scorecard.json"), "w") as f:
        json.dump(scorecard.to_dict(), f, indent=2)
    md = "# Bucket Scorecard\n\n| Criterion | Value | Pass? |\n|-----------|-------|-------|\n"
    md += f"| Overall improvement | {scorecard.overall_improvement:.4f} ({scorecard.overall_improvement_pct:.1f}%) | {'PASS' if scorecard.overall_improvement >= 0.01 else 'FAIL'} |\n"
    md += f"| Narrow-gap delta | {scorecard.narrow_gap_delta:+.4f} (max +0.10) | {'PASS' if scorecard.narrow_gap_acceptable else 'FAIL'} |\n"
    md += f"| Metals delta | {scorecard.metals_delta:+.4f} (max +0.05) | {'PASS' if scorecard.metals_preserved else 'FAIL'} |\n"
    md += f"| Wide-gap delta | {scorecard.wide_gap_delta:+.4f} (max +0.10) | {'PASS' if scorecard.wide_gap_preserved else 'FAIL'} |\n"
    md += f"| Complexity justified | {scorecard.overall_improvement:.4f} >= 0.02 | {'PASS' if scorecard.complexity_justified else 'FAIL'} |\n"
    md += f"\n**PROMOTE: {'YES' if scorecard.promote else 'NO'}**\n"
    with open(os.path.join(output_dir, "bucket_scorecard.md"), "w") as f:
        f.write(md)

    # Final scorecard
    with open(os.path.join(output_dir, "final_scorecard.json"), "w") as f:
        json.dump({"scorecard": scorecard.to_dict(), "decision": decision.to_dict()}, f, indent=2)
    with open(os.path.join(output_dir, "final_scorecard.md"), "w") as f:
        f.write(f"# Final Scorecard\n\n**Decision: {decision.decision}**\n\nSee bucket_scorecard.md\n")

    # Final decision
    with open(os.path.join(output_dir, "final_decision.json"), "w") as f:
        json.dump(decision.to_dict(), f, indent=2)
    md = f"# FINAL DECISION: **{decision.decision}**\n\n"
    md += f"- Production MAE: {decision.production_mae:.4f}\n"
    md += f"- 2-Tier MAE: {decision.two_tier_mae:.4f}\n"
    md += f"- 3-Tier MAE: {decision.three_tier_mae:.4f}\n"
    md += f"- Improvement: {decision.improvement_vs_production:.4f} ({decision.improvement_pct:.1f}%)\n"
    md += f"- Narrow-gap rescued: {decision.narrow_gap_rescued}\n"
    md += f"- Registry updated: {decision.registry_updated}\n\n"
    md += f"## Rationale\n{decision.rationale}\n"
    with open(os.path.join(output_dir, "final_decision.md"), "w") as f:
        f.write(md)
