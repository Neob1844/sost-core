#!/usr/bin/env python3
"""Priority 2 — Build geology features from public sources.

Uses Macrostrat API (universal, free) as primary source for all zones.
For Pilbara, supplements with Geoscience Australia 1:1M shapefiles if available.

Generates per-pixel features:
- lithology_code (integer ID per lithology type)
- lithology_group (broad category: ignite, sedimentary, metamorphic, volcanic, etc.)
- distance_to_contact_m (distance to nearest lithology boundary)
- geological_age_code (integer encoding of geological age)
- mapped_geology_available (1 if data exists, 0 if fallback/missing)
"""
import argparse, os, sys, json, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG

# Macrostrat lithology → group mapping
LITH_GROUPS = {
    "igneous": ["granite", "diorite", "gabbro", "basalt", "andesite", "rhyolite",
                 "dacite", "tonalite", "syenite", "monzonite", "pegmatite",
                 "plutonic", "igneous", "intrusive", "volcanic", "porphyry",
                 "diabase", "norite", "granodiorite", "trachyte", "phonolite"],
    "sedimentary": ["sandstone", "shale", "limestone", "dolomite", "conglomerate",
                     "siltstone", "mudstone", "marl", "chalk", "sedimentary",
                     "claystone", "greywacke", "arkose", "breccia", "turbidite",
                     "evaporite", "carbonate", "chert", "fluvial", "alluvium",
                     "colluvium", "lacustrine", "marine"],
    "metamorphic": ["gneiss", "schist", "marble", "quartzite", "slate",
                     "phyllite", "amphibolite", "granulite", "metamorphic",
                     "hornfels", "mylonite", "migmatite", "eclogite",
                     "paragneiss", "orthogneiss", "metasediment", "metavolcanic"],
    "volcanic": ["tuff", "ignimbrite", "lava", "pyroclastic", "ash",
                  "volcaniclastic", "flow", "agglomerate"],
    "ultramafic": ["peridotite", "serpentinite", "dunite", "komatiite",
                    "pyroxenite", "harzburgite", "ultramafic", "chromitite"],
    "surficial": ["regolith", "laterite", "soil", "sand", "gravel",
                   "clay", "calcrete", "ferricrete", "duricrust",
                   "quaternary", "alluvial", "aeolian", "glacial"],
}


def classify_lithology(name):
    """Classify a lithology name into a group."""
    if not name:
        return "unknown", 0
    name_lower = name.lower()
    for group, keywords in LITH_GROUPS.items():
        for kw in keywords:
            if kw in name_lower:
                return group, list(LITH_GROUPS.keys()).index(group) + 1
    return "unknown", 0


def classify_age(age_str):
    """Convert geological age string to numeric code (rough Ma midpoint)."""
    if not age_str:
        return 0
    if isinstance(age_str, (int, float)):
        return float(age_str)
    age_lower = str(age_str).lower()
    age_map = {
        "quaternary": 1, "holocene": 0.005, "pleistocene": 1,
        "neogene": 12, "pliocene": 4, "miocene": 15,
        "paleogene": 45, "oligocene": 30, "eocene": 45, "paleocene": 60,
        "cretaceous": 100, "jurassic": 175, "triassic": 230,
        "permian": 280, "carboniferous": 320,
        "devonian": 385, "silurian": 430, "ordovician": 470, "cambrian": 510,
        "neoproterozoic": 750, "cryogenian": 700, "ediacaran": 580,
        "mesoproterozoic": 1200, "paleoproterozoic": 2000,
        "archean": 3000, "neoarchean": 2700, "mesoarchean": 3100, "paleoarchean": 3500,
        "proterozoic": 1500, "precambrian": 2500,
        "cenozoic": 30, "mesozoic": 150, "paleozoic": 350, "phanerozoic": 250,
    }
    for key, val in age_map.items():
        if key in age_lower:
            return val
    return 0


def query_macrostrat_point(lat, lon, timeout=10):
    """Query Macrostrat API for geology at a single point."""
    import requests
    url = f"https://macrostrat.org/api/v2/geologic_units/map?lat={lat}&lng={lon}&response=long"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("success", {}).get("data"):
                units = data["success"]["data"]
                if units:
                    u = units[0]
                    return {
                        "lith": u.get("lith", ""),
                        "name": u.get("name", ""),
                        "strat_name": u.get("strat_name", ""),
                        "age": u.get("t_age", ""),
                        "b_age": u.get("b_age", 0),
                        "t_age": u.get("t_age", 0),
                        "lith_type": u.get("lith_type", ""),
                    }
    except Exception:
        pass
    return None


def build_geology_grid(bbox, grid_h, grid_w, transform, sample_step=20):
    """Query Macrostrat on a coarse grid, interpolate to full resolution."""
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    min_lon, min_lat, max_lon, max_lat = bbox
    # Coarse grid
    rows_sample = list(range(0, grid_h, sample_step))
    cols_sample = list(range(0, grid_w, sample_step))
    if rows_sample[-1] != grid_h - 1:
        rows_sample.append(grid_h - 1)
    if cols_sample[-1] != grid_w - 1:
        cols_sample.append(grid_w - 1)

    total_queries = len(rows_sample) * len(cols_sample)
    print(f"  Querying Macrostrat: {len(rows_sample)}x{len(cols_sample)} = {total_queries} points...")

    # Build lithology ID map
    lith_names = {}  # id -> name
    lith_counter = 1
    coarse_lith = np.zeros((len(rows_sample), len(cols_sample)), dtype=np.int32)
    coarse_group = np.zeros((len(rows_sample), len(cols_sample)), dtype=np.int32)
    coarse_age = np.zeros((len(rows_sample), len(cols_sample)), dtype=np.float32)
    coarse_avail = np.zeros((len(rows_sample), len(cols_sample)), dtype=np.int32)

    # Build query list
    queries = []
    for ri, r in enumerate(rows_sample):
        for ci, c in enumerate(cols_sample):
            px_lon = transform.c + (c + 0.5) * transform.a
            px_lat = transform.f + (r + 0.5) * transform.e
            queries.append((ri, ci, px_lat, px_lon))

    # Use thread pool for concurrent HTTP requests
    session = requests.Session()
    failed = 0
    done = 0

    def fetch_one(q):
        ri, ci, lat, lon = q
        return ri, ci, query_macrostrat_point(lat, lon, timeout=15)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_one, q): q for q in queries}
        for future in as_completed(futures):
            ri, ci, result = future.result()
            done += 1

            if result and result.get("lith"):
                lith_name = result["lith"]
                if lith_name not in lith_names.values():
                    lith_names[lith_counter] = lith_name
                    lith_id = lith_counter
                    lith_counter += 1
                else:
                    lith_id = [k for k, v in lith_names.items() if v == lith_name][0]

                group_name, group_id = classify_lithology(lith_name)
                age_val = classify_age(result.get("age", ""))
                if not age_val and result.get("b_age"):
                    try:
                        age_val = (float(result["b_age"]) + float(result.get("t_age", 0))) / 2
                    except (ValueError, TypeError):
                        pass

                coarse_lith[ri, ci] = lith_id
                coarse_group[ri, ci] = group_id
                coarse_age[ri, ci] = age_val
                coarse_avail[ri, ci] = 1
            else:
                failed += 1

            if done % 100 == 0:
                pct = done / total_queries * 100
                print(f"    {done}/{total_queries} ({pct:.0f}%) — {failed} failed")

    print(f"  Macrostrat queries: {done} total, {failed} failed, {len(lith_names)} unique lithologies")

    # Interpolate coarse to full resolution using nearest neighbor
    from scipy.ndimage import zoom
    # Map coarse grid indices to full grid
    lith_full = np.zeros((grid_h, grid_w), dtype=np.int32)
    group_full = np.zeros((grid_h, grid_w), dtype=np.int32)
    age_full = np.zeros((grid_h, grid_w), dtype=np.float32)
    avail_full = np.zeros((grid_h, grid_w), dtype=np.int32)

    # Simple nearest-neighbor upscaling
    for r in range(grid_h):
        ri = min(np.searchsorted(rows_sample, r, side='right') - 1, len(rows_sample) - 1)
        ri = max(0, ri)
        for c in range(grid_w):
            ci = min(np.searchsorted(cols_sample, c, side='right') - 1, len(cols_sample) - 1)
            ci = max(0, ci)
            lith_full[r, c] = coarse_lith[ri, ci]
            group_full[r, c] = coarse_group[ri, ci]
            age_full[r, c] = coarse_age[ri, ci]
            avail_full[r, c] = coarse_avail[ri, ci]

    return lith_full, group_full, age_full, avail_full, lith_names


def compute_distance_to_contact(lith_raster, px_size_m):
    """Compute distance to nearest lithology boundary for each pixel."""
    from scipy.ndimage import distance_transform_edt
    # Find contact pixels (where adjacent pixels have different lithology)
    h, w = lith_raster.shape
    contact = np.zeros((h, w), dtype=bool)

    # Check 4-neighbors
    contact[:-1, :] |= (lith_raster[:-1, :] != lith_raster[1:, :])
    contact[1:, :]  |= (lith_raster[:-1, :] != lith_raster[1:, :])
    contact[:, :-1] |= (lith_raster[:, :-1] != lith_raster[:, 1:])
    contact[:, 1:]  |= (lith_raster[:, :-1] != lith_raster[:, 1:])

    # Distance from each pixel to nearest contact
    if contact.any():
        dist = distance_transform_edt(~contact) * px_size_m
    else:
        dist = np.full((h, w), 99999.0, dtype=np.float32)
    return dist.astype(np.float32)


def main():
    p = argparse.ArgumentParser(description="Build geology features from public sources")
    p.add_argument("--stack", default=None,
                   help="Reference stack TIF for grid alignment")
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--sample-step", type=int, default=20,
                   help="Macrostrat sample every N pixels (default 20 ≈ 600m at 30m)")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/geology_maps"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    if args.stack is None:
        args.stack = os.path.expanduser(f"~/SOST/geaspirit/data/{args.pilot}_stack.tif")

    import rasterio

    # Check if stack exists
    if not os.path.exists(args.stack):
        print(f"  ! Stack not found: {args.stack}")
        print(f"  ! Satellite data must be downloaded first for {args.pilot}")
        # Write a stub report
        os.makedirs(args.reports, exist_ok=True)
        report = {
            "pilot": args.pilot,
            "status": "SKIPPED",
            "reason": f"No satellite stack found at {args.stack}",
            "recommendation": "Run satellite download scripts first",
        }
        with open(os.path.join(args.reports, f"{args.pilot}_geology_sources.md"), "w") as f:
            f.write(f"# Geology Features — {args.pilot}\n\n**SKIPPED**: No satellite stack.\n")
        with open(os.path.join(args.reports, f"{args.pilot}_geology_sources.json"), "w") as f:
            json.dump(report, f, indent=2)
        return

    # Load reference grid from stack
    print(f"=== Building Geology Features — {args.pilot} ===")
    with rasterio.open(args.stack) as src:
        h, w = src.height, src.width
        transform = src.transform
        crs = src.crs
        profile = src.profile.copy()

    px_deg = abs(transform.a)
    px_m = px_deg * 111000
    print(f"  Reference grid: {w}x{h}, {px_m:.1f}m/px, CRS={crs}")

    zone = ZONES[args.pilot]
    lat_c, lon_c = zone["center"]
    bbox = [lon_c - HALF_DEG, lat_c - HALF_DEG, lon_c + HALF_DEG, lat_c + HALF_DEG]

    # Query Macrostrat
    lith, group, age, avail, lith_names = build_geology_grid(
        bbox, h, w, transform, sample_step=args.sample_step
    )

    # Compute distance to contact
    print("  Computing distance to lithology contacts...")
    dist_contact = compute_distance_to_contact(lith, px_m)

    # Coverage stats
    coverage_pct = (avail > 0).sum() / (h * w) * 100
    unique_liths = len(lith_names)
    print(f"  Coverage: {coverage_pct:.1f}% of pixels have geology data")
    print(f"  Unique lithologies: {unique_liths}")
    print(f"  Lithology groups: {np.unique(group[group > 0]).tolist()}")

    # Save geology stack (5 bands)
    os.makedirs(args.output, exist_ok=True)
    out_path = os.path.join(args.output, f"{args.pilot}_geology_stack.tif")
    band_names = ["lithology_code", "lithology_group", "geological_age_ma",
                   "distance_to_contact_m", "mapped_geology_available"]
    stack = np.stack([
        lith.astype(np.float32),
        group.astype(np.float32),
        age.astype(np.float32),
        dist_contact,
        avail.astype(np.float32),
    ])

    profile.update(count=5, dtype='float32', compress='lzw')
    with rasterio.open(out_path, 'w', **profile) as dst:
        dst.write(stack)
    print(f"  Saved: {out_path}")

    # Metadata
    meta = {
        "pilot": args.pilot,
        "bands": band_names,
        "n_bands": 5,
        "source": "Macrostrat API (macrostrat.org)",
        "sample_step_px": args.sample_step,
        "coverage_pct": round(coverage_pct, 1),
        "unique_lithologies": unique_liths,
        "lithology_ids": {str(k): v for k, v in lith_names.items()},
        "lithology_groups": list(LITH_GROUPS.keys()),
        "grid": f"{w}x{h}",
        "px_size_m": round(px_m, 1),
    }
    meta_path = os.path.join(args.output, f"{args.pilot}_geology_metadata.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    # Report
    os.makedirs(args.reports, exist_ok=True)
    md = f"# Geology Features — {args.pilot}\n\n"
    md += f"## Source\n- **Macrostrat API** (macrostrat.org) — CC-BY 4.0\n"
    md += f"- Sample step: every {args.sample_step} pixels (~{args.sample_step * px_m:.0f}m)\n"
    md += f"- Coverage: {coverage_pct:.1f}%\n\n"
    md += f"## Bands\n"
    for i, name in enumerate(band_names):
        md += f"{i+1}. **{name}**\n"
    md += f"\n## Lithologies Found ({unique_liths})\n\n"
    for lid, name in sorted(lith_names.items()):
        grp, _ = classify_lithology(name)
        md += f"- ID {lid}: {name} ({grp})\n"
    md += f"\n## Limitations\n\n"
    if coverage_pct < 50:
        md += f"- Low coverage ({coverage_pct:.1f}%) — Macrostrat has limited data for this region\n"
    md += f"- Resolution limited by sample step ({args.sample_step * px_m:.0f}m)\n"
    md += f"- No fault/structure lines from Macrostrat (distance_to_fault not available)\n"
    md += f"- Lithology classification is approximate (keyword-based grouping)\n"

    with open(os.path.join(args.reports, f"{args.pilot}_geology_sources.md"), "w") as f:
        f.write(md)
    report_json = {
        "pilot": args.pilot,
        "status": "COMPLETE",
        "source": "Macrostrat API",
        "coverage_pct": round(coverage_pct, 1),
        "unique_lithologies": unique_liths,
        "bands": band_names,
        "output": out_path,
    }
    with open(os.path.join(args.reports, f"{args.pilot}_geology_sources.json"), "w") as f:
        json.dump(report_json, f, indent=2)
    print(f"  Report: {args.pilot}_geology_sources.md")


if __name__ == "__main__":
    main()
