#!/usr/bin/env python3
"""Trinity V13 scope gap audit v0.1.

Read-only re-verifier for the three V13 gap-analysis docs:

  - docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md
  - docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md
  - docs/V13_BEACON_II_B_III_GAPS.md

The auditor does two things:

  1. Doc-side checks: confirm each doc still contains the
     load-bearing tokens the operator requires (per the V13
     scope decision: 90 % threshold, 67-block signaling
     window, 61-block ceil, Guardian role, 10-block
     pronouncement window, V14 fallback at block 15,000,
     hard auto-disconnect at block 25,000, Memory-Lock
     deferred, etc.).

  2. Source-side checks: confirm the repo state still matches
     the claims the docs make (whether each gate is still
     RED / AMBER / GREEN). If a gate flips state (e.g. the
     operator wires `classify_gv_spend()` into
     `src/tx_validation.cpp`), the auditor reports
     `gap_closing` so the doc can be updated.

READ-ONLY observer:

  - NEVER mutates any file
  - NEVER opens the network
  - NEVER spawns a child process (pure pathlib + re + json)
  - NEVER touches a wallet, signing key, or release key
  - NEVER mutates git state
  - NEVER calls gpg / signify / minisign / openssl
  - NEVER uploads or publishes a release
  - NEVER calls the GitHub API

Usage:
    python3 scripts/trinity/v13_scope_gap_audit.py \\
        --repo-root /opt/sost \\
        --out-json  /tmp/.../audit.json \\
        --out-md    /tmp/.../audit.md

Exit codes:
    0 - all docs present + all load-bearing tokens present
    1 - at least one doc missing or missing a required token
    2 - usage / setup error
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
from typing import Any, Dict, List, Optional


SCHEMA_REPORT = "trinity-v13-scope-gap-audit/v0.1"


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
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(path))


# ---------------------------------------------------------------------------
# Per-doc required tokens
# ---------------------------------------------------------------------------


DOC_REQUIRED_TOKENS: Dict[str, List[str]] = {
    "docs/V13_POPC_ESCROW_AUTO_ACTIVATION_GAPS.md": [
        "POPC_ACTIVATION_HEIGHT",
        "12,000",
        "V14",
        "15,000",
        "Memory-Lock",
        "DEFERRED",
        "G-POPC-1", "G-POPC-2", "G-POPC-3", "G-POPC-4",
        "G-POPC-5", "G-POPC-6", "G-POPC-7", "G-POPC-8",
        "G-POPC-9",
        "SOSTEscrow.sol",
    ],
    "docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md": [
        "12,000", "V14", "15,000",
        "67",     # signaling window
        "61",     # ceil(0.90 * 67)
        "90 %",
        "75 % → 95 % → 90 %",
        "Guardian",
        "10 blocks",
        "25,000",  # hard auto-disconnect
        "G1", "G2", "G3", "G4", "G5", "G6",
        "ADDR_GOLD_VAULT",
        "classify_gv_spend",
        "Heritage Reserve",
        "Zodiac",
        "Reality.eth",
        "Sepolia",
    ],
    "docs/V13_BEACON_II_B_III_GAPS.md": [
        "12,000", "V14", "15,000",
        "Phase II-A", "Phase II-B", "Phase III",
        "BEACON_PHASE2A_ACTIVATION_HEIGHT",
        "BEACON_P2P_ACTIVATION_HEIGHT",
        "INT64_MAX",
        "DiscardDormant",
        "ECDSA",  # not Schnorr — the documented mismatch
        "Memory-Lock",
    ],
}


# ---------------------------------------------------------------------------
# Source-side facts the docs assert (re-verified at audit time)
# ---------------------------------------------------------------------------


def _check_source_facts(repo_root: Path) -> Dict[str, Any]:
    """Re-verify the key source-side claims the gap docs make.
    Each claim returns {"as_documented": bool, "evidence": str}."""

    facts: Dict[str, Any] = {}

    # --- PoPC -------------------------------------------------------------
    params_h = _read_text(repo_root / "include" / "sost" / "params.h") or ""
    facts["popc_activation_height_missing"] = {
        "as_documented": "POPC_ACTIVATION_HEIGHT" not in params_h,
        "evidence":      "absent in include/sost/params.h",
    }

    # --- Gold Vault accumulation (already live) ---------------------------
    facts["gold_vault_address_pinned"] = {
        "as_documented": "ADDR_GOLD_VAULT" in params_h,
        "evidence":      "include/sost/params.h contains ADDR_GOLD_VAULT",
    }

    # --- Gold Vault spend-side enforcement (dead code) --------------------
    tx_val = _read_text(repo_root / "src" / "tx_validation.cpp") or ""
    block_val = _read_text(repo_root / "src" / "block_validation.cpp") or ""
    # Strip comments before checking for the call.
    src_combined = re.sub(r"/\*.*?\*/", "", tx_val + "\n" + block_val,
                          flags=re.DOTALL)
    src_combined = re.sub(r"//[^\n]*", "", src_combined)
    facts["classify_gv_spend_is_dead_code"] = {
        "as_documented": "classify_gv_spend" not in src_combined,
        "evidence":      "not called from src/tx_validation.cpp or "
                         "src/block_validation.cpp",
    }

    # --- BIP9 signaling primitives exist ----------------------------------
    proposals_h = _read_text(
        repo_root / "include" / "sost" / "proposals.h"
    ) or ""
    facts["bip9_signaling_primitives_exist"] = {
        "as_documented": (
            "version_has_signal" in proposals_h
            and "count_version_signals" in proposals_h
        ),
        "evidence":      "include/sost/proposals.h",
    }

    # --- Beacon Phase II-A gate at V13_HEIGHT -----------------------------
    facts["beacon_phase2a_gate_at_v13"] = {
        "as_documented": bool(re.search(
            r"BEACON_PHASE2A_ACTIVATION_HEIGHT\s*=\s*V13_HEIGHT",
            params_h,
        )),
        "evidence":      "include/sost/params.h",
    }

    # --- Beacon Phase III gate sentinel-disabled --------------------------
    facts["beacon_p2p_gate_sentinel"] = {
        "as_documented": bool(re.search(
            r"BEACON_P2P_ACTIVATION_HEIGHT\s*=\s*INT64_MAX",
            params_h,
        )),
        "evidence":      "include/sost/params.h",
    }

    # --- Gold vault tests still 17 ----------------------------------------
    test_gv = _read_text(
        repo_root / "tests" / "test_gold_vault.cpp"
    ) or ""
    n_gv_tests = len(re.findall(r"\bGV\d+_", test_gv))
    facts["test_gold_vault_count"] = {
        "as_documented": n_gv_tests >= 17,
        "evidence":      "tests/test_gold_vault.cpp — found "
                         + str(n_gv_tests) + " GV* identifiers",
    }

    # --- Phase II-A tests present -----------------------------------------
    test_phase2a = _read_text(
        repo_root / "tests" / "test_v13_beacon_phase2a.cpp"
    ) or ""
    facts["test_phase2a_present"] = {
        "as_documented": "test_commands_must_be_empty" in test_phase2a,
        "evidence":      "tests/test_v13_beacon_phase2a.cpp",
    }

    return facts


# ---------------------------------------------------------------------------
# Per-doc token check
# ---------------------------------------------------------------------------


def _check_doc(repo_root: Path,
               rel_path: str,
               required_tokens: List[str]) -> Dict[str, Any]:
    p = repo_root / rel_path
    text = _read_text(p)
    if text is None:
        return {
            "path":             rel_path,
            "found":            False,
            "missing_tokens":   required_tokens,
            "all_tokens_present": False,
            "ok":               False,
        }
    missing = [tok for tok in required_tokens if tok not in text]
    return {
        "path":               rel_path,
        "found":              True,
        "missing_tokens":     missing,
        "all_tokens_present": (len(missing) == 0),
        "ok":                 (len(missing) == 0),
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_audit(
    *,
    repo_root: Path,
    pinned_time: str,
) -> Dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    if not repo_root.is_dir():
        raise SystemExit("repo-root not a directory: " + str(repo_root))

    docs = []
    for rel, toks in DOC_REQUIRED_TOKENS.items():
        docs.append(_check_doc(repo_root, rel, toks))
    source_facts = _check_source_facts(repo_root)

    all_docs_ok = all(d["ok"] for d in docs)
    all_facts_ok = all(f["as_documented"] for f in source_facts.values())
    all_green = all_docs_ok and all_facts_ok

    audit_id = "v13gapaudit-" + _sha16(_canonical_dumps({
        "pinned_time":        pinned_time,
        "repo_root_basename": repo_root.name,
        "docs_ok":            all_docs_ok,
        "facts_ok":           all_facts_ok,
    }))

    return {
        "schema":             SCHEMA_REPORT,
        "audit_id":           audit_id,
        "pinned_time":        pinned_time,
        "repo_root_basename": repo_root.name,
        "docs":               docs,
        "source_facts":       source_facts,
        "all_docs_ok":        all_docs_ok,
        "all_facts_ok":       all_facts_ok,
        "all_green":          all_green,
        "safety_status":      "ok" if all_green else "warning",
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
    a("# V13 Scope Gap Audit")
    a("")
    a("**audit_id:** `" + report["audit_id"] + "`  ")
    a("**pinned_time:** `" + report["pinned_time"] + "`  ")
    a("**repo:** `" + report["repo_root_basename"] + "`  ")
    a("**all_green:** **"
      + ("YES" if report["all_green"] else "NO") + "**")
    a("")
    a("## Documents")
    a("")
    a("| path | present | tokens ok |")
    a("|---|---|---|")
    for d in report["docs"]:
        a("| `" + d["path"] + "` | "
          + ("yes" if d["found"] else "**NO**") + " | "
          + ("yes" if d["all_tokens_present"]
             else "**MISSING: " + ", ".join(d["missing_tokens"]) + "**")
          + " |")
    a("")
    a("## Source-side facts")
    a("")
    a("| claim | as documented | evidence |")
    a("|---|---|---|")
    for k in sorted(report["source_facts"].keys()):
        v = report["source_facts"][k]
        a("| `" + k + "` | "
          + ("yes" if v["as_documented"] else "**NO — gap closing**")
          + " | " + v["evidence"] + " |")
    a("")
    a("If `as_documented` flips from `yes` to `NO` for a "
      "`*_missing` claim, that is good news: the gap is closing. "
      "Update the corresponding gap-analysis doc to reflect the "
      "new state. If it flips from `yes` to `NO` for a "
      "`*_pinned` or `*_at_v13` claim, that is a regression and "
      "should be investigated immediately.")
    a("")
    a("## Safety flags")
    a("")
    for k in sorted(report["safety_flags"].keys()):
        a("- `" + k + "`: **"
          + ("true" if report["safety_flags"][k] else "false")
          + "**")
    a("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v13_scope_gap_audit",
        description=(
            "Trinity V13 scope gap audit v0.1. Read-only. "
            "NEVER mutates, NEVER opens the network, NEVER "
            "spawns a child process, NEVER touches a wallet "
            "or key."
        ),
    )
    p.add_argument("--repo-root",   required=True)
    p.add_argument("--out-json",    required=True)
    p.add_argument("--out-md",      required=True)
    p.add_argument("--pinned-time", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()

    try:
        report = build_audit(
            repo_root=Path(args.repo_root),
            pinned_time=pinned,
        )
    except SystemExit:
        return 2

    out_json = Path(args.out_json)
    out_md   = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(out_json, report)
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        "[v13_scope_gap_audit] audit_id=" + report["audit_id"]
        + " all_green=" + ("true" if report["all_green"] else "false")
        + " docs_ok=" + ("true" if report["all_docs_ok"] else "false")
        + " facts_ok=" + ("true" if report["all_facts_ok"] else "false")
        + " json=" + str(out_json) + " md=" + str(out_md)
    )
    return 0 if report["all_green"] else 1


if __name__ == "__main__":
    sys.exit(main())
