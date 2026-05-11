#!/usr/bin/env python3
"""Trinity / Geo Discovery — End-to-end orchestrator v0.1.

Runs the full Geo Discovery v0.1 pipeline in one shot:

  1. ``geo_candidate_generator``  → candidate AOI pool
  2. ``geo_candidate_filter``     → filter verdicts
  3. ``geo_anomaly_scorer``       → v0.1 geo scorecard
  4. ``geo_dossier``              → real SOST AI Council reviews
  5. ``geo_compute_plan``         → heavy task plan (dry-run)
  6. ``geo_campaign``             → campaign manifest
  7. ``trinity_proof_bundle``     → final proof bundle

All seven stages are invoked in-process via importlib. No network, no
shell, no wallet, no broadcast. Deterministic given the same ``--seed``
and ``--pinned-time``.

Output basenames (anchored on the global_phase1 campaign label):
- TRINITY_GEO_CANDIDATE_AOIS_global_phase1.{json,md}
- TRINITY_GEO_FILTER_global_phase1.{json,md}
- TRINITY_GEO_SCORECARD_global_phase1.{json,md}
- TRINITY_GEO_DOSSIER_global_phase1.{json,md}
- TRINITY_GEO_USEFUL_COMPUTE_PLAN_global_phase1.{json,md}
- TRINITY_GEO_CAMPAIGN_global_phase1.{json,md}
- TRINITY_GEO_PROOF_BUNDLE_global_phase1.{json,md}
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCRIPTS_DIR = Path(__file__).resolve().parent


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_pipeline(
    *,
    mode: str,
    commodity: str,
    count: int,
    seed: str,
    pinned_time: str,
    out_dir: Optional[Path] = None,
    campaign: str = "global_phase1",
) -> Dict[str, Any]:
    out_dir = Path(out_dir or Path.cwd())
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = _load("geopipe_gen", _SCRIPTS_DIR / "geo_candidate_generator.py")
    flt = _load("geopipe_filter", _SCRIPTS_DIR / "geo_candidate_filter.py")
    scr = _load("geopipe_scorer", _SCRIPTS_DIR / "geo_anomaly_scorer.py")
    dossier_mod = _load("geopipe_dossier", _SCRIPTS_DIR / "geo_dossier.py")
    plan_mod = _load("geopipe_plan", _SCRIPTS_DIR / "geo_compute_plan.py")
    camp_mod = _load("geopipe_campaign", _SCRIPTS_DIR / "geo_campaign.py")
    bundle_mod = _load(
        "geopipe_bundle", _SCRIPTS_DIR / "trinity_proof_bundle.py"
    )

    p = {
        "candidates_json": out_dir / f"TRINITY_GEO_CANDIDATE_AOIS_{campaign}.json",
        "candidates_md":   out_dir / f"TRINITY_GEO_CANDIDATE_AOIS_{campaign}.md",
        "filter_json":     out_dir / f"TRINITY_GEO_FILTER_{campaign}.json",
        "filter_md":       out_dir / f"TRINITY_GEO_FILTER_{campaign}.md",
        "scorecard_json":  out_dir / f"TRINITY_GEO_SCORECARD_{campaign}.json",
        "scorecard_md":    out_dir / f"TRINITY_GEO_SCORECARD_{campaign}.md",
        "dossier_json":    out_dir / f"TRINITY_GEO_DOSSIER_{campaign}.json",
        "dossier_md":      out_dir / f"TRINITY_GEO_DOSSIER_{campaign}.md",
        "plan_json":       out_dir / f"TRINITY_GEO_USEFUL_COMPUTE_PLAN_{campaign}.json",
        "plan_md":         out_dir / f"TRINITY_GEO_USEFUL_COMPUTE_PLAN_{campaign}.md",
        "campaign_json":   out_dir / f"TRINITY_GEO_CAMPAIGN_{campaign}.json",
        "campaign_md":     out_dir / f"TRINITY_GEO_CAMPAIGN_{campaign}.md",
        "bundle_json":     out_dir / f"TRINITY_GEO_PROOF_BUNDLE_{campaign}.json",
        "bundle_md":       out_dir / f"TRINITY_GEO_PROOF_BUNDLE_{campaign}.md",
    }

    # Stage 1: candidate generator
    pool = gen.build_candidate_pool(
        mode=mode, commodity=commodity, count=count, seed=seed,
        generated_at_utc=pinned_time,
    )
    p["candidates_json"].write_text(
        gen.canonical_dumps(pool), encoding="utf-8"
    )
    p["candidates_md"].write_text(
        gen.render_markdown(pool), encoding="utf-8"
    )

    # Stage 2: filter
    filtered = flt.build_filtered_pool(
        candidate_pool_path=p["candidates_json"],
        generated_at_utc=pinned_time,
    )
    p["filter_json"].write_text(
        flt.canonical_dumps(filtered), encoding="utf-8"
    )
    p["filter_md"].write_text(
        flt.render_markdown(filtered), encoding="utf-8"
    )

    # Stage 3: anomaly scorer
    sc = scr.build_scorecard(
        candidate_pool_path=p["candidates_json"],
        filter_path=p["filter_json"],
        generated_at_utc=pinned_time,
    )
    p["scorecard_json"].write_text(
        scr.canonical_dumps(sc), encoding="utf-8"
    )
    p["scorecard_md"].write_text(
        scr.render_markdown(sc), encoding="utf-8"
    )

    if not sc["candidates"]:
        raise RuntimeError(
            "geo scorer emitted zero candidates; cannot continue "
            "with dossier / plan / campaign / bundle"
        )

    # Stage 4: dossier (real SOST AI council)
    d = dossier_mod.build_dossier(
        campaign=campaign,
        generated_at_utc=pinned_time,
        scorecard_path=p["scorecard_json"],
    )
    p["dossier_json"].write_text(
        dossier_mod.canonical_dumps(d), encoding="utf-8"
    )
    p["dossier_md"].write_text(
        dossier_mod.render_markdown(d), encoding="utf-8"
    )

    # Stage 5: compute plan
    plan = plan_mod.build_plan(
        campaign=campaign,
        generated_at_utc=pinned_time,
        dossier_path=p["dossier_json"],
    )
    p["plan_json"].write_text(
        plan_mod.canonical_dumps(plan), encoding="utf-8"
    )
    p["plan_md"].write_text(
        plan_mod.render_markdown(plan), encoding="utf-8"
    )

    # Stage 6: campaign manifest
    manifest = camp_mod.build_campaign(
        campaign=campaign,
        generated_at_utc=pinned_time,
        dossier_path=p["dossier_json"],
        plan_path=p["plan_json"],
    )
    p["campaign_json"].write_text(
        camp_mod.canonical_dumps(manifest), encoding="utf-8"
    )
    p["campaign_md"].write_text(
        camp_mod.render_markdown(manifest), encoding="utf-8"
    )

    # Stage 7: proof bundle
    bundle_argv = [
        "--dossier", str(p["dossier_json"]),
        "--useful-compute-plan", str(p["plan_json"]),
        "--campaign", str(p["campaign_json"]),
        "--aoi", "geo_global_phase1",
        "--bundle-name", campaign,
        "--pinned-time", pinned_time,
        "--out-json", str(p["bundle_json"]),
        "--out-md", str(p["bundle_md"]),
    ]
    rc = bundle_mod.main(bundle_argv)
    if rc != 0:
        raise RuntimeError("trinity_proof_bundle.main returned non-zero")

    return {
        "paths": {k: str(v) for k, v in p.items()},
        "shas": {
            "candidates": file_sha256(p["candidates_json"]),
            "filter":     file_sha256(p["filter_json"]),
            "scorecard":  file_sha256(p["scorecard_json"]),
            "dossier":    file_sha256(p["dossier_json"]),
            "plan":       file_sha256(p["plan_json"]),
            "campaign":   file_sha256(p["campaign_json"]),
            "bundle":     file_sha256(p["bundle_json"]),
        },
        "summary": {
            "pool_size":     pool["count_emitted"],
            "filter_accept": filtered["summary"]["accept"],
            "filter_reject": filtered["summary"]["reject"],
            "scored":        sc["summary"]["candidates_scored"],
            "dossier_summary": d["summary"],
            "plan_summary":    plan["summary"],
            "campaign_summary": manifest["summary"],
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="geo_discovery_pipeline",
        description=(
            "Run the full Trinity / Geo Discovery v0.1 pipeline in "
            "one shot. Dry-run, deterministic, offline."
        ),
    )
    p.add_argument(
        "--mode", type=str, default="offline-belts",
        choices=("offline-belts", "grid-seed"),
    )
    p.add_argument(
        "--commodity", type=str, default="copper_gold_critical_minerals",
    )
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--seed", type=str, default="trinity-geo-v0.1")
    p.add_argument(
        "--pinned-time", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument("--out-dir", type=str, default=None)
    p.add_argument("--campaign", type=str, default="global_phase1")
    args = p.parse_args(argv)

    result = run_pipeline(
        mode=args.mode,
        commodity=args.commodity,
        count=args.count,
        seed=args.seed,
        pinned_time=args.pinned_time,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        campaign=args.campaign,
    )

    print(
        f"[geopipe] mode={args.mode} commodity={args.commodity} "
        f"count={args.count} seed={args.seed!r}"
    )
    print(f"[geopipe] pool_size: {result['summary']['pool_size']}")
    print(
        f"[geopipe] filter: accept={result['summary']['filter_accept']}, "
        f"reject={result['summary']['filter_reject']}"
    )
    print(f"[geopipe] scored: {result['summary']['scored']}")
    print(f"[geopipe] dossier: {result['summary']['dossier_summary']}")
    plan_s = result['summary']['plan_summary']
    print(
        f"[geopipe] plan: tasks={plan_s.get('tasks_total')}, "
        f"by_class={plan_s.get('by_classification')}"
    )
    camp_s = result['summary']['campaign_summary']
    print(
        f"[geopipe] campaign: actions={camp_s.get('actions_total')}, "
        f"gaps_observed={camp_s.get('gaps_observed')}"
    )
    print()
    print(f"[geopipe] SHAs (byte-identical with pinned seed/time):")
    for k, v in sorted(result["shas"].items()):
        print(f"  {k:>10}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
