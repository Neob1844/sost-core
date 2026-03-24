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
