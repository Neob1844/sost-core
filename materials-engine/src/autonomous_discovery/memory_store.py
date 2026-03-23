"""Persistent memory for the autonomous discovery engine.

Tracks: candidates generated, errors, successes, overexplored zones,
rule performance, family performance, and campaign state.
"""
import json, os, time
from collections import defaultdict

DEFAULT_PATH = os.path.expanduser("~/SOST/materials-engine-discovery/memory.json")


class MemoryStore:
    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        self.candidates_seen = set()
        self.candidates_accepted = []
        self.candidates_rejected = []
        self.rule_stats = defaultdict(lambda: {"generated": 0, "accepted": 0, "rejected": 0, "avg_score": 0.0})
        self.family_stats = defaultdict(lambda: {"generated": 0, "accepted": 0, "rejected": 0})
        self.error_patterns = defaultdict(int)  # rejection_reason -> count
        self.overexplored_zones = set()
        self.iteration_count = 0
        self.total_generated = 0
        self.total_accepted = 0
        self.total_rejected = 0
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                self.candidates_seen = set(data.get("candidates_seen", []))
                self.candidates_accepted = data.get("candidates_accepted", [])
                self.candidates_rejected = data.get("candidates_rejected", [])[-1000:]  # keep last 1000
                self.rule_stats = defaultdict(lambda: {"generated": 0, "accepted": 0, "rejected": 0, "avg_score": 0.0},
                                              data.get("rule_stats", {}))
                self.family_stats = defaultdict(lambda: {"generated": 0, "accepted": 0, "rejected": 0},
                                                data.get("family_stats", {}))
                self.error_patterns = defaultdict(int, data.get("error_patterns", {}))
                self.overexplored_zones = set(data.get("overexplored_zones", []))
                self.iteration_count = data.get("iteration_count", 0)
                self.total_generated = data.get("total_generated", 0)
                self.total_accepted = data.get("total_accepted", 0)
                self.total_rejected = data.get("total_rejected", 0)
            except (json.JSONDecodeError, KeyError):
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = {
            "candidates_seen": list(self.candidates_seen)[-5000:],  # cap
            "candidates_accepted": self.candidates_accepted[-500:],
            "candidates_rejected": self.candidates_rejected[-1000:],
            "rule_stats": dict(self.rule_stats),
            "family_stats": dict(self.family_stats),
            "error_patterns": dict(self.error_patterns),
            "overexplored_zones": list(self.overexplored_zones),
            "iteration_count": self.iteration_count,
            "total_generated": self.total_generated,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "last_saved": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def is_duplicate(self, formula):
        return formula in self.candidates_seen

    def record_candidate(self, formula, method, score, accepted, rejection_reason=None):
        self.candidates_seen.add(formula)
        self.total_generated += 1
        # Rule stats
        rs = self.rule_stats[method]
        rs["generated"] += 1
        rs["avg_score"] = (rs["avg_score"] * (rs["generated"] - 1) + score) / rs["generated"]
        # Family stats
        family = _formula_family(formula)
        fs = self.family_stats[family]
        fs["generated"] += 1

        if accepted:
            self.total_accepted += 1
            rs["accepted"] += 1
            fs["accepted"] += 1
            self.candidates_accepted.append({
                "formula": formula, "method": method, "score": round(score, 4),
                "iteration": self.iteration_count,
            })
        else:
            self.total_rejected += 1
            rs["rejected"] += 1
            fs["rejected"] += 1
            if rejection_reason:
                self.error_patterns[rejection_reason] += 1
            self.candidates_rejected.append({
                "formula": formula, "method": method, "reason": rejection_reason or "low_score",
                "iteration": self.iteration_count,
            })

        # Check overexploredity
        if fs["generated"] > 50 and fs["accepted"] / max(fs["generated"], 1) < 0.05:
            self.overexplored_zones.add(family)

    def get_rule_penalty(self, method):
        """Return a penalty factor (0-1) for a generation method. Low = penalized."""
        rs = self.rule_stats.get(method, {"generated": 0, "accepted": 0})
        if rs["generated"] < 5:
            return 1.0  # not enough data
        accept_rate = rs["accepted"] / max(rs["generated"], 1)
        if accept_rate < 0.02:
            return 0.3  # heavily penalized
        elif accept_rate < 0.10:
            return 0.6
        return 1.0

    def get_family_penalty(self, formula):
        """Return penalty for overexplored families."""
        family = _formula_family(formula)
        if family in self.overexplored_zones:
            return 0.3
        fs = self.family_stats.get(family, {"generated": 0})
        if fs["generated"] > 30:
            return 0.7
        return 1.0

    def get_top_errors(self, n=10):
        return sorted(self.error_patterns.items(), key=lambda x: -x[1])[:n]

    def get_top_rules(self, n=5):
        ranked = sorted(self.rule_stats.items(),
                        key=lambda x: -x[1].get("avg_score", 0) * x[1].get("accepted", 0))
        return ranked[:n]

    def summary(self):
        return {
            "iterations": self.iteration_count,
            "total_generated": self.total_generated,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "accept_rate": round(self.total_accepted / max(self.total_generated, 1), 4),
            "unique_candidates": len(self.candidates_seen),
            "overexplored_zones": len(self.overexplored_zones),
            "top_errors": self.get_top_errors(5),
            "top_rules": [(k, v) for k, v in self.get_top_rules(3)],
        }


def _formula_family(formula):
    """Extract a rough 'family' from formula (element set, sorted)."""
    import re
    elements = sorted(set(re.findall(r'[A-Z][a-z]?', formula)))
    return "-".join(elements)
