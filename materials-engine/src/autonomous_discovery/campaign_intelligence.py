"""Campaign intelligence — chemistry-aware campaign and seed selection.

Uses family chemistry context, risk levels, evidence history, and
validation yields to recommend which campaigns to run and which
seeds to use. All decisions are explainable.
"""
from .chemistry_caution import label_candidate
from .chem_filters import parse_formula


# Family exploration status
FAMILY_STATUS = {
    "preferred": {"explore_boost": 0.0, "exploit_boost": 0.15, "noise_risk": 0.0},
    "stable": {"explore_boost": 0.0, "exploit_boost": 0.10, "noise_risk": 0.0},
    "promising": {"explore_boost": 0.10, "exploit_boost": 0.05, "noise_risk": 0.05},
    "exploratory": {"explore_boost": 0.15, "exploit_boost": 0.0, "noise_risk": 0.10},
    "cautionary": {"explore_boost": 0.0, "exploit_boost": 0.0, "noise_risk": 0.15},
    "noisy": {"explore_boost": -0.10, "exploit_boost": -0.10, "noise_risk": 0.25},
    "cooldown": {"explore_boost": -0.15, "exploit_boost": -0.15, "noise_risk": 0.20},
}


def classify_family_status(family_key, evidence_store=None, calibration_store=None):
    """Determine exploration status for a chemical family.

    Returns (status_name, reason).
    """
    if not evidence_store:
        return "exploratory", "no evidence available"

    fam = evidence_store.by_family.get(family_key, {})
    count = fam.get("count", 0)

    if count == 0:
        return "exploratory", "never validated — worth exploring"

    mae = evidence_store.family_mae(family_key, "fe")
    overconf = evidence_store.family_overconfidence_rate(family_key) or 0
    yield_rate = sum(1 for c in fam.get("classifications", [])
                     if c in ("model_supports_candidate", "model_partial_match")) / max(count, 1)

    if overconf > 0.40:
        return "noisy", f"overconfidence={overconf:.0%}, too many false positives"
    if count > 8 and yield_rate < 0.25:
        return "cooldown", f"low yield={yield_rate:.0%} after {count} validations"
    if mae is not None and mae < 0.15 and yield_rate >= 0.60:
        return "preferred", f"low MAE={mae:.3f}, high yield={yield_rate:.0%}"
    if mae is not None and mae < 0.30 and yield_rate >= 0.40:
        return "stable", f"decent MAE={mae:.3f}, yield={yield_rate:.0%}"
    if yield_rate >= 0.30:
        return "promising", f"moderate yield={yield_rate:.0%}, worth more exploration"
    if overconf > 0.25:
        return "cautionary", f"elevated overconfidence={overconf:.0%}"

    return "exploratory", f"limited evidence ({count} cases)"


def score_campaign_chemistry(name, profile, evidence_store=None, goals=None):
    """Score a campaign profile with chemistry-aware intelligence.

    Returns dict with score, reasons, target_families, avoided_families.
    """
    goals = goals or ["maximize_defensible_novel_candidates"]
    weights = profile.get("weights", {})
    score = 0.5

    reasons = []
    target_families = []
    avoided_families = []

    # Goal alignment (same as base)
    if "maximize_defensible_novel_candidates" in goals:
        score += weights.get("stability", 0) * 0.25
        score += weights.get("value", 0) * 0.15
    if "reduce_proxy_dependency" in goals:
        score += weights.get("diversity", 0) * 0.15

    # Chemistry-aware profile bonuses
    if profile.get("prefer_familiar_chemistry"):
        score += 0.08
        reasons.append("prefers familiar chemistry")
    if profile.get("use_evidence_calibration"):
        score += 0.05
        reasons.append("evidence-calibrated")

    # Evidence-based campaign history
    if evidence_store:
        camp = evidence_store.by_campaign.get(name, {})
        ev_count = camp.get("count", 0)
        if ev_count == 0:
            score += 0.08
            reasons.append("unexplored campaign")
        elif ev_count > 5:
            confirmed = camp.get("confirmed_count", 0)
            yield_rate = confirmed / max(ev_count, 1)
            if yield_rate >= 0.50:
                score += 0.10
                reasons.append(f"high yield={yield_rate:.0%}")
            elif yield_rate < 0.20:
                score -= 0.10
                reasons.append(f"low yield={yield_rate:.0%}")

        # Family health check across evidence
        noisy_count = 0
        preferred_count = 0
        for fk in evidence_store.by_family:
            status, _ = classify_family_status(fk, evidence_store)
            if status == "noisy" or status == "cooldown":
                noisy_count += 1
                avoided_families.append(fk)
            elif status in ("preferred", "stable"):
                preferred_count += 1
                target_families.append(fk)

        if preferred_count > 3:
            score += 0.05
            reasons.append(f"{preferred_count} reliable families available")

    if not reasons:
        reasons.append("default scoring")

    return {
        "score": round(max(0.0, min(1.0, score)), 3),
        "reasons": reasons,
        "target_families": target_families[:5],
        "avoided_families": avoided_families[:5],
    }


def score_seed_chemistry(seed_pair, evidence_store=None):
    """Score a seed pair based on chemistry context.

    Returns dict with score, family_context, reasons.
    """
    score = 0.5
    reasons = []
    families = []

    for formula in seed_pair:
        comp = parse_formula(formula)
        if not comp:
            continue
        elems = list(comp.keys())
        chem = label_candidate(formula)
        risk = chem.get("risk_level", "unknown")
        family = chem.get("family")

        if risk == "familiar":
            score += 0.08
            reasons.append(f"{formula}: familiar ({family or 'known family'})")
        elif risk == "plausible":
            score += 0.03
        elif risk == "unusual":
            score -= 0.05
            reasons.append(f"{formula}: unusual chemistry")
        elif risk == "risky":
            score -= 0.10
            reasons.append(f"{formula}: risky chemistry")

        if family:
            families.append(family)

        # Evidence bonus
        if evidence_store:
            fk = "-".join(sorted(elems))
            status, _ = classify_family_status(fk, evidence_store)
            if status == "preferred":
                score += 0.08
                reasons.append(f"{formula}: preferred family")
            elif status == "noisy":
                score -= 0.10
                reasons.append(f"{formula}: noisy family (cooldown)")

    if not reasons:
        reasons.append("default seed scoring")

    return {
        "score": round(max(0.0, min(1.0, score)), 3),
        "families": families,
        "reasons": reasons,
    }


def generate_campaign_rationale(profile_name, profile, chemistry_score):
    """Generate human-readable campaign launch rationale."""
    parts = [f"Selected profile: {profile_name}"]
    parts.append(f"Chemistry score: {chemistry_score['score']}")

    if chemistry_score["reasons"]:
        parts.append("Reasons: " + "; ".join(chemistry_score["reasons"]))

    if chemistry_score.get("target_families"):
        parts.append("Target families: " + ", ".join(chemistry_score["target_families"][:3]))

    if chemistry_score.get("avoided_families"):
        parts.append("Avoided families: " + ", ".join(chemistry_score["avoided_families"][:3]))

    desc = profile.get("description", "")
    if desc:
        parts.append(f"Profile focus: {desc}")

    return " | ".join(parts)
