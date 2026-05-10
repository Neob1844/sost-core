#!/usr/bin/env python3
"""Trinity entrypoint — AOI scorecard to dossier.

Usage
-----
    python3 scripts/trinity/aoi_to_dossier.py <aoi_name>
    python3 scripts/trinity/aoi_to_dossier.py --scorecard <path/to/file.json>
    python3 scripts/trinity/aoi_to_dossier.py kalgoorlie --out /tmp/dossier.md

Behaviour
---------
1. Locate the scorecard JSON for the requested AOI. Two resolution
   strategies, in order:
     a. `--scorecard <path>` if explicitly given.
     b. Search `<repo_parent>/geaspirit-research/GeaSpirit_outputs/`
        and `<repo>/geaspirit/outputs/` for `scorecard_<aoi>.json`.

2. Call `review_aoi(scorecard)` from
   `materials-engine-private.src.trinity.geo_target_council` to obtain
   a list of `GeoTargetReview` objects.

3. Render a Markdown dossier and a canonical JSON copy. Compute the
   SHA-256 of the canonical JSON bytes. Print the hash and the file
   paths on stdout.

4. The Markdown footer carries the SHA-256 plus a stub `sost-cli`
   command the operator can run manually to register the dossier as a
   `DOC_REF_OPEN` capsule on chain. The script never broadcasts on its
   own.

No network. No paid model. The bridge defaults to the three free
council members; this script does not override that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[2]            # sost-core/
_REPO_PARENT = _REPO_ROOT.parent.parent        # the dir containing sost-core/
                                               # in a WSL layout this is
                                               # /home/sost/SOST; in a VPS
                                               # layout where sost-core lives
                                               # under /opt it resolves to /
                                               # and is therefore not safe to
                                               # use as the only search root.
                                               # See env-var overrides below.


def _env_paths(name: str) -> List[Path]:
    """Read a colon-separated path env var, returning existing dirs.

    Used by `_candidate_scorecard_paths` (for `TRINITY_GEASPIRIT_OUTPUTS_PATH`)
    and `_ensure_bridge_importable` (for `TRINITY_MATERIALS_ENGINE_PATH`).
    Empty / unset / nonexistent entries are silently skipped — the
    caller is expected to fall back to compiled-in defaults.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    out: List[Path] = []
    for chunk in raw.split(os.pathsep):
        chunk = chunk.strip()
        if not chunk:
            continue
        p = Path(chunk).expanduser().resolve()
        if p.exists():
            out.append(p)
    return out


def _candidate_scorecard_paths(aoi: str) -> List[Path]:
    """Where to look for a scorecard JSON for the given AOI.

    Search order (first match wins per the caller; this function
    returns every match so the operator can see all candidates):

      1. `TRINITY_GEASPIRIT_OUTPUTS_PATH` (env var, colon-separated).
         Recommended for VPS / non-WSL environments.
      2. `<repo_parent>/geaspirit-research/GeaSpirit_outputs/`
         (the WSL-friendly default).
      3. `<repo_root>/geaspirit/outputs/`
         (local repo subdir, used when scorecards are committed in-tree).
      4. `~/SOST/geaspirit-research/GeaSpirit_outputs/`
         (last-chance fallback for the canonical WSL layout, robust to
         the repo living somewhere unexpected on disk).
    """
    name = aoi.strip().lower()
    candidates: List[Path] = []

    # 1) Env-var override(s). Highest priority because the operator
    #    set it intentionally for this machine.
    for root in _env_paths("TRINITY_GEASPIRIT_OUTPUTS_PATH"):
        for p in root.rglob(f"scorecard_{name}.json"):
            candidates.append(p)
        # Also accept the scorecard file directly under the root.
        direct = root / f"scorecard_{name}.json"
        if direct.is_file() and direct not in candidates:
            candidates.append(direct)

    # 2) WSL-friendly sister directory (the default we shipped in v0).
    sister = _REPO_PARENT / "geaspirit-research" / "GeaSpirit_outputs"
    if sister.exists():
        for p in sister.rglob(f"scorecard_{name}.json"):
            if p not in candidates:
                candidates.append(p)

    # 3) In-repo local outputs dir.
    local = _REPO_ROOT / "geaspirit" / "outputs"
    if local.exists():
        for p in local.rglob(f"scorecard_{name}.json"):
            if p not in candidates:
                candidates.append(p)

    # 4) Canonical WSL layout, last-chance fallback.
    home = Path(os.path.expanduser("~"))
    home_sister = home / "SOST" / "geaspirit-research" / "GeaSpirit_outputs"
    if home_sister.exists() and home_sister != sister:
        for p in home_sister.rglob(f"scorecard_{name}.json"):
            if p not in candidates:
                candidates.append(p)

    return candidates


def _materials_engine_root() -> Optional[Path]:
    """Resolve the materials-engine-private root directory.

    Search order (first existing wins):

      1. `TRINITY_MATERIALS_ENGINE_PATH` (env var).
      2. `<repo_parent>/materials-engine-private/`
         (WSL-friendly default shipped in v0).
      3. `~/SOST/materials-engine-private/`
         (canonical WSL layout, last-chance fallback).
    """
    env = _env_paths("TRINITY_MATERIALS_ENGINE_PATH")
    if env:
        return env[0]
    candidate = _REPO_PARENT / "materials-engine-private"
    if candidate.exists():
        return candidate
    home = Path(os.path.expanduser("~"))
    home_candidate = home / "SOST" / "materials-engine-private"
    if home_candidate.exists():
        return home_candidate
    return None


def _ensure_bridge_importable() -> None:
    """Add `materials-engine-private` to sys.path so the bridge import
    works whether the caller installed the package or not.
    """
    root = _materials_engine_root()
    if root is None:
        return
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)


_ensure_bridge_importable()

from src.trinity.geo_target_council import (   # noqa: E402
    GeoTargetReview,
    load_scorecard,
    review_aoi,
)


# ---------------------------------------------------------------------------
# Canonical serialisation (deterministic, sorted keys, UTF-8, LF newlines)
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> bytes:
    """Bytes that hash deterministically. The same logical input
    produces the same bytes across runs and machines.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Dossier assembly
# ---------------------------------------------------------------------------

_DOSSIER_VERSION = "trinity-dossier/v0"


def _build_dossier(
    aoi_name: str,
    scorecard: Dict[str, Any],
    reviews: List[GeoTargetReview],
    *,
    scorecard_path: Optional[Path] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the JSON-serialisable dossier dict.

    `generated_at` is an injectable ISO-8601 timestamp so tests can pin
    deterministic output. In normal use the caller leaves it as None.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    honesty = scorecard.get("honesty_matrix") or {}
    fallback = any(r.fallback_mode for r in reviews)

    return {
        "schema": _DOSSIER_VERSION,
        "generated_at_utc": generated_at,
        "aoi": aoi_name,
        "source": {
            "scorecard_path": (
                str(scorecard_path) if scorecard_path else "<inline>"
            ),
            "scorecard_zone": scorecard.get("zone"),
            "scorecard_features_available": scorecard.get(
                "features_available"
            ),
            "scorecard_features_total": scorecard.get("features_total"),
            "honesty_matrix": honesty,
        },
        "fallback_mode": fallback,
        "reviews": [r.to_dict() for r in reviews],
        "summary": {
            "n_reviews": len(reviews),
            "decisions": _decision_tally(reviews),
        },
        "publishability": "needs_human_review",
        "operator_actions": [
            (
                "Inspect the per-review next_step strings; only promote a "
                "target after independent geological field validation."
            ),
            (
                "Optionally register the dossier hash as a SOST capsule "
                "with `sost-cli send --capsule-mode doc-ref-open --capsule-locator "
                "<https-url-of-dossier> --recipient-pubkey <self>`. The "
                "hash to register is printed below."
            ),
        ],
    }


def _decision_tally(reviews: List[GeoTargetReview]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in reviews:
        d = r.decision.decision
        out[d] = out.get(d, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _md_escape(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown(dossier: Dict[str, Any], dossier_sha256: str) -> str:
    aoi = dossier["aoi"]
    src = dossier["source"]
    honesty = src["honesty_matrix"] or {}

    lines: List[str] = []
    lines.append(f"# Trinity dossier — AOI `{aoi}`")
    lines.append("")
    lines.append(f"- **Schema**: `{dossier['schema']}`")
    lines.append(f"- **Generated (UTC)**: {dossier['generated_at_utc']}")
    lines.append(f"- **Source scorecard**: `{src['scorecard_path']}`")
    lines.append(
        f"- **Features available / total**: "
        f"{src.get('scorecard_features_available')} / "
        f"{src.get('scorecard_features_total')}"
    )
    lines.append(f"- **Fallback mode**: `{dossier['fallback_mode']}`")
    lines.append(f"- **Publishability**: `{dossier['publishability']}`")
    lines.append("")

    lines.append("## Honesty matrix (verbatim from source scorecard)")
    lines.append("")
    if honesty:
        if honesty.get("tier"):
            lines.append(f"- **Tier**: {_md_escape(honesty.get('tier'))}")
        if honesty.get("environment"):
            lines.append(
                f"- **Environment**: {_md_escape(honesty.get('environment'))}"
            )
        if honesty.get("adjusted_confidence") is not None:
            lines.append(
                f"- **Adjusted confidence**: "
                f"{honesty.get('adjusted_confidence')}"
            )
        if honesty.get("recommendation"):
            lines.append("")
            lines.append(
                f"> **Source recommendation**: "
                f"{_md_escape(honesty.get('recommendation'))}"
            )
        if honesty.get("what_it_doesnt_see"):
            lines.append("")
            lines.append("**Acknowledged blind spots from the source:**")
            for bs in honesty.get("what_it_doesnt_see") or []:
                lines.append(f"- {_md_escape(bs)}")
    else:
        lines.append("_(scorecard had no honesty_matrix block)_")
    lines.append("")

    lines.append("## Reviews")
    lines.append("")
    for i, r in enumerate(dossier["reviews"], start=1):
        hyp = r["hypothesis"]
        dec = r["decision"]
        ctx = r["deposit_type_context"]
        lines.append(f"### {i}. {_md_escape(hyp.get('title'))}")
        lines.append("")
        lines.append(f"- **Subject**: `{hyp.get('subject')}`")
        lines.append(f"- **Type**: `{hyp.get('type')}`")
        lines.append(f"- **Hypothesis hash**: `{hyp.get('hypothesis_hash')}`")
        lines.append(f"- **Council decision**: `{dec.get('decision')}` "
                     f"(confidence {dec.get('confidence'):.2f})")
        if dec.get("next_step"):
            lines.append(
                f"- **Next step (council)**: {_md_escape(dec.get('next_step'))}"
            )
        if dec.get("strongest_argument"):
            lines.append(
                f"- **Strongest argument**: "
                f"{_md_escape(dec.get('strongest_argument'))}"
            )
        if dec.get("contradictions"):
            lines.append("- **Contradictions**:")
            for c in dec.get("contradictions") or []:
                lines.append(f"    - {_md_escape(c)}")
        lines.append("")
        lines.append(f"**Claim:** {_md_escape(hyp.get('claim'))}")
        lines.append("")
        if hyp.get("why_it_might_be_true"):
            lines.append(
                f"**Why it might be true:** "
                f"{_md_escape(hyp.get('why_it_might_be_true'))}"
            )
            lines.append("")
        if hyp.get("evidence_needed"):
            lines.append("**Evidence needed:**")
            for e in hyp.get("evidence_needed") or []:
                lines.append(f"- {_md_escape(e)}")
            lines.append("")
        if hyp.get("validation_path"):
            lines.append("**Validation path:**")
            for v in hyp.get("validation_path") or []:
                lines.append(f"- `{v}`")
            lines.append("")
        if ctx:
            lines.append("**Materials Engine context "
                         "(deposit-type → typical materials, hardcoded v0):**")
            lines.append(f"- Primary commodity: `{ctx.get('primary_commodity')}`")
            if ctx.get("byproducts"):
                lines.append(
                    f"- Byproducts: "
                    + ", ".join(f"`{b}`" for b in ctx.get("byproducts"))
                )
            if ctx.get("typical_minerals"):
                lines.append(
                    f"- Typical minerals: "
                    + ", ".join(f"`{m}`" for m in ctx.get("typical_minerals"))
                )
            if ctx.get("industrial_relevance"):
                lines.append(
                    f"- Industrial relevance: "
                    f"{_md_escape(ctx.get('industrial_relevance'))}"
                )
            lines.append("")
        opinions = dec.get("opinions") or []
        if opinions:
            lines.append("**Council opinions:**")
            lines.append("")
            lines.append("| Member | Verdict | Confidence | Rationale |")
            lines.append("| --- | --- | --- | --- |")
            for o in opinions:
                lines.append(
                    f"| `{o.get('member')}` | `{o.get('verdict')}` | "
                    f"{float(o.get('confidence', 0.0)):.2f} | "
                    f"{_md_escape(o.get('rationale'))} |"
                )
            lines.append("")
        lines.append("---")
        lines.append("")

    summary = dossier["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Reviews emitted**: {summary['n_reviews']}")
    if summary.get("decisions"):
        lines.append("- **Decision tally**:")
        for k, v in sorted(summary["decisions"].items()):
            lines.append(f"    - `{k}`: {v}")
    lines.append("")

    lines.append("## Operator actions")
    lines.append("")
    for a in dossier.get("operator_actions") or []:
        lines.append(f"- {_md_escape(a)}")
    lines.append("")

    lines.append("## Integrity")
    lines.append("")
    lines.append(
        f"- **Canonical JSON SHA-256**: `{dossier_sha256}`"
    )
    lines.append(
        "- The hash above is computed over the canonical (sorted, "
        "no-spaces, ASCII) JSON serialisation of the dossier object. "
        "Re-running the script with the same scorecard input will "
        "produce a different hash if the `generated_at_utc` field "
        "changes; pass `--pinned-time` to fix it."
    )
    lines.append("")
    lines.append(
        "## Capsule registration (manual, optional)"
    )
    lines.append("")
    lines.append(
        "If the operator chooses to register this dossier on chain as "
        "proof of priority, the SHA-256 above is the locator content. "
        "Two natural carriers in SOST are:"
    )
    lines.append("")
    lines.append(
        "1. `OPEN_NOTE_INLINE` — short label fitting in 80 bytes, "
        "for example: `trinity-dossier kalgoorlie sha256:<first16hex>`."
    )
    lines.append(
        "2. `DOC_REF_OPEN` — full URL pointing at the dossier file "
        "(commit hash on a public mirror or hosted JSON), with the "
        "SHA-256 stored in the capsule's hash field."
    )
    lines.append("")
    lines.append(
        "The script does not broadcast. The dossier is not a "
        "geological conclusion; it is a council-reviewed plan based "
        "on remote-proxy evidence with explicit limits."
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _default_output_paths(aoi: str) -> Tuple[Path, Path]:
    md = _REPO_ROOT / f"TRINITY_DEMO_DOSSIER_{aoi}.md"
    js = _REPO_ROOT / f"TRINITY_DEMO_DOSSIER_{aoi}.json"
    return md, js


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="aoi_to_dossier",
        description="Generate a Trinity dossier from a Geaspirit scorecard.",
    )
    p.add_argument(
        "aoi", nargs="?", default=None,
        help="AOI name (used to locate scorecard_<aoi>.json automatically). "
             "Optional if --scorecard is given."
    )
    p.add_argument(
        "--scorecard", type=str, default=None,
        help="Explicit path to the scorecard JSON. Overrides AOI lookup."
    )
    p.add_argument(
        "--out-md", type=str, default=None,
        help="Output Markdown path. Default: TRINITY_DEMO_DOSSIER_<aoi>.md"
    )
    p.add_argument(
        "--out-json", type=str, default=None,
        help="Output JSON path. Default: TRINITY_DEMO_DOSSIER_<aoi>.json"
    )
    p.add_argument(
        "--max-targets", type=int, default=10,
        help="Max number of ranked targets to emit hypotheses for."
    )
    p.add_argument(
        "--pinned-time", type=str, default=None,
        help="Pin generated_at_utc for deterministic SHA-256 (used by tests)."
    )
    args = p.parse_args(argv)

    if not args.aoi and not args.scorecard:
        print("error: provide an AOI name or --scorecard <path>", file=sys.stderr)
        return 2

    # Resolve scorecard.
    if args.scorecard:
        scorecard_path = Path(args.scorecard).resolve()
        if not scorecard_path.exists():
            print(f"error: scorecard not found at {scorecard_path}",
                  file=sys.stderr)
            return 1
    else:
        candidates = _candidate_scorecard_paths(args.aoi)
        if not candidates:
            env_dirs = _env_paths("TRINITY_GEASPIRIT_OUTPUTS_PATH")
            home = Path(os.path.expanduser("~"))
            print(
                f"error: no scorecard found for AOI {args.aoi!r}.\n"
                f"Searched in this order:\n"
                + "".join(f"  1. {p} (env TRINITY_GEASPIRIT_OUTPUTS_PATH)\n"
                          for p in env_dirs)
                + (""
                   if env_dirs
                   else "  1. (env TRINITY_GEASPIRIT_OUTPUTS_PATH unset)\n")
                + f"  2. {_REPO_PARENT}/geaspirit-research/GeaSpirit_outputs/\n"
                + f"  3. {_REPO_ROOT}/geaspirit/outputs/\n"
                + f"  4. {home}/SOST/geaspirit-research/GeaSpirit_outputs/\n"
                + "Fix: set TRINITY_GEASPIRIT_OUTPUTS_PATH=/path/to/outputs "
                  "or pass --scorecard /full/path/scorecard_<aoi>.json.",
                file=sys.stderr,
            )
            return 1
        scorecard_path = candidates[0]
        print(f"[trinity] using scorecard: {scorecard_path}", file=sys.stderr)

    aoi_name = (args.aoi or scorecard_path.stem.replace("scorecard_", "")).lower()

    # Run bridge.
    scorecard = load_scorecard(scorecard_path)
    reviews = review_aoi(scorecard, aoi_name=aoi_name,
                         max_targets=args.max_targets)

    # Build dossier and hash.
    dossier = _build_dossier(
        aoi_name=aoi_name,
        scorecard=scorecard,
        reviews=reviews,
        scorecard_path=scorecard_path,
        generated_at=args.pinned_time,
    )
    canonical = _canonical_json(dossier)
    dossier_sha256 = _sha256_hex(canonical)

    # Render Markdown.
    md_text = _render_markdown(dossier, dossier_sha256)

    # Decide output paths.
    if args.out_md:
        md_path = Path(args.out_md)
    else:
        md_path = _default_output_paths(aoi_name)[0]
    if args.out_json:
        js_path = Path(args.out_json)
    else:
        js_path = _default_output_paths(aoi_name)[1]

    md_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    js_path.write_bytes(canonical)

    print(f"[trinity] wrote {md_path}")
    print(f"[trinity] wrote {js_path}")
    print(f"[trinity] sha256: {dossier_sha256}")
    print(f"[trinity] reviews: {len(reviews)} "
          f"(fallback_mode={any(r.fallback_mode for r in reviews)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
