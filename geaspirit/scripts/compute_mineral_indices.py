#!/usr/bin/env python3
"""Compute mineral indices from Sentinel-2 GeoTIFF.

Usage: python3 scripts/compute_mineral_indices.py --input data/sentinel2/chuquicamata_s2.tif --output data/indices/
"""
import argparse
import os
import sys
import numpy as np

def main():
    parser = argparse.ArgumentParser(description="Compute mineral indices from Sentinel-2")
    parser.add_argument("--input", required=True, help="Sentinel-2 GeoTIFF path")
    parser.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/indices"))
    args = parser.parse_args()

    try:
        import rasterio
        from rasterio.transform import from_bounds
    except ImportError:
        print("Install rasterio: pip install rasterio")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    print(f"Reading {args.input}...")
    with rasterio.open(args.input) as src:
        # Sentinel-2 bands order: B2,B3,B4,B5,B6,B7,B8,B8A,B11,B12
        bands = src.read()
        profile = src.profile.copy()
        profile.update(count=1, dtype='float32')

        band_map = {
            "B2": bands[0], "B3": bands[1], "B4": bands[2],
            "B5": bands[3], "B6": bands[4], "B7": bands[5],
            "B8": bands[6], "B8A": bands[7], "B11": bands[8], "B12": bands[9],
        }

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from geaspirit.indices import iron_oxide, clay_hydroxyl, ferrous_iron, laterite, ndvi

    indices = {
        "iron_oxide": iron_oxide(band_map["B4"], band_map["B2"]),
        "clay_hydroxyl": clay_hydroxyl(band_map["B11"], band_map["B12"]),
        "ferrous_iron": ferrous_iron(band_map["B11"], band_map["B8A"]),
        "laterite": laterite(band_map["B4"], band_map["B3"]),
        "ndvi": ndvi(band_map["B8"], band_map["B4"]),
    }

    zone = os.path.splitext(os.path.basename(args.input))[0]
    for name, data in indices.items():
        out_path = os.path.join(args.output, f"{zone}_{name}.tif")
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data.astype(np.float32), 1)
        print(f"  ✓ {out_path}")

        # Quicklook PNG
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 1, figsize=(10, 8))
            valid = data[~np.isnan(data)]
            if len(valid) > 0:
                vmin, vmax = np.percentile(valid, [2, 98])
                ax.imshow(data, cmap="hot", vmin=vmin, vmax=vmax)
            ax.set_title(f"{name.upper()} — {zone}")
            ax.axis("off")
            png_path = os.path.join(args.output, f"{zone}_{name}.png")
            plt.savefig(png_path, dpi=150, bbox_inches="tight")
            plt.close()
            print(f"  ✓ {png_path}")
        except Exception as e:
            print(f"  ⚠ PNG failed: {e}")

    print(f"\nDone. {len(indices)} indices computed.")

if __name__ == "__main__":
    main()
