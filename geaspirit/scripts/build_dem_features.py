#!/usr/bin/env python3
"""Build DEM-derived features for GeaSpirit Platform."""
import argparse, os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import init_ee, get_bbox, download_ee_image, validate_tiff

def main():
    p = argparse.ArgumentParser(description="Build DEM features")
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--scale", type=int, default=30)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    if not args.output:
        args.output = os.path.expanduser(f"~/SOST/geaspirit/data/dem/{args.pilot}_dem.tif")

    ee = init_ee()
    bbox = get_bbox(args.pilot)

    print(f"→ Building DEM features for {args.pilot}...")
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    slope = ee.Terrain.slope(dem).rename("slope")
    aspect = ee.Terrain.aspect(dem)
    sin_asp = aspect.multiply(math.pi / 180).sin().rename("sin_aspect")
    cos_asp = aspect.multiply(math.pi / 180).cos().rename("cos_aspect")
    # TPI: elevation - focal mean (300m kernel ≈ 10 pixels at 30m)
    focal_mean = dem.focal_mean(radius=10, kernelType="circle", units="pixels")
    tpi = dem.subtract(focal_mean).rename("tpi")
    # Ruggedness: focal stdev
    rugged = dem.reduceNeighborhood(reducer=ee.Reducer.stdDev(),
                                    kernel=ee.Kernel.circle(10, "pixels")).rename("ruggedness")

    image = dem.rename("elevation").addBands(slope).addBands(sin_asp).addBands(cos_asp).addBands(tpi).addBands(rugged)

    print(f"→ Downloading DEM features (6 bands, {args.scale}m)...")
    ok = download_ee_image(image, bbox, args.output, args.scale)
    if ok and validate_tiff(args.output):
        print(f"✓ Saved: {args.output}")
    else:
        print("✗ Download failed"); sys.exit(1)

if __name__ == "__main__":
    main()
