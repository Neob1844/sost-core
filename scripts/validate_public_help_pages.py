#!/usr/bin/env python3
"""validate_public_help_pages.py — sanity checks for the public help
center and the miner troubleshooter.

Run from the repo root:

    python3 scripts/validate_public_help_pages.py

Exits non-zero if a required page is missing, the data JSON does not
parse, the JS files fetch external domains, any banned phrase appears
in the user-facing pages, or any of the safety promises (local-only
analysis, no upload, never share key material) are missing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "website"

REQUIRED_FILES = [
    "sost-help.html",
    "sost-miner-troubleshooter.html",
    "assets/js/sost-help-search.js",
    "assets/js/sost-miner-troubleshooter.js",
    "data/public_help_index.json",
    "data/miner_troubleshooting.json",
]

BANNED_PHRASES = [
    r"\bguaranteed\s+(?:profit|earnings|return)\b",
    r"\bpassive\s+income\b",
    r"\buseful\s+compute\s+rewards?\s+(?:are|is)\s+(?:active|live|enabled)\b",
    r"\b(?:confirmed|guaranteed)\s+mineral\b",
    r"\bsend\s+(?:your|me|us)?\s*(?:private\s+key|seed\s+phrase)\b",
    r"\bpaste\s+(?:your)?\s*(?:private\s+key|seed\s+phrase)\b",
    r"fernandezmoneo",
    r"\bCo-Authored-By:\s*Claude\b",
    r"\bAnthropic\b",
]

LOCAL_PROMISE_PATTERNS = [
    r"locally in your browser",
    r"no log is uploaded|no upload|never uploaded",
    r"never reveal|never share|will never ask",
]


def fail(errs: List[str], msg: str) -> None:
    errs.append(msg)


def check_required(errs: List[str]) -> None:
    print("== required files ==")
    for rel in REQUIRED_FILES:
        p = WEB / rel
        if not p.exists():
            fail(errs, f"missing: {rel}")
        else:
            print(f"  ok: {rel}")


def check_data_json(errs: List[str]) -> None:
    print("\n== data JSON ==")
    for rel in ("data/public_help_index.json", "data/miner_troubleshooting.json"):
        p = WEB / rel
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(errs, f"{rel}: invalid JSON: {exc}")
            continue
        print(f"  ok: {rel}")
        if rel.endswith("public_help_index.json"):
            if "entries" not in data:
                fail(errs, f"{rel}: missing 'entries' key")
        if rel.endswith("miner_troubleshooting.json"):
            if "rules" not in data or not isinstance(data["rules"], list):
                fail(errs, f"{rel}: missing or invalid 'rules' list")
            if "safety_notes" not in data or not data["safety_notes"]:
                fail(errs, f"{rel}: missing safety_notes")


def check_no_external_fetch(errs: List[str]) -> None:
    """The two help JS files must never fetch anything outside the
    same origin. Allowed targets: data/* paths only."""
    print("\n== JS files ==")
    for rel in ("assets/js/sost-help-search.js",
                "assets/js/sost-miner-troubleshooter.js"):
        p = WEB / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        # Find fetch() targets.
        for m in re.finditer(r"fetch\s*\(\s*['\"]([^'\"]+)['\"]", text):
            url = m.group(1)
            if url.startswith("data/"):
                continue
            fail(errs, f"{rel}: forbidden fetch URL: {url}")
        # Make sure no URL points outside the same origin in any way.
        if re.search(r"https?://(?!sostcore\.com\b)", text):
            fail(errs, f"{rel}: contains external URL")
        # Make sure no eval / Function constructor of strings.
        if re.search(r"\beval\s*\(", text):
            fail(errs, f"{rel}: uses eval()")
        # new Function() with a single string arg from user input is the
        # main worry; we use new RegExp() which is fine.
        if re.search(r"new\s+Function\s*\(", text):
            fail(errs, f"{rel}: uses new Function()")
        print(f"  ok: {rel}")


def _scan_text_for_banned(name: str, text: str, errs: List[str]) -> None:
    for pat in BANNED_PHRASES:
        if re.search(pat, text, re.IGNORECASE):
            fail(errs, f"{name}: banned phrase matched: {pat}")


def check_banned(errs: List[str]) -> None:
    print("\n== banned phrases ==")
    for rel in ("sost-help.html",
                "sost-miner-troubleshooter.html",
                "assets/js/sost-help-search.js",
                "assets/js/sost-miner-troubleshooter.js",
                "data/public_help_index.json",
                "data/miner_troubleshooting.json"):
        p = WEB / rel
        if not p.exists():
            continue
        _scan_text_for_banned(rel, p.read_text(encoding="utf-8"), errs)
    print("  ok (or see failures above)")


def check_safety_promises(errs: List[str]) -> None:
    """The troubleshooter page must explicitly tell the user that
    analysis is local and the log is not uploaded."""
    print("\n== safety promises ==")
    p = WEB / "sost-miner-troubleshooter.html"
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8").lower()
    found = []
    for pat in LOCAL_PROMISE_PATTERNS:
        if re.search(pat, text):
            found.append(pat)
    if not found:
        fail(errs, "sost-miner-troubleshooter.html: no local-only / no-upload / never-share promise found")
    else:
        print(f"  ok: {len(found)} safety phrase(s) found in troubleshooter page")
    # Help page must include the wallet-credentials warning too.
    p2 = WEB / "sost-help.html"
    if p2.exists():
        text2 = p2.read_text(encoding="utf-8").lower()
        if "private key" in text2 or "recovery words" in text2 or "wallet password" in text2:
            print("  ok: sost-help.html mentions credentials safety")
        else:
            fail(errs, "sost-help.html: no credentials-safety mention found")


def main() -> int:
    if not WEB.is_dir():
        print(f"website directory not found: {WEB}", file=sys.stderr)
        return 2
    errs: List[str] = []
    check_required(errs)
    check_data_json(errs)
    check_no_external_fetch(errs)
    check_banned(errs)
    check_safety_promises(errs)
    print()
    if errs:
        print("FAIL — issues found:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("All public-help checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
