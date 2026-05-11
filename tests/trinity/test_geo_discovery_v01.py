"""Tests for the Trinity / Geo Discovery v0.1 pipeline.

Mirrors the structure of test_materials_discovery_v01.py for geo:
deterministic generator, transparent filter, weighted scorer, real
SOST AI council dossier, compute plan, campaign, proof bundle, plus a
static safety-surface check across every geo script.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import requires_real_council


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
def gen_mod():
    return _load("geo_gen", SCRIPTS_DIR / "geo_candidate_generator.py")


@pytest.fixture(scope="module")
def filter_mod():
    return _load("geo_filter", SCRIPTS_DIR / "geo_candidate_filter.py")


@pytest.fixture(scope="module")
def scorer_mod():
    return _load("geo_scorer", SCRIPTS_DIR / "geo_anomaly_scorer.py")


@pytest.fixture(scope="module")
def dossier_mod():
    return _load("geo_dossier_test", SCRIPTS_DIR / "geo_dossier.py")


@pytest.fixture(scope="module")
def plan_mod():
    return _load("geo_plan", SCRIPTS_DIR / "geo_compute_plan.py")


@pytest.fixture(scope="module")
def campaign_mod():
    return _load("geo_campaign_mod", SCRIPTS_DIR / "geo_campaign.py")


@pytest.fixture(scope="module")
def pipeline_mod():
    return _load("geo_pipeline", SCRIPTS_DIR / "geo_discovery_pipeline.py")


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def test_generator_deterministic_with_same_seed(gen_mod):
    a = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="copper_gold_critical_minerals",
        count=30, seed="trinity-geo-v0.1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    b = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="copper_gold_critical_minerals",
        count=30, seed="trinity-geo-v0.1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert gen_mod.canonical_dumps(a) == gen_mod.canonical_dumps(b)


def test_generator_different_seed_changes_ordering(gen_mod):
    a = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="copper_gold_critical_minerals",
        count=30, seed="seed-A",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    b = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="copper_gold_critical_minerals",
        count=30, seed="seed-B",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert gen_mod.canonical_dumps(a) != gen_mod.canonical_dumps(b)


def test_generator_emits_requested_count(gen_mod):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="copper_gold_critical_minerals",
        count=47, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert p["count_requested"] == 47
    assert p["count_emitted"] == 47
    assert len(p["candidates"]) == 47


def test_generator_rejects_invalid_mode(gen_mod):
    with pytest.raises(ValueError, match="unknown mode"):
        gen_mod.build_candidate_pool(
            mode="from-satellite", commodity="all", count=5,
            seed="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        )


def test_generator_no_host_path_leak(gen_mod):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="all", count=10, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    blob = gen_mod.canonical_dumps(p)
    for needle in ("/home/", "/opt/", "/Users/", "C:/", "C:\\"):
        assert needle not in blob


def test_generator_every_candidate_has_safety_flags(gen_mod):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="all", count=15, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    for c in p["candidates"]:
        sf = c["safety_flags"]
        assert sf["not_a_reserve_claim"] is True
        assert sf["requires_field_validation"] is True
        assert sf["remote_proxy_only"] is True
        assert sf["no_drilling_evidence"] is True
        assert c["novelty_status"] == "not_known_deposit_claim"


def test_generator_coordinates_are_valid(gen_mod):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="all", count=100, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    for c in p["candidates"]:
        assert -90 <= c["center_lat"] <= 90, c
        assert -180 <= c["center_lon"] <= 180, c
        assert c["bbox"][0] < c["bbox"][2]
        assert c["bbox"][1] < c["bbox"][3]


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


def _write_pool(tmp_path, gen_mod, *, count=100, seed="trinity-geo-v0.1"):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="copper_gold_critical_minerals",
        count=count, seed=seed,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    path = tmp_path / "TRINITY_GEO_CANDIDATE_AOIS_global_phase1.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")
    return path


def test_filter_accepts_some_rejects_others(tmp_path, gen_mod, filter_mod):
    pool_path = _write_pool(tmp_path, gen_mod)
    out = filter_mod.build_filtered_pool(
        candidate_pool_path=pool_path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert out["summary"]["accept"] > 0
    assert out["summary"]["reject"] > 0


def test_filter_rejects_invalid_coordinates(tmp_path, gen_mod, filter_mod):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="all", count=3, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    p["candidates"][0]["center_lat"] = 200.0  # off-globe
    p["candidates"][0]["center_lon"] = 500.0
    path = tmp_path / "pool_invalid.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")
    out = filter_mod.build_filtered_pool(
        candidate_pool_path=path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    inv = next(d for d in out["decisions"] if d["id"] == p["candidates"][0]["id"])
    assert inv["filter_verdict"] == "reject"
    assert any("invalid_coordinates" in r for r in inv["reason_codes"])


def test_filter_rejects_near_known_demo_aoi(tmp_path, gen_mod, filter_mod):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="all", count=3, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    # Force candidate 0 to be near Kalgoorlie demo
    p["candidates"][0]["center_lat"] = -30.5
    p["candidates"][0]["center_lon"] = 121.4
    p["candidates"][0]["bbox"] = [120.9, -31.0, 121.9, -30.0]
    path = tmp_path / "pool_near_demo.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")
    out = filter_mod.build_filtered_pool(
        candidate_pool_path=path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    near = next(d for d in out["decisions"] if d["id"] == p["candidates"][0]["id"])
    assert near["filter_verdict"] == "reject"
    assert any("near_known_demo_aoi" in r for r in near["reason_codes"])


def test_filter_rejects_duplicate_bboxes(tmp_path, gen_mod, filter_mod):
    p = gen_mod.build_candidate_pool(
        mode="offline-belts", commodity="all", count=5, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    # Force candidates 0 and 1 to have identical bboxes (overlap = 1.0)
    p["candidates"][1]["center_lat"] = p["candidates"][0]["center_lat"]
    p["candidates"][1]["center_lon"] = p["candidates"][0]["center_lon"]
    p["candidates"][1]["bbox"] = list(p["candidates"][0]["bbox"])
    path = tmp_path / "pool_dupe.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")
    out = filter_mod.build_filtered_pool(
        candidate_pool_path=path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    second = next(d for d in out["decisions"] if d["id"] == p["candidates"][1]["id"])
    assert second["filter_verdict"] == "reject"
    assert any(
        "overlap_with_previously_accepted" in r for r in second["reason_codes"]
    )


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def _write_pool_and_filter(tmp_path, gen_mod, filter_mod):
    pool_path = _write_pool(tmp_path, gen_mod, count=80)
    flt = filter_mod.build_filtered_pool(
        candidate_pool_path=pool_path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    filter_path = tmp_path / "filter.json"
    filter_path.write_text(
        filter_mod.canonical_dumps(flt), encoding="utf-8"
    )
    return pool_path, filter_path


def test_scorer_emits_v01_schema(tmp_path, gen_mod, filter_mod, scorer_mod):
    pool, flt = _write_pool_and_filter(tmp_path, gen_mod, filter_mod)
    sc = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert sc["schema"] == "trinity-geo-scorecard/v0.1"
    assert sc["track"] == "geaspirit"
    for c in sc["candidates"]:
        assert 0.0 <= c["score"] <= 100.0
        assert c["evidence_level"] == "remote_proxy_only"
        # v0-compatible projection so dossier can read it
        assert "seed_novelty" in c
        assert "seed_frontier_proximity" in c
        assert "open_questions" in c
        assert "recommended_next_data_layers" in c


def test_scorer_sorts_descending_by_score(tmp_path, gen_mod, filter_mod, scorer_mod):
    pool, flt = _write_pool_and_filter(tmp_path, gen_mod, filter_mod)
    sc = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    scores = [c["score"] for c in sc["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_scorer_pinned_time_byte_identical(tmp_path, gen_mod, filter_mod, scorer_mod):
    pool, flt = _write_pool_and_filter(tmp_path, gen_mod, filter_mod)
    a = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    b = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert scorer_mod.canonical_dumps(a) == scorer_mod.canonical_dumps(b)


def test_scorer_top_candidates_have_reason_codes_and_missing_evidence(
    tmp_path, gen_mod, filter_mod, scorer_mod,
):
    pool, flt = _write_pool_and_filter(tmp_path, gen_mod, filter_mod)
    sc = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    for c in sc["candidates"][:10]:
        assert c["reason_codes"], c["id"]
        assert c["missing_evidence"], c["id"]


# ---------------------------------------------------------------------------
# Dossier — disclaimers + real council
# ---------------------------------------------------------------------------


_REQUIRED_DISCLAIMERS = (
    "autonomous AOI proposal",
    "remote proxy evidence only",
    "no field validation",
    "no drilling evidence",
    "no confirmed mineralization",
    "not a mineral reserve claim",
    "requires geological review before any public claim",
)


def _write_scorecard(tmp_path, gen_mod, filter_mod, scorer_mod):
    pool, flt = _write_pool_and_filter(tmp_path, gen_mod, filter_mod)
    sc = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    sc_path = tmp_path / "TRINITY_GEO_SCORECARD_global_phase1.json"
    sc_path.write_text(scorer_mod.canonical_dumps(sc), encoding="utf-8")
    return sc_path


@requires_real_council
def test_dossier_disclaimers_present_in_markdown(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    sc_path = _write_scorecard(tmp_path, gen_mod, filter_mod, scorer_mod)
    d = dossier_mod.build_dossier(
        campaign="global_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    md = dossier_mod.render_markdown(d)
    for phrase in _REQUIRED_DISCLAIMERS:
        assert phrase.lower() in md.lower(), (
            f"missing disclaimer in v0.1 geo dossier MD: {phrase!r}"
        )


@requires_real_council
def test_dossier_default_uses_real_council(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    sc_path = _write_scorecard(tmp_path, gen_mod, filter_mod, scorer_mod)
    d = dossier_mod.build_dossier(
        campaign="global_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    assert d["source"]["council_implementation"] == "real_sost_ai_free_tier"
    assert d["source"]["used_real_council"] is True


@requires_real_council
def test_dossier_real_council_byte_identical_cross_call(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    sc_path = _write_scorecard(tmp_path, gen_mod, filter_mod, scorer_mod)
    a = dossier_mod.build_dossier(
        campaign="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    b = dossier_mod.build_dossier(
        campaign="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path,
    )
    assert dossier_mod.canonical_dumps(a) == dossier_mod.canonical_dumps(b)


def test_dossier_allow_local_mock_uses_inline_mock(
    tmp_path, gen_mod, filter_mod, scorer_mod, dossier_mod,
):
    sc_path = _write_scorecard(tmp_path, gen_mod, filter_mod, scorer_mod)
    d = dossier_mod.build_dossier(
        campaign="x", generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sc_path, allow_local_mock=True,
    )
    assert d["source"]["council_implementation"] == "inline_mock_v0"


# ---------------------------------------------------------------------------
# End-to-end pipeline + offline verify + byte-identical cross-run
# ---------------------------------------------------------------------------


@requires_real_council
def test_pipeline_e2e_offline_verify(tmp_path, pipeline_mod):
    r = pipeline_mod.run_pipeline(
        mode="offline-belts",
        commodity="copper_gold_critical_minerals",
        count=80, seed="trinity-geo-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00",
        out_dir=tmp_path,
    )
    assert r["summary"]["pool_size"] == 80
    bundle_path = Path(r["paths"]["bundle_json"])
    assert bundle_path.exists()
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


@requires_real_council
def test_pipeline_byte_identical_across_runs(tmp_path, pipeline_mod):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = pipeline_mod.run_pipeline(
        mode="offline-belts",
        commodity="copper_gold_critical_minerals",
        count=80, seed="trinity-geo-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=a,
    )
    rb = pipeline_mod.run_pipeline(
        mode="offline-belts",
        commodity="copper_gold_critical_minerals",
        count=80, seed="trinity-geo-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=b,
    )
    assert ra["shas"]["bundle"] == rb["shas"]["bundle"]
    for k in ra["shas"]:
        assert ra["shas"][k] == rb["shas"][k], k


@requires_real_council
def test_pipeline_seed_change_changes_bundle(tmp_path, pipeline_mod):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = pipeline_mod.run_pipeline(
        mode="offline-belts",
        commodity="copper_gold_critical_minerals",
        count=50, seed="seed-A",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=a,
    )
    rb = pipeline_mod.run_pipeline(
        mode="offline-belts",
        commodity="copper_gold_critical_minerals",
        count=50, seed="seed-B",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=b,
    )
    assert ra["shas"]["candidates"] != rb["shas"]["candidates"]


# ---------------------------------------------------------------------------
# Static safety surface across every geo script
# ---------------------------------------------------------------------------


_GEO_SCRIPTS = (
    "geo_candidate_generator.py",
    "geo_candidate_filter.py",
    "geo_anomaly_scorer.py",
    "geo_dossier.py",
    "geo_compute_plan.py",
    "geo_campaign.py",
    "geo_discovery_pipeline.py",
)

_FORBIDDEN_CALL_PATTERNS = (
    "subprocess.run",
    "subprocess.Popen",
    "os.system",
    "requests.post",
    "requests.get",
    "urllib.request",
    "http.client",
    "socket.socket",
)
_FORBIDDEN_IMPORT_NAMES = (
    "requests", "urllib", "http", "socket",
)
_FORBIDDEN_TOKEN_NAMES = (
    "sost-cli", "sostcli", "send_capsule",
    "send_transaction", "activate_rewards",
)
_FORBIDDEN_CLI_FLAGS = (
    "--register", "--send", "--broadcast", "--activate",
    "--reward", "--sign-tx",
)


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', "", src)
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", "", src)
    src = re.sub(r"#.*$", "", src, flags=re.MULTILINE)
    return src


@pytest.mark.parametrize("script", _GEO_SCRIPTS)
def test_geo_script_safe_static_surface(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    code = _strip(src)
    code_lower = code.lower()
    for needle in _FORBIDDEN_CALL_PATTERNS:
        # Pipeline orchestrator imports via importlib, not subprocess.
        assert needle.lower() not in code_lower, (
            f"forbidden call pattern {needle!r} appears in {script}"
        )
    for needle in _FORBIDDEN_TOKEN_NAMES:
        assert needle.lower() not in code_lower, (
            f"forbidden token {needle!r} appears in {script}"
        )
    for name in _FORBIDDEN_IMPORT_NAMES:
        bad_import = re.search(
            rf"^\s*(?:import\s+{re.escape(name)}\b|from\s+{re.escape(name)}\b)",
            code,
            flags=re.MULTILINE,
        )
        assert bad_import is None, (
            f"forbidden import of {name!r} appears in {script}"
        )
    for forbidden_flag in _FORBIDDEN_CLI_FLAGS:
        assert forbidden_flag not in src, (
            f"{script} argparse must not expose {forbidden_flag!r}"
        )
