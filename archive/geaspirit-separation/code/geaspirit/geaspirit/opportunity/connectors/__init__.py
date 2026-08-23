"""
Opportunity connectors. Each module exposes a single public function:

    query(aoi: AOI, **kwargs) -> ConnectorResult

Connectors must:
* never raise on transient network errors — return ConnectorResult
  with status="error" and a populated error_message instead.
* never invent data — confidence reflects source quality.
* set fetched_at to a UTC ISO-8601 timestamp.
* keep stdlib-only for sprint 1 (no requests / shapely / geopandas).
"""
