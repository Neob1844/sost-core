#!/usr/bin/env python3
"""Build advanced geomorphometry features from existing DEM bands.

Derives curvature, TRI, multi-scale TPI, relative elevation from the
DEM elevation band already in each AOI stack. No new downloads needed.
"""
import argparse, os, sys, json, glob
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def compute_curvature(elevation, px_m):
    """Compute profile and plan curvature from elevation grid."""
    from scipy.ndimage import uniform_filter
    # Laplacian approximation for curvature
    gy, gx = np.gradient(elevation, px_m)
    gyy, gyx = np.gradient(gy, px_m)
    gxy, gxx = np.gradient(gx, px_m)
    # Total curvature (Laplacian)
    curvature = gxx + gyy
    return np.clip(curvature, -0.01, 0.01).astype(np.float32)


def compute_tri(elevation):
    """Terrain Ruggedness Index (Riley et al. 1999)."""
    from scipy.ndimage import generic_filter
    def _tri(x):
        center = x[4]  # 3x3 kernel center
        return np.sqrt(np.mean((x - center)**2))
    return generic_filter(elevation, _tri, size=3).astype(np.float32)


def compute_tpi_multiscale(elevation, scales_px=[5, 15, 30]):
    """Multi-scale TPI: elevation minus focal mean at different radii."""
    from scipy.ndimage import uniform_filter
    tpis = []
    for s in scales_px:
        focal = uniform_filter(elevation, size=s)
        tpi = (elevation - focal).astype(np.float32)
        tpis.append(tpi)
    return tpis


def compute_relative_elevation(elevation, window=51):
    """Elevation relative to local min-max range."""
    from scipy.ndimage import minimum_filter, maximum_filter
    local_min = minimum_filter(elevation, size=window)
    local_max = maximum_filter(elevation, size=window)
    drange = local_max - local_min
    drange[drange < 1] = 1  # avoid division by zero
    return ((elevation - local_min) / drange).astype(np.float32)


def main():
    p = argparse.ArgumentParser(description="Build advanced geomorphometry from existing DEM")
    p.add_argument("--aoi", required=True)
    p.add_argument("--stack-dir", default=os.path.expanduser("~/SOST/geaspirit/data/stack"))
    p.add_argument("--data-dir", default=os.path.expanduser("~/SOST/geaspirit/data"))
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/geomorph"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    import rasterio

    # Find stack
    for pattern in [f"{args.aoi}_global_stack.tif", f"{args.aoi}_full_stack.tif"]:
        sp = os.path.join(args.stack_dir, pattern)
        if os.path.exists(sp): break
    else:
        # Try legacy path
        sp = os.path.join(args.data_dir, f"{args.aoi}_stack.tif")
    if not os.path.exists(sp):
        print(f"  ! No stack for {args.aoi}"); return

    # Load and find elevation band
    meta_path = sp.replace(".tif", "_metadata.json")
    if not os.path.exists(meta_path):
        meta_path = sp.replace(".tif", "_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    band_names = meta.get("bands", [])

    with rasterio.open(sp) as src:
        bands = src.read()
        transform = src.transform
        h, w = src.height, src.width
        profile = src.profile.copy()

    px_m = abs(transform.a) * 111000

    # Find elevation band
    elev_idx = None
    for i, name in enumerate(band_names):
        if "elevation" in name.lower():
            elev_idx = i; break
    if elev_idx is None:
        # Try DEM band naming from Chuquicamata
        for i, name in enumerate(band_names):
            if "dem" in name.lower() and "b1" in name.lower():
                elev_idx = i; break

    if elev_idx is None:
        print(f"  ! No elevation band found in {args.aoi}")
        print(f"    Bands: {band_names}")
        return

    elevation = bands[elev_idx].astype(np.float32)
    elevation[~np.isfinite(elevation)] = np.nanmedian(elevation)
    print(f"=== Geomorphometry: {args.aoi} ({w}x{h}, elev band={elev_idx}) ===")

    # Compute features
    geomorph_bands = []
    geomorph_names = []

    # Curvature
    print("  Computing curvature...")
    curv = compute_curvature(elevation, px_m)
    geomorph_bands.append(curv)
    geomorph_names.append("curvature")

    # TRI
    print("  Computing TRI...")
    tri = compute_tri(elevation)
    geomorph_bands.append(tri)
    geomorph_names.append("tri")

    # Multi-scale TPI
    print("  Computing multi-scale TPI...")
    for scale, name in [(5, "tpi_150m"), (15, "tpi_450m"), (30, "tpi_900m")]:
        tpis = compute_tpi_multiscale(elevation, [scale])
        geomorph_bands.append(tpis[0])
        geomorph_names.append(name)

    # Relative elevation
    print("  Computing relative elevation...")
    rel_elev = compute_relative_elevation(elevation, window=51)
    geomorph_bands.append(rel_elev)
    geomorph_names.append("relative_elevation")

    # Stack and save
    stack = np.stack(geomorph_bands)
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, f"{args.aoi}_geomorph_stack.tif")
    profile.update(count=stack.shape[0], dtype="float32", compress="lzw")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(stack)

    meta_out = {"aoi": args.aoi, "bands": geomorph_names, "n_bands": len(geomorph_names),
                "source": "derived_from_dem", "pixel_size_m": round(px_m, 1)}
    with open(os.path.join(args.output_dir, f"{args.aoi}_geomorph_metadata.json"), "w") as f:
        json.dump(meta_out, f, indent=2)

    os.makedirs(args.reports, exist_ok=True)
    md = f"# Geomorphometry: {args.aoi}\n\n"
    md += f"Source: DEM band {elev_idx} ({band_names[elev_idx]})\n"
    md += f"Pixel: {px_m:.1f}m\n\n"
    md += "| Feature | Description |\n|---------|-------------|\n"
    for name in geomorph_names:
        md += f"| {name} | Derived from elevation |\n"
    with open(os.path.join(args.reports, f"{args.aoi}_geomorph_report.md"), "w") as f:
        f.write(md)

    valid = np.all(np.isfinite(stack), axis=0).sum()
    print(f"  Saved: {out_path} ({len(geomorph_names)} bands, {valid}/{h*w} valid)")


if __name__ == "__main__":
    main()
