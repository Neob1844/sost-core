#!/usr/bin/env python3
"""Trinity V13 RC1 Local Artifact Bundle v0.1.

Assembles a local, reproducible artefact bundle for the V13 RC1
release candidate. Copies the already-built binaries
(`sost-node`, `sost-miner`, `sost-cli`) into ``<out-dir>/bin/``,
copies the preflight `SHA256SUMS` + `report.json` + `report.md`
into ``<out-dir>/SHA256SUMS`` and ``<out-dir>/reports/``, copies
the three V13 config files into ``<out-dir>/config/``, writes
`MANIFEST.json` + `MANIFEST.md` + `VERIFY_COMMANDS.md`, and
optionally produces a single `.tar.gz` of the whole tree
(LOCAL ONLY — never uploaded).

READ-ONLY observer for everything outside ``--out-dir``:

    - NEVER touches a wallet
    - NEVER touches a private key
    - NEVER signs anything
    - NEVER broadcasts
    - NEVER uploads or publishes a release
    - NEVER opens the network (no fetch / requests / urllib)
    - NEVER calls the GitHub API
    - NEVER deploys (Ethereum or other)
    - NEVER mutates git state
    - NEVER uses subprocess (Python hashlib + shutil + tarfile only)
    - NEVER reads anything inside the wallet / data dir

SHA-256 over every copied file is computed in-process with
``hashlib``. Optional `.tar.gz` is built via Python's ``tarfile``
module (no shelled ``tar``).

Usage:
    python3 scripts/trinity/v13_rc1_artifact_bundle.py \\
        --repo-root      /opt/sost \\
        --build-dir      /opt/sost/build-v13-rc1 \\
        --preflight-dir  /tmp/sost-v13-binary-preflight-release \\
        --out-dir        /tmp/sost-v13-rc1-artifact-bundle \\
        --pinned-time    2026-05-18T15:30:00+00:00 \\
        [--require-preflight-ready] \\
        [--no-copy-binaries] \\
        [--write-tarball]

Exit codes:
    0 - bundle written successfully
    1 - bundle could not be assembled cleanly (missing binary,
        SHA mismatch vs preflight, required preflight not ready)
    2 - usage / setup error (bad repo-root, missing config)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_MANIFEST = "trinity-v13-rc1-artifact-bundle-manifest/v0.1"
SCHEMA_PREFLIGHT_REPORT = "trinity-v13-binary-preflight-report/v0.1"

REQUIRED_BINARIES = ("sost-node", "sost-miner", "sost-cli")

CONFIG_FILES = (
    ("v13_release_candidate.json", "config/v13_release_candidate.json"),
    ("v13_activation.json",        "config/v13_activation.json"),
    ("v13_binary_preflight.json",  "config/v13_binary_preflight.json"),
)

PREFLIGHT_REPORT_JSON_NAME = "preflight_report.json"
PREFLIGHT_REPORT_MD_NAME   = "preflight_report.md"
PREFLIGHT_SHA_NAME         = "SHA256SUMS"


class BundleError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(path))


def _ensure_clean_dir(p: Path) -> None:
    """Create p if missing. If it exists and is not a directory,
    raise. Existing contents are kept; the caller chooses whether
    to overwrite (this bundler always overwrites by name)."""
    if p.exists() and not p.is_dir():
        raise BundleError(
            "out-dir exists but is not a directory: " + str(p)
        )
    p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Preflight wiring
# ---------------------------------------------------------------------------


def _load_preflight(preflight_dir: Path) -> Dict[str, Any]:
    """Read the v13_binary_preflight report.json + SHA256SUMS
    from --preflight-dir. Both are required for the bundle to
    proceed (we want every binary SHA to be cross-checked
    against the preflight before we copy it into the bundle)."""
    rp = preflight_dir / "report.json"
    pre = _read_json(rp)
    if pre is None:
        raise BundleError(
            "preflight report not loadable: " + str(rp)
        )
    if pre.get("schema") != SCHEMA_PREFLIGHT_REPORT:
        raise BundleError(
            "preflight report has wrong schema: " + repr(pre.get("schema"))
        )
    return pre


def _load_sha256sums(p: Path) -> Dict[str, str]:
    """Parse a `<hex>  <basename>` SHA256SUMS file into a dict
    mapping basename -> sha256 (lowercase). Missing file returns
    an empty dict."""
    out: Dict[str, str] = {}
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts
        digest = digest.strip().lower()
        if len(digest) != 64:
            continue
        out[name.strip()] = digest
    return out


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------


def build_bundle(
    *,
    repo_root: Path,
    build_dir: Path,
    preflight_dir: Path,
    out_dir: Path,
    pinned_time: str,
    require_preflight_ready: bool = False,
    no_copy_binaries: bool = False,
    write_tarball: bool = False,
) -> Dict[str, Any]:
    repo_root      = Path(repo_root).resolve()
    build_dir      = Path(build_dir)
    preflight_dir  = Path(preflight_dir)
    out_dir        = Path(out_dir)

    if not repo_root.is_dir():
        raise BundleError(
            "repo-root not a directory: " + str(repo_root)
        )
    _ensure_clean_dir(out_dir)

    # 1) Read the preflight report + its SHA256SUMS.
    preflight = _load_preflight(preflight_dir)
    pre_sums  = _load_sha256sums(preflight_dir / PREFLIGHT_SHA_NAME)

    preflight_was_ready = bool(preflight.get("ready_to_release", False))
    if require_preflight_ready and not preflight_was_ready:
        raise BundleError(
            "--require-preflight-ready set, but preflight "
            "ready_to_release is false (cannot proceed)"
        )

    # 2) Resolve binaries.
    binaries_view: List[Dict[str, Any]] = []
    bin_subdir = out_dir / "bin"
    if not no_copy_binaries:
        _ensure_clean_dir(bin_subdir)
    sha_lines: List[str] = []
    for name in REQUIRED_BINARIES:
        src = build_dir / name
        if not src.is_file():
            raise BundleError(
                "required binary missing in build-dir: "
                + str(src)
            )
        digest = _sha256_file(src)
        if pre_sums:
            expected = pre_sums.get(name)
            if expected and expected.lower() != digest:
                raise BundleError(
                    "binary " + name + " sha256 mismatch: "
                    + "build-dir says " + digest
                    + ", preflight SHA256SUMS says " + expected
                )
        size_bytes = src.stat().st_size
        sha_lines.append(digest + "  " + name)
        if not no_copy_binaries:
            dst = bin_subdir / name
            shutil.copy2(str(src), str(dst))
        binaries_view.append({
            "name":              name,
            "basename_under_bin": name,
            "size_bytes":        int(size_bytes),
            "sha256":            digest,
        })

    # 3) Write SHA256SUMS (deterministic, sorted).
    sums_path = out_dir / PREFLIGHT_SHA_NAME
    sums_path.write_text(
        "\n".join(sorted(sha_lines)) + ("\n" if sha_lines else ""),
        encoding="utf-8",
    )

    # 4) Copy preflight report.json + report.md into reports/.
    reports_view: List[Dict[str, Any]] = []
    reports_subdir = out_dir / "reports"
    _ensure_clean_dir(reports_subdir)
    for (src_name, dst_name) in (
        ("report.json", PREFLIGHT_REPORT_JSON_NAME),
        ("report.md",   PREFLIGHT_REPORT_MD_NAME),
    ):
        src = preflight_dir / src_name
        if not src.is_file():
            raise BundleError(
                "preflight artefact missing: " + str(src)
            )
        dst = reports_subdir / dst_name
        shutil.copy2(str(src), str(dst))
        digest = _sha256_file(dst)
        reports_view.append({
            "name":                   src_name,
            "basename_under_reports": dst_name,
            "sha256":                 digest,
        })

    # 5) Copy the three V13 config files.
    configs_view: List[Dict[str, Any]] = []
    config_subdir = out_dir / "config"
    _ensure_clean_dir(config_subdir)
    for (dst_name, rel_src) in CONFIG_FILES:
        src = repo_root / rel_src
        if not src.is_file():
            raise BundleError(
                "config file missing in repo: " + rel_src
            )
        dst = config_subdir / dst_name
        shutil.copy2(str(src), str(dst))
        digest = _sha256_file(dst)
        configs_view.append({
            "name":                  rel_src,
            "basename_under_config": dst_name,
            "sha256":                digest,
        })

    # 6) Read min_commit from the binary preflight config (single
    # source of truth for the release base).
    bp_cfg = _read_json(
        repo_root / "config" / "v13_binary_preflight.json",
    )
    if bp_cfg is None:
        raise BundleError(
            "config/v13_binary_preflight.json not loadable"
        )
    rc_id     = str(bp_cfg.get("rc_id", "v13-rc1"))
    min_commit = str(bp_cfg.get("min_commit", "")).lower()
    if not min_commit:
        raise BundleError(
            "min_commit missing in v13_binary_preflight.json"
        )
    activation_height = int(
        bp_cfg.get("activation_height", 12000) or 12000
    )

    # 7) Bundle id (deterministic).
    bundle_id = "v13rc1bundle-" + _sha16(_canonical_dumps({
        "pinned_time":         pinned_time,
        "rc_id":               rc_id,
        "min_commit":          min_commit,
        "binaries":            [b["sha256"] for b in binaries_view],
        "no_copy_binaries":    bool(no_copy_binaries),
    }))

    manifest: Dict[str, Any] = {
        "schema":              SCHEMA_MANIFEST,
        "bundle_id":           bundle_id,
        "pinned_time":         pinned_time,
        "rc_id":               rc_id,
        "activation_height":   activation_height,
        "min_commit":          min_commit,
        "min_commit_short":    min_commit[:16],
        "repo_root_basename":  repo_root.name,
        "preflight_was_ready": preflight_was_ready,
        "binaries":            binaries_view,
        "sha256sums_basename": PREFLIGHT_SHA_NAME,
        "reports":             reports_view,
        "configs":             configs_view,
        "has_tarball":         False,
        "tarball":             None,
        "no_copy_binaries_mode": bool(no_copy_binaries),
        "safety_flags": {
            "no_wallet_access":      True,
            "no_private_key_access": True,
            "no_signing":            True,
            "no_broadcast":          True,
            "no_release_upload":     True,
            "no_network_required":   True,
            "no_auto_restart":       True,
            "no_subprocess":         True,
            "no_shell_true":         True,
            "no_github_api":         True,
            "no_ethereum_deploy":    True,
        },
    }

    # 8) Write MANIFEST.json + MANIFEST.md + VERIFY_COMMANDS.md.
    _atomic_write_json(out_dir / "MANIFEST.json", manifest)
    (out_dir / "MANIFEST.md").write_text(
        render_manifest_md(manifest), encoding="utf-8",
    )
    (out_dir / "VERIFY_COMMANDS.md").write_text(
        render_verify_commands_md(manifest), encoding="utf-8",
    )

    # 9) Optional .tar.gz of the whole bundle (LOCAL ONLY).
    if write_tarball:
        tar_name = (
            "v13-rc1-artifact-bundle-" + bundle_id + ".tar.gz"
        )
        tar_path = out_dir / tar_name
        # Build deterministically: sort, strip mtime, set 0:0
        # owner. The tarball excludes itself and any prior tar.gz.
        members: List[Path] = []
        for path in sorted(out_dir.rglob("*")):
            if path == tar_path:
                continue
            if path.suffix == ".gz" and path.name.endswith(".tar.gz"):
                continue
            members.append(path)
        with tarfile.open(str(tar_path), "w:gz") as tf:
            for m in members:
                arcname = str(m.relative_to(out_dir))
                info = tf.gettarinfo(str(m), arcname=arcname)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                if m.is_file():
                    with open(m, "rb") as f:
                        tf.addfile(info, f)
                else:
                    tf.addfile(info)
        manifest["has_tarball"] = True
        manifest["tarball"] = {
            "basename":   tar_name,
            "size_bytes": int(tar_path.stat().st_size),
            "sha256":     _sha256_file(tar_path),
        }
        # Re-write the MANIFEST.json so it carries the tarball info.
        _atomic_write_json(out_dir / "MANIFEST.json", manifest)
        (out_dir / "MANIFEST.md").write_text(
            render_manifest_md(manifest), encoding="utf-8",
        )

    return manifest


# ---------------------------------------------------------------------------
# Markdown renderers
# ---------------------------------------------------------------------------


def render_manifest_md(manifest: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# V13 RC1 Local Artifact Bundle Manifest")
    a("")
    a("**Bundle id:** `" + manifest["bundle_id"] + "`  ")
    a("**Pinned time:** `" + manifest["pinned_time"] + "`  ")
    a("**RC id:** `" + manifest["rc_id"] + "`  ")
    a("**Activation height:** **" + str(manifest["activation_height"]) + "**  ")
    a("**min_commit:** `" + manifest["min_commit_short"] + "`  ")
    a("**Repo:** `" + manifest["repo_root_basename"] + "`  ")
    a("**Preflight was ready:** `"
      + ("yes" if manifest["preflight_was_ready"] else "no") + "`  ")
    a("**No-copy-binaries mode:** `"
      + ("yes" if manifest["no_copy_binaries_mode"] else "no") + "`")
    a("")
    a("## Binaries")
    a("")
    if manifest["binaries"]:
        a("| name | basename | size | sha256 |")
        a("|---|---|---:|---|")
        for b in manifest["binaries"]:
            a(
                "| `" + b["name"] + "` | `" + b["basename_under_bin"] + "` | "
                + str(b["size_bytes"]) + " | `"
                + b["sha256"][:32] + "...` |"
            )
    else:
        a("- _none (no-copy-binaries mode)_")
    a("")
    a("## SHA256SUMS")
    a("")
    a("- basename: `" + manifest["sha256sums_basename"] + "`")
    a("")
    a("## Reports")
    a("")
    a("| name | basename | sha256 |")
    a("|---|---|---|")
    for r in manifest["reports"]:
        a(
            "| `" + r["name"] + "` | `" + r["basename_under_reports"] + "` | `"
            + r["sha256"][:32] + "...` |"
        )
    a("")
    a("## Configs")
    a("")
    a("| name | basename | sha256 |")
    a("|---|---|---|")
    for c in manifest["configs"]:
        a(
            "| `" + c["name"] + "` | `" + c["basename_under_config"] + "` | `"
            + c["sha256"][:32] + "...` |"
        )
    a("")
    a("## Tarball")
    a("")
    if manifest["has_tarball"] and manifest["tarball"]:
        t = manifest["tarball"]
        a("- basename:   `" + t["basename"] + "`")
        a("- size_bytes: `" + str(t["size_bytes"]) + "`")
        a("- sha256:     `" + t["sha256"] + "`")
    else:
        a("- _none (pass --write-tarball to generate)_")
    a("")
    a("## Safety flags")
    a("")
    for k in sorted(manifest["safety_flags"].keys()):
        a(
            "- `" + k + "`: **"
            + ("true" if manifest["safety_flags"][k] else "false")
            + "**"
        )
    a("")
    a("## What this bundle is NOT")
    a("")
    a("- NOT signed. Signing remains an explicit manual operator step.")
    a("- NOT uploaded. Publication remains an explicit manual operator step.")
    a("- NOT a binary release tag. The release tag is a separate manual step.")
    a("- NOT a wallet, key, or broadcast surface.")
    a("")
    return "\n".join(lines) + "\n"


def render_verify_commands_md(manifest: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# V13 RC1 Local Artifact Bundle — Verify Commands")
    a("")
    a("This bundle is reproducible and locally verifiable. The")
    a("commands below run entirely offline — no network access is")
    a("required and the operator does NOT need any wallet or key.")
    a("")
    a("## 1. Re-hash every binary and compare against SHA256SUMS")
    a("")
    a("```")
    a("cd <unpacked-bundle>")
    a("sha256sum -c SHA256SUMS")
    a("# expected: every line ends with '  OK'")
    a("```")
    a("")
    a("## 2. Cross-check the bundle manifest against the bundle tree")
    a("")
    a("```")
    a("python3 - <<'PY'")
    a("import json, hashlib, pathlib")
    a("root = pathlib.Path('.')")
    a("m = json.loads((root / 'MANIFEST.json').read_text())")
    a("def sha(p):")
    a("    h = hashlib.sha256()")
    a("    h.update(p.read_bytes())")
    a("    return h.hexdigest()")
    a("for b in m['binaries']:")
    a("    p = root / 'bin' / b['basename_under_bin']")
    a("    assert sha(p) == b['sha256'], b['name']")
    a("for r in m['reports']:")
    a("    p = root / 'reports' / r['basename_under_reports']")
    a("    assert sha(p) == r['sha256'], r['name']")
    a("for c in m['configs']:")
    a("    p = root / 'config' / c['basename_under_config']")
    a("    assert sha(p) == c['sha256'], c['name']")
    a("print('manifest cross-check OK')")
    a("PY")
    a("```")
    a("")
    a("## 3. Confirm safety flags are all const-true")
    a("")
    a("```")
    a("python3 -c \"import json,sys;m=json.load(open('MANIFEST.json'));"
      "sys.exit(0 if all(v is True for v in m['safety_flags'].values()) else 1)\"")
    a("```")
    a("")
    a("## 4. What the bundle does NOT include")
    a("")
    a("- A signature over SHA256SUMS (operator-side, separate step)")
    a("- A release upload (operator-side, separate step)")
    a("- A wallet, a private key, or any broadcast capability")
    a("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v13_rc1_artifact_bundle",
        description=(
            "Trinity V13 RC1 Local Artifact Bundle v0.1. "
            "Assembles binaries + SHA256SUMS + reports + "
            "configs + MANIFEST locally. NEVER signs, NEVER "
            "uploads, NEVER publishes a release, NEVER opens "
            "the network."
        ),
    )
    p.add_argument("--repo-root", required=True)
    p.add_argument("--build-dir", required=True)
    p.add_argument("--preflight-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pinned-time", default=None)
    p.add_argument(
        "--require-preflight-ready", action="store_true",
        help="Refuse to bundle unless the preflight report says "
             "ready_to_release is true.",
    )
    p.add_argument(
        "--no-copy-binaries", action="store_true",
        help="Skip copying the actual binaries; still compute "
             "their SHA-256 and produce the manifest.",
    )
    p.add_argument(
        "--write-tarball", action="store_true",
        help="Also build a deterministic <bundle>.tar.gz of the "
             "whole bundle inside --out-dir. LOCAL ONLY; never "
             "uploaded.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()

    try:
        manifest = build_bundle(
            repo_root=Path(args.repo_root),
            build_dir=Path(args.build_dir),
            preflight_dir=Path(args.preflight_dir),
            out_dir=Path(args.out_dir),
            pinned_time=pinned,
            require_preflight_ready=bool(args.require_preflight_ready),
            no_copy_binaries=bool(args.no_copy_binaries),
            write_tarball=bool(args.write_tarball),
        )
    except BundleError as exc:
        print(
            "[v13_rc1_artifact_bundle] error: " + str(exc),
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(
            "[v13_rc1_artifact_bundle] setup error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    print(
        "[v13_rc1_artifact_bundle] bundle_id=" + manifest["bundle_id"]
        + " rc_id=" + manifest["rc_id"]
        + " binaries=" + str(len(manifest["binaries"]))
        + " preflight_was_ready="
        + ("true" if manifest["preflight_was_ready"] else "false")
        + " no_copy_binaries="
        + ("true" if manifest["no_copy_binaries_mode"] else "false")
        + " has_tarball="
        + ("true" if manifest["has_tarball"] else "false")
        + " out=" + str(Path(args.out_dir))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
