"""Candidate generation engine — novelty-first pipeline.

Phase III.D: Generates plausible material candidates from corpus parents
using cheap heuristic strategies, then filters by novelty before viability.

Pipeline:
  PARENTS → GENERATE → BASIC SANITY → NOVELTY CHECK → VIABILITY FILTER → OUTPUT

NOT physics simulation. Candidates are hypotheses for further validation.
"""

import json
import hashlib
import logging
import os
import numpy as np
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple

from ..schema import Material
from ..storage.db import MaterialsDB
from ..features.fingerprint_store import FingerprintStore
from ..retrieval.index import RetrievalIndex
from ..novelty.fingerprint import combined_fingerprint, compositional_fingerprint, COMBINED_DIM
from ..novelty.scoring import EXACT_MATCH_THRESHOLD, NEAR_KNOWN_THRESHOLD
from .spec import GenerationSpec
from .rules import (
    get_substitutes, perturb_formula_counts, counts_to_formula,
    formula_to_counts, plausibility_score, SUBSTITUTION_FAMILIES,
    COMMON_STOICHIOMETRIES,
)

log = logging.getLogger(__name__)

GENERATION_DIR = "artifacts/generation"

# Decision states for generated candidates
DECISIONS = [
    "rejected_invalid",
    "rejected_known",
    "rejected_near_known",
    "watchlist_novel",
    "accepted_novel",
    "accepted_exotic",
]


@dataclass
class GeneratedCandidate:
    """A generated material candidate."""
    candidate_id: str = ""
    parent_ids: List[str] = field(default_factory=list)
    generation_strategy: str = ""
    formula: str = ""
    elements: List[str] = field(default_factory=list)
    n_elements: int = 0
    spacegroup: Optional[int] = None

    # Scores
    novelty_score: float = 0.0
    exotic_score: float = 0.0
    plausibility_score: float = 0.0
    stability_prior: float = 0.0  # from parent's formation energy
    generation_score: float = 0.0

    # Decision
    decision: str = "rejected_invalid"
    reason_codes: List[str] = field(default_factory=list)

    # Trace
    seed: int = 0
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "parent_ids": self.parent_ids,
            "generation_strategy": self.generation_strategy,
            "formula": self.formula,
            "elements": self.elements,
            "n_elements": self.n_elements,
            "spacegroup": self.spacegroup,
            "scores": {
                "novelty": round(self.novelty_score, 4),
                "exotic": round(self.exotic_score, 4),
                "plausibility": round(self.plausibility_score, 4),
                "stability_prior": round(self.stability_prior, 4),
                "generation": round(self.generation_score, 4),
            },
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "seed": self.seed,
            "created_at": self.created_at,
        }


class GenerationEngine:
    """Controlled candidate generation with novelty-first filtering."""

    def __init__(self, db: MaterialsDB,
                 store: Optional[FingerprintStore] = None,
                 output_dir: str = GENERATION_DIR):
        self.db = db
        self.output_dir = output_dir
        self._store = store
        self._index: Optional[RetrievalIndex] = None

    def _ensure_index(self):
        """Load or build fingerprint index for novelty checking."""
        if self._index is not None and self._index.is_ready:
            return
        if self._store is None:
            self._store = FingerprintStore()
        if not self._store.is_loaded:
            if not self._store.load():
                self._store.build(self.db)
        self._index = RetrievalIndex(self._store)
        self._index.build()

    def run(self, spec: GenerationSpec) -> dict:
        """Execute a generation run.

        Returns dict with run_id, spec, summary, candidates, disclaimers.
        """
        spec.validate()
        self._ensure_index()
        rng = np.random.RandomState(spec.random_seed)
        run_id = spec.run_id()
        now = datetime.now(timezone.utc).isoformat()

        # 1. Select parents from corpus
        parents = self._select_parents(spec, rng)
        log.info("Generation run %s: %d parents selected", run_id, len(parents))

        # 2. Generate raw candidates
        raw_candidates = self._generate(parents, spec, rng)
        log.info("Generated %d raw candidates", len(raw_candidates))

        # 3. Basic sanity filter
        sane = self._sanity_filter(raw_candidates, spec)
        log.info("After sanity filter: %d / %d", len(sane), len(raw_candidates))

        # 4. Deduplicate generated candidates
        deduped = self._dedup(sane)
        log.info("After dedup: %d / %d", len(deduped), len(sane))

        # 5. Novelty check against corpus
        scored = self._novelty_check(deduped, now)

        # 6. Viability filter + final scoring
        final = self._viability_filter(scored, spec)

        # 7. Sort by generation_score
        final.sort(key=lambda c: -c.generation_score)
        for i, c in enumerate(final):
            if i < spec.max_candidates:
                pass  # keep
            else:
                c.decision = "rejected_invalid"
                c.reason_codes.append("over_max_candidates")
        final = final[:spec.max_candidates]

        # Summarize
        decisions = Counter(c.decision for c in final)
        result = {
            "run_id": run_id,
            "spec": spec.to_dict(),
            "created_at": now,
            "summary": {
                "parents_used": len(parents),
                "raw_generated": len(raw_candidates),
                "after_sanity": len(sane),
                "after_dedup": len(deduped),
                "final_count": len(final),
                "decisions": dict(decisions),
            },
            "candidates": [c.to_dict() for c in final
                           if c.decision not in ("rejected_invalid", "rejected_known")],
            "top_candidates": [c.to_dict() for c in final[:20]
                               if c.decision in ("accepted_novel", "accepted_exotic",
                                                  "watchlist_novel")],
            "disclaimer": (
                "Generated candidates are heuristic hypotheses based on element "
                "substitution and stoichiometry perturbation from corpus materials. "
                "NOT validated by DFT, phonon calculation, or experiment. "
                "Novelty is relative to the ingested corpus only."
            ),
        }

        return result

    def run_and_save(self, spec: GenerationSpec) -> Tuple[dict, str]:
        result = self.run(spec)
        path = self._save(result)
        return result, path

    def check_candidate(self, formula: str, elements: List[str],
                        spacegroup: Optional[int] = None) -> dict:
        """Check a manually-provided candidate against corpus."""
        self._ensure_index()
        now = datetime.now(timezone.utc).isoformat()

        c = GeneratedCandidate(
            formula=formula, elements=sorted(elements),
            n_elements=len(elements), spacegroup=spacegroup,
            generation_strategy="manual_check", created_at=now)
        c.candidate_id = hashlib.sha256(
            f"{formula}|{spacegroup or 0}".encode()).hexdigest()[:12]

        # Novelty
        fp = combined_fingerprint(elements, spacegroup=spacegroup)
        self._score_novelty(c, fp)

        # Plausibility
        c.plausibility_score = plausibility_score(
            elements, len(elements), spacegroup)

        # Generation score
        c.generation_score = (0.4 * c.novelty_score
                              + 0.2 * c.exotic_score
                              + 0.3 * c.plausibility_score
                              + 0.1 * 0.5)

        return {
            "candidate": c.to_dict(),
            "disclaimer": "Novelty relative to ingested corpus only.",
        }

    def get_run(self, run_id: str) -> Optional[dict]:
        path = os.path.join(self.output_dir, f"generation_run_{run_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list_runs(self) -> List[dict]:
        if not os.path.exists(self.output_dir):
            return []
        runs = []
        for fname in sorted(os.listdir(self.output_dir)):
            if fname.startswith("generation_run_") and fname.endswith(".json"):
                path = os.path.join(self.output_dir, fname)
                try:
                    with open(path) as f:
                        d = json.load(f)
                    runs.append({
                        "run_id": d.get("run_id"),
                        "strategy": d.get("spec", {}).get("strategy"),
                        "final_count": d.get("summary", {}).get("final_count"),
                        "created_at": d.get("created_at"),
                    })
                except Exception:
                    continue
        return runs

    # ================================================================
    # Internal methods
    # ================================================================

    def _select_parents(self, spec: GenerationSpec,
                        rng: np.random.RandomState) -> List[Material]:
        """Select diverse parent materials from corpus."""
        pool = self.db.list_materials(limit=spec.pool_limit)
        if not pool:
            return []
        # Shuffle and sample
        indices = rng.permutation(len(pool))[:spec.max_parents]
        parents = [pool[i] for i in indices]
        # Apply element filters
        if spec.excluded_elements:
            excl = set(spec.excluded_elements)
            parents = [p for p in parents if not (set(p.elements) & excl)]
        if spec.allowed_elements:
            allowed = set(spec.allowed_elements)
            parents = [p for p in parents if set(p.elements).issubset(allowed)]
        return parents[:spec.max_parents]

    def _generate(self, parents: List[Material], spec: GenerationSpec,
                  rng: np.random.RandomState) -> List[GeneratedCandidate]:
        """Generate raw candidates from parents."""
        candidates = []
        strats = []
        if spec.strategy == "mixed":
            strats = ["element_substitution", "stoichiometry_perturbation",
                      "prototype_remix"]
        else:
            strats = [spec.strategy]

        budget_per_strat = max(1, spec.max_candidates // len(strats))

        for strat in strats:
            if strat == "element_substitution":
                candidates.extend(
                    self._gen_substitution(parents, budget_per_strat, spec, rng))
            elif strat == "stoichiometry_perturbation":
                candidates.extend(
                    self._gen_stoichiometry(parents, budget_per_strat, spec, rng))
            elif strat == "prototype_remix":
                candidates.extend(
                    self._gen_prototype(parents, budget_per_strat, spec, rng))

        return candidates

    def _gen_substitution(self, parents: List[Material], budget: int,
                          spec: GenerationSpec,
                          rng: np.random.RandomState) -> List[GeneratedCandidate]:
        """Element substitution: replace one element with a compatible one."""
        results = []
        for parent in parents:
            if len(results) >= budget:
                break
            for elem in parent.elements:
                subs = get_substitutes(elem, max_subs=3)
                if not subs:
                    continue
                sub = subs[rng.randint(len(subs))]
                new_elems = sorted(set(
                    (sub if e == elem else e) for e in parent.elements))
                if len(new_elems) > spec.max_n_elements:
                    continue
                counts = formula_to_counts(parent.formula)
                if elem in counts:
                    new_counts = {(sub if k == elem else k): v
                                  for k, v in counts.items()}
                    new_formula = counts_to_formula(new_counts)
                else:
                    new_formula = counts_to_formula(
                        {e: 1 for e in new_elems})

                c = GeneratedCandidate(
                    parent_ids=[parent.canonical_id],
                    generation_strategy="element_substitution",
                    formula=new_formula, elements=new_elems,
                    n_elements=len(new_elems),
                    spacegroup=parent.spacegroup,
                    stability_prior=self._stability_prior(parent),
                    seed=spec.random_seed,
                    created_at="",
                )
                c.candidate_id = hashlib.sha256(
                    f"sub|{new_formula}|{parent.spacegroup or 0}|{spec.random_seed}".encode()
                ).hexdigest()[:12]
                results.append(c)
                if len(results) >= budget:
                    break
        return results

    def _gen_stoichiometry(self, parents: List[Material], budget: int,
                           spec: GenerationSpec,
                           rng: np.random.RandomState) -> List[GeneratedCandidate]:
        """Stoichiometry perturbation: change element counts by ±1."""
        results = []
        for parent in parents:
            if len(results) >= budget:
                break
            counts = formula_to_counts(parent.formula)
            if not counts:
                continue
            perturbations = perturb_formula_counts(counts, max_delta=1)
            if not perturbations:
                continue
            idx = rng.randint(len(perturbations))
            new_counts = perturbations[idx]
            new_formula = counts_to_formula(new_counts)
            new_elems = sorted(new_counts.keys())

            c = GeneratedCandidate(
                parent_ids=[parent.canonical_id],
                generation_strategy="stoichiometry_perturbation",
                formula=new_formula, elements=new_elems,
                n_elements=len(new_elems),
                spacegroup=parent.spacegroup,
                stability_prior=self._stability_prior(parent),
                seed=spec.random_seed,
                created_at="",
            )
            c.candidate_id = hashlib.sha256(
                f"stoich|{new_formula}|{parent.spacegroup or 0}|{spec.random_seed}".encode()
            ).hexdigest()[:12]
            results.append(c)
        return results[:budget]

    def _gen_prototype(self, parents: List[Material], budget: int,
                       spec: GenerationSpec,
                       rng: np.random.RandomState) -> List[GeneratedCandidate]:
        """Prototype remix: keep spacegroup, vary composition."""
        results = []
        # Group parents by spacegroup
        by_sg: Dict[int, List[Material]] = {}
        for p in parents:
            if p.spacegroup:
                by_sg.setdefault(p.spacegroup, []).append(p)

        for sg, group in by_sg.items():
            if len(results) >= budget:
                break
            if len(group) < 2:
                continue
            # Pick two parents and mix elements
            idxs = rng.choice(len(group), size=min(2, len(group)), replace=False)
            p1, p2 = group[idxs[0]], group[idxs[1] if len(idxs) > 1 else 0]
            mixed_elems = sorted(set(p1.elements) | set(p2.elements))
            if len(mixed_elems) > spec.max_n_elements:
                mixed_elems = sorted(rng.choice(
                    mixed_elems, size=spec.max_n_elements, replace=False))
            new_formula = counts_to_formula({e: 1 for e in mixed_elems})

            c = GeneratedCandidate(
                parent_ids=[p1.canonical_id, p2.canonical_id],
                generation_strategy="prototype_remix",
                formula=new_formula, elements=mixed_elems,
                n_elements=len(mixed_elems),
                spacegroup=sg,
                stability_prior=(self._stability_prior(p1) + self._stability_prior(p2)) / 2,
                seed=spec.random_seed,
                created_at="",
            )
            c.candidate_id = hashlib.sha256(
                f"proto|{new_formula}|{sg}|{spec.random_seed}".encode()
            ).hexdigest()[:12]
            results.append(c)
        return results[:budget]

    def _stability_prior(self, parent: Material) -> float:
        """Stability prior from parent's formation energy."""
        if parent.formation_energy is None:
            return 0.3
        fe = parent.formation_energy
        return max(0.0, min(1.0, (2.0 - fe) / 5.0))

    def _sanity_filter(self, candidates: List[GeneratedCandidate],
                       spec: GenerationSpec) -> List[GeneratedCandidate]:
        """Basic sanity: valid elements, reasonable formula."""
        from ..features.crystal_graph import ELEM_TO_IDX
        valid = []
        for c in candidates:
            if not c.elements or not c.formula:
                c.decision = "rejected_invalid"
                c.reason_codes.append("empty_formula_or_elements")
                continue
            if c.n_elements > spec.max_n_elements:
                c.decision = "rejected_invalid"
                c.reason_codes.append("too_many_elements")
                continue
            # Check all elements are in our element list
            if not all(e in ELEM_TO_IDX for e in c.elements):
                c.decision = "rejected_invalid"
                c.reason_codes.append("unknown_element")
                continue
            valid.append(c)
        return valid

    def _dedup(self, candidates: List[GeneratedCandidate]) -> List[GeneratedCandidate]:
        """Remove duplicate formulas within generated batch."""
        seen = set()
        unique = []
        for c in candidates:
            key = f"{c.formula}|{c.spacegroup or 0}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)
        return unique

    def _novelty_check(self, candidates: List[GeneratedCandidate],
                       now: str) -> List[GeneratedCandidate]:
        """Check each candidate against corpus fingerprints."""
        for c in candidates:
            c.created_at = now
            fp = combined_fingerprint(c.elements, spacegroup=c.spacegroup)
            self._score_novelty(c, fp)
        return candidates

    def _score_novelty(self, c: GeneratedCandidate, fp: np.ndarray):
        """Score novelty and exotic from fingerprint search."""
        if fp.sum() == 0:
            c.novelty_score = 0.5
            c.decision = "watchlist_novel"
            c.reason_codes.append("insufficient_fingerprint")
            return

        neighbors = self._index.search(fp, top_k=5)
        if not neighbors:
            c.novelty_score = 1.0
            c.exotic_score = 0.8
            c.decision = "accepted_exotic"
            c.reason_codes.append("no_neighbors_found")
            return

        max_sim = neighbors[0][2]
        c.novelty_score = max(0.0, min(1.0, 1.0 - max_sim))

        # Exotic approximation from neighbor sparsity
        mean_sim = np.mean([s for _, _, s in neighbors])
        c.exotic_score = max(0.0, min(1.0, 1.0 - mean_sim))

        # Classify
        if max_sim >= EXACT_MATCH_THRESHOLD:
            c.decision = "rejected_known"
            c.reason_codes.append("corpus_exact_match")
        elif max_sim >= NEAR_KNOWN_THRESHOLD:
            c.decision = "rejected_near_known"
            c.reason_codes.append("corpus_near_duplicate")
        elif c.novelty_score > 0.3 and c.exotic_score > 0.2:
            c.decision = "accepted_exotic"
            c.reason_codes.append("novel_and_exotic")
        elif c.novelty_score > 0.1:
            c.decision = "accepted_novel"
            c.reason_codes.append("moderately_novel")
        else:
            c.decision = "watchlist_novel"
            c.reason_codes.append("low_novelty")

    def _viability_filter(self, candidates: List[GeneratedCandidate],
                          spec: GenerationSpec) -> List[GeneratedCandidate]:
        """Apply plausibility scoring and optional property filters."""
        for c in candidates:
            if c.decision.startswith("rejected"):
                continue

            c.plausibility_score = plausibility_score(
                c.elements, c.n_elements, c.spacegroup,
                parent_formula=c.parent_ids[0] if c.parent_ids else None)

            # Generation composite score
            c.generation_score = (
                0.35 * c.novelty_score
                + 0.20 * c.exotic_score
                + 0.25 * c.plausibility_score
                + 0.20 * c.stability_prior
            )

        return candidates

    def _save(self, result: dict) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        rid = result["run_id"]
        path = os.path.join(self.output_dir, f"generation_run_{rid}.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        log.info("Saved generation run: %s", path)
        return path
