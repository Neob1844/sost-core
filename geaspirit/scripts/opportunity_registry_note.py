#!/usr/bin/env python3
"""
Build a Protocol Registry capsule body for an opportunity scorecard
or campaign summary and print:

  1. the canonical SHA-256 of the input file,
  2. the capsule body (the literal string to anchor on chain),
  3. the suggested ``sost-cli registry-note`` invocation.

This script NEVER calls ``sost-cli`` itself, never touches the chain
and never opens a network socket. The operator decides when and how
to submit the capsule.

Examples
--------

  # Anchor a single scorecard:
  python3 scripts/opportunity_registry_note.py \\
      --scorecard data/opportunity/results/galicia__abcd1234.canonical.json

  # Anchor a whole campaign summary, redacting the campaign name:
  python3 scripts/opportunity_registry_note.py \\
      --campaign-summary data/opportunity/results/iberia/campaign_summary.canonical.json \\
      --redact

  # Auto-detect input kind:
  python3 scripts/opportunity_registry_note.py path/to/any.canonical.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running directly without installing the package.
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from geaspirit.opportunity import registry  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Build a Protocol Registry capsule body for an opportunity "
            "scorecard or campaign summary. Does not touch the chain."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--scorecard", type=Path,
                       help="Path to an opportunity scorecard canonical JSON.")
    group.add_argument("--campaign-summary", type=Path,
                       help="Path to a campaign summary canonical JSON.")
    ap.add_argument("path", nargs="?", type=Path,
                    help="Auto-detect input kind from this path "
                         "(used when neither --scorecard nor --campaign-summary "
                         "is given).")
    ap.add_argument("--redact", "--redact-coordinates", action="store_true",
                    dest="redact",
                    help=("For scorecards: redact the AOI name in the capsule. "
                          "For campaigns: redact the campaign name."))
    args = ap.parse_args()

    path = args.scorecard or args.campaign_summary or args.path
    if path is None:
        ap.error("provide one of --scorecard / --campaign-summary / <path>")
    if not path.exists():
        print(f"[opportunity_registry_note] file not found: {path}",
              file=sys.stderr)
        sys.exit(2)

    try:
        if args.scorecard:
            body, payload = registry.build_scorecard_capsule(path, redact_aoi=args.redact)
            kind = "scorecard"
        elif args.campaign_summary:
            body, payload = registry.build_campaign_capsule(path, redact_name=args.redact)
            kind = "campaign"
        else:
            kind, body, payload = registry.build_capsule(path, redact=args.redact)
    except ValueError as e:
        print(f"[opportunity_registry_note] {e}", file=sys.stderr)
        sys.exit(3)

    sha = registry.sha256_hex_of_file(path)
    print(f"[opportunity_registry_note] input    : {path}")
    print(f"[opportunity_registry_note] kind     : {kind}")
    print(f"[opportunity_registry_note] sha256   : {sha}")
    print()
    print("# Capsule body (paste this on chain via Protocol Registry):")
    print(body)
    print()
    print("# Suggested operator command (NOT executed by this script):")
    print(registry.suggested_sost_cli_command(body))


if __name__ == "__main__":
    main()
