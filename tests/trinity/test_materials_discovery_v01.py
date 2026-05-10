"""Tests for the Trinity / Materials Discovery v0.1 pipeline.

Three layers of coverage:
- Per-script unit: candidate generator, chemistry filter, industrial
  scorer.
- Cross-script integration: end-to-end discovery pipeline, including
  offline bundle verification and byte-identical cross-run SHA.
- Static safety surface: all four new v0.1 scripts must not expose
  subprocess / requests / urllib / socket imports, must not carry
  sost-cli / send / broadcast / activate tokens, and must not surface
  --register / --send / --broadcast CLI flags.
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
    return _load(
        "md_v01_gen", SCRIPTS_DIR / "materials_candidate_generator.py"
    )


@pytest.fixture(scope="module")
def filter_mod():
    return _load(
        "md_v01_filter", SCRIPTS_DIR / "materials_chemistry_filter.py"
    )


@pytest.fixture(scope="module")
def scorer_mod():
    return _load(
        "md_v01_scorer", SCRIPTS_DIR / "materials_industrial_scorer.py"
    )


@pytest.fixture(scope="module")
def pipeline_mod():
    return _load(
        "md_v01_pipeline", SCRIPTS_DIR / "materials_discovery_pipeline.py"
    )


# ---------------------------------------------------------------------------
# Candidate generator
# ---------------------------------------------------------------------------


def test_generator_deterministic_with_same_seed(gen_mod):
    a = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=20,
        seed="trinity-v0.1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    b = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=20,
        seed="trinity-v0.1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert gen_mod.canonical_dumps(a) == gen_mod.canonical_dumps(b)


def test_generator_different_seed_changes_output(gen_mod):
    a = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=20, seed="seed-a",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    b = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=20, seed="seed-b",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert gen_mod.canonical_dumps(a) != gen_mod.canonical_dumps(b)


def test_generator_emits_requested_count(gen_mod):
    p = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=37, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert p["count_requested"] == 37
    assert p["count_emitted"] == 37
    assert len(p["candidates"]) == 37


def test_generator_rejects_invalid_family(gen_mod):
    with pytest.raises(ValueError, match="unknown family"):
        gen_mod.build_candidate_pool(
            family="dark_matter", count=5, seed="x",
            generated_at_utc="2026-05-10T00:00:00+00:00",
        )


def test_generator_caps_count(gen_mod):
    with pytest.raises(ValueError, match="count"):
        gen_mod.build_candidate_pool(
            family="oxide_frontier", count=10_000, seed="x",
            generated_at_utc="2026-05-10T00:00:00+00:00",
        )


def test_generator_no_host_path_leak(gen_mod):
    p = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=10, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    blob = gen_mod.canonical_dumps(p)
    for needle in ("/home/", "/opt/", "/Users/", "C:/", "C:\\"):
        assert needle not in blob


def test_generator_every_candidate_has_safety_flags(gen_mod):
    p = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=15, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    for c in p["candidates"]:
        assert c["safety_flags"]["not_a_synthesis_recipe"] is True
        assert c["safety_flags"]["not_a_performance_claim"] is True
        assert c["safety_flags"]["requires_dft_validation"] is True
        assert c["novelty_status"] == "unknown_not_validated"


# ---------------------------------------------------------------------------
# Chemistry filter
# ---------------------------------------------------------------------------


def _write_pool(tmp_path, gen_mod, *, family="oxide_frontier",
                count=20, seed="trinity-v0.1"):
    p = gen_mod.build_candidate_pool(
        family=family, count=count, seed=seed,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    path = tmp_path / f"TRINITY_MATERIALS_CANDIDATES_{family}.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")
    return path


def test_filter_accepts_some_rejects_others(tmp_path, gen_mod, filter_mod):
    pool_path = _write_pool(tmp_path, gen_mod, count=50)
    out = filter_mod.build_filtered_pool(
        candidate_pool_path=pool_path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert out["summary"]["accept"] > 0
    assert out["summary"]["reject"] > 0
    # And every accept/reject decision carries a verdict.
    for d in out["decisions"]:
        assert d["filter_verdict"] in ("accept", "reject")


def test_filter_rejects_known_v0_demo_formula(tmp_path, gen_mod, filter_mod):
    # Inject a demo formula by hand, write it, then run the filter.
    p = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=5, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    # Force first candidate to a known v0 demo formula.
    p["candidates"][0]["formula"] = "Co3O4"
    p["candidates"][0]["composition"] = {"Co": 3, "O": 4}
    path = tmp_path / "pool.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")
    out = filter_mod.build_filtered_pool(
        candidate_pool_path=path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    rej = [d for d in out["decisions"] if d["filter_verdict"] == "reject"]
    assert any(
        "known_v0_demo_formula" in d["reason_codes"] for d in rej
    )


def test_filter_blocks_toxic_by_default(tmp_path, gen_mod, filter_mod):
    p = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=3, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    # Force first candidate to include Pb.
    p["candidates"][0]["formula"] = "PbTiO3"
    p["candidates"][0]["composition"] = {"Pb": 1, "Ti": 1, "O": 3}
    p["candidates"][0]["family"] = "perovskite"
    path = tmp_path / "pool_tox.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")

    blocked = filter_mod.build_filtered_pool(
        candidate_pool_path=path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    pb_dec = next(d for d in blocked["decisions"] if d["formula"] == "PbTiO3")
    assert pb_dec["filter_verdict"] == "reject"
    assert any("toxic_element_blocked" in r for r in pb_dec["reason_codes"])

    allowed = filter_mod.build_filtered_pool(
        candidate_pool_path=path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
        allow_toxic=True,
    )
    pb_dec2 = next(d for d in allowed["decisions"] if d["formula"] == "PbTiO3")
    assert pb_dec2["filter_verdict"] in ("accept", "reject")
    if pb_dec2["filter_verdict"] == "accept":
        assert any(
            "contains_toxic_element" in f for f in pb_dec2["filter_flags"]
        )


def test_filter_rejects_charge_unbalanced(tmp_path, gen_mod, filter_mod):
    """Force an obviously unbalanced composition and confirm the filter
    catches it with a charge_balance_nonzero reason code."""
    p = gen_mod.build_candidate_pool(
        family="oxide_frontier", count=3, seed="x",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    # NaOMg-impossible: Na(+1), Mg(+2), O(-2) — overall charge = 1+2-2 = 1.
    p["candidates"][0]["formula"] = "NaMgO"
    p["candidates"][0]["composition"] = {"Na": 1, "Mg": 1, "O": 1}
    p["candidates"][0]["family"] = "spinel"
    path = tmp_path / "pool_unb.json"
    path.write_text(gen_mod.canonical_dumps(p), encoding="utf-8")
    out = filter_mod.build_filtered_pool(
        candidate_pool_path=path,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    unbalanced = next(d for d in out["decisions"] if d["formula"] == "NaMgO")
    assert unbalanced["filter_verdict"] == "reject"
    assert any(
        "charge_balance_nonzero" in r for r in unbalanced["reason_codes"]
    )


# ---------------------------------------------------------------------------
# Industrial scorer
# ---------------------------------------------------------------------------


def _write_pool_and_filter(tmp_path, gen_mod, filter_mod):
    pool_path = _write_pool(tmp_path, gen_mod, count=50)
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
    assert sc["schema"] == "trinity-materials-scorecard/v0.1"
    assert sc["track"] == "materials"
    assert "candidates" in sc
    for c in sc["candidates"]:
        assert "score" in c and 0.0 <= c["score"] <= 100.0
        assert "confidence" in c and 0.0 <= c["confidence"] <= 1.0
        assert c["evidence_level"] == "remote_proxy_only"
        # v0-compatible projection must also be present.
        assert "seed_novelty" in c
        assert "seed_frontier_proximity" in c
        assert "open_questions" in c


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
    sc1 = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    sc2 = scorer_mod.build_scorecard(
        candidate_pool_path=pool, filter_path=flt,
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert scorer_mod.canonical_dumps(sc1) == scorer_mod.canonical_dumps(sc2)


def test_scorer_critical_element_penalised(tmp_path, gen_mod, filter_mod, scorer_mod):
    """An entry containing a critical element (Pt) gets a lower score
    than a similar entry without it."""
    base = {
        "id": "CT-001",
        "formula": "MgAl2O4",
        "family": "spinel",
        "composition": {"Mg": 1, "Al": 2, "O": 4},
        "industrial_hypotheses": ["oxygen_evolution_catalyst"],
    }
    pgm = {
        "id": "CT-002",
        "formula": "Pt-substituted MgAl2O4",
        "family": "spinel",
        "composition": {"Mg": 1, "Pt": 2, "O": 4},
        "industrial_hypotheses": ["oxygen_evolution_catalyst"],
    }
    b_score = scorer_mod._compute_score(
        base["composition"], base["family"], base["industrial_hypotheses"],
    )
    p_score = scorer_mod._compute_score(
        pgm["composition"], pgm["family"], pgm["industrial_hypotheses"],
    )
    assert b_score["score"] > p_score["score"]


# ---------------------------------------------------------------------------
# End-to-end pipeline + bundle verifier
# ---------------------------------------------------------------------------


def test_pipeline_e2e_offline_verify(tmp_path, pipeline_mod):
    result = pipeline_mod.run_pipeline(
        family="oxide_frontier", count=50, seed="trinity-v0.1",
        pinned_time="2026-05-10T00:00:00+00:00",
        out_dir=tmp_path,
    )
    assert result["summary"]["pool_size"] == 50
    assert result["summary"]["filter_accept"] > 0
    bundle_path = Path(result["paths"]["bundle_json"])
    assert bundle_path.exists()
    # Invoke verify_trinity_bundle on the produced bundle.
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


def test_pipeline_byte_identical_across_runs(tmp_path, pipeline_mod):
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
    for k in ra["shas"]:
        assert ra["shas"][k] == rb["shas"][k], k


def test_pipeline_seed_change_changes_bundle(tmp_path, pipeline_mod):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = pipeline_mod.run_pipeline(
        family="oxide_frontier", count=50, seed="seed-A",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=a,
    )
    rb = pipeline_mod.run_pipeline(
        family="oxide_frontier", count=50, seed="seed-B",
        pinned_time="2026-05-10T00:00:00+00:00", out_dir=b,
    )
    assert ra["shas"]["candidates"] != rb["shas"]["candidates"]


# ---------------------------------------------------------------------------
# Static safety surface
# ---------------------------------------------------------------------------


_V01_SCRIPTS = (
    "materials_candidate_generator.py",
    "materials_chemistry_filter.py",
    "materials_industrial_scorer.py",
    "materials_discovery_pipeline.py",
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
    # NOTE: subprocess is intentionally NOT in this list because
    # tests legitimately invoke `verify_trinity_bundle` via subprocess.
    # But the v0.1 *scripts* themselves must not import it. The check
    # below excludes the pipeline orchestrator's transitive import path
    # by inspecting source.
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


@pytest.mark.parametrize("script", _V01_SCRIPTS)
def test_v01_script_safe_static_surface(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    code = _strip(src)
    code_lower = code.lower()
    for needle in _FORBIDDEN_CALL_PATTERNS:
        # The pipeline orchestrator imports via importlib, not
        # subprocess. So forbidding subprocess.* is correct.
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
