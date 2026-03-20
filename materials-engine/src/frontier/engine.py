"""Frontier engine — dual-target multiobjectve candidate selection.

Phase IV.C: Combines promoted production models (CGCNN formation_energy +
ALIGNN-Lite band_gap) with novelty, exotic, structure analytics, and
validation priority into a unified frontier ranking.

Uses existing corpus data (known properties) and optionally evaluates
generated candidates with real GNN prediction on lifted structures.
"""

import json
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ..schema import Material
from ..storage.db import MaterialsDB
from ..novelty.filter import NoveltyFilter
from ..analytics.descriptors import compute_descriptors
from ..normalization.structure import load_structure
from .spec import (
    FrontierProfile, FrontierCandidate, ALL_FRONTIER_PRESETS,
    SRC_CORPUS, SRC_GENERATED, SRC_EVALUATED,
    EV_KNOWN, EV_PREDICTED, EV_UNAVAILABLE, EV_STRUCTURE,
)
from .scoring import (
    stability_score, band_gap_fit_score, structure_quality_score,
    compute_frontier_score, assign_reason_codes,
)

log = logging.getLogger(__name__)

FRONTIER_DIR = "artifacts/frontier"


class FrontierEngine:
    """Dual-target frontier candidate selector."""

    def __init__(self, db: MaterialsDB, output_dir: str = FRONTIER_DIR):
        self.db = db
        self.output_dir = output_dir
        self._nf: Optional[NoveltyFilter] = None

    def _get_nf(self) -> NoveltyFilter:
        if self._nf is None:
            self._nf = NoveltyFilter(self.db)
        return self._nf

    def run(self, profile: Optional[FrontierProfile] = None,
            source: str = "corpus",
            generated_candidates: Optional[List[dict]] = None) -> dict:
        """Run a frontier selection.

        Args:
            profile: scoring profile (default: balanced_frontier)
            source: "corpus" | "generated" | "mixed"
            generated_candidates: list of candidate dicts for generated/mixed mode
        """
        if profile is None:
            profile = ALL_FRONTIER_PRESETS["balanced_frontier"]()
        profile.validate()

        now = datetime.now(timezone.utc).isoformat()
        run_id = hashlib.sha256(
            f"frontier|{profile.name}|{source}|{now}".encode()
        ).hexdigest()[:12]

        # Load candidates
        candidates = []
        if source in ("corpus", "mixed"):
            candidates.extend(self._load_corpus(profile))
        if source in ("generated", "mixed") and generated_candidates:
            candidates.extend(self._load_generated(generated_candidates, profile))

        # Score all candidates
        nf = self._get_nf()
        for c in candidates:
            self._score_candidate(c, profile, nf)

        # Filter
        filtered = [c for c in candidates
                    if c.formation_energy is None or c.formation_energy <= profile.fe_max]
        if profile.novelty_min > 0:
            filtered = [c for c in filtered if c.novelty_score >= profile.novelty_min]
        if profile.exotic_min > 0:
            filtered = [c for c in filtered if c.exotic_score >= profile.exotic_min]

        # Sort and rank
        filtered.sort(key=lambda c: -c.frontier_score)
        for i, c in enumerate(filtered[:profile.top_k]):
            c.rank = i + 1

        shortlist = filtered[:profile.top_k]

        result = {
            "run_id": run_id,
            "profile": profile.to_dict(),
            "source": source,
            "created_at": now,
            "summary": {
                "pool_size": len(candidates),
                "after_filter": len(filtered),
                "shortlist_size": len(shortlist),
                "score_range": {
                    "max": round(shortlist[0].frontier_score, 4) if shortlist else 0,
                    "min": round(shortlist[-1].frontier_score, 4) if shortlist else 0,
                },
            },
            "shortlist": [c.to_dict() for c in shortlist],
            "disclaimer": (
                "Frontier scores combine predicted formation_energy (CGCNN) + "
                "predicted band_gap (ALIGNN-Lite) + novelty/exotic heuristics. "
                "NOT DFT-validated. NOT experimentally confirmed. "
                "Properties tagged 'known' come from JARVIS DFT corpus. "
                "Properties tagged 'predicted' come from baseline GNN models."
            ),
        }

        return result

    def run_and_save(self, profile=None, source="corpus",
                     generated_candidates=None) -> tuple:
        result = self.run(profile, source, generated_candidates)
        path = self._save(result)
        return result, path

    def get_run(self, run_id: str) -> Optional[dict]:
        path = os.path.join(self.output_dir, f"frontier_run_{run_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list_runs(self) -> List[dict]:
        if not os.path.exists(self.output_dir):
            return []
        runs = []
        for f in sorted(os.listdir(self.output_dir)):
            if f.startswith("frontier_run_") and f.endswith(".json"):
                try:
                    with open(os.path.join(self.output_dir, f)) as fh:
                        d = json.load(fh)
                    runs.append({
                        "run_id": d.get("run_id"),
                        "profile": d.get("profile", {}).get("name"),
                        "source": d.get("source"),
                        "shortlist_size": d.get("summary", {}).get("shortlist_size"),
                        "created_at": d.get("created_at"),
                    })
                except Exception:
                    continue
        return runs

    # ================================================================
    # Internal
    # ================================================================

    def _load_corpus(self, profile: FrontierProfile) -> List[FrontierCandidate]:
        materials = self.db.list_materials(limit=profile.pool_limit)
        candidates = []
        for m in materials:
            c = FrontierCandidate(
                canonical_id=m.canonical_id,
                formula=m.formula,
                source_type=SRC_CORPUS,
                spacegroup=m.spacegroup,
                elements=m.elements,
                formation_energy=m.formation_energy,
                formation_energy_evidence=EV_KNOWN if m.formation_energy is not None else EV_UNAVAILABLE,
                band_gap=m.band_gap,
                band_gap_evidence=EV_KNOWN if m.band_gap is not None else EV_UNAVAILABLE,
                has_structure=bool(m.structure_data),
            )
            # Get density if structure available
            if m.structure_data:
                try:
                    struct = load_structure(m.structure_data)
                    if struct:
                        c.density = round(struct.density, 4)
                except Exception:
                    pass
            candidates.append(c)
        return candidates

    def _load_generated(self, gen_data: List[dict],
                        profile: FrontierProfile) -> List[FrontierCandidate]:
        candidates = []
        for g in gen_data:
            preds = g.get("predictions", g.get("scores", {}))
            c = FrontierCandidate(
                canonical_id=g.get("candidate_id", ""),
                formula=g.get("formula", ""),
                source_type=SRC_GENERATED if "candidate_id" in g else SRC_EVALUATED,
                spacegroup=g.get("spacegroup"),
                elements=g.get("elements", []),
                formation_energy=preds.get("formation_energy"),
                formation_energy_evidence=EV_PREDICTED if preds.get("formation_energy") is not None else EV_UNAVAILABLE,
                band_gap=preds.get("band_gap"),
                band_gap_evidence=EV_PREDICTED if preds.get("band_gap") is not None else EV_UNAVAILABLE,
                has_structure=g.get("lift", {}).get("confidence", 0) > 0,
            )
            candidates.append(c)
        return candidates

    def _score_candidate(self, c: FrontierCandidate,
                         profile: FrontierProfile,
                         nf: NoveltyFilter):
        # Stability
        c.stability_score = stability_score(c.formation_energy)

        # Band gap fit
        c.band_gap_fit_score = band_gap_fit_score(
            c.band_gap, profile.band_gap_target, profile.band_gap_tolerance)

        # Novelty + exotic
        try:
            m = Material(formula=c.formula, elements=c.elements,
                         n_elements=len(c.elements), spacegroup=c.spacegroup,
                         source="frontier", source_id=c.canonical_id or "ephemeral")
            m.compute_canonical_id()
            novelty_r, exotic_r = nf.check_exotic(m)
            c.novelty_score = novelty_r.novelty_score
            c.exotic_score = exotic_r.exotic_score
        except Exception:
            c.novelty_score = 0.0
            c.exotic_score = 0.0

        # Structure quality
        c.structure_quality = structure_quality_score(c.has_structure, c.density)

        # Validation priority (simple: higher novelty + stability → higher priority)
        c.validation_priority_score = min(1.0, 0.4 * c.novelty_score + 0.3 * c.stability_score + 0.3 * c.band_gap_fit_score)

        # Frontier score
        c.frontier_score = compute_frontier_score(profile, c)

        # Reason codes
        c.reason_codes = assign_reason_codes(c)

    def _save(self, result: dict) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        rid = result["run_id"]
        path = os.path.join(self.output_dir, f"frontier_run_{rid}.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        return path
