#!/usr/bin/env python3
"""
check_whitepaper_sync.py — "whitepaper as code" sync guard (ADR-006).

When a change touches consensus / transaction / crypto / prototype / wallet /
explorer surfaces, the documentation that describes them (the canonical
whitepaper tree, the PQ_* research docs, the ADRs, the CHANGELOG, or the web
docs) should be updated in the SAME change. This script compares a diff range
and warns (soft) or fails (--strict) when watched source paths changed but no
doc surface did.

It is a REVIEW AID, not a consensus gate. By default it prints a warning and
exits 0 so it never hard-blocks `main` without a human decision; run with
--strict in CI jobs that should fail the build.

Usage:
  python3 scripts/check_whitepaper_sync.py                 # vs origin/main
  python3 scripts/check_whitepaper_sync.py --base HEAD~1
  python3 scripts/check_whitepaper_sync.py --strict        # exit 1 on mismatch

Author: NeoB.
"""
import argparse
import subprocess
import sys

# Source surfaces whose changes should be reflected in the docs.
WATCHED_SRC = (
    "src/tx_signer", "src/tx_validation", "src/transaction", "src/block_validation",
    "src/sbpow", "src/mempool", "src/script", "src/wallet",
    "include/sost/transaction.h", "include/sost/consensus_constants.h",
    "include/sost/tx_validation.h", "include/sost/block_validation.h",
    "include/sost/params.h", "include/sost/proposals.h",
    "prototype/pq/", "scripts/pq_bench/", "wallet/", "explorer/",
)

# Doc surfaces that count as "the docs were updated".
DOC_SURFACES = (
    "docs/whitepaper/", "docs/PQ_", "docs/ADR/", "CHANGELOG.md",
    "docs/WHITEPAPER_MANIFEST.md", "README.md", "website/",
)


def changed_files(base):
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        # Fall back to a two-dot diff if the merge-base form fails.
        out = subprocess.check_output(
            ["git", "diff", "--name-only", base], stderr=subprocess.DEVNULL).decode()
    return [l.strip() for l in out.splitlines() if l.strip()]


def matches(path, prefixes):
    return any(path.startswith(p) or p in path for p in prefixes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    files = changed_files(args.base)
    if not files:
        print(f"check_whitepaper_sync: no changes vs {args.base}.")
        return 0

    src_changed = [f for f in files if matches(f, WATCHED_SRC)]
    docs_changed = [f for f in files if matches(f, DOC_SURFACES)]

    print(f"check_whitepaper_sync: base={args.base} "
          f"watched-src-changed={len(src_changed)} docs-changed={len(docs_changed)}")

    if src_changed and not docs_changed:
        print("WARNING: watched source surfaces changed but NO documentation surface "
              "was updated:", file=sys.stderr)
        for f in src_changed:
            print(f"  - {f}", file=sys.stderr)
        print("Update docs/whitepaper/, docs/PQ_*, docs/ADR/, CHANGELOG.md, README.md "
              "or website/ to describe the change (ADR-006).", file=sys.stderr)
        if args.strict:
            return 1
        print("(soft mode: not failing; pass --strict to enforce)")
        return 0

    print("check_whitepaper_sync: OK "
          "(no watched-source change without a matching doc update).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
