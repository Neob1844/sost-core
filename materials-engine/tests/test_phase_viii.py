#!/usr/bin/env python3
"""Phase VIII Tests — Validation bridge, lifecycle, reconciliation, calibration."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from validation_bridge.lifecycle import can_transition, get_tier, LIFECYCLE_STATES
from validation_bridge.registry import HandoffRegistry
from validation_bridge.result_ingest import ValidationResult, ingest_manual
from validation_bridge.reconciliation import reconcile, classify_for_learning
from validation_bridge.calibration import CalibrationStore
from validation_bridge.bridge import ValidationBridge, DryRunBackend
from autonomous_discovery.policy import get_profile


class TestLifecycle(unittest.TestCase):

    def test_valid_transitions(self):
        self.assertTrue(can_transition("DFT_handoff_ready", "handed_off"))
        self.assertTrue(can_transition("handed_off", "validation_pending"))
        self.assertTrue(can_transition("validation_pending", "result_received"))
        self.assertTrue(can_transition("result_received", "confirmed_partial"))

    def test_invalid_transitions(self):
        self.assertFalse(can_transition("rejected", "handed_off"))
        self.assertFalse(can_transition("watchlist", "handed_off"))
        self.assertFalse(can_transition("DFT_handoff_ready", "confirmed_partial"))

    def test_tier_ordering(self):
        self.assertLess(get_tier("rejected"), get_tier("watchlist"))
        self.assertLess(get_tier("watchlist"), get_tier("validation_candidate"))
        self.assertLess(get_tier("DFT_handoff_ready"), get_tier("handed_off"))
        self.assertLess(get_tier("handed_off"), get_tier("result_received"))

    def test_all_states_have_tiers(self):
        for state in LIFECYCLE_STATES:
            self.assertGreaterEqual(get_tier(state), 0)


class TestRegistry(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.reg = HandoffRegistry(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_register_and_retrieve(self):
        cid = self.reg.register_candidate("AlGa", "element_substitution", "GaAs")
        self.assertIsNotNone(cid)
        self.assertTrue(cid.startswith("cand_"))
        rec = self.reg.get_record(cid)
        self.assertEqual(rec["formula"], "AlGa")
        self.assertEqual(rec["state"], "DFT_handoff_ready")

    def test_hand_off(self):
        cid = self.reg.register_candidate("OZn2", "element_substitution")
        ok, msg = self.reg.hand_off(cid)
        self.assertTrue(ok)
        rec = self.reg.get_record(cid)
        self.assertEqual(rec["state"], "validation_pending")
        self.assertIsNotNone(rec["job_id"])

    def test_save_load_roundtrip(self):
        cid = self.reg.register_candidate("Ni2O", "cross_substitution")
        self.reg.save()
        reg2 = HandoffRegistry(self.tmp.name)
        rec = reg2.get_record(cid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["formula"], "Ni2O")

    def test_count_by_state(self):
        self.reg.register_candidate("A", "m")
        self.reg.register_candidate("B", "m")
        cid = self.reg.register_candidate("C", "m")
        self.reg.hand_off(cid)
        counts = self.reg.count_by_state()
        self.assertEqual(counts.get("DFT_handoff_ready", 0), 2)
        self.assertEqual(counts.get("validation_pending", 0), 1)


class TestReconciliation(unittest.TestCase):

    def test_good_fe_match(self):
        pack = {"formation_energy_predicted": -0.30, "band_gap_predicted": None,
                "uncertainty_score": 0.25, "confidence_score": 0.75}
        result = {"candidate_id": "x", "observed_fe": -0.28, "observed_bg": None}
        rec = reconcile(pack, result)
        self.assertEqual(rec["classification"], "model_supports_candidate")
        self.assertLessEqual(rec["fe_abs_error"], 0.15)

    def test_poor_fe_match(self):
        pack = {"formation_energy_predicted": -0.30, "band_gap_predicted": None,
                "uncertainty_score": 0.20, "confidence_score": 0.80}
        result = {"candidate_id": "x", "observed_fe": 0.50, "observed_bg": None}
        rec = reconcile(pack, result)
        self.assertIn(rec["classification"], ("model_overconfident", "model_partial_match"))
        self.assertGreater(rec["fe_abs_error"], 0.40)

    def test_no_comparison(self):
        pack = {"formation_energy_predicted": None, "band_gap_predicted": None,
                "uncertainty_score": 0.5, "confidence_score": 0.5}
        result = {"candidate_id": "x", "observed_fe": None, "observed_bg": None}
        rec = reconcile(pack, result)
        self.assertEqual(rec["classification"], "no_comparison_data")

    def test_learning_signals_good_match(self):
        pack = {"formation_energy_predicted": -0.30, "confidence_score": 0.75,
                "uncertainty_score": 0.25}
        result = {"candidate_id": "x", "observed_fe": -0.28}
        rec = reconcile(pack, result)
        signals = classify_for_learning(rec)
        self.assertLess(signals["uncertainty_adjustment"], 0)  # decrease uncertainty

    def test_learning_signals_overconfident(self):
        pack = {"formation_energy_predicted": -0.30, "confidence_score": 0.80,
                "uncertainty_score": 0.20}
        result = {"candidate_id": "x", "observed_fe": 0.80}
        rec = reconcile(pack, result)
        signals = classify_for_learning(rec)
        self.assertGreater(signals["uncertainty_adjustment"], 0)  # increase uncertainty
        self.assertEqual(signals["retraining_relevance"], "high")


class TestCalibration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.cal = CalibrationStore(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_update_and_retrieve(self):
        recon = {"classification": "model_overconfident", "fe_abs_error": 0.5}
        signals = {"uncertainty_adjustment": 0.15, "strategy_trust_delta": -0.05}
        self.cal.update_from_reconciliation(recon, signals, "AlGa", "element_substitution")
        self.assertEqual(self.cal.recalibration_count, 1)
        adj = self.cal.get_strategy_adjustment("element_substitution")
        self.assertLess(adj, 0)

    def test_save_load(self):
        recon = {"classification": "model_supports_candidate"}
        signals = {"uncertainty_adjustment": -0.05, "strategy_trust_delta": 0.02}
        self.cal.update_from_reconciliation(recon, signals, "GaIn", "cross_substitution")
        self.cal.save()
        cal2 = CalibrationStore(self.tmp.name)
        self.assertEqual(cal2.recalibration_count, 1)


class TestBridge(unittest.TestCase):

    def setUp(self):
        self.reg_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.cal_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.reg_tmp.close()
        self.cal_tmp.close()
        self.bridge = ValidationBridge(self.reg_tmp.name, self.cal_tmp.name)

    def tearDown(self):
        os.unlink(self.reg_tmp.name)
        os.unlink(self.cal_tmp.name)

    def test_full_lifecycle(self):
        # 1. Submit
        pack = {"formation_energy_predicted": -0.379, "confidence_score": 0.75,
                "uncertainty_score": 0.25}
        cid = self.bridge.submit_for_validation("AlGa", "element_substitution", "GaAs", pack)
        self.assertIsNotNone(cid)

        # 2. Hand off
        ok, msg = self.bridge.hand_off(cid)
        self.assertTrue(ok)

        # 3. Ingest result
        result = ingest_manual(cid, observed_fe=-0.35, validation_source="test",
                                notes="unit test", confidence="medium")
        recon, signals = self.bridge.ingest_result(result)
        self.assertIsNotNone(recon)
        self.assertEqual(recon["classification"], "model_supports_candidate")

        # 4. Check final state
        rec = self.bridge.registry.get_record(cid)
        self.assertEqual(rec["state"], "confirmed_partial")

    def test_dry_run_backend(self):
        pack = {"formation_energy_predicted": -0.50, "band_gap_predicted": 1.5,
                "confidence_score": 0.6, "uncertainty_score": 0.4}
        cid = self.bridge.submit_for_validation("OZn2", "element_substitution", "ZnO", pack)
        self.bridge.hand_off(cid)

        dry = DryRunBackend(self.bridge)
        recon, signals = dry.run_dry_validation(cid, fe_offset=0.03, bg_offset=0.05)
        self.assertIsNotNone(recon)
        self.assertIn(recon["classification"],
                       ("model_supports_candidate", "model_partial_match", "no_comparison_data"))

    def test_ingest_json(self):
        pack = {"formation_energy_predicted": -0.30, "confidence_score": 0.7,
                "uncertainty_score": 0.3}
        cid = self.bridge.submit_for_validation("GaIn", "element_substitution", "GaAs", pack)
        self.bridge.hand_off(cid)

        # Create temp JSON
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix=".json", delete=False)
        json.dump({"results": [{"candidate_id": cid, "observed_fe": -0.28,
                                 "validation_source": "test_json"}]}, tmp)
        tmp.close()

        outcomes = self.bridge.ingest_from_json(tmp.name)
        os.unlink(tmp.name)
        self.assertEqual(len(outcomes), 1)
        self.assertIsNotNone(outcomes[0]["reconciliation"])

    def test_summary(self):
        self.bridge.submit_for_validation("A", "m")
        self.bridge.submit_for_validation("B", "m")
        s = self.bridge.summary()
        self.assertEqual(s["registry"]["total_records"], 2)


class TestValidationPriorityProfile(unittest.TestCase):

    def test_profile_exists(self):
        p = get_profile("validation_priority")
        self.assertIn("weights", p)
        self.assertTrue(p.get("prefer_validated", False))
        self.assertGreater(p["exploit_ratio"], 0.4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
