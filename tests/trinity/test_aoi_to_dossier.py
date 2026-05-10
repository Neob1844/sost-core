"""Tests for `scripts/trinity/aoi_to_dossier.py`.

Pure stdlib + pytest. No network. Synthetic scorecards and pinned
timestamps so the SHA-256 is deterministic.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "trinity" / "aoi_to_dossier.py"


def _load_module():
    """Import the script-as-module without putting scripts/ on sys.path
    permanently."""
    spec = importlib.util.spec_from_file_location(
        "trinity_aoi_to_dossier", _SCRIPT
    )
    assert spec and spec.loader, "could not load aoi_to_dossier.py spec"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


@pytest.fixture
def synth_scorecard(tmp_path: Path):
    sc = {
        "zone": "synth_aoi",
        "features_available": 0,
        "features_total": 5,
        "honesty_matrix": {
            "tier": "Tier 1 — Remote proxy evidence only",
            "environment": "test",
            "adjusted_confidence": 0.0,
            "what_it_doesnt_see": ["Subsurface depth", "Buried ore"],
            "recommendation": "Field validation required.",
        },
    }
    p = tmp_path / "scorecard_synth_aoi.json"
    p.write_text(json.dumps(sc), encoding="utf-8")
    return p


@pytest.fixture
def populated_scorecard(tmp_path: Path):
    sc = {
        "zone": "populated_aoi",
        "features_available": 3,
        "features_total": 5,
        "honesty_matrix": {
            "tier": "Tier 2 — Layered evidence",
            "adjusted_confidence": 0.55,
            "recommendation": "Suitable for follow-up.",
            "what_it_doesnt_see": ["Drill confirmation"],
        },
        "targets": [
            {
                "id": "X-1",
                "name": "alpha",
                "deposit_type": "porphyry copper",
                "lat": 0.0,
                "lon": 0.0,
                "probability": 0.6,
                "rank": 1,
            },
        ],
    }
    p = tmp_path / "scorecard_populated_aoi.json"
    p.write_text(json.dumps(sc), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Canonical serialisation tests
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_sorted_keys(self, mod):
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}
        assert mod._canonical_json(a) == mod._canonical_json(b)

    def test_no_spaces(self, mod):
        out = mod._canonical_json({"k": "v"})
        assert b" " not in out

    def test_ascii_escapes_non_ascii(self, mod):
        out = mod._canonical_json({"k": "ñ"})
        assert b"\\u00f1" in out


class TestSha256:
    def test_known_hash(self, mod):
        # SHA-256 of empty bytes is well-known.
        assert mod._sha256_hex(b"") == \
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_canonical_json_hash_stable(self, mod):
        d = {"hello": "world", "n": 1}
        h1 = mod._sha256_hex(mod._canonical_json(d))
        h2 = mod._sha256_hex(mod._canonical_json(d))
        assert h1 == h2


# ---------------------------------------------------------------------------
# End-to-end via main() with synthetic inputs
# ---------------------------------------------------------------------------

class TestMainEndToEnd:
    def test_runs_on_fallback_scorecard(self, mod, synth_scorecard, tmp_path,
                                          capsys):
        out_md = tmp_path / "out.md"
        out_json = tmp_path / "out.json"
        rc = mod.main([
            "synth_aoi",
            "--scorecard", str(synth_scorecard),
            "--out-md", str(out_md),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        assert out_md.exists()
        assert out_json.exists()
        # Markdown contains the AOI name and the fallback flag.
        text = out_md.read_text(encoding="utf-8")
        assert "synth_aoi" in text
        assert "fallback" in text.lower()
        # JSON parses and has the expected schema.
        data = json.loads(out_json.read_bytes())
        assert data["aoi"] == "synth_aoi"
        assert data["fallback_mode"] is True
        assert data["schema"] == "trinity-dossier/v0"
        # Stdout contains the sha256.
        captured = capsys.readouterr()
        assert "sha256:" in captured.out

    def test_runs_on_populated_scorecard(self, mod, populated_scorecard,
                                          tmp_path):
        out_md = tmp_path / "out.md"
        out_json = tmp_path / "out.json"
        rc = mod.main([
            "populated_aoi",
            "--scorecard", str(populated_scorecard),
            "--out-md", str(out_md),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        data = json.loads(out_json.read_bytes())
        assert data["aoi"] == "populated_aoi"
        assert data["fallback_mode"] is False
        assert data["summary"]["n_reviews"] == 1
        # Decision is one of the canonical values.
        dec = data["reviews"][0]["decision"]["decision"]
        assert dec in {"accept", "reject", "hold", "contradicted"}

    def test_pinned_time_makes_hash_deterministic(self, mod, synth_scorecard,
                                                    tmp_path):
        out_json_a = tmp_path / "a.json"
        out_json_b = tmp_path / "b.json"
        for out in (out_json_a, out_json_b):
            mod.main([
                "synth_aoi",
                "--scorecard", str(synth_scorecard),
                "--out-md", str(out.with_suffix(".md")),
                "--out-json", str(out),
                "--pinned-time", "2026-01-01T00:00:00+00:00",
            ])
        assert out_json_a.read_bytes() == out_json_b.read_bytes()

    def test_missing_aoi_and_scorecard_returns_error(self, mod, capsys):
        rc = mod.main([])
        assert rc == 2

    def test_nonexistent_scorecard_returns_error(self, mod, tmp_path):
        rc = mod.main([
            "ghost",
            "--scorecard", str(tmp_path / "does_not_exist.json"),
        ])
        assert rc == 1


# ---------------------------------------------------------------------------
# Markdown rendering smoke tests
# ---------------------------------------------------------------------------

class TestMarkdownRender:
    def test_includes_honesty_matrix(self, mod, synth_scorecard, tmp_path):
        out_md = tmp_path / "out.md"
        mod.main([
            "synth_aoi",
            "--scorecard", str(synth_scorecard),
            "--out-md", str(out_md),
            "--out-json", str(tmp_path / "out.json"),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        text = out_md.read_text(encoding="utf-8")
        assert "Honesty matrix" in text
        assert "Tier 1" in text
        assert "Buried ore" in text

    def test_capsule_registration_block_present(self, mod, synth_scorecard,
                                                  tmp_path):
        out_md = tmp_path / "out.md"
        mod.main([
            "synth_aoi",
            "--scorecard", str(synth_scorecard),
            "--out-md", str(out_md),
            "--out-json", str(tmp_path / "out.json"),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        text = out_md.read_text(encoding="utf-8")
        assert "Capsule registration" in text
        assert "OPEN_NOTE_INLINE" in text
        assert "DOC_REF_OPEN" in text

    def test_does_not_promise_geological_conclusion(self, mod, synth_scorecard,
                                                     tmp_path):
        out_md = tmp_path / "out.md"
        mod.main([
            "synth_aoi",
            "--scorecard", str(synth_scorecard),
            "--out-md", str(out_md),
            "--out-json", str(tmp_path / "out.json"),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        text = out_md.read_text(encoding="utf-8").lower()
        # The dossier must NEVER claim "guaranteed" mineral presence.
        assert "guaranteed" not in text
        assert "remote-proxy" in text or "remote proxy" in text
