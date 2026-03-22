#!/usr/bin/env python3
"""Stack all available rasters into a single multi-band GeoTIFF for GeaSpirit Platform."""
import argparse, os, sys, json
import numpy as np

def main():
    p = argparse.ArgumentParser(description="Stack all feature rasters")
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--output", default=None)
    args = p.parse_args()
    base = os.path.expanduser("~/SOST/geaspirit/data")
    if not args.output:
        args.output = os.path.expanduser(f"~/SOST/geaspirit/data/{args.pilot}_stack.tif")

    import rasterio
    from rasterio.warp import reproject, Resampling

    # Collect all available rasters
    candidates = {
        "s2_indices": sorted([os.path.join(base, "indices", f) for f in os.listdir(os.path.join(base, "indices"))
                              if f.startswith(args.pilot) and f.endswith(".tif")]) if os.path.isdir(os.path.join(base, "indices")) else [],
        "sentinel1": [os.path.join(base, "sentinel1", f"{args.pilot}_s1.tif")],
        "dem": [os.path.join(base, "dem", f"{args.pilot}_dem.tif")],
        "thermal": [os.path.join(base, "landsat", f"{args.pilot}_lst.tif")],
    }

    # Reference: first S2 index for grid alignment
    ref_path = candidates["s2_indices"][0] if candidates["s2_indices"] else None
    if not ref_path or not os.path.exists(ref_path):
        print("✗ No S2 indices found as reference"); sys.exit(1)

    with rasterio.open(ref_path) as ref:
        ref_crs, ref_transform, ref_w, ref_h = ref.crs, ref.transform, ref.width, ref.height
    print(f"Reference grid: {ref_w}×{ref_h}, {ref_crs}")

    bands = []
    band_names = []

    for source, paths in candidates.items():
        for path in paths:
            if not os.path.exists(path):
                print(f"  [SKIP] {os.path.basename(path)} — not found")
                continue
            try:
                with rasterio.open(path) as src:
                    for bi in range(1, src.count + 1):
                        data = src.read(bi)
                        # Reproject if needed
                        if src.crs != ref_crs or src.width != ref_w or src.height != ref_h:
                            dst_data = np.empty((ref_h, ref_w), dtype=np.float32)
                            reproject(data, dst_data, src_transform=src.transform, src_crs=src.crs,
                                      dst_transform=ref_transform, dst_crs=ref_crs,
                                      resampling=Resampling.bilinear)
                            data = dst_data
                        bands.append(data.astype(np.float32))
                        name = f"{source}_{os.path.splitext(os.path.basename(path))[0]}_b{bi}"
                        band_names.append(name)
                        print(f"  ✓ {name}")
            except Exception as e:
                print(f"  [WARN] {os.path.basename(path)}: {e}")

    if not bands:
        print("✗ No bands stacked"); sys.exit(1)

    # Write stack
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    profile = {"driver": "GTiff", "dtype": "float32", "width": ref_w, "height": ref_h,
               "count": len(bands), "crs": ref_crs, "transform": ref_transform}
    with rasterio.open(args.output, "w", **profile) as dst:
        for i, band in enumerate(bands):
            dst.write(band, i + 1)

    # Save metadata
    meta_path = args.output.replace(".tif", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump({"bands": band_names, "count": len(bands), "width": ref_w, "height": ref_h}, f, indent=2)

    print(f"\n✓ Stack saved: {args.output} ({len(bands)} bands)")
    print(f"✓ Metadata: {meta_path}")

if __name__ == "__main__":
    main()
