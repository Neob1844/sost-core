"""Tests for the Materials Track v0.2 dossier — real SOST AI council.

These tests assert the v0.2-specific invariants that were not part of
v0.1:

- Default path imports the real ``multi_ai_review.ai_council.AICouncil``
  from ``materials-engine-private`` (or fails loudly).
- Free-tier members only (Validator + LocalKnowledge + MockAI); no
  network member is ever invoked.
- Determinism: two runs from clean dirs with the same seed and pinned
  time produce byte-identical bundle SHAs.
- ``--allow-local-mock`` exists as the explicit escape hatch.
- The dossier source block exposes ``council_implementation`` so
  consumers can tell which path produced the reviews.
- Honesty disclaimers in the rendered markdown are preserved for the
  v0.1 autonomous-source path.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dossier_mod():
    return _load("md_v02_dossier", SCRIPTS_DIR / "materials_dossier.py")


@pytest.fixture(scope="module")
def pipeline_mod():
    return _load(
        "md_v02_pipeline", SCRIPTS_DIR / "materials_discovery_pipeline.py"
    )


@pytest.fixture(scope="module")
def gen_mod():
    return _load(
        "md_v02_gen", SCRIPTS_DIR / "materials_candidate_generator.py"
    )


@pytest.fixture(scope="module")
def filter_mod():
    return _load(
        "md_v02_filter", SCRIPTS_DIR / "materials_chemistry_filter.py"
    )


@pytest.fixture(scope="module")
def scorer_mod():
    return _load(
        "md_v02_scorer", SCRIPTS_DIR / "materials_industrial_scorer.py"
    )


# ---------------------------------------------------------------------------
# Schema bump
# ---------------------------------------------------------------------------


def test_dossier_schema_is_v02(dossier_mod):
    assert dossier_mod._SCHEMA == "trinity-materials-dossier/v0.2"


def test_compute_plan_accepts_v02_dossier_schema():
    plan_mod = _load(
        "md_v02_plan", SCRIPTS_DIR / "materials_compute_plan.py"
    )
    assert "trinity-materials-dossier/v0.2" in plan_mod._DOSSIER_SCHEMAS_ACCEPTED


def test_campaign_accepts_v02_dossier_schema():
    campaign_mod = _load(
        "md_v02_campaign", SCRIPTS_DIR / "materials_campaign.py"
    )
    assert "trinity-materials-dossier/v0.2" in (
        campaign_mod._DOSSIER_SCHEMAS_ACCEPTED
    )


# ---------------------------------------------------------------------------
# Real council import + free-tier members
# ---------------------------------------------------------------------------


def test_real_council_import_succeeds(dossier_mod):
    """The default path must locate materials-engine-private and import
    AICouncil + HypothesisScore + the three free-tier member classes."""
    mod = dossier_mod._import_real_council()
    assert "AICouncil" in mod
    assert "Hypothesis" in mod
    assert "HypothesisScore" in mod
    assert len(mod["members_classes"]) == 3
    # Names: ValidatorMember, LocalKnowledgeMember, MockAIMember
    class_names = sorted(c.__name__ for c in mod["members_classes"])
    assert class_names == ["LocalKnowledgeMember", "MockAIMember", "ValidatorMember"]


def test_real_council_members_are_free_tier_only(dossier_mod):
    """No network member, no paid member."""
    mod = dossier_mod._import_real_council()
    for cls in mod["members_classes"]:
        inst = cls()
        assert getattr(inst, "requires_network", False) is False, (
            f"{cls.__name__} requires network — not free-tier"
        )
        assert getattr(inst, "requires_paid", False) is False, (
            f"{cls.__name__} requires paid — not free-tier"
        )


def test_real_council_import_fails_loudly_without_engine(
    monkeypatch, tmp_path, dossier_mod,
):
    """If TRINITY_MATERIALS_ENGINE_PATH is unset and the default home
    location does not exist, _import_real_council must raise
    ImportError with a clear message."""
    # Point HOME at a tmp dir so the default fallback path also misses.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TRINITY_MATERIALS_ENGINE_PATH", raising=False)
    # Also override the candidate list by setting an explicit bad path.
    monkeypatch.setenv(
        "TRINITY_MATERIALS_ENGINE_PATH",
        str(tmp_path / "nonexistent"),
    )
    with pytest.raises(ImportError, match="materials-engine-private"):
        dossier_mod._import_real_council()


# ---------------------------------------------------------------------------
# Dossier behavior: default real council vs --allow-local-mock fallback
# ---------------------------------------------------------------------------


def _build_pipeline_inputs_through_scorer(tmp_path, gen_mod, filter_mod, scorer_mod):
    """Run generator + filter + scorer and write the three input files
    into tmp_path. Returns the path to the v0.1 scorecard JSON."""
    pool = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=50, seed="trinity-v0.1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    pool_path = tmp_path / "TRINITY_MATERIALS_CANDIDATES_oxide_frontier.json"
    pool_path.write_text(gen_mod.canonical_dumps(pool), encoding="utf-8")
    flt = filter_mod.build_filtered_pool(
        candidate_pool_path=pool_path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    flt_path = tmp_path / "TRINITY_MATERIALS_FILTER_oxide_frontier.json"
    flt_path.write_text(filter_mod.canonical_dumps(flt), encoding="utf-8")
    sc = scorer_mod.build_scorecard(
        candidate_pool_path=pool_path, filter_path=flt_path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    sc_path = tmp_path / "TRINITY_MATERIALS_SCORECARD_oxide_frontier_v02.json"
    sc_path.write_text(scorer_mod.canonical_dumps(sc), encoding="utf-8")
    return sc_path


def test_dossier_default_uses_real_council(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    sc_path = _build_pipeline_inputs_through_scorer(
        tmp_path, gen_mod, filter_mod, scorer_mod
    )
    d = dossier_mod.build_dossier(
        campaign="oxide_frontier_v02",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
        # allow_local_mock NOT set — default real council
    )
    assert d["source"]["council_implementation"] == "real_sost_ai_free_tier"
    assert d["source"]["used_real_council"] is True
    # Council members from multi_ai_review carry names like
    # "validator_member", "local_knowledge_member", "mock_ai_member".
    members = [m.lower() for m in d["council_members"]]
    assert any("validator" in m for m in members)
    assert any("local_knowledge" in m or "localknowledge" in m for m in members)
    assert any("mock" in m for m in members)


def test_dossier_allow_local_mock_uses_inline_mock(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    sc_path = _build_pipeline_inputs_through_scorer(
        tmp_path, gen_mod, filter_mod, scorer_mod
    )
    d = dossier_mod.build_dossier(
        campaign="oxide_frontier_v02",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
        allow_local_mock=True,
    )
    assert d["source"]["council_implementation"] == "inline_mock_v0"
    assert d["source"]["used_real_council"] is False
    members = d["council_members"]
    assert "validator" in members
    assert "materials_expert" in members
    assert "novelty_judge" in members


def test_dossier_real_and_mock_produce_different_summaries(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    """Sanity: the real council and the inline mock are NOT the same
    function, so for the v0.1 oxide_frontier scorecard their decision
    summaries differ. (This anchors the test that the swap is real,
    not cosmetic.)"""
    sc_path = _build_pipeline_inputs_through_scorer(
        tmp_path, gen_mod, filter_mod, scorer_mod
    )
    d_real = dossier_mod.build_dossier(
        campaign="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    d_mock = dossier_mod.build_dossier(
        campaign="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path, allow_local_mock=True,
    )
    real_blob = dossier_mod.canonical_dumps(d_real)
    mock_blob = dossier_mod.canonical_dumps(d_mock)
    assert real_blob != mock_blob


def test_dossier_real_council_byte_identical_cross_call(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    """The real council with free-tier members is deterministic:
    two consecutive calls on the same scorecard produce byte-identical
    canonical JSON."""
    sc_path = _build_pipeline_inputs_through_scorer(
        tmp_path, gen_mod, filter_mod, scorer_mod
    )
    a = dossier_mod.build_dossier(
        campaign="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    b = dossier_mod.build_dossier(
        campaign="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    assert dossier_mod.canonical_dumps(a) == dossier_mod.canonical_dumps(b)


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_exposes_allow_local_mock_flag():
    src = (SCRIPTS_DIR / "materials_dossier.py").read_text(encoding="utf-8")
    assert "--allow-local-mock" in src
    # And the default must remain "off"
    assert 'action="store_true"' in src


def test_cli_does_not_expose_register_send_broadcast_flags():
    src = (SCRIPTS_DIR / "materials_dossier.py").read_text(encoding="utf-8")
    for forbidden in (
        "--register", "--send", "--broadcast", "--activate",
        "--reward", "--sign-tx",
    ):
        assert forbidden not in src


# ---------------------------------------------------------------------------
# Honesty disclaimers preserved on the v0.1 autonomous path
# ---------------------------------------------------------------------------


_REQUIRED_DISCLAIMERS = (
    "autonomous candidate proposal",
    "not experimentally validated",
    "not DFT validated",
    "not a patent claim",
    "not a commercial performance claim",
    "requires Useful Compute / DFT / synthesis review",
)


def test_disclaimers_present_in_v02_markdown(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    sc_path = _build_pipeline_inputs_through_scorer(
        tmp_path, gen_mod, filter_mod, scorer_mod
    )
    d = dossier_mod.build_dossier(
        campaign="oxide_frontier_v02",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    md = dossier_mod.render_markdown(d)
    for phrase in _REQUIRED_DISCLAIMERS:
        assert phrase.lower() in md.lower(), (
            f"disclaimer phrase missing from v0.2 dossier MD: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Pipeline e2e with real council
# ---------------------------------------------------------------------------


def test_pipeline_v02_e2e_byte_identical_cross_run(tmp_path, pipeline_mod):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = pipeline_mod.run_pipeline(
        family="oxide_frontier", count=50, seed="trinity-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=a,
    )
    rb = pipeline_mod.run_pipeline(
        family="oxide_frontier", count=50, seed="trinity-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=b,
    )
    assert ra["shas"]["bundle"] == rb["shas"]["bundle"]
    assert ra["shas"]["dossier"] == rb["shas"]["dossier"]


def test_pipeline_v02_outputs_v02_files(tmp_path, pipeline_mod):
    r = pipeline_mod.run_pipeline(
        family="oxide_frontier", count=50, seed="trinity-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=tmp_path,
    )
    for key, path in r["paths"].items():
        # Bundle / dossier / plan / campaign / scorecard must be v02
        if any(s in key for s in ("dossier", "plan", "campaign", "bundle", "scorecard")):
            assert "_v02" in path, f"path for {key} is not v02: {path}"
            assert "_v01" not in path, f"path for {key} still has v01: {path}"


def test_pipeline_v02_offline_verify_passes(tmp_path, pipeline_mod):
    r = pipeline_mod.run_pipeline(
        family="oxide_frontier", count=50, seed="trinity-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=tmp_path,
    )
    bundle_path = Path(r["paths"]["bundle_json"])
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "verify_trinity_bundle.py"),
            str(bundle_path),
        ],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[verify] OK" in proc.stdout


# ---------------------------------------------------------------------------
# Static safety surface — refactored file still has no forbidden surfaces
# ---------------------------------------------------------------------------


def test_dossier_v02_safe_static_surface():
    src = (SCRIPTS_DIR / "materials_dossier.py").read_text(encoding="utf-8")
    # Strip strings + comments for the check.
    import re
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    code = re.sub(r'"(?:\\.|[^"\\\n])*"', "", code)
    code = re.sub(r"'(?:\\.|[^'\\\n])*'", "", code)
    code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
    code_lower = code.lower()
    for needle in (
        "subprocess.run", "subprocess.Popen", "os.system",
        "requests.post", "requests.get",
        "urllib.request", "http.client", "socket.socket",
    ):
        assert needle.lower() not in code_lower, (
            f"forbidden call pattern {needle!r} appears in dossier code"
        )
    for token in ("sost-cli", "sostcli", "send_capsule",
                  "send_transaction", "activate_rewards"):
        assert token.lower() not in code_lower, (
            f"forbidden token {token!r} appears in dossier code"
        )
