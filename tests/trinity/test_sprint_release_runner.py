"""Functional tests for Sprint 5.40 sprint_release_runner.py."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCRIPT = SCRIPTS_DIR / "sprint_release_runner.py"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "sprint_release_report.schema.json"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sprint_release_runner", str(SCRIPT),
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


def _git(args, cwd, env_extra=None):
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "NeoB"
    env["GIT_AUTHOR_EMAIL"] = "neob@sostprotocol.com"
    env["GIT_COMMITTER_NAME"] = "NeoB"
    env["GIT_COMMITTER_EMAIL"] = "neob@sostprotocol.com"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
        check=True,
        env=env,
    )


def _make_repo(tmp_path: Path) -> Path:
    """Initialise a small git repo with main + a feature branch
    one commit ahead. Returns the repo root."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(["add", "README.md"], repo)
    _git(["commit", "-m", "first"], repo)
    _git(["checkout", "-b", "feature/x"], repo)
    (repo / "FEATURE.md").write_text("feature\n", encoding="utf-8")
    _git(["add", "FEATURE.md"], repo)
    _git(["commit", "-m", "feature commit"], repo)
    return repo


def test_script_exists():
    assert SCRIPT.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_clean_report_validates(srr, tmp_path, schema):
    repo = _make_repo(tmp_path)
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
    )
    jsonschema.validate(report, schema)
    assert report["branch_match"] is True
    assert report["ready_to_release"] is True
    assert report["safety_status"] == "ok"
    assert report["changed_files_count"] == 1
    assert report["commits_ahead_count"] == 1
    assert re.match(r"^tsr-[0-9a-f]{16}$", report["report_id"])
    assert re.match(r"^[0-9a-f]{40}$", report["head_commit"])


def test_safety_flags_all_const_true(srr, tmp_path):
    repo = _make_repo(tmp_path)
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
    )
    for flag in (
        "no_git_push",
        "no_git_merge",
        "no_git_tag",
        "no_wallet_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
    ):
        assert report["safety_flags"][flag] is True, "flag: " + flag


def test_wrong_branch_warns_and_not_ready(srr, tmp_path):
    repo = _make_repo(tmp_path)
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/wrong-name",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
    )
    assert report["branch_match"] is False
    assert report["ready_to_release"] is False
    assert any(
        "does not match" in w for w in report["warnings"]
    ), report["warnings"]


def test_dirty_tracked_tree_blocks_with_require_clean(srr, tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "FEATURE.md").write_text("changed\n", encoding="utf-8")
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
        require_clean_tracked_tree=True,
    )
    assert report["tree_status"]["tracked_dirty"] is True
    assert report["ready_to_release"] is False
    assert any("dirty" in w for w in report["warnings"]), report["warnings"]


def test_untracked_files_block_unless_allowed(srr, tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "scratch.txt").write_text("notes\n", encoding="utf-8")
    report_block = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
    )
    assert report_block["tree_status"]["untracked_count"] >= 1
    assert report_block["ready_to_release"] is False
    report_allow = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
        allow_untracked=True,
    )
    assert report_allow["tree_status"]["untracked_allowed"] is True
    assert report_allow["ready_to_release"] is True


def test_artifact_discovery_by_schema_content(srr, tmp_path):
    """Drop a fake autopilot report + dashboard + daily report +
    trial pack manifest into a demo dir under arbitrary file
    names. The runner must find them by their schema field,
    not by their filename."""
    repo = _make_repo(tmp_path)
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "weird-name-1.json").write_text(json.dumps({
        "schema": "trinity-task-queue-autopilot-report/v0.1",
        "autopilot_id": "tap-0123456789abcdef",
        "batches_attempted": 3,
        "items_completed": 5,
        "items_failed": 0,
        "safety_status": "ok",
        "stopped_reason": "queue_empty",
    }))
    (demo / "weird-name-2.json").write_text(json.dumps({
        "schema": "trinity-task-queue-dashboard/v0.1",
        "dashboard_id": "dsh-fedcba9876543210",
        "counts": {
            "pending": 0, "running": 0,
            "completed": 5, "failed": 0, "batches": 1,
        },
        "safety_status": "ok",
        "latest_items": [{"queue_item_id": "qit-x"}],
    }))
    nested = demo / "nested" / "sub"
    nested.mkdir(parents=True)
    (nested / "any.json").write_text(json.dumps({
        "schema": "trinity-daily-report/v0.1",
        "report_id": "tdr-1111222233334444",
        "counts": {
            "pending": 0, "running": 0,
            "completed": 5, "failed": 0, "batches": 1,
        },
        "top_materials": ["PrOx", "CeO2"],
        "cache_hits_total": 4,
        "workers_seen_total": 2,
        "safety_status": "ok",
    }))
    (demo / "manifest.json").write_text(json.dumps({
        "schema": "trinity-worker-trial-pack-manifest/v0.1",
        "pack_id": "twtp-aaaaaaaaaaaaaaaa",
        "worker_id": "worker-D",
        "repo_commit": "deadbeef" * 5,
        "repo_tag": "sprint-5.34-5.36",
        "expected_compute_output_sha256": "f" * 64,
        "files": [{"name": "a"}, {"name": "b"}],
    }))
    # And a non-Trinity JSON that must be IGNORED.
    (demo / "noise.json").write_text(json.dumps({
        "hello": "world",
    }))
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
        demo_root=demo,
    )
    types = sorted(a["artifact_type"] for a in report["demo_artifacts"])
    assert types == sorted([
        "autopilot_report", "dashboard",
        "daily_report", "trial_pack_manifest",
    ])
    # Verify per-artifact summary surfaced.
    by_type = {a["artifact_type"]: a for a in report["demo_artifacts"]}
    assert by_type["autopilot_report"]["summary"]["items_completed"] == 5
    assert by_type["dashboard"]["summary"]["counts"]["completed"] == 5
    assert by_type["daily_report"]["summary"]["top_materials"][:2] == [
        "PrOx", "CeO2",
    ]
    assert by_type["trial_pack_manifest"]["summary"]["worker_id"] == (
        "worker-D"
    )


def test_pytest_failure_marks_not_ready(srr, tmp_path):
    """Run pytest against a target file that fails on purpose, in
    a tempdir. The runner must capture failed > 0 and mark
    ready_to_release false."""
    repo = _make_repo(tmp_path)
    failing = repo / "test_failing.py"
    failing.write_text("def test_fails():\n    assert False\n")
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
        pytest_target="test_failing.py",
    )
    assert report["pytest"]["ran"] is True
    assert report["pytest"]["failed"] >= 1
    assert report["pytest"]["returncode"] != 0
    assert report["ready_to_release"] is False


def test_pytest_pass_keeps_ready_true(srr, tmp_path):
    repo = _make_repo(tmp_path)
    passing = repo / "test_passing.py"
    passing.write_text("def test_ok():\n    assert True\n")
    # Commit the new test file so the tree stays clean — otherwise
    # the untracked-file gate would block ready_to_release.
    _git(["add", "test_passing.py"], repo)
    _git(["commit", "-m", "add passing test"], repo)
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
        pytest_target="test_passing.py",
    )
    assert report["pytest"]["ran"] is True
    assert report["pytest"]["passed"] >= 1
    assert report["pytest"]["failed"] == 0
    assert report["pytest"]["returncode"] == 0
    assert report["ready_to_release"] is True


def test_disallowed_git_verb_rejected(srr):
    """The runner refuses any non-read-only git verb at call time."""
    with pytest.raises(srr.ReleaseRunnerError):
        srr._run_git(["push", "origin", "main"], Path("/tmp"))
    with pytest.raises(srr.ReleaseRunnerError):
        srr._run_git(["merge", "main"], Path("/tmp"))
    with pytest.raises(srr.ReleaseRunnerError):
        srr._run_git(["tag", "v1.0"], Path("/tmp"))
    with pytest.raises(srr.ReleaseRunnerError):
        srr._run_git(["reset", "--hard", "HEAD~1"], Path("/tmp"))
    with pytest.raises(srr.ReleaseRunnerError):
        srr._run_git(["checkout", "--", "README.md"], Path("/tmp"))


def test_render_markdown_has_all_sections(srr, tmp_path):
    repo = _make_repo(tmp_path)
    report = srr.build_report(
        repo_root=repo,
        sprint_id="sprint-5.40",
        branch="feature/x",
        base_ref="main",
        pinned_time="2026-05-18T00:10:00+00:00",
    )
    md = srr.render_markdown(report)
    for header in (
        "# Trinity Sprint Release Report",
        "## Branch",
        "## Commits",
        "## Tree status",
        "## Changed files",
        "## Tests",
        "## Demo artifacts",
        "## Warnings",
        "## Safety flags",
    ):
        assert header in md, "missing section: " + header
    assert "/tmp/" not in md  # no absolute path leak (path basenames only)


def test_cli_smoke(srr, tmp_path):
    repo = _make_repo(tmp_path)
    out_json = tmp_path / "out.json"
    out_md   = tmp_path / "out.md"
    rc = srr.main([
        "verify",
        "--repo-root", str(repo),
        "--sprint-id", "sprint-5.40",
        "--branch", "feature/x",
        "--base-ref", "main",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--pinned-time", "2026-05-18T00:10:00+00:00",
    ])
    assert rc == 0
    assert out_json.is_file()
    assert out_md.is_file()
    parsed = json.loads(out_json.read_text())
    assert parsed["schema"] == "trinity-sprint-release-report/v0.1"
    assert parsed["ready_to_release"] is True


def test_cli_returns_1_on_not_ready(srr, tmp_path):
    repo = _make_repo(tmp_path)
    out_json = tmp_path / "out.json"
    out_md   = tmp_path / "out.md"
    rc = srr.main([
        "verify",
        "--repo-root", str(repo),
        "--sprint-id", "sprint-5.40",
        "--branch", "feature/MISMATCH",
        "--base-ref", "main",
        "--out-json", str(out_json),
        "--out-md", str(out_md),
        "--pinned-time", "2026-05-18T00:10:00+00:00",
    ])
    assert rc == 1
    parsed = json.loads(out_json.read_text())
    assert parsed["ready_to_release"] is False


def test_cli_returns_2_on_missing_repo(srr, tmp_path):
    rc = srr.main([
        "verify",
        "--repo-root", str(tmp_path / "nope"),
        "--sprint-id", "sprint-5.40",
        "--branch", "feature/x",
        "--base-ref", "main",
        "--out-json", str(tmp_path / "out.json"),
        "--out-md", str(tmp_path / "out.md"),
        "--pinned-time", "2026-05-18T00:10:00+00:00",
    ])
    assert rc == 2
