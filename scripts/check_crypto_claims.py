#!/usr/bin/env python3
"""
check_crypto_claims.py — SOST cryptography-claim linter.

Flags dangerous or false cryptography claims in documentation and web copy, so
the repo never ships text asserting that SOST is post-quantum secure, that
transactions use Schnorr, that ML-KEM signs, that ML-DSA/Dilithium is active on
mainnet, that PQ is enabled, or that the crypto has been externally audited —
none of which are true today.

TRUTH (mainnet, verified):
  - Spend signatures: ECDSA secp256k1, compact 64-byte, canonical LOW-S.
  - BIP-340 Schnorr: SbPoW block-identity binding ONLY (not spend).
  - Post-quantum: NOT active. Under research/prototype/testnet only.
  - No external audit of the crypto has been performed.

The linter is deliberately conservative: an affirmative dangerous phrase is only
flagged when it is NOT accompanied by a nearby negation / research qualifier
(not / no / under research / roadmap / planned / future / would / prototype /
testnet / reserved / not active / target). Documented exceptions live in
ALLOWLIST.

Exit code: 0 = clean, 1 = at least one un-allowlisted violation. Intended for CI
signal; it does not modify files.

Author: NeoB.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_EXT = (".md", ".html", ".htm", ".txt")
SKIP_DIRS = {
    ".git", "vendor", "third_party", "node_modules", "backups", ".venv",
}
SKIP_DIR_PREFIXES = ("build",)  # build*, build-ci, ...

# Qualifiers that make a nearby dangerous phrase acceptable (honest/negated).
QUALIFIER = re.compile(
    r"\b(not|no|never|isn't|is not|are not|under research|research|roadmap|"
    r"planned|plan|future|would|will|proposed|prototype|testnet|reserved|"
    r"target|migration|not active|not yet|aspirational|goal|intend)\b",
    re.IGNORECASE,
)

# (name, regex) — affirmative dangerous claims.
PATTERNS = [
    ("quantum_safe",        re.compile(r"\bSOST\s+is\s+(?:now\s+)?quantum[- ]safe\b", re.I)),
    ("quantum_safe_generic", re.compile(r"\bis\s+quantum[- ]safe\b", re.I)),
    ("post_quantum_secure", re.compile(r"\b(?:is\s+)?post[- ]quantum\s+secure\b", re.I)),
    ("tx_use_schnorr",      re.compile(r"\b(?:transaction|tx|spend|spending)s?\s+(?:are\s+)?(?:use|signed\s+with|using)\s+schnorr\b", re.I)),
    ("mlkem_signature",     re.compile(r"\bML[- ]?KEM\b.{0,20}\bsignatur", re.I)),
    ("mlkem_signs",         re.compile(r"\bML[- ]?KEM\b.{0,10}\bsign(?:s|ing|ature)?\b", re.I)),
    ("dilithium_active",    re.compile(r"\b(?:dilithium|ML[- ]?DSA)\b.{0,30}\b(?:active|enabled|live)\b.{0,20}\bmainnet\b", re.I)),
    ("mldsa_active_generic", re.compile(r"\bML[- ]?DSA\s+is\s+(?:now\s+)?(?:active|enabled|live)\b", re.I)),
    ("pq_enabled",          re.compile(r"\b(?:PQ|post[- ]quantum)\s+(?:is\s+)?enabled\b", re.I)),
    ("externally_audited",  re.compile(r"\b(?:externally|independently)\s+audited\b", re.I)),
]

# Documented, reviewed exceptions: (path-substring, phrase-substring lowercased).
# Only add here with a written justification in the PR.
ALLOWLIST = [
    # This linter file itself names the forbidden phrases to define them.
    ("scripts/check_crypto_claims.py", None),
    # The manifest / sync docs quote the forbidden phrases to forbid them.
    ("docs/WHITEPAPER_MANIFEST.md", None),
    ("scripts/check_whitepaper_sync.py", None),
    # ADR-005 (no-activation) and ADR-006 (this very linter / claims policy) are
    # meta-documents: they quote the forbidden phrases in order to prohibit them.
    ("docs/ADR/ADR-005-no-mainnet-activation-yet.md", None),
    ("docs/ADR/ADR-006-whitepaper-as-code.md", None),
    # The audit checklist enumerates claims that must NOT appear once activated.
    ("docs/PQ_AUDIT_CHECKLIST_V3.md", None),
]


def allowlisted(relpath, line):
    low = line.lower()
    for sub, phrase in ALLOWLIST:
        if sub in relpath and (phrase is None or phrase in low):
            return True
    return False


def scan_file(path, relpath):
    findings = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return findings
    for i, line in enumerate(lines, 1):
        if allowlisted(relpath, line):
            continue
        for name, pat in PATTERNS:
            if pat.search(line):
                # Accept if a qualifier appears on the same or adjacent line.
                window = line
                if i >= 2:
                    window = lines[i - 2] + window
                if i < len(lines):
                    window = window + lines[i]
                if QUALIFIER.search(window):
                    continue
                findings.append((i, name, line.strip()[:160]))
    return findings


def main():
    total = 0
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and not d.startswith(SKIP_DIR_PREFIXES)]
        for fn in files:
            if not fn.endswith(SCAN_EXT):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, REPO)
            for lineno, name, text in scan_file(path, rel):
                total += 1
                print(f"{rel}:{lineno}: [{name}] {text}")
    if total:
        print(f"\ncheck_crypto_claims: {total} dangerous claim(s) found.", file=sys.stderr)
        print("Fix the copy or add a justified ALLOWLIST entry.", file=sys.stderr)
        return 1
    print("check_crypto_claims: OK (no dangerous crypto claims found).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
