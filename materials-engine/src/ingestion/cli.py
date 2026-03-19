"""CLI for materials ingestion.

Usage:
  python -m src.ingestion.cli ingest cod --limit 100
  python -m src.ingestion.cli ingest all --limit 50 --dry-run
"""

import argparse
import logging
import sys
import yaml
from datetime import datetime, timezone

from .materials_project import MaterialsProjectIngestor
from .aflow import AFLOWIngestor
from .cod import CODIngestor
from .jarvis import JARVISIngestor
from ..normalization.normalizer import normalize
from ..storage.db import MaterialsDB

log = logging.getLogger("ingestion")


def _load_config(path: str) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        log.warning("Config %s not found, using defaults", path)
        return {}


def _get_ingestor(source: str, cfg: dict):
    if source == "materials_project":
        key = cfg.get("materials_project", {}).get("api_key", "")
        if not key:
            log.error("Materials Project requires api_key in config.yaml")
            return None
        return MaterialsProjectIngestor(api_key=key)
    elif source == "aflow":
        return AFLOWIngestor()
    elif source == "cod":
        return CODIngestor()
    elif source == "jarvis":
        return JARVISIngestor()
    else:
        log.error("Unknown source: %s", source)
        return None


def run_ingest(source: str, cfg: dict, limit: int, offset: int,
               batch_size: int, dry_run: bool, db_path: str):
    """Run ingestion for a single source. Returns stats dict."""
    stats = {"source": source, "fetched": 0, "normalized": 0,
             "inserted": 0, "failed": 0, "skipped": 0}

    ingestor = _get_ingestor(source, cfg)
    if not ingestor:
        stats["failed"] = 1
        return stats

    db = None if dry_run else MaterialsDB(db_path)

    log.info("[%s] Starting ingestion: limit=%d offset=%d dry_run=%s",
             source, limit, offset, dry_run)

    fetched = 0
    while fetched < limit:
        batch_limit = min(batch_size, limit - fetched)
        try:
            raw_batch = ingestor.fetch_materials(limit=batch_limit, offset=offset + fetched)
        except Exception as e:
            log.error("[%s] Fetch error at offset %d: %s", source, offset + fetched, e)
            stats["failed"] += 1
            break

        if not raw_batch:
            log.info("[%s] No more data at offset %d", source, offset + fetched)
            break

        stats["fetched"] += len(raw_batch)
        for raw in raw_batch:
            try:
                m = normalize(raw, source)
                stats["normalized"] += 1
                if dry_run:
                    log.debug("[DRY] %s %s bg=%s", m.formula, m.source_id, m.band_gap)
                else:
                    if db.insert_material(m):
                        stats["inserted"] += 1
                    else:
                        stats["failed"] += 1
            except Exception as e:
                log.warning("[%s] Normalize/insert error: %s", source, e)
                stats["failed"] += 1

        fetched += len(raw_batch)
        log.info("[%s] Progress: %d/%d fetched, %d normalized, %d inserted",
                 source, fetched, limit, stats["normalized"], stats["inserted"])

    log.info("[%s] DONE: %s", source, stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Materials Engine Ingestion CLI")
    parser.add_argument("command", choices=["ingest"])
    parser.add_argument("source", nargs="?", default="all",
                        choices=["mp", "materials_project", "aflow", "cod", "jarvis", "all"])
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = _load_config(args.config)
    db_path = args.db or cfg.get("storage", {}).get("db_path", "materials.db")

    source_map = {"mp": "materials_project", "materials_project": "materials_project",
                  "aflow": "aflow", "cod": "cod", "jarvis": "jarvis"}

    if args.source == "all":
        sources = ["cod", "aflow", "jarvis"]  # MP requires key, run separately
        mp_key = cfg.get("materials_project", {}).get("api_key", "")
        if mp_key:
            sources.insert(0, "materials_project")
        else:
            log.warning("Skipping Materials Project (no API key)")
    else:
        sources = [source_map.get(args.source, args.source)]

    all_stats = []
    for src in sources:
        s = run_ingest(src, cfg, args.limit, args.offset,
                       args.batch_size, args.dry_run, db_path)
        all_stats.append(s)

    # Summary
    print("\n=== INGESTION SUMMARY ===")
    total_f, total_n, total_i, total_fail = 0, 0, 0, 0
    for s in all_stats:
        print(f"  {s['source']:20s}: fetched={s['fetched']}, normalized={s['normalized']}, "
              f"inserted={s['inserted']}, failed={s['failed']}")
        total_f += s["fetched"]
        total_n += s["normalized"]
        total_i += s["inserted"]
        total_fail += s["failed"]
    print(f"  {'TOTAL':20s}: fetched={total_f}, normalized={total_n}, "
          f"inserted={total_i}, failed={total_fail}")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
