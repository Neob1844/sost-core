#!/usr/bin/env python3
"""Trinity V13 RC1 Binary Preflight v0.1.

Read-only preflight checker for cutting V13 RC1 binaries on the
operator's own machine. Inspects git HEAD, validates the three V13
config files (binary preflight + activation + release candidate),
re-runs v13_readiness_check and v13_release_candidate_check
in-process, optionally runs the full Trinity pytest suite and a
short list of allow-listed ctest binaries, computes SHA-256 for
any binaries it finds in --build-dir, and writes a JSON + Markdown
report (plus an optional SHA256SUMS file).

READ-ONLY observer:

    - NEVER touches a wallet
    - NEVER touches a private key
    - NEVER signs anything
    - NEVER broadcasts
    - NEVER uploads or publishes a release
    - NEVER opens the network
    - NEVER calls the GitHub API
    - NEVER deploys (to Ethereum or anywhere)
    - NEVER mutates git state (no push, no merge, no tag)
    - NEVER invokes cmake or make (the operator builds manually)

Subprocess is used ONLY with argv-list calls and ONLY against a
hard allow-list:

    - git rev-parse / status / diff / log / branch / ls-files / rev-list
    - python -m pytest <target> (when --run-tests is passed)
    - ctest -R <name> (when --run-ctest is passed)

Shell-string subprocess invocation is forbidden in source. SHA-256 over binaries uses
``hashlib`` directly (no shelling out to ``sha256sum``).

Usage:
    python3 scripts/trinity/v13_binary_preflight.py \\
        --repo-root  /opt/sost \\
        --build-dir  /opt/sost/build-v13-rc1 \\
        --out-dir    /tmp/sost-v13-binary-preflight \\
        --pinned-time 2026-05-18T14:00:00+00:00 \\
        [--require-binaries] [--run-tests] [--run-ctest] [--write-sha256sums]

Exit codes:
    0 - ready_to_build true (configs OK, gates open) AND
        (if --require-binaries) all 3 binaries present AND
        (if --run-tests)        pytest rc == 0 AND
        (if --run-ctest)        every required ctest passed
    1 - any of the above failed
    2 - usage / setup error (bad repo-root, unreadable config)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_REPORT = "trinity-v13-binary-preflight-report/v0.1"
SCHEMA_CONFIG = "sost-v13-binary-preflight/v0.1"

CONFIG_REL_PATH                = "config/v13_binary_preflight.json"
ACTIVATION_CONFIG_REL_PATH     = "config/v13_activation.json"
RC_CONFIG_REL_PATH             = "config/v13_release_candidate.json"

# Read-only git verbs the script is allowed to invoke.
ALLOWED_GIT_VERBS = (
    "rev-parse",
    "status",
    "diff",
    "log",
    "branch",
    "ls-files",
    "rev-list",
    "merge-base",
)


class PreflightError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _read_text(p: Path) -> Optional[str]:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(path))


# ---------------------------------------------------------------------------
# Subprocess helpers (argv-only, allow-listed)
# ---------------------------------------------------------------------------


def _run_git(args: List[str], cwd: Path, *, allow_fail: bool = False):
    """Argv-list git invocation. Refuses any verb outside
    ALLOWED_GIT_VERBS. Never uses shell-string mode."""
    if not args:
        raise PreflightError("git invoked with no args")
    verb = args[0]
    if verb not in ALLOWED_GIT_VERBS:
        raise PreflightError(
            "git verb " + repr(verb) + " is not in the read-only "
            "allow-list " + repr(ALLOWED_GIT_VERBS)
        )
    import subprocess  # noqa: PLC0415 - localised so static greps that
    # forbid module-level subprocess imports stay simple to express.
    proc = subprocess.run(  # noqa: S603
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if proc.returncode != 0 and not allow_fail:
        raise PreflightError(
            "git " + " ".join(args) + " failed (rc="
            + str(proc.returncode) + "): "
            + (proc.stderr or "").strip()[:300]
        )
    return proc


def _run_pytest(target: str, cwd: Path) -> Dict[str, Any]:
    import subprocess
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", target, "-q", "--tb=no"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    passed = failed = skipped = errors = 0
    summary_line = ""
    for line in reversed(
        [ln for ln in proc.stdout.splitlines() if ln.strip()]
    ):
        if "passed" in line or "failed" in line or "error" in line:
            summary_line = line.strip()
            break
    for m in re.finditer(
        r"(\d+)\s+(passed|failed|skipped|errors?)", summary_line,
    ):
        n = int(m.group(1))
        k = m.group(2)
        if k == "passed":
            passed = n
        elif k == "failed":
            failed = n
        elif k == "skipped":
            skipped = n
        elif k.startswith("error"):
            errors = n
    return {
        "ran":         True,
        "target":      target,
        "returncode":  int(proc.returncode),
        "passed":      passed,
        "failed":      failed,
        "skipped":     skipped,
        "errors":      errors,
        "summary":     summary_line[:300],
    }


def _run_ctest(test_name: str, build_dir: Path) -> Dict[str, Any]:
    """Run one ctest by exact name from the build dir. Returns
    {ran, returncode, status}."""
    if not build_dir.is_dir():
        return {
            "ran":        False,
            "returncode": -1,
            "status":     "missing",
        }
    if not re.match(r"^[A-Za-z0-9._-]+$", test_name):
        return {
            "ran":        False,
            "returncode": -1,
            "status":     "fail",
        }
    import subprocess
    proc = subprocess.run(  # noqa: S603
        ["ctest", "-R", "^" + test_name + "$", "--output-on-failure"],
        cwd=str(build_dir),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if proc.returncode == 0:
        return {
            "ran":        True,
            "returncode": 0,
            "status":     "pass",
        }
    # ctest returns non-zero on missing test, too — distinguish by
    # checking stdout for "No tests were found".
    out = (proc.stdout or "") + (proc.stderr or "")
    if "No tests were found" in out or "Test not available" in out:
        return {
            "ran":        False,
            "returncode": int(proc.returncode),
            "status":     "missing",
        }
    return {
        "ran":        True,
        "returncode": int(proc.returncode),
        "status":     "fail",
    }


# ---------------------------------------------------------------------------
# Git probes (read-only)
# ---------------------------------------------------------------------------


def _git_head_commit(repo_root: Path) -> str:
    return _run_git(["rev-parse", "HEAD"], repo_root).stdout.strip()


def _git_current_branch(repo_root: Path) -> str:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)\
        .stdout.strip()


def _git_tracked_dirty(repo_root: Path) -> bool:
    out = _run_git(["status", "--porcelain"], repo_root).stdout
    for line in out.splitlines():
        if not line:
            continue
        if line.startswith("??"):
            continue
        return True
    return False


# Hex-only check for the configured min_commit. We never pass the
# config value directly to a subprocess until it has cleared this
# regex — guards against accidental option-injection if the config
# is ever sourced from an untrusted file.
_MIN_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _git_resolve_commit(
    repo_root: Path, commit_ish: str,
) -> Optional[str]:
    """Return the full 40-hex SHA for a short / long commit, or
    None if git cannot resolve it. Uses `git rev-parse --verify
    <commit>^{commit}` so we only accept things that already
    exist in this repo's history."""
    if not _MIN_COMMIT_RE.match(commit_ish or ""):
        return None
    proc = _run_git(
        ["rev-parse", "--verify", "--quiet",
         commit_ish + "^{commit}"],
        repo_root,
        allow_fail=True,
    )
    sha = proc.stdout.strip()
    if proc.returncode != 0 or len(sha) != 40:
        return None
    return sha.lower()


def _git_is_ancestor(
    repo_root: Path, ancestor_sha: str, head_sha: str,
) -> bool:
    """Returns True iff `ancestor_sha` is reachable from
    `head_sha` (i.e. `git merge-base --is-ancestor` returns rc=0).
    Both arguments MUST be full 40-hex SHAs that already pass
    _git_resolve_commit; we re-validate to be paranoid."""
    if not (
        re.fullmatch(r"[0-9a-f]{40}", ancestor_sha or "")
        and re.fullmatch(r"[0-9a-f]{40}", head_sha or "")
    ):
        return False
    proc = _run_git(
        ["merge-base", "--is-ancestor", ancestor_sha, head_sha],
        repo_root,
        allow_fail=True,
    )
    # rc 0 = is ancestor; rc 1 = not ancestor; anything else = error.
    return proc.returncode == 0


def _head_matches_min_commit(
    repo_root: Path, head_commit: str, min_commit: str,
) -> Tuple[bool, str]:
    """Return (matches, reason). Semantics:
        1. min_commit empty               -> (False, "no min_commit configured")
        2. HEAD equals min_commit         -> (True, "head == min_commit")
        3. HEAD starts with min_commit    -> (True, "head matches min_commit prefix")
        4. min_commit resolves and is an
           ancestor of HEAD               -> (True, "min_commit is ancestor of HEAD")
        5. otherwise                       -> (False, ...)
    Cases 1 and 5 cause the script to record a warning.
    """
    mc = (min_commit or "").lower()
    hc = (head_commit or "").lower()
    if not mc:
        return False, "no min_commit configured"
    # Exact and prefix matches: we are exactly on the recorded
    # base commit (this is the common case for the released main
    # after merge + push).
    if hc == mc:
        return True, "HEAD == min_commit (exact match)"
    if mc and hc.startswith(mc):
        return True, "HEAD matches min_commit prefix"
    # Ancestry: feature branches built on top of the release base
    # are also valid runs of the preflight — they include all the
    # commits min_commit is supposed to pin.
    resolved = _git_resolve_commit(repo_root, mc)
    if resolved is None:
        return False, (
            "min_commit " + (mc[:16] or "(empty)")
            + " is not a known commit in this repo"
        )
    if _git_is_ancestor(repo_root, resolved, hc):
        return True, (
            "min_commit " + resolved[:16]
            + " is an ancestor of HEAD " + hc[:16]
        )
    return False, (
        "git HEAD " + hc[:16] + " is not at or after min_commit "
        + (mc[:16] or "(missing)")
        + " (min_commit is not reachable from HEAD ancestry)"
    )


# ---------------------------------------------------------------------------
# Sibling checker invocation (in-process, NOT via subprocess)
# ---------------------------------------------------------------------------


def _import_sibling(name: str, repo_root: Path):
    """Import a sibling Trinity checker (v13_readiness_check or
    v13_release_candidate_check) as a module so we can call its
    build_report() directly. This avoids subprocess and keeps the
    preflight in-process. Restricted to the two named modules."""
    if name not in (
        "v13_readiness_check",
        "v13_release_candidate_check",
    ):
        raise PreflightError(
            "refusing to import sibling " + repr(name)
        )
    scripts_dir = repo_root / "scripts" / "trinity"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import importlib.util
    src = scripts_dir / (name + ".py")
    if not src.is_file():
        raise PreflightError(
            "sibling " + name + " not found at " + str(src)
        )
    spec = importlib.util.spec_from_file_location(name, str(src))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(
    *,
    repo_root: Path,
    build_dir: Path,
    out_dir: Path,
    pinned_time: str,
    require_binaries: bool = False,
    run_tests: bool = False,
    run_ctest: bool = False,
    write_sha256sums: bool = False,
) -> Dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    build_dir = Path(build_dir)
    out_dir = Path(out_dir)
    if not repo_root.is_dir():
        raise PreflightError(
            "repo-root not a directory: " + str(repo_root)
        )

    config_path = repo_root / CONFIG_REL_PATH
    cfg = _read_json(config_path)
    cfg_loaded = cfg is not None
    if cfg is None:
        raise PreflightError(
            "config not loadable: " + str(config_path)
        )
    if cfg.get("schema") != SCHEMA_CONFIG:
        raise PreflightError(
            "config schema mismatch: " + repr(cfg.get("schema"))
        )

    warnings: List[str] = []

    # Git probes.
    head_commit    = _git_head_commit(repo_root)
    current_branch = _git_current_branch(repo_root)
    tracked_dirty  = _git_tracked_dirty(repo_root)
    min_commit     = str(cfg.get("min_commit", ""))
    head_matches_min_commit, head_match_reason = _head_matches_min_commit(
        repo_root, head_commit, min_commit,
    )
    if not head_matches_min_commit:
        warnings.append("min_commit check failed: " + head_match_reason)
    if tracked_dirty:
        warnings.append(
            "tracked tree is dirty; binaries built from a dirty tree "
            "MUST NOT be tagged as a release"
        )

    # Sibling configs presence (we only check load; the dedicated
    # sibling checkers validate the contents).
    activation_loaded = (
        repo_root / ACTIVATION_CONFIG_REL_PATH
    ).is_file()
    rc_loaded = (repo_root / RC_CONFIG_REL_PATH).is_file()
    if not activation_loaded:
        warnings.append("config/v13_activation.json missing")
    if not rc_loaded:
        warnings.append("config/v13_release_candidate.json missing")

    # In-process re-run of v13_readiness_check.
    try:
        readiness_mod = _import_sibling(
            "v13_readiness_check", repo_root,
        )
        readiness_report = readiness_mod.build_report(
            repo_root=repo_root, pinned_time=pinned_time,
        )
        readiness_ok = bool(
            readiness_report["v13_ready_for_confirmed_items"]
        )
        if not readiness_ok:
            warnings.append(
                "v13_readiness_check says confirmed items NOT ready"
            )
    except Exception as exc:  # noqa: BLE001 - defensive
        readiness_ok = False
        warnings.append(
            "v13_readiness_check raised: " + repr(exc)[:200]
        )

    # In-process re-run of v13_release_candidate_check.
    try:
        rc_mod = _import_sibling(
            "v13_release_candidate_check", repo_root,
        )
        rc_report = rc_mod.build_report(
            repo_root=repo_root, pinned_time=pinned_time,
        )
        rc_ok = bool(rc_report["rc_ready"])
        if not rc_ok:
            warnings.append(
                "v13_release_candidate_check says rc_ready=false"
            )
    except Exception as exc:  # noqa: BLE001
        rc_ok = False
        warnings.append(
            "v13_release_candidate_check raised: " + repr(exc)[:200]
        )

    # Binaries inspection.
    binaries_view: List[Dict[str, Any]] = []
    sha_lines: List[str] = []
    all_binaries_present = True
    for bin_spec in (cfg.get("required_binaries") or []):
        name = str(bin_spec.get("name", ""))
        rel  = str(bin_spec.get("relative_path", name))
        path = build_dir / rel
        if path.is_file():
            size = path.stat().st_size
            digest = _sha256_file(path)
            binaries_view.append({
                "name":       name,
                "present":    True,
                "size_bytes": int(size),
                "sha256":     digest,
            })
            sha_lines.append(digest + "  " + name)
        else:
            all_binaries_present = False
            binaries_view.append({
                "name":       name,
                "present":    False,
                "size_bytes": None,
                "sha256":     None,
            })

    if require_binaries and not all_binaries_present:
        warnings.append(
            "--require-binaries set but some required binaries are "
            "missing from " + str(build_dir.name)
        )

    # Tests (pytest).
    pytest_result = {
        "ran":        False,
        "target":     "tests/trinity/",
        "returncode": -1,
        "passed":     0,
        "failed":     0,
        "skipped":    0,
        "errors":     0,
        "summary":    "",
    }
    if run_tests:
        pytest_result = _run_pytest("tests/trinity/", repo_root)
        if pytest_result["failed"] > 0 or pytest_result["errors"] > 0 \
                or pytest_result["returncode"] != 0:
            warnings.append(
                "pytest tests/trinity/ failed: " + pytest_result["summary"]
            )

    # Tests (ctest).
    ctest_view: List[Dict[str, Any]] = []
    if run_ctest:
        for t in (cfg.get("required_tests") or []):
            if str(t.get("kind", "")) != "ctest":
                continue
            test_name = str(t.get("name", ""))
            test_id   = str(t.get("id", test_name))
            res = _run_ctest(test_name, build_dir)
            entry = {
                "id":         test_id,
                "name":       test_name,
                "ran":        bool(res.get("ran", False)),
                "returncode": int(res.get("returncode", -1)),
                "status":     str(res.get("status", "missing")),
            }
            ctest_view.append(entry)
            if entry["status"] == "fail":
                warnings.append(
                    "ctest " + test_name + " failed"
                )
            elif entry["status"] == "missing":
                warnings.append(
                    "ctest " + test_name
                    + " missing (build the corresponding target "
                    "with `make -j$(nproc) test-" + test_name
                    + "`)"
                )
    else:
        # When --run-ctest is OFF, still surface the expected list
        # with status="skipped" so the schema is satisfied.
        for t in (cfg.get("required_tests") or []):
            if str(t.get("kind", "")) != "ctest":
                continue
            test_name = str(t.get("name", ""))
            test_id   = str(t.get("id", test_name))
            ctest_view.append({
                "id":         test_id,
                "name":       test_name,
                "ran":        False,
                "returncode": -1,
                "status":     "skipped",
            })

    # SHA256SUMS write.
    out_dir.mkdir(parents=True, exist_ok=True)
    sums_written = False
    if write_sha256sums and sha_lines:
        sums_path = out_dir / "SHA256SUMS"
        sums_path.write_text(
            "\n".join(sorted(sha_lines)) + "\n",
            encoding="utf-8",
        )
        sums_written = True

    # Top-level booleans.
    ready_to_build = (
        cfg_loaded
        and activation_loaded
        and rc_loaded
        and readiness_ok
        and rc_ok
        and not tracked_dirty
        and head_matches_min_commit
    )
    ready_to_release = (
        ready_to_build
        and all_binaries_present
        and (
            (not run_tests)
            or (
                pytest_result.get("returncode") == 0
                and pytest_result.get("failed", 0) == 0
                and pytest_result.get("errors", 0) == 0
            )
        )
        and all(
            entry["status"] == "pass"
            for entry in ctest_view
            if entry["status"] != "skipped"
        )
    )

    if not ready_to_build:
        safety_status = "warning"
    elif warnings:
        safety_status = "warning"
    else:
        safety_status = "ok"

    report_id = "v13bpf-" + _sha16(_canonical_dumps({
        "pinned_time":       pinned_time,
        "preflight_id":      str(cfg.get("preflight_id", "")),
        "head_commit":       head_commit,
        "min_commit":        min_commit,
        "build_dir_basename": build_dir.name,
        "ready_to_build":    ready_to_build,
        "ready_to_release":  ready_to_release,
    }))

    return {
        "schema":              SCHEMA_REPORT,
        "report_id":           report_id,
        "pinned_time":         pinned_time,
        "preflight_id":        str(cfg.get(
            "preflight_id", "v13-rc1-preflight-v01")),
        "rc_id":               str(cfg.get("rc_id", "v13-rc1")),
        "repo_root_basename":  repo_root.name,
        "build_dir_basename":  build_dir.name,
        "git": {
            "head_commit":             head_commit,
            "head_commit_short":       head_commit[:16],
            "min_commit":              min_commit,
            "min_commit_short":        min_commit[:16],
            "head_matches_min_commit": head_matches_min_commit,
            "current_branch":          current_branch,
            "tracked_dirty":           tracked_dirty,
        },
        "configs": {
            "v13_binary_preflight_loaded":  cfg_loaded,
            "v13_activation_loaded":        activation_loaded,
            "v13_release_candidate_loaded": rc_loaded,
        },
        "binaries": binaries_view,
        "tests": {
            "pytest": pytest_result,
            "ctest":  {
                "ran":   bool(run_ctest),
                "tests": ctest_view,
            },
        },
        "options": {
            "require_binaries":  bool(require_binaries),
            "run_tests":         bool(run_tests),
            "run_ctest":         bool(run_ctest),
            "write_sha256sums":  bool(write_sha256sums),
        },
        "sha256sums_written":  bool(sums_written),
        "ready_to_build":      bool(ready_to_build),
        "ready_to_release":    bool(ready_to_release),
        "warnings":            warnings,
        "safety_status":       safety_status,
        "safety_flags": {
            "no_wallet_access":      True,
            "no_private_key_access": True,
            "no_signing":            True,
            "no_broadcast":          True,
            "no_release_upload":     True,
            "no_network_required":   True,
            "no_auto_restart":       True,
            "no_ethereum_deploy":    True,
            "no_destructive_git":    True,
            "no_shell_true":         True,
            "no_make_invocation":    True,
            "no_cmake_invocation":   True,
        },
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# Trinity V13 Binary Preflight Report")
    a("")
    a("**Report id:** `" + report["report_id"] + "`  ")
    a("**Pinned time:** `" + report["pinned_time"] + "`  ")
    a("**Preflight id:** `" + report["preflight_id"] + "`  ")
    a("**RC id:** `" + report["rc_id"] + "`  ")
    a("**Repo:** `" + report["repo_root_basename"] + "`  ")
    a("**Build dir:** `" + report["build_dir_basename"] + "`  ")
    a("**ready_to_build:** `"
      + ("true" if report["ready_to_build"] else "false") + "`  ")
    a("**ready_to_release:** `"
      + ("true" if report["ready_to_release"] else "false") + "`  ")
    a("**Safety status:** `" + report["safety_status"] + "`")
    a("")
    a("## Git")
    a("")
    g = report["git"]
    a("- HEAD:                       `" + g["head_commit_short"] + "`")
    a("- min_commit:                 `" + g["min_commit_short"] + "`")
    a("- head_matches_min_commit:    `"
      + ("yes" if g["head_matches_min_commit"] else "**NO**") + "`")
    a("- current branch:             `" + g["current_branch"] + "`")
    a("- tracked_dirty:              `"
      + ("yes" if g["tracked_dirty"] else "no") + "`")
    a("")
    a("## Configs")
    a("")
    for k in sorted(report["configs"].keys()):
        v = report["configs"][k]
        a("- `" + k + "`: " + ("yes" if v else "**NO**"))
    a("")
    a("## Binaries (in build_dir)")
    a("")
    a("| name | present | size | sha256 |")
    a("|---|---|---:|---|")
    for b in report["binaries"]:
        present = "yes" if b["present"] else "**NO**"
        size = (str(b["size_bytes"]) if b["size_bytes"] is not None
                else "_-_")
        sha = b["sha256"] if b["sha256"] else "_-_"
        a("| `" + b["name"] + "` | " + present + " | "
          + size + " | `" + (sha if sha == "_-_" else sha[:32] + "...") + "` |")
    a("")
    a("## Tests")
    a("")
    p = report["tests"]["pytest"]
    if p["ran"]:
        a("### pytest")
        a("")
        a("- target:     `" + p["target"] + "`")
        a("- returncode: `" + str(p["returncode"]) + "`")
        a(
            "- passed:     **" + str(p["passed"])
            + "**, failed: **" + str(p["failed"])
            + "**, skipped: **" + str(p["skipped"])
            + "**, errors: **" + str(p["errors"]) + "**"
        )
        if p["summary"]:
            a("- summary:    `" + p["summary"] + "`")
        a("")
    else:
        a("### pytest")
        a("")
        a("- _skipped — pass --run-tests to execute._")
        a("")
    a("### ctest")
    a("")
    c = report["tests"]["ctest"]
    a("- ran flag: `" + ("yes" if c["ran"] else "no (skipped)") + "`")
    if c["tests"]:
        a("")
        a("| id | name | ran | rc | status |")
        a("|---|---|---|---:|---|")
        for t in c["tests"]:
            a("| `" + t["id"] + "` | `" + t["name"] + "` | "
              + ("yes" if t["ran"] else "no") + " | "
              + str(t["returncode"]) + " | `" + t["status"] + "` |")
    a("")
    a("## Options")
    a("")
    o = report["options"]
    for k in sorted(o.keys()):
        a("- `" + k + "`: `" + ("on" if o[k] else "off") + "`")
    a("")
    a("- sha256sums written: `"
      + ("yes" if report["sha256sums_written"] else "no") + "`")
    a("")
    a("## Warnings")
    a("")
    if report["warnings"]:
        for w in report["warnings"]:
            a("- " + w)
    else:
        a("- _none_")
    a("")
    a("## Safety flags")
    a("")
    for k in sorted(report["safety_flags"].keys()):
        a(
            "- `" + k + "`: **"
            + ("true" if report["safety_flags"][k] else "false")
            + "**"
        )
    a("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v13_binary_preflight",
        description=(
            "Trinity V13 RC1 Binary Preflight v0.1. Read-only "
            "preflight for cutting V13 RC1 binaries locally. "
            "NEVER signs, NEVER broadcasts, NEVER uploads, "
            "NEVER touches a wallet, NEVER invokes cmake or make."
        ),
    )
    p.add_argument("--repo-root", required=True)
    p.add_argument("--build-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pinned-time", default=None)
    p.add_argument(
        "--require-binaries", action="store_true",
        help="Treat missing required binaries as a failure.",
    )
    p.add_argument(
        "--run-tests", action="store_true",
        help="Run the full Trinity pytest suite (tests/trinity/).",
    )
    p.add_argument(
        "--run-ctest", action="store_true",
        help="Run the allow-listed C++ ctest names from --build-dir.",
    )
    p.add_argument(
        "--write-sha256sums", action="store_true",
        help="Write a SHA256SUMS file to --out-dir with the "
             "checksum of every binary the preflight finds.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()

    try:
        report = build_report(
            repo_root=Path(args.repo_root),
            build_dir=Path(args.build_dir),
            out_dir=Path(args.out_dir),
            pinned_time=pinned,
            require_binaries=bool(args.require_binaries),
            run_tests=bool(args.run_tests),
            run_ctest=bool(args.run_ctest),
            write_sha256sums=bool(args.write_sha256sums),
        )
    except PreflightError as exc:
        print(
            "[v13_binary_preflight] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "report.json"
    out_md   = out_dir / "report.md"
    _atomic_write_json(out_json, report)
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        "[v13_binary_preflight] report_id=" + report["report_id"]
        + " preflight_id=" + report["preflight_id"]
        + " head_short=" + report["git"]["head_commit_short"]
        + " head_matches_min="
        + ("true" if report["git"]["head_matches_min_commit"] else "false")
        + " tracked_dirty="
        + ("true" if report["git"]["tracked_dirty"] else "false")
        + " ready_to_build="
        + ("true" if report["ready_to_build"] else "false")
        + " ready_to_release="
        + ("true" if report["ready_to_release"] else "false")
        + " safety_status=" + report["safety_status"]
        + " sha256sums="
        + ("yes" if report["sha256sums_written"] else "no")
        + " json=" + str(out_json)
        + " md=" + str(out_md)
    )

    # Exit-code contract:
    #   0 - ready_to_build (and all opt-in gates green)
    #   1 - any required check failed
    #   2 - setup error (handled above)
    ok = report["ready_to_build"]
    if args.require_binaries and not all(
        b["present"] for b in report["binaries"]
    ):
        ok = False
    if args.run_tests and (
        report["tests"]["pytest"]["returncode"] != 0
        or report["tests"]["pytest"]["failed"] > 0
        or report["tests"]["pytest"]["errors"] > 0
    ):
        ok = False
    if args.run_ctest and any(
        t["status"] == "fail" for t in report["tests"]["ctest"]["tests"]
    ):
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
