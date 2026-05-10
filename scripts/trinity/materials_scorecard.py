#!/usr/bin/env python3
"""Trinity / Materials Track — materials scorecard builder (mock-first).

Produces ``TRINITY_MATERIALS_SCORECARD_<campaign>.json`` and its Markdown
sidecar. The scorecard is the input artefact of the Materials Track,
mirroring the role of a GeaSpirit scorecard in the Earth Track.

DRY-RUN / MOCK-FIRST INVARIANTS
- No live import of ``materials-engine-private``. v0 uses pinned data.
- ``--live-materials-engine`` flag is wired but in v0 it logs a stub
  message and falls back to the mock; v0.1 will wire the real import.
- Canonical JSON: ``sort_keys=True``, ``separators=(",", ":")``,
  ``ensure_ascii=True``, no trailing newline. Byte-identical given the
  same pinned time.
- No host-path leak: the source block stores only the campaign name,
  module name, and the input set version — never an absolute path.
- No RPC, no network, no wallet, no subprocess to any tool.

Schema
------
::

    {
      "schema": "trinity-materials-scorecard/v0",
      "campaign": "novel_frontier_phase1",
      "track": "materials",
      "generated_at_utc": "2026-05-10T00:00:00+00:00",
      "features_available": 0,
      "source": {
        "mode": "mock" | "live",
        "module": "materials_engine.frontier+novelty (mocked in v0)",
        "input_set_version": "novel_frontier_v0_pinned"
      },
      "honesty_matrix": {
        "candidates_have_synthesis_data": false,
        "candidates_have_dft_relaxation": false,
        "candidates_have_phonon_screening": false,
        "novelty_baseline_locked": true,
        "frontier_scores_are_seeds_not_validations": true
      },
      "candidates": [
        {
          "id": "C-01",
          "formula": "Fe2MgO4",
          "family": "spinel oxide",
          "seed_novelty": 0.62,
          "seed_frontier_proximity": 0.71,
          "open_questions": [
              "no measured formation energy",
              "no synthesised polymorph baseline"
          ]
        },
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCHEMA = "trinity-materials-scorecard/v0"
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")


# Pinned candidate set for v0 demo campaign. These are public, well-known
# formulas chosen to exercise the pipeline; v0 makes no novelty claim for
# them. The numeric seeds are deterministic and frozen.
NOVEL_FRONTIER_PHASE1_CANDIDATES: List[Dict[str, Any]] = [
    {
        "id": "C-01",
        "formula": "Fe2MgO4",
        "family": "spinel oxide",
        "seed_novelty": 0.62,
        "seed_frontier_proximity": 0.71,
        "open_questions": [
            "no measured formation energy on file",
            "no MLIP relaxation baseline",
            "no synthesised polymorph reference for ferrimagnetic ordering"
        ],
    },
    {
        "id": "C-02",
        "formula": "LiNi0.5Mn1.5O4",
        "family": "layered oxide / cathode candidate",
        "seed_novelty": 0.48,
        "seed_frontier_proximity": 0.59,
        "open_questions": [
            "Mn/Ni ordering not resolved",
            "no DFT+U baseline at the chosen U_eff",
            "no calorimetric reference for phase stability"
        ],
    },
    {
        "id": "C-03",
        "formula": "BaZrO3:Y",
        "family": "perovskite / proton conductor",
        "seed_novelty": 0.55,
        "seed_frontier_proximity": 0.66,
        "open_questions": [
            "Y dopant site occupancy unconfirmed",
            "no phonon screening at the operating temperature",
            "no Kroger-Vink defect inventory"
        ],
    },
    {
        "id": "C-04",
        "formula": "CaCu3Ti4O12",
        "family": "giant-permittivity oxide",
        "seed_novelty": 0.41,
        "seed_frontier_proximity": 0.52,
        "open_questions": [
            "internal barrier layer capacitor mechanism still debated",
            "no GW band-edge alignment",
            "no spin-orbit coupling check on Ti 3d"
        ],
    },
    {
        "id": "C-05",
        "formula": "Co3O4",
        "family": "transition-metal oxide reference",
        "seed_novelty": 0.30,
        "seed_frontier_proximity": 0.40,
        "open_questions": [
            "reference material, included as calibration anchor",
            "no fresh DFT relaxation in the current MLIP basis"
        ],
    },
]


HONESTY_MATRIX_DEFAULT: Dict[str, bool] = {
    "candidates_have_synthesis_data": False,
    "candidates_have_dft_relaxation": False,
    "candidates_have_phonon_screening": False,
    "novelty_baseline_locked": True,
    "frontier_scores_are_seeds_not_validations": True,
}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit scorecard: host-path markers leaked into "
            f"canonical JSON: {leaked}"
        )


def build_scorecard(
    *,
    campaign: str,
    generated_at_utc: str,
    candidates: Optional[List[Dict[str, Any]]] = None,
    honesty_matrix: Optional[Dict[str, bool]] = None,
    live_mode: bool = False,
) -> Dict[str, Any]:
    """Return a canonical-ready scorecard dict for the given campaign."""
    if not isinstance(campaign, str) or not campaign.strip():
        raise ValueError("campaign must be a non-empty string")
    if not isinstance(generated_at_utc, str) or not generated_at_utc.endswith(
        "+00:00"
    ):
        raise ValueError(
            "generated_at_utc must be an ISO-8601 string ending in +00:00"
        )

    cands = list(candidates or NOVEL_FRONTIER_PHASE1_CANDIDATES)
    hm = dict(honesty_matrix or HONESTY_MATRIX_DEFAULT)

    if live_mode:
        # v0 stub. v0.1 will replace this branch with a real import from
        # materials-engine-private's frontier + novelty modules through
        # TRINITY_MATERIALS_ENGINE_PATH. For now, log and fall through.
        print(
            "[materials_scorecard] --live-materials-engine: live "
            "integration not yet implemented in v0; using mock candidate "
            "set.",
            file=sys.stderr,
        )

    source = {
        "mode": "mock",
        "module": "materials_engine.frontier+novelty (mocked in v0)",
        "input_set_version": "novel_frontier_v0_pinned",
    }

    # features_available mirrors the GeaSpirit honesty signal. v0 ships
    # with zero "validated" features so the downstream dossier stays in
    # fallback mode, exactly like Kalgoorlie Phase 1.
    features_available = 0

    scorecard = {
        "schema": _SCHEMA,
        "campaign": campaign,
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "features_available": features_available,
        "source": source,
        "honesty_matrix": hm,
        "candidates": cands,
    }

    blob = canonical_dumps(scorecard)
    _check_no_host_paths(blob)
    return scorecard


def render_markdown(scorecard: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Track — Scorecard "
        f"`{scorecard['campaign']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN scorecard.** This document is a pinned, deterministic "
        "input artefact for the Materials Track pipeline. It records the "
        "candidate set, honesty matrix and source attribution. It does "
        "not claim novelty for any specific material."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{scorecard['schema']}`")
    lines.append(f"- **Track**: `{scorecard['track']}`")
    lines.append(f"- **Generated (UTC)**: {scorecard['generated_at_utc']}")
    lines.append(
        f"- **features_available**: `{scorecard['features_available']}`"
    )
    src = scorecard["source"]
    lines.append("- **Source**:")
    for k in sorted(src):
        lines.append(f"  - `{k}`: `{src[k]}`")
    lines.append("")
    lines.append("## Honesty matrix")
    lines.append("")
    hm = scorecard["honesty_matrix"]
    for k in sorted(hm):
        lines.append(f"- `{k}`: `{hm[k]}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    lines.append(
        "| id | formula | family | seed_novelty | seed_frontier_proximity |"
    )
    lines.append("| --- | --- | --- | --- | --- |")
    for c in scorecard["candidates"]:
        lines.append(
            f"| `{c['id']}` | `{c['formula']}` | {c['family']} | "
            f"{c['seed_novelty']:.2f} | {c['seed_frontier_proximity']:.2f} |"
        )
    lines.append("")
    lines.append("### Open questions per candidate")
    lines.append("")
    for c in scorecard["candidates"]:
        lines.append(f"- **`{c['id']}` ({c['formula']})**")
        for q in c["open_questions"]:
            lines.append(f"  - {q}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_scorecard",
        description=(
            "Build a Trinity / Materials Track scorecard for the demo "
            "campaign. Mock-first; never broadcasts or registers anything."
        ),
    )
    p.add_argument(
        "--campaign", type=str, default="novel_frontier_phase1",
    )
    p.add_argument(
        "--generated-at-utc", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument(
        "--out-json", type=str,
        default=None,
        help=(
            "Output JSON path. Defaults to "
            "TRINITY_MATERIALS_SCORECARD_<campaign>.json"
        ),
    )
    p.add_argument(
        "--out-md", type=str,
        default=None,
        help=(
            "Output Markdown path. Defaults to "
            "TRINITY_MATERIALS_SCORECARD_<campaign>.md"
        ),
    )
    p.add_argument(
        "--live-materials-engine", action="store_true",
        help=(
            "v0 stub: live integration not yet implemented; falls back "
            "to the pinned mock candidate set."
        ),
    )
    args = p.parse_args(argv)

    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_SCORECARD_{args.campaign}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_SCORECARD_{args.campaign}.md"
    )

    scorecard = build_scorecard(
        campaign=args.campaign,
        generated_at_utc=args.generated_at_utc,
        live_mode=args.live_materials_engine,
    )

    out_json.write_text(canonical_dumps(scorecard), encoding="utf-8")
    out_md.write_text(render_markdown(scorecard), encoding="utf-8")

    print(f"[materials_scorecard] wrote {out_json}")
    print(f"[materials_scorecard] wrote {out_md}")
    print(
        f"[materials_scorecard] candidates: {len(scorecard['candidates'])}; "
        f"features_available: {scorecard['features_available']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
