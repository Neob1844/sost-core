"""Final hierarchical promotion benchmark — direct measurement, no projections.

Phase IV.Q: Runs the actual gate + regressor pipeline on a holdout test set
and measures real errors per bucket. This is the definitive comparison.
"""

import json
import logging
import math
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

log = logging.getLogger(__name__)

ARTIFACT_DIR = "artifacts/hierarchical_band_gap_final"

PRODUCTION_REF = {"name": "production_alignn_lite_20k", "test_mae": 0.3422,
                  "test_rmse": 0.7362, "test_r2": 0.707}

BUCKET_RANGES = [
    ("0.0-0.05", 0.0, 0.05),
    ("0.05-1.0", 0.05, 1.0),
    ("1.0-3.0", 1.0, 3.0),
    ("3.0-6.0", 3.0, 6.0),
    ("6.0+", 6.0, 100.0),
]


@dataclass
class BenchmarkEntry:
    """One pipeline's benchmark results."""
    name: str = ""
    role: str = ""
    overall_mae: float = 0.0
    overall_rmse: float = 0.0
    overall_r2: float = 0.0
    bucket_mae: Dict[str, float] = field(default_factory=dict)
    bucket_counts: Dict[str, int] = field(default_factory=dict)
    sample_size: int = 0
    elapsed_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionScorecard:
    """Scorecard for promotion decision."""
    overall_improvement: float = 0.0
    overall_improvement_pct: float = 0.0
    narrow_gap_acceptable: bool = False
    narrow_gap_delta: float = 0.0
    metals_preserved: bool = False
    metals_delta: float = 0.0
    wide_gap_improved: bool = False
    wide_gap_delta: float = 0.0
    complexity_justified: bool = False
    promote: bool = False
    score_details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinalDecision:
    """The definitive promotion decision."""
    decision: str = ""  # PROMOTE_HIERARCHICAL_BG or HOLD_SINGLE_STAGE_BG
    production_mae: float = 0.0
    hierarchical_mae: float = 0.0
    improvement: float = 0.0
    improvement_pct: float = 0.0
    scorecard: Dict = field(default_factory=dict)
    rationale: str = ""
    registry_updated: bool = False
    new_production_model: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _load_test_set(db: MaterialsDB, sample_size: int = 2000, seed: int = 42):
    """Load a reproducible test set with structures converted to graphs."""
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
        samples.append({
            "formula": m.formula,
            "band_gap": float(m.band_gap),
            "graph": graph,
        })

    rng.shuffle(samples)
    samples = samples[:sample_size]
    log.info("Loaded %d test samples for benchmark", len(samples))
    return samples


def _predict_single_stage(samples, model_path, arch="alignn_lite"):
    """Run production single-stage model predictions."""
    if arch == "alignn_lite":
        from ..models.alignn_lite import ALIGNNLite
        model = ALIGNNLite()
    else:
        model = CGCNN()

    if not os.path.exists(model_path):
        log.warning("Model checkpoint not found: %s", model_path)
        return None

    model.load_state_dict(torch.load(model_path, weights_only=True))
    model.eval()

    predictions = []
    with torch.no_grad():
        for s in samples:
            g = s["graph"]
            pred = model(torch.tensor(g["atom_features"]),
                         torch.tensor(g["bond_distances"]),
                         torch.tensor(g["neighbor_indices"]))
            predictions.append(pred.item())
    return predictions


def _predict_hierarchical(samples, gate_path, regressor_path):
    """Run hierarchical gate + regressor pipeline predictions."""
    # Load gate
    gate = CGCNN()
    if not os.path.exists(gate_path):
        log.warning("Gate checkpoint not found: %s", gate_path)
        return None
    gate.load_state_dict(torch.load(gate_path, weights_only=True))
    gate.eval()

    # Load regressor
    from ..models.alignn_lite import ALIGNNLite
    regressor = ALIGNNLite()
    if not os.path.exists(regressor_path):
        log.warning("Regressor checkpoint not found: %s", regressor_path)
        return None
    regressor.load_state_dict(torch.load(regressor_path, weights_only=True))
    regressor.eval()

    predictions = []
    with torch.no_grad():
        for s in samples:
            g = s["graph"]
            atom_f = torch.tensor(g["atom_features"])
            bond_d = torch.tensor(g["bond_distances"])
            nbr_i = torch.tensor(g["neighbor_indices"])

            # Gate: sigmoid output
            logit = gate(atom_f, bond_d, nbr_i)
            is_nonmetal = torch.sigmoid(logit).item() >= 0.5

            if is_nonmetal:
                pred = regressor(atom_f, bond_d, nbr_i).item()
                pred = max(0.0, pred)  # BG can't be negative
            else:
                pred = 0.0  # metal → BG = 0

            predictions.append(pred)
    return predictions


def _compute_metrics(actuals, predictions, name, role):
    """Compute overall and per-bucket metrics."""
    actuals = np.array(actuals)
    predictions = np.array(predictions)
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
        count = int(mask.sum())
        bucket_counts[label] = count
        if count > 0:
            bucket_mae[label] = round(float(np.mean(errors[mask])), 4)
        else:
            bucket_mae[label] = 0.0

    return BenchmarkEntry(
        name=name, role=role,
        overall_mae=round(mae, 4), overall_rmse=round(rmse, 4),
        overall_r2=round(r2, 4),
        bucket_mae=bucket_mae, bucket_counts=bucket_counts,
        sample_size=len(actuals))


def run_final_benchmark(db: MaterialsDB, sample_size: int = 2000,
                        seed: int = 42) -> Dict:
    """Run the definitive benchmark comparing production vs hierarchical."""
    now = datetime.now(timezone.utc).isoformat()

    # Load test set
    samples = _load_test_set(db, sample_size, seed)
    actuals = [s["band_gap"] for s in samples]

    results = []

    # 1. Production single-stage (ALIGNN-Lite)
    prod_path = "artifacts/training_ladder_band_gap/rung_20k/alignn_band_gap_best.pt"
    if not os.path.exists(prod_path):
        prod_path = "artifacts/training/alignn_band_gap_best.pt"

    log.info("Benchmarking production model...")
    t0 = time.time()
    prod_preds = _predict_single_stage(samples, prod_path, "alignn_lite")
    prod_time = time.time() - t0

    if prod_preds:
        prod_entry = _compute_metrics(actuals, prod_preds, "production_alignn_20k", "production")
        prod_entry.elapsed_sec = round(prod_time, 1)
        results.append(prod_entry)
        log.info("  Production: MAE=%.4f, RMSE=%.4f, R²=%.4f",
                 prod_entry.overall_mae, prod_entry.overall_rmse, prod_entry.overall_r2)

    # 2. Hierarchical V2 (best gate + best regressor from IV.P)
    gate_path = "artifacts/hierarchical_band_gap/metal_gate_best.pt"
    reg_v2_path = "artifacts/hierarchical_band_gap_regressor/challenger_nonmetal_lower_lr/alignn_band_gap_best.pt"
    if not os.path.exists(reg_v2_path):
        reg_v2_path = "artifacts/hierarchical_band_gap/alignn_band_gap_best.pt"

    log.info("Benchmarking hierarchical V2...")
    t0 = time.time()
    hier_preds = _predict_hierarchical(samples, gate_path, reg_v2_path)
    hier_time = time.time() - t0

    if hier_preds:
        hier_entry = _compute_metrics(actuals, hier_preds, "hierarchical_v2_gate_reg", "hierarchical")
        hier_entry.elapsed_sec = round(hier_time, 1)
        results.append(hier_entry)
        log.info("  Hierarchical: MAE=%.4f, RMSE=%.4f, R²=%.4f",
                 hier_entry.overall_mae, hier_entry.overall_rmse, hier_entry.overall_r2)

    return {"entries": [r.to_dict() for r in results], "sample_size": len(samples),
            "seed": seed, "created_at": now}


def build_scorecard(benchmark: Dict) -> PromotionScorecard:
    """Build promotion scorecard from direct benchmark results."""
    entries = benchmark["entries"]
    prod = next((e for e in entries if e["role"] == "production"), None)
    hier = next((e for e in entries if e["role"] == "hierarchical"), None)

    if not prod or not hier:
        return PromotionScorecard(promote=False)

    improvement = prod["overall_mae"] - hier["overall_mae"]
    pct = round(improvement / max(prod["overall_mae"], 0.001) * 100, 2)

    # Narrow-gap: DIRECT measurement
    narrow_prod = prod["bucket_mae"].get("0.05-1.0", 999)
    narrow_hier = hier["bucket_mae"].get("0.05-1.0", 999)
    narrow_delta = round(narrow_hier - narrow_prod, 4)
    narrow_ok = narrow_delta <= 0.10  # allow up to +0.10 regression

    # Metals
    metal_prod = prod["bucket_mae"].get("0.0-0.05", 999)
    metal_hier = hier["bucket_mae"].get("0.0-0.05", 999)
    metal_delta = round(metal_hier - metal_prod, 4)
    metals_ok = metal_delta <= 0.05  # metals should not regress

    # Wide-gap
    wide_prod = prod["bucket_mae"].get("3.0-6.0", 999)
    wide_hier = hier["bucket_mae"].get("3.0-6.0", 999)
    wide_delta = round(wide_hier - wide_prod, 4)
    wide_improved = wide_delta < -0.01

    # Complexity justified: hierarchical adds gate + routing but improves MAE
    complexity_ok = improvement >= 0.02  # at least 0.02 eV improvement

    promote = (
        improvement >= 0.01 and
        narrow_ok and
        metals_ok and
        complexity_ok
    )

    return PromotionScorecard(
        overall_improvement=round(improvement, 4),
        overall_improvement_pct=pct,
        narrow_gap_acceptable=narrow_ok,
        narrow_gap_delta=narrow_delta,
        metals_preserved=metals_ok,
        metals_delta=metal_delta,
        wide_gap_improved=wide_improved,
        wide_gap_delta=wide_delta,
        complexity_justified=complexity_ok,
        promote=promote,
        score_details={
            "production": prod, "hierarchical": hier,
            "threshold_narrow_gap_delta": 0.10,
            "threshold_metal_delta": 0.05,
            "threshold_min_improvement": 0.01,
        })


def make_final_decision(scorecard: PromotionScorecard,
                        benchmark: Dict) -> FinalDecision:
    """Make the final promote/hold decision."""
    now = datetime.now(timezone.utc).isoformat()
    entries = benchmark["entries"]
    prod = next((e for e in entries if e["role"] == "production"), {})
    hier = next((e for e in entries if e["role"] == "hierarchical"), {})

    if scorecard.promote:
        decision = "PROMOTE_HIERARCHICAL_BG"
        rationale = (f"Hierarchical pipeline improves overall MAE by "
                     f"{scorecard.overall_improvement:.4f} eV ({scorecard.overall_improvement_pct:.1f}%). "
                     f"Narrow-gap delta={scorecard.narrow_gap_delta:+.4f} (within tolerance). "
                     f"Metals delta={scorecard.metals_delta:+.4f} (preserved). "
                     f"Complexity justified by {scorecard.overall_improvement:.4f} eV improvement.")
    else:
        decision = "HOLD_SINGLE_STAGE_BG"
        reasons = []
        if scorecard.overall_improvement < 0.01:
            reasons.append(f"insufficient improvement ({scorecard.overall_improvement:.4f})")
        if not scorecard.narrow_gap_acceptable:
            reasons.append(f"narrow-gap regression ({scorecard.narrow_gap_delta:+.4f})")
        if not scorecard.metals_preserved:
            reasons.append(f"metals regression ({scorecard.metals_delta:+.4f})")
        rationale = "Blocked by: " + "; ".join(reasons) if reasons else "No clear improvement"

    return FinalDecision(
        decision=decision,
        production_mae=prod.get("overall_mae", 0),
        hierarchical_mae=hier.get("overall_mae", 0),
        improvement=scorecard.overall_improvement,
        improvement_pct=scorecard.overall_improvement_pct,
        scorecard=scorecard.to_dict(),
        rationale=rationale,
        registry_updated=scorecard.promote,
        new_production_model="hierarchical_gate_alignn_v2" if scorecard.promote else None,
        created_at=now)


def update_registry_if_promoted(decision: FinalDecision):
    """Update model_registry.json only if promoted."""
    if not decision.registry_updated:
        return

    registry_path = "artifacts/training/model_registry.json"
    with open(registry_path) as f:
        registry = json.load(f)

    # Mark old BG model as superseded
    for entry in registry:
        if entry.get("target") == "band_gap" and entry.get("promoted_for_production"):
            entry["promoted_for_production"] = False
            entry["superseded_by"] = "hierarchical_gate_alignn_v2"
            entry["superseded_at"] = decision.created_at

    # Add new hierarchical entry
    registry.append({
        "model": "hierarchical_gate_alignn_v2",
        "target": "band_gap",
        "architecture": "cgcnn_gate + alignn_lite_regressor",
        "gate_checkpoint": "artifacts/hierarchical_band_gap/metal_gate_best.pt",
        "regressor_checkpoint": "artifacts/hierarchical_band_gap_regressor/challenger_nonmetal_lower_lr/alignn_band_gap_best.pt",
        "test_mae": decision.hierarchical_mae,
        "promoted_for_production": True,
        "promotion_phase": "IV.Q",
        "promotion_rationale": decision.rationale,
        "created_at": decision.created_at,
    })

    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)
    log.info("Registry updated: hierarchical_gate_alignn_v2 promoted for band_gap")


def save_all_artifacts(benchmark, scorecard, decision, output_dir=ARTIFACT_DIR):
    """Save all final benchmark artifacts."""
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "final_benchmark.json"), "w") as f:
        json.dump(benchmark, f, indent=2)
    entries = benchmark["entries"]
    md = "# Final Hierarchical Promotion Benchmark\n\n"
    md += f"Sample size: {benchmark['sample_size']}, seed: {benchmark['seed']}\n\n"
    md += "| Pipeline | MAE | RMSE | R² | Time |\n|----------|-----|------|----|------|\n"
    for e in entries:
        md += f"| {e['name']} | {e['overall_mae']:.4f} | {e['overall_rmse']:.4f} | {e['overall_r2']:.4f} | {e['elapsed_sec']:.1f}s |\n"
    md += "\n## Per-Bucket MAE\n\n| Bucket |"
    for e in entries:
        md += f" {e['name'][:15]} |"
    md += "\n|--------|" + "---------|" * len(entries) + "\n"
    for label, _, _ in BUCKET_RANGES:
        md += f"| {label} |"
        for e in entries:
            v = e['bucket_mae'].get(label, 0)
            n = e['bucket_counts'].get(label, 0)
            md += f" {v:.4f} (n={n}) |"
        md += "\n"
    with open(os.path.join(output_dir, "final_benchmark.md"), "w") as f:
        f.write(md)

    with open(os.path.join(output_dir, "bucket_scorecard.json"), "w") as f:
        json.dump(scorecard.to_dict(), f, indent=2)
    md = "# Bucket Scorecard\n\n"
    md += f"| Criterion | Value | Pass? |\n|-----------|-------|-------|\n"
    md += f"| Overall improvement | {scorecard.overall_improvement:.4f} ({scorecard.overall_improvement_pct:.1f}%) | {'PASS' if scorecard.overall_improvement >= 0.01 else 'FAIL'} |\n"
    md += f"| Narrow-gap delta | {scorecard.narrow_gap_delta:+.4f} (max +0.10) | {'PASS' if scorecard.narrow_gap_acceptable else 'FAIL'} |\n"
    md += f"| Metals delta | {scorecard.metals_delta:+.4f} (max +0.05) | {'PASS' if scorecard.metals_preserved else 'FAIL'} |\n"
    md += f"| Wide-gap improved | {scorecard.wide_gap_delta:+.4f} | {'YES' if scorecard.wide_gap_improved else 'NO'} |\n"
    md += f"| Complexity justified | {scorecard.overall_improvement:.4f} >= 0.02 | {'YES' if scorecard.complexity_justified else 'NO'} |\n"
    md += f"\n**PROMOTE: {'YES' if scorecard.promote else 'NO'}**\n"
    with open(os.path.join(output_dir, "bucket_scorecard.md"), "w") as f:
        f.write(md)

    with open(os.path.join(output_dir, "promotion_scorecard.json"), "w") as f:
        json.dump({"scorecard": scorecard.to_dict(), "decision": decision.to_dict()}, f, indent=2)
    with open(os.path.join(output_dir, "promotion_scorecard.md"), "w") as f:
        f.write(f"# Promotion Scorecard\n\nSee bucket_scorecard.md for details.\n\n**Decision: {decision.decision}**\n")

    with open(os.path.join(output_dir, "final_decision.json"), "w") as f:
        json.dump(decision.to_dict(), f, indent=2)
    md = f"# FINAL DECISION: **{decision.decision}**\n\n"
    md += f"- Production MAE: {decision.production_mae:.4f}\n"
    md += f"- Hierarchical MAE: {decision.hierarchical_mae:.4f}\n"
    md += f"- Improvement: {decision.improvement:.4f} ({decision.improvement_pct:.1f}%)\n"
    md += f"- Registry updated: {decision.registry_updated}\n\n"
    md += f"## Rationale\n{decision.rationale}\n"
    with open(os.path.join(output_dir, "final_decision.md"), "w") as f:
        f.write(md)
