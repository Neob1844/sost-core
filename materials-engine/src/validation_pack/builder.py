"""Validation Pack builder — constructs packs from frontier results.

Phase IV.D: Bridge between frontier selection and validation queue.
Reuses existing dossier, calibration, analytics, and comparison layers.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ..storage.db import MaterialsDB
from ..frontier.engine import FrontierEngine
from ..frontier.spec import FrontierProfile, ALL_FRONTIER_PRESETS, SRC_CORPUS, SRC_GENERATED
from ..intelligence.applications import classify_applications
from ..intelligence.evidence import KNOWN, PREDICTED, PROXY, UNAVAILABLE
from ..calibration.confidence import load_calibration, get_calibrated_confidence
from ..validation.queue import ValidationQueue
from ..validation.spec import ValidationCandidate, RC_DUPLICATE
from .spec import (
    ValidationPack, NEXT_KEEP_REF, NEXT_WATCH, NEXT_PROXY_REVIEW,
    NEXT_DFT_QUEUE, NEXT_NEEDS_STRUCTURE, NEXT_DISCARD,
    RISK_KNOWN, RISK_WEAK_BG, RISK_WEAK_STRUCT, RISK_HIGH_PROXY,
    RISK_LIMITED_EV, RISK_GEN_UNVAL, RISK_NOT_CORPUS,
)

log = logging.getLogger(__name__)

PACK_DIR = "artifacts/validation_pack"


class ValidationPackBuilder:
    """Builds validation packs from frontier results."""

    def __init__(self, db: MaterialsDB, output_dir: str = PACK_DIR):
        self.db = db
        self.output_dir = output_dir

    def build_from_frontier(self, frontier_result: dict,
                            top_k: int = 20) -> List[ValidationPack]:
        """Build packs from a frontier run result."""
        shortlist = frontier_result.get("shortlist", [])[:top_k]
        profile_name = frontier_result.get("profile", {}).get("name", "unknown")
        packs = []
        for candidate in shortlist:
            pack = self._build_one(candidate, profile_name)
            packs.append(pack)
        return packs

    def build_from_frontier_id(self, run_id: str, top_k: int = 20) -> List[ValidationPack]:
        """Build packs from a saved frontier run."""
        engine = FrontierEngine(self.db)
        result = engine.get_run(run_id)
        if not result:
            return []
        return self.build_from_frontier(result, top_k)

    def build_one(self, formula: str, elements: List[str],
                  spacegroup: Optional[int] = None,
                  source_type: str = SRC_CORPUS,
                  frontier_score: float = 0.0,
                  scores: Optional[dict] = None,
                  properties: Optional[dict] = None) -> ValidationPack:
        """Build a single pack from raw parameters."""
        now = datetime.now(timezone.utc).isoformat()
        pack = ValidationPack(
            pack_id=hashlib.sha256(f"pack|{formula}|{now}".encode()).hexdigest()[:12],
            formula=formula,
            source_type=source_type,
            spacegroup=spacegroup,
            frontier_profile="manual",
            frontier_score=frontier_score,
            created_at=now,
        )
        if scores:
            pack.novelty_score = scores.get("novelty", 0.0)
            pack.exotic_score = scores.get("exotic", 0.0)
            pack.score_breakdown = scores
        if properties:
            pack.properties = properties

        self._enrich(pack, elements)
        return pack

    def push_to_queue(self, packs: List[ValidationPack],
                      queue: Optional[ValidationQueue] = None) -> dict:
        """Push packs to the validation queue with dedup."""
        if queue is None:
            queue = ValidationQueue()
            queue.load()

        added = 0
        duped = 0
        for pack in packs:
            vc = ValidationCandidate(
                source_type=pack.source_type,
                formula=pack.formula,
                spacegroup=pack.spacegroup,
                novelty_score=pack.novelty_score,
                exotic_score=pack.exotic_score,
                evaluation_score=pack.frontier_score,
                benchmark_confidence_band=pack.calibration_band,
                expected_error_band=pack.expected_error,
            )
            result = queue.add(vc)
            if result.get("status") == "queued":
                added += 1
            else:
                duped += 1

        queue.save()
        return {"added": added, "duplicates": duped, "total_in_queue": queue.size}

    def save_batch(self, packs: List[ValidationPack], label: str = "") -> str:
        """Save a batch of packs to artifacts."""
        os.makedirs(self.output_dir, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"validation_pack_batch_{label}_{now}" if label else f"validation_pack_batch_{now}"

        # JSON
        data = {
            "batch_size": len(packs),
            "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "packs": [p.to_dict() for p in packs],
        }
        json_path = os.path.join(self.output_dir, f"{name}.json")
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        # Markdown
        md = f"# Validation Pack Batch: {label or 'unnamed'}\n\n"
        md += f"**Count:** {len(packs)}\n\n"
        for pack in packs:
            md += pack.to_markdown() + "\n---\n\n"
        md_path = os.path.join(self.output_dir, f"{name}.md")
        with open(md_path, "w") as f:
            f.write(md)

        return json_path

    def export_csv(self, packs: List[ValidationPack]) -> str:
        """Export summary CSV."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, "validation_pack_export.csv")
        if not packs:
            return path
        rows = [p.to_summary_row() for p in packs]
        headers = list(rows[0].keys())
        with open(path, "w") as f:
            f.write(",".join(headers) + "\n")
            for row in rows:
                f.write(",".join(str(row.get(h, "")) for h in headers) + "\n")
        return path

    # ================================================================
    # Internal
    # ================================================================

    def _build_one(self, candidate: dict, profile_name: str) -> ValidationPack:
        """Build a pack from a frontier candidate dict."""
        now = datetime.now(timezone.utc).isoformat()
        props = candidate.get("properties", {})
        scores = candidate.get("scores", {})
        formula = candidate.get("formula", "")

        pack = ValidationPack(
            pack_id=hashlib.sha256(f"pack|{formula}|{now}".encode()).hexdigest()[:12],
            formula=formula,
            source_type=candidate.get("source_type", SRC_CORPUS),
            material_id=candidate.get("canonical_id"),
            spacegroup=candidate.get("spacegroup"),
            frontier_profile=profile_name,
            frontier_score=scores.get("frontier", 0.0),
            score_breakdown=scores,
            properties={
                "formation_energy": props.get("formation_energy", {"value": None, "evidence": UNAVAILABLE}),
                "band_gap": props.get("band_gap", {"value": None, "evidence": UNAVAILABLE}),
            },
            novelty_score=scores.get("novelty", 0.0),
            exotic_score=scores.get("exotic", 0.0),
            has_structure=props.get("has_structure", False),
            density=props.get("density"),
            reason_codes=candidate.get("reason_codes", []),
            created_at=now,
        )

        elements = candidate.get("elements", [])
        self._enrich(pack, elements)
        return pack

    def _enrich(self, pack: ValidationPack, elements: List[str]):
        """Add calibration, applications, risk flags, next step, summary."""
        # Calibration
        fe_cal = load_calibration("formation_energy")
        if fe_cal:
            conf = get_calibrated_confidence(fe_cal, n_elements=len(elements))
            pack.calibration_band = conf.get("confidence_band", "unknown")
            pack.expected_error = conf.get("expected_error")

        # Applications
        fe_val = pack.properties.get("formation_energy", {}).get("value")
        bg_val = pack.properties.get("band_gap", {}).get("value")
        fe_ev = pack.properties.get("formation_energy", {}).get("evidence", UNAVAILABLE)
        bg_ev = pack.properties.get("band_gap", {}).get("evidence", UNAVAILABLE)
        pack.likely_applications = classify_applications(
            band_gap=bg_val, band_gap_evidence=bg_ev,
            formation_energy=fe_val, fe_evidence=fe_ev,
            elements=elements)

        # Risk flags
        pack.risk_flags = self._compute_risks(pack)

        # Next step
        pack.recommended_next_step = self._compute_next_step(pack)

        # Human summary
        pack.human_summary = self._generate_summary(pack)

    def _compute_risks(self, pack: ValidationPack) -> List[str]:
        flags = []
        if pack.source_type == SRC_CORPUS:
            flags.append(RISK_KNOWN)
        if pack.source_type == SRC_GENERATED:
            flags.append(RISK_GEN_UNVAL)
            flags.append(RISK_NOT_CORPUS)
        bg_ev = pack.properties.get("band_gap", {}).get("evidence", UNAVAILABLE)
        if bg_ev in (PREDICTED, PROXY, UNAVAILABLE):
            flags.append(RISK_WEAK_BG)
        if not pack.has_structure:
            flags.append(RISK_WEAK_STRUCT)
        fe_ev = pack.properties.get("formation_energy", {}).get("evidence", UNAVAILABLE)
        if fe_ev == PROXY or bg_ev == PROXY:
            flags.append(RISK_HIGH_PROXY)
        known_count = sum(1 for v in pack.properties.values()
                         if isinstance(v, dict) and v.get("evidence") == KNOWN)
        if known_count < 1:
            flags.append(RISK_LIMITED_EV)
        return flags

    def _compute_next_step(self, pack: ValidationPack) -> str:
        if RISK_KNOWN in pack.risk_flags and pack.novelty_score < 0.1:
            return NEXT_KEEP_REF
        if pack.frontier_score < 0.15:
            return NEXT_DISCARD
        if not pack.has_structure:
            return NEXT_NEEDS_STRUCTURE
        if RISK_GEN_UNVAL in pack.risk_flags:
            return NEXT_PROXY_REVIEW
        if pack.frontier_score >= 0.4 and pack.novelty_score > 0.2:
            return NEXT_DFT_QUEUE
        if pack.frontier_score >= 0.25:
            return NEXT_PROXY_REVIEW
        return NEXT_WATCH

    def _generate_summary(self, pack: ValidationPack) -> str:
        fe = pack.properties.get("formation_energy", {}).get("value")
        bg = pack.properties.get("band_gap", {}).get("value")
        parts = [f"{pack.formula}"]
        if fe is not None:
            parts.append(f"FE={fe:.2f}")
        if bg is not None:
            parts.append(f"BG={bg:.2f}")
        parts.append(f"frontier={pack.frontier_score:.3f}")
        if pack.likely_applications:
            top_app = pack.likely_applications[0]["label"]
            if top_app != "unknown_application":
                parts.append(f"app={top_app}")
        parts.append(f"next={pack.recommended_next_step}")
        return " | ".join(parts)
