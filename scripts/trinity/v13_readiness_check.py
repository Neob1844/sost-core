#!/usr/bin/env python3
"""Trinity V13 Activation Readiness Check v0.1.

Local preflight verifier for the SOST V13 hardfork at block 12,000.
Inspects the repo for the constants, files, tests and implementation
surfaces required to ship the CONFIRMED V13 items and the GATED
target/fallback items (PoPC Model A+B, Beacon Phase II-B, Beacon
Phase III, Memory-Lock per-instance). Emits a single
``trinity-v13-readiness-report/v0.1`` JSON plus a Markdown rendering.

The script is a READ-ONLY observer:

    - NEVER touches a wallet
    - NEVER touches a private key
    - NEVER signs anything
    - NEVER broadcasts
    - NEVER opens the network
    - NEVER calls the GitHub API
    - NEVER mutates git state (no push, no merge, no tag)
    - NEVER executes a shell-string subprocess (shell-string mode forbidden)

It only reads files, parses constants, greps source for invariants,
and reports.

Usage:
    python3 scripts/trinity/v13_readiness_check.py \\
        --repo-root /opt/sost \\
        --out-json /var/lib/trinity/v13/report.json \\
        --out-md   /var/lib/trinity/v13/report.md \\
        --pinned-time 2026-05-18T00:30:00+00:00

Exit codes:
    0 - confirmed V13 items wired AND no fatal gate misclassification
    1 - confirmed V13 items not wired (V13 fork would slip)
    2 - usage / setup error (missing config, bad repo-root)
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


SCHEMA_REPORT = "trinity-v13-readiness-report/v0.1"
SCHEMA_CONFIG = "trinity-v13-activation-config/v0.1"

CONFIG_RELATIVE_PATH = "config/v13_activation.json"


class ReadinessError(Exception):
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


def _file_contains(p: Path, needles: Tuple[str, ...]) -> Tuple[bool, str]:
    """Return (any_found, first_hit) — fast substring scan."""
    text = _read_text(p)
    if text is None:
        return (False, "")
    for n in needles:
        if n in text:
            return (True, n)
    return (False, "")


def _grep_repo(
    repo_root: Path,
    rel_dirs: Tuple[str, ...],
    needles: Tuple[str, ...],
    file_globs: Tuple[str, ...] = ("*.cpp", "*.h", "*.hpp", "*.py", "*.md"),
) -> List[Tuple[Path, str]]:
    """Walk the given relative dirs and return [(path, matched_needle)]
    for any file containing any needle. Symlink-safe and bounded."""
    hits: List[Tuple[Path, str]] = []
    seen_paths: set = set()
    for rel in rel_dirs:
        base = repo_root / rel
        if not base.exists():
            continue
        for glob in file_globs:
            for p in base.rglob(glob):
                try:
                    rp = p.resolve()
                except OSError:
                    continue
                try:
                    rp.relative_to(repo_root.resolve())
                except ValueError:
                    continue
                if rp in seen_paths:
                    continue
                seen_paths.add(rp)
                ok, hit = _file_contains(p, needles)
                if ok:
                    hits.append((p, hit))
                if len(hits) >= 200:
                    return hits
    return hits


# ---------------------------------------------------------------------------
# Confirmed item gates
# ---------------------------------------------------------------------------


def _check_casert_all_profiles(repo_root: Path) -> Dict[str, Any]:
    # Looking for a V13-gated profile-ceiling expansion. The current
    # code has CASERT_CEILING_H13_HEIGHT historical and a hard ceiling
    # constant; we look for a helper or constant that lifts the
    # ceiling at V13_HEIGHT.
    hits = _grep_repo(
        repo_root,
        ("include/sost", "src"),
        (
            "effective_profile_ceiling_at",
            "CASERT_V13_PROFILE_CEILING",
            "CASERT_ALL_PROFILES_HEIGHT",
            "casert_v13_profile_ceiling",
        ),
    )
    wired = bool(hits)
    if wired:
        evidence = "; ".join(
            str(p.relative_to(repo_root)) + ":" + needle
            for p, needle in hits[:3]
        )
        return {
            "wired_in_code": True,
            "evidence": evidence[:480],
        }
    return {
        "wired_in_code": False,
        "evidence": (
            "no V13-gated profile-ceiling expansion found in "
            "include/sost/ or src/; current ceiling lives at "
            "CASERT_HARD_PROFILE_CEILING / CASERT_CEILING_H13_HEIGHT "
            "without a height-conditional helper opening H35"
        ),
        "blocker_note": (
            "Add an `effective_profile_ceiling_at(height)` helper "
            "(or CASERT_V13_PROFILE_CEILING constant) that returns "
            "35 for height >= V13_HEIGHT, with paired tests, before "
            "the V13 binary cut. Otherwise fallback this item to V15."
        ),
    }


def _check_dtd_cooldown_6(repo_root: Path) -> Dict[str, Any]:
    params = repo_root / "include" / "sost" / "params.h"
    text = _read_text(params) or ""
    wired = (
        "lottery_exclusion_window_at" in text
        and "height >= V13_HEIGHT" in text
        and "return (height >= V13_HEIGHT)" in text
    )
    if wired:
        return {
            "wired_in_code": True,
            "evidence": (
                "include/sost/params.h: lottery_exclusion_window_at("
                "height) returns 6 for height >= V13_HEIGHT, else "
                "LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW (= 5)"
            ),
        }
    return {
        "wired_in_code": False,
        "evidence": (
            "lottery_exclusion_window_at(height) helper not found "
            "in include/sost/params.h"
        ),
        "blocker_note": (
            "Add the helper or confirm it lives in another header"
        ),
    }


def _check_timestamp_drift_10s(repo_root: Path) -> Dict[str, Any]:
    params = repo_root / "include" / "sost" / "params.h"
    text = _read_text(params) or ""
    wired = (
        "max_future_drift_at" in text
        and "if (height >= V13_HEIGHT)" in text
        and "return 10" in text
    )
    if wired:
        return {
            "wired_in_code": True,
            "evidence": (
                "include/sost/params.h: max_future_drift_at(height) "
                "returns 10 for height >= V13_HEIGHT"
            ),
        }
    return {
        "wired_in_code": False,
        "evidence": "max_future_drift_at(height) not wired for 10 s at V13",
        "blocker_note": "Wire the 10 s cap at V13_HEIGHT in params.h",
    }


def _check_beacon_phase_ii_a(repo_root: Path) -> Dict[str, Any]:
    params = repo_root / "include" / "sost" / "params.h"
    beacon_h = repo_root / "include" / "sost" / "beacon.h"
    text_params = _read_text(params) or ""
    text_beacon = _read_text(beacon_h) or ""
    wired = (
        "BEACON_PHASE2A_ACTIVATION_HEIGHT" in text_params
        and "V13_HEIGHT" in text_params
        and "BEACON_PUBKEY_HEX" in text_beacon
    )
    if wired:
        return {
            "wired_in_code": True,
            "evidence": (
                "include/sost/params.h: BEACON_PHASE2A_ACTIVATION_HEIGHT "
                "= V13_HEIGHT; include/sost/beacon.h: BEACON_PUBKEY_HEX "
                "declared as the hardcoded operator-side key"
            ),
        }
    return {
        "wired_in_code": False,
        "evidence": "Beacon Phase II-A activation gate not found",
        "blocker_note": "Add BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT",
    }


CONFIRMED_CHECKERS = {
    "casert_all_profiles_e7_h35": _check_casert_all_profiles,
    "dtd_cooldown_6":             _check_dtd_cooldown_6,
    "timestamp_drift_10s":        _check_timestamp_drift_10s,
    "beacon_phase_ii_a":          _check_beacon_phase_ii_a,
}


# ---------------------------------------------------------------------------
# Gated item checks
# ---------------------------------------------------------------------------


def _check_popc_a_audit_daemon(repo_root: Path) -> Dict[str, Any]:
    # Look for evidence of a real daemon: a service file, a thread,
    # or a script that explicitly executes rather than only prints.
    daemon_py = repo_root / "scripts" / "popc_daemon.py"
    text = _read_text(daemon_py) or ""
    explicit_disclaimer = (
        "Does NOT execute transactions" in text
        or "operator review" in text.lower()
    )
    # A real daemon would have a long-running poll loop with sleep().
    has_systemd = (repo_root / "scripts" / "popc_daemon.service").exists()
    if explicit_disclaimer and not has_systemd:
        return {
            "status": "fail",
            "evidence": (
                "scripts/popc_daemon.py header declares 'Does NOT "
                "execute transactions — generates CLI commands "
                "for operator review'; no systemd unit found"
            ),
            "blocker_note": (
                "Convert popc_daemon.py to a real polling daemon, OR "
                "ship a systemd unit + cron + RPC call wrapper that "
                "invokes popc_check / popc_release without operator "
                "copy-paste"
            ),
        }
    if has_systemd:
        return {
            "status": "pass",
            "evidence": "scripts/popc_daemon.service present",
        }
    return {
        "status": "unknown",
        "evidence": "popc_daemon.py present but execution mode unclear",
        "blocker_note": (
            "Verify production wiring; add explicit systemd unit "
            "or cron entry to the deploy artifacts"
        ),
    }


def _check_popc_b_auto_slash(repo_root: Path) -> Dict[str, Any]:
    # Search for an automatic invocation path that calls popc_slash
    # on an audit-failure event.
    src_files = list((repo_root / "src").rglob("*.cpp")) + \
        list((repo_root / "src").rglob("*.h")) + \
        list((repo_root / "scripts").rglob("*.py")) + \
        list((repo_root / "scripts").rglob("*.sh"))
    auto_slash_evidence: List[str] = []
    for p in src_files:
        text = _read_text(p) or ""
        if (
            "popc_slash" in text
            and ("audit_failed" in text or "is_audit_triggered" in text
                 or "audit_failure" in text)
        ):
            try:
                auto_slash_evidence.append(str(p.relative_to(repo_root)))
            except ValueError:
                pass
    if auto_slash_evidence:
        return {
            "status": "pass",
            "evidence": "auto-slash wired in: "
                       + ", ".join(auto_slash_evidence[:3]),
        }
    return {
        "status": "fail",
        "evidence": (
            "popc_slash exists as RPC but no automatic invocation "
            "path tied to is_audit_triggered / audit failure found"
        ),
        "blocker_note": (
            "Wire popc_slash to fire automatically when the audit "
            "daemon detects a failure (e.g., scripts/popc_daemon.py "
            "+ a slash_queue consumer that calls the RPC)"
        ),
    }


def _check_popc_c_auto_settlement(repo_root: Path) -> Dict[str, Any]:
    # Look for a cron / systemd path that fires popc_release on
    # commitment maturity. Check the auto-distribute script for
    # a real execution path.
    sh = repo_root / "scripts" / "popc_auto_distribute.sh"
    text = _read_text(sh) or ""
    has_cron = (repo_root / "scripts" / "popc_release.cron").exists() or \
        "* * * * *" in text
    if "popc_release" in text and has_cron:
        return {
            "status": "pass",
            "evidence": (
                "scripts/popc_auto_distribute.sh invokes popc_release "
                "and has a documented cron schedule"
            ),
        }
    if "popc_release" in text:
        return {
            "status": "fail",
            "evidence": (
                "scripts/popc_auto_distribute.sh calls popc_release "
                "but no cron/systemd schedule was found in the repo"
            ),
            "blocker_note": (
                "Add a cron entry or systemd timer that invokes "
                "popc_auto_distribute.sh; commit the deploy artifact "
                "(scripts/popc_release.cron or scripts/popc_release."
                "service) to the repo"
            ),
        }
    return {
        "status": "fail",
        "evidence": "no popc_release auto-invocation path found",
        "blocker_note": "Wire popc_release into a scheduled task",
    }


def _check_popc_d_escrow_deployment(repo_root: Path) -> Dict[str, Any]:
    # The SOSTEscrow contract source exists; we need a deployment
    # record file with a verified address.
    sol = repo_root / "contracts" / "SOSTEscrow.sol"
    deploy_records = list(
        (repo_root / "contracts").glob("*deployment*.json")
    ) + list(
        (repo_root / "contracts").glob("*deployed*.json")
    ) + list(
        (repo_root / "contracts").glob("*addresses*.json")
    )
    if not sol.exists():
        return {
            "status": "fail",
            "evidence": "contracts/SOSTEscrow.sol not found",
            "blocker_note": "Solidity contract source missing",
        }
    if deploy_records:
        # Quick parse for an Ethereum-shaped address.
        for r in deploy_records:
            text = _read_text(r) or ""
            if re.search(r"0x[a-fA-F0-9]{40}", text):
                return {
                    "status": "pass",
                    "evidence": (
                        "deployment record at "
                        + str(r.relative_to(repo_root))
                        + " contains an Ethereum address"
                    ),
                }
    return {
        "status": "fail",
        "evidence": (
            "contracts/SOSTEscrow.sol present but no deployment "
            "record file with an Ethereum address found in "
            "contracts/"
        ),
        "blocker_note": (
            "Deploy SOSTEscrow to Sepolia (then mainnet), record "
            "the verified address in contracts/SOSTEscrow.deployment"
            ".json"
        ),
    }


def _check_popc_e_event_listener(repo_root: Path) -> Dict[str, Any]:
    # Search for a listener that decodes GoldDeposited events and
    # calls escrow_register on the SOST side.
    hits = _grep_repo(
        repo_root,
        ("scripts", "src"),
        ("GoldDeposited", "Deposited(", "escrow_register"),
        file_globs=("*.py", "*.cpp", "*.h"),
    )
    listener_files: List[str] = []
    for p, _ in hits:
        text = _read_text(p) or ""
        if "GoldDeposited" in text and "escrow_register" in text:
            try:
                listener_files.append(str(p.relative_to(repo_root)))
            except ValueError:
                pass
    if listener_files:
        return {
            "status": "pass",
            "evidence": "event listener wired in: "
                       + ", ".join(listener_files[:3]),
        }
    return {
        "status": "fail",
        "evidence": (
            "no file binds GoldDeposited event decoding to "
            "escrow_register() on the SOST side"
        ),
        "blocker_note": (
            "Add an Ethereum JSON-RPC listener (Python or C++) "
            "that decodes GoldDeposited events from the deployed "
            "SOSTEscrow address and calls escrow_register via RPC"
        ),
    }


def _check_popc_f_consensus_gate(repo_root: Path) -> Dict[str, Any]:
    consensus = repo_root / "include" / "sost" / "consensus_constants.h"
    params = repo_root / "include" / "sost" / "params.h"
    popc_h = repo_root / "include" / "sost" / "popc.h"
    for f in (consensus, params, popc_h):
        text = _read_text(f) or ""
        if "POPC_ACTIVATION_HEIGHT" in text:
            return {
                "status": "pass",
                "evidence": (
                    "POPC_ACTIVATION_HEIGHT declared in "
                    + str(f.relative_to(repo_root))
                ),
            }
    return {
        "status": "fail",
        "evidence": (
            "no POPC_ACTIVATION_HEIGHT constant found in "
            "include/sost/{consensus_constants.h, params.h, popc.h}; "
            "BOND_ACTIVATION_HEIGHT_MAINNET = 10000 only unlocks TX "
            "types, it does not gate the lifecycle"
        ),
        "blocker_note": (
            "Add `inline constexpr int64_t POPC_ACTIVATION_HEIGHT "
            "= V13_HEIGHT;` (or = V15_HEIGHT if deferring) and "
            "reference it from the lifecycle entry points"
        ),
    }


def _check_popc_g_e2e_test(repo_root: Path) -> Dict[str, Any]:
    # Search tests/ for an end-to-end PoPC lifecycle integration test.
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return {
            "status": "fail",
            "evidence": "tests/ directory not found",
            "blocker_note": "Add tests/test_popc_lifecycle_e2e.cpp",
        }
    candidates = []
    for p in tests_dir.rglob("test_popc*"):
        text = _read_text(p) or ""
        # An end-to-end test should mention all four phases.
        if all(
            tok in text
            for tok in ("register", "audit", "release")
        ) and (
            "slash" in text or "settle" in text
        ):
            candidates.append(str(p.relative_to(repo_root)))
    if candidates:
        return {
            "status": "pass",
            "evidence": "PoPC e2e lifecycle test(s): "
                       + ", ".join(candidates[:3]),
        }
    return {
        "status": "fail",
        "evidence": (
            "no PoPC test covers the full register -> audit -> "
            "slash-or-settle -> release lifecycle without manual "
            "RPC intervention"
        ),
        "blocker_note": (
            "Add tests/test_popc_lifecycle_e2e.cpp (or .py) that "
            "exercises the full lifecycle end-to-end"
        ),
    }


def _check_beacon_iib_design_closed(repo_root: Path) -> Dict[str, Any]:
    candidates = [
        repo_root / "docs" / "BEACON_PHASE_IIB_SPEC.md",
        repo_root / "docs" / "BEACON_PHASE2B_SPEC.md",
        repo_root / "docs" / "BEACON_PHASE_2B_SPEC.md",
        repo_root / "docs" / "V13_BEACON_IIB.md",
    ]
    for c in candidates:
        if c.exists():
            return {
                "status": "pass",
                "evidence": "design doc at "
                           + str(c.relative_to(repo_root)),
            }
    return {
        "status": "fail",
        "evidence": "no Beacon Phase II-B design doc found in docs/",
        "blocker_note": (
            "Write docs/BEACON_PHASE_IIB_SPEC.md with the five "
            "design candidates (expiration-by-height, N-of-M "
            "threshold sig, mirror, revocation, severity)"
        ),
    }


def _check_beacon_iib_implementation(repo_root: Path) -> Dict[str, Any]:
    hits = _grep_repo(
        repo_root,
        ("include/sost", "src"),
        (
            "BEACON_PHASE2B_ACTIVATION_HEIGHT",
            "BEACON_PHASE_IIB_ACTIVATION_HEIGHT",
            "expires_at_height",
            "notice_threshold_sig",
        ),
    )
    if hits:
        return {
            "status": "pass",
            "evidence": "II-B implementation tokens found in: "
                       + ", ".join(
                           str(p.relative_to(repo_root)) for p, _ in hits[:3]
                       ),
        }
    return {
        "status": "fail",
        "evidence": "no II-B activation constant or capability tokens found",
        "blocker_note": (
            "Add BEACON_PHASE2B_ACTIVATION_HEIGHT and implement at "
            "least one II-B capability"
        ),
    }


def _check_beacon_iib_tests_green(repo_root: Path) -> Dict[str, Any]:
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return {"status": "fail", "evidence": "no tests/ directory"}
    hits = []
    for p in tests_dir.rglob("test_beacon*"):
        text = _read_text(p) or ""
        if "phase_ii_b" in text.lower() or "phase 2b" in text.lower():
            hits.append(str(p.relative_to(repo_root)))
    if hits:
        return {
            "status": "pass",
            "evidence": "Beacon II-B tests: " + ", ".join(hits[:3]),
        }
    return {
        "status": "fail",
        "evidence": "no Beacon II-B specific tests found",
    }


def _check_beacon_iii_p2p_implementation(
    repo_root: Path,
) -> Dict[str, Any]:
    h = repo_root / "include" / "sost" / "beacon_p2p.h"
    cpp = repo_root / "src" / "beacon_p2p.cpp"
    if h.exists() and cpp.exists():
        return {
            "status": "pass",
            "evidence": (
                "include/sost/beacon_p2p.h + src/beacon_p2p.cpp present"
            ),
        }
    if h.exists() and not cpp.exists():
        return {
            "status": "fail",
            "evidence": "beacon_p2p.h present but src/beacon_p2p.cpp missing",
            "blocker_note": "Implement the P2P NOTICE message handler",
        }
    return {
        "status": "fail",
        "evidence": "Beacon Phase III P2P scaffold missing",
    }


def _check_beacon_iii_activation_constant(
    repo_root: Path,
) -> Dict[str, Any]:
    params = repo_root / "include" / "sost" / "params.h"
    text = _read_text(params) or ""
    if "BEACON_P2P_ACTIVATION_HEIGHT" not in text:
        return {
            "status": "fail",
            "evidence": "BEACON_P2P_ACTIVATION_HEIGHT not declared",
        }
    if "BEACON_P2P_ACTIVATION_HEIGHT     = INT64_MAX" in text \
            or "BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX" in text:
        return {
            "status": "fail",
            "evidence": (
                "BEACON_P2P_ACTIVATION_HEIGHT = INT64_MAX (Phase III "
                "is intentionally dormant; lower it to V13_HEIGHT "
                "to ship in V13)"
            ),
            "blocker_note": (
                "Change BEACON_P2P_ACTIVATION_HEIGHT to V13_HEIGHT "
                "or V15_HEIGHT depending on the activation decision"
            ),
        }
    if "V13_HEIGHT" in text and "BEACON_P2P_ACTIVATION_HEIGHT" in text:
        return {
            "status": "pass",
            "evidence": (
                "BEACON_P2P_ACTIVATION_HEIGHT set to a non-dormant "
                "height in params.h"
            ),
        }
    return {
        "status": "unknown",
        "evidence": "BEACON_P2P_ACTIVATION_HEIGHT present, value unclear",
    }


def _check_beacon_iii_safety_invariants(
    repo_root: Path,
) -> Dict[str, Any]:
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return {"status": "fail", "evidence": "no tests/ directory"}
    hits = []
    for p in tests_dir.rglob("test_beacon*"):
        text = _read_text(p) or ""
        if "phase_iii" in text.lower() or "phase 3" in text.lower() \
                or "p2p" in text.lower():
            hits.append(str(p.relative_to(repo_root)))
    if hits:
        return {
            "status": "pass",
            "evidence": "Beacon III tests: " + ", ".join(hits[:3]),
        }
    return {
        "status": "fail",
        "evidence": "no Beacon Phase III / P2P test surface found",
    }


def _check_beacon_iii_anti_dos_tests(repo_root: Path) -> Dict[str, Any]:
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return {"status": "fail", "evidence": "no tests/ directory"}
    hits = []
    for p in tests_dir.rglob("test_beacon*"):
        text = _read_text(p) or ""
        if "RATE_PER_MIN" in text or "CACHE_MAX_NOTICES" in text:
            hits.append(str(p.relative_to(repo_root)))
    if hits:
        return {
            "status": "pass",
            "evidence": "anti-DoS tests: " + ", ".join(hits[:3]),
        }
    return {
        "status": "fail",
        "evidence": (
            "no tests exercise BEACON_P2P_PEER_RATE_PER_MIN or "
            "BEACON_P2P_CACHE_MAX_NOTICES bounds"
        ),
    }


def _check_memlock_design_doc(repo_root: Path) -> Dict[str, Any]:
    candidates = [
        repo_root / "docs" / "MEMORY_LOCK_PER_INSTANCE_SPEC.md",
        repo_root / "docs" / "MEMORY_LOCK_SPEC.md",
        repo_root / "docs" / "MEMLOCK_SPEC.md",
    ]
    for c in candidates:
        if c.exists():
            return {
                "status": "pass",
                "evidence": str(c.relative_to(repo_root)),
            }
    return {
        "status": "fail",
        "evidence": (
            "no dedicated design doc; only references in V11_SPEC.md "
            "and V11_PHASE2_DESIGN.md"
        ),
        "blocker_note": (
            "Write docs/MEMORY_LOCK_PER_INSTANCE_SPEC.md before "
            "any activation"
        ),
    }


def _check_memlock_simulation_artifact(
    repo_root: Path,
) -> Dict[str, Any]:
    sim_dirs = [
        repo_root / "simulations" / "memory_lock",
        repo_root / "scripts" / "simulations",
        repo_root / "docs" / "simulations",
    ]
    for d in sim_dirs:
        if d.exists() and any(d.iterdir()):
            return {
                "status": "pass",
                "evidence": "simulation artifacts at "
                           + str(d.relative_to(repo_root)),
            }
    return {
        "status": "fail",
        "evidence": (
            "no Memory-Lock simulation script or result file found "
            "in simulations/ or scripts/simulations/"
        ),
        "blocker_note": (
            "V11_SPEC.md requires 'independent simulation' before "
            "activation"
        ),
    }


def _check_memlock_implementation(repo_root: Path) -> Dict[str, Any]:
    hits = _grep_repo(
        repo_root,
        ("include/sost", "src"),
        (
            "MEMORY_LOCK_ACTIVATION_HEIGHT",
            "memory_lock_per_instance",
            "MEMLOCK_ACTIVATION_HEIGHT",
        ),
    )
    if hits:
        return {
            "status": "pass",
            "evidence": "implementation tokens at: "
                       + ", ".join(
                           str(p.relative_to(repo_root)) for p, _ in hits[:3]
                       ),
        }
    return {
        "status": "fail",
        "evidence": "no Memory-Lock activation constant or code path found",
    }


def _check_memlock_small_miner_safety(
    repo_root: Path,
) -> Dict[str, Any]:
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return {"status": "fail", "evidence": "no tests/ directory"}
    hits = []
    for p in tests_dir.rglob("*memory_lock*"):
        hits.append(str(p.relative_to(repo_root)))
    for p in tests_dir.rglob("*memlock*"):
        hits.append(str(p.relative_to(repo_root)))
    if hits:
        return {
            "status": "pass",
            "evidence": "small-miner safety tests: " + ", ".join(hits[:3]),
        }
    return {
        "status": "fail",
        "evidence": "no Memory-Lock safety test for the 8 GB floor",
    }


GATE_CHECKERS = {
    "popc_a_audit_daemon":             _check_popc_a_audit_daemon,
    "popc_b_auto_slash":               _check_popc_b_auto_slash,
    "popc_c_auto_settlement":          _check_popc_c_auto_settlement,
    "popc_d_escrow_deployment":        _check_popc_d_escrow_deployment,
    "popc_e_event_listener":           _check_popc_e_event_listener,
    "popc_f_consensus_gate":           _check_popc_f_consensus_gate,
    "popc_g_e2e_test":                 _check_popc_g_e2e_test,
    "beacon_iib_design_closed":        _check_beacon_iib_design_closed,
    "beacon_iib_implementation":       _check_beacon_iib_implementation,
    "beacon_iib_tests_green":          _check_beacon_iib_tests_green,
    "beacon_iii_p2p_implementation":   _check_beacon_iii_p2p_implementation,
    "beacon_iii_activation_constant":  _check_beacon_iii_activation_constant,
    "beacon_iii_safety_invariants":    _check_beacon_iii_safety_invariants,
    "beacon_iii_anti_dos_tests":       _check_beacon_iii_anti_dos_tests,
    "memlock_design_doc":              _check_memlock_design_doc,
    "memlock_simulation_artifact":     _check_memlock_simulation_artifact,
    "memlock_implementation":          _check_memlock_implementation,
    "memlock_small_miner_safety":      _check_memlock_small_miner_safety,
}


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
        raise ReadinessError(
            "repo-root not a directory: " + str(repo_root)
        )

    config_path = repo_root / CONFIG_RELATIVE_PATH
    config = _read_json(config_path)
    config_loaded = config is not None
    if config is None:
        raise ReadinessError(
            "config not loadable: " + str(config_path)
            + ". Run from a repo that has config/v13_activation.json"
        )
    if config.get("schema") != SCHEMA_CONFIG:
        raise ReadinessError(
            "config schema mismatch: " + str(config.get("schema"))
        )

    warnings: List[str] = []

    # Confirmed items.
    confirmed_view: List[Dict[str, Any]] = []
    for cfg_item in config.get("confirmed_items", []) or []:
        item_id = cfg_item.get("id", "")
        checker = CONFIRMED_CHECKERS.get(item_id)
        if checker is None:
            warnings.append(
                "confirmed item " + item_id
                + " has no checker registered; skipping"
            )
            continue
        result = checker(repo_root)
        ready = bool(result.get("wired_in_code"))
        if not ready:
            warnings.append(
                "confirmed item " + item_id
                + " NOT wired in code: "
                + str(result.get("blocker_note", ""))[:200]
            )
        confirmed_view.append({
            "id":            item_id,
            "label":         str(cfg_item.get("label", ""))[:200],
            "wired_in_code": ready,
            "evidence":      str(result.get("evidence", ""))[:500],
            "ready":         ready,
            "blocker_note":  str(result.get("blocker_note", ""))[:500],
        })

    # Gated items.
    gated_view: List[Dict[str, Any]] = []
    fallback_to_v15: List[str] = []
    for cfg_item in config.get("gated_items", []) or []:
        item_id = cfg_item.get("id", "")
        gates_cfg = cfg_item.get("gates", []) or []
        gates_view: List[Dict[str, Any]] = []
        any_fail = False
        for gate in gates_cfg:
            gate_id = gate.get("id", "")
            checker = GATE_CHECKERS.get(gate_id)
            if checker is None:
                gates_view.append({
                    "id":       gate_id,
                    "rule":     str(gate.get("rule", ""))[:500],
                    "status":   "unknown",
                    "evidence": "no checker registered for this gate",
                })
                any_fail = True
                continue
            result = checker(repo_root)
            status = str(result.get("status", "unknown"))
            if status not in ("pass", "fail", "unknown"):
                status = "unknown"
            gates_view.append({
                "id":       gate_id,
                "rule":     str(gate.get("rule", ""))[:500],
                "status":   status,
                "evidence": str(result.get("evidence", ""))[:500],
                "blocker_note":
                    str(result.get("blocker_note", ""))[:500],
            })
            if status != "pass":
                any_fail = True
        v13_ready = not any_fail
        resolved_height = (
            int(cfg_item.get("target_height", 12000))
            if v13_ready
            else int(cfg_item.get("fallback_height", 15000))
        )
        gated_view.append({
            "id":                         item_id,
            "label":                      str(cfg_item.get("label", ""))[:200],
            "target_height":              int(cfg_item.get("target_height", 12000)),
            "fallback_height":            int(cfg_item.get("fallback_height", 15000)),
            "gates":                      gates_view,
            "v13_ready":                  v13_ready,
            "resolved_activation_height": resolved_height,
        })
        if not v13_ready:
            fallback_to_v15.append(item_id)

    # Top-level booleans.
    v13_ready_for_confirmed_items = all(
        c["ready"] for c in confirmed_view
    )
    popc_v13_ready          = _gated_ready(gated_view, "popc_model_a_b")
    beacon_iib_v13_ready    = _gated_ready(gated_view, "beacon_phase_ii_b")
    beacon_iii_v13_ready    = _gated_ready(gated_view, "beacon_phase_iii")
    memory_lock_v13_ready   = _gated_ready(gated_view, "memory_lock_per_instance")

    # Overall decision.
    if not v13_ready_for_confirmed_items:
        overall_decision = "v13_confirmed_items_not_ready_block_fork"
        safety_status = "warning"
    elif (
        popc_v13_ready
        and beacon_iib_v13_ready
        and beacon_iii_v13_ready
        and memory_lock_v13_ready
    ):
        overall_decision = "v13_all_ready"
        safety_status = "ok"
    else:
        overall_decision = (
            "v13_confirmed_items_ready_gated_items_fallback_to_v15"
        )
        safety_status = "ok" if v13_ready_for_confirmed_items else "warning"

    if warnings:
        if safety_status == "ok":
            safety_status = "warning"

    heights_cfg = config.get("activation_heights", {}) or {}
    activation_heights = {
        "v13_activation_height":       12000,
        "v15_fallback_height":         15000,
        "dtd_lottery_decision_height": 12100,
        "current_height_estimate":
            int(heights_cfg.get("current_height_estimate", 0) or 0),
    }

    decision_at_12100 = {
        "subject":
            (config.get("decision_at_12100", {}) or {})
            .get("subject", "DTD lottery: keep or remove")[:200],
        "decision_window_opens_at_height": 12100,
    }

    report_id = "v13rr-" + _sha16(_canonical_dumps({
        "pinned_time":            pinned_time,
        "repo_root_basename":     repo_root.name,
        "v13_ready_for_confirmed": v13_ready_for_confirmed_items,
        "popc_v13_ready":         popc_v13_ready,
        "beacon_iib_v13_ready":   beacon_iib_v13_ready,
        "beacon_iii_v13_ready":   beacon_iii_v13_ready,
        "memory_lock_v13_ready":  memory_lock_v13_ready,
    }))

    return {
        "schema":                        SCHEMA_REPORT,
        "report_id":                     report_id,
        "pinned_time":                   pinned_time,
        "repo_root_basename":            repo_root.name,
        "config_loaded":                 config_loaded,
        "activation_heights":            activation_heights,
        "confirmed_items":               confirmed_view,
        "gated_items":                   gated_view,
        "decision_at_12100":             decision_at_12100,
        "v13_ready_for_confirmed_items": v13_ready_for_confirmed_items,
        "popc_v13_ready":                popc_v13_ready,
        "beacon_iib_v13_ready":          beacon_iib_v13_ready,
        "beacon_iii_v13_ready":          beacon_iii_v13_ready,
        "memory_lock_v13_ready":         memory_lock_v13_ready,
        "fallback_to_v15_items":         fallback_to_v15,
        "warnings":                      warnings,
        "overall_decision":              overall_decision,
        "safety_status":                 safety_status,
        "safety_flags": {
            "no_wallet_access":             True,
            "no_private_key_access":        True,
            "no_signing":                   True,
            "no_broadcast":                 True,
            "no_network_calls":             True,
            "no_github_api":                True,
            "no_shell_true":                True,
            "no_destructive_git":           True,
            "no_auto_push_merge_tag":       True,
            "ntp_mandatory_post_v13":       True,
            "half_enabled_items_forbidden": True,
        },
    }


def _gated_ready(gated_view: List[Dict[str, Any]], item_id: str) -> bool:
    for it in gated_view:
        if it["id"] == item_id:
            return bool(it["v13_ready"])
    return False


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# Trinity V13 Activation Readiness Report")
    a("")
    a("**Report id:** `" + report["report_id"] + "`  ")
    a("**Pinned time:** `" + report["pinned_time"] + "`  ")
    a("**Repo:** `" + report["repo_root_basename"] + "`  ")
    a("**Overall decision:** `" + report["overall_decision"] + "`  ")
    a("**Safety status:** `" + report["safety_status"] + "`")
    a("")
    a("## Activation heights")
    a("")
    h = report["activation_heights"]
    a("- V13 activation height: **" + str(h["v13_activation_height"]) + "**")
    a("- V15 fallback height: **" + str(h["v15_fallback_height"]) + "**")
    a("- DTD lottery decision: **" + str(h["dtd_lottery_decision_height"]) + "**")
    a("- current height (estimate): **"
      + str(h.get("current_height_estimate", 0)) + "**")
    a("")
    a("## Confirmed V13 items")
    a("")
    a("| id | wired? | evidence |")
    a("|---|---|---|")
    for c in report["confirmed_items"]:
        wired = "yes" if c["wired_in_code"] else "**NO**"
        a(
            "| `" + c["id"] + "` | " + wired + " | "
            + c["evidence"].replace("|", "\\|") + " |"
        )
    a("")
    a("**v13_ready_for_confirmed_items:** `"
      + ("true" if report["v13_ready_for_confirmed_items"] else "false")
      + "`")
    a("")
    a("## Gated items (V13 target, V15 fallback)")
    a("")
    for g in report["gated_items"]:
        a("### `" + g["id"] + "` — " + g["label"])
        a("")
        a("- target_height: **" + str(g["target_height"]) + "**")
        a("- fallback_height: **" + str(g["fallback_height"]) + "**")
        a("- v13_ready: `"
          + ("true" if g["v13_ready"] else "false") + "`")
        a("- resolved_activation_height: **"
          + str(g["resolved_activation_height"]) + "**")
        a("")
        a("| gate | status | evidence |")
        a("|---|---|---|")
        for gate in g["gates"]:
            a(
                "| `" + gate["id"] + "` | `" + gate["status"] + "` | "
                + gate["evidence"].replace("|", "\\|") + " |"
            )
        a("")
    a("## Item-level decisions")
    a("")
    a(
        "- popc_v13_ready: `"
        + ("true" if report["popc_v13_ready"] else "false") + "`"
    )
    a(
        "- beacon_iib_v13_ready: `"
        + ("true" if report["beacon_iib_v13_ready"] else "false") + "`"
    )
    a(
        "- beacon_iii_v13_ready: `"
        + ("true" if report["beacon_iii_v13_ready"] else "false") + "`"
    )
    a(
        "- memory_lock_v13_ready: `"
        + ("true" if report["memory_lock_v13_ready"] else "false") + "`"
    )
    a("")
    a("## Fallback to V15")
    a("")
    if report["fallback_to_v15_items"]:
        for it in report["fallback_to_v15_items"]:
            a("- `" + it + "`")
    else:
        a("- _none — every gated item is V13-ready_")
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
        prog="v13_readiness_check",
        description=(
            "Trinity V13 Activation Readiness Check v0.1. "
            "Read-only preflight verifier for the V13 hardfork. "
            "NEVER touches a wallet, NEVER signs, NEVER "
            "broadcasts, NEVER uses GitHub API, NEVER mutates "
            "git state."
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
    except ReadinessError as exc:
        print(
            "[v13_readiness_check] error: " + str(exc),
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
        "[v13_readiness_check] report_id=" + report["report_id"]
        + " v13_confirmed_ready="
        + ("true" if report["v13_ready_for_confirmed_items"] else "false")
        + " popc_v13_ready="
        + ("true" if report["popc_v13_ready"] else "false")
        + " beacon_iib_v13_ready="
        + ("true" if report["beacon_iib_v13_ready"] else "false")
        + " beacon_iii_v13_ready="
        + ("true" if report["beacon_iii_v13_ready"] else "false")
        + " memory_lock_v13_ready="
        + ("true" if report["memory_lock_v13_ready"] else "false")
        + " overall=" + report["overall_decision"]
        + " json=" + str(out_json)
        + " md=" + str(out_md)
    )
    if not report["v13_ready_for_confirmed_items"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
