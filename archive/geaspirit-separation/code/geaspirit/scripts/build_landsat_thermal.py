#!/usr/bin/env python3
"""Build Landsat thermal features for GeaSpirit Platform."""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import init_ee, get_bbox, download_ee_image, validate_tiff

def main():
    p = argparse.ArgumentParser(description="Build Landsat thermal features")
    p.add_argument("--pilot", default="chuquicamata")
    p.add_argument("--start", default="2023-01-01")
    p.add_argument("--end", default="2024-12-31")
    p.add_argument("--scale", type=int, default=30)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    if not args.output:
        args.output = os.path.expanduser(f"~/SOST/geaspirit/data/landsat/{args.pilot}_lst.tif")

    ee = init_ee()
    bbox = get_bbox(args.pilot)
    roi = ee.Geometry.Rectangle(bbox)

    print(f"→ Searching Landsat 8/9 for {args.pilot}...")
    def mask_clouds(img):
        qa = img.select("QA_PIXEL")
        return img.updateMask(qa.bitwiseAnd(1 << 3).eq(0))  # cloud bit

    l8 = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(roi)
          .filterDate(args.start, args.end).filter(ee.Filter.lt("CLOUD_COVER", 20)).map(mask_clouds))
    l9 = (ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").filterBounds(roi)
          .filterDate(args.start, args.end).filter(ee.Filter.lt("CLOUD_COVER", 20)).map(mask_clouds))
    col = l8.merge(l9)

    count = col.size().getInfo()
    print(f"  Found {count} scenes")
    if count == 0:
        print("✗ No Landsat thermal data found"); sys.exit(1)

    # ST_B10 is surface temperature (Kelvin * 0.00341802 + 149)
    lst = col.select("ST_B10").map(lambda img: img.multiply(0.00341802).add(149))
    median_lst = lst.median().rename("lst_median")
    p90_lst = lst.reduce(ee.Reducer.percentile([90])).rename("lst_p90")
    mean = lst.reduce(ee.Reducer.mean())
    std = lst.reduce(ee.Reducer.stdDev())
    zscore = median_lst.subtract(mean).divide(std.max(0.01)).rename("lst_zscore")

    image = median_lst.addBands(p90_lst).addBands(zscore)

    print(f"→ Downloading thermal features (3 bands, {args.scale}m)...")
    ok = download_ee_image(image, bbox, args.output, args.scale)
    if ok and validate_tiff(args.output):
        print(f"✓ Saved: {args.output}")
    else:
        print("✗ Download failed"); sys.exit(1)

if __name__ == "__main__":
    main()
