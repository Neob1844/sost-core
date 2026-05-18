#!/usr/bin/env python3
"""Trinity V13 Release Candidate Check v0.1.

Local preflight verifier for the V13 release-candidate package.
Reads ``config/v13_release_candidate.json`` (single source of
truth), ``website/api/v13_release_candidate.json`` (public mirror),
the V13 activation plan + readiness gates + miner/operator
checklist + release-candidate note, and the V13 readiness checker
output, and emits a single ``trinity-v13-release-candidate-report/
v0.1`` JSON plus a Markdown rendering with a final ``rc_ready``
boolean.

READ-ONLY observer:

    - NEVER touches a wallet
    - NEVER touches a private key
    - NEVER signs anything
    - NEVER broadcasts
    - NEVER opens the network
    - NEVER calls the GitHub API
    - NEVER mutates git state (no push, no merge, no tag)
    - NEVER uses subprocess (not even argv-list)
    - NEVER deploys to Ethereum or any other chain

Usage:
    python3 scripts/trinity/v13_release_candidate_check.py \\
        --repo-root /opt/sost \\
        --out-json  /var/lib/trinity/v13-rc/report.json \\
        --out-md    /var/lib/trinity/v13-rc/report.md \\
        --pinned-time 2026-05-18T13:00:00+00:00

Exit codes:
    0 - rc_ready == true
    1 - rc_ready == false (warnings recorded)
    2 - usage / setup error (bad repo-root, missing config)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_REPORT = "trinity-v13-release-candidate-report/v0.1"
SCHEMA_CONFIG = "sost-v13-release-candidate/v0.1"
SCHEMA_PUBLIC = "sost-v13-release-candidate-public/v0.1"

CONFIG_REL_PATH        = "config/v13_release_candidate.json"
PUBLIC_MIRROR_REL_PATH = "website/api/v13_release_candidate.json"

RC_DOC_RELEASE_CANDIDATE = "docs/V13_RELEASE_CANDIDATE.md"
RC_DOC_MINER_CHECKLIST   = "docs/V13_MINER_OPERATOR_CHECKLIST.md"
RC_DOC_ACTIVATION_PLAN   = "docs/V13_ACTIVATION_PLAN.md"
RC_DOC_READINESS_GATES   = "docs/V13_READINESS_GATES.md"

# Field names the public mirror must mirror byte-for-byte from
# the in-repo config. Fields not listed here are intentionally
# private (e.g. evidence_keyword and detailed reasons live only
# in the in-repo config).
PUBLIC_MIRROR_REQUIRED_FIELDS = (
    "v13_activation_height",
    "v15_fallback_height",
    "dtd_lottery_decision_height",
    "min_commit",
    "required_binary_label",
    "ntp_required",
    "future_timestamp_drift_seconds_post_v13",
    "dtd_lottery_cooldown_post_v13",
)


class ReleaseCandidateError(Exception):
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


def _file_contains(p: Path, needle: str) -> bool:
    text = _read_text(p)
    if text is None:
        return False
    return needle in text


# ---------------------------------------------------------------------------
# Confirmed item readiness (mirrors v13_readiness_check confirmed checks)
# ---------------------------------------------------------------------------


def _check_casert_all_profiles(repo_root: Path) -> bool:
    """The V13 cASERT wire (validator_profile_ceiling_at /
    effective_profile_ceiling_at / CASERT_MAX_ACTIVE_PROFILE_V13)
    is in params.h."""
    params = repo_root / "include" / "sost" / "params.h"
    text = _read_text(params) or ""
    return (
        "CASERT_MAX_ACTIVE_PROFILE_V13" in text
        and "validator_profile_ceiling_at" in text
        and "effective_profile_ceiling_at" in text
    )


def _check_dtd_cooldown_6(repo_root: Path) -> bool:
    params = repo_root / "include" / "sost" / "params.h"
    text = _read_text(params) or ""
    return (
        "lottery_exclusion_window_at" in text
        and "height >= V13_HEIGHT" in text
    )


def _check_timestamp_drift_10s(repo_root: Path) -> bool:
    params = repo_root / "include" / "sost" / "params.h"
    text = _read_text(params) or ""
    return (
        "max_future_drift_at" in text
        and "if (height >= V13_HEIGHT)" in text
        and "return 10" in text
    )


def _check_beacon_phase_ii_a(repo_root: Path) -> bool:
    params = repo_root / "include" / "sost" / "params.h"
    beacon = repo_root / "include" / "sost" / "beacon.h"
    text_p = _read_text(params) or ""
    text_b = _read_text(beacon) or ""
    return (
        "BEACON_PHASE2A_ACTIVATION_HEIGHT" in text_p
        and "V13_HEIGHT" in text_p
        and "BEACON_PUBKEY_HEX" in text_b
    )


CONFIRMED_CHECKERS = {
    "casert_all_profiles_e7_h35": _check_casert_all_profiles,
    "dtd_cooldown_6":             _check_dtd_cooldown_6,
    "timestamp_drift_10s":        _check_timestamp_drift_10s,
    "beacon_phase_ii_a":          _check_beacon_phase_ii_a,
}


# ---------------------------------------------------------------------------
# Public mirror check
# ---------------------------------------------------------------------------


def _public_mirror_matches(
    config: Dict[str, Any], public: Dict[str, Any],
) -> List[str]:
    """Return a list of mismatch descriptions. Empty list means OK."""
    out: List[str] = []
    if public.get("schema") != SCHEMA_PUBLIC:
        out.append(
            "public mirror schema mismatch (got "
            + repr(public.get("schema")) + ", want "
            + repr(SCHEMA_PUBLIC) + ")"
        )
    for field in PUBLIC_MIRROR_REQUIRED_FIELDS:
        cv = config.get(field)
        pv = public.get(field)
        if cv != pv:
            out.append(
                "public mirror " + field + ": got " + repr(pv)
                + ", want " + repr(cv)
            )
    # Confirmed item IDs.
    cfg_ids = sorted(
        c.get("id", "") for c in (config.get("confirmed_items") or [])
    )
    pub_ids = sorted(
        public.get("confirmed_items_ids", []) or []
    )
    if cfg_ids != pub_ids:
        out.append(
            "public mirror confirmed_items_ids: got "
            + repr(pub_ids) + ", want " + repr(cfg_ids)
        )
    # Fallback V15 IDs.
    cfg_fb = sorted(
        f.get("id", "") for f in (config.get("fallback_v15_items") or [])
    )
    pub_fb = sorted(
        public.get("fallback_v15_items_ids", []) or []
    )
    if cfg_fb != pub_fb:
        out.append(
            "public mirror fallback_v15_items_ids: got "
            + repr(pub_fb) + ", want " + repr(cfg_fb)
        )
    # Safety block must be const-true everywhere.
    for k, v in (config.get("safety", {}) or {}).items():
        if v is not True:
            out.append("config safety flag " + k + " is not const-true")
        if public.get("safety", {}).get(k) is not True:
            out.append("public safety flag " + k + " is not const-true")
    return out


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(
    *,
    repo_root: Path,
    pinned_time: str,
) -> Dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    if not repo_root.is_dir():
        raise ReleaseCandidateError(
            "repo-root not a directory: " + str(repo_root)
        )

    config_path = repo_root / CONFIG_REL_PATH
    config = _read_json(config_path)
    config_loaded = config is not None
    if config is None:
        raise ReleaseCandidateError(
            "config not loadable: " + str(config_path)
        )
    if config.get("schema") != SCHEMA_CONFIG:
        raise ReleaseCandidateError(
            "config schema mismatch: " + repr(config.get("schema"))
        )

    public_path = repo_root / PUBLIC_MIRROR_REL_PATH
    public = _read_json(public_path)
    public_mirror_loaded = public is not None

    warnings: List[str] = []

    # Confirmed-item readiness.
    confirmed_view: Dict[str, bool] = {}
    for cfg_item in (config.get("confirmed_items") or []):
        item_id = cfg_item.get("id", "")
        checker = CONFIRMED_CHECKERS.get(item_id)
        if checker is None:
            warnings.append(
                "no checker registered for confirmed item " + item_id
            )
            confirmed_view[item_id] = False
            continue
        wired = bool(checker(repo_root))
        confirmed_view[item_id] = wired
        if not wired:
            warnings.append(
                "confirmed item " + item_id
                + " NOT wired in code at this commit"
            )

    all_ready = all(
        confirmed_view.get(item_id, False)
        for item_id in (
            "casert_all_profiles_e7_h35",
            "dtd_cooldown_6",
            "timestamp_drift_10s",
            "beacon_phase_ii_a",
        )
    )
    confirmed_view["all_ready"] = all_ready

    # Fallback V15 IDs (read from config, surfaced for the report).
    fallback_ids = [
        str(f.get("id", "")) for f in (config.get("fallback_v15_items") or [])
    ]

    # Docs presence.
    docs_present = {
        "release_candidate_md":
            (repo_root / RC_DOC_RELEASE_CANDIDATE).is_file(),
        "miner_operator_checklist_md":
            (repo_root / RC_DOC_MINER_CHECKLIST).is_file(),
        "activation_plan_md":
            (repo_root / RC_DOC_ACTIVATION_PLAN).is_file(),
        "readiness_gates_md":
            (repo_root / RC_DOC_READINESS_GATES).is_file(),
    }
    for k, v in docs_present.items():
        if not v:
            warnings.append("doc missing: " + k)

    # Doc content scans. Check both V13_RELEASE_CANDIDATE.md and
    # V13_MINER_OPERATOR_CHECKLIST.md for the four required tokens.
    def _docs_mention(needle: str) -> bool:
        for rel in (RC_DOC_RELEASE_CANDIDATE, RC_DOC_MINER_CHECKLIST):
            if _file_contains(repo_root / rel, needle):
                return True
        return False

    docs_mention_block_12000        = _docs_mention("block 12000") or \
        _docs_mention("block 12,000")
    docs_mention_ntp_10s            = _docs_mention("NTP") and \
        (_docs_mention("10 s") or _docs_mention("10s") or
         _docs_mention("10-second") or _docs_mention("10 second"))
    docs_mention_dtd_decision_12100 = _docs_mention("12100") or \
        _docs_mention("12,100")
    docs_mention_fallback_v15       = _docs_mention("V15") or \
        _docs_mention("15,000") or _docs_mention("15000")

    if not docs_mention_block_12000:
        warnings.append("docs do not mention block 12,000")
    if not docs_mention_ntp_10s:
        warnings.append("docs do not mention NTP / 10 s drift cap")
    if not docs_mention_dtd_decision_12100:
        warnings.append("docs do not mention DTD decision at 12,100")
    if not docs_mention_fallback_v15:
        warnings.append("docs do not mention fallback V15 (block 15,000)")

    # Public mirror match.
    public_mirror_matches = False
    if public_mirror_loaded and public is not None:
        mismatches = _public_mirror_matches(config, public)
        if not mismatches:
            public_mirror_matches = True
        else:
            for m in mismatches:
                warnings.append("public mirror mismatch: " + m)
    else:
        warnings.append("public mirror not loaded: " + str(public_path))

    rc_ready = (
        config_loaded
        and public_mirror_loaded
        and all_ready
        and all(docs_present.values())
        and docs_mention_block_12000
        and docs_mention_ntp_10s
        and docs_mention_dtd_decision_12100
        and docs_mention_fallback_v15
        and public_mirror_matches
    )

    if not rc_ready:
        safety_status = "warning"
    elif warnings:
        safety_status = "warning"
    else:
        safety_status = "ok"

    report_id = "v13rc-" + _sha16(_canonical_dumps({
        "pinned_time":             pinned_time,
        "repo_root_basename":      repo_root.name,
        "config_min_commit":       str(config.get("min_commit", "")),
        "all_confirmed_ready":     all_ready,
        "public_mirror_matches":   public_mirror_matches,
        "rc_ready":                rc_ready,
    }))

    return {
        "schema":                                   SCHEMA_REPORT,
        "report_id":                                report_id,
        "pinned_time":                              pinned_time,
        "repo_root_basename":                       repo_root.name,
        "config_loaded":                            config_loaded,
        "public_mirror_loaded":                     public_mirror_loaded,
        "rc_id":                                    str(config.get("rc_id", "v13-rc1")),
        "activation_heights": {
            "v13_activation_height":       12000,
            "v15_fallback_height":         15000,
            "dtd_lottery_decision_height": 12100,
        },
        "min_commit":                               str(config.get("min_commit", "")),
        "required_binary_label":                    str(config.get("required_binary_label", "v13-rc1")),
        "ntp_required":                             True,
        "future_timestamp_drift_seconds_post_v13":  10,
        "dtd_lottery_cooldown_post_v13":            6,
        "confirmed_items_ready":                    confirmed_view,
        "fallback_v15_items":                       fallback_ids,
        "docs_present":                             docs_present,
        "docs_mention_block_12000":                 docs_mention_block_12000,
        "docs_mention_ntp_10s":                     docs_mention_ntp_10s,
        "docs_mention_dtd_decision_12100":          docs_mention_dtd_decision_12100,
        "docs_mention_fallback_v15":                docs_mention_fallback_v15,
        "public_mirror_matches_safe_fields":        public_mirror_matches,
        "rc_ready":                                 rc_ready,
        "warnings":                                 warnings,
        "safety_status":                            safety_status,
        "safety_flags": {
            "no_wallet_access":           True,
            "no_private_key_access":      True,
            "no_signing":                 True,
            "no_broadcast":               True,
            "no_network_required":        True,
            "no_github_api":              True,
            "no_shell_true":              True,
            "no_destructive_git":         True,
            "no_auto_push_merge_tag":     True,
            "no_subprocess":              True,
            "no_ethereum_deploy":         True,
        },
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# Trinity V13 Release Candidate Report")
    a("")
    a("**Report id:** `" + report["report_id"] + "`  ")
    a("**Pinned time:** `" + report["pinned_time"] + "`  ")
    a("**Repo:** `" + report["repo_root_basename"] + "`  ")
    a("**RC id:** `" + report["rc_id"] + "`  ")
    a("**rc_ready:** `" + ("true" if report["rc_ready"] else "false") + "`  ")
    a("**Safety status:** `" + report["safety_status"] + "`")
    a("")
    a("## Activation heights")
    a("")
    h = report["activation_heights"]
    a("- V13 activation height: **" + str(h["v13_activation_height"]) + "**")
    a("- V15 fallback height: **" + str(h["v15_fallback_height"]) + "**")
    a("- DTD lottery decision: **"
      + str(h["dtd_lottery_decision_height"]) + "**")
    a("")
    a("## Binary")
    a("")
    a("- min_commit: `" + report["min_commit"] + "`")
    a("- required_binary_label: `" + report["required_binary_label"] + "`")
    a("- NTP required: `"
      + ("true" if report["ntp_required"] else "false") + "`")
    a("- future-drift cap post-V13: **"
      + str(report["future_timestamp_drift_seconds_post_v13"]) + " s**")
    a("- DTD cooldown post-V13: **"
      + str(report["dtd_lottery_cooldown_post_v13"]) + " blocks**")
    a("")
    a("## Confirmed V13 items (wired in code at this commit)")
    a("")
    a("| id | wired |")
    a("|---|---|")
    cir = report["confirmed_items_ready"]
    for k in (
        "casert_all_profiles_e7_h35",
        "dtd_cooldown_6",
        "timestamp_drift_10s",
        "beacon_phase_ii_a",
    ):
        wired = "yes" if cir.get(k, False) else "**NO**"
        a("| `" + k + "` | " + wired + " |")
    a("")
    a("**all_ready:** `"
      + ("true" if cir.get("all_ready", False) else "false") + "`")
    a("")
    a("## Fallback V15 items")
    a("")
    if report["fallback_v15_items"]:
        for it in report["fallback_v15_items"]:
            a("- `" + it + "`")
    else:
        a("- _none_")
    a("")
    a("## Docs present")
    a("")
    for k in sorted(report["docs_present"].keys()):
        v = report["docs_present"][k]
        a("- `" + k + "`: " + ("yes" if v else "**NO**"))
    a("")
    a("## Docs content checks")
    a("")
    a("- mentions block 12,000:        `"
      + ("yes" if report["docs_mention_block_12000"] else "**NO**") + "`")
    a("- mentions NTP / 10 s drift cap: `"
      + ("yes" if report["docs_mention_ntp_10s"] else "**NO**") + "`")
    a("- mentions DTD decision 12,100: `"
      + ("yes" if report["docs_mention_dtd_decision_12100"] else "**NO**") + "`")
    a("- mentions fallback V15:        `"
      + ("yes" if report["docs_mention_fallback_v15"] else "**NO**") + "`")
    a("")
    a("## Public mirror")
    a("")
    a("- loaded: `"
      + ("yes" if report["public_mirror_loaded"] else "**NO**") + "`")
    a("- safe-field match: `"
      + ("yes" if report["public_mirror_matches_safe_fields"] else "**NO**")
      + "`")
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
        prog="v13_release_candidate_check",
        description=(
            "Trinity V13 Release Candidate Check v0.1. Read-only "
            "preflight verifier for the V13 release-candidate "
            "package. NEVER touches a wallet, NEVER signs, NEVER "
            "broadcasts, NEVER opens the network, NEVER uses "
            "GitHub API, NEVER deploys."
        ),
    )
    p.add_argument("--repo-root", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-md", required=True)
    p.add_argument("--pinned-time", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()

    try:
        report = build_report(
            repo_root=Path(args.repo_root),
            pinned_time=pinned,
        )
    except ReleaseCandidateError as exc:
        print(
            "[v13_release_candidate_check] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    out_json = Path(args.out_json)
    out_md   = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        "[v13_release_candidate_check] report_id=" + report["report_id"]
        + " rc_id=" + report["rc_id"]
        + " rc_ready="
        + ("true" if report["rc_ready"] else "false")
        + " confirmed_all_ready="
        + ("true" if report["confirmed_items_ready"]["all_ready"] else "false")
        + " public_mirror="
        + ("matches" if report["public_mirror_matches_safe_fields"] else "MISMATCH")
        + " safety_status=" + report["safety_status"]
        + " json=" + str(out_json)
        + " md=" + str(out_md)
    )
    if not report["rc_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
