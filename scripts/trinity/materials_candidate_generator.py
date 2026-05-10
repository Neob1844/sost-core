#!/usr/bin/env python3
"""Trinity / Materials Discovery Engine — Candidate Generator v0.1.

Deterministically generates a pool of **proposed** materials candidates
(formulas + family + composition + industrial-use hypotheses) from a
pinned seed string. Does NOT claim novelty, validation or commercial
viability for any candidate. The output is an autonomous candidate
proposal pool that downstream stages (chemistry filter, industrial
scorer, AI Council, Useful Compute planner) refine.

Determinism
-----------
The generator is fully deterministic. No use of ``random`` module, no
filesystem entropy. All "random" choices come from
``hashlib.sha256(seed_bytes || index_bytes || axis_label)`` and are
mapped to integers / floats via fixed bit-extraction.

Two identical ``(--seed, --count, --family, --pinned-time)`` invocations
produce byte-identical output on any machine.

Output schema (``trinity-materials-candidate-pool/v0.1``)
-------------------------------------------------------
::

    {
      "schema": "trinity-materials-candidate-pool/v0.1",
      "family": "oxide_frontier",
      "track": "materials",
      "generated_at_utc": "2026-05-10T00:00:00+00:00",
      "seed": "trinity-v0.1",
      "count_requested": 50,
      "count_emitted": 50,
      "generator_version": "v0.1",
      "candidates": [
        {
          "id": "MX-0001",
          "formula": "Fe2MgO4",
          "family": "spinel",
          "composition": {"Fe": 2, "Mg": 1, "O": 4},
          "generation_method": "deterministic_rule_based_v0.1",
          "novelty_status": "unknown_not_validated",
          "industrial_hypotheses": [
              "battery_cathode", "oxygen_evolution_catalyst"
          ],
          "safety_flags": {
              "not_a_synthesis_recipe": true,
              "not_a_performance_claim": true,
              "requires_dft_validation": true,
              "requires_synthesis_validation": true
          }
        },
        ...
      ]
    }

Invariants
----------
- Dry-run. No network, no subprocess, no wallet, no broadcast surface.
- No host-path leak. Output JSON forbidden to contain ``/home/``,
  ``/opt/``, ``/Users/``, ``C:/`` or ``C:\\``.
- Canonical JSON: ``sort_keys=True``, ``separators=(",", ":")``,
  ``ensure_ascii=True``, no trailing newline.
- Every candidate carries ``novelty_status = "unknown_not_validated"``
  and a ``safety_flags`` block that refuses synthesis / performance
  claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_SCHEMA = "trinity-materials-candidate-pool/v0.1"
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")


# ---------------------------------------------------------------------------
# Family taxonomy
#
# Each entry is one of the four base oxide families. The chemistry filter
# downstream will check charge balance against the listed cation oxidation
# states; only candidates that balance against O^{2-} survive.
# ---------------------------------------------------------------------------


_FAMILY_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "spinel": {
        "label": "spinel oxide AB2O4",
        "a_cations": [
            ("Mg", 2), ("Zn", 2), ("Fe", 2), ("Co", 2),
            ("Ni", 2), ("Mn", 2), ("Cu", 2),
        ],
        "b_cations": [
            ("Al", 3), ("Cr", 3), ("Fe", 3), ("Mn", 3),
            ("Ga", 3), ("V", 3),
        ],
        "anion": ("O", -2),
        "stoichiometry": "AB2O4",
        "industrial_hypotheses": [
            "oxygen_evolution_catalyst", "magnetic_oxide",
            "battery_cathode",
        ],
    },
    "perovskite": {
        "label": "perovskite ABO3",
        "a_cations": [
            ("Ca", 2), ("Sr", 2), ("Ba", 2), ("La", 3),
            ("Y", 3), ("Pr", 3), ("Nd", 3),
        ],
        "b_cations": [
            ("Ti", 4), ("Zr", 4), ("Hf", 4), ("Mn", 3),
            ("Fe", 3), ("Co", 3), ("Ni", 3), ("Nb", 5),
            ("Ta", 5),
        ],
        "anion": ("O", -2),
        "stoichiometry": "ABO3",
        "industrial_hypotheses": [
            "proton_conductor", "ferroelectric",
            "magnetoresistance_oxide", "thermoelectric",
            "oxygen_evolution_catalyst",
        ],
    },
    "layered_oxide": {
        "label": "layered transition-metal oxide AxByO2",
        "a_cations": [
            ("Li", 1), ("Na", 1), ("K", 1),
        ],
        "b_cations": [
            ("Mn", 4), ("Ni", 4), ("Co", 3), ("Fe", 3),
            ("V", 5), ("Ti", 4),
        ],
        "anion": ("O", -2),
        "stoichiometry": "AxBO2",
        "industrial_hypotheses": [
            "battery_cathode", "ion_conductor",
        ],
    },
    "oxide_interface": {
        "label": "binary oxide motif AOx-BOy",
        "a_cations": [
            ("Ti", 4), ("Zr", 4), ("Sn", 4), ("Ce", 4),
        ],
        "b_cations": [
            ("Al", 3), ("Cr", 3), ("Fe", 3), ("Ga", 3),
        ],
        "anion": ("O", -2),
        "stoichiometry": "AO2-BO1.5",
        "industrial_hypotheses": [
            "high_k_dielectric", "corrosion_resistant_coating",
            "photocatalyst",
        ],
    },
}

# Aggregate family label used when --family oxide_frontier is requested.
_OXIDE_FRONTIER_MIX = (
    ("spinel", 14),
    ("perovskite", 20),
    ("layered_oxide", 10),
    ("oxide_interface", 6),
)


# ---------------------------------------------------------------------------
# Deterministic pseudo-random source
# ---------------------------------------------------------------------------


def _sha_digest(seed: str, idx: int, axis: str) -> bytes:
    h = hashlib.sha256()
    h.update(seed.encode("utf-8"))
    h.update(b":")
    h.update(str(idx).encode("ascii"))
    h.update(b":")
    h.update(axis.encode("utf-8"))
    return h.digest()


def _pick(seed: str, idx: int, axis: str, choices: List[Any]) -> Any:
    if not choices:
        raise ValueError("empty choices list")
    d = _sha_digest(seed, idx, axis)
    n = int.from_bytes(d[:8], "big", signed=False)
    return choices[n % len(choices)]


def _pick_subset(
    seed: str, idx: int, axis: str, choices: List[Any], k: int,
) -> List[Any]:
    """Pick a deterministic k-subset (preserving choices order)."""
    if k <= 0:
        return []
    if k >= len(choices):
        return list(choices)
    d = _sha_digest(seed, idx, axis)
    selected: List[Any] = []
    pool = list(choices)
    for j in range(k):
        n = int.from_bytes(d[j * 4:j * 4 + 4], "big", signed=False)
        if not pool:
            break
        chosen = pool.pop(n % len(pool))
        selected.append(chosen)
    return selected


# ---------------------------------------------------------------------------
# Per-family generators
# ---------------------------------------------------------------------------


def _gen_spinel(
    seed: str, idx: int,
) -> Tuple[str, Dict[str, int], Dict[str, int]]:
    fam = _FAMILY_DEFINITIONS["spinel"]
    a_sym, a_val = _pick(seed, idx, "spinel.A", fam["a_cations"])
    b_sym, b_val = _pick(seed, idx, "spinel.B", fam["b_cations"])
    # AB2O4 stoichiometry.
    formula = f"{a_sym}{b_sym}2O4"
    comp = {a_sym: 1, b_sym: 2, "O": 4}
    valences = {a_sym: a_val, b_sym: b_val, "O": -2}
    return formula, comp, valences


def _gen_perovskite(
    seed: str, idx: int,
) -> Tuple[str, Dict[str, int], Dict[str, int]]:
    fam = _FAMILY_DEFINITIONS["perovskite"]
    a_sym, a_val = _pick(seed, idx, "perov.A", fam["a_cations"])
    b_sym, b_val = _pick(seed, idx, "perov.B", fam["b_cations"])
    formula = f"{a_sym}{b_sym}O3"
    comp = {a_sym: 1, b_sym: 1, "O": 3}
    valences = {a_sym: a_val, b_sym: b_val, "O": -2}
    return formula, comp, valences


def _gen_layered_oxide(
    seed: str, idx: int,
) -> Tuple[str, Dict[str, int], Dict[str, int]]:
    fam = _FAMILY_DEFINITIONS["layered_oxide"]
    a_sym, a_val = _pick(seed, idx, "layer.A", fam["a_cations"])
    b_sym, b_val = _pick(seed, idx, "layer.B", fam["b_cations"])
    # AxBO2 — x in {1} for v0.1 (avoids fractional reporting).
    formula = f"{a_sym}{b_sym}O2"
    comp = {a_sym: 1, b_sym: 1, "O": 2}
    valences = {a_sym: a_val, b_sym: b_val, "O": -2}
    return formula, comp, valences


def _gen_oxide_interface(
    seed: str, idx: int,
) -> Tuple[str, Dict[str, int], Dict[str, int]]:
    fam = _FAMILY_DEFINITIONS["oxide_interface"]
    a_sym, a_val = _pick(seed, idx, "intf.A", fam["a_cations"])
    b_sym, b_val = _pick(seed, idx, "intf.B", fam["b_cations"])
    # Reported as one motif AO2-BO1.5 → integer surrogate: A1B2O7
    # (one AO2 unit + 2 BO1.5 units = one B2O3 unit) to keep integer
    # composition for charge-balance machinery.
    formula = f"{a_sym}{b_sym}2O7"
    comp = {a_sym: 1, b_sym: 2, "O": 7}
    valences = {a_sym: a_val, b_sym: b_val, "O": -2}
    return formula, comp, valences


_GENERATORS = {
    "spinel": _gen_spinel,
    "perovskite": _gen_perovskite,
    "layered_oxide": _gen_layered_oxide,
    "oxide_interface": _gen_oxide_interface,
}


# ---------------------------------------------------------------------------
# Industrial-hypothesis assignment
# ---------------------------------------------------------------------------


def _assign_hypotheses(
    seed: str, idx: int, family: str,
) -> List[str]:
    pool = list(_FAMILY_DEFINITIONS[family]["industrial_hypotheses"])
    # 1..min(3, |pool|) hypotheses per candidate.
    d = _sha_digest(seed, idx, "hypotheses.k")
    k = (int.from_bytes(d[:2], "big") % min(3, len(pool))) + 1
    return sorted(_pick_subset(seed, idx, "hypotheses.pick", pool, k))


# ---------------------------------------------------------------------------
# Top-level generation
# ---------------------------------------------------------------------------


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit candidate pool: host-path markers leaked: "
            f"{leaked}"
        )


def _family_for_index(
    family_request: str, idx: int, count: int,
) -> str:
    """For the mixed --family oxide_frontier, deterministically map an
    index to a base family per the fixed mix table. For a base family
    name, return it unchanged."""
    if family_request in _GENERATORS:
        return family_request
    if family_request != "oxide_frontier":
        raise ValueError(
            f"unknown family {family_request!r}; expected one of "
            f"{sorted(list(_GENERATORS) + ['oxide_frontier'])}"
        )
    # Distribute by mix table proportions, deterministic.
    total_weight = sum(w for _, w in _OXIDE_FRONTIER_MIX)
    cum: List[Tuple[int, str]] = []
    acc = 0
    for fam, w in _OXIDE_FRONTIER_MIX:
        acc += w
        cum.append((acc, fam))
    # Map idx -> position in [0, total_weight) round-robin so the mix
    # is honored regardless of count.
    pos = (idx * total_weight // max(1, count)) % total_weight
    for boundary, fam in cum:
        if pos < boundary:
            return fam
    return cum[-1][1]


def build_candidate_pool(
    *,
    family: str,
    count: int,
    seed: str,
    generated_at_utc: str,
) -> Dict[str, Any]:
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("seed must be a non-empty string")
    if not isinstance(count, int) or count <= 0 or count > 500:
        raise ValueError("count must be a positive int <= 500")
    if not isinstance(generated_at_utc, str) or not generated_at_utc.endswith(
        "+00:00"
    ):
        raise ValueError(
            "generated_at_utc must be ISO-8601 ending in +00:00"
        )

    candidates: List[Dict[str, Any]] = []
    for i in range(count):
        fam = _family_for_index(family, i, count)
        gen = _GENERATORS[fam]
        formula, comp, _ = gen(seed, i)
        hypotheses = _assign_hypotheses(seed, i, fam)
        candidates.append({
            "id": f"MX-{i + 1:04d}",
            "formula": formula,
            "family": fam,
            "composition": comp,
            "generation_method": "deterministic_rule_based_v0.1",
            "novelty_status": "unknown_not_validated",
            "industrial_hypotheses": hypotheses,
            "safety_flags": {
                "not_a_synthesis_recipe": True,
                "not_a_performance_claim": True,
                "requires_dft_validation": True,
                "requires_synthesis_validation": True,
            },
        })

    pool = {
        "schema": _SCHEMA,
        "family": family,
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "seed": seed,
        "count_requested": count,
        "count_emitted": len(candidates),
        "generator_version": "v0.1",
        "candidates": candidates,
    }

    blob = canonical_dumps(pool)
    _check_no_host_paths(blob)
    return pool


def render_markdown(pool: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Discovery — Candidate Pool "
        f"`{pool['family']}`"
    )
    lines.append("")
    lines.append(
        "> **AUTONOMOUS CANDIDATE PROPOSAL.** Deterministically generated"
        " from a pinned seed. Not a synthesis recipe, not a performance"
        " claim, not a novelty claim. Downstream stages (chemistry"
        " filter, industrial scorer, AI Council) refine the pool;"
        " nothing here is validated yet."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{pool['schema']}`")
    lines.append(f"- **Family**: `{pool['family']}`")
    lines.append(f"- **Seed**: `{pool['seed']}`")
    lines.append(f"- **Generated (UTC)**: {pool['generated_at_utc']}")
    lines.append(
        f"- **count_requested / count_emitted**: "
        f"`{pool['count_requested']} / {pool['count_emitted']}`"
    )
    lines.append(f"- **Generator version**: `{pool['generator_version']}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    lines.append("| id | formula | family | hypotheses |")
    lines.append("| --- | --- | --- | --- |")
    for c in pool["candidates"]:
        hyp = ", ".join(c["industrial_hypotheses"])
        lines.append(
            f"| `{c['id']}` | `{c['formula']}` | `{c['family']}` | {hyp} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_candidate_generator",
        description=(
            "Deterministic materials candidate proposal generator. "
            "Dry-run; nothing here is validated."
        ),
    )
    p.add_argument("--family", type=str, default="oxide_frontier")
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--seed", type=str, default="trinity-v0.1")
    p.add_argument(
        "--pinned-time", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    args = p.parse_args(argv)

    pool = build_candidate_pool(
        family=args.family,
        count=args.count,
        seed=args.seed,
        generated_at_utc=args.pinned_time,
    )

    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_CANDIDATES_{args.family}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_CANDIDATES_{args.family}.md"
    )
    out_json.write_text(canonical_dumps(pool), encoding="utf-8")
    out_md.write_text(render_markdown(pool), encoding="utf-8")

    print(f"[candidates] wrote {out_json}")
    print(f"[candidates] wrote {out_md}")
    print(
        f"[candidates] emitted: {pool['count_emitted']}; family={pool['family']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
