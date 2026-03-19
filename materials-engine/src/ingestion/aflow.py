"""Ingestor for AFLOW REST API (http://aflow.org/API/aflux/)."""

import httpx
from typing import List, Optional
from .base import BaseIngestor


class AFLOWIngestor(BaseIngestor):
    """Fetches materials from the AFLOW database via AFLUX API.

    No API key required.
    """

    def __init__(self, base_url: str = "http://aflow.org/API/aflux/",
                 rate_limit: float = 2.0, batch_size: int = 500):
        super().__init__(rate_limit)
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size

    @property
    def source_name(self) -> str:
        return "aflow"

    def fetch_materials(self, limit: int = 100, offset: int = 0,
                        filters: Optional[dict] = None) -> List[dict]:
        self._throttle()
        # AFLUX query: request key properties, paginate with paging(offset,limit)
        keywords = "compound,Egap,Bvoigt,sg2,species"
        url = (f"{self.base_url}?matchbook(*),paging({offset},{min(limit, self.batch_size)}),"
               f"$({keywords}),format(json)")
        try:
            resp = httpx.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", data.get("response", []))
        except Exception as e:
            print(f"[AFLOW] Error: {e}")
            return []

    def get_material_by_id(self, source_id: str) -> Optional[dict]:
        self._throttle()
        url = f"{self.base_url}?auid('{source_id}'),format(json)"
        try:
            resp = httpx.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data if isinstance(data, list) else data.get("data", [])
            return results[0] if results else None
        except Exception as e:
            print(f"[AFLOW] Error fetching {source_id}: {e}")
            return None

    def total_count(self) -> int:
        # AFLOW doesn't have a simple count endpoint; return known estimate
        return 3500000


if __name__ == "__main__":
    af = AFLOWIngestor()
    batch = af.fetch_materials(limit=3)
    print(f"Fetched {len(batch)} materials from AFLOW")
    for m in batch[:3]:
        print(f"  {m}")
