"""Ingestor for JARVIS-DFT (https://jarvis.nist.gov/).

No API key required. Uses the JARVIS REST API.
Fields obtained: jid, formula, spg_number, spg_symbol, optb88vdw_bandgap,
formation_energy_peratom, ehull, kv, gv, nat.

Note: JARVIS also distributes data via jarvis-tools Python package
(pip install jarvis-tools). This ingestor uses the REST API for simplicity.
The jarvis-tools package provides fuller access including atomic structures.
"""

import logging
import httpx
from typing import List, Optional
from .base import BaseIngestor

log = logging.getLogger(__name__)

# JARVIS REST endpoint for DFT data
JARVIS_API = "https://jarvis.nist.gov/jarvisdft/search"


class JARVISIngestor(BaseIngestor):

    def __init__(self, base_url: str = JARVIS_API,
                 rate_limit: float = 2.0, batch_size: int = 500, **kwargs):
        super().__init__(rate_limit=rate_limit, **kwargs)
        self.base_url = base_url
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=self.timeout)

    @property
    def source_name(self) -> str:
        return "jarvis"

    def fetch_materials(self, limit: int = 100, offset: int = 0,
                        filters: Optional[dict] = None) -> List[dict]:
        """Fetch from JARVIS REST API.

        Note: JARVIS REST API has limited query capabilities compared to
        jarvis-tools. For bulk ingestion, consider using jarvis-tools directly:
            from jarvis.db.figshare import data
            dft_3d = data("dft_3d")
        """
        def _do():
            params = {"limit": min(limit, self.batch_size), "offset": offset}
            if filters:
                params.update(filters)
            resp = self._client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", data.get("results", []))
        try:
            return self._retry_request(_do)
        except Exception as e:
            log.warning("[JARVIS] fetch_materials failed: %s", e)
            return []

    def get_material_by_id(self, source_id: str) -> Optional[dict]:
        def _do():
            resp = self._client.get(self.base_url, params={"jid": source_id})
            resp.raise_for_status()
            data = resp.json()
            results = data if isinstance(data, list) else data.get("data", [])
            return results[0] if results else None
        try:
            return self._retry_request(_do)
        except Exception:
            return None

    def total_count(self) -> int:
        return 80000  # known approximate size of JARVIS-DFT 3D
