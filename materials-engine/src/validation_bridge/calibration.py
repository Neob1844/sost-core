"""Calibration update — feed validation evidence back into scoring.

Tracks family-level and strategy-level trust adjustments based on
accumulated reconciliation results. Persisted as JSON.
"""
import json, os, time


class CalibrationStore:
    """Persistent calibration data from validation evidence."""

    def __init__(self, path=None):
        self.path = path or os.path.expanduser(
            "~/SOST/materials-engine-discovery/calibration.json")
        self.family_trust = {}       # element_set_key → trust_delta
        self.strategy_trust = {}     # method → trust_delta
        self.reconciliation_log = [] # list of reconciliation summaries
        self.recalibration_count = 0
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                self.family_trust = data.get("family_trust", {})
                self.strategy_trust = data.get("strategy_trust", {})
                self.reconciliation_log = data.get("reconciliation_log", [])
                self.recalibration_count = data.get("recalibration_count", 0)
            except Exception:
                pass

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({
                "family_trust": self.family_trust,
                "strategy_trust": self.strategy_trust,
                "reconciliation_log": self.reconciliation_log[-200:],  # keep last 200
                "recalibration_count": self.recalibration_count,
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, f, indent=2, default=str)

    def update_from_reconciliation(self, reconciliation, learning_signals, formula="", method=""):
        """Apply learning signals from a reconciliation to calibration state."""
        # Family trust
        elements = sorted(set(c for c in formula if c.isupper()))  # rough element extraction
        family_key = "-".join(elements) if elements else "unknown"

        current_family = self.family_trust.get(family_key, 0.0)
        delta = learning_signals.get("uncertainty_adjustment", 0.0)
        self.family_trust[family_key] = round(max(-0.5, min(0.5, current_family + delta)), 4)

        # Strategy trust
        current_strategy = self.strategy_trust.get(method, 0.0)
        s_delta = learning_signals.get("strategy_trust_delta", 0.0)
        self.strategy_trust[method] = round(max(-0.3, min(0.3, current_strategy + s_delta)), 4)

        # Log
        self.reconciliation_log.append({
            "formula": formula,
            "method": method,
            "family_key": family_key,
            "classification": reconciliation.get("classification"),
            "fe_abs_error": reconciliation.get("fe_abs_error"),
            "bg_abs_error": reconciliation.get("bg_abs_error"),
            "uncertainty_adj": delta,
            "strategy_adj": s_delta,
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        self.recalibration_count += 1

    def get_family_adjustment(self, elements):
        """Get cumulative trust adjustment for an element family."""
        family_key = "-".join(sorted(elements))
        return self.family_trust.get(family_key, 0.0)

    def get_strategy_adjustment(self, method):
        """Get cumulative trust adjustment for a generation strategy."""
        return self.strategy_trust.get(method, 0.0)

    def get_overestimated_families(self, threshold=-0.05):
        """Get families where the model consistently overestimates."""
        return {k: v for k, v in self.family_trust.items() if v <= threshold}

    def get_underperforming_strategies(self, threshold=-0.03):
        """Get strategies that produce poorly-validating candidates."""
        return {k: v for k, v in self.strategy_trust.items() if v <= threshold}

    def summary(self):
        return {
            "recalibration_count": self.recalibration_count,
            "families_tracked": len(self.family_trust),
            "strategies_tracked": len(self.strategy_trust),
            "overestimated_families": self.get_overestimated_families(),
            "underperforming_strategies": self.get_underperforming_strategies(),
            "recent_log_count": len(self.reconciliation_log),
        }
