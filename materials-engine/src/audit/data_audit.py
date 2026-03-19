"""Corpus audit — generates reports on data quality and coverage.

Produces:
  artifacts/data_audit.json — machine-readable audit
  artifacts/data_audit.md  — human-readable report
"""

import json
import os
import logging
from datetime import datetime, timezone
from ..storage.db import MaterialsDB

log = logging.getLogger(__name__)


def run_audit(db: MaterialsDB, output_dir: str = "artifacts") -> dict:
    """Run full corpus audit. Returns audit dict and writes artifacts."""
    os.makedirs(output_dir, exist_ok=True)
    s = db.stats()
    counts = db.audit_counts()

    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_materials": counts["total"],
        "by_source": s["by_source"],
        "by_crystal_system": s["by_crystal_system"],
        "coverage": {
            "with_formula": counts["with_formula"],
            "with_band_gap": counts["with_band_gap"],
            "with_formation_energy": counts["with_formation_energy"],
            "with_bulk_modulus": counts["with_bulk_modulus"],
            "with_shear_modulus": counts["with_shear_modulus"],
            "with_spacegroup": counts["with_spacegroup"],
            "with_valid_structure": counts["with_valid_structure"],
        },
        "ml_readiness": {
            "band_gap_prediction": counts["ml_ready_bg"],
            "formation_energy_prediction": counts["ml_ready_fe"],
        },
    }

    # Write JSON
    json_path = os.path.join(output_dir, "data_audit.json")
    with open(json_path, "w") as f:
        json.dump(audit, f, indent=2)

    # Write Markdown
    md_path = os.path.join(output_dir, "data_audit.md")
    with open(md_path, "w") as f:
        f.write(f"# Materials Engine — Data Audit Report\n\n")
        f.write(f"**Generated:** {audit['timestamp']}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"| Metric | Count |\n|--------|-------|\n")
        f.write(f"| Total materials | {counts['total']} |\n")
        for k, v in audit["coverage"].items():
            pct = f"({v/max(counts['total'],1)*100:.1f}%)" if counts["total"] > 0 else ""
            f.write(f"| {k} | {v} {pct} |\n")
        f.write(f"\n## By Source\n\n")
        for src, cnt in s["by_source"].items():
            f.write(f"- **{src}**: {cnt}\n")
        f.write(f"\n## ML Readiness\n\n")
        f.write(f"- Band gap prediction candidates: **{counts['ml_ready_bg']}**\n")
        f.write(f"- Formation energy prediction candidates: **{counts['ml_ready_fe']}**\n")
        f.write(f"\n---\n*Phase I audit. Not production data.*\n")

    log.info("Audit written to %s and %s", json_path, md_path)
    return audit


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "materials.db"
    db = MaterialsDB(db_path)
    result = run_audit(db)
    print(json.dumps(result, indent=2))
