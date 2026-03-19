"""SQLite storage for materials (dev backend — migrate to PostgreSQL for production).

Design is migration-friendly: standard SQL, parameterized queries, no SQLite-specific features.
Thread safety: each call creates its own connection. For server use, wrap with connection pool.

Phase 1 prototype. Not production-ready.
"""

import sqlite3
import json
import logging
from typing import List, Optional
from ..schema import Material

log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS materials (
    canonical_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    formula TEXT NOT NULL DEFAULT '',
    formula_pretty TEXT DEFAULT '',
    elements TEXT DEFAULT '[]',
    n_elements INTEGER DEFAULT 0,
    spacegroup INTEGER,
    spacegroup_symbol TEXT,
    crystal_system TEXT,
    lattice_params TEXT,
    nsites INTEGER,
    structure_ref TEXT,
    structure_format TEXT,
    structure_data TEXT,
    structure_sha256 TEXT,
    has_valid_structure INTEGER,
    band_gap REAL,
    band_gap_direct INTEGER,
    formation_energy REAL,
    energy_above_hull REAL,
    bulk_modulus REAL,
    shear_modulus REAL,
    total_magnetization REAL,
    raw_payload_sha256 TEXT,
    source_url TEXT,
    ingested_at TEXT,
    normalized_at TEXT,
    normalizer_version TEXT,
    confidence REAL DEFAULT 0.0,
    applications TEXT DEFAULT '[]',
    embedding TEXT,
    PRIMARY KEY (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_id ON materials(canonical_id);
CREATE INDEX IF NOT EXISTS idx_formula ON materials(formula);
CREATE INDEX IF NOT EXISTS idx_band_gap ON materials(band_gap);
CREATE INDEX IF NOT EXISTS idx_formation_energy ON materials(formation_energy);
CREATE INDEX IF NOT EXISTS idx_elements ON materials(elements);
"""


class MaterialsDB:
    def __init__(self, db_path: str = "materials.db"):
        self.db_path = db_path
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        conn = self._connect()
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    def insert_material(self, m: Material) -> bool:
        """Upsert: insert or update if (source, source_id) already exists."""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO materials
                   (canonical_id, source, source_id, formula, formula_pretty,
                    elements, n_elements, spacegroup, spacegroup_symbol,
                    crystal_system, lattice_params, nsites,
                    structure_ref, structure_format, structure_data, structure_sha256, has_valid_structure,
                    band_gap, band_gap_direct, formation_energy, energy_above_hull,
                    bulk_modulus, shear_modulus, total_magnetization,
                    raw_payload_sha256, source_url, ingested_at, normalized_at,
                    normalizer_version, confidence, applications, embedding)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source, source_id) DO UPDATE SET
                    canonical_id=excluded.canonical_id, formula=excluded.formula,
                    band_gap=excluded.band_gap, formation_energy=excluded.formation_energy,
                    bulk_modulus=excluded.bulk_modulus, normalized_at=excluded.normalized_at,
                    confidence=excluded.confidence, raw_payload_sha256=excluded.raw_payload_sha256,
                    has_valid_structure=excluded.has_valid_structure""",
                (m.canonical_id, m.source, m.source_id, m.formula, m.formula_pretty,
                 json.dumps(m.elements), m.n_elements,
                 m.spacegroup, m.spacegroup_symbol,
                 m.crystal_system,
                 json.dumps(m.lattice_params) if m.lattice_params else None,
                 m.nsites, m.structure_ref, m.structure_format, m.structure_data,
                 m.structure_sha256,
                 1 if m.has_valid_structure else (0 if m.has_valid_structure is not None else None),
                 m.band_gap,
                 1 if m.band_gap_direct else (0 if m.band_gap_direct is not None else None),
                 m.formation_energy, m.energy_above_hull,
                 m.bulk_modulus, m.shear_modulus, m.total_magnetization,
                 m.raw_payload_sha256, m.source_url,
                 m.ingested_at, m.normalized_at, m.normalizer_version,
                 m.confidence,
                 json.dumps(m.applications) if m.applications else "[]",
                 json.dumps(m.embedding) if m.embedding else None))
            conn.commit()
            return True
        except Exception as e:
            log.error("Insert error: %s", e)
            return False
        finally:
            conn.close()

    def _row_to_material(self, row) -> Material:
        d = dict(row)
        d["elements"] = json.loads(d.get("elements") or "[]")
        d["applications"] = json.loads(d.get("applications") or "[]")
        lp = d.get("lattice_params")
        d["lattice_params"] = json.loads(lp) if lp else None
        emb = d.get("embedding")
        d["embedding"] = json.loads(emb) if emb else None
        bgd = d.get("band_gap_direct")
        d["band_gap_direct"] = bool(bgd) if bgd is not None else None
        hvs = d.get("has_valid_structure")
        d["has_valid_structure"] = bool(hvs) if hvs is not None else None
        return Material.from_dict(d)

    def get_material(self, canonical_id: str) -> Optional[Material]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM materials WHERE canonical_id=?",
                               (canonical_id,)).fetchone()
            return self._row_to_material(row) if row else None
        finally:
            conn.close()

    def get_by_source(self, source: str, source_id: str) -> Optional[Material]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM materials WHERE source=? AND source_id=?",
                               (source, source_id)).fetchone()
            return self._row_to_material(row) if row else None
        finally:
            conn.close()

    def search_materials(self, formula: str = None, elements: List[str] = None,
                         band_gap_min: float = None, band_gap_max: float = None,
                         formation_energy_min: float = None, formation_energy_max: float = None,
                         bulk_modulus_min: float = None, bulk_modulus_max: float = None,
                         source: str = None,
                         limit: int = 100, offset: int = 0) -> List[Material]:
        """Compound search with all filters in a single SQL query."""
        conditions, params = [], []
        if formula:
            conditions.append("formula = ?")
            params.append(formula)
        if elements:
            for e in elements:
                conditions.append("elements LIKE ?")
                params.append(f'%"{e}"%')
        if source:
            conditions.append("source = ?")
            params.append(source)

        range_filters = [
            ("band_gap", band_gap_min, band_gap_max),
            ("formation_energy", formation_energy_min, formation_energy_max),
            ("bulk_modulus", bulk_modulus_min, bulk_modulus_max),
        ]
        for col, mn, mx in range_filters:
            if mn is not None:
                conditions.append(f"{col} >= ?")
                params.append(mn)
            if mx is not None:
                conditions.append(f"{col} <= ?")
                params.append(mx)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM materials {where} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_material(r) for r in rows]
        finally:
            conn.close()

    def list_materials(self, limit: int = 20, offset: int = 0) -> List[Material]:
        return self.search_materials(limit=limit, offset=offset)

    def count(self) -> int:
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        finally:
            conn.close()

    def stats(self) -> dict:
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
            by_source = {}
            for row in conn.execute(
                    "SELECT source, COUNT(*) as c FROM materials GROUP BY source"):
                by_source[row["source"]] = row["c"]
            by_crystal = {}
            for row in conn.execute(
                    "SELECT crystal_system, COUNT(*) as c FROM materials "
                    "WHERE crystal_system IS NOT NULL GROUP BY crystal_system"):
                by_crystal[row["crystal_system"]] = row["c"]
            return {"total": total, "by_source": by_source, "by_crystal_system": by_crystal}
        finally:
            conn.close()

    # --- Audit queries ---

    def list_missing_structure(self, limit: int = 100) -> List[Material]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM materials WHERE has_valid_structure IS NULL OR has_valid_structure = 0 LIMIT ?",
                (limit,)).fetchall()
            return [self._row_to_material(r) for r in rows]
        finally:
            conn.close()

    def list_missing_properties(self, prop: str = "band_gap", limit: int = 100) -> List[Material]:
        allowed = {"band_gap", "formation_energy", "bulk_modulus", "shear_modulus"}
        if prop not in allowed:
            return []
        conn = self._connect()
        try:
            rows = conn.execute(f"SELECT * FROM materials WHERE {prop} IS NULL LIMIT ?",
                                (limit,)).fetchall()
            return [self._row_to_material(r) for r in rows]
        finally:
            conn.close()

    def search_training_candidates(self, required_props: List[str] = None,
                                   limit: int = 10000) -> List[Material]:
        """Find materials suitable for ML training (have all required properties)."""
        if not required_props:
            required_props = ["band_gap", "formation_energy"]
        conditions = [f"{p} IS NOT NULL" for p in required_props]
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        conn = self._connect()
        try:
            rows = conn.execute(f"SELECT * FROM materials {where} LIMIT ?",
                                (limit,)).fetchall()
            return [self._row_to_material(r) for r in rows]
        finally:
            conn.close()

    def audit_counts(self) -> dict:
        """Return comprehensive audit counts for the corpus."""
        conn = self._connect()
        try:
            def _count(where=""): return conn.execute(
                f"SELECT COUNT(*) FROM materials {where}").fetchone()[0]
            return {
                "total": _count(),
                "with_formula": _count("WHERE formula != ''"),
                "with_band_gap": _count("WHERE band_gap IS NOT NULL"),
                "with_formation_energy": _count("WHERE formation_energy IS NOT NULL"),
                "with_bulk_modulus": _count("WHERE bulk_modulus IS NOT NULL"),
                "with_shear_modulus": _count("WHERE shear_modulus IS NOT NULL"),
                "with_spacegroup": _count("WHERE spacegroup IS NOT NULL"),
                "with_valid_structure": _count("WHERE has_valid_structure = 1"),
                "ml_ready_bg": _count("WHERE band_gap IS NOT NULL AND formula != ''"),
                "ml_ready_fe": _count("WHERE formation_energy IS NOT NULL AND formula != ''"),
            }
        finally:
            conn.close()
