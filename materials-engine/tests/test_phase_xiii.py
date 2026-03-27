"""Phase XIII tests: relaxation readiness, structure repair, stronger routing, backends."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from autonomous_discovery.relaxation_readiness import assess_relaxation_readiness
from autonomous_discovery.structure_repair import assess_structure_repair
from autonomous_discovery.compute_backends import (
    list_backends, get_backend, RelaxationBackend, DFTBackend, StrongerComputeBackend
)
from autonomous_discovery.validation_queue import route_candidate, DECISIONS
from autonomous_discovery.physics_screening import compute_pre_dft_score
from validation_bridge.reporting import phase_xiii_dossier_section

passed = 0
failed = 0

def TEST(name, condition):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")

print("=" * 60)
print("Phase XIII Tests")
print("=" * 60)

# --- Relaxation Readiness ---
print("\n[1] Relaxation Readiness")

# Good structure → relaxation ready
good_phys = {
    "structure_sanity_score": 0.75,
    "pre_dft_ready": True,
    "bond_distance_sanity": True,
    "density_sanity": True,
    "geometry_warnings": [],
    "physics_flags": ["STRUCTURE_SANITY_PASS"],
    "min_bond_distance": 2.1,
    "volume_per_atom": 15.0,
    "mean_nn_distance": 2.8,
    "density": 5.2,
}
good_unc = {"structure_reliability": 0.65, "confidence_score": 0.60}
good_ready = {"validation_readiness_score": 0.65}
good_ctx = {"prediction_origin": "direct_gnn_lifted", "has_structure_lift": True, "risk_level": "familiar"}

rr = assess_relaxation_readiness(good_phys, good_unc, good_ready, good_ctx)
TEST("good structure is relaxation_ready", rr["relaxation_ready"] == True)
TEST("good structure tier is relaxation_ready", rr["relaxation_readiness_tier"] == "relaxation_ready")
TEST("good structure no repair needed", rr["structure_repair_needed"] == False)
TEST("good structure likely stable", rr["likely_relaxation_stable"] == True)
TEST("good structure not likely fail", rr["likely_relaxation_fail"] == False)
TEST("good structure is stronger compute candidate", rr["stronger_compute_candidate"] == True)

# Bad structure → not ready
bad_phys = {
    "structure_sanity_score": 0.15,
    "pre_dft_ready": False,
    "bond_distance_sanity": False,
    "density_sanity": False,
    "geometry_warnings": ["ATOMS_TOO_CLOSE (0.8 Å)", "EXTREME_DENSITY (0.5 g/cm³)"],
    "physics_flags": ["GEOMETRY_WARNING"],
    "min_bond_distance": 0.8,
    "volume_per_atom": 3.0,
    "mean_nn_distance": 1.5,
    "density": 0.5,
}
bad_ctx = {"prediction_origin": "proxy_only", "has_structure_lift": False}

rr_bad = assess_relaxation_readiness(bad_phys, {}, {}, bad_ctx)
TEST("bad structure not relaxation_ready", rr_bad["relaxation_ready"] == False)
TEST("bad structure likely fail", rr_bad["likely_relaxation_fail"] == True)
TEST("bad structure tier is discard", rr_bad["relaxation_readiness_tier"] == "not_ready_discard_or_rebuild")

# Moderate structure → repair candidate
mod_phys = {
    "structure_sanity_score": 0.42,
    "pre_dft_ready": False,
    "bond_distance_sanity": False,
    "density_sanity": True,
    "geometry_warnings": ["SHORT_BONDS (1.3 Å)"],
    "physics_flags": [],
    "min_bond_distance": 1.3,
    "volume_per_atom": 12.0,
    "mean_nn_distance": 2.5,
    "density": 4.5,
}
mod_ctx = {"has_structure_lift": True, "risk_level": "plausible"}

rr_mod = assess_relaxation_readiness(mod_phys, {"structure_reliability": 0.50, "confidence_score": 0.45},
                                       {"validation_readiness_score": 0.45}, mod_ctx)
TEST("moderate structure needs repair", rr_mod["structure_repair_needed"] == True)
TEST("moderate structure repair priority is medium", rr_mod["geometry_repair_priority"] == "medium")

# --- Structure Repair ---
print("\n[2] Structure Repair")

repair_clean = assess_structure_repair(good_phys, "NaCl", good_ctx)
TEST("clean structure no repair needed", repair_clean["repair_severity"] == "none")
TEST("clean structure is repairable (trivially)", repair_clean["repairable_structure"] == True)
TEST("clean structure confidence 1.0", repair_clean["repair_confidence"] == 1.0)

repair_bad = assess_structure_repair(bad_phys, "XyZ", bad_ctx)
TEST("bad structure repair severity severe or non_repairable",
     repair_bad["repair_severity"] in ("severe", "non_repairable"))

# No structure
no_struct = {"geometry_warnings": ["NO_STRUCTURE_AVAILABLE"], "structure_sanity_score": 0}
repair_none = assess_structure_repair(no_struct, "Fe2O3", {"has_structure_lift": False})
TEST("no structure is non_repairable", repair_none["repair_severity"] == "non_repairable")
TEST("no structure not repairable", repair_none["repairable_structure"] == False)

# --- Compute Backends ---
print("\n[3] Compute Backends")

backends = list_backends()
TEST("3 backends registered", len(backends) == 3)
TEST("relaxation backend exists", "relaxation" in backends)
TEST("dft backend exists", "dft" in backends)
TEST("all backends are placeholders", all(b["status"] == "placeholder" for b in backends.values()))

rb = get_backend("relaxation")
TEST("relaxation backend cannot run", rb.can_run() == False)
result = rb.submit({})
TEST("submit returns not_operational", result["status"] == "not_operational")
TEST("expected input has cif_text", "cif_text" in rb.expected_input())
TEST("expected output has relaxed_cif", "relaxed_cif" in rb.expected_output())

# --- Validation Queue (Phase XIII routing) ---
print("\n[4] Stronger Validation Routing")

# Check new decisions exist
TEST("relaxation_candidate in DECISIONS", "relaxation_candidate" in DECISIONS)
TEST("structure_repair_candidate in DECISIONS", "structure_repair_candidate" in DECISIONS)
TEST("stronger_compute_candidate in DECISIONS", "stronger_compute_candidate" in DECISIONS)

# Route with relaxation info
scores = {"composite_score": 0.60, "plausibility": 0.65, "is_novel_direct_gnn": True}
ml = {"ml_confidence": "medium", "ml_inference_status": "known_in_corpus"}
ctx = {"prediction_origin": "direct_gnn_lifted", "has_structure_lift": True, "is_known_material": False}
relax_info = {"relaxation_readiness_tier": "relaxation_ready"}

routed = route_candidate(scores, ml, ctx, relaxation_info=relax_info)
TEST("relaxation_ready routes to relaxation_candidate",
     routed["validation_decision"] == "relaxation_candidate")

repair_info = {"relaxation_readiness_tier": "structure_repair_candidate"}
routed2 = route_candidate(scores, ml, ctx, relaxation_info=repair_info)
TEST("repair candidate routes to structure_repair_candidate",
     routed2["validation_decision"] == "structure_repair_candidate")

# --- Dossier Section ---
print("\n[5] Phase XIII Dossier")

candidate = {
    "relaxation_readiness": {"relaxation_ready": True, "relaxation_readiness_tier": "relaxation_ready",
                              "stronger_compute_candidate": True, "relaxation_rationale": "Ready."},
    "structure_repair": {"repair_severity": "none", "repair_actions_recommended": ["NONE_NEEDED"]},
    "physics_screening": {"structure_sanity_score": 0.75, "geometry_warnings": []},
}
dossier = phase_xiii_dossier_section(candidate)
TEST("dossier has section name", dossier["section"] == "phase_xiii_compute_readiness")
TEST("dossier shows relaxation ready", dossier["relaxation_ready"] == True)
TEST("dossier has plain language", "usable" in dossier["plain_language"].lower())

# --- Physics Pre-DFT Score (existing, regression check) ---
print("\n[6] Regression: Pre-DFT Score")

pre_dft = compute_pre_dft_score(good_phys, good_unc, good_ready, scores, good_ctx)
TEST("pre_dft_physics_score is float", isinstance(pre_dft["pre_dft_physics_score"], float))
TEST("pre_dft_physics_score in range", 0 <= pre_dft["pre_dft_physics_score"] <= 1)
TEST("relaxation_candidate is bool", isinstance(pre_dft["relaxation_candidate"], bool))

# --- Summary ---
print(f"\n{'=' * 60}")
print(f"Phase XIII: {passed} passed, {failed} failed out of {passed + failed}")
if failed == 0:
    print("ALL TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
print("=" * 60)
