#!/usr/bin/env python3
"""
Run a multi-AOI opportunity campaign and write the ranking.

Examples
--------

  # Score every AOI in the canned Iberia campaign and write outputs
  # under ./out/iberia/
  python3 scripts/opportunity_campaign.py \\
      --campaign-file data/opportunity/campaigns/iberia_mine_waste_alpha.json \\
      --out-dir       data/opportunity/results/iberia

  # Smoke run with the first 2 AOIs only:
  python3 scripts/opportunity_campaign.py \\
      --campaign-file data/opportunity/campaigns/iberia_mine_waste_alpha.json \\
      --limit 2

  # Public teaser — strip lat/lon from the summary:
  python3 scripts/opportunity_campaign.py \\
      --campaign-file data/opportunity/campaigns/iberia_mine_waste_alpha.json \\
      --redact-coordinates
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path

# Allow running directly without installing the package.
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from geaspirit.opportunity import campaign as cmp  # noqa: E402


def _print_table(scorecards):
    if not scorecards:
        print("(no scorecards produced)")
        return
    print()
    head = (f"{'#':>2}  {'aoi':<42}  {'class':<18} {'gr':<3} "
            f"{'com':>4}  {'g':>3}/{'l':>3}/{'e':>3}/{'L':>3}  sha256")
    print(head)
    print("-" * len(head))
    for i, sc in enumerate(scorecards, start=1):
        sha = cmp.sha256_of_canonical(sc)[:12]
        print(f"{i:>2}  {sc.aoi.name[:42]:<42}  "
              f"{sc.opportunity_class:<18} {sc.class_grade:<3} "
              f"{sc.score:>4}  "
              f"{sc.subscores.geological:>3}/"
              f"{sc.subscores.logistics:>3}/"
              f"{sc.subscores.environmental:>3}/"
              f"{sc.subscores.legal:>3}  {sha}")
    print()


def main():
    ap = argparse.ArgumentParser(
        description="Score an opportunity campaign and emit ranking outputs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--campaign-file", required=True, type=Path,
        help="Path to the campaign JSON describing the AOI list.",
    )
    ap.add_argument(
        "--out-dir", type=Path, default=None,
        help=("Directory to write per-AOI scorecards, summary and CSV "
              "(default: data/opportunity/results/<campaign_name>__<utc_stamp>)."),
    )
    ap.add_argument(
        "--limit", type=int, default=None,
        help="Only score the first N AOIs (smoke runs).",
    )
    ap.add_argument(
        "--redact-coordinates", action="store_true",
        help="Strip lat/lon from the campaign summary (public teaser mode).",
    )
    args = ap.parse_args()

    if not args.campaign_file.exists():
        print(f"[opportunity_campaign] campaign file not found: {args.campaign_file}",
              file=sys.stderr)
        sys.exit(2)

    # Resolve default out dir.
    if args.out_dir is None:
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = args.campaign_file.stem
        args.out_dir = _PROJECT_ROOT / "data" / "opportunity" / "results" \
                       / f"{stem}__{stamp}"

    print(f"[opportunity_campaign] campaign : {args.campaign_file}")
    print(f"[opportunity_campaign] out_dir  : {args.out_dir}")
    if args.limit:
        print(f"[opportunity_campaign] limit    : {args.limit}")
    if args.redact_coordinates:
        print(f"[opportunity_campaign] redacting coordinates in summary")
    print("[opportunity_campaign] scoring AOIs (may hit OSM Overpass + read disk caches) ...")

    scorecards, written = cmp.run_and_export(
        args.campaign_file, args.out_dir,
        limit=args.limit,
        redact_coordinates=args.redact_coordinates,
    )

    _print_table(scorecards)
    print(f"[opportunity_campaign] wrote {len(written)} file(s) under {args.out_dir}")
    print(f"[opportunity_campaign] summary  : "
          f"{written['campaign:canonical'].name}")
    print(f"[opportunity_campaign] ranking  : "
          f"{written['campaign:csv'].name}")


if __name__ == "__main__":
    main()
