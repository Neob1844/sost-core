"""Validation bridge — orchestrates the full validation lifecycle.

Connects: candidate selection → handoff → result ingestion →
reconciliation → calibration → learning feedback.
"""
import json, os
from .registry import HandoffRegistry
from .result_ingest import ValidationResult, ingest_json, ingest_csv, ingest_manual
from .reconciliation import reconcile, classify_for_learning
from .calibration import CalibrationStore
from .lifecycle import can_transition, LIFECYCLE_STATES


class ValidationBridge:
    """Orchestrates the full validation lifecycle for candidates."""

    def __init__(self, registry_path=None, calibration_path=None):
        self.registry = HandoffRegistry(registry_path)
        self.calibration = CalibrationStore(calibration_path)

    def submit_for_validation(self, formula, method, parent_a="", handoff_pack=None):
        """Register a candidate and prepare for handoff.

        Returns (candidate_id, job_id or None).
        """
        cid = self.registry.register_candidate(formula, method, parent_a, handoff_pack)
        return cid

    def hand_off(self, candidate_id):
        """Move candidate to validation queue."""
        return self.registry.hand_off(candidate_id)

    def ingest_result(self, validation_result):
        """Ingest a validation result and trigger reconciliation.

        Args:
            validation_result: ValidationResult instance or dict

        Returns:
            (reconciliation_dict, learning_signals_dict) or (None, None) if failed
        """
        if isinstance(validation_result, ValidationResult):
            vr = validation_result.to_dict()
        else:
            vr = validation_result

        cid = vr.get("candidate_id")
        rec = self.registry.get_record(cid)
        if not rec:
            return None, None

        # Transition to result_received
        self.registry.transition(cid, "result_received", "validation result ingested")

        # Store result
        rec["validation_result"] = vr

        # Reconcile if handoff pack exists
        pack = rec.get("handoff_pack") or {}
        recon = reconcile(pack, vr)
        rec["reconciliation"] = recon

        # Determine final state
        cls = recon.get("classification", "inconclusive")
        if cls == "model_supports_candidate":
            self.registry.transition(cid, "confirmed_partial",
                                      "model prediction partially confirmed by validation")
        elif cls in ("model_overconfident", "model_underconfident"):
            self.registry.transition(cid, "disagrees_with_model",
                                      f"validation disagrees: {cls}")
        else:
            self.registry.transition(cid, "inconclusive",
                                      "validation result inconclusive")

        # Learning signals
        signals = classify_for_learning(recon)

        # Update calibration
        self.calibration.update_from_reconciliation(
            recon, signals,
            formula=rec.get("formula", ""),
            method=rec.get("method", ""))

        return recon, signals

    def ingest_from_json(self, path):
        """Ingest multiple results from a JSON file."""
        results = ingest_json(path)
        outcomes = []
        for vr in results:
            recon, signals = self.ingest_result(vr)
            outcomes.append({"candidate_id": vr.candidate_id,
                              "reconciliation": recon, "signals": signals})
        return outcomes

    def ingest_from_csv(self, path):
        """Ingest multiple results from a CSV file."""
        results = ingest_csv(path)
        outcomes = []
        for vr in results:
            recon, signals = self.ingest_result(vr)
            outcomes.append({"candidate_id": vr.candidate_id,
                              "reconciliation": recon, "signals": signals})
        return outcomes

    def get_pending(self):
        """Get all candidates awaiting validation."""
        return self.registry.get_pending()

    def get_handoff_ready(self):
        """Get all candidates ready for handoff."""
        return self.registry.get_all_handoff_ready()

    def save(self):
        self.registry.save()
        self.calibration.save()

    def summary(self):
        return {
            "registry": self.registry.summary(),
            "calibration": self.calibration.summary(),
        }


class DryRunBackend:
    """Dry-run backend — validates flow without real DFT.

    Simulates the validation lifecycle: submit → hand off → receive result.
    Uses a simple heuristic to generate fake results for testing.
    """

    def __init__(self, bridge):
        self.bridge = bridge

    def run_dry_validation(self, candidate_id, fe_offset=0.05, bg_offset=0.10):
        """Simulate a validation result for testing.

        Generates an observation by applying small offsets to the predicted values.
        This is NOT real DFT — it's for flow testing only.
        """
        rec = self.bridge.registry.get_record(candidate_id)
        if not rec:
            return None, "candidate not found"

        pack = rec.get("handoff_pack") or {}
        pred_fe = pack.get("formation_energy_predicted")
        pred_bg = pack.get("band_gap_predicted")

        obs_fe = round(pred_fe + fe_offset, 4) if pred_fe is not None else None
        obs_bg = round(pred_bg + bg_offset, 4) if pred_bg is not None else None

        result = ingest_manual(
            candidate_id,
            observed_fe=obs_fe,
            observed_bg=obs_bg,
            validation_source="dry_run",
            validation_type="simulated",
            notes=f"DRY RUN: offset FE={fe_offset}, BG={bg_offset}. NOT REAL DFT.",
            confidence="none",
        )

        recon, signals = self.bridge.ingest_result(result)
        return recon, signals
