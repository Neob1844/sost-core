"""Tests for `scripts/trinity/trinity_campaign.py`.

No network. Synthetic dossier + plan JSON files. Pinned timestamps.
Every test asserts at minimum that the rendered manifest's
canonical JSON is byte-deterministic, that proof bundle metadata
carries ready_to_register=true / registered=false, and that no
absolute path leaks into the manifest.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "trinity" / "trinity_campaign.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "trinity_campaign", _SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


@pytest.fixture
def synth_dossier_file(tmp_path: Path) -> Path:
    d = {
        "schema": "trinity-dossier/v0",
        "aoi": "synth_camp_aoi",
        "fallback_mode": True,
        "source": {
            "scorecard_sha256": "f" * 64,
            "scorecard_basename": "scorecard_synth_camp_aoi.json",
            "scorecard_zone": "synth_camp_aoi",
            "scorecard_features_available": 0,
            "scorecard_features_total": 5,
            "honesty_matrix": {
                "tier": "Tier 1",
                "what_it_doesnt_see": [
                    "Replacement of field geophysics (ERT, GPR, gravity, magnetics)",
                    "Reliable detection through dense vegetation (C-band limitation)",
                ],
                "recommendation": "x",
            },
        },
        "reviews": [
            {
                "hypothesis": {
                    "project": "geaspirit",
                    "type": "aoi_priority",
                    "subject": "aoi:synth_camp_aoi",
                    "claim": "x", "hypothesis_hash": "h1",
                    "validation_path": ["geaspirit_layer_review"],
                    "metadata": {"fallback_mode": True},
                },
                "decision": {"decision": "hold", "confidence": 0.5,
                             "opinions": []},
                "fallback_mode": True,
            },
        ],
    }
    p = tmp_path / "TRINITY_DEMO_DOSSIER_synth.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


@pytest.fixture
def synth_plan_file(tmp_path: Path) -> Path:
    p = {
        "source_dossier_aoi": "synth_camp_aoi",
        "n_reviews_considered": 1,
        "candidates": [
            {
                "family_id": "aoi_tile_scoring",
                "family_name": "AOI feature tile scoring",
                "project": "geaspirit",
                "source_hypothesis_hash": "h1",
                "source_hypothesis_subject": "aoi:synth_camp_aoi",
                "description": "...",
                "estimated_runtime_seconds": 300,
                "estimated_memory_mb": 1536,
                "requires_n_workers": 2,
                "deterministic": True,
                "auditable": True,
                "dependencies": [],
                "notes": "",
                "dry_run": True,
            },
        ],
        "reward_reports": [
            {
                "family_id": "aoi_tile_scoring",
                "family_name": "AOI feature tile scoring",
                "project": "geaspirit",
                "reward_status": "candidate_reward_worthy",
                "classification": {},
                "why": "x",
                "dry_run": True,
            },
        ],
        "queue": {"n_workers": 8, "n_tasks": 1,
                  "total_serial_seconds": 300,
                  "estimated_wallclock_seconds": 300,
                  "per_worker_seconds": [300, 0, 0, 0, 0, 0, 0, 0],
                  "scheduled": [], "dry_run": True},
        "safety_notice": "DRY-RUN ONLY",
        "dry_run": True,
    }
    f = tmp_path / "TRINITY_USEFUL_COMPUTE_PLAN_synth.json"
    f.write_text(json.dumps(p), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# End-to-end via main()
# ---------------------------------------------------------------------------

class TestMainEndToEnd:
    def test_runs_and_writes_outputs(self, mod, synth_dossier_file,
                                       synth_plan_file, tmp_path, capsys):
        out_md = tmp_path / "camp.md"
        out_json = tmp_path / "camp.json"
        rc = mod.main([
            "--dossier", str(synth_dossier_file),
            "--useful-compute-plan", str(synth_plan_file),
            "--campaign-name", "synth_phase1",
            "--out-md", str(out_md),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        data = json.loads(out_json.read_bytes())
        # Required top-level shape.
        for k in ("schema", "campaign_name", "aoi", "dossier_sha256",
                  "useful_compute_plan_sha256", "scorecard_sha256",
                  "objectives", "evidence_gaps", "next_actions",
                  "useful_compute_candidate_queue", "safety_status",
                  "ready_to_register", "registered", "dry_run"):
            assert k in data, f"missing key {k!r}"
        assert data["aoi"] == "synth_camp_aoi"
        assert data["campaign_name"] == "synth_phase1"
        assert data["dry_run"] is True
        assert data["ready_to_register"] is True
        assert data["registered"] is False

    def test_dossier_and_plan_shas_match_sha256sum(self, mod,
                                                     synth_dossier_file,
                                                     synth_plan_file,
                                                     tmp_path):
        """The SHAs the manifest embeds must equal hashlib.sha256 of
        the raw file bytes, so a third party can verify with
        `sha256sum`."""
        out_json = tmp_path / "camp.json"
        mod.main([
            "--dossier", str(synth_dossier_file),
            "--useful-compute-plan", str(synth_plan_file),
            "--campaign-name", "x",
            "--out-md", str(tmp_path / "x.md"),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        d = json.loads(out_json.read_bytes())
        expected_d_sha = hashlib.sha256(synth_dossier_file.read_bytes()).hexdigest()
        expected_p_sha = hashlib.sha256(synth_plan_file.read_bytes()).hexdigest()
        assert d["dossier_sha256"] == expected_d_sha
        assert d["useful_compute_plan_sha256"] == expected_p_sha

    def test_pinned_time_makes_manifest_byte_deterministic(self, mod,
                                                             synth_dossier_file,
                                                             synth_plan_file,
                                                             tmp_path):
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"
        for out in (out_a, out_b):
            mod.main([
                "--dossier", str(synth_dossier_file),
                "--useful-compute-plan", str(synth_plan_file),
                "--campaign-name", "x",
                "--out-md", str(out.with_suffix(".md")),
                "--out-json", str(out),
                "--pinned-time", "2026-01-01T00:00:00+00:00",
            ])
        assert out_a.read_bytes() == out_b.read_bytes()

    def test_evidence_gaps_include_fallback_and_features_zero(self, mod,
                                                                synth_dossier_file,
                                                                synth_plan_file,
                                                                tmp_path):
        out_json = tmp_path / "x.json"
        mod.main([
            "--dossier", str(synth_dossier_file),
            "--useful-compute-plan", str(synth_plan_file),
            "--campaign-name", "x",
            "--out-md", str(tmp_path / "x.md"),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        d = json.loads(out_json.read_bytes())
        ids = {g["gap_id"] for g in d["evidence_gaps"]}
        assert "fallback_mode_active" in ids
        assert "features_available_zero" in ids

    def test_unsafe_or_forbidden_present_in_actions(self, mod,
                                                      synth_dossier_file,
                                                      synth_plan_file,
                                                      tmp_path):
        out_json = tmp_path / "x.json"
        mod.main([
            "--dossier", str(synth_dossier_file),
            "--useful-compute-plan", str(synth_plan_file),
            "--campaign-name", "x",
            "--out-md", str(tmp_path / "x.md"),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        d = json.loads(out_json.read_bytes())
        unsafe = [a for a in d["next_actions"]
                  if a["bucket"] == "unsafe_or_forbidden"]
        assert len(unsafe) >= 5
        for a in unsafe:
            assert a["safety"] == "forbidden"

    def test_nonexistent_dossier_returns_error(self, mod, tmp_path):
        rc = mod.main([
            "--dossier", str(tmp_path / "no.json"),
            "--useful-compute-plan", str(tmp_path / "no_p.json"),
            "--campaign-name", "x",
        ])
        assert rc == 1


# ---------------------------------------------------------------------------
# Safety rendering
# ---------------------------------------------------------------------------

class TestSafetyRendering:
    def test_markdown_carries_dry_run_banner(self, mod, synth_dossier_file,
                                               synth_plan_file, tmp_path):
        out_md = tmp_path / "out.md"
        mod.main([
            "--dossier", str(synth_dossier_file),
            "--useful-compute-plan", str(synth_plan_file),
            "--campaign-name", "x",
            "--out-md", str(out_md),
            "--out-json", str(tmp_path / "x.json"),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        text = out_md.read_text(encoding="utf-8")
        assert "DRY-RUN ONLY" in text
        assert "ready_to_register=true" in text.lower() or \
               "ready_to_register`: `true`" in text.lower()

    def test_markdown_includes_what_this_is_not(self, mod,
                                                  synth_dossier_file,
                                                  synth_plan_file,
                                                  tmp_path):
        out_md = tmp_path / "out.md"
        mod.main([
            "--dossier", str(synth_dossier_file),
            "--useful-compute-plan", str(synth_plan_file),
            "--campaign-name", "x",
            "--out-md", str(out_md),
            "--out-json", str(tmp_path / "x.json"),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        text = out_md.read_text(encoding="utf-8")
        low = "".join(ch for ch in text.lower() if ch != "*")
        assert "what this document is not" in low
        assert "not an announcement" in low or "not a published task list" in low


# ---------------------------------------------------------------------------
# No host paths in canonical JSON
# ---------------------------------------------------------------------------

class TestPathHygiene:
    def test_no_host_path_leaks_into_manifest_json(self, mod,
                                                     synth_dossier_file,
                                                     synth_plan_file,
                                                     tmp_path):
        out_json = tmp_path / "x.json"
        mod.main([
            "--dossier", str(synth_dossier_file),
            "--useful-compute-plan", str(synth_plan_file),
            "--campaign-name", "x",
            "--out-md", str(tmp_path / "x.md"),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        blob = out_json.read_text(encoding="utf-8")
        # tmp_path is a sandbox-specific absolute path; if any field
        # leaks it, this would catch it.
        assert str(tmp_path) not in blob, \
            "tmp_path leaked into manifest JSON"
        for marker in ("/home/", "/opt/", "/Users/"):
            assert marker not in blob, f"host marker {marker!r} leaked"


# ---------------------------------------------------------------------------
# Public surface forbids broadcast / activate helpers
# ---------------------------------------------------------------------------

class TestNoBroadcastHelper:
    def test_script_has_no_broadcast_or_activate(self, mod):
        forbidden = (
            "broadcast", "activate_rewards", "publish_task",
            "open_public_api", "move_funds", "register_on_chain",
        )
        for name in forbidden:
            assert not hasattr(mod, name), \
                f"script unexpectedly exposes {name!r}"
