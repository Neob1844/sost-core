"""Tests for `scripts/trinity/aoi_to_dossier.py`.

Pure stdlib + pytest. No network. Synthetic scorecards and pinned
timestamps so the SHA-256 is deterministic.
"""

from __future__ import annotations

import importlib.util
import json
import os
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

class TestReproducibility:
    """The dossier MUST be byte-identical across machines when the
    scorecard content and pinned time are the same. The original v0
    leaked the absolute scorecard path into the canonical JSON, which
    differs between WSL (/home/sost/SOST/...) and the VPS
    (/opt/sost-trinity-option-b-v0/...), and that broke the on-chain
    proof story. The hotfix replaces source.scorecard_path with
    source.scorecard_sha256 + source.scorecard_basename so the
    dossier records the *content* of the scorecard, not where the
    operator happened to store the file. These tests pin the
    invariant in place.
    """

    def test_dossier_sha_independent_of_scorecard_path(self, mod,
                                                         tmp_path: Path):
        """Two scorecards with byte-identical content at different
        absolute paths must produce the same dossier JSON bytes."""
        # Construct one scorecard payload; write it verbatim to two
        # different directories with two different filenames-of-the-
        # parent-directory.
        sc = {
            "zone": "repro_aoi",
            "features_available": 0,
            "features_total": 5,
            "honesty_matrix": {
                "tier": "Tier 1 — Remote proxy evidence only",
                "environment": "test",
                "adjusted_confidence": 0.0,
                "what_it_doesnt_see": ["test blind spot"],
                "recommendation": "Field validation required.",
            },
        }
        sc_bytes = json.dumps(sc).encode("utf-8")

        path_a = tmp_path / "dir_a" / "scorecard_repro_aoi.json"
        path_b = tmp_path / "dir_b" / "deep" / "scorecard_repro_aoi.json"
        path_a.parent.mkdir(parents=True, exist_ok=True)
        path_b.parent.mkdir(parents=True, exist_ok=True)
        path_a.write_bytes(sc_bytes)
        path_b.write_bytes(sc_bytes)

        out_json_a = tmp_path / "out_a.json"
        out_json_b = tmp_path / "out_b.json"

        for sc_path, out in ((path_a, out_json_a), (path_b, out_json_b)):
            rc = mod.main([
                "repro_aoi",
                "--scorecard", str(sc_path),
                "--out-md", str(out.with_suffix(".md")),
                "--out-json", str(out),
                "--pinned-time", "2026-01-01T00:00:00+00:00",
            ])
            assert rc == 0, f"main failed on {sc_path}"

        # The invariant we care about: identical bytes.
        assert out_json_a.read_bytes() == out_json_b.read_bytes(), (
            "Dossier JSON bytes differ across paths for identical content. "
            "The scorecard_path leak is back."
        )

    def test_dossier_records_scorecard_sha256(self, mod, tmp_path: Path):
        """The recorded SHA-256 must match `sha256sum scorecard.json`
        on the original bytes."""
        import hashlib
        sc = {"zone": "hashcheck", "honesty_matrix": {"tier": "T"}}
        sc_bytes = json.dumps(sc).encode("utf-8")
        expected_sha = hashlib.sha256(sc_bytes).hexdigest()

        sc_path = tmp_path / "scorecard_hashcheck.json"
        sc_path.write_bytes(sc_bytes)
        out_json = tmp_path / "out.json"

        rc = mod.main([
            "hashcheck",
            "--scorecard", str(sc_path),
            "--out-md", str(tmp_path / "out.md"),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        data = json.loads(out_json.read_bytes())
        assert data["source"]["scorecard_sha256"] == expected_sha
        assert data["source"]["scorecard_basename"] == "scorecard_hashcheck.json"

    def test_dossier_does_not_leak_absolute_path(self, mod, tmp_path: Path):
        """No source.* field may contain the absolute scorecard path."""
        sc = {"zone": "leakcheck", "honesty_matrix": {"tier": "T"}}
        sc_path = tmp_path / "very_distinctive_directory_name" \
                            / "scorecard_leakcheck.json"
        sc_path.parent.mkdir(parents=True)
        sc_path.write_bytes(json.dumps(sc).encode("utf-8"))
        out_json = tmp_path / "out.json"

        rc = mod.main([
            "leakcheck",
            "--scorecard", str(sc_path),
            "--out-md", str(tmp_path / "out.md"),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        data = json.loads(out_json.read_bytes())
        # No field in source.* may contain the directory name we used.
        canon = json.dumps(data["source"], sort_keys=True)
        assert "very_distinctive_directory_name" not in canon, (
            "Absolute path appears to be leaking into the dossier "
            "source provenance block."
        )
        # Specifically the legacy scorecard_path key must be gone.
        assert "scorecard_path" not in data["source"]


class TestEnvVarOverrides:
    """The two env-var overrides exist so a non-WSL host (e.g. the VPS)
    can point Trinity at custom paths without needing the user to pass
    `--scorecard` on every run.
    """

    def test_geaspirit_outputs_path_finds_scorecard(
        self, mod, tmp_path, monkeypatch, capsys
    ):
        # Layout under the env-var root:
        #   <root>/sub/scorecard_aoi_x.json
        # — the function must rglob, not require it at root level.
        outputs_root = tmp_path / "alt_geaspirit_outputs"
        sub = outputs_root / "phase60"
        sub.mkdir(parents=True)
        sc = {
            "zone": "aoi_x",
            "features_available": 0,
            "features_total": 5,
            "honesty_matrix": {
                "tier": "Tier 1 — Remote proxy evidence only",
                "what_it_doesnt_see": ["test blind spot"],
                "recommendation": "Test recommendation.",
            },
        }
        (sub / "scorecard_aoi_x.json").write_text(
            json.dumps(sc), encoding="utf-8"
        )

        monkeypatch.setenv("TRINITY_GEASPIRIT_OUTPUTS_PATH", str(outputs_root))

        out_md = tmp_path / "out.md"
        out_json = tmp_path / "out.json"
        rc = mod.main([
            "aoi_x",
            "--out-md", str(out_md),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        data = json.loads(out_json.read_bytes())
        assert data["aoi"] == "aoi_x"
        # The dossier records the scorecard by content (sha256) and
        # by filename only — no absolute path. The basename must
        # match the file we wrote under the env-var root.
        assert data["source"]["scorecard_basename"] == "scorecard_aoi_x.json"
        assert len(data["source"]["scorecard_sha256"]) == 64
        assert "scorecard_path" not in data["source"]

    def test_geaspirit_outputs_path_accepts_colon_separated(
        self, mod, tmp_path, monkeypatch
    ):
        # First root is empty; second contains the scorecard.
        empty_root = tmp_path / "empty"
        good_root = tmp_path / "good"
        empty_root.mkdir()
        good_root.mkdir()
        sc = {
            "zone": "aoi_y",
            "honesty_matrix": {"tier": "Tier 1", "what_it_doesnt_see": []},
        }
        (good_root / "scorecard_aoi_y.json").write_text(
            json.dumps(sc), encoding="utf-8"
        )

        joined = os.pathsep.join([str(empty_root), str(good_root)])
        monkeypatch.setenv("TRINITY_GEASPIRIT_OUTPUTS_PATH", joined)

        out_md = tmp_path / "out.md"
        out_json = tmp_path / "out.json"
        rc = mod.main([
            "aoi_y",
            "--out-md", str(out_md),
            "--out-json", str(out_json),
            "--pinned-time", "2026-01-01T00:00:00+00:00",
        ])
        assert rc == 0
        data = json.loads(out_json.read_bytes())
        # Same content-only check: the basename and SHA are present;
        # the absolute path is not leaked.
        assert data["source"]["scorecard_basename"] == "scorecard_aoi_y.json"
        assert len(data["source"]["scorecard_sha256"]) == 64
        assert "scorecard_path" not in data["source"]

    def test_geaspirit_outputs_path_unset_does_not_crash(
        self, mod, monkeypatch
    ):
        # Unset / empty env var must not produce a traceback; the
        # helper just returns no env-derived candidates and we fall
        # through to the default search.
        monkeypatch.delenv("TRINITY_GEASPIRIT_OUTPUTS_PATH", raising=False)
        # Calling the helper directly is enough for this safety check.
        paths = mod._candidate_scorecard_paths("never_exists_aoi_xyz")
        # Either an empty list or a list of real Path objects.
        assert isinstance(paths, list)
        for p in paths:
            assert hasattr(p, "exists")

    def test_geaspirit_outputs_path_nonexistent_is_skipped(
        self, mod, monkeypatch, tmp_path
    ):
        # If the env var points at a nonexistent dir, the helper must
        # not raise; it just skips that entry.
        monkeypatch.setenv(
            "TRINITY_GEASPIRIT_OUTPUTS_PATH",
            str(tmp_path / "does_not_exist"),
        )
        paths = mod._candidate_scorecard_paths("never_exists_aoi_xyz")
        assert isinstance(paths, list)

    def test_materials_engine_path_resolves(
        self, mod, tmp_path, monkeypatch
    ):
        # The function must return the env-var path when it exists,
        # in preference to the WSL/HOME fallbacks.
        custom_root = tmp_path / "alt_materials_engine"
        custom_root.mkdir()
        monkeypatch.setenv("TRINITY_MATERIALS_ENGINE_PATH", str(custom_root))

        resolved = mod._materials_engine_root()
        assert resolved is not None
        assert resolved == custom_root

    def test_materials_engine_path_unset_falls_back(
        self, mod, monkeypatch
    ):
        # Unsetting the env var must not raise; the function returns
        # either a fallback path that exists or None.
        monkeypatch.delenv("TRINITY_MATERIALS_ENGINE_PATH", raising=False)
        resolved = mod._materials_engine_root()
        # Resolved is either None (test host has neither WSL nor HOME
        # candidate) or a real Path. Either way no crash.
        assert resolved is None or resolved.exists()


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
