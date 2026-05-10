"""Tests for the Trinity Proof Registry v0 builder + verifier."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load_module(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def builder():
    return _load_module(
        "trinity_proof_registry_under_test",
        SCRIPTS_DIR / "trinity_proof_registry.py",
    )


@pytest.fixture(scope="module")
def verifier():
    return _load_module(
        "verify_trinity_registry_under_test",
        SCRIPTS_DIR / "verify_trinity_registry.py",
    )


@pytest.fixture
def kalgoorlie_entry(builder) -> Dict[str, Any]:
    return copy.deepcopy(builder.KALGOORLIE_PHASE1_ENTRY)


def _build_with(entry, builder, **overrides):
    kwargs = dict(
        generated_at_utc="2026-05-10T00:00:00+00:00",
        network="SOST mainnet",
        entries=[entry],
        repo_root=None,
        require_bundle_match=False,
    )
    kwargs.update(overrides)
    return builder.build_registry(**kwargs)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_canonical_dumps_is_byte_identical(builder, kalgoorlie_entry):
    r1 = _build_with(kalgoorlie_entry, builder)
    r2 = _build_with(copy.deepcopy(kalgoorlie_entry), builder)
    blob1 = builder.canonical_dumps(r1)
    blob2 = builder.canonical_dumps(r2)
    assert blob1 == blob2
    assert blob1.startswith('{"entries":[')
    assert "registry_generated_at_utc" in blob1


def test_changing_pinned_time_changes_blob(builder, kalgoorlie_entry):
    r1 = _build_with(kalgoorlie_entry, builder)
    r2 = _build_with(
        copy.deepcopy(kalgoorlie_entry),
        builder,
        generated_at_utc="2026-06-01T00:00:00+00:00",
    )
    assert builder.canonical_dumps(r1) != builder.canonical_dumps(r2)


def test_canonical_blob_has_no_host_paths(builder, kalgoorlie_entry):
    blob = builder.canonical_dumps(_build_with(kalgoorlie_entry, builder))
    for needle in ("/home/", "/opt/", "/Users/", "C:/", "C:\\"):
        assert needle not in blob


# ---------------------------------------------------------------------------
# Validation: the canonical Kalgoorlie entry passes
# ---------------------------------------------------------------------------


def test_valid_kalgoorlie_entry_validates(builder, kalgoorlie_entry):
    builder.validate_entry(kalgoorlie_entry, require_bundle_match=False)


def test_valid_registry_round_trip_through_canonical(builder, kalgoorlie_entry):
    r = _build_with(kalgoorlie_entry, builder)
    blob = builder.canonical_dumps(r)
    parsed = json.loads(blob)
    assert parsed["schema"] == "trinity-proof-registry/v0"
    assert parsed["entries"][0]["id"] == "kalgoorlie_phase1"
    assert parsed["entries"][0]["block_height"] == 8085


# ---------------------------------------------------------------------------
# Validation: each individual constraint rejects the right input
# ---------------------------------------------------------------------------


def test_invalid_txid_short_hex_fails(builder, kalgoorlie_entry):
    kalgoorlie_entry["txid"] = "deadbeef"
    with pytest.raises(builder.RegistryError, match="txid"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_invalid_txid_uppercase_fails(builder, kalgoorlie_entry):
    kalgoorlie_entry["txid"] = kalgoorlie_entry["txid"].upper()
    with pytest.raises(builder.RegistryError, match="txid"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_invalid_proof_bundle_sha256_fails(builder, kalgoorlie_entry):
    kalgoorlie_entry["proof_bundle_sha256"] = "x" * 64
    with pytest.raises(builder.RegistryError, match="proof_bundle_sha256"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_sha16_must_match_first_16_of_full_sha(builder, kalgoorlie_entry):
    # Tamper with sha16 only.
    kalgoorlie_entry["proof_bundle_sha16"] = "0000000000000000"
    with pytest.raises(
        builder.RegistryError, match="proof_bundle_sha16"
    ):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_capsule_text_must_contain_sha16(builder, kalgoorlie_entry):
    kalgoorlie_entry["capsule_text"] = "trinity-proof kalgoorlie_phase1 wrong"
    with pytest.raises(builder.RegistryError, match="capsule_text"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_status_must_be_in_allowed_set(builder, kalgoorlie_entry):
    kalgoorlie_entry["status"] = "broadcasted"
    with pytest.raises(builder.RegistryError, match="status"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_capsule_mode_must_be_in_allowed_set(builder, kalgoorlie_entry):
    kalgoorlie_entry["capsule_mode"] = "binary-blob"
    with pytest.raises(builder.RegistryError, match="capsule_mode"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_block_height_must_be_positive_int(builder, kalgoorlie_entry):
    kalgoorlie_entry["block_height"] = -1
    with pytest.raises(builder.RegistryError, match="block_height"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_block_height_zero_fails(builder, kalgoorlie_entry):
    kalgoorlie_entry["block_height"] = 0
    with pytest.raises(builder.RegistryError, match="block_height"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_missing_safety_field_fails(builder, kalgoorlie_entry):
    kalgoorlie_entry["safety_status"].pop("not_a_mineral_reserve_claim")
    with pytest.raises(builder.RegistryError, match="not_a_mineral_reserve_claim"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_safety_field_must_be_true(builder, kalgoorlie_entry):
    kalgoorlie_entry["safety_status"]["no_auto_broadcast"] = False
    with pytest.raises(builder.RegistryError, match="no_auto_broadcast"):
        builder.validate_entry(
            kalgoorlie_entry, require_bundle_match=False,
        )


def test_generated_at_utc_must_end_with_offset(builder, kalgoorlie_entry):
    with pytest.raises(builder.RegistryError, match="generated_at_utc"):
        _build_with(
            kalgoorlie_entry, builder,
            generated_at_utc="2026-05-10T00:00:00",
        )


def test_duplicate_entry_id_rejected(builder, kalgoorlie_entry):
    second = copy.deepcopy(kalgoorlie_entry)
    with pytest.raises(builder.RegistryError, match="duplicate entry id"):
        _build_with(
            kalgoorlie_entry, builder,
            entries=[kalgoorlie_entry, second],
        )


# ---------------------------------------------------------------------------
# Host-path leak guard
# ---------------------------------------------------------------------------


def test_host_path_leak_in_entry_is_rejected(builder, kalgoorlie_entry):
    kalgoorlie_entry["operator"] = "neob /home/sost/oops"
    with pytest.raises(builder.RegistryError, match="host-path"):
        _build_with(kalgoorlie_entry, builder)


# ---------------------------------------------------------------------------
# Local bundle rehash check
# ---------------------------------------------------------------------------


def test_bundle_match_succeeds_when_file_present(
    tmp_path, builder, kalgoorlie_entry,
):
    # Copy the live bundle into tmp_path so the rehash check finds it.
    src = REPO_ROOT / "TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json"
    if not src.exists():
        pytest.skip("live bundle file not available in this branch")
    dst = tmp_path / "TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json"
    dst.write_bytes(src.read_bytes())
    # Should validate cleanly with require_bundle_match=True.
    builder.validate_entry(
        kalgoorlie_entry,
        repo_root=tmp_path,
        require_bundle_match=True,
    )


def test_bundle_match_fails_on_tampered_local_file(
    tmp_path, builder, kalgoorlie_entry,
):
    dst = tmp_path / "TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json"
    dst.write_bytes(b'{"schema":"tampered"}')
    with pytest.raises(builder.RegistryError, match="does not match"):
        builder.validate_entry(
            kalgoorlie_entry,
            repo_root=tmp_path,
            require_bundle_match=True,
        )


# ---------------------------------------------------------------------------
# Static safety: builder + verifier never broadcast / send / reward / activate
# ---------------------------------------------------------------------------


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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_strings_and_comments(src: str) -> str:
    """Remove triple-quoted strings, single/double quoted strings and
    line comments so static checks only see executable code tokens."""
    # Triple-quoted strings.
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    # Single and double quoted strings on a single line.
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', "", src)
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", "", src)
    # Line comments.
    src = re.sub(r"#.*$", "", src, flags=re.MULTILINE)
    return src


def _assert_safe_code_surface(src: str, label: str) -> None:
    code = _strip_strings_and_comments(src)
    code_lower = code.lower()
    for needle in _FORBIDDEN_CALL_PATTERNS:
        assert needle.lower() not in code_lower, (
            f"forbidden call pattern {needle!r} appears in {label}"
        )
    for needle in _FORBIDDEN_TOKEN_NAMES:
        assert needle.lower() not in code_lower, (
            f"forbidden token {needle!r} appears in {label}"
        )
    # Forbidden imports: match `import X` or `from X` at top level.
    for name in _FORBIDDEN_IMPORT_NAMES:
        bad_import = re.search(
            rf"^\s*(?:import\s+{re.escape(name)}\b|from\s+{re.escape(name)}\b)",
            code,
            flags=re.MULTILINE,
        )
        assert bad_import is None, (
            f"forbidden import of {name!r} appears in {label}"
        )


def test_builder_has_no_network_or_broadcast_calls():
    _assert_safe_code_surface(
        _read(SCRIPTS_DIR / "trinity_proof_registry.py"),
        "builder",
    )


def test_verifier_has_no_network_or_broadcast_calls():
    _assert_safe_code_surface(
        _read(SCRIPTS_DIR / "verify_trinity_registry.py"),
        "verifier",
    )


def test_builder_cli_has_no_register_or_send_or_broadcast_flag():
    """The argparse surface must not expose --register / --send / --broadcast."""
    src = _read(SCRIPTS_DIR / "trinity_proof_registry.py")
    for forbidden_flag in (
        "--register", "--send", "--broadcast", "--activate",
        "--reward", "--sign-tx",
    ):
        assert forbidden_flag not in src, (
            f"builder argparse must not expose {forbidden_flag!r}"
        )


# ---------------------------------------------------------------------------
# Verifier behaviour
# ---------------------------------------------------------------------------


def _write_canonical(path: Path, registry: Dict[str, Any], builder) -> None:
    path.write_text(builder.canonical_dumps(registry), encoding="utf-8")


def test_verifier_passes_on_valid_registry(
    tmp_path, builder, verifier, kalgoorlie_entry,
):
    reg = _build_with(kalgoorlie_entry, builder)
    p = tmp_path / "registry.json"
    _write_canonical(p, reg, builder)
    ok, lines = verifier.verify_registry(
        p, search_paths=[tmp_path, REPO_ROOT],
    )
    assert ok, "valid registry should pass: " + "\n".join(lines)
    assert any("R1 schema" in l for l in lines)
    assert any("R10" in l and "PASS" in l for l in lines)


def test_verifier_detects_tampered_proof_sha(
    tmp_path, builder, verifier, kalgoorlie_entry,
):
    reg = _build_with(kalgoorlie_entry, builder)
    # Tamper with sha16 so it no longer matches the full SHA prefix.
    reg["entries"][0]["proof_bundle_sha16"] = "0000000000000000"
    p = tmp_path / "registry.json"
    _write_canonical(p, reg, builder)
    ok, lines = verifier.verify_registry(p, search_paths=[tmp_path])
    assert not ok
    assert any(
        "R7" in l and "FAIL" in l for l in lines
    ), "\n".join(lines)


def test_verifier_detects_wrong_capsule_prefix(
    tmp_path, builder, verifier, kalgoorlie_entry,
):
    reg = _build_with(kalgoorlie_entry, builder)
    # Replace the sha16 inside capsule_text with garbage but keep
    # sha16 itself intact, so R8 trips and not R7.
    reg["entries"][0]["capsule_text"] = (
        "trinity-proof kalgoorlie_phase1 0000000000000000"
    )
    p = tmp_path / "registry.json"
    _write_canonical(p, reg, builder)
    ok, lines = verifier.verify_registry(p, search_paths=[tmp_path])
    assert not ok
    assert any("R8" in l and "FAIL" in l for l in lines)


def test_verifier_detects_invalid_txid(
    tmp_path, builder, verifier, kalgoorlie_entry,
):
    reg = _build_with(kalgoorlie_entry, builder)
    reg["entries"][0]["txid"] = "not-a-real-txid"
    p = tmp_path / "registry.json"
    _write_canonical(p, reg, builder)
    ok, lines = verifier.verify_registry(p, search_paths=[tmp_path])
    assert not ok
    assert any("R6" in l and "FAIL" in l for l in lines)


def test_verifier_detects_missing_safety_flag(
    tmp_path, builder, verifier, kalgoorlie_entry,
):
    reg = _build_with(kalgoorlie_entry, builder)
    reg["entries"][0]["safety_status"]["no_auto_broadcast"] = False
    p = tmp_path / "registry.json"
    _write_canonical(p, reg, builder)
    ok, lines = verifier.verify_registry(p, search_paths=[tmp_path])
    assert not ok
    assert any("R10" in l and "FAIL" in l for l in lines)


def test_verifier_detects_host_path_leak_in_raw_file(
    tmp_path, builder, verifier, kalgoorlie_entry,
):
    # We bypass the builder's leak guard by writing a pre-built blob
    # that contains a host path. The verifier must catch it via R11.
    reg = _build_with(kalgoorlie_entry, builder)
    p = tmp_path / "registry.json"
    blob = builder.canonical_dumps(reg)
    # Surgically inject a leak inside an existing string field.
    blob = blob.replace(
        '"operator":"NeoB"', '"operator":"NeoB /home/sost/leak"'
    )
    p.write_text(blob, encoding="utf-8")
    ok, lines = verifier.verify_registry(p, search_paths=[tmp_path])
    assert not ok
    assert any("R11" in l and "FAIL" in l for l in lines)


def test_verifier_detects_tampered_proof_bundle_file(
    tmp_path, builder, verifier, kalgoorlie_entry,
):
    """If the live bundle file is present but its SHA doesn't match
    the recorded ``proof_bundle_sha256``, R12 must FAIL."""
    reg = _build_with(kalgoorlie_entry, builder)
    p = tmp_path / "registry.json"
    _write_canonical(p, reg, builder)
    # Place a tampered bundle file alongside the registry.
    tampered = tmp_path / "TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.json"
    tampered.write_bytes(b'{"schema":"trinity-proof-bundle/v0","tampered":true}')
    ok, lines = verifier.verify_registry(p, search_paths=[tmp_path])
    assert not ok
    assert any("R12" in l and "FAIL" in l for l in lines)


def test_cli_builder_writes_and_round_trips(tmp_path):
    """End-to-end: invoke the builder as a script, then run the
    verifier as a script. Both must exit 0 and produce expected files."""
    out_json = tmp_path / "TRINITY_PROOF_REGISTRY.json"
    out_md = tmp_path / "TRINITY_PROOF_REGISTRY.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "trinity_proof_registry.py"),
            "--out-json", str(out_json),
            "--out-md", str(out_md),
            "--no-bundle-match",
            "--no-verify-bundle",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_json.exists() and out_md.exists()
    parsed = json.loads(out_json.read_text(encoding="utf-8"))
    assert parsed["entries"][0]["id"] == "kalgoorlie_phase1"

    proc2 = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "verify_trinity_registry.py"),
            str(out_json),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    assert "[verify] OK" in proc2.stdout
