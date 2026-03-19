"""Structure backfill — recover and persist crystal structures for corpus materials.

Phase III.J: Recovers structures from JARVIS atoms dicts, converts to pymatgen,
validates, serializes to CIF, and persists to the existing database.

Does NOT delete or recreate the database. Only updates structure fields
for materials that are missing them.
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict

from ..normalization.structure import (
    jarvis_atoms_to_pymatgen, validate_structure_obj, structure_to_cif,
    structure_sha256,
)

log = logging.getLogger(__name__)

BACKFILL_DIR = "artifacts/structure_backfill"

# Reason codes
RC_RECOVERED = "recovered"
RC_VALIDATED = "validated"
RC_PERSISTED = "persisted"
RC_MISSING_PAYLOAD = "missing_source_payload"
RC_INVALID_STRUCTURE = "invalid_structure_object"
RC_PYMATGEN_FAILED = "pymatgen_parse_failed"
RC_SERIALIZATION_FAILED = "serialization_failed"
RC_PERSIST_FAILED = "persist_failed"
RC_ALREADY_PRESENT = "skipped_already_present"


def backfill_jarvis(db_path: str = "materials.db",
                    limit: int = 100000,
                    offset: int = 0,
                    batch_size: int = 1000,
                    only_missing: bool = True,
                    dry_run: bool = False) -> dict:
    """Backfill structures for JARVIS materials from jarvis-tools bulk data.

    Args:
        db_path: path to SQLite database
        limit: max materials to process
        offset: skip first N JARVIS entries
        batch_size: commit every N updates
        only_missing: skip materials that already have structure_data
        dry_run: don't write to database

    Returns stats dict.
    """
    from jarvis.db.figshare import data as jarvis_data

    t0 = time.time()
    now = datetime.now(timezone.utc).isoformat()

    log.info("Loading JARVIS bulk data...")
    dft = jarvis_data("dft_3d")
    log.info("Loaded %d JARVIS entries", len(dft))

    # Build jid→atoms lookup
    jid_to_atoms = {}
    for entry in dft:
        jid = entry.get("jid", "")
        atoms = entry.get("atoms")
        if jid and atoms:
            jid_to_atoms[jid] = atoms

    log.info("Built lookup: %d entries with atoms", len(jid_to_atoms))

    # Get materials needing backfill
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if only_missing:
        query = ("SELECT source_id, canonical_id, formula FROM materials "
                 "WHERE source='jarvis' AND (structure_data IS NULL OR structure_data='') "
                 "LIMIT ? OFFSET ?")
    else:
        query = ("SELECT source_id, canonical_id, formula FROM materials "
                 "WHERE source='jarvis' LIMIT ? OFFSET ?")

    rows = conn.execute(query, (limit, offset)).fetchall()
    log.info("Materials to process: %d", len(rows))

    stats = {
        "attempted": 0, "recovered": 0, "validated": 0, "persisted": 0,
        "failed": 0, "skipped_already_present": 0,
        "errors": {"missing_payload": 0, "invalid_structure": 0,
                   "pymatgen_failed": 0, "serialization_failed": 0,
                   "persist_failed": 0},
    }

    batch_count = 0
    for row in rows:
        source_id = row["source_id"]
        canonical_id = row["canonical_id"]
        formula = row["formula"]
        stats["attempted"] += 1

        # Look up atoms dict
        atoms_dict = jid_to_atoms.get(source_id)
        if not atoms_dict:
            stats["failed"] += 1
            stats["errors"]["missing_payload"] += 1
            continue

        # Convert to pymatgen
        try:
            struct = jarvis_atoms_to_pymatgen(atoms_dict)
        except Exception as e:
            stats["failed"] += 1
            stats["errors"]["pymatgen_failed"] += 1
            continue

        if struct is None:
            stats["failed"] += 1
            stats["errors"]["invalid_structure"] += 1
            continue

        # Validate
        valid, err = validate_structure_obj(struct)
        if not valid:
            stats["failed"] += 1
            stats["errors"]["invalid_structure"] += 1
            continue

        stats["recovered"] += 1
        stats["validated"] += 1

        # Serialize to CIF
        cif = structure_to_cif(struct)
        if not cif:
            stats["failed"] += 1
            stats["errors"]["serialization_failed"] += 1
            continue

        sha = structure_sha256(cif)
        n_sites = len(struct)

        # Extract symmetry
        sg_number = None
        sg_symbol = None
        crystal_system = None
        try:
            from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
            sga = SpacegroupAnalyzer(struct, symprec=0.1)
            sg_number = sga.get_space_group_number()
            sg_symbol = sga.get_space_group_symbol()
            crystal_system = sga.get_crystal_system()
        except Exception:
            pass

        if dry_run:
            stats["persisted"] += 1
            continue

        # Persist to database
        try:
            conn.execute(
                """UPDATE materials SET
                   structure_data=?, structure_format=?, structure_sha256=?,
                   has_valid_structure=1, nsites=?,
                   spacegroup_symbol=COALESCE(spacegroup_symbol, ?),
                   crystal_system=COALESCE(crystal_system, ?)
                   WHERE source='jarvis' AND source_id=?""",
                (cif, "cif", sha, n_sites, sg_symbol, crystal_system, source_id))
            stats["persisted"] += 1
            batch_count += 1

            if batch_count >= batch_size:
                conn.commit()
                batch_count = 0
                log.info("Progress: %d/%d attempted, %d persisted",
                         stats["attempted"], len(rows), stats["persisted"])
        except Exception as e:
            stats["failed"] += 1
            stats["errors"]["persist_failed"] += 1
            log.warning("Persist failed for %s: %s", source_id, e)

    # Final commit
    if not dry_run:
        conn.commit()
    conn.close()

    elapsed = time.time() - t0
    stats["elapsed_sec"] = round(elapsed, 1)
    stats["started_at"] = now

    log.info("Backfill complete: %d attempted, %d persisted, %d failed (%.1fs)",
             stats["attempted"], stats["persisted"], stats["failed"], elapsed)

    return stats


def pre_backfill_audit(db_path: str = "materials.db") -> dict:
    """Audit structure coverage before backfill."""
    conn = sqlite3.connect(db_path)
    total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    with_struct = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE structure_data IS NOT NULL AND structure_data != ''").fetchone()[0]
    without_struct = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE structure_data IS NULL OR structure_data = ''").fetchone()[0]
    valid_struct = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE has_valid_structure = 1").fetchone()[0]
    jarvis_total = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE source='jarvis'").fetchone()[0]
    jarvis_missing = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE source='jarvis' AND (structure_data IS NULL OR structure_data='')").fetchone()[0]
    conn.close()

    return {
        "total_materials": total,
        "with_structure_data": with_struct,
        "without_structure_data": without_struct,
        "has_valid_structure": valid_struct,
        "jarvis_total": jarvis_total,
        "jarvis_missing_structure": jarvis_missing,
        "structure_coverage_pct": round(100.0 * with_struct / total, 2) if total > 0 else 0,
    }


def post_backfill_audit(db_path: str = "materials.db") -> dict:
    """Audit structure coverage after backfill."""
    return pre_backfill_audit(db_path)


def save_audit(audit: dict, filename: str, output_dir: str = BACKFILL_DIR):
    """Save audit to JSON and Markdown."""
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, f"{filename}.json")
    with open(json_path, "w") as f:
        json.dump(audit, f, indent=2)

    md_path = os.path.join(output_dir, f"{filename}.md")
    md = f"# {filename.replace('_', ' ').title()}\n\n"
    for k, v in audit.items():
        md += f"- **{k}:** {v}\n"
    with open(md_path, "w") as f:
        f.write(md)

    return json_path
