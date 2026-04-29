#!/usr/bin/env python3
"""validate_miner_onboarding_pages.py — sanity checks for the public
mining onboarding pages and the install script.

Run from the repo root:

    python3 scripts/validate_miner_onboarding_pages.py

Exits non-zero if any required page is missing, or if any page contains
banned wording (profit promise, key/seed prompts, dangerous shell
patterns, leaked personal email or AI attribution).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "website"

REQUIRED_PAGES = [
    "sost-mine.html",
    "sost-why-no-pools.html",
    "sost-mining-calculator.html",
    "sost-network-status.html",
    "install-sost.sh",
]

# Phrases we never want to ship publicly.
BANNED_PHRASES = [
    "guaranteed profit",
    "guaranteed earnings",
    "guaranteed return",
    "passive income",
    "risk free",
    "risk-free",
    "no risk",
    "private key",          # the install script must not ask for one
    "seed phrase",          # nor a seed phrase
    "wallet.dat",           # nor read a wallet file
    "fernandezmoneo",       # personal email / handle leak
    "Co-Authored-By: Claude",
    "Co-Authored-By: Anthropic",
    "claude.ai",
    "Anthropic",
]

# Phrases we expect to find in specific pages (positive checks).
REQUIRED_IN = {
    "sost-mining-calculator.html": [
        "variance",
        "Solo mining",
        "pre-market",
    ],
    "sost-mine.html": [
        "inspect",                          # tells users to inspect the script
        "install-sost.sh",
        "memory-bandwidth",                 # threads warning
    ],
    "sost-why-no-pools.html": [
        "Solo",
        "variance",
    ],
    "install-sost.sh": [
        "set -euo pipefail",
        "never asked for",
        "private key",                      # in the safety statement, not as a prompt
    ],
}

# Patterns the install script must NOT contain.
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/(?!tmp/)",              # any rm -rf / except /tmp
    r"\bsudo\s+rm\s+-rf\b",                  # never sudo rm -rf in the installer
    r"\bcurl\s+[^|]*\|\s*sudo\s+bash",      # never curl | sudo bash inside the script
]


def fail(msg: str) -> None:
    print(f"  FAIL: {msg}", file=sys.stderr)


def check_required_pages() -> int:
    errs = 0
    print("== required pages ==")
    for name in REQUIRED_PAGES:
        path = WEB / name
        if not path.exists():
            fail(f"missing: {path}")
            errs += 1
        else:
            print(f"  ok: {name}")
    return errs


def check_banned() -> int:
    errs = 0
    print("\n== banned phrases (scoped to miner onboarding pages) ==")
    # Only scan the pages this script is responsible for. Other pages
    # (wallet, security, useful-compute) legitimately discuss private
    # keys / seed phrases inside their own safety disclaimers.
    scoped_pages = [WEB / name for name in REQUIRED_PAGES if name.endswith(".html")]
    for path in scoped_pages:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for phrase in BANNED_PHRASES:
            if phrase.lower() in text.lower():
                lc = phrase.lower()
                ok_contexts = [
                    "never asked for",
                    "never reads or writes any private key",
                    "never asks for, reads or writes",
                    "without a custodian",
                    "no obligation",
                    "this script never asks for",
                    "the script never asks for",
                    "does not ask for private",
                    "does not ask for, read or write any private",
                    "private key or seed phrase",
                    "the wallet file is stored locally",  # mine page step 1
                ]
                near = text.lower()
                bad = False
                for m in re.finditer(re.escape(lc), near):
                    start = max(0, m.start() - 160)
                    end = min(len(near), m.end() + 80)
                    context = near[start:end]
                    if any(ok in context for ok in ok_contexts):
                        continue
                    bad = True
                    fail(f"{path.name}: '{phrase}' near …{context.strip()}…")
                    errs += 1
                    break
                if not bad:
                    print(f"  ok: {path.name} mentions '{phrase}' only in safety context")
    # also scan install script
    inst = WEB / "install-sost.sh"
    if inst.exists():
        text = inst.read_text(encoding="utf-8", errors="replace")
        for phrase in BANNED_PHRASES:
            lc = phrase.lower()
            if lc in text.lower():
                # Same whitelist: the safety section explicitly says it
                # never touches private keys, seed phrases or wallet files.
                ok_contexts = [
                    "never asks for, reads, or writes",
                    "never ask for, read or write",
                    "never asks for or stores",
                    "never asked for, read, or wrote",
                    "no private key",
                    "you remain in control of your keys",
                ]
                bad = False
                for m in re.finditer(re.escape(lc), text.lower()):
                    start = max(0, m.start() - 160)
                    end = min(len(text), m.end() + 60)
                    context = text.lower()[start:end]
                    if any(ok in context for ok in ok_contexts):
                        continue
                    bad = True
                    fail(f"install-sost.sh: '{phrase}' near …{context.strip()}…")
                    errs += 1
                    break
    return errs


def check_required_in() -> int:
    errs = 0
    print("\n== positive content checks ==")
    for name, needles in REQUIRED_IN.items():
        path = WEB / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle.lower() not in text.lower():
                fail(f"{name}: missing required phrase '{needle}'")
                errs += 1
            else:
                print(f"  ok: {name} contains '{needle}'")
    return errs


def check_install_script_safety() -> int:
    errs = 0
    print("\n== install script safety ==")
    inst = WEB / "install-sost.sh"
    if not inst.exists():
        fail("install-sost.sh missing")
        return 1
    text = inst.read_text(encoding="utf-8", errors="replace")
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, text):
            fail(f"install-sost.sh: dangerous pattern matched: {pat}")
            errs += 1
    if errs == 0:
        print("  ok: no dangerous shell patterns")
    return errs


def main() -> int:
    if not WEB.is_dir():
        print(f"website directory not found: {WEB}", file=sys.stderr)
        return 2
    total = 0
    total += check_required_pages()
    total += check_banned()
    total += check_required_in()
    total += check_install_script_safety()
    print()
    if total == 0:
        print("All miner onboarding pages pass the safety checks.")
        return 0
    print(f"{total} issue(s) found.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
