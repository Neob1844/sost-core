#!/usr/bin/env python3
"""Build a satellite feature stack for any AOI on Earth.

Reads an AOI definition JSON and downloads/generates all available layers
via Google Earth Engine, then stacks them into a single aligned GeoTIFF.
"""
import argparse, os, sys, json, math
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def load_aoi(name, aoi_dir):
    """Load AOI definition from JSON."""
    path = os.path.join(aoi_dir, f"{name}.json")
    if not os.path.exists(path):
        print(f"  ! AOI not found: {path}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def main():
    p = argparse.ArgumentParser(description="Build global AOI satellite stack")
    p.add_argument("--aoi", required=True, help="AOI name")
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    p.add_argument("--start", default="2023-06-01")
    p.add_argument("--end", default="2024-09-30")
    p.add_argument("--scale", type=int, default=30, help="Resolution in meters")
    p.add_argument("--max-cloud", type=int, default=15)
    p.add_argument("--output-dir", default=os.path.expanduser("~/SOST/geaspirit/data/stack"))
    args = p.parse_args()

    aoi = load_aoi(args.aoi, args.aoi_dir)
    bbox = aoi["bbox"]
    name = aoi["name"]

    # Auto-adjust scale for large AOIs to stay under GEE limits
    area_km2 = aoi["area_km2"]
    if area_km2 > 5000 and args.scale < 60:
        args.scale = 60
        print(f"  Auto-adjusted scale to {args.scale}m for large AOI ({area_km2} km²)")

    print(f"=== Building Global AOI Stack: {name} ===")
    print(f"  BBox: {bbox}")
    print(f"  Scale: {args.scale}m, Date: {args.start} to {args.end}")

    import ee
    from geaspirit.ee_download import download_ee_image, validate_tiff

    ee.Initialize(project="ee-sost-geaspirit")
    roi = ee.Geometry.Rectangle(bbox)

    os.makedirs(args.output_dir, exist_ok=True)
    tmp_dir = os.path.join(args.output_dir, f"_tmp_{name}")
    os.makedirs(tmp_dir, exist_ok=True)

    layers = {}

    # --- Sentinel-2 median composite ---
    print("  [S2] Sentinel-2 composite...")
    s2_bands = ["B2","B3","B4","B5","B6","B7","B8","B8A","B11","B12"]
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(roi).filterDate(args.start, args.end)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", args.max_cloud))
          .select(s2_bands).median().clip(roi))
    s2_path = os.path.join(tmp_dir, "s2.tif")
    if download_ee_image(s2, bbox, s2_path, args.scale):
        layers["s2"] = s2_path

    # --- Mineral indices from S2 ---
    print("  [IDX] Mineral indices...")
    b4 = s2.select("B4").toFloat()
    b2 = s2.select("B2").toFloat()
    b3 = s2.select("B3").toFloat()
    b8 = s2.select("B8").toFloat()
    b8a = s2.select("B8A").toFloat()
    b11 = s2.select("B11").toFloat()
    b12 = s2.select("B12").toFloat()
    indices = (b4.divide(b2).rename("iron_oxide")
               .addBands(b11.divide(b12).rename("clay_hydroxyl"))
               .addBands(b11.divide(b8a).rename("ferrous_iron"))
               .addBands(b4.divide(b3).rename("laterite"))
               .addBands(b8.subtract(b4).divide(b8.add(b4)).rename("ndvi")))
    idx_path = os.path.join(tmp_dir, "indices.tif")
    if download_ee_image(indices, bbox, idx_path, args.scale):
        layers["indices"] = idx_path

    # --- Sentinel-1 SAR ---
    print("  [SAR] Sentinel-1...")
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterBounds(roi).filterDate(args.start, args.end)
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation","VV"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation","VH"))
          .select(["VV","VH"]))
    if s1.size().getInfo() > 0:
        vv = s1.select("VV").median()
        vh = s1.select("VH").median()
        ratio = vv.divide(vh).rename("VV_VH_ratio")
        texture = vv.reduceNeighborhood(reducer=ee.Reducer.variance(),
                                         kernel=ee.Kernel.circle(3,"pixels")).rename("VV_var")
        sar = vv.rename("VV").addBands(vh.rename("VH")).addBands(ratio).addBands(texture)
        sar_path = os.path.join(tmp_dir, "sar.tif")
        if download_ee_image(sar.clip(roi), bbox, sar_path, args.scale):
            layers["sar"] = sar_path

    # --- DEM ---
    print("  [DEM] Copernicus DEM...")
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    slope = ee.Terrain.slope(dem).rename("slope")
    aspect = ee.Terrain.aspect(dem)
    sin_asp = aspect.multiply(math.pi/180).sin().rename("sin_aspect")
    cos_asp = aspect.multiply(math.pi/180).cos().rename("cos_aspect")
    tpi = dem.subtract(dem.focal_mean(radius=10,kernelType="circle",units="pixels")).rename("tpi")
    rugged = dem.reduceNeighborhood(reducer=ee.Reducer.stdDev(),
                                    kernel=ee.Kernel.circle(10,"pixels")).rename("ruggedness")
    dem_stack = (dem.rename("elevation").addBands(slope).addBands(sin_asp)
                 .addBands(cos_asp).addBands(tpi).addBands(rugged))
    dem_path = os.path.join(tmp_dir, "dem.tif")
    if download_ee_image(dem_stack.clip(roi), bbox, dem_path, args.scale):
        layers["dem"] = dem_path

    # --- Landsat thermal ---
    print("  [LST] Landsat thermal...")
    lst_coll = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
                .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
                .filterBounds(roi).filterDate(args.start, args.end)
                .filter(ee.Filter.lt("CLOUD_COVER", 20))
                .map(lambda img: img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15).rename("LST")))
    if lst_coll.size().getInfo() > 0:
        lst_median = lst_coll.median().rename("LST_median")
        lst_p90 = lst_coll.reduce(ee.Reducer.percentile([90])).rename("LST_p90")
        lst_mean = lst_coll.mean()
        lst_std = lst_coll.reduce(ee.Reducer.stdDev())
        lst_z = lst_median.subtract(lst_mean).divide(lst_std.add(0.01)).rename("LST_zscore")
        thermal = lst_median.addBands(lst_p90).addBands(lst_z)
        lst_path = os.path.join(tmp_dir, "thermal.tif")
        if download_ee_image(thermal.clip(roi), bbox, lst_path, args.scale):
            layers["thermal"] = lst_path

    # --- Stack all layers ---
    print(f"\n  Stacking {len(layers)} layer groups...")
    import rasterio
    from rasterio.warp import reproject, Resampling

    if not layers:
        print("  ! No layers downloaded — aborting")
        return

    # Use indices as reference grid (or first available)
    ref_key = "indices" if "indices" in layers else list(layers.keys())[0]
    with rasterio.open(layers[ref_key]) as ref:
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_w, ref_h = ref.width, ref.height
        ref_profile = ref.profile.copy()

    all_bands = []
    band_names = []
    band_name_map = {
        "indices": ["iron_oxide","clay_hydroxyl","ferrous_iron","laterite","ndvi"],
        "sar": ["VV","VH","VV_VH_ratio","VV_variance"],
        "dem": ["elevation","slope","sin_aspect","cos_aspect","tpi","ruggedness"],
        "thermal": ["LST_median","LST_p90","LST_zscore"],
    }

    for key in ["indices", "sar", "dem", "thermal"]:
        if key not in layers:
            continue
        with rasterio.open(layers[key]) as src:
            for bi in range(1, src.count + 1):
                data = src.read(bi)
                if src.width != ref_w or src.height != ref_h:
                    dst = np.empty((ref_h, ref_w), dtype=np.float32)
                    reproject(source=data, destination=dst,
                              src_transform=src.transform, src_crs=src.crs,
                              dst_transform=ref_transform, dst_crs=ref_crs,
                              resampling=Resampling.bilinear)
                    data = dst
                all_bands.append(data.astype(np.float32))
                names = band_name_map.get(key, [])
                bname = names[bi-1] if bi-1 < len(names) else f"{key}_b{bi}"
                band_names.append(bname)

    stack = np.stack(all_bands)
    out_path = os.path.join(args.output_dir, f"{name}_global_stack.tif")
    ref_profile.update(count=stack.shape[0], dtype="float32", compress="lzw")
    with rasterio.open(out_path, "w", **ref_profile) as dst:
        dst.write(stack)

    meta = {
        "aoi": name,
        "bbox": bbox,
        "bands": band_names,
        "n_bands": len(band_names),
        "width": ref_w,
        "height": ref_h,
        "scale_m": args.scale,
        "layers_downloaded": list(layers.keys()),
        "date_range": [args.start, args.end],
    }
    meta_path = out_path.replace(".tif", "_metadata.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Cleanup tmp
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    valid = np.all(np.isfinite(stack), axis=0).sum()
    total = ref_h * ref_w
    print(f"\n  Stack: {out_path}")
    print(f"  {ref_w}x{ref_h}, {len(band_names)} bands, {valid}/{total} valid ({valid/total*100:.1f}%)")


if __name__ == "__main__":
    main()
