"""Ingestor for Crystallography Open Database (https://www.crystallography.net/cod)."""

import httpx
from typing import List, Optional
from .base import BaseIngestor


class CODIngestor(BaseIngestor):
    """Fetches crystal structures from the Crystallography Open Database.

    No API key required. Primarily provides structural data (formula, spacegroup,
    lattice parameters) with fewer computed properties than MP or AFLOW.
    """

    def __init__(self, base_url: str = "https://www.crystallography.net/cod",
                 rate_limit: float = 2.0, batch_size: int = 100):
        super().__init__(rate_limit)
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size

    @property
    def source_name(self) -> str:
        return "cod"

    def fetch_materials(self, limit: int = 100, offset: int = 0,
                        filters: Optional[dict] = None) -> List[dict]:
        self._throttle()
        url = f"{self.base_url}/result.json"
        params = {
            "format": "json",
            "limit": min(limit, self.batch_size),
            "skip": offset,
        }
        if filters:
            if "formula" in filters:
                params["formula"] = filters["formula"]
            if "elements" in filters:
                params["el1"] = filters["elements"][0] if len(filters["elements"]) > 0 else ""
        try:
            resp = httpx.get(url, params=params, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("results", [])
        except Exception as e:
            print(f"[COD] Error: {e}")
            return []

    def get_material_by_id(self, source_id: str) -> Optional[dict]:
        self._throttle()
        url = f"{self.base_url}/result.json"
        params = {"id": source_id, "format": "json"}
        try:
            resp = httpx.get(url, params=params, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            results = data if isinstance(data, list) else data.get("results", [])
            return results[0] if results else None
        except Exception as e:
            print(f"[COD] Error fetching {source_id}: {e}")
            return None

    def total_count(self) -> int:
        return 530000  # known approximate size


if __name__ == "__main__":
    cod = CODIngestor()
    batch = cod.fetch_materials(limit=3)
    print(f"Fetched {len(batch)} structures from COD")
    for m in batch[:3]:
        print(f"  {m}")
