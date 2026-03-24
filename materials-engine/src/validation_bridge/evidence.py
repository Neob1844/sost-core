"""Evidence accumulation — longitudinal tracking by family, strategy, campaign.

Tracks prediction accuracy, calibration drift, and validation yield over time.
"""
import json, os, time
from collections import defaultdict


class EvidenceStore:
    """Accumulates validation evidence longitudinally."""

    def __init__(self, path=None):
        self.path = path or os.path.expanduser(
            "~/SOST/materials-engine-discovery/evidence_store.json")
        self.by_family = defaultdict(lambda: {"count": 0, "fe_errors": [], "bg_errors": [],
                                                "classifications": [], "trust_history": []})
        self.by_strategy = defaultdict(lambda: {"count": 0, "fe_errors": [], "bg_errors": [],
                                                  "classifications": [], "yield_rate": 0})
        self.by_campaign = defaultdict(lambda: {"count": 0, "classifications": [],
                                                  "handoff_count": 0, "confirmed_count": 0})
        self.by_origin = defaultdict(lambda: {"count": 0, "fe_errors": [], "bg_errors": []})
        self.total_evidence = 0
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                # Restore defaultdicts from plain dicts
                for k, v in data.get("by_family", {}).items():
                    self.by_family[k] = v
                for k, v in data.get("by_strategy", {}).items():
                    self.by_strategy[k] = v
                for k, v in data.get("by_campaign", {}).items():
                    self.by_campaign[k] = v
                for k, v in data.get("by_origin", {}).items():
                    self.by_origin[k] = v
                self.total_evidence = data.get("total_evidence", 0)
            except Exception:
                pass

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({
                "by_family": dict(self.by_family),
                "by_strategy": dict(self.by_strategy),
                "by_campaign": dict(self.by_campaign),
                "by_origin": dict(self.by_origin),
                "total_evidence": self.total_evidence,
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, f, indent=2, default=str)

    def record(self, reconciliation, formula="", method="", campaign="",
               prediction_origin="unknown", elements=None):
        """Record a reconciliation result into all accumulation dimensions."""
        self.total_evidence += 1
        cls = reconciliation.get("classification", "unknown")
        fe_ae = reconciliation.get("fe_abs_error")
        bg_ae = reconciliation.get("bg_abs_error")

        # Family key
        family_key = "-".join(sorted(elements)) if elements else "unknown"
        fam = self.by_family[family_key]
        fam["count"] += 1
        if fe_ae is not None:
            fam["fe_errors"].append(fe_ae)
            fam["fe_errors"] = fam["fe_errors"][-100:]  # keep last 100
        if bg_ae is not None:
            fam["bg_errors"].append(bg_ae)
            fam["bg_errors"] = fam["bg_errors"][-100:]
        fam["classifications"].append(cls)
        fam["classifications"] = fam["classifications"][-100:]

        # Strategy
        strat = self.by_strategy[method]
        strat["count"] += 1
        if fe_ae is not None:
            strat["fe_errors"].append(fe_ae)
            strat["fe_errors"] = strat["fe_errors"][-100:]
        if bg_ae is not None:
            strat["bg_errors"].append(bg_ae)
            strat["bg_errors"] = strat["bg_errors"][-100:]
        strat["classifications"].append(cls)
        strat["classifications"] = strat["classifications"][-100:]

        # Campaign
        camp = self.by_campaign[campaign]
        camp["count"] += 1
        camp["classifications"].append(cls)
        camp["classifications"] = camp["classifications"][-100:]
        if cls in ("model_supports_candidate", "model_partial_match"):
            camp["confirmed_count"] += 1

        # Origin (direct_gnn vs proxy)
        orig = self.by_origin[prediction_origin]
        orig["count"] += 1
        if fe_ae is not None:
            orig["fe_errors"].append(fe_ae)
            orig["fe_errors"] = orig["fe_errors"][-100:]
        if bg_ae is not None:
            orig["bg_errors"].append(bg_ae)
            orig["bg_errors"] = orig["bg_errors"][-100:]

    def family_mae(self, family_key, target="fe"):
        """Get mean absolute error for a family."""
        fam = self.by_family.get(family_key, {})
        errors = fam.get(f"{target}_errors", [])
        if not errors:
            return None
        return round(sum(errors) / len(errors), 4)

    def family_overconfidence_rate(self, family_key):
        """Rate of overconfident predictions for a family."""
        fam = self.by_family.get(family_key, {})
        cls = fam.get("classifications", [])
        if not cls:
            return None
        return round(cls.count("model_overconfident") / len(cls), 4)

    def strategy_yield(self, method):
        """Fraction of candidates that validate positively."""
        strat = self.by_strategy.get(method, {})
        cls = strat.get("classifications", [])
        if not cls:
            return None
        positive = sum(1 for c in cls if c in ("model_supports_candidate", "model_partial_match"))
        return round(positive / len(cls), 4)

    def top_reliable_families(self, n=5):
        """Families with lowest mean FE error."""
        families = []
        for k, v in self.by_family.items():
            mae = self.family_mae(k, "fe")
            if mae is not None and v["count"] >= 2:
                families.append((k, mae, v["count"]))
        families.sort(key=lambda x: x[1])
        return families[:n]

    def top_unstable_families(self, n=5):
        """Families with highest overconfidence rate."""
        families = []
        for k, v in self.by_family.items():
            rate = self.family_overconfidence_rate(k)
            if rate is not None and v["count"] >= 2:
                families.append((k, rate, v["count"]))
        families.sort(key=lambda x: -x[1])
        return families[:n]

    def summary(self):
        return {
            "total_evidence": self.total_evidence,
            "families_tracked": len(self.by_family),
            "strategies_tracked": len(self.by_strategy),
            "campaigns_tracked": len(self.by_campaign),
            "origins_tracked": len(self.by_origin),
        }
