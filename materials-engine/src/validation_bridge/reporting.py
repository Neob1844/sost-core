"""Scientific reporting — operational reports for validation pipeline.

Generates JSON, Markdown, and summary reports for CTO/scientific review.
"""
import json, time


def validation_operations_summary(registry, batch_manager, evidence, calibration):
    """Generate a high-level validation operations summary."""
    return {
        "report_type": "validation_operations_summary",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "registry": registry.summary(),
        "batches": batch_manager.summary(),
        "evidence": evidence.summary(),
        "calibration": calibration.summary(),
    }


def family_calibration_report(evidence, calibration):
    """Report on per-family prediction accuracy and trust."""
    families = {}
    for key in evidence.by_family:
        fam = evidence.by_family[key]
        if fam["count"] < 1:
            continue
        fe_mae = evidence.family_mae(key, "fe")
        bg_mae = evidence.family_mae(key, "bg")
        overconf = evidence.family_overconfidence_rate(key)
        trust_adj = calibration.get_family_adjustment(key.split("-"))
        families[key] = {
            "evidence_count": fam["count"],
            "fe_mae": fe_mae,
            "bg_mae": bg_mae,
            "overconfidence_rate": overconf,
            "trust_adjustment": trust_adj,
        }
    return {
        "report_type": "family_calibration",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "families": families,
        "top_reliable": evidence.top_reliable_families(5),
        "top_unstable": evidence.top_unstable_families(5),
    }


def strategy_performance_report(evidence, calibration):
    """Report on per-strategy validation yield and trust."""
    strategies = {}
    for method in evidence.by_strategy:
        strat = evidence.by_strategy[method]
        if strat["count"] < 1:
            continue
        yield_rate = evidence.strategy_yield(method)
        trust_adj = calibration.get_strategy_adjustment(method)
        strategies[method] = {
            "evidence_count": strat["count"],
            "validation_yield": yield_rate,
            "trust_adjustment": trust_adj,
        }
    return {
        "report_type": "strategy_performance",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategies": strategies,
    }


def priority_handoff_report(registry):
    """Report on candidates ready for handoff."""
    ready = registry.get_all_handoff_ready()
    pending = registry.get_pending()
    return {
        "report_type": "priority_handoff",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "handoff_ready_count": len(ready),
        "pending_count": len(pending),
        "handoff_ready": [
            {"candidate_id": r["candidate_id"], "formula": r.get("formula", "?"),
             "method": r.get("method", "?")}
            for r in ready[:20]
        ],
    }


def report_to_markdown(report):
    """Convert any report dict to readable Markdown."""
    rtype = report.get("report_type", "unknown")
    lines = [f"# {rtype.replace('_', ' ').title()}", "",
             f"Generated: {report.get('generated_at', '?')}", ""]

    for key, val in report.items():
        if key in ("report_type", "generated_at"):
            continue
        if isinstance(val, dict):
            lines.append(f"## {key}")
            for k2, v2 in val.items():
                lines.append(f"- **{k2}**: {v2}")
            lines.append("")
        elif isinstance(val, list):
            lines.append(f"## {key}")
            for item in val:
                lines.append(f"- {item}")
            lines.append("")
        else:
            lines.append(f"- **{key}**: {val}")

    return "\n".join(lines)


def phase_xiii_dossier_section(candidate):
    """Generate Phase XIII dossier section for a candidate.

    Covers relaxation readiness, structure repair, and stronger compute suitability.
    """
    relax = candidate.get("relaxation_readiness", {})
    repair = candidate.get("structure_repair", {})
    phys = candidate.get("physics_screening", {})

    return {
        "section": "phase_xiii_compute_readiness",
        "relaxation_ready": relax.get("relaxation_ready", False),
        "relaxation_tier": relax.get("relaxation_readiness_tier", "not_assessed"),
        "structure_repair_needed": repair.get("repair_severity", "not_assessed"),
        "repair_actions": repair.get("repair_actions_recommended", []),
        "stronger_compute_suitable": relax.get("stronger_compute_candidate", False),
        "structure_sanity_score": phys.get("structure_sanity_score"),
        "geometry_warnings_count": len(phys.get("geometry_warnings", [])),
        "rationale": relax.get("relaxation_rationale", "Not assessed."),
        "plain_language": _plain_language_compute_readiness(relax, repair),
    }


def _plain_language_compute_readiness(relax, repair):
    """Human-readable summary of compute readiness."""
    tier = relax.get("relaxation_readiness_tier", "unknown")
    if tier == "relaxation_ready":
        return "This structure looks usable as-is for stronger computational methods."
    elif tier == "structure_repair_candidate":
        sev = repair.get("repair_severity", "unknown")
        return f"This structure needs cleanup ({sev} severity) before it can be used for serious computation."
    elif tier == "stronger_compute_with_caveats":
        return "This structure might work for stronger compute, but has some issues to watch."
    elif tier == "not_ready_discard_or_rebuild":
        return "This structure is not suitable for stronger computation in its current form."
    return "Compute readiness has not been assessed for this candidate."
