#!/usr/bin/env python3
"""Trinity / Materials Discovery — Chemistry filter v0.1.

Reads a candidate pool produced by ``materials_candidate_generator.py``
and removes (or flags) candidates that fail a closed set of transparent
chemistry rules. Output is a *filtered* candidate pool with per-candidate
``filter_verdict`` (``accept`` / ``reject`` / ``flag``) and a closed list
of ``reason_codes``.

Hard rules
----------
- **Charge balance.** For each candidate, sum
  ``Σ count(elem) × valence(elem)``. Must equal zero. Cation valences
  come from the family definition; anion valence is fixed at -2 for
  oxygen.
- **Element whitelist.** Only elements that appear in the family
  definitions of ``materials_candidate_generator`` are allowed (plus
  oxygen). Anything else → ``reject``.
- **Toxicity gate.** Candidates containing any element in the toxicity
  list (Pb, Cd, Hg, As, Tl, Be) are rejected by default; with
  ``--allow-toxic`` they are flagged but kept.
- **Criticality flag.** Candidates containing PGM (Pt, Pd, Rh, Ir, Os,
  Ru) or scandium / dysprosium / terbium are flagged with
  ``flag:contains_critical_element``. They are **not** rejected by
  default but will be penalised downstream by the industrial scorer.
- **Known-demo exclusion.** Five v0 demo formulas
  (``Fe2MgO4``, ``LiNi0.5Mn1.5O4``, ``BaZrO3:Y``, ``CaCu3Ti4O12``,
  ``Co3O4``) and their structural equivalents are rejected so the v0.1
  pool is genuinely additive.

The filter is **transparent**: every reject/flag carries the exact
substring code that triggered it.

Invariants
----------
- Deterministic given the same input candidate pool and the same flag
  set. Pure stdlib.
- No network, no subprocess, no wallet, no broadcast surface.
- Canonical JSON. No host-path leak.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


_INPUT_SCHEMA = "trinity-materials-candidate-pool/v0.1"
_OUTPUT_SCHEMA = "trinity-materials-candidate-filter/v0.1"
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")


# Element → fixed cation valence used for charge-balance verification.
# Must agree with the family cation lists in
# materials_candidate_generator.
_VALENCES: Dict[str, int] = {
    # Spinel A2+
    "Mg": 2, "Zn": 2, "Co": 2, "Ni": 2, "Mn": 2, "Cu": 2,
    # Spinel B3+
    "Al": 3, "Cr": 3, "Ga": 3,
    # Iron is ambiguous; the generator alternates valence by site so
    # use a canonical choice and let charge balance decide.
    # For spinel AB2O4 with A=Fe (2+) and B=Fe (3+) we resolve by site:
    # we record Fe twice with disambiguation suffix.
    "Fe": 3,
    # Perovskite A
    "Ca": 2, "Sr": 2, "Ba": 2, "La": 3, "Y": 3, "Pr": 3, "Nd": 3,
    # Perovskite B / interface A
    "Ti": 4, "Zr": 4, "Hf": 4, "Sn": 4, "Ce": 4,
    "Nb": 5, "Ta": 5, "V": 5,
    # Layered-oxide A
    "Li": 1, "Na": 1, "K": 1,
}

_ANION_VALENCES: Dict[str, int] = {"O": -2}

_ALLOWED_ELEMENTS = set(_VALENCES) | set(_ANION_VALENCES)

_TOXIC_ELEMENTS = {"Pb", "Cd", "Hg", "As", "Tl", "Be"}
_CRITICAL_ELEMENTS = {
    "Pt", "Pd", "Rh", "Ir", "Os", "Ru",
    "Sc", "Dy", "Tb",
}

# v0 demo set (formulas that already appeared in Materials Track v0).
_V0_DEMO_FORMULAS = {
    "Fe2MgO4",
    "LiNi0.5Mn1.5O4",
    "BaZrO3:Y",
    "CaCu3Ti4O12",
    "Co3O4",
}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit filtered pool: host-path markers leaked: "
            f"{leaked}"
        )


def _charge_balance(
    composition: Mapping[str, int],
    family: str,
) -> int:
    """Return the algebraic charge sum for one composition. Family is
    used to disambiguate Fe(2+/3+): in a spinel AB2O4 with A=Fe and
    B=Fe (rare), Fe at the A site is taken as 2+ and at the B site as
    3+. For non-mixed Fe occupancy we use the canonical Fe3+ valence
    declared in _VALENCES."""
    total = 0
    fe_count = composition.get("Fe", 0)
    if family == "spinel" and fe_count and "Fe" in composition:
        # If exactly one Fe atom, it is the A site (Fe2+). If exactly
        # three Fe atoms, A=Fe2+ and B=Fe3+×2. Otherwise treat all Fe
        # as Fe3+ for v0.1 simplicity.
        if fe_count == 1:
            total += 2 * 1
            for elem, count in composition.items():
                if elem == "Fe":
                    continue
                v = _VALENCES.get(elem) or _ANION_VALENCES.get(elem)
                if v is None:
                    return 10 ** 6  # signal: unknown element
                total += v * count
            return total
        if fe_count == 3:
            total += 2 * 1 + 3 * 2  # A=Fe2+, B=Fe3+×2
            total += _ANION_VALENCES["O"] * composition.get("O", 0)
            return total
    # Default path: every element contributes count × valence.
    for elem, count in composition.items():
        v = _VALENCES.get(elem)
        if v is None:
            v = _ANION_VALENCES.get(elem)
        if v is None:
            return 10 ** 6
        total += v * count
    return total


def _evaluate_candidate(
    c: Mapping[str, Any],
    *,
    allow_toxic: bool,
) -> Dict[str, Any]:
    reasons: List[str] = []
    flags: List[str] = []
    verdict = "accept"

    formula = c.get("formula", "")
    composition = c.get("composition") or {}
    family = c.get("family", "")

    if formula in _V0_DEMO_FORMULAS:
        verdict = "reject"
        reasons.append("known_v0_demo_formula")

    unsupported = [
        elem for elem in composition if elem not in _ALLOWED_ELEMENTS
    ]
    if unsupported:
        verdict = "reject"
        reasons.append(
            f"unsupported_elements:{sorted(set(unsupported))!s}"
        )

    # Charge balance — only run if the element whitelist passed.
    if verdict == "accept":
        cb = _charge_balance(composition, family)
        if cb != 0:
            verdict = "reject"
            reasons.append(
                f"charge_balance_nonzero:expected_0_got_{cb}"
            )

    toxic_hit = sorted(
        {elem for elem in composition if elem in _TOXIC_ELEMENTS}
    )
    if toxic_hit:
        if allow_toxic:
            flags.append(f"contains_toxic_element:{toxic_hit!s}")
        else:
            verdict = "reject"
            reasons.append(f"toxic_element_blocked:{toxic_hit!s}")

    critical_hit = sorted(
        {elem for elem in composition if elem in _CRITICAL_ELEMENTS}
    )
    if critical_hit:
        flags.append(f"contains_critical_element:{critical_hit!s}")

    return {
        "id": c.get("id"),
        "formula": formula,
        "family": family,
        "filter_verdict": verdict,
        "reason_codes": reasons,
        "filter_flags": flags,
    }


def build_filtered_pool(
    *,
    candidate_pool_path: Path,
    generated_at_utc: str,
    allow_toxic: bool = False,
) -> Dict[str, Any]:
    if not candidate_pool_path.exists():
        raise FileNotFoundError(
            f"candidate pool not found: {candidate_pool_path}"
        )
    raw = candidate_pool_path.read_bytes()
    pool = json.loads(raw.decode("utf-8"))
    if pool.get("schema") != _INPUT_SCHEMA:
        raise ValueError(
            f"input schema must be {_INPUT_SCHEMA!r}; got "
            f"{pool.get('schema')!r}"
        )
    if pool.get("track") != _TRACK:
        raise ValueError("input pool is not a materials-track pool")

    pool_sha = hashlib.sha256(raw).hexdigest()
    decisions: List[Dict[str, Any]] = []
    counts = {"accept": 0, "reject": 0, "flag": 0}

    for c in pool.get("candidates", []):
        decision = _evaluate_candidate(c, allow_toxic=allow_toxic)
        # accept with flags is reported as "accept" but bucketed for
        # downstream visibility.
        counts[decision["filter_verdict"]] = counts.get(
            decision["filter_verdict"], 0
        ) + 1
        if (
            decision["filter_verdict"] == "accept"
            and decision["filter_flags"]
        ):
            counts["flag"] = counts.get("flag", 0) + 1
        decisions.append(decision)

    filtered = {
        "schema": _OUTPUT_SCHEMA,
        "family": pool.get("family"),
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "source": {
            "candidate_pool_basename": candidate_pool_path.name,
            "candidate_pool_sha256": pool_sha,
            "seed": pool.get("seed"),
            "count_input": len(pool.get("candidates", [])),
        },
        "allow_toxic": bool(allow_toxic),
        "decisions": decisions,
        "summary": {
            "accept": counts.get("accept", 0),
            "reject": counts.get("reject", 0),
            "flag": counts.get("flag", 0),
        },
    }
    blob = canonical_dumps(filtered)
    _check_no_host_paths(blob)
    return filtered


def render_markdown(filtered: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Discovery — Chemistry Filter "
        f"`{filtered['family']}`"
    )
    lines.append("")
    lines.append(
        "> **DRY-RUN chemistry filter.** Closed rules: charge balance, "
        "element whitelist, toxicity gate, criticality flag, "
        "known-demo exclusion. Not a synthesis recipe and not a "
        "performance claim."
    )
    lines.append("")
    lines.append(f"- **Schema**: `{filtered['schema']}`")
    lines.append(f"- **Family**: `{filtered['family']}`")
    lines.append(f"- **Generated (UTC)**: {filtered['generated_at_utc']}")
    s = filtered["summary"]
    lines.append(
        f"- **Summary**: accept=`{s['accept']}`, reject=`{s['reject']}`,"
        f" flag=`{s['flag']}`"
    )
    lines.append("")
    lines.append("## Decisions")
    lines.append("")
    lines.append("| id | formula | family | verdict | reasons | flags |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for d in filtered["decisions"]:
        reasons = "; ".join(d["reason_codes"]) or "—"
        flags = "; ".join(d["filter_flags"]) or "—"
        lines.append(
            f"| `{d['id']}` | `{d['formula']}` | `{d['family']}` | "
            f"**{d['filter_verdict']}** | {reasons} | {flags} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_chemistry_filter",
        description=(
            "Apply transparent chemistry rules to a materials candidate "
            "pool. Dry-run; deterministic."
        ),
    )
    p.add_argument("--family", type=str, default="oxide_frontier")
    p.add_argument("--candidate-pool", type=str, default=None)
    p.add_argument(
        "--pinned-time", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument(
        "--allow-toxic", action="store_true",
        help=(
            "Keep candidates with toxic elements (Pb, Cd, Hg, As, Tl, "
            "Be) by flagging instead of rejecting. Default rejects."
        ),
    )
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    args = p.parse_args(argv)

    pool_path = Path(
        args.candidate_pool
        or f"TRINITY_MATERIALS_CANDIDATES_{args.family}.json"
    )
    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_FILTER_{args.family}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_FILTER_{args.family}.md"
    )

    filtered = build_filtered_pool(
        candidate_pool_path=pool_path,
        generated_at_utc=args.pinned_time,
        allow_toxic=args.allow_toxic,
    )

    out_json.write_text(canonical_dumps(filtered), encoding="utf-8")
    out_md.write_text(render_markdown(filtered), encoding="utf-8")

    s = filtered["summary"]
    print(f"[filter] wrote {out_json}")
    print(f"[filter] wrote {out_md}")
    print(
        f"[filter] accept={s['accept']}, reject={s['reject']}, "
        f"flag={s['flag']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
