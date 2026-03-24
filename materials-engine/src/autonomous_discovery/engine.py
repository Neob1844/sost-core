"""Core autonomous discovery engine — runs iterative discovery cycles."""
import time, random
from .memory_store import MemoryStore
from .policy import get_profile, CAMPAIGN_PROFILES
from .chem_filters import filter_candidate, parse_formula
from .scorer import score_candidate
from .ml_evaluator import evaluate_candidate_ml, find_nearest_neighbors
from .validation_queue import route_candidate
from .structure_pipeline import lift_structure_for_candidate, run_gnn_inference, run_direct_gnn_inference, get_parent_cif
from .chem_filters import normalize_formula
from .uncertainty import compute_uncertainty, compute_validation_readiness, apply_diversity_constraint, generate_handoff_pack

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from material_mixer.generator import generate_candidates as mix_generate


# Seed pools for different profiles
DEFAULT_SEEDS = [
    ("GaAs", "AlN"), ("TiO2", "ZnO"), ("Si", "Ge"),
    ("SiC", "BN"), ("Fe2O3", "Al2O3"), ("BaTiO3", "SrTiO3"),
    ("LiCoO2", "NiO"), ("CdTe", "CuInSe2"), ("MgO", "ZrO2"),
    ("InP", "GaN"), ("Cu2O", "ZnO"), ("FeS2", "NiS2"),
]


class DiscoveryEngine:
    """Autonomous iterative discovery engine."""

    def __init__(self, profile_name="balanced", memory_path=None, seeds=None):
        self.profile = get_profile(profile_name)
        self.profile_name = profile_name
        self.memory = MemoryStore(memory_path)
        self.seeds = seeds or list(DEFAULT_SEEDS)
        self.state = "idle"  # idle | running | paused | stopped
        self.current_iteration = 0
        self.results = []

    def run_iteration(self, max_candidates=30):
        """Run a single discovery iteration. Returns iteration report."""
        self.state = "running"
        self.memory.iteration_count += 1
        self.current_iteration = self.memory.iteration_count
        t0 = time.time()

        # 1. Select seed pair
        seed_a, seed_b = self._select_seeds()

        # 2. Generate candidates
        raw_candidates = mix_generate(seed_a, seed_b, max_candidates=max_candidates * 2)

        # 3. Filter
        filtered = []
        rejections = []
        for c in raw_candidates:
            formula = c["formula"]
            # Duplicate check
            if self.memory.is_duplicate(formula):
                rejections.append({"formula": formula, "reason": "duplicate"})
                continue
            # Chemical filter
            ok, reason = filter_candidate(formula, seed_a, seed_b)
            if not ok:
                rejections.append({"formula": formula, "reason": reason})
                self.memory.record_candidate(formula, c.get("method", "unknown"), 0.0, False, reason)
                continue
            filtered.append(c)

        # 4. Score + ML evaluation + Structure lift + GNN (Phase V.B)
        scored = []
        lift_attempted = 0
        lift_success = 0
        gnn_evaluated = 0
        direct_fe_success_count = 0
        direct_bg_success_count = 0
        known_reference_count = 0
        proxy_only_count = 0
        new_candidate_count = 0
        for c in filtered[:max_candidates]:
            elements = c.get("elements", list(parse_formula(c["formula"]).keys()))
            parent_a = c.get("parent_a", "")

            # ML evaluation (corpus context)
            ml = evaluate_candidate_ml(c["formula"], elements, c.get("method", "unknown"),
                                        parent_a, c.get("parent_b", ""))
            c["ml_evaluation"] = ml

            # Phase V.B: Detect known material
            norm = normalize_formula(c["formula"])
            is_known = get_parent_cif(norm) is not None

            # Structure lift attempt
            lift = lift_structure_for_candidate(
                c["formula"], elements, parent_a, c.get("method", "unknown"))
            c["structure_lift"] = lift
            lift_attempted += 1

            # Phase V.B: Use run_direct_gnn_inference for combined FE+BG
            gnn_combined = {"prediction_origin": "unavailable", "bg_prediction_origin": "unavailable",
                            "direct_fe_inference_success": False, "direct_bg_inference_success": False,
                            "direct_fe_value": None, "direct_bg_value": None,
                            "direct_fe_confidence": "none", "direct_bg_confidence": "none"}
            if lift.get("structure_lift_status") == "lifted_ok":
                lift_success += 1
                gnn_combined = run_direct_gnn_inference(lift.get("lifted_cif"))
                c["gnn_combined"] = gnn_combined

                if gnn_combined.get("direct_fe_inference_success"):
                    direct_fe_success_count += 1
                if gnn_combined.get("direct_bg_inference_success"):
                    direct_bg_success_count += 1
                if gnn_combined.get("overall_status") in ("corpus_exact_match", "direct_gnn_success"):
                    gnn_evaluated += 1

                # Override ML evaluation with GNN results
                if gnn_combined.get("direct_fe_value") is not None:
                    ml["formation_energy_predicted"] = gnn_combined["direct_fe_value"]
                    ml["ml_inference_status"] = gnn_combined.get("overall_status", "unavailable")
                    ml["ml_confidence"] = gnn_combined.get("direct_fe_confidence", "none")
                    ml["prediction_path"] = "lifted_structure"

            # Build candidate_context for Phase V.B scoring
            prediction_origin = gnn_combined.get("prediction_origin", "unavailable")
            if is_known:
                prediction_origin = "known_exact"
                known_reference_count += 1
            elif prediction_origin == "proxy_only":
                proxy_only_count += 1
            elif prediction_origin not in ("known_exact",):
                new_candidate_count += 1

            candidate_context = {
                "is_known_material": is_known,
                "has_direct_gnn_fe": gnn_combined.get("direct_fe_inference_success", False),
                "has_direct_gnn_bg": gnn_combined.get("direct_bg_inference_success", False),
                "has_structure_lift": lift.get("structure_lift_status") == "lifted_ok",
                "prediction_origin": prediction_origin,
                "gnn_confidence": gnn_combined.get("direct_fe_confidence", "none"),
            }
            c["candidate_context"] = candidate_context

            # Phase V.C: scorer handles all bonuses/penalties via candidate_context
            scores = score_candidate(c["formula"], elements, c.get("method", "unknown"),
                                     self.profile, self.memory, neighbors=ml.get("nearest_neighbors"),
                                     candidate_context=candidate_context)

            # Phase VII: Uncertainty-aware scoring
            unc = compute_uncertainty(
                candidate_context, scores, c.get("method", "unknown"),
                len(elements), ml.get("nearest_neighbors"))
            readiness = compute_validation_readiness(unc, scores, candidate_context)
            c["uncertainty"] = unc
            c["readiness"] = readiness
            scores["uncertainty_score"] = unc["uncertainty_score"]
            scores["confidence_score"] = unc["confidence_score"]
            scores["validation_readiness_score"] = readiness["validation_readiness_score"]

            c["scores"] = scores
            c["composite_score"] = scores["composite_score"]
            scored.append(c)

        # 5. Rank and decide — with diversity constraint (Phase VII)
        scored.sort(key=lambda x: -x["composite_score"])
        scored = apply_diversity_constraint(scored, max_per_family=3, top_k=len(scored))
        accepted = []
        watchlist = []
        validation_candidates = []
        rejected_by_score = 0
        for c in scored:
            vq = route_candidate(c["scores"], c.get("ml_evaluation"), c.get("candidate_context"))
            c["validation"] = vq
            vd = vq["validation_decision"]
            is_accepted = vd in ("priority_validation", "validation_candidate", "manual_review")
            self.memory.record_candidate(
                c["formula"], c.get("method", "unknown"),
                c["composite_score"], is_accepted,
                None if is_accepted else f"validation:{vd}"
            )
            if vd in ("priority_validation", "validation_candidate"):
                accepted.append(c)
                validation_candidates.append(c)
            elif vd == "manual_review":
                accepted.append(c)
            elif vd == "watchlist":
                watchlist.append(c)
            else:
                rejected_by_score += 1

        elapsed = round(time.time() - t0, 2)

        # Build iteration report
        report = {
            "iteration": self.current_iteration,
            "profile": self.profile_name,
            "seeds": [seed_a, seed_b],
            "raw_generated": len(raw_candidates),
            "filtered": len(filtered),
            "scored": len(scored),
            "accepted": len(accepted),
            "rejected_filter": len(rejections),
            "rejected_score": rejected_by_score,
            "watchlist": len(watchlist),
            "structure_lift_attempted": lift_attempted,
            "structure_lift_success": lift_success,
            "gnn_evaluated": gnn_evaluated,
            "direct_fe_success_count": direct_fe_success_count,
            "direct_bg_success_count": direct_bg_success_count,
            "known_reference_count": known_reference_count,
            "proxy_only_count": proxy_only_count,
            "new_candidate_count": new_candidate_count,
            "elapsed_s": elapsed,
            "top_candidates": [
                {"rank": i+1, "formula": c["formula"], "method": c.get("method", ""),
                 "composite_score": c["composite_score"], "scores": c["scores"],
                 "ml_status": c.get("ml_evaluation", {}).get("ml_inference_status", "unavailable"),
                 "ml_confidence": c.get("ml_evaluation", {}).get("ml_confidence", "none"),
                 "prototype_hint": c.get("ml_evaluation", {}).get("prototype_hint"),
                 "nearest_formula": c.get("ml_evaluation", {}).get("nearest_neighbors", [{}])[0].get("formula", "—") if c.get("ml_evaluation", {}).get("nearest_neighbors") else "—",
                 "validation": c.get("validation", {}).get("validation_decision", "unknown"),
                 "validation_priority": c.get("validation", {}).get("validation_priority", 0),
                 "next_step": c.get("validation", {}).get("recommended_next_step", "unknown"),
                 "prediction_origin": c.get("candidate_context", {}).get("prediction_origin", "unavailable"),
                 "direct_fe_value": c.get("gnn_combined", {}).get("direct_fe_value"),
                 "direct_bg_value": c.get("gnn_combined", {}).get("direct_bg_value"),
                 "uncertainty_score": c.get("uncertainty", {}).get("uncertainty_score"),
                 "confidence_score": c.get("uncertainty", {}).get("confidence_score"),
                 "out_of_domain_risk": c.get("uncertainty", {}).get("out_of_domain_risk"),
                 "support_strength": c.get("uncertainty", {}).get("support_strength"),
                 "validation_readiness": c.get("readiness", {}).get("validation_readiness_score"),
                 "dft_handoff_ready": c.get("readiness", {}).get("dft_handoff_ready"),
                 "readiness_action": c.get("readiness", {}).get("next_action")}
                for i, c in enumerate(accepted[:10])
            ],
            "top_rejections": rejections[:5],
            "memory_summary": self.memory.summary(),
        }

        self.results.append(report)
        self.memory.save()
        self.state = "idle"
        return report

    def run_campaign(self, n_iterations=5, max_candidates_per_iter=30):
        """Run multiple iterations as a campaign."""
        campaign_results = []
        for i in range(n_iterations):
            if self.state == "stopped":
                break
            report = self.run_iteration(max_candidates=max_candidates_per_iter)
            campaign_results.append(report)
            # Re-seed from top winners after each iteration (exploit)
            self._update_seeds_from_winners()

        # Build campaign summary
        total_gen = sum(r["raw_generated"] for r in campaign_results)
        total_acc = sum(r["accepted"] for r in campaign_results)
        all_top = []
        for r in campaign_results:
            all_top.extend(r["top_candidates"])
        all_top.sort(key=lambda x: -x["composite_score"])

        return {
            "profile": self.profile_name,
            "iterations": len(campaign_results),
            "total_generated": total_gen,
            "total_accepted": total_acc,
            "accept_rate": round(total_acc / max(total_gen, 1), 4),
            "top_candidates_overall": all_top[:20],
            "iteration_reports": campaign_results,
            "memory_summary": self.memory.summary(),
            "disclaimer": (
                "All candidates are THEORETICAL — generated by heuristic rules and "
                "scored with proxy metrics. No DFT, experimental synthesis, or "
                "high-fidelity validation has been performed. Requires independent verification."
            ),
        }

    def _select_seeds(self):
        """Select seed pair based on explore/exploit policy."""
        explore_r = self.profile.get("explore_ratio", 0.5)
        exploit_r = self.profile.get("exploit_ratio", 0.3)

        roll = random.random()
        if roll < exploit_r and self.memory.candidates_accepted:
            # Exploit: use a top winner as seed
            top = sorted(self.memory.candidates_accepted, key=lambda x: -x.get("score", 0))[:5]
            winner = random.choice(top)
            base = random.choice(self.seeds)
            return winner["formula"], base[1]
        elif roll < exploit_r + explore_r:
            # Explore: random seed pair
            return random.choice(self.seeds)
        else:
            # Diversify: mix seeds from different pairs
            a = random.choice(self.seeds)
            b = random.choice(self.seeds)
            return a[0], b[1]

    def _update_seeds_from_winners(self):
        """Add top-scoring winners as new seed sources."""
        if not self.memory.candidates_accepted:
            return
        top = sorted(self.memory.candidates_accepted, key=lambda x: -x.get("score", 0))[:3]
        for w in top:
            pair = (w["formula"], random.choice(self.seeds)[1])
            if pair not in self.seeds:
                self.seeds.append(pair)
                if len(self.seeds) > 30:
                    self.seeds.pop(0)  # keep bounded

    def stop(self):
        self.state = "stopped"

    def pause(self):
        self.state = "paused"

    def resume(self):
        self.state = "idle"

    def status(self):
        return {
            "state": self.state,
            "profile": self.profile_name,
            "current_iteration": self.current_iteration,
            "memory": self.memory.summary(),
        }
