"""Ingestor for Materials Project API v2.

Requires a free API key from https://materialsproject.org/api
Fields actually obtained: material_id, formula_pretty, elements, nsites,
symmetry (number, symbol, crystal_system), band_gap, is_gap_direct,
formation_energy_per_atom, energy_above_hull, k_vrh, g_vrh, total_magnetization.
"""

import logging
import httpx
from typing import List, Optional
from .base import BaseIngestor

log = logging.getLogger(__name__)


class MaterialsProjectIngestor(BaseIngestor):

    def __init__(self, api_key: str, base_url: str = "https://api.materialsproject.org",
                 rate_limit: float = 5.0, batch_size: int = 1000, **kwargs):
        super().__init__(rate_limit=rate_limit, **kwargs)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=self.timeout, headers={
            "X-API-KEY": self.api_key, "Accept": "application/json"
        })
        self._fields = [
            "material_id", "formula_pretty", "elements", "nsites",
            "symmetry", "band_gap", "is_gap_direct",
            "formation_energy_per_atom", "energy_above_hull",
            "k_vrh", "g_vrh", "total_magnetization",
        ]

    @property
    def source_name(self) -> str:
        return "materials_project"

    def fetch_materials(self, limit: int = 100, offset: int = 0,
                        filters: Optional[dict] = None) -> List[dict]:
        def _do():
            url = f"{self.base_url}/materials/summary/"
            params = {"_fields": ",".join(self._fields),
                      "_limit": min(limit, self.batch_size), "_skip": offset}
            if filters:
                params.update(filters)
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            return resp.json().get("data", [])
        return self._retry_request(_do)

    def get_material_by_id(self, source_id: str) -> Optional[dict]:
        def _do():
            url = f"{self.base_url}/materials/summary/{source_id}"
            params = {"_fields": ",".join(self._fields)}
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            results = resp.json().get("data", [])
            return results[0] if results else None
        return self._retry_request(_do)

    def total_count(self) -> int:
        def _do():
            url = f"{self.base_url}/materials/summary/"
            resp = self._client.get(url, params={"_limit": 1, "_fields": "material_id"})
            resp.raise_for_status()
            return resp.json().get("meta", {}).get("total_doc", 0)
        try:
            return self._retry_request(_do)
        except Exception:
            return 0
