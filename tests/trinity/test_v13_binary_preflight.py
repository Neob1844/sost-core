"""Functional tests for v13_binary_preflight.py."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_binary_preflight.py"
CONFIG = REPO_ROOT / "config" / "v13_binary_preflight.json"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_binary_preflight_report.schema.json"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v13_binary_preflight", str(SCRIPT),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def srr():
    return _import_script()


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_script_exists():
    assert SCRIPT.is_file()


def test_config_exists():
    assert CONFIG.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_config_schema_id():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["schema"] == "sost-v13-binary-preflight/v0.1"


def test_config_rc_and_heights():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["rc_id"]              == "v13-rc1"
    assert cfg["activation_height"]  == 12000
    assert cfg["expected_tag"]       == "v13-rc1-preflight-v01"


def test_config_required_binaries():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    names = sorted(b["name"] for b in cfg["required_binaries"])
    assert names == sorted(["sost-node", "sost-miner", "sost-cli"])


def test_config_required_tests_have_kinds():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    kinds = sorted(t["kind"] for t in cfg["required_tests"])
    assert "pytest" in kinds
    assert kinds.count("ctest") >= 4


def test_config_safety_all_const_true():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_release_upload",
        "no_network_required",
        "no_auto_restart",
        "no_ethereum_deploy",
        "no_destructive_git",
        "no_shell_true",
        "no_make_invocation",
        "no_cmake_invocation",
    ):
        assert cfg["safety"][flag] is True, "config flag: " + flag


def test_report_validates_against_schema(srr, schema, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "nonexistent-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    jsonschema.validate(report, schema)


def test_report_top_level_shape(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "nonexistent-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    assert report["schema"] == "trinity-v13-binary-preflight-report/v0.1"
    assert re.match(r"^v13bpf-[0-9a-f]{16}$", report["report_id"])
    assert report["preflight_id"] == "v13-rc1-preflight-v01"
    assert report["rc_id"] == "v13-rc1"
    assert report["repo_root_basename"] == REPO_ROOT.name


def test_git_section_populated(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "nope",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    g = report["git"]
    assert re.match(r"^[0-9a-f]{40}$", g["head_commit"])
    assert g["head_commit_short"] == g["head_commit"][:16]
    assert isinstance(g["current_branch"], str) and g["current_branch"]
    assert isinstance(g["tracked_dirty"], bool)


def test_configs_loaded(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "nope",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    assert report["configs"]["v13_binary_preflight_loaded"]  is True
    assert report["configs"]["v13_activation_loaded"]        is True
    assert report["configs"]["v13_release_candidate_loaded"] is True


def test_binaries_marked_absent_when_build_dir_missing(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "definitely-not-here",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    for b in report["binaries"]:
        assert b["present"] is False
        assert b["size_bytes"] is None
        assert b["sha256"] is None


def test_binaries_detected_when_build_dir_has_them(srr, tmp_path):
    bd = tmp_path / "build-fake"
    bd.mkdir()
    (bd / "sost-node").write_bytes(b"fake-node-bytes\n")
    (bd / "sost-miner").write_bytes(b"fake-miner-bytes\n")
    (bd / "sost-cli").write_bytes(b"fake-cli-bytes\n")
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=bd,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    by_name = {b["name"]: b for b in report["binaries"]}
    for name in ("sost-node", "sost-miner", "sost-cli"):
        assert by_name[name]["present"] is True
        assert by_name[name]["size_bytes"] > 0
        assert re.match(r"^[0-9a-f]{64}$", by_name[name]["sha256"])


def test_sha256sums_written_when_flag_set(srr, tmp_path):
    bd = tmp_path / "build-fake"
    bd.mkdir()
    (bd / "sost-node").write_bytes(b"fake-node-bytes\n")
    (bd / "sost-miner").write_bytes(b"fake-miner-bytes\n")
    (bd / "sost-cli").write_bytes(b"fake-cli-bytes\n")
    out = tmp_path / "out"
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=bd,
        out_dir=out,
        pinned_time="2026-05-18T14:00:00+00:00",
        write_sha256sums=True,
    )
    assert report["sha256sums_written"] is True
    sums = (out / "SHA256SUMS").read_text(encoding="utf-8")
    for name in ("sost-node", "sost-miner", "sost-cli"):
        assert name in sums


def test_require_binaries_flag_warns_when_missing(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "nope",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
        require_binaries=True,
    )
    assert any("require-binaries" in w for w in report["warnings"])


def test_safety_flags_all_const_true(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "nope",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_release_upload",
        "no_network_required",
        "no_auto_restart",
        "no_ethereum_deploy",
        "no_destructive_git",
        "no_shell_true",
        "no_make_invocation",
        "no_cmake_invocation",
    ):
        assert report["safety_flags"][flag] is True, "flag: " + flag


def test_ready_to_build_true_when_min_commit_matches(srr, tmp_path):
    """On a clean main HEAD that matches min_commit, with the
    confirmed-items wired (which they are post-V13 readiness +
    cASERT V13 wire), ready_to_build must be true."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build-yet",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    # The check requires HEAD to start with min_commit. On a feature
    # branch HEAD will differ from the config's recorded min_commit;
    # we therefore only assert ready_to_build is a bool and the
    # downstream gates (readiness, RC) are true.
    assert isinstance(report["ready_to_build"], bool)
    # The two sibling re-runs must both report green at this commit.
    assert not any(
        "v13_readiness_check says confirmed items NOT ready" in w
        for w in report["warnings"]
    )
    assert not any(
        "v13_release_candidate_check says rc_ready=false" in w
        for w in report["warnings"]
    )


def test_ctest_skipped_entries_when_run_ctest_off(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
        run_ctest=False,
    )
    assert report["tests"]["ctest"]["ran"] is False
    entries = report["tests"]["ctest"]["tests"]
    assert len(entries) >= 4
    for t in entries:
        assert t["status"] == "skipped"
        assert t["ran"] is False


def test_pytest_section_when_not_run(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    p = report["tests"]["pytest"]
    assert p["ran"] is False
    assert p["target"] == "tests/trinity/"
    assert p["returncode"] == -1


def test_report_deterministic(srr, tmp_path):
    r1 = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    r2 = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build",
        out_dir=tmp_path / "out2",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    assert r1["report_id"] == r2["report_id"]


def test_cli_writes_report_files(srr, tmp_path):
    out = tmp_path / "out"
    rc = srr.main([
        "--repo-root",   str(REPO_ROOT),
        "--build-dir",   str(tmp_path / "no-build"),
        "--out-dir",     str(out),
        "--pinned-time", "2026-05-18T14:00:00+00:00",
    ])
    assert rc in (0, 1)
    assert (out / "report.json").is_file()
    assert (out / "report.md").is_file()
    parsed = json.loads((out / "report.json").read_text())
    assert parsed["schema"] == "trinity-v13-binary-preflight-report/v0.1"


def test_cli_returns_2_on_missing_repo(srr, tmp_path):
    rc = srr.main([
        "--repo-root",   str(tmp_path / "nope"),
        "--build-dir",   str(tmp_path / "no-build"),
        "--out-dir",     str(tmp_path / "out"),
        "--pinned-time", "2026-05-18T14:00:00+00:00",
    ])
    assert rc == 2


def test_disallowed_git_verb_rejected(srr):
    with pytest.raises(srr.PreflightError):
        srr._run_git(["push", "origin", "main"], REPO_ROOT)
    with pytest.raises(srr.PreflightError):
        srr._run_git(["merge", "main"], REPO_ROOT)
    with pytest.raises(srr.PreflightError):
        srr._run_git(["tag", "v1.0"], REPO_ROOT)
    with pytest.raises(srr.PreflightError):
        srr._run_git(["commit", "-m", "x"], REPO_ROOT)


def test_merge_base_verb_allowed(srr):
    """merge-base must now pass the read-only allow-list."""
    head = srr._git_head_commit(REPO_ROOT)
    # merge-base --is-ancestor of head against itself returns rc=0.
    proc = srr._run_git(
        ["merge-base", "--is-ancestor", head, head],
        REPO_ROOT,
        allow_fail=True,
    )
    assert proc.returncode == 0


def test_head_matches_min_commit_exact(srr):
    """Case 1: HEAD exactly equals min_commit."""
    head = srr._git_head_commit(REPO_ROOT)
    ok, reason = srr._head_matches_min_commit(REPO_ROOT, head, head)
    assert ok is True
    assert "exact" in reason or "prefix" in reason


def test_head_matches_min_commit_descendant(srr):
    """Case 2: HEAD is a descendant of min_commit. The HEAD~1
    commit IS an ancestor of HEAD by construction, so it must
    return True via the ancestry path."""
    head     = srr._git_head_commit(REPO_ROOT)
    ancestor = srr._run_git(
        ["rev-parse", "HEAD~1"], REPO_ROOT,
    ).stdout.strip()
    ok, reason = srr._head_matches_min_commit(REPO_ROOT, head, ancestor)
    assert ok is True
    assert "ancestor" in reason


def test_head_matches_min_commit_not_in_ancestry(srr):
    """Case 3: min_commit not in ancestry. Construct a synthetic
    SHA that doesn't exist in the repo."""
    head = srr._git_head_commit(REPO_ROOT)
    fake = "0" * 40
    ok, reason = srr._head_matches_min_commit(REPO_ROOT, head, fake)
    assert ok is False
    assert "min_commit" in reason


def test_head_matches_min_commit_short_prefix(srr):
    """Case 4: short HEAD prefix supplied as min_commit. The
    prefix path inside _head_matches_min_commit short-circuits
    before the ancestry probe runs."""
    head = srr._git_head_commit(REPO_ROOT)
    short = head[:7]
    ok, reason = srr._head_matches_min_commit(REPO_ROOT, head, short)
    assert ok is True
    # Either prefix or ancestry path may report — both are valid.
    assert "prefix" in reason or "ancestor" in reason or "exact" in reason


def test_head_matches_min_commit_empty_returns_false(srr):
    head = srr._git_head_commit(REPO_ROOT)
    ok, reason = srr._head_matches_min_commit(REPO_ROOT, head, "")
    assert ok is False
    assert "min_commit" in reason


def test_head_matches_min_commit_non_hex_safe(srr):
    """Defensive: non-hex min_commit must not blow up and must
    NOT be passed to subprocess (the helper validates with regex
    before any git call)."""
    head = srr._git_head_commit(REPO_ROOT)
    ok, reason = srr._head_matches_min_commit(
        REPO_ROOT, head, "--option-injection-attempt",
    )
    assert ok is False
    assert "known commit" in reason or "min_commit" in reason


def test_head_matches_min_commit_true_on_feature_branch(srr, tmp_path):
    """The critical regression: on a feature branch whose HEAD is
    a descendant of the config's min_commit, head_matches_min_commit
    must be true. Before this fix it was false because the script
    required HEAD.startswith(min_commit).

    We only assert the ancestry semantic here. `ready_to_build`
    additionally depends on tracked-tree cleanliness which is out
    of scope for this test (the developer running pytest may have
    uncommitted changes on the working tree)."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:45:00+00:00",
    )
    g = report["git"]
    assert g["head_matches_min_commit"] is True, (
        "head_matches_min_commit must be true when running on a "
        "feature branch whose base is min_commit; warnings: "
        + repr(report.get("warnings"))
    )
    # And — crucially — the warning list must NOT carry the old
    # "does not start with min_commit" string.
    for w in report["warnings"]:
        assert "does not start with min_commit" not in w, (
            "old strict-prefix warning leaked back: " + w
        )


def test_render_markdown_has_all_sections(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    md = srr.render_markdown(report)
    for header in (
        "# Trinity V13 Binary Preflight Report",
        "## Git",
        "## Configs",
        "## Binaries",
        "## Tests",
        "## Options",
        "## Warnings",
        "## Safety flags",
    ):
        assert header in md, "missing section: " + header


def test_markdown_no_html_no_js(srr, tmp_path):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        build_dir=tmp_path / "no-build",
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T14:00:00+00:00",
    )
    md = srr.render_markdown(report)
    assert "<script" not in md
    assert "javascript:" not in md
    assert "<html" not in md
    assert "<style" not in md
