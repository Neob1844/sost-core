"""Tests for `scripts/trinity/trinity_proof_bundle.py` and its
verifier `scripts/trinity/verify_trinity_bundle.py`.

No network. Synthetic inputs and pinned timestamps. Every test pins
one of the safety properties the bundle must satisfy:

  - dry_run / registered / ready_to_register / no_rewards_active flags
  - Merkle root matches the documented algorithm
  - canonical JSON contains no absolute host path
  - changing any anchor changes proof_bundle_sha256
  - the verifier rejects a tampered bundle
  - the verifier rejects registered=true
  - the capsule preview never reports execution
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILDER_SCRIPT = _REPO_ROOT / "scripts" / "trinity" / "trinity_proof_bundle.py"
_VERIFIER_SCRIPT = _REPO_ROOT / "scripts" / "trinity" / "verify_trinity_bundle.py"


def _load(path: Path, modname: str):
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def builder():
    return _load(_BUILDER_SCRIPT, "trinity_proof_bundle")


@pytest.fixture(scope="module")
def verifier():
    return _load(_VERIFIER_SCRIPT, "verify_trinity_bundle")


# ---------------------------------------------------------------------------
# Helpers: build small synthetic inputs on disk that the CLI can consume.
# ---------------------------------------------------------------------------

def _write_synth_inputs(tmp_path: Path):
    dossier = {
        "schema": "trinity-dossier/v0",
        "aoi": "synth_pb_aoi",
        "fallback_mode": True,
        "source": {
            "scorecard_sha256":
                "11" * 32,
            "scorecard_basename": "scorecard_synth_pb_aoi.json",
            "scorecard_zone": "synth_pb_aoi",
            "scorecard_features_available": 0,
            "scorecard_features_total": 5,
            "honesty_matrix": {"tier": "T1", "what_it_doesnt_see": []},
        },
        "reviews": [],
    }
    plan = {
        "source_dossier_aoi": "synth_pb_aoi",
        "n_reviews_considered": 0,
        "candidates": [],
        "reward_reports": [],
        "queue": {"n_workers": 4, "n_tasks": 0,
                  "total_serial_seconds": 0,
                  "estimated_wallclock_seconds": 0,
                  "per_worker_seconds": [0, 0, 0, 0],
                  "scheduled": [], "dry_run": True},
        "safety_notice": "DRY-RUN ONLY",
        "dry_run": True,
    }
    campaign = {
        "schema": "trinity-campaign-manifest/v0",
        "campaign_name": "pb_test",
        "aoi": "synth_pb_aoi",
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "dossier_sha256": "00" * 32,
        "useful_compute_plan_sha256": "00" * 32,
        "scorecard_sha256": "11" * 32,
        "objectives": [],
        "evidence_gaps": [],
        "next_actions": [],
        "useful_compute_candidate_queue": [],
        "safety_status": {"dry_run": True, "no_rewards_active": True},
        "ready_to_register": True,
        "registered": False,
        "dry_run": True,
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    d_path = tmp_path / "TRINITY_DEMO_DOSSIER_synth.json"
    p_path = tmp_path / "TRINITY_USEFUL_COMPUTE_PLAN_synth.json"
    c_path = tmp_path / "TRINITY_CAMPAIGN_pb_test.json"
    d_path.write_text(json.dumps(dossier), encoding="utf-8")
    p_path.write_text(json.dumps(plan), encoding="utf-8")
    c_path.write_text(json.dumps(campaign), encoding="utf-8")
    return d_path, p_path, c_path


def _run_builder(builder_mod, tmp_path, **overrides):
    d_path, p_path, c_path = _write_synth_inputs(tmp_path)
    out_md = tmp_path / "pb.md"
    out_json = tmp_path / "pb.json"
    argv = [
        "--dossier", str(d_path),
        "--useful-compute-plan", str(p_path),
        "--campaign", str(c_path),
        "--aoi", "synth_pb_aoi",
        "--bundle-name", overrides.get("bundle_name", "pb_test"),
        "--pinned-time", "2026-01-01T00:00:00+00:00",
        "--out-md", str(out_md),
        "--out-json", str(out_json),
    ]
    rc = builder_mod.main(argv)
    return rc, out_md, out_json, d_path, p_path, c_path


# ---------------------------------------------------------------------------
# Builder: determinism, shape, Merkle, anti-leak
# ---------------------------------------------------------------------------

class TestBuilderDeterminism:
    def test_pinned_time_produces_byte_identical_output(self, builder,
                                                          tmp_path):
        rc, _, json_a, *_ = _run_builder(builder, tmp_path / "a")
        assert rc == 0
        rc, _, json_b, *_ = _run_builder(builder, tmp_path / "b")
        assert rc == 0
        assert json_a.read_bytes() == json_b.read_bytes(), \
            "two runs with the same pinned-time must produce " \
            "byte-identical bundles"

    def test_changing_dossier_changes_proof_bundle_sha(self, builder,
                                                        tmp_path):
        rc, _, json_a, d_path, *_ = _run_builder(builder, tmp_path / "a")
        sha_a = hashlib.sha256(json_a.read_bytes()).hexdigest()

        # Mutate the dossier bytes, regenerate, expect a different
        # proof_bundle_sha256.
        rc, _, json_b, _, _, _ = _run_builder(builder, tmp_path / "b")
        d_path_b = tmp_path / "b" / "TRINITY_DEMO_DOSSIER_synth.json"
        original = json.loads(d_path_b.read_text(encoding="utf-8"))
        original["reviews"].append({"hypothesis": {"type": "noise"}})
        d_path_b.write_text(json.dumps(original), encoding="utf-8")
        # Re-run only the builder over the mutated dossier.
        argv = [
            "--dossier", str(d_path_b),
            "--useful-compute-plan",
            str(tmp_path / "b" / "TRINITY_USEFUL_COMPUTE_PLAN_synth.json"),
            "--campaign",
            str(tmp_path / "b" / "TRINITY_CAMPAIGN_pb_test.json"),
            "--aoi", "synth_pb_aoi",
            "--bundle-name", "pb_test",
            "--pinned-time", "2026-01-01T00:00:00+00:00",
            "--out-md", str(tmp_path / "b" / "pb.md"),
            "--out-json", str(tmp_path / "b" / "pb.json"),
        ]
        rc = builder.main(argv)
        assert rc == 0
        sha_b = hashlib.sha256(
            (tmp_path / "b" / "pb.json").read_bytes()
        ).hexdigest()
        assert sha_a != sha_b, (
            "Mutating the dossier did not change the proof bundle "
            "SHA — the bundle is not sensitive to its inputs."
        )


class TestBundleShape:
    def test_required_keys_present(self, builder, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        assert rc == 0
        data = json.loads(js.read_bytes())
        for k in ("schema", "bundle_name", "aoi", "anchors",
                  "anchor_basenames", "merkle", "safety_status",
                  "capsule_preview", "verification"):
            assert k in data, f"missing top-level key {k!r}"
        for ak in ("scorecard_sha256", "dossier_sha256",
                    "useful_compute_plan_sha256", "campaign_sha256"):
            assert ak in data["anchors"], f"missing anchor {ak!r}"

    def test_safety_status_flags(self, builder, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = json.loads(js.read_bytes())
        ss = data["safety_status"]
        assert ss["dry_run"] is True
        assert ss["registered"] is False
        assert ss["ready_to_register"] is True
        assert ss["no_rewards_active"] is True
        assert ss["no_chain_broadcast"] is True

    def test_capsule_preview_is_not_executed(self, builder, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = json.loads(js.read_bytes())
        cp = data["capsule_preview"]
        assert "NOT_EXECUTED" in cp["execution_status"]
        # The manual command is a template, not a real sost-cli call.
        cmd = cp["manual_sost_cli_template"]
        assert "<your-wallet>" in cmd or "OPERATOR-DRIVEN" in cmd


class TestMerkleRoot:
    def test_merkle_root_matches_documented_algorithm(self, builder):
        a = "01" * 32
        b = "02" * 32
        c = "03" * 32
        d = "04" * 32
        expected_node01 = hashlib.sha256(
            bytes.fromhex(a) + bytes.fromhex(b)
        ).digest()
        expected_node23 = hashlib.sha256(
            bytes.fromhex(c) + bytes.fromhex(d)
        ).digest()
        expected_root = hashlib.sha256(
            expected_node01 + expected_node23
        ).hexdigest()
        actual = builder.merkle_root_from_hashes(a, b, c, d)
        assert actual == expected_root

    def test_merkle_root_changes_when_leaf_order_changes(self, builder):
        a = "01" * 32
        b = "02" * 32
        c = "03" * 32
        d = "04" * 32
        r1 = builder.merkle_root_from_hashes(a, b, c, d)
        r2 = builder.merkle_root_from_hashes(b, a, c, d)
        assert r1 != r2

    def test_merkle_root_rejects_malformed_input(self, builder):
        with pytest.raises(ValueError):
            builder.merkle_root_from_hashes(
                "not_hex", "01" * 32, "02" * 32, "03" * 32,
            )

    def test_bundle_merkle_root_in_output(self, builder, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = json.loads(js.read_bytes())
        # Recompute Merkle locally from the anchors and confirm it
        # matches what the bundle stored.
        a = data["anchors"]
        local = builder.merkle_root_from_hashes(
            a["scorecard_sha256"], a["dossier_sha256"],
            a["useful_compute_plan_sha256"], a["campaign_sha256"],
        )
        assert local == data["merkle"]["root"]


class TestAntiLeak:
    def test_no_absolute_paths_in_json(self, builder, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        blob = js.read_text(encoding="utf-8")
        for marker in (str(tmp_path), "/home/", "/opt/", "/Users/"):
            assert marker not in blob, \
                f"host marker {marker!r} leaked into proof bundle JSON"


# ---------------------------------------------------------------------------
# Verifier: must accept clean bundles and reject tampered ones
# ---------------------------------------------------------------------------

class TestVerifierAcceptsClean:
    def test_clean_bundle_passes(self, builder, verifier, tmp_path):
        rc, _, js, d_path, p_path, c_path = _run_builder(builder, tmp_path)
        ok, lines = verifier.verify_bundle(
            js, search_paths=[tmp_path],
        )
        assert ok, "Clean bundle should pass verification.\n" \
            + "\n".join(lines)
        # Every check produced an entry; none was a FAIL.
        assert not any(l.startswith("[FAIL]") for l in lines)

    def test_main_returns_zero_on_clean_bundle(self, builder, verifier,
                                                  tmp_path, capsys):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        rc2 = verifier.main([str(js)])
        assert rc2 == 0


class TestVerifierRejectsTampering:
    def _load_bundle(self, js: Path):
        return json.loads(js.read_text(encoding="utf-8"))

    def _save_bundle(self, js: Path, data):
        # Re-serialise canonically so the JSON parses cleanly.
        js.write_text(
            json.dumps(data, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def test_rejects_wrong_anchor_hash(self, builder, verifier, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = self._load_bundle(js)
        data["anchors"]["dossier_sha256"] = "00" * 32
        self._save_bundle(js, data)
        ok, lines = verifier.verify_bundle(js, search_paths=[tmp_path])
        assert ok is False
        # Either C3 (merkle mismatch) or C10 (local hash mismatch)
        # should fire.
        fails = [l for l in lines if l.startswith("[FAIL]")]
        assert any("C3" in f or "C10" in f for f in fails)

    def test_rejects_registered_true(self, builder, verifier, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = self._load_bundle(js)
        data["safety_status"]["registered"] = True
        self._save_bundle(js, data)
        ok, lines = verifier.verify_bundle(js, search_paths=[tmp_path])
        assert ok is False
        assert any("C5" in l for l in lines if l.startswith("[FAIL]"))

    def test_rejects_no_rewards_active_false(self, builder, verifier,
                                                tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = self._load_bundle(js)
        data["safety_status"]["no_rewards_active"] = False
        self._save_bundle(js, data)
        ok, lines = verifier.verify_bundle(js, search_paths=[tmp_path])
        assert ok is False
        assert any("C6" in l for l in lines if l.startswith("[FAIL]"))

    def test_rejects_dry_run_false(self, builder, verifier, tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = self._load_bundle(js)
        data["safety_status"]["dry_run"] = False
        self._save_bundle(js, data)
        ok, lines = verifier.verify_bundle(js, search_paths=[tmp_path])
        assert ok is False
        assert any("C4" in l for l in lines if l.startswith("[FAIL]"))

    def test_rejects_tampered_merkle_root(self, builder, verifier,
                                            tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = self._load_bundle(js)
        data["merkle"]["root"] = "ff" * 32
        self._save_bundle(js, data)
        ok, lines = verifier.verify_bundle(js, search_paths=[tmp_path])
        assert ok is False
        assert any("C3" in l for l in lines if l.startswith("[FAIL]"))

    def test_rejects_executed_capsule_status(self, builder, verifier,
                                                tmp_path):
        rc, _, js, *_ = _run_builder(builder, tmp_path)
        data = self._load_bundle(js)
        data["capsule_preview"]["execution_status"] = "EXECUTED"
        self._save_bundle(js, data)
        ok, lines = verifier.verify_bundle(js, search_paths=[tmp_path])
        assert ok is False
        assert any("C9" in l for l in lines if l.startswith("[FAIL]"))


# ---------------------------------------------------------------------------
# Verifier safety: no network, no broadcast helpers
# ---------------------------------------------------------------------------

class TestVerifierSafety:
    def test_verifier_module_has_no_broadcast_helper(self, verifier):
        forbidden = (
            "broadcast", "activate_rewards", "publish_task",
            "open_public_api", "move_funds", "register_on_chain",
            "sost_cli_send",
        )
        for name in forbidden:
            assert not hasattr(verifier, name), \
                f"verifier unexpectedly exposes {name!r}"

    def test_builder_module_has_no_broadcast_helper(self, builder):
        forbidden = (
            "broadcast", "activate_rewards", "publish_task",
            "open_public_api", "move_funds", "register_on_chain",
            "sost_cli_send",
        )
        for name in forbidden:
            assert not hasattr(builder, name), \
                f"builder unexpectedly exposes {name!r}"
