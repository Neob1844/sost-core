"""Calibration intelligence — converts accumulated evidence into actionable
scoring adjustments for the autonomous discovery engine.

Provides family trust, strategy trust, and origin trust signals that
the scorer and uncertainty modules can use to make evidence-driven decisions.
"""


def compute_family_trust(elements, evidence_store, calibration_store):
    """Compute trust score for an element family based on historical evidence.

    Returns dict with:
      family_trust_score: -1.0 (very unreliable) to 1.0 (very reliable)
      family_overconfidence_rate: 0-1
      family_mae_fe: float or None
      family_validation_yield: float or None
      family_evidence_count: int
      family_reliability: "strong" | "moderate" | "weak" | "unknown"
    """
    family_key = "-".join(sorted(elements))
    ev = evidence_store
    cal = calibration_store

    count = ev.by_family.get(family_key, {}).get("count", 0) if ev else 0
    mae_fe = ev.family_mae(family_key, "fe") if ev and count > 0 else None
    overconf = ev.family_overconfidence_rate(family_key) if ev and count > 0 else None
    cal_adj = cal.get_family_adjustment(elements) if cal else 0.0

    # Compute trust score
    trust = 0.0  # neutral
    if count == 0:
        trust = 0.0  # no evidence
        reliability = "unknown"
    else:
        # Positive: low MAE, low overconfidence
        if mae_fe is not None and mae_fe < 0.15:
            trust += 0.3
        elif mae_fe is not None and mae_fe < 0.40:
            trust += 0.1
        elif mae_fe is not None:
            trust -= 0.2

        if overconf is not None and overconf < 0.15:
            trust += 0.2
        elif overconf is not None and overconf > 0.40:
            trust -= 0.3

        # Add calibration adjustment
        trust += cal_adj

        trust = max(-1.0, min(1.0, round(trust, 4)))

        if trust >= 0.3:
            reliability = "strong"
        elif trust >= 0.0:
            reliability = "moderate"
        elif trust >= -0.3:
            reliability = "weak"
        else:
            reliability = "weak"

    return {
        "family_trust_score": trust,
        "family_overconfidence_rate": overconf,
        "family_mae_fe": mae_fe,
        "family_evidence_count": count,
        "family_reliability": reliability,
        "family_key": family_key,
    }


def compute_strategy_trust(method, evidence_store, calibration_store):
    """Compute trust score for a generation strategy.

    Returns dict with:
      strategy_trust_score: -1.0 to 1.0
      strategy_validation_yield: 0-1 or None
      strategy_evidence_count: int
      strategy_reliability: "strong" | "moderate" | "weak" | "unknown"
    """
    ev = evidence_store
    cal = calibration_store

    count = ev.by_strategy.get(method, {}).get("count", 0) if ev else 0
    yield_rate = ev.strategy_yield(method) if ev and count > 0 else None
    cal_adj = cal.get_strategy_adjustment(method) if cal else 0.0

    trust = 0.0
    if count == 0:
        reliability = "unknown"
    else:
        if yield_rate is not None and yield_rate >= 0.60:
            trust += 0.3
        elif yield_rate is not None and yield_rate >= 0.40:
            trust += 0.1
        elif yield_rate is not None:
            trust -= 0.2

        trust += cal_adj
        trust = max(-1.0, min(1.0, round(trust, 4)))

        if trust >= 0.2:
            reliability = "strong"
        elif trust >= 0.0:
            reliability = "moderate"
        else:
            reliability = "weak"

    return {
        "strategy_trust_score": trust,
        "strategy_validation_yield": yield_rate,
        "strategy_evidence_count": count,
        "strategy_reliability": reliability,
    }


def compute_scoring_adjustments(family_trust, strategy_trust):
    """Convert trust scores into scoring adjustments for the engine.

    Returns dict with:
      family_trust_bonus: float (-0.10 to +0.08)
      strategy_trust_bonus: float (-0.06 to +0.05)
      noise_suppression_penalty: float (0.0 to 0.15)
      evidence_quality_label: str
    """
    ft = family_trust.get("family_trust_score", 0)
    st = strategy_trust.get("strategy_trust_score", 0)

    # Family trust → scoring adjustment
    if ft >= 0.3:
        family_bonus = 0.08  # historically reliable family
    elif ft >= 0.0:
        family_bonus = 0.0   # neutral
    elif ft >= -0.3:
        family_bonus = -0.05  # somewhat unreliable
    else:
        family_bonus = -0.10  # historically poor

    # Strategy trust → scoring adjustment
    if st >= 0.2:
        strategy_bonus = 0.05
    elif st >= 0.0:
        strategy_bonus = 0.0
    else:
        strategy_bonus = -0.06

    # Noise suppression: penalize if both family AND strategy are weak
    noise = 0.0
    if ft < -0.2 and st < -0.1:
        noise = 0.15  # strong noise penalty
    elif ft < -0.1 or st < -0.1:
        noise = 0.05  # mild noise penalty

    # Label
    if family_bonus > 0 and strategy_bonus > 0:
        label = "evidence_supported"
    elif family_bonus >= 0 and strategy_bonus >= 0:
        label = "evidence_neutral"
    elif noise > 0.10:
        label = "evidence_warns"
    else:
        label = "evidence_mixed"

    return {
        "family_trust_bonus": round(family_bonus, 4),
        "strategy_trust_bonus": round(strategy_bonus, 4),
        "noise_suppression_penalty": round(noise, 4),
        "evidence_quality_label": label,
    }
