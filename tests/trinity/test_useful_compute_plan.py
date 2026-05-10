"""Tests for `scripts/trinity/useful_compute_plan.py`.

Pure stdlib + pytest. No network. Synthetic dossiers, pinned
timestamps. Asserts that nothing the script can produce activates
Useful Compute rewards or publishes tasks.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "trinity" / "useful_compute_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "trinity_useful_compute_plan", _SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


@pytest.fixture
def synth_dossier(tmp_path: Path):
    """Synthetic dossier with two reviews so the planner emits more
    than one candidate family."""
    d = {
        "schema": "trinity-dossier/v0",
        "aoi": "synth_uc_aoi",
        "source": {"scorecard_zone": "synth_uc_aoi"},
        "fallback_mode": False,
        "reviews": [
            {
                "hypothesis": {
                    "project": "geaspirit",
                    "type": "mineral_target",
                    "title": "synth: t1 — cu candidate",
                    "subject": "aoi:synth|target:t1",
                    "claim": ".",
                    "hypothesis_hash": "aaaa1111",
                },
                "decision": {"decision": "hold", "confidence": 0.5},
                "deposit_type_context": None,
                "fallback_mode": False,
            },
            {
                "hypothesis": {
                    "project": "geaspirit",
                    "type": "aoi_priority",
                    "title": "synth: aoi-level",
                    "subject": "aoi:synth",
                    "claim": ".",
                    "hypothesis_hash": "bbbb2222",
                },
                "decision": {"decision": "hold", "confidence": 0.4},
                "deposit_type_context": None,
                "fallback_mode": True,
            },
        ],
    }
    p = tmp_path / "synth_dossier.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_sorted_keys(self, mod):
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}
        assert mod._canonical_json(a) == mod._canonical_json(b)

    def test_no_spaces(self, mod):
        out = mod._canonical_json({"k": "v"})
        assert b" " not in out

    def test_sha256_known(self, mod):
        assert mod._sha256_hex(b"") == \
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ---------------------------------------------------------------------------
# End-to-end via main()
# ---------------------------------------------------------------------------

class TestMainEndToEnd:
    def test_runs_on_synth_dossier(self, mod, synth_dossier, tmp_path,
                                    capsys):
        out_md = tmp_path / "plan.md"
        out_json = tmp_path / "plan.json"
        rc = mod.main([
            str(synth_dossier),
            "--workers", "4",
            "--out-md", str(out_md),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        assert out_md.exists()
        assert out_json.exists()
        data = json.loads(out_json.read_bytes())
        # Shape contract.
        for k in ("source_dossier_aoi", "candidates", "reward_reports",
                  "queue", "safety_notice", "dry_run"):
            assert k in data, f"missing key {k!r}"
        # Dry-run must be true everywhere.
        assert data["dry_run"] is True
        assert data["queue"]["dry_run"] is True
        for c in data["candidates"]:
            assert c["dry_run"] is True
        for r in data["reward_reports"]:
            assert r["dry_run"] is True
        # Stdout has the sha256.
        captured = capsys.readouterr()
        assert "sha256:" in captured.out

    def test_pinned_time_makes_hash_deterministic(self, mod, synth_dossier,
                                                    tmp_path):
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"
        for out in (out_a, out_b):
            mod.main([
                str(synth_dossier),
                "--workers", "4",
                "--out-md", str(out.with_suffix(".md")),
                "--out-json", str(out),
                "--pinned-time", "2026-01-01T00:00:00+00:00",
            ])
        assert out_a.read_bytes() == out_b.read_bytes()

    def test_nonexistent_dossier_returns_error(self, mod, tmp_path):
        rc = mod.main([str(tmp_path / "does_not_exist.json")])
        assert rc == 1

    def test_invalid_json_dossier_returns_error(self, mod, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json", encoding="utf-8")
        rc = mod.main([str(bad)])
        assert rc == 1


# ---------------------------------------------------------------------------
# Safety: rendered output cannot claim rewards are active
# ---------------------------------------------------------------------------

class TestSafetyRendering:
    def test_markdown_contains_dry_run_warning(self, mod, synth_dossier,
                                                 tmp_path):
        out_md = tmp_path / "plan.md"
        mod.main([
            str(synth_dossier),
            "--out-md", str(out_md),
            "--out-json", str(tmp_path / "plan.json"),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        text = out_md.read_text(encoding="utf-8")
        assert "DRY-RUN ONLY" in text
        assert "No rewards are active" in text

    def test_markdown_explicitly_disclaims_publication(self, mod,
                                                         synth_dossier,
                                                         tmp_path):
        out_md = tmp_path / "plan.md"
        mod.main([
            str(synth_dossier),
            "--out-md", str(out_md),
            "--out-json", str(tmp_path / "plan.json"),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        text = out_md.read_text(encoding="utf-8")
        # The "What this document is NOT" section must be present.
        assert "What this document is NOT" in text
        # And must explicitly disclaim that this is an announcement of
        # active rewards, and that activation requires a separate
        # procedure. The markdown formatting may sprinkle bold
        # asterisks between words, so strip them before matching.
        low = "".join(ch for ch in text.lower() if ch != "*")
        assert "not an announcement" in low
        assert "activation requires" in low

    def test_no_public_helper_named_publish(self, mod):
        # The script must NOT export anything that publishes or
        # activates rewards.
        forbidden = (
            "publish_task", "enqueue_task", "activate_rewards",
            "submit_to_worker", "open_queue",
        )
        for name in forbidden:
            assert not hasattr(mod, name), \
                f"script unexpectedly exposes {name!r}"
