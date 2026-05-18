"""Functional tests for v13_rc1_artifact_bundle.py."""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_rc1_artifact_bundle.py"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_rc1_artifact_bundle_manifest.schema.json"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v13_rc1_artifact_bundle", str(SCRIPT),
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


def _make_fake_build_dir(tmp_path: Path) -> Path:
    bd = tmp_path / "build-fake"
    bd.mkdir()
    (bd / "sost-node").write_bytes(b"FAKE-NODE-BYTES\n")
    (bd / "sost-miner").write_bytes(b"FAKE-MINER-BYTES\n")
    (bd / "sost-cli").write_bytes(b"FAKE-CLI-BYTES\n")
    return bd


def _make_fake_preflight_dir(tmp_path: Path, build_dir: Path,
                              ready: bool = True) -> Path:
    """Build a tiny preflight-output dir that matches the
    preflight schema (just the bits the bundler reads)."""
    import hashlib
    pd = tmp_path / "preflight-fake"
    pd.mkdir()
    sha_lines = []
    for name in ("sost-node", "sost-miner", "sost-cli"):
        digest = hashlib.sha256(
            (build_dir / name).read_bytes()
        ).hexdigest()
        sha_lines.append(digest + "  " + name)
    (pd / "SHA256SUMS").write_text(
        "\n".join(sorted(sha_lines)) + "\n", encoding="utf-8",
    )
    fake_report = {
        "schema": "trinity-v13-binary-preflight-report/v0.1",
        "ready_to_release": bool(ready),
        # extra fields the bundler does NOT read are allowed by
        # not validating against the preflight schema here.
    }
    (pd / "report.json").write_text(
        json.dumps(fake_report, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (pd / "report.md").write_text(
        "# fake preflight report\n", encoding="utf-8",
    )
    return pd


def test_script_exists():
    assert SCRIPT.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_bundle_creates_expected_tree(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out = tmp_path / "out"
    manifest = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd,
        preflight_dir=pd,
        out_dir=out,
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    assert (out / "MANIFEST.json").is_file()
    assert (out / "MANIFEST.md").is_file()
    assert (out / "VERIFY_COMMANDS.md").is_file()
    assert (out / "SHA256SUMS").is_file()
    for n in ("sost-node", "sost-miner", "sost-cli"):
        assert (out / "bin" / n).is_file()
    assert (out / "reports" / "preflight_report.json").is_file()
    assert (out / "reports" / "preflight_report.md").is_file()
    for f in (
        "v13_release_candidate.json",
        "v13_activation.json",
        "v13_binary_preflight.json",
    ):
        assert (out / "config" / f).is_file()
    # No tarball without --write-tarball.
    assert manifest["has_tarball"] is False
    assert manifest["tarball"] is None
    assert not any(out.glob("*.tar.gz"))


def test_manifest_validates_against_schema(srr, schema, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    manifest = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd,
        preflight_dir=pd,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    jsonschema.validate(manifest, schema)


def test_manifest_top_level_shape(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    manifest = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd,
        preflight_dir=pd,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    assert manifest["schema"] == (
        "trinity-v13-rc1-artifact-bundle-manifest/v0.1"
    )
    assert re.match(r"^v13rc1bundle-[0-9a-f]{16}$", manifest["bundle_id"])
    assert manifest["rc_id"] == "v13-rc1"
    assert manifest["activation_height"] == 12000
    assert manifest["sha256sums_basename"] == "SHA256SUMS"
    assert manifest["no_copy_binaries_mode"] is False


def test_binaries_sha_matches_preflight(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out = tmp_path / "out"
    manifest = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd,
        preflight_dir=pd,
        out_dir=out,
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    pre_sums = (pd / "SHA256SUMS").read_text().splitlines()
    pre_map = {}
    for line in pre_sums:
        digest, name = line.split(None, 1)
        pre_map[name.strip()] = digest.strip()
    for b in manifest["binaries"]:
        assert b["sha256"] == pre_map[b["name"]], b["name"]
    out_sums = (out / "SHA256SUMS").read_text().splitlines()
    assert sorted(out_sums) == sorted(pre_sums)


def test_sha_mismatch_with_preflight_aborts(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    # Tamper with the preflight's recorded SHA for sost-node so
    # the bundler sees a mismatch.
    text = (pd / "SHA256SUMS").read_text().splitlines()
    new = []
    for line in text:
        if line.endswith("  sost-node"):
            new.append("0" * 64 + "  sost-node")
        else:
            new.append(line)
    (pd / "SHA256SUMS").write_text("\n".join(new) + "\n",
                                    encoding="utf-8")
    with pytest.raises(srr.BundleError) as ei:
        srr.build_bundle(
            repo_root=REPO_ROOT,
            build_dir=bd,
            preflight_dir=pd,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-18T15:30:00+00:00",
        )
    assert "mismatch" in str(ei.value).lower()


def test_require_preflight_ready_blocks_when_false(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd, ready=False)
    with pytest.raises(srr.BundleError) as ei:
        srr.build_bundle(
            repo_root=REPO_ROOT,
            build_dir=bd,
            preflight_dir=pd,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-18T15:30:00+00:00",
            require_preflight_ready=True,
        )
    assert "ready_to_release" in str(ei.value).lower()


def test_no_copy_binaries_mode(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out = tmp_path / "out"
    manifest = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd,
        preflight_dir=pd,
        out_dir=out,
        pinned_time="2026-05-18T15:30:00+00:00",
        no_copy_binaries=True,
    )
    assert manifest["no_copy_binaries_mode"] is True
    # bin/ dir not populated.
    assert not (out / "bin").exists() or not any(
        (out / "bin").iterdir()
    )
    # But SHA256SUMS still written.
    assert (out / "SHA256SUMS").is_file()


def test_write_tarball(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out = tmp_path / "out"
    manifest = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd,
        preflight_dir=pd,
        out_dir=out,
        pinned_time="2026-05-18T15:30:00+00:00",
        write_tarball=True,
    )
    assert manifest["has_tarball"] is True
    tar_basename = manifest["tarball"]["basename"]
    assert tar_basename.endswith(".tar.gz")
    tar_path = out / tar_basename
    assert tar_path.is_file()
    assert tar_path.stat().st_size > 0


def test_tarball_deterministic(srr, tmp_path):
    """Two runs over the same inputs must produce byte-identical
    tarballs (sorted membership, uid=gid=0, mtime=0)."""
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out_a = tmp_path / "out-a"
    out_b = tmp_path / "out-b"
    m_a = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd, out_dir=out_a,
        pinned_time="2026-05-18T15:30:00+00:00",
        write_tarball=True,
    )
    m_b = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd, out_dir=out_b,
        pinned_time="2026-05-18T15:30:00+00:00",
        write_tarball=True,
    )
    assert m_a["bundle_id"] == m_b["bundle_id"]
    assert m_a["tarball"]["sha256"] == m_b["tarball"]["sha256"]


def test_missing_binary_raises(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    (bd / "sost-miner").unlink()
    with pytest.raises(srr.BundleError) as ei:
        srr.build_bundle(
            repo_root=REPO_ROOT,
            build_dir=bd, preflight_dir=pd,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-18T15:30:00+00:00",
        )
    assert "sost-miner" in str(ei.value)


def test_missing_preflight_report_raises(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    (pd / "report.json").unlink()
    with pytest.raises(srr.BundleError) as ei:
        srr.build_bundle(
            repo_root=REPO_ROOT,
            build_dir=bd, preflight_dir=pd,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-18T15:30:00+00:00",
        )
    assert "preflight report" in str(ei.value).lower()


def test_safety_flags_all_const_true(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    manifest = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_release_upload",
        "no_network_required",
        "no_auto_restart",
        "no_subprocess",
        "no_shell_true",
        "no_github_api",
        "no_ethereum_deploy",
    ):
        assert manifest["safety_flags"][flag] is True, flag


def test_manifest_no_absolute_tmp_paths(srr, tmp_path):
    """Defensive: the public manifest.json must NOT contain any
    absolute /tmp/ path leaking the operator's local build dir."""
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out = tmp_path / "out"
    srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd, out_dir=out,
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    blob = (out / "MANIFEST.json").read_text()
    assert "/tmp/" not in blob, "MANIFEST.json leaks /tmp path"


def test_bundle_id_deterministic_across_runs(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    m1 = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd,
        out_dir=tmp_path / "o1",
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    m2 = srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd,
        out_dir=tmp_path / "o2",
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    assert m1["bundle_id"] == m2["bundle_id"]


def test_manifest_md_has_all_sections(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out = tmp_path / "out"
    srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd, out_dir=out,
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    md = (out / "MANIFEST.md").read_text()
    for header in (
        "# V13 RC1 Local Artifact Bundle Manifest",
        "## Binaries",
        "## SHA256SUMS",
        "## Reports",
        "## Configs",
        "## Tarball",
        "## Safety flags",
        "## What this bundle is NOT",
    ):
        assert header in md, "missing section: " + header


def test_verify_commands_md_has_recipe(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    out = tmp_path / "out"
    srr.build_bundle(
        repo_root=REPO_ROOT,
        build_dir=bd, preflight_dir=pd, out_dir=out,
        pinned_time="2026-05-18T15:30:00+00:00",
    )
    md = (out / "VERIFY_COMMANDS.md").read_text()
    assert "sha256sum -c SHA256SUMS" in md
    assert "manifest cross-check OK" in md
    assert "safety_flags" in md


def test_cli_returns_0_on_success(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    rc = srr.main([
        "--repo-root",      str(REPO_ROOT),
        "--build-dir",      str(bd),
        "--preflight-dir",  str(pd),
        "--out-dir",        str(tmp_path / "out"),
        "--pinned-time",    "2026-05-18T15:30:00+00:00",
    ])
    assert rc == 0


def test_cli_returns_1_on_sha_mismatch(srr, tmp_path):
    bd = _make_fake_build_dir(tmp_path)
    pd = _make_fake_preflight_dir(tmp_path, bd)
    # Tamper with the binary so the SHA differs from preflight.
    (bd / "sost-node").write_bytes(b"TAMPERED-NODE-BYTES\n")
    rc = srr.main([
        "--repo-root",      str(REPO_ROOT),
        "--build-dir",      str(bd),
        "--preflight-dir",  str(pd),
        "--out-dir",        str(tmp_path / "out"),
        "--pinned-time",    "2026-05-18T15:30:00+00:00",
    ])
    assert rc == 1
