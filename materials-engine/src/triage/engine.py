"""Triage engine — pre-DFT decision gate.

Phase IV.E: Takes ValidationPacks and produces triage decisions based on
signal/risk ratio. Cheap-first: no expensive compute, just intelligent
filtering using all existing evidence.
"""

import json
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from ..validation_pack.spec import ValidationPack, RISK_KNOWN, RISK_GEN_UNVAL, RISK_WEAK_STRUCT
from ..validation_pack.builder import ValidationPackBuilder
from ..frontier.engine import FrontierEngine
from ..frontier.spec import ALL_FRONTIER_PRESETS
from ..storage.db import MaterialsDB
from ..intelligence.evidence import KNOWN, PREDICTED
from .spec import (
    TriageProfile, TriageResult, ALL_TRIAGE_PRESETS,
    DECISION_APPROVED, DECISION_MANUAL, DECISION_WATCHLIST, DECISION_REJECT,
    ACTION_PROMOTE, ACTION_REVIEW, ACTION_KEEP, ACTION_HOLD, ACTION_DEFER, ACTION_DROP,
)

log = logging.getLogger(__name__)

TRIAGE_DIR = "artifacts/triage"

# Calibration band scores
CAL_SCORES = {"high": 1.0, "medium": 0.6, "low": 0.3, "unknown": 0.2}


class TriageEngine:
    """Pre-DFT triage gate for validation packs."""

    def __init__(self, db: MaterialsDB, output_dir: str = TRIAGE_DIR):
        self.db = db
        self.output_dir = output_dir

    def run(self, packs: List[ValidationPack],
            profile: Optional[TriageProfile] = None) -> dict:
        """Run triage on a batch of validation packs."""
        if profile is None:
            profile = ALL_TRIAGE_PRESETS["balanced_review_gate"]()
        profile.validate()

        now = datetime.now(timezone.utc).isoformat()
        run_id = hashlib.sha256(f"triage|{profile.name}|{now}".encode()).hexdigest()[:12]

        results: List[TriageResult] = []
        for pack in packs:
            tr = self._triage_one(pack, profile)
            results.append(tr)

        results.sort(key=lambda r: -r.triage_score)

        decisions = {}
        for r in results:
            decisions[r.decision] = decisions.get(r.decision, 0) + 1

        output = {
            "run_id": run_id,
            "profile": profile.to_dict(),
            "created_at": now,
            "summary": {
                "total": len(results),
                "decisions": decisions,
            },
            "results": [r.to_dict() for r in results[:profile.top_k]],
            "disclaimer": (
                "Triage decisions are based on ML predictions + heuristic evidence scoring. "
                "NOT DFT-validated. NOT experimentally confirmed. "
                "'approved_for_budgeted_validation' means the candidate passes the pre-DFT "
                "gate and is recommended for more serious (and expensive) validation when budget allows."
            ),
        }

        return output

    def run_from_frontier(self, frontier_run_id: str,
                          profile: Optional[TriageProfile] = None,
                          top_k: int = 20) -> dict:
        """Run triage from a frontier run via validation packs."""
        builder = ValidationPackBuilder(self.db)
        packs = builder.build_from_frontier_id(frontier_run_id, top_k)
        if not packs:
            return {"error": "Frontier run not found or empty"}
        return self.run(packs, profile)

    def run_and_save(self, packs: List[ValidationPack],
                     profile: Optional[TriageProfile] = None) -> tuple:
        result = self.run(packs, profile)
        path = self._save(result)
        return result, path

    def get_run(self, run_id: str) -> Optional[dict]:
        path = os.path.join(self.output_dir, f"triage_run_{run_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list_runs(self) -> List[dict]:
        if not os.path.exists(self.output_dir):
            return []
        runs = []
        for f in sorted(os.listdir(self.output_dir)):
            if f.startswith("triage_run_") and f.endswith(".json"):
                try:
                    with open(os.path.join(self.output_dir, f)) as fh:
                        d = json.load(fh)
                    runs.append({
                        "run_id": d.get("run_id"),
                        "profile": d.get("profile", {}).get("name"),
                        "total": d.get("summary", {}).get("total"),
                        "decisions": d.get("summary", {}).get("decisions"),
                        "created_at": d.get("created_at"),
                    })
                except Exception:
                    continue
        return runs

    # ================================================================
    # Internal
    # ================================================================

    def _triage_one(self, pack: ValidationPack, profile: TriageProfile) -> TriageResult:
        tr = TriageResult(
            pack_id=pack.pack_id,
            formula=pack.formula,
            source_type=pack.source_type,
            frontier_score=pack.frontier_score,
            risk_flags=list(pack.risk_flags),
            calibration_band=pack.calibration_band,
            novelty_score=pack.novelty_score,
            has_structure=pack.has_structure,
        )

        # Evidence strength: count known + predicted fields
        known_count = sum(1 for v in pack.properties.values()
                         if isinstance(v, dict) and v.get("evidence") in (KNOWN, PREDICTED))
        total_props = max(1, len(pack.properties))
        tr.evidence_strength = known_count / total_props

        # Calibration score
        cal_score = CAL_SCORES.get(pack.calibration_band, 0.2)

        # Risk penalty (0 = no risk, 1 = max risk)
        risk_penalty = min(1.0, len(pack.risk_flags) / 6.0)

        # Structure score
        struct_score = 1.0 if pack.has_structure else 0.0

        # Triage score
        tr.triage_score = (
            profile.w_frontier * pack.frontier_score
            + profile.w_calibration * cal_score
            + profile.w_evidence * tr.evidence_strength
            + profile.w_novelty * pack.novelty_score
            + profile.w_structure * struct_score
            + profile.w_risk_penalty * (1.0 - risk_penalty)
        )

        # Reason codes
        tr.reason_codes = self._compute_reasons(pack, tr, profile)

        # Hard gates → reject
        if len(pack.risk_flags) > profile.reject_max_risk_flags:
            tr.decision = DECISION_REJECT
            tr.next_action = ACTION_DROP
            tr.reason_codes.append("too_many_risk_flags")
            tr.human_summary = f"{pack.formula}: rejected — {len(pack.risk_flags)} risk flags exceed limit"
            return tr

        if profile.reject_if_known_low_novelty and RISK_KNOWN in pack.risk_flags and pack.novelty_score < 0.05:
            tr.decision = DECISION_REJECT
            tr.next_action = ACTION_HOLD
            tr.reason_codes.append("known_material_low_novelty")
            tr.human_summary = f"{pack.formula}: rejected — known material with negligible novelty"
            return tr

        if profile.require_structure and not pack.has_structure:
            tr.decision = DECISION_REJECT
            tr.next_action = ACTION_DEFER
            tr.reason_codes.append("no_structure_required")
            tr.human_summary = f"{pack.formula}: rejected — structure required but not available"
            return tr

        # Decision logic
        if (pack.frontier_score >= profile.approve_min_frontier
                and pack.novelty_score >= profile.approve_min_novelty
                and risk_penalty < 0.5
                and tr.evidence_strength >= 0.3):
            tr.decision = DECISION_APPROVED
            tr.next_action = ACTION_PROMOTE
        elif RISK_GEN_UNVAL in pack.risk_flags:
            tr.decision = DECISION_MANUAL
            tr.next_action = ACTION_REVIEW
        elif tr.triage_score >= 0.35:
            tr.decision = DECISION_MANUAL
            tr.next_action = ACTION_REVIEW
        elif tr.triage_score >= 0.20:
            tr.decision = DECISION_WATCHLIST
            tr.next_action = ACTION_KEEP
        else:
            tr.decision = DECISION_REJECT
            tr.next_action = ACTION_DROP

        tr.human_summary = (
            f"{pack.formula}: {tr.decision} | triage={tr.triage_score:.3f} | "
            f"frontier={pack.frontier_score:.3f} | action={tr.next_action}"
        )

        return tr

    def _compute_reasons(self, pack, tr, profile):
        codes = []
        if pack.frontier_score >= profile.approve_min_frontier:
            codes.append("strong_frontier_score")
        elif pack.frontier_score >= 0.3:
            codes.append("moderate_frontier_score")
        else:
            codes.append("weak_frontier_score")

        if pack.calibration_band == "high":
            codes.append("good_calibration_support")
        elif pack.calibration_band in ("low", "unknown"):
            codes.append("weak_calibration")

        if tr.evidence_strength >= 0.5:
            codes.append("good_evidence_coverage")
        elif tr.evidence_strength < 0.2:
            codes.append("limited_evidence")

        if pack.novelty_score > 0.3:
            codes.append("high_novelty")
        if pack.exotic_score > 0.2:
            codes.append("high_exotic")

        if pack.has_structure:
            codes.append("good_structure_coverage")
        else:
            codes.append("no_structure_data")

        if RISK_KNOWN in pack.risk_flags:
            codes.append("known_material_penalty")
        if RISK_GEN_UNVAL in pack.risk_flags:
            codes.append("generated_candidate_requires_review")

        return codes

    def _save(self, result: dict) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        rid = result["run_id"]
        json_path = os.path.join(self.output_dir, f"triage_run_{rid}.json")
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)

        # Markdown
        md_path = os.path.join(self.output_dir, f"triage_run_{rid}.md")
        md = f"# Triage Run: {result['profile']['name']}\n\n"
        md += f"Total: {result['summary']['total']} | "
        md += " | ".join(f"{k}: {v}" for k, v in result['summary']['decisions'].items()) + "\n\n"
        for r in result["results"]:
            tr = TriageResult(**{k: v for k, v in r.items() if k in TriageResult.__dataclass_fields__})
            md += tr.to_markdown() + "\n"
        with open(md_path, "w") as f:
            f.write(md)

        return json_path
