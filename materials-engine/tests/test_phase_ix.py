#!/usr/bin/env python3
"""Phase IX Tests — Batch workflows, evidence accumulation, reporting, operations."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from validation_bridge.batch import ValidationBatch, BatchManager
from validation_bridge.evidence import EvidenceStore
from validation_bridge.reporting import (
    validation_operations_summary, family_calibration_report,
    strategy_performance_report, priority_handoff_report, report_to_markdown
)
from validation_bridge.registry import HandoffRegistry
from validation_bridge.calibration import CalibrationStore
from autonomous_discovery.policy import get_profile


class TestBatchWorkflows(unittest.TestCase):

    def test_create_batch(self):
        b = ValidationBatch("test_batch", "dry_run", 3)
        b.add_candidate("cand_001")
        b.add_candidate("cand_002")
        self.assertEqual(len(b.candidate_ids), 2)
        self.assertEqual(b.state, "created")

    def test_batch_progress(self):
        b = ValidationBatch("test")
        b.add_candidate("c1")
        b.add_candidate("c2")
        b.add_candidate("c3")
        self.assertEqual(b.progress()["pct"], 0.0)
        b.record_result("c1", {"classification": "model_supports_candidate"})
        self.assertEqual(b.state, "partially_processed")
        self.assertAlmostEqual(b.progress()["pct"], 33.3, places=0)
        b.record_result("c2", {"classification": "model_partial_match"})
        b.record_result("c3", {"classification": "model_overconfident"})
        self.assertEqual(b.state, "complete")
        self.assertEqual(b.progress()["pct"], 100.0)

    def test_batch_serialization(self):
        b = ValidationBatch("serial_test", "manual_review", 5)
        b.add_candidate("c1")
        d = b.to_dict()
        b2 = ValidationBatch.from_dict(d)
        self.assertEqual(b2.name, "serial_test")
        self.assertEqual(b2.backend, "manual_review")
        self.assertEqual(b2.candidate_ids, ["c1"])

    def test_batch_no_duplicate_candidates(self):
        b = ValidationBatch("dedup")
        b.add_candidate("c1")
        b.add_candidate("c1")
        self.assertEqual(len(b.candidate_ids), 1)

    def test_batch_manager(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        try:
            mgr = BatchManager(tmp.name)
            batch = mgr.create_batch("test", ["c1", "c2"], "dry_run")
            self.assertEqual(batch.state, "queued")
            mgr.save()
            mgr2 = BatchManager(tmp.name)
            self.assertEqual(mgr2.summary()["total_batches"], 1)
        finally:
            os.unlink(tmp.name)


class TestEvidenceAccumulation(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.ev = EvidenceStore(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_record_and_query(self):
        recon = {"classification": "model_supports_candidate", "fe_abs_error": 0.08}
        self.ev.record(recon, "GaAs", "element_substitution", "test_campaign",
                        "direct_gnn_lifted", ["Ga", "As"])
        self.assertEqual(self.ev.total_evidence, 1)
        self.assertEqual(self.ev.family_mae("As-Ga", "fe"), 0.08)

    def test_multiple_records(self):
        for err in [0.05, 0.10, 0.15]:
            self.ev.record({"classification": "model_supports_candidate", "fe_abs_error": err},
                            elements=["Ti", "O"])
        self.assertAlmostEqual(self.ev.family_mae("O-Ti", "fe"), 0.10, places=4)

    def test_overconfidence_rate(self):
        self.ev.record({"classification": "model_supports_candidate"}, elements=["Zn", "O"])
        self.ev.record({"classification": "model_overconfident"}, elements=["Zn", "O"])
        self.ev.record({"classification": "model_supports_candidate"}, elements=["Zn", "O"])
        rate = self.ev.family_overconfidence_rate("O-Zn")
        self.assertAlmostEqual(rate, 1/3, places=2)

    def test_strategy_yield(self):
        self.ev.record({"classification": "model_supports_candidate"}, method="element_substitution")
        self.ev.record({"classification": "model_overconfident"}, method="element_substitution")
        yield_rate = self.ev.strategy_yield("element_substitution")
        self.assertAlmostEqual(yield_rate, 0.5, places=2)

    def test_save_load(self):
        self.ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.1},
                        elements=["Ga", "N"])
        self.ev.save()
        ev2 = EvidenceStore(self.tmp.name)
        self.assertEqual(ev2.total_evidence, 1)
        self.assertEqual(ev2.family_mae("Ga-N", "fe"), 0.1)

    def test_top_families(self):
        for _ in range(3):
            self.ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.05},
                            elements=["Ga", "As"])
        for _ in range(3):
            self.ev.record({"classification": "model_overconfident", "fe_abs_error": 0.5},
                            elements=["X", "Y"])
        reliable = self.ev.top_reliable_families(2)
        self.assertEqual(reliable[0][0], "As-Ga")
        unstable = self.ev.top_unstable_families(2)
        self.assertEqual(unstable[0][0], "X-Y")


class TestReporting(unittest.TestCase):

    def test_operations_summary(self):
        reg = HandoffRegistry("/tmp/_test_reg_ix.json")
        from validation_bridge.batch import BatchManager
        mgr = BatchManager("/tmp/_test_batch_ix.json")
        ev = EvidenceStore("/tmp/_test_ev_ix.json")
        cal = CalibrationStore("/tmp/_test_cal_ix.json")
        report = validation_operations_summary(reg, mgr, ev, cal)
        self.assertEqual(report["report_type"], "validation_operations_summary")
        self.assertIn("registry", report)
        self.assertIn("evidence", report)
        # cleanup
        for p in ["/tmp/_test_reg_ix.json", "/tmp/_test_batch_ix.json",
                   "/tmp/_test_ev_ix.json", "/tmp/_test_cal_ix.json"]:
            if os.path.exists(p):
                os.unlink(p)

    def test_family_report(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.08},
                    elements=["Ga", "As"])
        ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.12},
                    elements=["Ga", "As"])
        report = family_calibration_report(ev, cal)
        self.assertIn("As-Ga", report["families"])

    def test_strategy_report(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        ev.record({"classification": "model_supports_candidate"}, method="element_substitution")
        report = strategy_performance_report(ev, cal)
        self.assertIn("element_substitution", report["strategies"])

    def test_markdown_output(self):
        report = {"report_type": "test_report", "generated_at": "now",
                   "metric_a": 42, "items": ["x", "y"]}
        md = report_to_markdown(report)
        self.assertIn("# Test Report", md)
        self.assertIn("**metric_a**: 42", md)


class TestValidationOperationsProfile(unittest.TestCase):

    def test_profile_exists(self):
        p = get_profile("validation_operations")
        self.assertIn("weights", p)
        self.assertTrue(p.get("prefer_diverse_validation", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
