"""Functional tests for Sprint 5.37 worker_trial_pack.py."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "worker_trial_pack.py"
FIXTURE = (
    REPO_ROOT / "tests" / "trinity" / "fixtures"
    / "useful_compute" / "request_materials_engine.json"
)


def _import_script():
    """Import worker_trial_pack.py as a module without using subprocess."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "worker_trial_pack", str(SCRIPT),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def wtp():
    return _import_script()


def _build_pack(wtp, out_dir, worker_id="worker-D",
                pinned_time="2026-05-18T00:00:00+00:00",
                repo_commit="abc1234567",
                repo_tag="sprint-5.34-5.36"):
    return wtp.build_trial_pack(
        worker_id=worker_id,
        pinned_time=pinned_time,
        out_dir=Path(out_dir),
        request_fixture=FIXTURE,
        repo_commit=repo_commit,
        repo_tag=repo_tag,
    )


def test_script_exists():
    assert SCRIPT.is_file()


def test_fixture_exists():
    assert FIXTURE.is_file(), "needs the scientific_intake request fixture"


def test_pack_files_present(tmp_path, wtp):
    _build_pack(wtp, tmp_path)
    for name in (
        "PACK_MANIFEST.json",
        "README_WORKER_TRIAL.md",
        "worker_config.json",
        "sample_request.json",
        "expected_result_hashes.json",
    ):
        assert (tmp_path / name).is_file(), "missing: " + name


def test_manifest_shape(tmp_path, wtp):
    manifest = _build_pack(wtp, tmp_path)
    assert manifest["schema"] == "trinity-worker-trial-pack-manifest/v0.1"
    assert re.match(r"^twtp-[0-9a-f]{16}$", manifest["pack_id"])
    assert manifest["worker_id"] == "worker-D"
    assert re.match(r"^[0-9a-f]{16}$", manifest["worker_id_hash"])
    assert manifest["repo_commit"] == "abc1234567"
    assert manifest["repo_tag"] == "sprint-5.34-5.36"
    assert re.match(
        r"^[0-9a-f]{64}$", manifest["expected_compute_output_sha256"]
    )
    assert manifest["request_basename"] == "sample_request.json"
    assert len(manifest["files"]) == 4
    file_names = sorted(f["name"] for f in manifest["files"])
    assert file_names == sorted([
        "README_WORKER_TRIAL.md",
        "worker_config.json",
        "sample_request.json",
        "expected_result_hashes.json",
    ])


def test_safety_status_all_const_true(tmp_path, wtp):
    manifest = _build_pack(wtp, tmp_path)
    for flag in (
        "no_wallet_required",
        "no_private_key_required",
        "no_seed_phrase_required",
        "no_broadcast_capability",
        "no_network_in_worker_process",
        "pack_carries_no_secrets",
    ):
        assert manifest["safety_status"][flag] is True, "flag: " + flag


def test_pack_is_deterministic(tmp_path, wtp):
    p1 = tmp_path / "pack-1"
    p2 = tmp_path / "pack-2"
    m1 = _build_pack(wtp, p1)
    m2 = _build_pack(wtp, p2)
    # Per-file content must be byte-identical.
    for name in (
        "PACK_MANIFEST.json",
        "README_WORKER_TRIAL.md",
        "worker_config.json",
        "sample_request.json",
        "expected_result_hashes.json",
    ):
        a = (p1 / name).read_bytes()
        b = (p2 / name).read_bytes()
        assert a == b, "non-deterministic file: " + name
    assert m1["pack_id"] == m2["pack_id"]
    assert m1["expected_compute_output_sha256"] == (
        m2["expected_compute_output_sha256"]
    )


def test_pack_files_match_manifest_sha256(tmp_path, wtp):
    manifest = _build_pack(wtp, tmp_path)
    import hashlib
    for f in manifest["files"]:
        contents = (tmp_path / f["name"]).read_bytes()
        h = hashlib.sha256(contents).hexdigest()
        assert h == f["sha256"], "sha256 mismatch on " + f["name"]
        assert len(contents) == f["size_bytes"]


def test_no_real_sost_address_in_pack(tmp_path, wtp):
    _build_pack(wtp, tmp_path)
    for p in tmp_path.iterdir():
        text = p.read_text(encoding="utf-8")
        m = re.search(r"sost1[0-9a-f]{40}", text)
        assert not m, "real SOST address leaked into " + p.name


def test_no_64hex_blob_in_pack(tmp_path, wtp):
    """A 64-hex blob inside the pack must be a hash, not a private
    key. We check that every 64-hex appears next to a known hash
    field name (sha256, compute_output_sha256, hash, ...). Any 64-hex
    that is NOT bound to a hash field is suspect."""
    _build_pack(wtp, tmp_path)
    pattern = re.compile(r"[0-9a-f]{64}")
    hash_field_marker = re.compile(
        r"(sha256|cache_sha256|compute_output_sha256"
        r"|expected_compute_output_sha256|hash|sha)"
        r"[^A-Za-z0-9]+[0-9a-f]{64}",
        re.IGNORECASE,
    )
    for p in tmp_path.iterdir():
        if p.suffix == ".md":
            # README explicitly prints the expected hash by name.
            continue
        text = p.read_text(encoding="utf-8")
        matches = pattern.findall(text)
        bound = hash_field_marker.findall(text)
        # every 64-hex must be inside a hash binding; we expect
        # bound count >= matches count for the JSON files.
        assert len(bound) >= len(matches), (
            "unbound 64-hex blob in " + p.name + " (suspected secret)"
        )


def test_invalid_worker_id_rejected(tmp_path, wtp):
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, worker_id="bad/id")
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, worker_id="")
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, worker_id="a" * 65)


def test_invalid_commit_rejected(tmp_path, wtp):
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, repo_commit="ABC1234")  # uppercase
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, repo_commit="zz")
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, repo_commit="ab")


def test_invalid_tag_rejected(tmp_path, wtp):
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, repo_tag="bad tag")  # space
    with pytest.raises(wtp.TrialPackError):
        _build_pack(wtp, tmp_path, repo_tag="")


def test_payout_address_is_placeholder_only(tmp_path, wtp):
    _build_pack(wtp, tmp_path)
    cfg = json.loads((tmp_path / "worker_config.json").read_text())
    ws = cfg["address_map_template"]["workers"]
    assert ws[0]["payout_address"] == "<PAYOUT_ADDRESS_FOR_worker-D>"


def test_expected_hashes_payload(tmp_path, wtp):
    _build_pack(wtp, tmp_path)
    exp = json.loads(
        (tmp_path / "expected_result_hashes.json").read_text()
    )
    assert exp["schema"] == "trinity-worker-trial-pack-expected/v0.1"
    assert re.match(r"^[0-9a-f]{64}$", exp["compute_output_sha256"])
    assert exp["backend_name"] == "local_materials_engine_v01"
    assert exp["backend_kind"] == "real_backend"
    assert exp["materials_project_cache_used"] is True
    assert exp["materials_project_cache_hit_count"] >= 1
    assert exp["materials_project_cache_miss_count"] >= 0


def test_cli_argv(tmp_path, wtp):
    """Invoke the CLI through main() directly (no subprocess)."""
    out_dir = tmp_path / "cli_out"
    rc = wtp.main([
        "--worker-id", "worker-D",
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-18T00:00:00+00:00",
        "--request-fixture", str(FIXTURE),
        "--repo-commit", "abc1234567",
        "--repo-tag", "sprint-5.34-5.36",
    ])
    assert rc == 0
    assert (out_dir / "PACK_MANIFEST.json").is_file()


def test_cli_invalid_worker_id_returns_2(tmp_path, wtp):
    out_dir = tmp_path / "cli_out"
    rc = wtp.main([
        "--worker-id", "bad/id",
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-18T00:00:00+00:00",
        "--request-fixture", str(FIXTURE),
        "--repo-commit", "abc1234567",
        "--repo-tag", "sprint-5.34-5.36",
    ])
    assert rc == 2


def test_readme_mentions_expected_hash(tmp_path, wtp):
    manifest = _build_pack(wtp, tmp_path)
    readme = (tmp_path / "README_WORKER_TRIAL.md").read_text()
    assert manifest["expected_compute_output_sha256"] in readme


def test_no_absolute_tmp_path_in_pack_files(tmp_path, wtp):
    _build_pack(wtp, tmp_path)
    for p in tmp_path.iterdir():
        text = p.read_text(encoding="utf-8")
        # Any absolute /tmp/ in the pack is leakage of the operator
        # build dir.
        assert "/tmp/" not in text, "absolute /tmp/ leaked into " + p.name
