"""Campaign engine — runs search campaigns and persists results.

Phase III.C: Campaigns are reproducible search sessions that combine
shortlist building with formal spec, persistence, and reporting.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, List

from ..storage.db import MaterialsDB
from ..shortlist.engine import ShortlistEngine
from ..thermo.conditions import ThermoPressureConditions, AMBIENT_TEMPERATURE_K, AMBIENT_PRESSURE_GPA
from .spec import CampaignSpec

log = logging.getLogger(__name__)

CAMPAIGNS_DIR = "artifacts/campaigns"


class CampaignEngine:
    """Runs and persists search campaigns."""

    def __init__(self, db: MaterialsDB, output_dir: str = CAMPAIGNS_DIR):
        self.db = db
        self.output_dir = output_dir
        self._shortlist_engine = ShortlistEngine(db)

    def run(self, spec: CampaignSpec) -> dict:
        """Execute a campaign and return results."""
        spec.validate()
        campaign_id = spec.campaign_id()

        # Build conditions if specified
        conditions = None
        if spec.temperature_K is not None or spec.pressure_GPa is not None:
            conditions = ThermoPressureConditions(
                temperature_K=spec.temperature_K or AMBIENT_TEMPERATURE_K,
                pressure_GPa=spec.pressure_GPa or AMBIENT_PRESSURE_GPA)
            conditions.validate()

        criteria = spec.get_criteria()

        # Run shortlist
        shortlist_result = self._shortlist_engine.build(
            criteria=criteria, conditions=conditions,
            pool_limit=spec.pool_limit)

        result = {
            "campaign_id": campaign_id,
            "spec": spec.to_dict(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "result_summary": {
                "pool_size": shortlist_result["pool_size"],
                "evaluated": shortlist_result["evaluated"],
                "decisions": shortlist_result["decisions"],
                "shortlist_size": shortlist_result["shortlist_size"],
            },
            "shortlist": shortlist_result["shortlist"],
            "criteria_used": shortlist_result["criteria"],
            "conditions_used": shortlist_result["conditions"],
            "disclaimer": shortlist_result["disclaimer"],
        }

        log.info("Campaign '%s' completed: %d candidates from %d pool",
                 spec.name, shortlist_result["shortlist_size"],
                 shortlist_result["pool_size"])

        return result

    def run_and_save(self, spec: CampaignSpec) -> tuple:
        """Run campaign and save to disk. Returns (result, path)."""
        result = self.run(spec)
        path = self.save_run(result)
        return result, path

    def save_run(self, result: dict) -> str:
        """Save campaign result to artifacts."""
        os.makedirs(self.output_dir, exist_ok=True)
        cid = result["campaign_id"]
        path = os.path.join(self.output_dir, f"campaign_{cid}.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        log.info("Saved campaign: %s", path)
        return path

    def get_run(self, campaign_id: str) -> Optional[dict]:
        """Load a saved campaign run."""
        path = os.path.join(self.output_dir, f"campaign_{campaign_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list_runs(self) -> List[dict]:
        """List all saved campaign runs (summaries only)."""
        if not os.path.exists(self.output_dir):
            return []
        runs = []
        for fname in sorted(os.listdir(self.output_dir)):
            if fname.startswith("campaign_") and fname.endswith(".json"):
                path = os.path.join(self.output_dir, fname)
                try:
                    with open(path) as f:
                        d = json.load(f)
                    runs.append({
                        "campaign_id": d.get("campaign_id"),
                        "name": d.get("spec", {}).get("name"),
                        "type": d.get("spec", {}).get("campaign_type"),
                        "status": d.get("status"),
                        "shortlist_size": d.get("result_summary", {}).get("shortlist_size"),
                        "pool_size": d.get("result_summary", {}).get("pool_size"),
                        "created_at": d.get("created_at"),
                    })
                except Exception:
                    continue
        return runs
