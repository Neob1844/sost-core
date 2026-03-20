"""Niche discovery campaign engine — themed search orchestrator.

Phase IV.F: Orchestrates frontier → validation pack → triage into a single
themed campaign with niche tags, summaries, and cross-campaign comparison.
"""

import json
import hashlib
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ..storage.db import MaterialsDB
from ..frontier.engine import FrontierEngine
from ..frontier.spec import ALL_FRONTIER_PRESETS, FrontierProfile
from ..validation_pack.builder import ValidationPackBuilder
from ..triage.engine import TriageEngine
from ..triage.spec import ALL_TRIAGE_PRESETS, DECISION_APPROVED, DECISION_MANUAL, DECISION_WATCHLIST
from .spec import NicheCampaignSpec, NicheCandidate, ALL_NICHE_PRESETS

log = logging.getLogger(__name__)

NICHE_DIR = "artifacts/niche"


class NicheCampaignEngine:
    """Runs themed niche discovery campaigns."""

    def __init__(self, db: MaterialsDB, output_dir: str = NICHE_DIR):
        self.db = db
        self.output_dir = output_dir

    def run(self, spec: NicheCampaignSpec,
            generated_candidates: Optional[List[dict]] = None) -> dict:
        """Execute a niche campaign end-to-end."""
        now = datetime.now(timezone.utc).isoformat()
        campaign_id = spec.campaign_id()

        # 1. Frontier
        frontier_profile = self._get_frontier_profile(spec)
        fe = FrontierEngine(self.db)
        frontier_result = fe.run(
            profile=frontier_profile,
            source=spec.source_mode,
            generated_candidates=generated_candidates)

        # 2. Validation packs
        builder = ValidationPackBuilder(self.db)
        packs = builder.build_from_frontier(frontier_result, top_k=spec.frontier_top_k)

        # 3. Triage
        triage_profile = self._get_triage_profile(spec)
        triage_profile.top_k = spec.triage_top_k
        te = TriageEngine(self.db)
        triage_result = te.run(packs, triage_profile)

        # 4. Build niche candidates with tags
        candidates = []
        for tr in triage_result.get("results", []):
            nc = NicheCandidate(
                formula=tr.get("formula", ""),
                source_type=tr.get("source_type", ""),
                frontier_score=tr.get("frontier_score", 0.0),
                triage_score=tr.get("triage_score", 0.0),
                triage_decision=tr.get("decision", ""),
                next_action=tr.get("next_action", ""),
                niche_tags=list(spec.niche_tags),
                reason_codes=tr.get("reason_codes", []),
                risk_flags=tr.get("risk_flags", []),
            )
            # Find matching pack for properties
            for p in packs:
                if p.formula == nc.formula:
                    nc.properties = {
                        "formation_energy": p.properties.get("formation_energy", {}),
                        "band_gap": p.properties.get("band_gap", {}),
                    }
                    break
            # Auto-tag
            if nc.triage_decision == DECISION_APPROVED:
                if "budget_candidate" not in nc.niche_tags:
                    nc.niche_tags.append("budget_candidate")
            if nc.source_type == "known_corpus_candidate":
                nc.niche_tags.append("known_reference")
            candidates.append(nc)

        # 5. Summary
        decisions = Counter(c.triage_decision for c in candidates)
        top_reasons = Counter()
        top_risks = Counter()
        for c in candidates:
            for r in c.reason_codes:
                top_reasons[r] += 1
            for r in c.risk_flags:
                top_risks[r] += 1

        result = {
            "campaign_id": campaign_id,
            "spec": spec.to_dict(),
            "created_at": now,
            "summary": {
                "total_evaluated": len(packs),
                "total_shortlist": len(candidates),
                "decisions": dict(decisions),
                "top_reasons": dict(top_reasons.most_common(8)),
                "top_risks": dict(top_risks.most_common(6)),
            },
            "candidates": [c.to_dict() for c in candidates],
            "top_candidates": [c.to_dict() for c in candidates
                               if c.triage_decision in (DECISION_APPROVED, DECISION_MANUAL)][:10],
            "disclaimer": (
                "Niche campaign results use ML predictions (CGCNN, ALIGNN-Lite) + heuristic scoring. "
                "NOT DFT-validated. NOT experimentally confirmed. "
                "Candidates are ranked hypotheses, not confirmed discoveries."
            ),
        }

        return result

    def run_and_save(self, spec: NicheCampaignSpec, **kwargs) -> tuple:
        result = self.run(spec, **kwargs)
        path = self._save(result)
        return result, path

    def run_batch(self, specs: List[NicheCampaignSpec]) -> List[dict]:
        """Run multiple campaigns and return all results."""
        return [self.run(spec) for spec in specs]

    def compare(self, results: List[dict]) -> dict:
        """Cross-campaign comparison."""
        rows = []
        for r in results:
            s = r.get("summary", {})
            decisions = s.get("decisions", {})
            rows.append({
                "campaign": r.get("spec", {}).get("name", "?"),
                "niche_tags": r.get("spec", {}).get("niche_tags", []),
                "evaluated": s.get("total_evaluated", 0),
                "shortlist": s.get("total_shortlist", 0),
                "approved": decisions.get(DECISION_APPROVED, 0),
                "manual_review": decisions.get(DECISION_MANUAL, 0),
                "watchlist": decisions.get(DECISION_WATCHLIST, 0),
                "rejected": decisions.get("reject_for_now", 0),
                "top_reason": list(s.get("top_reasons", {}).keys())[:2],
                "top_risk": list(s.get("top_risks", {}).keys())[:2],
            })
        # Best signal/risk ratio
        for row in rows:
            useful = row["approved"] + row["manual_review"]
            total = max(1, row["shortlist"])
            row["signal_ratio"] = round(useful / total, 3)
        return {"comparison": rows}

    def get_run(self, campaign_id: str) -> Optional[dict]:
        path = os.path.join(self.output_dir, f"niche_run_{campaign_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list_runs(self) -> List[dict]:
        if not os.path.exists(self.output_dir):
            return []
        runs = []
        for f in sorted(os.listdir(self.output_dir)):
            if f.startswith("niche_run_") and f.endswith(".json"):
                try:
                    with open(os.path.join(self.output_dir, f)) as fh:
                        d = json.load(fh)
                    runs.append({
                        "campaign_id": d.get("campaign_id"),
                        "name": d.get("spec", {}).get("name"),
                        "shortlist": d.get("summary", {}).get("total_shortlist"),
                        "created_at": d.get("created_at"),
                    })
                except Exception:
                    continue
        return runs

    # ================================================================
    # Internal
    # ================================================================

    def _get_frontier_profile(self, spec: NicheCampaignSpec) -> FrontierProfile:
        if spec.frontier_profile in ALL_FRONTIER_PRESETS:
            p = ALL_FRONTIER_PRESETS[spec.frontier_profile]()
        else:
            from ..frontier.spec import balanced_frontier
            p = balanced_frontier()
        if spec.band_gap_target is not None:
            p.band_gap_target = spec.band_gap_target
            p.band_gap_tolerance = spec.band_gap_tolerance
        p.fe_max = spec.fe_max
        p.top_k = spec.frontier_top_k
        p.pool_limit = spec.pool_limit
        p.novelty_min = spec.novelty_min
        p.exotic_min = spec.exotic_min
        return p

    def _get_triage_profile(self, spec: NicheCampaignSpec):
        if spec.triage_profile in ALL_TRIAGE_PRESETS:
            return ALL_TRIAGE_PRESETS[spec.triage_profile]()
        from ..triage.spec import balanced_review_gate
        return balanced_review_gate()

    def _save(self, result: dict) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        cid = result["campaign_id"]
        json_path = os.path.join(self.output_dir, f"niche_run_{cid}.json")
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)

        # Markdown
        md = f"# Niche Campaign: {result['spec']['name']}\n\n"
        md += f"**Objective:** {result['spec']['objective']}\n\n"
        s = result["summary"]
        md += f"Evaluated: {s['total_evaluated']} | Shortlist: {s['total_shortlist']}\n"
        md += f"Decisions: {s['decisions']}\n\n"
        md += "## Top Candidates\n\n"
        for c in result.get("top_candidates", [])[:10]:
            fe = c.get("properties", {}).get("formation_energy", {}).get("value", "?")
            bg = c.get("properties", {}).get("band_gap", {}).get("value", "?")
            md += f"- **{c['formula']}** — frontier={c['frontier_score']:.3f} triage={c['triage_score']:.3f} → `{c['triage_decision']}` tags={c['niche_tags']}\n"
        md_path = os.path.join(self.output_dir, f"niche_run_{cid}.md")
        with open(md_path, "w") as f:
            f.write(md)

        return json_path
