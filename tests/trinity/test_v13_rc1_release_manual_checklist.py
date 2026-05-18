"""Functional tests for v13_rc1_release_manual_checklist.py."""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT / "scripts" / "trinity"
    / "v13_rc1_release_manual_checklist.py"
)
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_rc1_release_manual_checklist.schema.json"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v13_rc1_release_manual_checklist", str(SCRIPT),
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


def _make_fake_repo_root(tmp_path: Path, release_status: str) -> Path:
    """Build a minimal repo_root that contains a single public
    manifest at the requested release_status. Used by the CLI
    happy-path test so it does NOT depend on the live state of
    the actual repository (which moves forward as the V13 RC1
    release machine advances)."""
    import json as _json
    rr = tmp_path / "fake-repo"
    (rr / "website" / "api").mkdir(parents=True)
    (rr / "website" / "api" / "v13_rc1_artifact_manifest.json").write_text(
        _json.dumps({
            "schema": "sost-v13-rc1-artifact-manifest-public/v0.1",
            "release_status": release_status,
        }),
        encoding="utf-8",
    )
    return rr


def _make_fake_bundle(tmp_path: Path) -> Path:
    bd = tmp_path / "bundle-fake"
    bd.mkdir()
    (bd / "bin").mkdir()
    (bd / "bin" / "sost-node").write_bytes(b"FAKE-NODE\n")
    (bd / "bin" / "sost-miner").write_bytes(b"FAKE-MINER\n")
    (bd / "bin" / "sost-cli").write_bytes(b"FAKE-CLI\n")
    (bd / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (bd / "MANIFEST.md").write_text("# x\n", encoding="utf-8")
    (bd / "VERIFY_COMMANDS.md").write_text("# y\n", encoding="utf-8")
    # SHA256SUMS with three canonical lines
    import hashlib
    lines = []
    for name in ("sost-node", "sost-miner", "sost-cli"):
        h = hashlib.sha256(
            (bd / "bin" / name).read_bytes()
        ).hexdigest()
        lines.append(h + "  " + name)
    (bd / "SHA256SUMS").write_text(
        "\n".join(sorted(lines)) + "\n", encoding="utf-8",
    )
    # Tarball placeholder (just a name with .tar.gz suffix)
    (bd / "v13-rc1-artifact-bundle-fake.tar.gz").write_bytes(
        b"FAKE-TAR\n",
    )
    return bd


def test_script_exists():
    assert SCRIPT.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_checklist_validates_against_schema(srr, schema, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    checklist = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    jsonschema.validate(checklist, schema)


def test_checklist_top_level_shape(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    assert cl["schema"] == "trinity-v13-rc1-release-manual-checklist/v0.1"
    assert re.match(r"^v13rc1cl-[0-9a-f]{16}$", cl["checklist_id"])
    assert cl["rc_id"] == "v13-rc1"
    assert cl["activation_height"] == 12000
    assert cl["repo_root_basename"] == REPO_ROOT.name


def test_bundle_checks_all_ok_with_real_bundle(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    assert cl["bundle_checks"]["all_ok"] is True
    for b in cl["bundle_checks"]["binaries_present"]:
        assert b["present"] is True
    assert cl["bundle_checks"]["sha256sums_present"] is True
    assert len(cl["bundle_checks"]["sha256sums_lines"]) == 3
    for row in cl["bundle_checks"]["sha256sums_lines"]:
        assert re.match(r"^[0-9a-f]{64}$", row["sha256"])
        assert row["name"] in ("sost-node", "sost-miner", "sost-cli")


def test_bundle_check_detects_missing_binary(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    (bd / "bin" / "sost-miner").unlink()
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    by_name = {b["name"]: b for b in cl["bundle_checks"]["binaries_present"]}
    assert by_name["sost-miner"]["present"] is False
    assert cl["bundle_checks"]["all_ok"] is False
    assert cl["safety_status"] in ("warning", "failed")


def test_public_metadata_state_reads_repo(srr, tmp_path):
    """The script reads website/api/v13_rc1_artifact_manifest.json
    from the repo. On the current main, that file already exists
    and is at metadata_only_not_signed_not_uploaded. The check
    should report matches=true."""
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    pm = cl["public_metadata_state"]
    assert pm["release_status_expected"] == (
        "metadata_only_not_signed_not_uploaded"
    )
    assert pm["release_status_current"] in (
        "metadata_only_not_signed_not_uploaded",
        "signed_metadata_only",
        "signed_and_published",
        "unknown",
    )
    # On current main, the metadata published by website-v268 is
    # exactly the pre-signing state, so matches must be true.
    if pm["release_status_current"] == (
        "metadata_only_not_signed_not_uploaded"
    ):
        assert pm["matches"] is True


def test_manual_steps_cover_all_stages(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    stages = sorted({s["stage"] for s in cl["manual_steps"]})
    assert stages == sorted([
        "A_preverify", "B_sign", "C_upload",
        "D_update_metadata", "E_announce",
    ])
    # At least one step per stage.
    for stage in stages:
        n = sum(1 for s in cl["manual_steps"] if s["stage"] == stage)
        assert n >= 1, "stage " + stage + " has no steps"


def test_every_manual_step_must_be_done_by_operator(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    for s in cl["manual_steps"]:
        assert s["must_be_done_by_operator"] is True, s["id"]


def test_signing_step_is_marked_uses_release_key(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    by_id = {s["id"]: s for s in cl["manual_steps"]}
    assert by_id["A3"]["uses_release_key"] is True
    assert by_id["B1"]["uses_release_key"] is True
    # B2 / B3 only verify or hash; do not use the key.
    assert by_id["B2"]["uses_release_key"] is False
    assert by_id["B3"]["uses_release_key"] is False


def test_upload_steps_are_marked_uses_network(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    by_id = {s["id"]: s for s in cl["manual_steps"]}
    for cid in ("C1", "C2", "C3"):
        assert by_id[cid]["uses_network"] is True, cid
    # Pre-sign steps must NOT use network.
    for aid in ("A1", "A2", "A3"):
        assert by_id[aid]["uses_network"] is False, aid


def test_safety_flags_all_const_true(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    for flag in (
        "no_private_key_access",
        "no_signing_executed",
        "no_release_upload",
        "no_github_api",
        "no_wallet_access",
        "no_broadcast",
        "no_network_required",
        "no_subprocess",
        "no_shell_true",
        "no_ethereum_deploy",
        "no_gpg_invocation",
    ):
        assert cl["safety_flags"][flag] is True, flag


def test_checklist_deterministic(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    c1 = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    c2 = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    assert c1["checklist_id"] == c2["checklist_id"]


def test_cli_returns_0_on_happy_path(srr, tmp_path):
    """Happy path = bundle intact + public metadata at the expected
    pre-signing state. Use a self-contained fake repo so the test
    does not depend on the live repository's release_status, which
    legitimately advances as the V13 RC1 release machine moves
    forward (metadata_only_not_signed_not_uploaded ->
    signed_metadata_only -> signed_and_published)."""
    bd = _make_fake_bundle(tmp_path)
    rr = _make_fake_repo_root(
        tmp_path, "metadata_only_not_signed_not_uploaded",
    )
    rc = srr.main([
        "--repo-root",   str(rr),
        "--bundle-dir",  str(bd),
        "--out-json",    str(tmp_path / "out.json"),
        "--out-md",      str(tmp_path / "out.md"),
        "--pinned-time", "2026-05-18T16:30:00+00:00",
    ])
    assert rc == 0


def test_cli_returns_1_on_missing_binary(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    (bd / "bin" / "sost-cli").unlink()
    rr = _make_fake_repo_root(
        tmp_path, "metadata_only_not_signed_not_uploaded",
    )
    rc = srr.main([
        "--repo-root",   str(rr),
        "--bundle-dir",  str(bd),
        "--out-json",    str(tmp_path / "out.json"),
        "--out-md",      str(tmp_path / "out.md"),
        "--pinned-time", "2026-05-18T16:30:00+00:00",
    ])
    assert rc == 1


def test_cli_returns_1_when_metadata_already_signed(srr, tmp_path):
    """Once the operator has signed (release_status =
    signed_metadata_only) the pre-signing checklist no longer
    matches; the CLI must report that the metadata has moved
    past the pre-signing state by returning 1."""
    bd = _make_fake_bundle(tmp_path)
    rr = _make_fake_repo_root(tmp_path, "signed_metadata_only")
    rc = srr.main([
        "--repo-root",   str(rr),
        "--bundle-dir",  str(bd),
        "--out-json",    str(tmp_path / "out.json"),
        "--out-md",      str(tmp_path / "out.md"),
        "--pinned-time", "2026-05-18T16:30:00+00:00",
    ])
    assert rc == 1


def test_cli_returns_2_on_missing_repo(srr, tmp_path):
    rc = srr.main([
        "--repo-root",   str(tmp_path / "nope"),
        "--bundle-dir",  str(tmp_path / "bundle"),
        "--out-json",    str(tmp_path / "out.json"),
        "--out-md",      str(tmp_path / "out.md"),
        "--pinned-time", "2026-05-18T16:30:00+00:00",
    ])
    assert rc == 2


def test_render_markdown_has_all_sections(srr, tmp_path):
    bd = _make_fake_bundle(tmp_path)
    cl = srr.build_checklist(
        repo_root=REPO_ROOT, bundle_dir=bd,
        pinned_time="2026-05-18T16:30:00+00:00",
    )
    md = srr.render_markdown(cl)
    for header in (
        "# V13 RC1 Release Manual Checklist",
        "## 0. Pre-flight bundle checks",
        "## 0a. Public metadata state",
        "## 1. Manual steps (operator-only)",
        "### A — Pre-sign verification",
        "### B — Sign SHA256SUMS",
        "### C — Upload release",
        "### D — Update public metadata",
        "### E — Announce",
        "## 2. Hard warnings",
        "## 3. State transition",
        "## 4. Safety flags",
    ):
        assert header in md, "missing section: " + header
