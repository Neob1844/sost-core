"""Shortlist engine — candidate pool → filtered → ranked → shortlist.

Phase III.B: Integrates novelty, exotic, stability, property fit,
and T/P screening into a single reproducible pipeline.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from ..schema import Material
from ..storage.db import MaterialsDB
from ..novelty.filter import NoveltyFilter
from ..thermo.conditions import ThermoPressureConditions, AMBIENT_TEMPERATURE_K, AMBIENT_PRESSURE_GPA
from ..thermo.proxies import screen_tp_proxy
from .criteria import ShortlistCriteria, default_criteria
from .ranking import (
    CandidateResult, compute_stability_score, compute_property_fit,
    assign_decision, ACCEPTED_THRESHOLD,
)

log = logging.getLogger(__name__)


class ShortlistEngine:
    """End-to-end shortlist builder.

    Pipeline:
      1. Load candidate pool from DB (or receive materials directly)
      2. Apply hard filters → reject disqualified
      3. Score each candidate (novelty, exotic, stability, property fit)
      4. Apply T/P proxy screening if conditions provided
      5. Compute weighted shortlist_score
      6. Assign decision bands (accepted/watchlist/rejected)
      7. Rank and select top_k
    """

    def __init__(self, db: MaterialsDB):
        self.db = db
        self._nf: Optional[NoveltyFilter] = None

    def _get_novelty_filter(self) -> NoveltyFilter:
        if self._nf is None:
            self._nf = NoveltyFilter(self.db)
        return self._nf

    def build(self, criteria: Optional[ShortlistCriteria] = None,
              conditions: Optional[ThermoPressureConditions] = None,
              materials: Optional[List[Material]] = None,
              pool_limit: int = 5000) -> dict:
        """Build a shortlist from the corpus or provided materials.

        Args:
            criteria: Selection criteria (defaults to sensible defaults)
            conditions: T/P conditions for screening (None = ambient)
            materials: If provided, use these instead of DB corpus
            pool_limit: Max materials to load from DB

        Returns:
            dict with pool_size, criteria, candidates, decisions summary, disclaimers
        """
        if criteria is None:
            criteria = default_criteria()
        criteria.validate()

        if conditions is not None:
            conditions.validate()

        # Load pool
        if materials is not None:
            pool = materials
        else:
            pool = self.db.list_materials(limit=pool_limit)

        nf = self._get_novelty_filter()
        candidates: List[CandidateResult] = []

        for m in pool:
            c = self._evaluate_candidate(m, criteria, conditions, nf)
            candidates.append(c)

        # Sort by shortlist_score descending
        candidates.sort(key=lambda c: -c.shortlist_score)

        # Assign ranks
        for i, c in enumerate(candidates):
            c.rank = i + 1

        # Select top_k accepted + watchlist
        shortlist = [c for c in candidates
                     if c.decision in ("accepted", "watchlist")][:criteria.top_k]

        decisions = {"accepted": 0, "watchlist": 0, "rejected": 0}
        for c in candidates:
            decisions[c.decision] += 1

        return {
            "pool_size": len(pool),
            "evaluated": len(candidates),
            "criteria": criteria.to_dict(),
            "conditions": conditions.to_dict() if conditions else None,
            "decisions": decisions,
            "shortlist_size": len(shortlist),
            "shortlist": [c.to_dict() for c in shortlist],
            "all_candidates_count": len(candidates),
            "disclaimer": (
                "Shortlist scores are relative to the current ingested corpus. "
                "T/P screening uses heuristic proxies, not physics simulation. "
                "Exotic/novel = rare/unexplored, not necessarily useful."
            ),
        }

    def _evaluate_candidate(self, m: Material,
                            criteria: ShortlistCriteria,
                            conditions: Optional[ThermoPressureConditions],
                            nf: NoveltyFilter) -> CandidateResult:
        """Evaluate a single candidate against criteria."""
        c = CandidateResult(
            canonical_id=m.canonical_id,
            formula=m.formula,
            source=m.source,
            spacegroup=m.spacegroup,
            band_gap=m.band_gap,
            formation_energy=m.formation_energy,
        )

        # --- Hard filters ---
        if criteria.require_valid_structure and not m.has_valid_structure:
            c.reason_codes.append("structure_invalid")
            c.decision = "rejected"
            return c

        for prop in criteria.require_properties:
            if getattr(m, prop, None) is None:
                c.reason_codes.append("missing_required_property")
                c.decision = "rejected"
                return c

        if (criteria.max_formation_energy is not None
                and m.formation_energy is not None
                and m.formation_energy > criteria.max_formation_energy):
            c.reason_codes.append("formation_energy_too_high")
            c.decision = "rejected"
            return c

        # --- Novelty + Exotic ---
        try:
            novelty, exotic = nf.check_exotic(m)
            c.novelty_score = novelty.novelty_score
            c.exotic_score = exotic.exotic_score
        except Exception:
            c.novelty_score = 0.0
            c.exotic_score = 0.0

        if c.novelty_score < criteria.novelty_min and criteria.novelty_min > 0:
            c.reason_codes.append("below_novelty_minimum")
            c.decision = "rejected"
            return c

        # --- Stability ---
        c.stability_score = compute_stability_score(
            m.formation_energy, m.energy_above_hull)

        # --- Property fit ---
        c.property_fit_score = compute_property_fit(
            m.band_gap, criteria.band_gap_target, criteria.band_gap_tolerance)

        # --- Reason codes ---
        if c.novelty_score > 0.3:
            c.reason_codes.append("high_novelty")
        if c.exotic_score > 0.2:
            c.reason_codes.append("high_exoticity")
        if m.formation_energy is not None and m.formation_energy < -1.0:
            c.reason_codes.append("low_formation_energy")
        if c.stability_score < 0.2:
            c.reason_codes.append("low_reliability")
        if not m.has_valid_structure:
            c.reason_codes.append("insufficient_structure_signal")

        # --- T/P screening ---
        if conditions is not None and not conditions.is_ambient:
            tp_result = screen_tp_proxy(m, conditions)
            c.screening_reliability = tp_result["reliability"]
            if tp_result.get("risk_level") == "high":
                c.reason_codes.append("tp_risk_flag")
        elif conditions is not None:
            c.screening_reliability = "baseline_ambient"
        else:
            c.screening_reliability = "not_available"

        # --- Weighted score ---
        c.shortlist_score = (
            criteria.w_novelty * c.novelty_score
            + criteria.w_exotic * c.exotic_score
            + criteria.w_stability * c.stability_score
            + criteria.w_property_fit * c.property_fit_score
        )

        # Exotic soft filter
        if c.exotic_score < criteria.exotic_min and criteria.exotic_min > 0:
            c.reason_codes.append("below_exotic_minimum")

        # --- Decision ---
        c.decision = assign_decision(c.shortlist_score, c.reason_codes)

        return c

    def save_run(self, result: dict, output_dir: str = "artifacts/shortlist") -> str:
        """Save shortlist run to artifacts."""
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(output_dir, f"shortlist_run_{ts}.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        log.info("Saved shortlist run: %s", path)
        return path
