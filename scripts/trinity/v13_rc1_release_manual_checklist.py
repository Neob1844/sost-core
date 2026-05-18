#!/usr/bin/env python3
"""Trinity V13 RC1 Release Manual Checklist v0.1.

Read-only generator for the manual signing + publication
checklist the operator runs OUTSIDE of any automation. The
script:

    - Verifies the local artifact bundle is intact
      (MANIFEST.json + MANIFEST.md + SHA256SUMS +
      VERIFY_COMMANDS.md + three binaries + optional tarball).
    - Verifies the public website metadata is still in the
      pre-signing state (``release_status =
      metadata_only_not_signed_not_uploaded``).
    - Emits the full step-by-step manual operator checklist
      as a JSON document + a Markdown rendering. Every
      command in the checklist is a STRING TEMPLATE that the
      operator copies into their own terminal — this script
      never executes it, never invokes gpg / signify / minisign,
      never opens the network, never touches a wallet, never
      uploads anything.

READ-ONLY observer:

    - NEVER touches a wallet
    - NEVER touches a private key
    - NEVER signs anything
    - NEVER invokes gpg / signify / minisign / openssl dgst
    - NEVER broadcasts
    - NEVER uploads or publishes a release
    - NEVER opens the network (no fetch / requests / urllib)
    - NEVER calls the GitHub API
    - NEVER deploys (Ethereum or other)
    - NEVER mutates git state
    - NEVER uses subprocess (Python hashlib only)

Usage:
    python3 scripts/trinity/v13_rc1_release_manual_checklist.py \\
        --repo-root   /opt/sost \\
        --bundle-dir  /tmp/sost-v13-rc1-artifact-bundle \\
        --out-json    /tmp/sost-v13-rc1-release-checklist/checklist.json \\
        --out-md      /tmp/sost-v13-rc1-release-checklist/checklist.md \\
        --pinned-time 2026-05-18T16:30:00+00:00

Exit codes:
    0 - bundle + public metadata both in the expected pre-signing
        state; checklist written
    1 - bundle has gaps OR public metadata is not in the
        pre-signing state (the operator should fix that BEFORE
        running the manual signing steps); checklist still written
    2 - usage / setup error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_REPORT = "trinity-v13-rc1-release-manual-checklist/v0.1"
SCHEMA_PUBLIC_MANIFEST = (
    "sost-v13-rc1-artifact-manifest-public/v0.1"
)

PUBLIC_MANIFEST_REL_PATH = (
    "website/api/v13_rc1_artifact_manifest.json"
)

REQUIRED_BINARIES = ("sost-node", "sost-miner", "sost-cli")

EXPECTED_RELEASE_STATUS = "metadata_only_not_signed_not_uploaded"


class ChecklistError(Exception):
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


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _parse_sha256sums(p: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
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
        if len(digest) != 64 or not all(
            c in "0123456789abcdef" for c in digest
        ):
            continue
        out.append({"name": name.strip(), "sha256": digest})
    return out


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(path))


# ---------------------------------------------------------------------------
# Bundle inspection
# ---------------------------------------------------------------------------


def _check_bundle(bundle_dir: Path) -> Dict[str, Any]:
    binaries_view = [
        {
            "name":    name,
            "present": (bundle_dir / "bin" / name).is_file(),
        }
        for name in REQUIRED_BINARIES
    ]
    sha_lines = _parse_sha256sums(bundle_dir / "SHA256SUMS")
    # Cap to the schema's maxItems just in case the operator
    # extended SHA256SUMS with extra entries.
    sha_lines = sha_lines[:16]

    has_tarball = False
    for f in bundle_dir.iterdir() if bundle_dir.is_dir() else []:
        if f.suffix == ".gz" and f.name.endswith(".tar.gz"):
            has_tarball = True
            break

    manifest_json_present  = (bundle_dir / "MANIFEST.json").is_file()
    manifest_md_present    = (bundle_dir / "MANIFEST.md").is_file()
    sha256sums_present     = (bundle_dir / "SHA256SUMS").is_file()
    verify_commands_present = (
        bundle_dir / "VERIFY_COMMANDS.md"
    ).is_file()

    sha_names = {row["name"] for row in sha_lines}
    sha_covers_three = sha_names.issuperset(set(REQUIRED_BINARIES))

    all_ok = (
        manifest_json_present
        and manifest_md_present
        and sha256sums_present
        and verify_commands_present
        and sha_covers_three
        and all(b["present"] for b in binaries_view)
    )

    return {
        "manifest_json_present":   manifest_json_present,
        "manifest_md_present":     manifest_md_present,
        "sha256sums_present":      sha256sums_present,
        "verify_commands_present": verify_commands_present,
        "binaries_present":        binaries_view,
        "tarball_present":         has_tarball,
        "sha256sums_lines":        sha_lines,
        "all_ok":                  all_ok,
    }


def _check_public_metadata(repo_root: Path) -> Dict[str, Any]:
    path = repo_root / PUBLIC_MANIFEST_REL_PATH
    obj = _read_json(path)
    if obj is None or obj.get("schema") != SCHEMA_PUBLIC_MANIFEST:
        return {
            "release_status_current":  "unknown",
            "release_status_expected": EXPECTED_RELEASE_STATUS,
            "matches":                 False,
        }
    current = str(
        obj.get("release_status", "unknown")
    )
    if current not in (
        "metadata_only_not_signed_not_uploaded",
        "signed_metadata_only",
        "signed_and_published",
    ):
        current = "unknown"
    return {
        "release_status_current":  current,
        "release_status_expected": EXPECTED_RELEASE_STATUS,
        "matches":                 current == EXPECTED_RELEASE_STATUS,
    }


# ---------------------------------------------------------------------------
# Manual-step generator (every command is a STRING template; no execution)
# ---------------------------------------------------------------------------


def _manual_steps(bundle_dir: Path) -> List[Dict[str, Any]]:
    bd = str(bundle_dir)
    return [
        # ----- Stage A — pre-sign verification --------------------
        {
            "id":          "A1",
            "stage":       "A_preverify",
            "title":       "Re-verify the local bundle hashes",
            "description":
                "Independently re-hash every binary in the bundle "
                "and compare against SHA256SUMS. The operator does "
                "this BEFORE signing so the signature never "
                "endorses a binary that drifted from the preflight.",
            "command_template":
                "cd " + bd + "/bin && sha256sum -c ../SHA256SUMS",
            "uses_release_key":         False,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "A2",
            "stage":       "A_preverify",
            "title":       "(Optional) Re-run the V13 binary preflight",
            "description":
                "Re-runs scripts/trinity/v13_binary_preflight.py to "
                "confirm ready_to_release is still true on the "
                "same tree the bundle was built from.",
            "command_template":
                "python3 scripts/trinity/v13_binary_preflight.py "
                "--repo-root /opt/sost --build-dir /opt/sost/build-v13-rc1 "
                "--out-dir /tmp/sost-v13-binary-preflight-release "
                "--pinned-time $(date -u +%Y-%m-%dT%H:%M:%S+00:00) "
                "--require-binaries --run-tests --run-ctest "
                "--write-sha256sums",
            "uses_release_key":         False,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "A3",
            "stage":       "A_preverify",
            "title":       "Confirm release-key fingerprint and host posture",
            "description":
                "Run on the SECURE host that holds the release "
                "key. The release key MUST be a dedicated release "
                "key, separate from any wallet, mining or SbPoW "
                "key. The fingerprint shown MUST match the "
                "fingerprint the operator has previously announced "
                "in the BitcoinTalk thread.",
            "command_template":
                "# operator-only — runs on the offline / secure host "
                "where the release key lives.",
            "uses_release_key":         True,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },

        # ----- Stage B — sign SHA256SUMS --------------------------
        {
            "id":          "B1",
            "stage":       "B_sign",
            "title":       "Detached-sign SHA256SUMS with the release key",
            "description":
                "Generates an ASCII-armored detached signature next "
                "to SHA256SUMS. The signing tool (gpg / signify / "
                "minisign) is the operator's choice; the command "
                "template uses gpg for illustration. The script "
                "you are reading does NOT execute this command — "
                "the operator copies it into their own terminal.",
            "command_template":
                "# operator-only, on the secure host that holds the "
                "release key.\n"
                "gpg --detach-sign --armor "
                + bd + "/SHA256SUMS",
            "uses_release_key":         True,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "B2",
            "stage":       "B_sign",
            "title":       "Verify the signature locally",
            "description":
                "Confirms the newly produced signature verifies "
                "cleanly against SHA256SUMS using the release "
                "public key the operator has already published.",
            "command_template":
                "gpg --verify " + bd + "/SHA256SUMS.asc "
                + bd + "/SHA256SUMS",
            "uses_release_key":         False,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "B3",
            "stage":       "B_sign",
            "title":       "Record the signature SHA-256",
            "description":
                "Computes SHA-256 over the signature file itself, "
                "so the operator can publish it inside the next "
                "metadata bump (signed_metadata_only stage).",
            "command_template":
                "sha256sum " + bd + "/SHA256SUMS.asc",
            "uses_release_key":         False,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },

        # ----- Stage C — upload release ---------------------------
        {
            "id":          "C1",
            "stage":       "C_upload",
            "title":       "Create the GitHub release shell",
            "description":
                "Creates the v13-rc1 release on the project's "
                "GitHub mirror. Operator chooses whether to do "
                "this via `gh release create` or the GitHub web "
                "UI. Either way, the script you are reading does "
                "NOT call the GitHub API.",
            "command_template":
                "# operator-only — example with the gh CLI:\n"
                "gh release create v13-rc1 --draft "
                "--title 'SOST V13 RC1' "
                "--notes-file " + bd + "/MANIFEST.md",
            "uses_release_key":         False,
            "uses_network":             True,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "C2",
            "stage":       "C_upload",
            "title":       "Upload binaries + SHA256SUMS + signature",
            "description":
                "Attaches the three binaries, the SHA256SUMS file, "
                "and the detached signature to the release. "
                "Optionally also attach the deterministic tarball.",
            "command_template":
                "# operator-only — gh CLI example:\n"
                "gh release upload v13-rc1 "
                + bd + "/bin/sost-node "
                + bd + "/bin/sost-miner "
                + bd + "/bin/sost-cli "
                + bd + "/SHA256SUMS "
                + bd + "/SHA256SUMS.asc",
            "uses_release_key":         False,
            "uses_network":             True,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "C3",
            "stage":       "C_upload",
            "title":       "Re-download and re-verify from the public URL",
            "description":
                "Confirms the published URLs actually serve the "
                "exact bytes the operator uploaded. Run from a "
                "different host than the one that uploaded.",
            "command_template":
                "# operator-only — replace <release-url> with the "
                "actual published path.\n"
                "curl -fSsLO <release-url>/SHA256SUMS\n"
                "curl -fSsLO <release-url>/SHA256SUMS.asc\n"
                "gpg --verify SHA256SUMS.asc SHA256SUMS\n"
                "# then re-hash binaries fetched from the URL "
                "and compare against SHA256SUMS.",
            "uses_release_key":         False,
            "uses_network":             True,
            "must_be_done_by_operator": True,
        },

        # ----- Stage D — update public metadata -------------------
        {
            "id":          "D1",
            "stage":       "D_update_metadata",
            "title":       "Bump release_status -> signed_and_published",
            "description":
                "Edit website/api/v13_rc1_artifact_manifest.json: "
                "change release_status from "
                "'metadata_only_not_signed_not_uploaded' to "
                "'signed_and_published' once both the signature "
                "and the binaries are publicly downloadable. If "
                "only the signature is up (binaries still being "
                "uploaded), use 'signed_metadata_only' as an "
                "intermediate value.",
            "command_template":
                "# operator-only — edit the file directly on a "
                "feature branch:\n"
                "$EDITOR website/api/v13_rc1_artifact_manifest.json",
            "uses_release_key":         False,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "D2",
            "stage":       "D_update_metadata",
            "title":       "Add signature fields to the public manifest",
            "description":
                "Add a signature block with basename, sha256 and "
                "public URL of the detached signature. Example "
                "shape:\n"
                "  \"signature\": {\n"
                "    \"basename\": \"SHA256SUMS.asc\",\n"
                "    \"sha256\":   \"<from-step-B3>\",\n"
                "    \"public_url\": \"<published URL>\"\n"
                "  }\n"
                "Also add a top-level signature_public_path field "
                "alongside sha256sums_public_path so reviewers can "
                "find the signature without scanning the whole "
                "JSON.",
            "command_template":
                "# operator-only — schema bump: "
                "sost-v13-rc1-artifact-manifest-public/v0.1 may "
                "need a follow-on v0.2 if the signature shape is "
                "made required; for now the public consumer "
                "treats the field as optional.",
            "uses_release_key":         False,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "D3",
            "stage":       "D_update_metadata",
            "title":       "Bump website/api/explorer_version.json (v268 -> v269)",
            "description":
                "Increments the explorer version banner so users "
                "see a v269 bump describing the signed/published "
                "transition.",
            "command_template":
                "# operator-only — edit on the same feature branch:\n"
                "$EDITOR website/api/explorer_version.json",
            "uses_release_key":         False,
            "uses_network":             False,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "D4",
            "stage":       "D_update_metadata",
            "title":       "Operator interactive release sequence",
            "description":
                "Operator pushes the feature branch, merges into "
                "main, pushes main, tags website-v269 (or "
                "website-signed-v01 / website-published-v01, "
                "operator's choice), pushes the tag, deletes the "
                "branch. The script you are reading never "
                "performs any of these git mutations.",
            "command_template":
                "# operator-only — run from the operator's own "
                "SSH session with the operator's interactive "
                "GitHub credentials. See the project's standard "
                "release block.",
            "uses_release_key":         False,
            "uses_network":             True,
            "must_be_done_by_operator": True,
        },

        # ----- Stage E — announce --------------------------------
        {
            "id":          "E1",
            "stage":       "E_announce",
            "title":       "Post BitcoinTalk announcement",
            "description":
                "Post the V13 RC1 signed-and-published "
                "announcement to the canonical BitcoinTalk "
                "thread, with the release URL, the four SHA-256 "
                "hashes (three binaries + SHA256SUMS), the "
                "signature URL, the release-key fingerprint, "
                "and the verification command (sha256sum -c + "
                "gpg --verify).",
            "command_template":
                "# operator-only — manual post; no automation.",
            "uses_release_key":         False,
            "uses_network":             True,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "E2",
            "stage":       "E_announce",
            "title":       "Post to the official Telegram channel",
            "description":
                "Same content as the BitcoinTalk post, condensed. "
                "The Telegram channel is announced from the "
                "BitcoinTalk thread first to block impersonators.",
            "command_template":
                "# operator-only — manual post; no automation.",
            "uses_release_key":         False,
            "uses_network":             True,
            "must_be_done_by_operator": True,
        },
        {
            "id":          "E3",
            "stage":       "E_announce",
            "title":       "Update sostcore.com explorer + DEX + wallet pages",
            "description":
                "If any user-facing page still says 'metadata "
                "only', flip the wording to point at the "
                "signed-and-published release URL. This is the "
                "same kind of edit as the V13 RC1 operator notice "
                "(website-v267) and V13 RC1 public artifact "
                "metadata (website-v268), and should ride on the "
                "next website bump.",
            "command_template":
                "# operator-only — bundle with the D4 release "
                "sequence on the same feature branch.",
            "uses_release_key":         False,
            "uses_network":             True,
            "must_be_done_by_operator": True,
        },
    ]


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_checklist(
    *,
    repo_root: Path,
    bundle_dir: Path,
    pinned_time: str,
) -> Dict[str, Any]:
    repo_root  = Path(repo_root).resolve()
    bundle_dir = Path(bundle_dir)

    if not repo_root.is_dir():
        raise ChecklistError(
            "repo-root not a directory: " + str(repo_root)
        )

    bundle_checks   = _check_bundle(bundle_dir)
    metadata_state  = _check_public_metadata(repo_root)
    steps           = _manual_steps(bundle_dir)

    safety_status = "ok"
    if not bundle_checks["all_ok"]:
        safety_status = "warning"
    if not metadata_state["matches"]:
        safety_status = "warning"

    checklist_id = "v13rc1cl-" + _sha16(_canonical_dumps({
        "pinned_time":         pinned_time,
        "bundle_dir_basename": bundle_dir.name,
        "repo_root_basename":  repo_root.name,
        "release_status":      metadata_state["release_status_current"],
    }))

    return {
        "schema":              SCHEMA_REPORT,
        "checklist_id":        checklist_id,
        "pinned_time":         pinned_time,
        "rc_id":               "v13-rc1",
        "activation_height":   12000,
        "bundle_dir_basename": bundle_dir.name,
        "repo_root_basename":  repo_root.name,
        "bundle_checks":       bundle_checks,
        "public_metadata_state": metadata_state,
        "manual_steps":        steps,
        "safety_status":       safety_status,
        "safety_flags": {
            "no_private_key_access": True,
            "no_signing_executed":   True,
            "no_release_upload":     True,
            "no_github_api":         True,
            "no_wallet_access":      True,
            "no_broadcast":          True,
            "no_network_required":   True,
            "no_subprocess":         True,
            "no_shell_true":         True,
            "no_ethereum_deploy":    True,
            "no_gpg_invocation":     True,
        },
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# V13 RC1 Release Manual Checklist")
    a("")
    a("**Checklist id:** `" + report["checklist_id"] + "`  ")
    a("**Pinned time:** `" + report["pinned_time"] + "`  ")
    a("**RC id:** `" + report["rc_id"] + "`  ")
    a("**Activation height:** **" + str(report["activation_height"]) + "**  ")
    a("**Bundle dir:** `" + report["bundle_dir_basename"] + "`  ")
    a("**Repo:** `" + report["repo_root_basename"] + "`  ")
    a("**Safety status:** `" + report["safety_status"] + "`")
    a("")
    a("This checklist is **informational**. Every step is something")
    a("the operator runs by hand — the script that produced this")
    a("file never signs, never uploads, never calls any network")
    a("endpoint, never touches a wallet or key, never invokes gpg,")
    a("and never spawns any child process")
    a("")
    a("## 0. Pre-flight bundle checks")
    a("")
    bc = report["bundle_checks"]
    a("| check | result |")
    a("|---|---|")
    a("| MANIFEST.json present       | "
      + ("yes" if bc["manifest_json_present"] else "**NO**") + " |")
    a("| MANIFEST.md present         | "
      + ("yes" if bc["manifest_md_present"] else "**NO**") + " |")
    a("| SHA256SUMS present          | "
      + ("yes" if bc["sha256sums_present"] else "**NO**") + " |")
    a("| VERIFY_COMMANDS.md present  | "
      + ("yes" if bc["verify_commands_present"] else "**NO**") + " |")
    a("| Tarball present             | "
      + ("yes" if bc["tarball_present"] else "no (optional)") + " |")
    a("")
    a("Required binaries:")
    a("")
    a("| name | present |")
    a("|---|---|")
    for b in bc["binaries_present"]:
        a("| `" + b["name"] + "` | "
          + ("yes" if b["present"] else "**NO**") + " |")
    a("")
    a("Bundle SHA256SUMS lines: " + str(len(bc["sha256sums_lines"])))
    a("")
    a("**all_ok:** `" + ("true" if bc["all_ok"] else "false") + "`")
    a("")
    a("## 0a. Public metadata state")
    a("")
    pm = report["public_metadata_state"]
    a("- current:  `" + pm["release_status_current"] + "`")
    a("- expected: `" + pm["release_status_expected"] + "`")
    a("- matches:  `" + ("yes" if pm["matches"] else "**NO**") + "`")
    a("")
    a("If `matches` is false, the operator should NOT start the")
    a("signing steps — the public manifest must be back at")
    a("`metadata_only_not_signed_not_uploaded` first.")
    a("")
    a("## 1. Manual steps (operator-only)")
    a("")
    stage_titles = {
        "A_preverify":       "A — Pre-sign verification",
        "B_sign":            "B — Sign SHA256SUMS",
        "C_upload":          "C — Upload release",
        "D_update_metadata": "D — Update public metadata",
        "E_announce":        "E — Announce",
    }
    for stage_key in (
        "A_preverify", "B_sign", "C_upload",
        "D_update_metadata", "E_announce",
    ):
        steps = [s for s in report["manual_steps"]
                 if s["stage"] == stage_key]
        if not steps:
            continue
        a("### " + stage_titles[stage_key])
        a("")
        for s in steps:
            a("- [ ] **" + s["id"] + " — " + s["title"] + "**  ")
            a("      " + s["description"])
            a("")
            a("      Command template (operator runs in their own shell):")
            a("")
            a("      ```")
            for cmd_line in s["command_template"].splitlines():
                a("      " + cmd_line)
            a("      ```")
            a("")
            a("      uses_release_key: `"
              + ("yes" if s["uses_release_key"] else "no") + "`  ")
            a("      uses_network:     `"
              + ("yes" if s["uses_network"] else "no") + "`  ")
            a("      must_be_done_by_operator: `yes` (always)")
            a("")
    a("## 2. Hard warnings")
    a("")
    a("- The release key MUST stay offline / on a secure host. "
      "Never let any automated agent see it.")
    a("- NEVER sign on an untrusted host.")
    a("- NEVER upload unsigned binaries as a final release. "
      "If the binaries go up first, leave the manifest at "
      "`signed_metadata_only` until the signature follows.")
    a("- NEVER let a third party publish under the operator's "
      "release identity. Re-verify every published URL from a "
      "different host before announcing.")
    a("- This checklist is NOT a script. It generates strings "
      "the operator runs. Do not pipe its output into a shell.")
    a("")
    a("## 3. State transition")
    a("")
    a("```")
    a("metadata_only_not_signed_not_uploaded")
    a("    -> signed_metadata_only        (after step B + D2)")
    a("    -> signed_and_published        (after step C + D1/D3/D4)")
    a("```")
    a("")
    a("Each transition is announced from the BitcoinTalk thread first.")
    a("")
    a("## 4. Safety flags")
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
        prog="v13_rc1_release_manual_checklist",
        description=(
            "Trinity V13 RC1 Release Manual Checklist v0.1. "
            "Read-only. NEVER signs, NEVER uploads, NEVER opens "
            "the network, NEVER invokes gpg, NEVER touches a "
            "wallet or key."
        ),
    )
    p.add_argument("--repo-root",   required=True)
    p.add_argument("--bundle-dir",  required=True)
    p.add_argument("--out-json",    required=True)
    p.add_argument("--out-md",      required=True)
    p.add_argument("--pinned-time", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()

    try:
        report = build_checklist(
            repo_root=Path(args.repo_root),
            bundle_dir=Path(args.bundle_dir),
            pinned_time=pinned,
        )
    except ChecklistError as exc:
        print(
            "[v13_rc1_release_manual_checklist] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    out_json = Path(args.out_json)
    out_md   = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(out_json, report)
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        "[v13_rc1_release_manual_checklist] "
        "checklist_id=" + report["checklist_id"]
        + " bundle_all_ok="
        + ("true" if report["bundle_checks"]["all_ok"] else "false")
        + " public_metadata_matches="
        + ("true" if report["public_metadata_state"]["matches"]
           else "false")
        + " safety_status=" + report["safety_status"]
        + " manual_steps=" + str(len(report["manual_steps"]))
        + " json=" + str(out_json)
        + " md=" + str(out_md)
    )
    if (
        not report["bundle_checks"]["all_ok"]
        or not report["public_metadata_state"]["matches"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
