#!/usr/bin/env python3
"""
Render an HTML dossier from an opportunity campaign summary.

The dossier is a single self-contained HTML file: no external CSS,
no JavaScript, no remote fonts. It is printable from any browser
(Save as PDF if you want PDF). The disclaimer and per-AOI Protocol
Registry capsule notes are baked into the page so a recipient can
re-verify each SHA-256.

This script never calls ``sost-cli``, never touches the chain and
never opens a network socket.

Examples
--------

  # Render with full coordinates:
  python3 scripts/opportunity_dossier.py \\
      --campaign-summary /tmp/geaspirit_iberia_24/campaign_summary.canonical.json \\
      --out             /tmp/geaspirit_iberia_24/dossier.html

  # Public teaser (no lat/lon, no campaign name in the capsule):
  python3 scripts/opportunity_dossier.py \\
      --campaign-summary /tmp/geaspirit_iberia_24/campaign_summary.canonical.json \\
      --out             /tmp/geaspirit_iberia_24/dossier.public.html \\
      --redact-coordinates
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running directly without installing the package.
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from geaspirit.opportunity import dossier  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description="Render an HTML dossier from a campaign summary JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--campaign-summary", required=True, type=Path,
        help="Path to the campaign_summary.canonical.json produced by "
             "opportunity_campaign.py.",
    )
    ap.add_argument(
        "--out", required=True, type=Path,
        help="Where to write the rendered dossier HTML.",
    )
    ap.add_argument(
        "--redact-coordinates", action="store_true",
        help="Strip lat/lon from per-AOI cards and the campaign capsule "
             "(public teaser mode).",
    )
    args = ap.parse_args()

    if not args.campaign_summary.exists():
        print(f"[opportunity_dossier] campaign summary not found: "
              f"{args.campaign_summary}", file=sys.stderr)
        sys.exit(2)

    try:
        html = dossier.render_from_path(
            args.campaign_summary,
            redact_coordinates=args.redact_coordinates,
        )
    except ValueError as e:
        print(f"[opportunity_dossier] {e}", file=sys.stderr)
        sys.exit(3)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    size_kb = args.out.stat().st_size / 1024.0

    print(f"[opportunity_dossier] input  : {args.campaign_summary}")
    print(f"[opportunity_dossier] output : {args.out}")
    print(f"[opportunity_dossier] size   : {size_kb:.1f} KB")
    if args.redact_coordinates:
        print(f"[opportunity_dossier] redacted coordinates: yes")
    print(f"[opportunity_dossier] disclaimer + capsule note baked in. "
          f"Open in a browser; print/save-as-PDF as desired.")


if __name__ == "__main__":
    main()
