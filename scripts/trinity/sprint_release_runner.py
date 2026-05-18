#!/usr/bin/env python3
"""Trinity Sprint Release Runner v0.1 (Sprint 5.40).

Local preflight verifier. Inspects the repo state, runs tests,
optionally walks a demo directory to find Trinity artifacts by
schema content, and emits a single JSON + Markdown release
readiness report. The runner is a READ-ONLY observer:

    - NEVER pushes
    - NEVER merges
    - NEVER tags
    - NEVER touches a wallet
    - NEVER signs anything
    - NEVER broadcasts
    - NEVER opens the network
    - NEVER uses GitHub API

It uses ``subprocess`` ONLY with argv lists and ONLY for read-only
git plumbing commands (``rev-parse``, ``status``, ``diff``,
``log``, ``branch``) plus the pytest invocation. Shell-string
invocation is forbidden statically; destructive git verbs (``push``,
``merge``, ``tag``, ``reset --hard``, ``checkout -- <file>``) are
forbidden statically.

Usage:
    python3 scripts/trinity/sprint_release_runner.py verify \\
        --repo-root /opt/sost \\
        --sprint-id sprint-5.40 \\
        --branch trinity/sprint-release-runner-v01 \\
        --base-ref main \\
        --out-json /tmp/trinity-5-40-release/report.json \\
        --out-md   /tmp/trinity-5-40-release/report.md \\
        --pinned-time 2026-05-18T00:10:00+00:00

Optional flags:
    --pytest-target tests/trinity/
    --demo-root     /tmp/trinity-5-37-39-final-v3
    --require-clean-tracked-tree
    --allow-untracked

Exit codes:
    0 - report written, ready_to_release true
    1 - report written, ready_to_release false (warnings recorded)
    2 - usage / setup error (bad branch, unreadable repo, etc.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_RELEASE_REPORT = "trinity-sprint-release-report/v0.1"

# Known Trinity artifact schemas the runner can recognise. The
# value is the artifact_type used in the report.
KNOWN_ARTIFACT_SCHEMAS: Dict[str, str] = {
    "trinity-task-queue-autopilot-report/v0.1": "autopilot_report",
    "trinity-task-queue-dashboard/v0.1":         "dashboard",
    "trinity-daily-report/v0.1":                 "daily_report",
    "trinity-worker-trial-pack-manifest/v0.1":   "trial_pack_manifest",
}

ARTIFACT_TYPES = sorted(set(KNOWN_ARTIFACT_SCHEMAS.values()))


class ReleaseRunnerError(Exception):
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


def _safe_basename(s: Optional[str]) -> str:
    if s is None or not isinstance(s, str) or not s:
        return ""
    name = os.path.basename(s)
    return name or ""


# ---------------------------------------------------------------------------
# Argv-only git plumbing (read-only commands only)
# ---------------------------------------------------------------------------
#
# We allow exactly these git verbs, all read-only:
#     rev-parse, status, diff, log, branch, ls-files
# Any other git verb is rejected at call time. Shell-string
# invocation is never used. A static safety test asserts the
# destructive verbs
# (push, merge, tag, reset, checkout) never appear in source.

ALLOWED_GIT_VERBS = (
    "rev-parse",
    "status",
    "diff",
    "log",
    "branch",
    "ls-files",
    "rev-list",
)


def _run_git(
    args: List[str],
    cwd: Path,
    *,
    allow_fail: bool = False,
) -> "subprocess.CompletedProcess[str]":
    if not args:
        raise ReleaseRunnerError("git invoked with no args")
    verb = args[0]
    if verb not in ALLOWED_GIT_VERBS:
        raise ReleaseRunnerError(
            "git verb " + repr(verb) + " not in read-only allow-list "
            + repr(ALLOWED_GIT_VERBS)
        )
    proc = subprocess.run(  # noqa: S603 - argv list, no shell
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if proc.returncode != 0 and not allow_fail:
        raise ReleaseRunnerError(
            "git " + " ".join(args) + " failed (rc="
            + str(proc.returncode) + "): "
            + (proc.stderr or "").strip()[:300]
        )
    return proc


# ---------------------------------------------------------------------------
# Git probes
# ---------------------------------------------------------------------------


def _git_current_branch(repo_root: Path) -> str:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)\
        .stdout.strip()


def _git_head_commit(repo_root: Path) -> str:
    return _run_git(["rev-parse", "HEAD"], repo_root).stdout.strip()


def _git_ref_commit(repo_root: Path, ref: str) -> str:
    return _run_git(["rev-parse", ref], repo_root).stdout.strip()


def _git_tracked_dirty(repo_root: Path) -> bool:
    # `git status --porcelain` lists every untracked + every modified.
    # We split: tracked-dirty means anything NOT prefixed by '??'.
    out = _run_git(["status", "--porcelain"], repo_root).stdout
    for line in out.splitlines():
        if not line:
            continue
        if line.startswith("??"):
            continue
        return True
    return False


def _git_untracked_files(repo_root: Path) -> List[str]:
    out = _run_git(["status", "--porcelain"], repo_root).stdout
    untracked: List[str] = []
    for line in out.splitlines():
        if line.startswith("??"):
            # `?? <path>` - the path always starts at col 3.
            untracked.append(line[3:].strip())
    return untracked


def _git_changed_files_vs_base(
    repo_root: Path, base_ref: str,
) -> List[Dict[str, Any]]:
    """Return [{path, status, additions, deletions}] for files
    that differ from base_ref in HEAD."""
    proc = _run_git(
        ["diff", "--numstat", base_ref + "..HEAD"],
        repo_root,
        allow_fail=True,
    )
    if proc.returncode != 0:
        # base_ref unreachable; we don't crash — the caller
        # captures this as a warning.
        return []
    changed: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        adds_s, dels_s, path = parts
        try:
            adds = -1 if adds_s == "-" else int(adds_s)
            dels = -1 if dels_s == "-" else int(dels_s)
        except ValueError:
            adds = -1
            dels = -1
        changed.append({
            "path": path,
            "status": "modified",  # numstat doesn't disambiguate
            "additions": adds,
            "deletions": dels,
        })
    return changed


def _git_commits_ahead(
    repo_root: Path, base_ref: str,
) -> List[Dict[str, Any]]:
    """Return summarised commits in HEAD that are not in base_ref.
    Capped at 50 entries to keep the report bounded."""
    proc = _run_git(
        ["log", "--pretty=%H %s", base_ref + "..HEAD"],
        repo_root,
        allow_fail=True,
    )
    if proc.returncode != 0:
        return []
    out: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines()[:50]:
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        sha, subject = parts
        if len(sha) >= 7:
            out.append({
                "sha_short": sha[:16],
                "subject": subject[:200],
            })
    return out


# ---------------------------------------------------------------------------
# Pytest runner (argv-list subprocess, no shell)
# ---------------------------------------------------------------------------


_PYTEST_SUMMARY_RE = re.compile(
    r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+skipped|(\d+)\s+errors?",
)


def _run_pytest(target: str, cwd: Path) -> Dict[str, Any]:
    proc = subprocess.run(  # noqa: S603 - argv list, no shell
        [sys.executable, "-m", "pytest", target, "-q", "--tb=no"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    passed = failed = skipped = errors = 0
    summary_line = ""
    # The last non-empty line of pytest -q output usually carries
    # the summary (e.g. "1474 passed, 38 skipped in 8.81s").
    for line in reversed(
        [ln for ln in proc.stdout.splitlines() if ln.strip()]
    ):
        if "passed" in line or "failed" in line or "error" in line:
            summary_line = line.strip()
            break
    # Parse counts. The regex finds digit-keyword pairs anywhere.
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


# ---------------------------------------------------------------------------
# Demo-artifact discovery (by schema content, not by filename)
# ---------------------------------------------------------------------------


def _safe_load_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _summarise_artifact(
    artifact_type: str, obj: Dict[str, Any],
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    if artifact_type == "autopilot_report":
        summary["autopilot_id"] = str(obj.get("autopilot_id", ""))[:64]
        summary["batches_attempted"] = int(
            obj.get("batches_attempted", 0) or 0,
        )
        summary["items_completed"] = int(
            obj.get("items_completed", 0) or 0,
        )
        summary["items_failed"] = int(
            obj.get("items_failed", 0) or 0,
        )
        summary["safety_status"] = str(
            obj.get("safety_status", "warning"),
        )[:16]
        summary["stopped_reason"] = str(
            obj.get("stopped_reason", ""),
        )[:64]
    elif artifact_type == "dashboard":
        summary["dashboard_id"] = str(obj.get("dashboard_id", ""))[:64]
        counts = obj.get("counts", {}) or {}
        summary["counts"] = {
            k: int(counts.get(k, 0) or 0)
            for k in ("pending", "running", "completed",
                      "failed", "batches")
        }
        summary["safety_status"] = str(
            obj.get("safety_status", "warning"),
        )[:16]
        summary["latest_items_count"] = len(
            obj.get("latest_items", []) or [],
        )
    elif artifact_type == "daily_report":
        summary["report_id"] = str(obj.get("report_id", ""))[:64]
        counts = obj.get("counts", {}) or {}
        summary["counts"] = {
            k: int(counts.get(k, 0) or 0)
            for k in ("pending", "running", "completed",
                      "failed", "batches")
        }
        tm = obj.get("top_materials", []) or []
        summary["top_materials"] = [
            str(x)[:64] for x in tm[:10]
        ]
        summary["safety_status"] = str(
            obj.get("safety_status", "warning"),
        )[:16]
        summary["cache_hits_total"] = int(
            obj.get("cache_hits_total", 0) or 0,
        )
        summary["workers_seen_total"] = int(
            obj.get("workers_seen_total", 0) or 0,
        )
    elif artifact_type == "trial_pack_manifest":
        summary["pack_id"] = str(obj.get("pack_id", ""))[:64]
        summary["worker_id"] = str(obj.get("worker_id", ""))[:64]
        summary["repo_commit_short"] = str(
            obj.get("repo_commit", ""),
        )[:16]
        summary["repo_tag"] = str(obj.get("repo_tag", ""))[:64]
        summary["expected_compute_output_sha256"] = str(
            obj.get("expected_compute_output_sha256", ""),
        )[:64]
        summary["files_count"] = len(
            obj.get("files", []) or [],
        )
    return summary


def _discover_demo_artifacts(
    demo_root: Path, warnings: List[str],
) -> List[Dict[str, Any]]:
    """Walk ``demo_root`` recursively; for every .json file, parse,
    check the ``schema`` field against KNOWN_ARTIFACT_SCHEMAS, and
    summarise. Cap the result at 100 entries to keep the report
    bounded."""
    artifacts: List[Dict[str, Any]] = []
    if not demo_root.exists():
        warnings.append(
            "demo-root missing: " + str(demo_root.name)
        )
        return artifacts
    if not demo_root.is_dir():
        warnings.append(
            "demo-root not a directory: " + str(demo_root.name)
        )
        return artifacts
    for p in sorted(demo_root.rglob("*.json")):
        # Symlink guard: only follow files inside demo_root.
        try:
            rp = p.resolve()
        except OSError:
            continue
        try:
            rp.relative_to(demo_root.resolve())
        except ValueError:
            continue
        obj = _safe_load_json(p)
        if obj is None:
            continue
        schema = obj.get("schema")
        if not isinstance(schema, str):
            continue
        a_type = KNOWN_ARTIFACT_SCHEMAS.get(schema)
        if a_type is None:
            continue
        artifacts.append({
            "artifact_type": a_type,
            "path_basename": p.name,
            "schema":        schema,
            "summary":       _summarise_artifact(a_type, obj),
        })
        if len(artifacts) >= 100:
            break
    return artifacts


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(
    *,
    repo_root: Path,
    sprint_id: str,
    branch: str,
    base_ref: str,
    pinned_time: str,
    pytest_target: Optional[str] = None,
    demo_root: Optional[Path] = None,
    require_clean_tracked_tree: bool = False,
    allow_untracked: bool = False,
) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    if not repo_root.is_dir():
        raise ReleaseRunnerError(
            "repo-root not a directory: " + str(repo_root)
        )

    warnings: List[str] = []

    current_branch = _git_current_branch(repo_root)
    branch_match = (current_branch == branch)
    if not branch_match:
        warnings.append(
            "current branch " + current_branch
            + " does not match --branch " + branch
        )

    head_commit = _git_head_commit(repo_root)

    try:
        base_commit = _git_ref_commit(repo_root, base_ref)
    except ReleaseRunnerError as exc:
        base_commit = ""
        warnings.append("base-ref unreadable: " + str(exc))

    tracked_dirty = _git_tracked_dirty(repo_root)
    untracked = _git_untracked_files(repo_root)
    untracked_count = len(untracked)

    if tracked_dirty:
        warnings.append(
            "tracked tree is dirty ("
            + str(_count_dirty_tracked(repo_root)) + " files)"
        )
    if untracked_count > 0 and not allow_untracked:
        warnings.append(
            "tracked tree has " + str(untracked_count)
            + " untracked files (use --allow-untracked to permit)"
        )

    changed_files = _git_changed_files_vs_base(repo_root, base_ref) \
        if base_commit else []
    additions_total = sum(
        max(0, x.get("additions", 0)) for x in changed_files
    )
    deletions_total = sum(
        max(0, x.get("deletions", 0)) for x in changed_files
    )
    commits_ahead = _git_commits_ahead(repo_root, base_ref) \
        if base_commit else []

    pytest_result: Dict[str, Any] = {
        "ran":        False,
        "target":     pytest_target or "",
        "returncode": -1,
        "passed":     0,
        "failed":     0,
        "skipped":    0,
        "errors":     0,
        "summary":    "",
    }
    if pytest_target:
        pytest_result = _run_pytest(pytest_target, repo_root)

    demo_artifacts: List[Dict[str, Any]] = []
    if demo_root is not None:
        demo_artifacts = _discover_demo_artifacts(
            Path(demo_root), warnings,
        )

    ready = True
    # Hard gates:
    if not branch_match:
        ready = False
    if require_clean_tracked_tree and tracked_dirty:
        ready = False
    if untracked_count > 0 and not allow_untracked:
        ready = False
    if pytest_result["ran"] and (
        pytest_result["failed"] > 0
        or pytest_result["errors"] > 0
        or pytest_result["returncode"] != 0
    ):
        ready = False

    if not ready:
        safety_status = "warning"
    elif warnings:
        safety_status = "warning"
    else:
        safety_status = "ok"

    report_id = "tsr-" + _sha16(_canonical_dumps({
        "pinned_time":      pinned_time,
        "sprint_id":        sprint_id,
        "branch":           branch,
        "head_commit":      head_commit,
        "base_commit":      base_commit,
    }))

    report: Dict[str, Any] = {
        "schema":             SCHEMA_RELEASE_REPORT,
        "report_id":          report_id,
        "pinned_time":        pinned_time,
        "sprint_id":          sprint_id,
        "branch":             branch,
        "current_branch":     current_branch,
        "branch_match":       bool(branch_match),
        "base_ref":           base_ref,
        "head_commit":        head_commit,
        "head_commit_short":  head_commit[:16],
        "base_commit":        base_commit,
        "base_commit_short":  base_commit[:16],
        "repo_root_basename": repo_root.name,
        "tree_status": {
            "tracked_dirty":     bool(tracked_dirty),
            "untracked_count":   int(untracked_count),
            "untracked_allowed": bool(allow_untracked),
        },
        "changed_files":         changed_files[:200],
        "changed_files_count":   len(changed_files),
        "additions_total":       int(additions_total),
        "deletions_total":       int(deletions_total),
        "commits_ahead":         commits_ahead,
        "commits_ahead_count":   len(commits_ahead),
        "pytest":                pytest_result,
        "demo_artifacts":        demo_artifacts,
        "demo_artifacts_count":  len(demo_artifacts),
        "warnings":              warnings,
        "ready_to_release":      bool(ready),
        "require_clean_tracked_tree": bool(require_clean_tracked_tree),
        "safety_status":         safety_status,
        "safety_flags": {
            "no_git_push":         True,
            "no_git_merge":        True,
            "no_git_tag":          True,
            "no_wallet_access":    True,
            "no_signing":          True,
            "no_broadcast":        True,
            "no_network_required": True,
        },
    }
    return report


def _count_dirty_tracked(repo_root: Path) -> int:
    out = _run_git(["status", "--porcelain"], repo_root).stdout
    n = 0
    for line in out.splitlines():
        if line and not line.startswith("??"):
            n += 1
    return n


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# Trinity Sprint Release Report")
    a("")
    a("**Sprint:** `" + str(report["sprint_id"]) + "`  ")
    a("**Report id:** `" + str(report["report_id"]) + "`  ")
    a("**Pinned time:** `" + str(report["pinned_time"]) + "`  ")
    a("**Repo:** `" + str(report["repo_root_basename"]) + "`  ")
    a(
        "**Ready to release:** `"
        + ("true" if report["ready_to_release"] else "false")
        + "`  "
    )
    a("**Safety status:** `" + str(report["safety_status"]) + "`")
    a("")
    a("## Branch")
    a("")
    a("- requested: `" + str(report["branch"]) + "`")
    a("- current:   `" + str(report["current_branch"]) + "`")
    a(
        "- match:     `"
        + ("yes" if report["branch_match"] else "no") + "`"
    )
    a("")
    a("## Commits")
    a("")
    a("- HEAD:       `" + str(report["head_commit_short"]) + "`")
    a("- base ref:   `" + str(report["base_ref"]) + "`")
    a("- base sha:   `" + str(report["base_commit_short"]) + "`")
    a(
        "- ahead:      **"
        + str(report["commits_ahead_count"]) + "** commit(s)"
    )
    if report["commits_ahead"]:
        for c in report["commits_ahead"][:20]:
            a(
                "    - `" + str(c["sha_short"]) + "`  "
                + str(c["subject"])
            )
    a("")
    a("## Tree status")
    a("")
    ts = report["tree_status"]
    a("- tracked_dirty:     `"
      + ("yes" if ts["tracked_dirty"] else "no") + "`")
    a("- untracked_count:   `" + str(ts["untracked_count"]) + "`")
    a("- untracked_allowed: `"
      + ("yes" if ts["untracked_allowed"] else "no") + "`")
    a("")
    a("## Changed files (vs " + str(report["base_ref"]) + ")")
    a("")
    a("- files:    **" + str(report["changed_files_count"]) + "**")
    a("- additions: **" + str(report["additions_total"]) + "**")
    a("- deletions: **" + str(report["deletions_total"]) + "**")
    if report["changed_files"]:
        a("")
        a("| path | +adds | -dels |")
        a("|---|---:|---:|")
        for f in report["changed_files"][:60]:
            a(
                "| `" + str(f["path"]) + "` | "
                + str(f["additions"]) + " | "
                + str(f["deletions"]) + " |"
            )
    a("")
    a("## Tests")
    a("")
    p = report["pytest"]
    if not p["ran"]:
        a("- _no --pytest-target provided; tests not run._")
    else:
        a("- target:     `" + str(p["target"]) + "`")
        a("- returncode: `" + str(p["returncode"]) + "`")
        a(
            "- passed:     **" + str(p["passed"])
            + "**, failed: **" + str(p["failed"])
            + "**, skipped: **" + str(p["skipped"])
            + "**, errors: **" + str(p["errors"]) + "**"
        )
        if p["summary"]:
            a("- summary:    `" + str(p["summary"]) + "`")
    a("")
    a("## Demo artifacts")
    a("")
    if not report["demo_artifacts"]:
        a("- _no --demo-root provided, or no Trinity artifacts found._")
    else:
        for da in report["demo_artifacts"]:
            a("### `" + str(da["path_basename"]) + "`")
            a("")
            a("- type:   `" + str(da["artifact_type"]) + "`")
            a("- schema: `" + str(da["schema"]) + "`")
            sm = da.get("summary", {}) or {}
            for k in sorted(sm.keys()):
                v = sm[k]
                a("- " + k + ": `" + str(v) + "`")
            a("")
    a("## Warnings")
    a("")
    if report["warnings"]:
        for w in report["warnings"]:
            a("- " + str(w))
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
        prog="sprint_release_runner",
        description=(
            "Trinity Sprint Release Runner v0.1. Read-only "
            "preflight verifier. NEVER pushes, NEVER merges, "
            "NEVER tags, NEVER touches a wallet, NEVER signs, "
            "NEVER broadcasts, NEVER uses GitHub API."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    pv = sub.add_parser(
        "verify",
        help="Verify release readiness and write JSON + Markdown.",
    )
    pv.add_argument("--repo-root", required=True)
    pv.add_argument("--sprint-id", required=True)
    pv.add_argument("--branch", required=True)
    pv.add_argument("--base-ref", required=True)
    pv.add_argument("--out-json", required=True)
    pv.add_argument("--out-md", required=True)
    pv.add_argument("--pinned-time", required=True)
    pv.add_argument("--pytest-target", default=None)
    pv.add_argument("--demo-root", default=None)
    pv.add_argument(
        "--require-clean-tracked-tree", action="store_true",
        help="Exit nonzero if any tracked file has unstaged or "
             "staged changes.",
    )
    pv.add_argument(
        "--allow-untracked", action="store_true",
        help="Permit existing untracked files (otherwise they "
             "trip a warning and ready_to_release becomes false).",
    )
    return p


def _cmd_verify(args) -> int:
    try:
        report = build_report(
            repo_root=Path(args.repo_root),
            sprint_id=args.sprint_id,
            branch=args.branch,
            base_ref=args.base_ref,
            pinned_time=args.pinned_time,
            pytest_target=args.pytest_target,
            demo_root=(
                Path(args.demo_root) if args.demo_root else None
            ),
            require_clean_tracked_tree=bool(
                args.require_clean_tracked_tree,
            ),
            allow_untracked=bool(args.allow_untracked),
        )
    except ReleaseRunnerError as exc:
        print(
            "[sprint_release_runner] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        "[sprint_release_runner] report_id=" + report["report_id"]
        + " sprint=" + report["sprint_id"]
        + " branch_match="
        + ("true" if report["branch_match"] else "false")
        + " ready_to_release="
        + ("true" if report["ready_to_release"] else "false")
        + " safety_status=" + report["safety_status"]
        + " warnings=" + str(len(report["warnings"]))
        + " json=" + str(out_json)
        + " md=" + str(out_md)
    )
    if not report["ready_to_release"]:
        return 1
    return 0


COMMANDS = {
    "verify": _cmd_verify,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
