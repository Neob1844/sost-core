#!/usr/bin/env python3
"""Build Sentinel-1 SAR features for GeaSpirit Platform."""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import init_ee, get_bbox, download_ee_image, validate_tiff

def main():
    p = argparse.ArgumentParser(description="Build Sentinel-1 SAR features")
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2024-12-31")
    p.add_argument("--scale", type=int, default=30)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    if not args.output:
        args.output = os.path.expanduser(f"~/SOST/geaspirit/data/sentinel1/{args.pilot}_s1.tif")

    ee = init_ee()
    bbox = get_bbox(args.pilot)
    roi = ee.Geometry.Rectangle(bbox)

    print(f"→ Searching Sentinel-1 for {args.pilot}...")
    col = (ee.ImageCollection("COPERNICUS/S1_GRD")
           .filterBounds(roi)
           .filterDate(args.start, args.end)
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))

    count = col.size().getInfo()
    print(f"  Found {count} scenes")
    if count == 0:
        print("✗ No S1 data found"); sys.exit(1)

    vv = col.select("VV").median()
    vh = col.select("VH").median()
    ratio = vv.subtract(vh).rename("VV_VH_ratio")
    # GLCM texture on VV (int conversion required)
    vv_int = vv.add(30).multiply(100).toInt()
    glcm = vv_int.glcmTexture(size=3)
    variance = glcm.select("VV_var").rename("VV_variance")
    contrast = glcm.select("VV_contrast").rename("VV_contrast")

    image = vv.rename("VV").addBands(vh.rename("VH")).addBands(ratio).addBands(variance).addBands(contrast)

    print(f"→ Downloading S1 features (5 bands, {args.scale}m)...")
    ok = download_ee_image(image, bbox, args.output, args.scale)
    if ok and validate_tiff(args.output):
        print(f"✓ Saved: {args.output}")
    else:
        print("✗ Download failed"); sys.exit(1)

if __name__ == "__main__":
    main()
