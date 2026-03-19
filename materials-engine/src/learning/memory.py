"""Learning memory — identify promising regions and model failures.

Phase III.G: Scaffold for the learning loop. Analyzes feedback to find
patterns that should inform future model retraining.

NOT an active retraining system — just the analysis layer.
"""

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import List, Optional, Dict

from .feedback import FeedbackMemory, FeedbackEntry

log = logging.getLogger(__name__)

LEARNING_DIR = "artifacts/learning"


def build_learning_queue(feedback: FeedbackMemory) -> List[dict]:
    """Identify entries that should feed into future retraining.

    Candidates for retraining:
    - Entries with decision='needs_retrain'
    - Entries with large prediction error
    - Entries with observed_value (any — they're valuable training data)
    """
    queue = []
    for entry in feedback._entries:
        reasons = []
        priority = 0.0

        if entry.decision == "needs_retrain":
            reasons.append("flagged_needs_retrain")
            priority += 0.4

        if entry.observed_value is not None:
            reasons.append("has_observed_value")
            priority += 0.3

        if entry.error is not None and entry.error > 0.5:
            reasons.append("large_prediction_error")
            priority += 0.3

        if reasons:
            queue.append({
                "feedback_id": entry.feedback_id,
                "formula": entry.formula,
                "target_property": entry.target_property,
                "predicted": entry.predicted_value,
                "observed": entry.observed_value,
                "error": entry.error,
                "reasons": reasons,
                "priority": round(min(1.0, priority), 3),
            })

    queue.sort(key=lambda x: -x["priority"])
    return queue


def rank_learning_candidates(feedback: FeedbackMemory, top_k: int = 20) -> List[dict]:
    """Rank candidates by learning value."""
    return build_learning_queue(feedback)[:top_k]


def summarize_model_failures(feedback: FeedbackMemory) -> dict:
    """Identify systematic model failures by property and element family."""
    failures_by_prop = defaultdict(list)
    failures_by_elem = defaultdict(list)

    for entry in feedback._entries:
        if entry.error is not None and entry.error > 0.5:
            failures_by_prop[entry.target_property].append(entry.error)
            for el in entry.elements:
                failures_by_elem[el].append(entry.error)

    return {
        "by_property": {
            prop: {
                "count": len(errs),
                "mean_error": round(sum(errs) / len(errs), 4),
                "max_error": round(max(errs), 4),
            }
            for prop, errs in failures_by_prop.items()
        },
        "by_element": {
            el: {
                "count": len(errs),
                "mean_error": round(sum(errs) / len(errs), 4),
            }
            for el, errs in sorted(failures_by_elem.items(),
                                    key=lambda x: -len(x[1]))[:20]
        },
        "total_failures": sum(len(v) for v in failures_by_prop.values()),
        "note": "Failure defined as prediction error > 0.5. "
                "This is a scaffold — real analysis requires observed values.",
    }


def summarize_promising_regions(feedback: FeedbackMemory) -> dict:
    """Identify chemical regions producing good candidates."""
    promoted = defaultdict(int)
    kept = defaultdict(int)

    for entry in feedback._entries:
        for el in entry.elements:
            if entry.decision == "promote":
                promoted[el] += 1
            elif entry.decision == "keep":
                kept[el] += 1

    return {
        "promoted_elements": dict(sorted(promoted.items(),
                                          key=lambda x: -x[1])[:15]),
        "kept_elements": dict(sorted(kept.items(),
                                      key=lambda x: -x[1])[:15]),
        "note": "Elements frequently appearing in promoted/kept candidates. "
                "Scaffold — requires real feedback data to be meaningful.",
    }


def generate_learning_summary(feedback: FeedbackMemory,
                              output_dir: str = LEARNING_DIR) -> dict:
    """Generate complete learning summary with artifacts."""
    os.makedirs(output_dir, exist_ok=True)

    queue = build_learning_queue(feedback)
    failures = summarize_model_failures(feedback)
    regions = summarize_promising_regions(feedback)

    summary = {
        "total_feedback": feedback.size,
        "learning_queue_size": len(queue),
        "learning_queue": queue[:20],
        "model_failures": failures,
        "promising_regions": regions,
        "feedback_status": feedback.status(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Learning loop scaffold. Real retraining not yet triggered. "
                "Queue populated from feedback entries with observed values or errors.",
    }

    # Save artifacts
    with open(os.path.join(output_dir, "learning_queue.json"), "w") as f:
        json.dump(queue, f, indent=2)

    md = "# Learning Summary\n\n"
    md += f"**Total feedback entries:** {feedback.size}\n"
    md += f"**Learning queue size:** {len(queue)}\n\n"
    if queue:
        md += "## Top Learning Candidates\n\n"
        md += "| Formula | Property | Predicted | Observed | Error | Priority |\n"
        md += "|---------|----------|-----------|----------|-------|----------|\n"
        for q in queue[:10]:
            md += (f"| {q['formula']} | {q['target_property']} | "
                   f"{q['predicted']} | {q['observed']} | {q['error']} | "
                   f"{q['priority']} |\n")
    md += "\n## Model Failures\n\n"
    md += f"Total failures (error > 0.5): {failures['total_failures']}\n\n"
    md += "## Note\n\n"
    md += summary["note"] + "\n"

    with open(os.path.join(output_dir, "learning_summary.md"), "w") as f:
        f.write(md)

    return summary
