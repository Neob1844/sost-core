"""Tests for the Trinity / Materials Track v0 pipeline.

Covers each script standalone + the end-to-end pipeline, plus a static
safety surface check shared across all four Materials Track scripts.
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
def scorecard_mod():
    return _load("mt_scorecard", SCRIPTS_DIR / "materials_scorecard.py")


@pytest.fixture(scope="module")
def dossier_mod():
    return _load("mt_dossier", SCRIPTS_DIR / "materials_dossier.py")


@pytest.fixture(scope="module")
def plan_mod():
    return _load(
        "mt_compute_plan", SCRIPTS_DIR / "materials_compute_plan.py"
    )


@pytest.fixture(scope="module")
def campaign_mod():
    return _load("mt_campaign", SCRIPTS_DIR / "materials_campaign.py")


@pytest.fixture(scope="module")
def registry_mod():
    return _load(
        "mt_registry", SCRIPTS_DIR / "trinity_proof_registry.py"
    )


# ---------------------------------------------------------------------------
# materials_scorecard
# ---------------------------------------------------------------------------


def test_scorecard_canonical_is_deterministic(scorecard_mod):
    a = scorecard_mod.build_scorecard(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    b = scorecard_mod.build_scorecard(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert scorecard_mod.canonical_dumps(a) == scorecard_mod.canonical_dumps(b)


def test_scorecard_track_and_schema(scorecard_mod):
    s = scorecard_mod.build_scorecard(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    assert s["schema"] == "trinity-materials-scorecard/v0"
    assert s["track"] == "materials"
    assert s["features_available"] == 0
    assert s["source"]["mode"] == "mock"
    assert len(s["candidates"]) >= 5
    assert {c["id"] for c in s["candidates"]} >= {
        "C-01", "C-02", "C-03", "C-04", "C-05"
    }


def test_scorecard_rejects_bad_time(scorecard_mod):
    with pytest.raises(ValueError, match="generated_at_utc"):
        scorecard_mod.build_scorecard(
            campaign="x",
            generated_at_utc="2026-05-10T00:00:00",
        )


def test_scorecard_rejects_empty_campaign(scorecard_mod):
    with pytest.raises(ValueError, match="campaign"):
        scorecard_mod.build_scorecard(
            campaign="",
            generated_at_utc="2026-05-10T00:00:00+00:00",
        )


def test_scorecard_host_path_leak_guarded(scorecard_mod):
    # Inject a host path into a candidate's open_questions text and the
    # canonical-dumps host-path guard should reject the result.
    tainted = copy.deepcopy(scorecard_mod.NOVEL_FRONTIER_PHASE1_CANDIDATES)
    tainted[0]["open_questions"].append("see /home/sost/leak.txt")
    with pytest.raises(ValueError, match="host-path"):
        scorecard_mod.build_scorecard(
            campaign="novel_frontier_phase1",
            generated_at_utc="2026-05-10T00:00:00+00:00",
            candidates=tainted,
        )


# ---------------------------------------------------------------------------
# materials_dossier
# ---------------------------------------------------------------------------


def _write_scorecard(tmp_path: Path, scorecard_mod) -> Path:
    s = scorecard_mod.build_scorecard(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
    )
    p = tmp_path / "TRINITY_MATERIALS_SCORECARD_novel_frontier_phase1.json"
    p.write_text(scorecard_mod.canonical_dumps(s), encoding="utf-8")
    return p


@requires_real_council
def test_dossier_v0_demo_produces_no_accepts(
    tmp_path, scorecard_mod, dossier_mod,
):
    """v0 demo data is intentionally thin; council should produce 0
    accepts, 4 holds and 1 reject — same honesty profile as Kalgoorlie
    Phase 1."""
    sp = _write_scorecard(tmp_path, scorecard_mod)
    d = dossier_mod.build_dossier(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sp,
    )
    summary = d["summary"]
    assert summary["decisions_accept"] == 0
    assert summary["decisions_hold"] == 4
    assert summary["decisions_reject"] == 1
    assert summary["candidates_total"] == 5
    # No validator veto fires because no candidate has every non-validator
    # member voting accept — the materials_expert always holds on this
    # honesty profile.
    assert summary["validator_vetoes_applied"] == 0


@requires_real_council
def test_dossier_review_combine_is_strictest_wins(
    tmp_path, scorecard_mod, dossier_mod,
):
    sp = _write_scorecard(tmp_path, scorecard_mod)
    d = dossier_mod.build_dossier(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sp,
    )
    for h in d["hypotheses"]:
        votes = {r["decision"] for r in h["reviews"]}
        if "reject" in votes:
            assert h["decision"] == "reject"
        elif "hold" in votes:
            assert h["decision"] == "hold"
        else:
            assert h["decision"] == "accept"


@requires_real_council
def test_dossier_records_scorecard_sha_not_path(
    tmp_path, scorecard_mod, dossier_mod,
):
    sp = _write_scorecard(tmp_path, scorecard_mod)
    d = dossier_mod.build_dossier(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sp,
    )
    src = d["source"]
    assert re.fullmatch(r"[0-9a-f]{64}", src["scorecard_sha256"])
    assert src["scorecard_basename"] == sp.name
    blob = dossier_mod.canonical_dumps(d)
    for prefix in ("/home/", "/opt/", "/Users/", "C:/"):
        assert prefix not in blob


def test_dossier_rejects_wrong_track(tmp_path, dossier_mod):
    # Hand-write a scorecard with track=earth and feed it to the
    # materials dossier builder. It must refuse.
    bad = {
        "schema": "trinity-materials-scorecard/v0",
        "campaign": "x",
        "track": "earth",
        "generated_at_utc": "2026-05-10T00:00:00+00:00",
        "candidates": [],
    }
    p = tmp_path / "bad_scorecard.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="materials"):
        dossier_mod.build_dossier(
            campaign="x",
            generated_at_utc="2026-05-10T00:00:00+00:00",
            scorecard_path=p,
        )


# ---------------------------------------------------------------------------
# materials_compute_plan
# ---------------------------------------------------------------------------


def _write_dossier(tmp_path, scorecard_mod, dossier_mod) -> Path:
    sp = _write_scorecard(tmp_path, scorecard_mod)
    d = dossier_mod.build_dossier(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        scorecard_path=sp,
    )
    p = tmp_path / "TRINITY_MATERIALS_DOSSIER_novel_frontier_phase1.json"
    p.write_text(dossier_mod.canonical_dumps(d), encoding="utf-8")
    return p


@requires_real_council
def test_plan_classifications_match_dossier(
    tmp_path, scorecard_mod, dossier_mod, plan_mod,
):
    dp = _write_dossier(tmp_path, scorecard_mod, dossier_mod)
    plan = plan_mod.build_plan(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        dossier_path=dp,
    )
    s = plan["summary"]
    # Per the v0 propose_for_hold/_reject/_accept rules:
    #   - 4 holds × 2 families = 8 (mlip_relaxation reward_worthy +
    #     dft_input_preparation deferred-because-not-heavy)
    #   - 1 reject × 1 family = 1 deferred
    # Net: 4 candidate_reward_worthy + 5 deferred + 0 not.
    assert s["tasks_total"] == 9
    assert s["by_classification"]["candidate_reward_worthy"] == 4
    assert s["by_classification"]["deferred"] == 5
    assert s["by_classification"]["not_reward_worthy"] == 0


def test_plan_hard_signal_veto_downgrades(plan_mod):
    """A family whose label contains 'symbolic' (a hard-signal forbidden
    substring) is downgraded to not_reward_worthy even if every hard
    signal is True."""
    rogue_family = {
        "family_id": "rogue_x",
        "human_label": "symbolic shortcut benchmark",
        "purpose": "...",
        "useful": True,
        "deterministic": True,
        "auditable": True,
        "heavy_enough": True,
        "safe_to_verify": True,
        "typical_minutes": 90,
    }
    cls = plan_mod._classify(rogue_family, "shortcut rationale")
    assert cls["classification"] == "not_reward_worthy"


@requires_real_council
def test_plan_safety_status_invariants(
    tmp_path, scorecard_mod, dossier_mod, plan_mod,
):
    dp = _write_dossier(tmp_path, scorecard_mod, dossier_mod)
    plan = plan_mod.build_plan(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        dossier_path=dp,
    )
    ss = plan["safety_status"]
    assert ss["dry_run"] is True
    assert ss["no_rewards_active"] is True
    assert ss["no_chain_broadcast"] is True
    assert ss["no_auto_publish"] is True
    assert ss["no_consensus_modification"] is True


# ---------------------------------------------------------------------------
# materials_campaign
# ---------------------------------------------------------------------------


def _write_plan(tmp_path, scorecard_mod, dossier_mod, plan_mod) -> Path:
    dp = _write_dossier(tmp_path, scorecard_mod, dossier_mod)
    plan = plan_mod.build_plan(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        dossier_path=dp,
    )
    p = tmp_path / (
        "TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_novel_frontier_phase1.json"
    )
    p.write_text(plan_mod.canonical_dumps(plan), encoding="utf-8")
    # Also leave the dossier next to it for the campaign builder.
    return p


@requires_real_council
def test_campaign_unsafe_actions_are_at_the_end(
    tmp_path, scorecard_mod, dossier_mod, plan_mod, campaign_mod,
):
    _write_plan(tmp_path, scorecard_mod, dossier_mod, plan_mod)
    dp = tmp_path / "TRINITY_MATERIALS_DOSSIER_novel_frontier_phase1.json"
    pp = tmp_path / (
        "TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_novel_frontier_phase1.json"
    )
    m = campaign_mod.build_campaign(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        dossier_path=dp,
        plan_path=pp,
    )
    # First action must be safe; last action must be unsafe.
    actions = m["next_actions"]
    assert actions[0]["safety"] == "safe"
    assert actions[-1]["safety"] == "unsafe"
    # All unsafe actions must be in the unsafe_or_forbidden bucket.
    for a in actions:
        if a["safety"] == "unsafe":
            assert a["bucket"] == "unsafe_or_forbidden"


@requires_real_council
def test_campaign_no_safe_action_in_unsafe_bucket(
    tmp_path, scorecard_mod, dossier_mod, plan_mod, campaign_mod,
):
    _write_plan(tmp_path, scorecard_mod, dossier_mod, plan_mod)
    dp = tmp_path / "TRINITY_MATERIALS_DOSSIER_novel_frontier_phase1.json"
    pp = tmp_path / (
        "TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_novel_frontier_phase1.json"
    )
    m = campaign_mod.build_campaign(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        dossier_path=dp,
        plan_path=pp,
    )
    for a in m["next_actions"]:
        if a["bucket"] == "unsafe_or_forbidden":
            assert a["safety"] == "unsafe", a


@requires_real_council
def test_campaign_safety_status_invariants(
    tmp_path, scorecard_mod, dossier_mod, plan_mod, campaign_mod,
):
    _write_plan(tmp_path, scorecard_mod, dossier_mod, plan_mod)
    dp = tmp_path / "TRINITY_MATERIALS_DOSSIER_novel_frontier_phase1.json"
    pp = tmp_path / (
        "TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_novel_frontier_phase1.json"
    )
    m = campaign_mod.build_campaign(
        campaign="novel_frontier_phase1",
        generated_at_utc="2026-05-10T00:00:00+00:00",
        dossier_path=dp,
        plan_path=pp,
    )
    ss = m["safety_status"]
    assert ss["dry_run"] is True
    assert ss["ready_to_register"] is True
    assert ss["registered"] is False
    assert ss["no_rewards_active"] is True
    assert ss["no_chain_broadcast"] is True


def test_campaign_gap_taxonomy_is_closed_and_deterministic(campaign_mod):
    ids = [g["gap_id"] for g in campaign_mod._GAP_TAXONOMY]
    assert ids == sorted(set(ids), key=ids.index), "gap_ids must be unique"
    assert all(gid.startswith("gap_") for gid in ids)


# ---------------------------------------------------------------------------
# Registry track field
# ---------------------------------------------------------------------------


def test_registry_kalgoorlie_entry_now_has_track_earth(registry_mod):
    e = registry_mod.KALGOORLIE_PHASE1_ENTRY
    assert e["track"] == "earth"


def test_registry_accepts_track_materials_entry(registry_mod):
    materials_entry = {
        "id": "novel_frontier_phase1",
        "track": "materials",
        "aoi": "novel_frontier",
        "title": "Novel frontier candidates Phase 1",
        "status": "ready_to_register",
        "registration_method": "not-yet-registered",
        "operator": "NeoB",
        "block_height": 1,
        "txid": "0" * 64,
        "capsule_mode": "open-note",
        "capsule_text": (
            "trinity-proof novel_frontier_phase1 03e04c2a5e638913"
        ),
        "proof_bundle_sha256": (
            "03e04c2a5e6389133ef6cf7e430d110d8bf05dd711a6e68c7c7ed7c2acae4595"
        ),
        "proof_bundle_sha16": "03e04c2a5e638913",
        "merkle_root": (
            "10b84f5b6ef5a76550d688b0abedd9748ed11e572ef09417a05cb472d621a03d"
        ),
        "anchor_files": {
            "proof_bundle": (
                "TRINITY_MATERIALS_PROOF_BUNDLE_novel_frontier_phase1.json"
            ),
        },
        "safety_status": {
            "not_a_mineral_reserve_claim": True,
            "not_a_geological_conclusion": True,
            "no_active_useful_compute_rewards": True,
            "no_auto_broadcast": True,
            "no_consensus_change": True,
        },
    }
    # Validates cleanly even though the bundle file is not on disk
    # (require_bundle_match=False).
    registry_mod.validate_entry(
        materials_entry, require_bundle_match=False,
    )


def test_registry_rejects_invalid_track(registry_mod):
    bad = copy.deepcopy(registry_mod.KALGOORLIE_PHASE1_ENTRY)
    bad["track"] = "ocean"
    with pytest.raises(registry_mod.RegistryError, match="track"):
        registry_mod.validate_entry(bad, require_bundle_match=False)


def test_registry_accepts_legacy_entry_without_track(registry_mod):
    """Legacy entries (no track field) must validate with default
    'earth' to preserve backward compatibility with any pre-Sprint-5.2
    registry copies that someone might still be holding."""
    legacy = copy.deepcopy(registry_mod.KALGOORLIE_PHASE1_ENTRY)
    legacy.pop("track")
    registry_mod.validate_entry(legacy, require_bundle_match=False)


# ---------------------------------------------------------------------------
# Static safety surface across all four Materials Track scripts
# ---------------------------------------------------------------------------


_MATERIALS_SCRIPTS = (
    "materials_scorecard.py",
    "materials_dossier.py",
    "materials_compute_plan.py",
    "materials_campaign.py",
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
    "subprocess",
    "requests",
    "urllib",
    "http",
    "socket",
)
_FORBIDDEN_TOKEN_NAMES = (
    "sost-cli",
    "sostcli",
    "send_capsule",
    "send_transaction",
    "activate_rewards",
)
_FORBIDDEN_CLI_FLAGS = (
    "--register",
    "--send",
    "--broadcast",
    "--activate",
    "--reward",
    "--sign-tx",
)


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', "", src)
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", "", src)
    src = re.sub(r"#.*$", "", src, flags=re.MULTILINE)
    return src


@pytest.mark.parametrize("script", _MATERIALS_SCRIPTS)
def test_materials_script_safe_static_surface(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    code = _strip(src)
    code_lower = code.lower()
    for needle in _FORBIDDEN_CALL_PATTERNS:
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


# ---------------------------------------------------------------------------
# End-to-end pipeline + offline bundle verification
# ---------------------------------------------------------------------------


@requires_real_council
def test_end_to_end_pipeline_via_cli(tmp_path):
    """Run all four scripts back-to-back from the CLI and confirm the
    final proof bundle verifies cleanly with the existing
    verify_trinity_bundle.py."""
    env_args = dict(cwd=tmp_path, capture_output=True, text=True)
    pinned = "2026-05-10T00:00:00+00:00"
    campaign = "novel_frontier_phase1"

    r1 = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "materials_scorecard.py"),
            "--campaign", campaign,
            "--generated-at-utc", pinned,
        ],
        **env_args,
    )
    assert r1.returncode == 0, r1.stderr

    r2 = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "materials_dossier.py"),
            "--campaign", campaign,
            "--generated-at-utc", pinned,
        ],
        **env_args,
    )
    assert r2.returncode == 0, r2.stderr

    r3 = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "materials_compute_plan.py"),
            "--campaign", campaign,
            "--generated-at-utc", pinned,
        ],
        **env_args,
    )
    assert r3.returncode == 0, r3.stderr

    r4 = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "materials_campaign.py"),
            "--campaign", campaign,
            "--generated-at-utc", pinned,
        ],
        **env_args,
    )
    assert r4.returncode == 0, r4.stderr

    r5 = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "trinity_proof_bundle.py"),
            "--dossier",
            f"TRINITY_MATERIALS_DOSSIER_{campaign}.json",
            "--useful-compute-plan",
            f"TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_{campaign}.json",
            "--campaign",
            f"TRINITY_MATERIALS_CAMPAIGN_{campaign}.json",
            "--aoi", "novel_frontier",
            "--bundle-name", campaign,
            "--pinned-time", pinned,
            "--out-json",
            f"TRINITY_MATERIALS_PROOF_BUNDLE_{campaign}.json",
            "--out-md",
            f"TRINITY_MATERIALS_PROOF_BUNDLE_{campaign}.md",
        ],
        **env_args,
    )
    assert r5.returncode == 0, r5.stderr

    r6 = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "verify_trinity_bundle.py"),
            f"TRINITY_MATERIALS_PROOF_BUNDLE_{campaign}.json",
        ],
        **env_args,
    )
    assert r6.returncode == 0, r6.stdout + r6.stderr
    assert "[verify] OK" in r6.stdout


@requires_real_council
def test_pipeline_outputs_byte_identical_cross_run(tmp_path):
    """Same inputs, same pinned time → byte-identical bundle SHA across
    two independent end-to-end runs."""
    pinned = "2026-05-10T00:00:00+00:00"
    campaign = "novel_frontier_phase1"

    def one_run(workdir: Path) -> str:
        scripts = [
            "materials_scorecard.py", "materials_dossier.py",
            "materials_compute_plan.py", "materials_campaign.py",
        ]
        for s in scripts:
            r = subprocess.run(
                [
                    sys.executable, str(SCRIPTS_DIR / s),
                    "--campaign", campaign,
                    "--generated-at-utc", pinned,
                ],
                cwd=workdir, capture_output=True, text=True,
            )
            assert r.returncode == 0, r.stderr
        out_json = workdir / f"TRINITY_MATERIALS_PROOF_BUNDLE_{campaign}.json"
        r = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "trinity_proof_bundle.py"),
                "--dossier",
                f"TRINITY_MATERIALS_DOSSIER_{campaign}.json",
                "--useful-compute-plan",
                f"TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_{campaign}.json",
                "--campaign",
                f"TRINITY_MATERIALS_CAMPAIGN_{campaign}.json",
                "--aoi", "novel_frontier",
                "--bundle-name", campaign,
                "--pinned-time", pinned,
                "--out-json", str(out_json),
                "--out-md", str(out_json.with_suffix(".md")),
            ],
            cwd=workdir, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        import hashlib
        return hashlib.sha256(out_json.read_bytes()).hexdigest()

    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    sha_a = one_run(a_dir)
    sha_b = one_run(b_dir)
    assert sha_a == sha_b, f"non-deterministic bundle: {sha_a} vs {sha_b}"
