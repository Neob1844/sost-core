#!/usr/bin/env python3
"""import_public_help_pack.py — copy a reviewed public help pack from
the private repo into website/data/.

This is the manual M9-C bridge between the private exporter and the
public website. It does NOT auto-deploy, NOT git-add, NOT commit, and
NOT push. It only validates the pack and copies the two JSON files
the website actually serves.

Usage:

    python3 scripts/import_public_help_pack.py \\
        --pack-dir ~/SOST/materials-engine-private/reports/ai_engine/approved_public_help/<id>

By default the script refuses to copy if:
  - the pack directory does not exist
  - any required file is missing
  - safety_manifest.json reports any blocked items
  - checksums.sha256 does not match the file contents
  - any banned phrase is detected in public_help.md or the JSON files
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "website" / "data"


REQUIRED_PACK_FILES = (
    "public_help_index.json",
    "public_help_index.min.json",
    "public_help.md",
    "miner_troubleshooting.json",
    "faq.json",
    "safety_manifest.json",
    "source_manifest.json",
    "checksums.sha256",
)


# Same banned-phrase list as the private validator. Kept in sync by
# inspection; if you change one, change both.
BANNED_PHRASES = (
    r"\bguaranteed\s+(?:profit|earnings|return)\b",
    r"\bpassive\s+income\b",
    r"\buseful\s+compute\s+rewards?\s+(?:are|is)\s+(?:active|live|enabled)\b",
    r"\b(?:confirmed|guaranteed)\s+mineral\b",
    r"\bDFT[-\s]?validated\b",
    r"\bfully\s+trustless\s+(?:dex|exchange)\b",
    r"\bsend\s+(?:your|me|us)?\s*(?:private\s+key|seed\s+phrase)\b",
    r"\bpaste\s+(?:your)?\s*(?:private\s+key|seed\s+phrase)\b",
    r"fernandezmoneo",
    r"\bCo-Authored-By:\s*Claude\b",
    r"\bAnthropic\b",
)


def fail(errs: List[str], msg: str) -> None:
    errs.append(msg)


def check_required(pack: Path, errs: List[str]) -> None:
    for name in REQUIRED_PACK_FILES:
        if not (pack / name).exists():
            fail(errs, f"missing in pack: {name}")


def check_safety_manifest(pack: Path, errs: List[str]) -> None:
    p = pack / "safety_manifest.json"
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(errs, f"safety_manifest.json is not JSON: {exc}")
        return
    n_blocked = int(data.get("n_blocked_unsafe", 0))
    if n_blocked > 0:
        fail(errs, f"safety_manifest reports {n_blocked} blocked-unsafe items — refusing import")


def check_checksums(pack: Path, errs: List[str]) -> None:
    cs = pack / "checksums.sha256"
    if not cs.exists():
        fail(errs, "checksums.sha256 missing — refusing import")
        return
    for line in cs.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            fail(errs, f"malformed checksum line: {line!r}")
            continue
        want, name = parts
        target = pack / name
        if not target.exists():
            fail(errs, f"checksum entry refers to missing file: {name}")
            continue
        got = hashlib.sha256(target.read_bytes()).hexdigest()
        if got != want:
            fail(errs, f"checksum mismatch for {name}: want {want[:12]} got {got[:12]}")


def check_banned(pack: Path, errs: List[str]) -> None:
    targets = [
        "public_help.md",
        "public_help_index.json",
        "public_help_index.min.json",
        "faq.json",
        "miner_troubleshooting.json",
    ]
    for name in targets:
        p = pack / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for pat in BANNED_PHRASES:
            if re.search(pat, text, re.IGNORECASE):
                fail(errs, f"banned phrase {pat!r} matched in {name}")


def copy_pack(pack: Path) -> List[Path]:
    """Copy the two JSON files the website serves. Returns the list
    of destination paths."""
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    dests: List[Path] = []
    plan = [
        (pack / "public_help_index.min.json", WEB_DATA / "public_help_index.json"),
        (pack / "public_help_index.json",     WEB_DATA / "public_help_full.json"),
        (pack / "miner_troubleshooting.json", WEB_DATA / "miner_troubleshooting.json"),
    ]
    for src, dst in plan:
        if not src.exists():
            continue
        shutil.copyfile(src, dst)
        dests.append(dst)
    return dests


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="import_public_help_pack",
        description="Copy a reviewed help pack from the private repo into website/data/.",
    )
    p.add_argument("--pack-dir", required=True,
                   help="Path to the approved_public_help/<id> directory in the private repo.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate the pack but do not copy any file.")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    pack = Path(args.pack_dir).expanduser().resolve()
    if not pack.is_dir():
        print(f"not a directory: {pack}", file=sys.stderr)
        return 2

    errs: List[str] = []
    print(f"validating pack: {pack}")
    check_required(pack, errs)
    check_safety_manifest(pack, errs)
    check_checksums(pack, errs)
    check_banned(pack, errs)

    if errs:
        print("REFUSING IMPORT — issues found:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("DRY-RUN OK — pack would be copied. Re-run without --dry-run to import.")
        return 0

    dests = copy_pack(pack)
    print()
    print("Imported files (no git-add, no commit, no deploy):")
    for d in dests:
        print(f"  -> {d.relative_to(ROOT)}")
    print()
    print("Next steps:")
    print("  1. Review the diff:    git diff -- website/data/")
    print("  2. Verify pages load:  open website/sost-help.html in a browser")
    print("  3. Validator pass:     python3 scripts/validate_public_help_pages.py")
    print("  4. Commit when happy:  git add website/data/ && git commit -m '...'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
