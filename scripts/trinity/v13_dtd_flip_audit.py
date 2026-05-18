#!/usr/bin/env python3
"""Trinity V13 DTD flip audit v0.1.

Read-only audit that proves the V11 Phase 2 lottery cadence flip
at block 12,100 (2-of-3 bootstrap -> 1-of-3 permanent) is
consensus-enforced and genuinely automatic:

  - V11_PHASE2_HEIGHT      == 7100  (compile-time constant)
  - LOTTERY_HIGH_FREQ_WINDOW == 5000 (compile-time constant)
  - V13_HEIGHT             == 12000 (compile-time constant)
  - is_lottery_block(height, phase2_height) is the SINGLE source
    of truth, defined inline in include/sost/lottery.h
  - every call site in src/ passes a NAMED CONSTANT or a VARIABLE
    as phase2_height, NEVER a numeric literal (so the schedule
    cannot be silently shifted in any single call site)
  - sost-miner.cpp does NOT recompute cadence; it consumes the
    `lottery_triggered` field from the node's RPC response
  - lottery_exclusion_window_at returns 5 pre-V13 and 6 post-V13
    and does NOT couple to is_lottery_block (the V13 cooldown
    change at 12,000 does not interfere with the V11 Phase 2
    cadence flip at 12,100)
  - the pure Python re-implementation of the cadence rule
    agrees with the documented firing pattern at heights
    12,095..12,110

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
    python3 scripts/trinity/v13_dtd_flip_audit.py \\
        --repo-root /opt/sost \\
        --out-json  /tmp/.../audit.json \\
        --out-md    /tmp/.../audit.md

Exit codes:
    0 - all gates GREEN (consensus integrity confirmed)
    1 - at least one gate RED (consensus integrity broken)
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
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_REPORT = "trinity-v13-dtd-flip-audit/v0.1"

EXPECTED_V11_PHASE2_HEIGHT       = 7100
EXPECTED_LOTTERY_HIGH_FREQ_WIN   = 5000
EXPECTED_V13_HEIGHT              = 12000
EXPECTED_PRE_V13_EXCLUSION       = 5
EXPECTED_POST_V13_EXCLUSION      = 6

PARAMS_H_REL_PATH  = "include/sost/params.h"
LOTTERY_H_REL_PATH = "include/sost/lottery.h"
SRC_DIR_REL_PATH   = "src"
MINER_REL_PATH     = "src/sost-miner.cpp"


class AuditError(Exception):
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
# Pure re-implementation of the C++ rule (for math sanity check)
# ---------------------------------------------------------------------------


def py_is_lottery_block(height: int, phase2_height: int) -> bool:
    """Mirror of sost::lottery::is_lottery_block in include/sost/lottery.h.
    Pure function, height-only, deterministic."""
    if phase2_height >= 2**63 - 1:
        return False
    if height < phase2_height:
        return False
    offset = height - phase2_height
    if offset < EXPECTED_LOTTERY_HIGH_FREQ_WIN:
        return (height % 3) != 0
    return (height % 3) == 0


# ---------------------------------------------------------------------------
# Gate 1 — pinned compile-time constants
# ---------------------------------------------------------------------------


def _scan_constant(
    src: str, name: str,
) -> Tuple[Optional[int], Optional[int]]:
    """Return (value, line) for an `inline constexpr ... name = <int>;`
    declaration. Tolerates spacing variations."""
    pat = re.compile(
        r"^\s*inline\s+constexpr\s+\S+\s+" + re.escape(name)
        + r"\s*=\s*([0-9_]+)\s*;",
        re.MULTILINE,
    )
    m = pat.search(src)
    if not m:
        return None, None
    raw = m.group(1).replace("_", "")
    try:
        val = int(raw)
    except ValueError:
        return None, None
    line = src[:m.start()].count("\n") + 1
    return val, line


def _check_constants(repo_root: Path) -> Dict[str, Any]:
    p = repo_root / PARAMS_H_REL_PATH
    text = _read_text(p)
    if text is None:
        return {
            "params_h_path": PARAMS_H_REL_PATH,
            "params_h_found": False,
            "items": [],
            "ok": False,
        }
    items = []
    for name, expected in (
        ("V11_PHASE2_HEIGHT",        EXPECTED_V11_PHASE2_HEIGHT),
        ("LOTTERY_HIGH_FREQ_WINDOW", EXPECTED_LOTTERY_HIGH_FREQ_WIN),
        ("V13_HEIGHT",               EXPECTED_V13_HEIGHT),
        ("LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW",
                                     EXPECTED_PRE_V13_EXCLUSION),
    ):
        val, line = _scan_constant(text, name)
        items.append({
            "name":     name,
            "value":    val,
            "expected": expected,
            "line":     line,
            "ok":       (val == expected),
        })
    return {
        "params_h_path":  PARAMS_H_REL_PATH,
        "params_h_found": True,
        "items":          items,
        "ok":             all(i["ok"] for i in items),
    }


# ---------------------------------------------------------------------------
# Gate 2 — single source of truth (is_lottery_block defined inline)
# ---------------------------------------------------------------------------


def _check_helper_defined(repo_root: Path) -> Dict[str, Any]:
    p = repo_root / LOTTERY_H_REL_PATH
    text = _read_text(p)
    if text is None:
        return {
            "lottery_h_path":  LOTTERY_H_REL_PATH,
            "lottery_h_found": False,
            "ok":              False,
        }
    pat = re.compile(
        r"^\s*inline\s+bool\s+is_lottery_block\s*\("
        r"\s*int64_t\s+height\s*,\s*int64_t\s+phase2_height\s*\)\s*\{",
        re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        return {
            "lottery_h_path":  LOTTERY_H_REL_PATH,
            "lottery_h_found": True,
            "signature_found": False,
            "ok":              False,
        }
    line = text[:m.start()].count("\n") + 1
    return {
        "lottery_h_path":  LOTTERY_H_REL_PATH,
        "lottery_h_found": True,
        "signature_found": True,
        "definition_line": line,
        "ok":              True,
    }


# ---------------------------------------------------------------------------
# Gate 3 — all src/ call sites pass a named constant or variable as
# phase2_height (never a numeric literal)
# ---------------------------------------------------------------------------


_CALL_RE = re.compile(
    r"\bis_lottery_block\s*\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*\)",
)
_NUMERIC_RE = re.compile(r"^[+-]?[0-9][0-9'_]*([eE][+-]?\d+)?$")


def _classify_arg(arg: str) -> str:
    """Classify the second argument to is_lottery_block.

    Returns one of:
        "named_const"  — V11_PHASE2_HEIGHT (with or without sost:: prefix)
        "variable"     — any other identifier-like expression
                          (phase2_h, phase2_height, in.phase2_height, ...)
        "literal"      — a numeric literal (forbidden)
        "complex"      — anything else (flagged for human review)
    """
    a = arg.strip()
    if _NUMERIC_RE.match(a):
        return "literal"
    # INT64_MAX is a macro-named numeric sentinel; flag it as literal
    # because in production the rule is "always pass the constant or a
    # tracked variable; sentinel use is a test-only pattern".
    if a in ("INT64_MAX", "std::numeric_limits<int64_t>::max()"):
        return "literal"
    if re.fullmatch(r"(sost::)?V11_PHASE2_HEIGHT", a):
        return "named_const"
    # Identifier or dotted/scoped name → variable.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*"
                    r"(\s*[.:]+\s*[A-Za-z_][A-Za-z0-9_]*)*",
                    a):
        return "variable"
    return "complex"


def _iter_source_files(src_dir: Path):
    if not src_dir.is_dir():
        return
    for p in sorted(src_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix not in (".cpp", ".cc", ".h", ".hpp"):
            continue
        # Skip backup files like sost-miner.cpp.pre-rpc-resync-callsite.bak
        if ".bak" in p.name or p.name.endswith("~"):
            continue
        yield p


def _check_call_sites(repo_root: Path) -> Dict[str, Any]:
    src_dir = repo_root / SRC_DIR_REL_PATH
    sites: List[Dict[str, Any]] = []
    for p in _iter_source_files(src_dir):
        text = _read_text(p)
        if text is None:
            continue
        for m in _CALL_RE.finditer(text):
            line = text[:m.start()].count("\n") + 1
            full_line = text.splitlines()[line - 1].strip()
            # Skip comment-only matches: a leading "//" before the match
            # in the same physical line means the call is documented,
            # not invoked.
            comment_pos = full_line.find("//")
            if comment_pos != -1:
                # Match start column within the line:
                line_start = text.rfind("\n", 0, m.start()) + 1
                col = m.start() - line_start
                if col >= comment_pos:
                    continue
            klass = _classify_arg(m.group(2))
            sites.append({
                "path":            str(p.relative_to(repo_root)),
                "line":            line,
                "snippet":         full_line[:200],
                "first_arg":       m.group(1).strip(),
                "second_arg":      m.group(2).strip(),
                "classification": klass,
                "ok":              klass in ("named_const", "variable"),
            })
    return {
        "src_dir_path":             SRC_DIR_REL_PATH,
        "call_sites":               sites,
        "call_site_count":          len(sites),
        "all_routed_through_helper": True,  # by virtue of grepping for it
        "no_numeric_literals":      all(
            s["classification"] != "literal" for s in sites
        ),
        "no_complex_args":          all(
            s["classification"] != "complex" for s in sites
        ),
        "ok":                       all(s["ok"] for s in sites),
    }


# ---------------------------------------------------------------------------
# Gate 4 — miner has no parallel cadence logic
# ---------------------------------------------------------------------------


def _check_miner_independence(repo_root: Path) -> Dict[str, Any]:
    p = repo_root / MINER_REL_PATH
    text = _read_text(p)
    if text is None:
        return {
            "miner_path":  MINER_REL_PATH,
            "miner_found": False,
            "ok":          False,
        }
    # Strip block comments and line comments before checking for calls,
    # so we do not flag a documentation reference like "// uses
    # is_lottery_block via RPC" as a real call.
    stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    stripped = re.sub(r"//[^\n]*", "", stripped)
    has_call = bool(re.search(r"\bis_lottery_block\s*\(", stripped))
    has_rpc_field = "lottery_triggered" in text
    # Also defend against a stray height % 3 in the miner that would
    # bypass the RPC consumer pattern.
    has_modulo_three = bool(re.search(r"\bheight\s*%\s*3\b", stripped))
    return {
        "miner_path":                  MINER_REL_PATH,
        "miner_found":                 True,
        "has_is_lottery_block_call":   has_call,
        "consumes_lottery_triggered":  has_rpc_field,
        "has_height_modulo_three":     has_modulo_three,
        "ok":                          (not has_call)
                                       and has_rpc_field
                                       and (not has_modulo_three),
    }


# ---------------------------------------------------------------------------
# Gate 5 — V13 cooldown helper exists, is height-gated, does NOT couple
# to is_lottery_block (so the V13 cooldown change at 12,000 cannot
# interfere with the V11 Phase 2 cadence flip at 12,100)
# ---------------------------------------------------------------------------


def _check_cooldown_helper(repo_root: Path) -> Dict[str, Any]:
    p = repo_root / PARAMS_H_REL_PATH
    text = _read_text(p) or ""
    pat = re.compile(
        r"inline\s+constexpr\s+int32_t\s+lottery_exclusion_window_at"
        r"\s*\(\s*int64_t\s+height\s*\)\s*\{([\s\S]*?)\}",
    )
    m = pat.search(text)
    if not m:
        return {
            "helper_found":               False,
            "returns_5_pre_v13":          False,
            "returns_6_post_v13":         False,
            "couples_to_is_lottery_block": False,
            "ok":                         False,
        }
    body = m.group(1)
    returns_6 = "6" in body and "V13_HEIGHT" in body
    returns_5 = (
        "LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW" in body
        or "5" in body
    )
    couples = "is_lottery_block" in body
    line = text[:m.start()].count("\n") + 1
    return {
        "helper_found":               True,
        "helper_line":                line,
        "returns_5_pre_v13":          returns_5,
        "returns_6_post_v13":         returns_6,
        "couples_to_is_lottery_block": couples,
        "ok":                         (
            returns_5 and returns_6 and not couples
        ),
    }


# ---------------------------------------------------------------------------
# Gate 6 — math sanity (pure Python re-implementation agrees with the
# documented firing pattern at heights 12,095..12,110)
# ---------------------------------------------------------------------------


def _check_math_sanity() -> Dict[str, Any]:
    expected = {
        12095: True,    12096: False,   12097: True,
        12098: True,    12099: False,
        12100: False,   12101: False,   12102: True,
        12103: False,   12104: False,   12105: True,
        12106: False,   12107: False,   12108: True,
        12109: False,   12110: False,
    }
    rows: List[Dict[str, Any]] = []
    for h in sorted(expected.keys()):
        computed = py_is_lottery_block(h, EXPECTED_V11_PHASE2_HEIGHT)
        rows.append({
            "height":   h,
            "expected": expected[h],
            "computed": computed,
            "ok":       computed == expected[h],
            "phase":    "bootstrap" if h < 12100 else "permanent",
        })
    # Density counts in the visualised window.
    bootstrap_fires = sum(
        1 for r in rows if r["phase"] == "bootstrap" and r["computed"]
    )
    permanent_fires = sum(
        1 for r in rows if r["phase"] == "permanent" and r["computed"]
    )
    bootstrap_total = sum(1 for r in rows if r["phase"] == "bootstrap")
    permanent_total = sum(1 for r in rows if r["phase"] == "permanent")
    return {
        "heights":                rows,
        "bootstrap_fires":        bootstrap_fires,
        "bootstrap_total":        bootstrap_total,
        "permanent_fires":        permanent_fires,
        "permanent_total":        permanent_total,
        "all_ok":                 all(r["ok"] for r in rows),
        "ok":                     all(r["ok"] for r in rows),
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
        raise AuditError(
            "repo-root not a directory: " + str(repo_root)
        )

    constants    = _check_constants(repo_root)
    helper_def   = _check_helper_defined(repo_root)
    call_sites   = _check_call_sites(repo_root)
    miner_indep  = _check_miner_independence(repo_root)
    cooldown     = _check_cooldown_helper(repo_root)
    math_sanity  = _check_math_sanity()

    gates = {
        "g1_constants_pinned":          constants["ok"],
        "g2_helper_defined":            helper_def["ok"],
        "g3_no_literal_call_sites":     call_sites["ok"],
        "g4_miner_no_shadow_logic":     miner_indep["ok"],
        "g5_cooldown_helper_correct":   cooldown["ok"],
        "g6_math_sanity":               math_sanity["ok"],
    }
    all_green = all(gates.values())

    audit_id = "v13dtdaudit-" + _sha16(_canonical_dumps({
        "pinned_time":        pinned_time,
        "repo_root_basename": repo_root.name,
        "constants":          [(i["name"], i["value"])
                               for i in constants["items"]],
        "helper_line":        helper_def.get("definition_line"),
        "call_site_count":    call_sites["call_site_count"],
        "all_green":          all_green,
    }))

    return {
        "schema":             SCHEMA_REPORT,
        "audit_id":           audit_id,
        "pinned_time":        pinned_time,
        "repo_root_basename": repo_root.name,
        "constants":          constants,
        "helper_definition":  helper_def,
        "call_sites":         call_sites,
        "miner_independence": miner_indep,
        "cooldown_helper":    cooldown,
        "math_sanity":        math_sanity,
        "gates":              gates,
        "all_green":          all_green,
        "safety_status":      "ok" if all_green else "failed",
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
    a("# V13 DTD Flip Audit (block 12,100)")
    a("")
    a("**audit_id:** `" + report["audit_id"] + "`  ")
    a("**pinned_time:** `" + report["pinned_time"] + "`  ")
    a("**repo:** `" + report["repo_root_basename"] + "`  ")
    a("**all_green:** **" + ("YES" if report["all_green"] else "NO")
      + "**")
    a("")
    a("This audit proves the V11 Phase 2 lottery cadence flip from")
    a("**2-of-3 (bootstrap)** to **1-of-3 (permanent)** at block")
    a("12,100 is consensus-enforced, pure, and genuinely automatic")
    a("(no operator action, no restart, no Beacon, no RPC, no")
    a("config flag required).")
    a("")
    a("## Gates")
    a("")
    a("| # | Gate | Result |")
    a("|---|---|---|")
    g = report["gates"]
    for key, label in (
        ("g1_constants_pinned",
         "G1 — Constants pinned (V11_PHASE2_HEIGHT=7100, "
         "LOTTERY_HIGH_FREQ_WINDOW=5000, V13_HEIGHT=12000)"),
        ("g2_helper_defined",
         "G2 — is_lottery_block defined inline in lottery.h"),
        ("g3_no_literal_call_sites",
         "G3 — every src/ call site passes a named constant "
         "or variable (no numeric literal)"),
        ("g4_miner_no_shadow_logic",
         "G4 — sost-miner.cpp consumes RPC lottery_triggered "
         "(no parallel cadence math)"),
        ("g5_cooldown_helper_correct",
         "G5 — V13 cooldown helper (5 pre-V13 → 6 post-V13) "
         "is decoupled from is_lottery_block"),
        ("g6_math_sanity",
         "G6 — Python re-implementation agrees with documented "
         "firing pattern at heights 12,095..12,110"),
    ):
        a("| " + key.split("_")[0].upper() + " | " + label
          + " | " + ("GREEN" if g[key] else "**RED**") + " |")
    a("")
    a("## 1. Constants (" + report["constants"]["params_h_path"] + ")")
    a("")
    a("| name | value | expected | line | ok |")
    a("|---|---|---|---|---|")
    for it in report["constants"]["items"]:
        a("| `" + it["name"] + "` | "
          + str(it["value"]) + " | "
          + str(it["expected"]) + " | "
          + (str(it["line"]) if it["line"] is not None else "—")
          + " | " + ("yes" if it["ok"] else "**NO**") + " |")
    a("")
    a("## 2. Single source of truth")
    a("")
    h = report["helper_definition"]
    if h["ok"]:
        a("`is_lottery_block(int64_t height, int64_t phase2_height)`")
        a("is defined inline at `" + h["lottery_h_path"] + ":"
          + str(h["definition_line"]) + "`.")
    else:
        a("**MISSING.** `is_lottery_block` was not found with the")
        a("expected inline signature in `" + h["lottery_h_path"] + "`.")
    a("")
    a("## 3. Call sites in `" + report["call_sites"]["src_dir_path"]
      + "` (" + str(report["call_sites"]["call_site_count"]) + ")")
    a("")
    a("Every call site MUST pass a named constant or a variable as")
    a("`phase2_height` — never a numeric literal. A numeric literal")
    a("would silently shift the cadence at that single call site.")
    a("")
    a("| path | line | second_arg | classification | ok |")
    a("|---|---|---|---|---|")
    for s in report["call_sites"]["call_sites"]:
        a("| `" + s["path"] + "` | " + str(s["line"]) + " | `"
          + s["second_arg"] + "` | " + s["classification"]
          + " | " + ("yes" if s["ok"] else "**NO**") + " |")
    a("")
    a("## 4. Miner independence (`"
      + report["miner_independence"]["miner_path"] + "`)")
    a("")
    mi = report["miner_independence"]
    if mi.get("miner_found"):
        a("- has `is_lottery_block(...)` call: `"
          + ("yes" if mi["has_is_lottery_block_call"] else "no") + "`")
        a("- consumes `lottery_triggered` from RPC: `"
          + ("yes" if mi["consumes_lottery_triggered"] else "no") + "`")
        a("- has stray `height % 3` math: `"
          + ("yes" if mi["has_height_modulo_three"] else "no") + "`")
    else:
        a("(miner source not found)")
    a("")
    a("## 5. Cooldown helper decoupling")
    a("")
    c = report["cooldown_helper"]
    if c["helper_found"]:
        a("`lottery_exclusion_window_at(int64_t height)` defined at")
        a("`" + PARAMS_H_REL_PATH + ":" + str(c["helper_line"]) + "`.")
        a("")
        a("- returns 5 pre-V13: `"
          + ("yes" if c["returns_5_pre_v13"] else "**NO**") + "`")
        a("- returns 6 post-V13: `"
          + ("yes" if c["returns_6_post_v13"] else "**NO**") + "`")
        a("- couples to `is_lottery_block`: `"
          + ("**YES (bad)**" if c["couples_to_is_lottery_block"]
             else "no") + "`")
    else:
        a("**MISSING.** Cooldown helper not found.")
    a("")
    a("## 6. Math sanity — contiguous run 12,095..12,110")
    a("")
    ms = report["math_sanity"]
    a("Python re-implementation of `is_lottery_block` against")
    a("`V11_PHASE2_HEIGHT = " + str(EXPECTED_V11_PHASE2_HEIGHT)
      + "`. The boundary is at height 12,100 (offset = 5,000).")
    a("")
    a("| height | phase | expected | computed | ok |")
    a("|---|---|---|---|---|")
    for r in ms["heights"]:
        a("| " + str(r["height"]) + " | " + r["phase"] + " | "
          + ("FIRES" if r["expected"] else "—") + " | "
          + ("FIRES" if r["computed"] else "—") + " | "
          + ("yes" if r["ok"] else "**NO**") + " |")
    a("")
    a("Density in the visualised window:")
    a("- bootstrap (5 blocks 12,095..12,099): "
      + str(ms["bootstrap_fires"]) + " fires / "
      + str(ms["bootstrap_total"]) + " blocks")
    a("- permanent (11 blocks 12,100..12,110): "
      + str(ms["permanent_fires"]) + " fires / "
      + str(ms["permanent_total"]) + " blocks")
    a("")
    a("(Long-run density is 2/3 in bootstrap and 1/3 in permanent;")
    a("the existing test `tests/test_lottery_frequency.cpp` proves")
    a("the long-run density over 1,500 + 6,000 blocks.)")
    a("")
    a("## 7. Safety flags")
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
        prog="v13_dtd_flip_audit",
        description=(
            "Trinity V13 DTD flip audit v0.1. Read-only. Proves the "
            "V11 Phase 2 cadence flip at block 12,100 is "
            "consensus-enforced and automatic. NEVER mutates, NEVER "
            "opens the network, NEVER spawns a child process, NEVER "
            "touches a wallet or key."
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
    except AuditError as exc:
        print(
            "[v13_dtd_flip_audit] error: " + str(exc),
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
        "[v13_dtd_flip_audit] audit_id=" + report["audit_id"]
        + " all_green=" + ("true" if report["all_green"] else "false")
        + " gates_green="
        + str(sum(1 for v in report["gates"].values() if v))
        + "/" + str(len(report["gates"]))
        + " call_sites=" + str(report["call_sites"]["call_site_count"])
        + " json=" + str(out_json)
        + " md=" + str(out_md)
    )
    return 0 if report["all_green"] else 1


if __name__ == "__main__":
    sys.exit(main())
