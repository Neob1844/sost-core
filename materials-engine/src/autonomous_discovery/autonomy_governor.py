"""Autonomy governor — controls what the engine can decide on its own.

Defines autonomy levels, campaign auto-selection, auto-promotion/demotion,
human review triggers, and policy adaptation. All decisions are traceable.
"""
import time
from .policy import CAMPAIGN_PROFILES


# ============================================================
# AUTONOMY LEVELS
# ============================================================

AUTONOMY_LEVELS = {
    0: {"name": "manual_only", "description": "All decisions require human input",
        "auto_campaign": False, "auto_promote": False, "auto_demote": False,
        "auto_seed": False, "policy_adapt": False},
    1: {"name": "assisted", "description": "Engine recommends, human confirms",
        "auto_campaign": False, "auto_promote": False, "auto_demote": False,
        "auto_seed": True, "policy_adapt": False},
    2: {"name": "supervised", "description": "Engine acts within guardrails, human reviews",
        "auto_campaign": True, "auto_promote": False, "auto_demote": True,
        "auto_seed": True, "policy_adapt": False},
    3: {"name": "guided", "description": "Engine self-directs with evidence, human vetoes",
        "auto_campaign": True, "auto_promote": True, "auto_demote": True,
        "auto_seed": True, "policy_adapt": True},
    4: {"name": "high_autonomy", "description": "Engine operates independently, human veto only",
        "auto_campaign": True, "auto_promote": True, "auto_demote": True,
        "auto_seed": True, "policy_adapt": True},
}


class AutonomyGovernor:
    """Controls what the engine can decide autonomously."""

    def __init__(self, level=2, evidence_store=None, calibration_store=None):
        self.level = level
        self.evidence = evidence_store
        self.calibration = calibration_store
        self.decision_log = []
        self._goals = ["maximize_defensible_novel_candidates"]

    @property
    def config(self):
        return AUTONOMY_LEVELS.get(self.level, AUTONOMY_LEVELS[0])

    def set_level(self, level):
        old = self.level
        self.level = max(0, min(4, level))
        self._log("autonomy_level_change", f"{old} → {self.level}")

    def set_goals(self, goals):
        self._goals = goals
        self._log("goals_updated", str(goals))

    # ============================================================
    # CAMPAIGN AUTO-SELECTION
    # ============================================================

    def recommend_campaign(self):
        """Recommend the best campaign to run next.

        Returns dict with profile, reason, expected_value, or None if manual needed.
        """
        if not self.config["auto_campaign"]:
            return {"profile": None, "reason": "autonomy_level_too_low",
                    "requires_human": True}

        scores = {}
        for name, profile in CAMPAIGN_PROFILES.items():
            score = self._score_campaign(name, profile)
            scores[name] = score

        if not scores:
            return {"profile": "balanced", "reason": "no_scoring_data",
                    "requires_human": False, "expected_value": 0.5}

        best = max(scores, key=scores.get)
        reason = self._explain_campaign_choice(best)

        self._log("campaign_recommended", f"{best}: {reason}")
        return {
            "profile": best,
            "reason": reason,
            "expected_value": round(scores[best], 3),
            "requires_human": False,
            "all_scores": {k: round(v, 3) for k, v in sorted(scores.items(), key=lambda x: -x[1])[:5]},
        }

    def _score_campaign(self, name, profile):
        """Score a campaign profile based on evidence and goals."""
        score = 0.5  # neutral base

        # Goal alignment
        weights = profile.get("weights", {})
        if "maximize_defensible_novel_candidates" in self._goals:
            score += weights.get("stability", 0) * 0.3
            score += weights.get("value", 0) * 0.2
        if "reduce_proxy_dependency" in self._goals:
            score += weights.get("diversity", 0) * 0.2
        if "improve_weak_families" in self._goals:
            score += profile.get("explore_ratio", 0.3) * 0.2

        # Evidence-based adjustments
        if self.evidence:
            ev_count = self.evidence.by_campaign.get(name, {}).get("count", 0)
            if ev_count == 0:
                score += 0.1  # unexplored campaign — worth trying
            elif ev_count > 10:
                # Check if this campaign has been productive
                camp = self.evidence.by_campaign.get(name, {})
                confirmed = camp.get("confirmed_count", 0)
                yield_rate = confirmed / max(ev_count, 1)
                score += (yield_rate - 0.5) * 0.2  # reward productive campaigns

        # Prefer profiles with evidence calibration
        if profile.get("use_evidence_calibration"):
            score += 0.05
        if profile.get("prefer_uncertain") and "improve_weak_families" in self._goals:
            score += 0.1

        return max(0.0, min(1.0, score))

    def _explain_campaign_choice(self, name):
        parts = []
        if name in ("evidence_guided_discovery",):
            parts.append("evidence-calibrated discovery")
        if name in ("battery_relevant", "strategic_materials_search"):
            parts.append("high strategic value")
        if name in ("high_uncertainty_probe",):
            parts.append("uncertainty exploration")
        if name in ("validation_priority", "validation_operations"):
            parts.append("validation-focused")
        if not parts:
            parts.append("best score for current goals")
        return "; ".join(parts)

    # ============================================================
    # AUTO-SEED SELECTION
    # ============================================================

    def recommend_seeds(self, available_seeds, n=3):
        """Recommend seed pairs for the next campaign."""
        if not self.config["auto_seed"]:
            return available_seeds[:n]

        # Prefer seeds from reliable families
        scored = []
        for seed in available_seeds:
            score = 0.5
            if self.evidence:
                for s in seed:
                    from .chem_filters import parse_formula
                    elems = list(parse_formula(s).keys())
                    family_key = "-".join(sorted(elems))
                    fam = self.evidence.by_family.get(family_key, {})
                    if fam.get("count", 0) > 0:
                        overconf = self.evidence.family_overconfidence_rate(family_key) or 0
                        score -= overconf * 0.3  # penalize overconfident families
                        mae = self.evidence.family_mae(family_key, "fe")
                        if mae is not None and mae < 0.15:
                            score += 0.2  # reward reliable families
            scored.append((seed, score))

        scored.sort(key=lambda x: -x[1])
        selected = [s[0] for s in scored[:n]]
        self._log("seeds_recommended", str(selected))
        return selected

    # ============================================================
    # AUTO-PROMOTION / AUTO-DEMOTION
    # ============================================================

    def should_promote(self, candidate_scores, uncertainty, readiness):
        """Decide if a candidate should be automatically promoted."""
        if not self.config["auto_promote"]:
            return False, "auto_promote_disabled"

        composite = candidate_scores.get("composite_score", 0)
        conf = uncertainty.get("confidence_score", 0)
        ready = readiness.get("validation_readiness_score", 0)
        is_novel_gnn = candidate_scores.get("is_novel_direct_gnn", False)

        if is_novel_gnn and composite >= 0.55 and conf >= 0.55 and ready >= 0.55:
            reason = f"auto_promote: novel_gnn + score={composite:.2f} + conf={conf:.2f} + ready={ready:.2f}"
            self._log("auto_promotion", reason)
            return True, reason

        return False, "below_auto_promote_threshold"

    def should_demote(self, candidate_scores, uncertainty):
        """Decide if a candidate should be demoted to watchlist."""
        if not self.config["auto_demote"]:
            return False, "auto_demote_disabled"

        composite = candidate_scores.get("composite_score", 0)
        conf = uncertainty.get("confidence_score", 0)
        evidence_quality = candidate_scores.get("evidence_quality", "no_evidence")

        if composite < 0.35 and conf < 0.30:
            reason = f"auto_demote: low_score={composite:.2f} + low_conf={conf:.2f}"
            self._log("auto_demotion", reason)
            return True, reason

        if evidence_quality == "evidence_warns" and composite < 0.45:
            reason = f"auto_demote: evidence_warns + score={composite:.2f}"
            self._log("auto_demotion", reason)
            return True, reason

        return False, "no_demotion_needed"

    # ============================================================
    # HUMAN REVIEW TRIGGERS
    # ============================================================

    def needs_human_review(self, candidate_scores, uncertainty, readiness):
        """Determine if this candidate needs human review."""
        composite = candidate_scores.get("composite_score", 0)
        conf = uncertainty.get("confidence_score", 0)
        ood = uncertainty.get("out_of_domain_risk", 0)
        ready = readiness.get("validation_readiness_score", 0)

        triggers = []

        # High value + high uncertainty
        if composite >= 0.50 and conf < 0.40:
            triggers.append("high_value_high_uncertainty")

        # Near handoff threshold
        if 0.55 <= ready <= 0.65:
            triggers.append("near_handoff_threshold")

        # High OOD risk with decent score
        if ood > 0.50 and composite >= 0.45:
            triggers.append("high_ood_with_decent_score")

        return triggers

    # ============================================================
    # DECISION LOG
    # ============================================================

    def _log(self, event_type, detail):
        self.decision_log.append({
            "event": event_type,
            "detail": detail,
            "level": self.level,
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        # Keep bounded
        if len(self.decision_log) > 500:
            self.decision_log = self.decision_log[-500:]

    def summary(self):
        return {
            "autonomy_level": self.level,
            "autonomy_name": self.config["name"],
            "goals": self._goals,
            "decisions_logged": len(self.decision_log),
            "capabilities": {k: v for k, v in self.config.items() if k not in ("name", "description")},
        }
