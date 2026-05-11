#!/usr/bin/env python3
"""Trinity / Materials Discovery — End-to-end orchestrator v0.1.

Runs the full Materials Discovery v0.1 pipeline in one shot:

  1. ``materials_candidate_generator``   → candidate pool
  2. ``materials_chemistry_filter``      → filter verdicts
  3. ``materials_industrial_scorer``     → v0.1 scorecard
  4. ``materials_dossier``               → council reviews
  5. ``materials_compute_plan``          → heavy task plan
  6. ``materials_campaign``              → campaign manifest
  7. ``trinity_proof_bundle``            → final proof bundle

All seven stages are invoked in-process, not via subprocess, so the
pipeline is completely self-contained and any caller exception
propagates with a real Python traceback. No network, no shell, no
wallet, no broadcast.

Determinism
-----------
Given the same ``--seed`` and ``--pinned-time`` the pipeline produces
byte-identical artefacts on every machine.

Output (basenames anchored on ``--family``)
-------------------------------------------
- ``TRINITY_MATERIALS_CANDIDATES_<family>.json`` + ``.md``
- ``TRINITY_MATERIALS_FILTER_<family>.json`` + ``.md``
- ``TRINITY_MATERIALS_SCORECARD_<family>_v02.json`` + ``.md``
- ``TRINITY_MATERIALS_DOSSIER_<family>_v02.json`` + ``.md``
- ``TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_<family>_v02.json`` + ``.md``
- ``TRINITY_MATERIALS_CAMPAIGN_<family>_v02.json`` + ``.md``
- ``TRINITY_MATERIALS_PROOF_BUNDLE_<family>_v02.json`` + ``.md``
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
    family: str,
    count: int,
    seed: str,
    pinned_time: str,
    allow_toxic: bool = False,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    out_dir = Path(out_dir or Path.cwd())
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = _load("mdpipe_gen", _SCRIPTS_DIR / "materials_candidate_generator.py")
    flt = _load(
        "mdpipe_filter", _SCRIPTS_DIR / "materials_chemistry_filter.py"
    )
    scr = _load(
        "mdpipe_scorer", _SCRIPTS_DIR / "materials_industrial_scorer.py"
    )
    dossier = _load("mdpipe_dossier", _SCRIPTS_DIR / "materials_dossier.py")
    plan_mod = _load(
        "mdpipe_plan", _SCRIPTS_DIR / "materials_compute_plan.py"
    )
    campaign_mod = _load(
        "mdpipe_campaign", _SCRIPTS_DIR / "materials_campaign.py"
    )
    bundle_mod = _load(
        "mdpipe_bundle", _SCRIPTS_DIR / "trinity_proof_bundle.py"
    )

    fam = family
    paths = {
        "candidates_json": out_dir / f"TRINITY_MATERIALS_CANDIDATES_{fam}.json",
        "candidates_md":   out_dir / f"TRINITY_MATERIALS_CANDIDATES_{fam}.md",
        "filter_json":     out_dir / f"TRINITY_MATERIALS_FILTER_{fam}.json",
        "filter_md":       out_dir / f"TRINITY_MATERIALS_FILTER_{fam}.md",
        "scorecard_json":  out_dir / f"TRINITY_MATERIALS_SCORECARD_{fam}_v02.json",
        "scorecard_md":    out_dir / f"TRINITY_MATERIALS_SCORECARD_{fam}_v02.md",
        "dossier_json":    out_dir / f"TRINITY_MATERIALS_DOSSIER_{fam}_v02.json",
        "dossier_md":      out_dir / f"TRINITY_MATERIALS_DOSSIER_{fam}_v02.md",
        "plan_json":       out_dir / f"TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_{fam}_v02.json",
        "plan_md":         out_dir / f"TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_{fam}_v02.md",
        "campaign_json":   out_dir / f"TRINITY_MATERIALS_CAMPAIGN_{fam}_v02.json",
        "campaign_md":     out_dir / f"TRINITY_MATERIALS_CAMPAIGN_{fam}_v02.md",
        "bundle_json":     out_dir / f"TRINITY_MATERIALS_PROOF_BUNDLE_{fam}_v02.json",
        "bundle_md":       out_dir / f"TRINITY_MATERIALS_PROOF_BUNDLE_{fam}_v02.md",
    }

    # Stage 1: generator
    pool = gen.build_candidate_pool(
        family=family, count=count, seed=seed,
        generated_at_utc=pinned_time,
    )
    paths["candidates_json"].write_text(
        gen.canonical_dumps(pool), encoding="utf-8"
    )
    paths["candidates_md"].write_text(
        gen.render_markdown(pool), encoding="utf-8"
    )

    # Stage 2: filter
    filtered = flt.build_filtered_pool(
        candidate_pool_path=paths["candidates_json"],
        generated_at_utc=pinned_time,
        allow_toxic=allow_toxic,
    )
    paths["filter_json"].write_text(
        flt.canonical_dumps(filtered), encoding="utf-8"
    )
    paths["filter_md"].write_text(
        flt.render_markdown(filtered), encoding="utf-8"
    )

    # Stage 3: industrial scorer
    sc = scr.build_scorecard(
        candidate_pool_path=paths["candidates_json"],
        filter_path=paths["filter_json"],
        generated_at_utc=pinned_time,
    )
    paths["scorecard_json"].write_text(
        scr.canonical_dumps(sc), encoding="utf-8"
    )
    paths["scorecard_md"].write_text(
        scr.render_markdown(sc), encoding="utf-8"
    )

    if not sc["candidates"]:
        raise RuntimeError(
            "industrial scorer emitted zero candidates; cannot continue "
            "with dossier / plan / campaign / bundle"
        )

    # Stage 4: dossier
    campaign_name = f"{fam}_v02"
    d = dossier.build_dossier(
        campaign=campaign_name,
        generated_at_utc=pinned_time,
        scorecard_path=paths["scorecard_json"],
    )
    paths["dossier_json"].write_text(
        dossier.canonical_dumps(d), encoding="utf-8"
    )
    paths["dossier_md"].write_text(
        dossier.render_markdown(d), encoding="utf-8"
    )

    # Stage 5: compute plan
    plan = plan_mod.build_plan(
        campaign=campaign_name,
        generated_at_utc=pinned_time,
        dossier_path=paths["dossier_json"],
    )
    paths["plan_json"].write_text(
        plan_mod.canonical_dumps(plan), encoding="utf-8"
    )
    paths["plan_md"].write_text(
        plan_mod.render_markdown(plan), encoding="utf-8"
    )

    # Stage 6: campaign manifest
    manifest = campaign_mod.build_campaign(
        campaign=campaign_name,
        generated_at_utc=pinned_time,
        dossier_path=paths["dossier_json"],
        plan_path=paths["plan_json"],
    )
    paths["campaign_json"].write_text(
        campaign_mod.canonical_dumps(manifest), encoding="utf-8"
    )
    paths["campaign_md"].write_text(
        campaign_mod.render_markdown(manifest), encoding="utf-8"
    )

    # Stage 7: proof bundle.
    # trinity_proof_bundle exposes a main() with CLI args. We re-call
    # it in-process by constructing argv and invoking main().
    bundle_argv = [
        "--dossier", str(paths["dossier_json"]),
        "--useful-compute-plan", str(paths["plan_json"]),
        "--campaign", str(paths["campaign_json"]),
        "--aoi", "materials_oxide_frontier",
        "--bundle-name", campaign_name,
        "--pinned-time", pinned_time,
        "--out-json", str(paths["bundle_json"]),
        "--out-md", str(paths["bundle_md"]),
    ]
    rc = bundle_mod.main(bundle_argv)
    if rc != 0:
        raise RuntimeError("trinity_proof_bundle.main returned non-zero")

    return {
        "paths": {k: str(v) for k, v in paths.items()},
        "shas": {
            "candidates": file_sha256(paths["candidates_json"]),
            "filter":     file_sha256(paths["filter_json"]),
            "scorecard":  file_sha256(paths["scorecard_json"]),
            "dossier":    file_sha256(paths["dossier_json"]),
            "plan":       file_sha256(paths["plan_json"]),
            "campaign":   file_sha256(paths["campaign_json"]),
            "bundle":     file_sha256(paths["bundle_json"]),
        },
        "summary": {
            "pool_size":       pool["count_emitted"],
            "filter_accept":   filtered["summary"]["accept"],
            "filter_reject":   filtered["summary"]["reject"],
            "scored":          sc["summary"]["candidates_scored"],
            "dossier_summary": d["summary"],
            "plan_summary":    plan["summary"],
            "campaign_summary": manifest["summary"],
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_discovery_pipeline",
        description=(
            "Run the full Trinity / Materials Discovery v0.1 pipeline "
            "in one shot. Dry-run, deterministic, offline."
        ),
    )
    p.add_argument("--family", type=str, default="oxide_frontier")
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--seed", type=str, default="trinity-v0.1")
    p.add_argument(
        "--pinned-time", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument(
        "--allow-toxic", action="store_true",
        help=(
            "Keep candidates with toxic elements as flagged instead of "
            "rejecting them. Default: reject."
        ),
    )
    p.add_argument("--out-dir", type=str, default=None)
    args = p.parse_args(argv)

    result = run_pipeline(
        family=args.family,
        count=args.count,
        seed=args.seed,
        pinned_time=args.pinned_time,
        allow_toxic=args.allow_toxic,
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )

    print(f"[pipeline] family={args.family} count={args.count} seed={args.seed!r}")
    print(f"[pipeline] pool_size: {result['summary']['pool_size']}")
    print(
        f"[pipeline] filter: accept={result['summary']['filter_accept']}, "
        f"reject={result['summary']['filter_reject']}"
    )
    print(f"[pipeline] scored: {result['summary']['scored']}")
    print(f"[pipeline] dossier: {result['summary']['dossier_summary']}")
    plan_s = result['summary']['plan_summary']
    print(
        f"[pipeline] plan: tasks={plan_s.get('tasks_total')}, "
        f"by_class={plan_s.get('by_classification')}"
    )
    print()
    print(f"[pipeline] SHAs (byte-identical with pinned seed/time):")
    for k, v in sorted(result["shas"].items()):
        print(f"  {k:>10}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
