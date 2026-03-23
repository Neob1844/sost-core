#!/usr/bin/env python3
"""Phase 4A Priority 4 — Integrate open geophysics for Pilbara.

Downloads and aligns Geoscience Australia open geophysics:
- Aeromagnetics TMI (Total Magnetic Intensity)
- Radiometrics (K, Th, U)
- Gravity (Bouguer anomaly)

Uses GA's WCS (Web Coverage Service) or direct grid downloads.
All data is CC-BY 4.0.
"""
import argparse, os, sys, json, tempfile
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES, HALF_DEG

# Geoscience Australia WCS endpoints for national grids
# These are the authoritative endpoints for open geophysics data
GA_WCS = {
    "magnetics_tmi": {
        "name": "Total Magnetic Intensity (TMI) Anomaly",
        "wcs_url": "https://services.ga.gov.au/gis/services/Total_Magnetic_Intensity/MapServer/WCSServer",
        "coverage_id": "1",
        "resolution_m": 80,
        "license": "CC-BY 4.0",
        "source": "Geoscience Australia — 6th Edition Magnetic Anomaly Map",
        "band_names": ["magnetic_tmi"],
    },
    "radiometrics_k": {
        "name": "Radiometrics — Potassium (K%)",
        "wcs_url": "https://services.ga.gov.au/gis/services/Radmap_v4_2019_Filtered_pctK/MapServer/WCSServer",
        "coverage_id": "1",
        "resolution_m": 100,
        "license": "CC-BY 4.0",
        "source": "Geoscience Australia — Radiometric Map of Australia v4 2019",
        "band_names": ["radiometric_K"],
    },
    "radiometrics_th": {
        "name": "Radiometrics — Thorium (eTh ppm)",
        "wcs_url": "https://services.ga.gov.au/gis/services/Radmap_v4_2019_Filtered_eTh/MapServer/WCSServer",
        "coverage_id": "1",
        "resolution_m": 100,
        "license": "CC-BY 4.0",
        "source": "Geoscience Australia — Radiometric Map of Australia v4 2019",
        "band_names": ["radiometric_Th"],
    },
    "radiometrics_u": {
        "name": "Radiometrics — Uranium (eU ppm)",
        "wcs_url": "https://services.ga.gov.au/gis/services/Radmap_v4_2019_Filtered_eU/MapServer/WCSServer",
        "coverage_id": "1",
        "resolution_m": 100,
        "license": "CC-BY 4.0",
        "source": "Geoscience Australia — Radiometric Map of Australia v4 2019",
        "band_names": ["radiometric_U"],
    },
    "gravity_bouguer": {
        "name": "Bouguer Gravity Anomaly",
        "wcs_url": "https://services.ga.gov.au/gis/services/Bouguer_Gravity_Anomaly/MapServer/WCSServer",
        "coverage_id": "1",
        "resolution_m": 800,
        "license": "CC-BY 4.0",
        "source": "Geoscience Australia — Gravity Anomaly Map",
        "band_names": ["gravity_bouguer"],
    },
}


def download_wcs_coverage(wcs_url, coverage_id, bbox, output_path, target_crs="EPSG:4326"):
    """Download a WCS coverage for a given bounding box."""
    import requests
    min_lon, min_lat, max_lon, max_lat = bbox

    # Try WCS GetCoverage request
    params = {
        "SERVICE": "WCS",
        "VERSION": "1.0.0",
        "REQUEST": "GetCoverage",
        "COVERAGE": coverage_id,
        "CRS": target_crs,
        "BBOX": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "FORMAT": "GeoTIFF",
        "WIDTH": "500",
        "HEIGHT": "500",
    }

    try:
        resp = requests.get(wcs_url, params=params, timeout=120, stream=True)
        if resp.status_code == 200 and resp.headers.get('content-type', '').startswith(('image/', 'application/octet')):
            with open(output_path, 'wb') as f:
                for chunk in resp.iter_content(1024*1024):
                    f.write(chunk)
            size_mb = os.path.getsize(output_path) / (1024*1024)
            if size_mb > 0.01:
                return True, f"Downloaded {size_mb:.2f}MB"
            else:
                os.unlink(output_path)
                return False, "Response too small — may be error XML"
        else:
            # Try to read error
            err = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
            return False, f"WCS error: {err}"
    except Exception as e:
        return False, f"Request failed: {e}"


def download_wms_as_geotiff(wms_url, layer, bbox, output_path, width=1000, height=1000):
    """Fallback: download WMS GetMap as image, georeference manually."""
    import requests

    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "SRS": "EPSG:4326",
        "BBOX": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/tiff",
    }

    try:
        resp = requests.get(wms_url, params=params, timeout=120, stream=True)
        if resp.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in resp.iter_content(1024*1024):
                    f.write(chunk)
            if os.path.getsize(output_path) > 1000:
                return True, "Downloaded via WMS"
        return False, f"WMS failed: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"WMS request failed: {e}"


def align_to_reference(src_path, ref_path, out_path):
    """Reproject and resample a raster to match reference grid."""
    import rasterio
    from rasterio.warp import reproject, Resampling

    with rasterio.open(ref_path) as ref:
        ref_transform = ref.transform
        ref_crs = ref.crs
        ref_w, ref_h = ref.width, ref.height
        ref_profile = ref.profile.copy()

    with rasterio.open(src_path) as src:
        src_data = src.read()
        src_transform = src.transform
        src_crs = src.crs

    dst_data = np.zeros((src_data.shape[0], ref_h, ref_w), dtype=np.float32)
    for band in range(src_data.shape[0]):
        reproject(
            source=src_data[band],
            destination=dst_data[band],
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=ref_transform,
            dst_crs=ref_crs,
            resampling=Resampling.bilinear,
        )

    ref_profile.update(count=dst_data.shape[0], dtype='float32', compress='lzw')
    with rasterio.open(out_path, 'w', **ref_profile) as dst:
        dst.write(dst_data)
    return True


def main():
    p = argparse.ArgumentParser(description="Build Pilbara geophysics stack from GA open data")
    p.add_argument("--ref-stack", default=os.path.expanduser("~/SOST/geaspirit/data/pilbara_stack.tif"),
                   help="Reference satellite stack for grid alignment")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/data/geophysics"))
    p.add_argument("--reports", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    import rasterio

    zone = ZONES["pilbara"]
    lat_c, lon_c = zone["center"]
    bbox = [lon_c - HALF_DEG, lat_c - HALF_DEG, lon_c + HALF_DEG, lat_c + HALF_DEG]

    print(f"=== Pilbara Open Geophysics Integration ===")
    print(f"  AOI: {bbox}")

    # Check reference stack
    has_ref = os.path.exists(args.ref_stack)
    if has_ref:
        with rasterio.open(args.ref_stack) as ref:
            ref_h, ref_w = ref.height, ref.width
            print(f"  Reference stack: {ref_w}x{ref_h}")
    else:
        print(f"  ! No reference stack — will save raw downloads only")

    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.reports, exist_ok=True)
    tmp_dir = os.path.join(args.output, "_raw")
    os.makedirs(tmp_dir, exist_ok=True)

    results = {}
    aligned_bands = []
    all_band_names = []

    for layer_key, layer_info in GA_WCS.items():
        print(f"\n  [{layer_key}] {layer_info['name']}...")
        raw_path = os.path.join(tmp_dir, f"{layer_key}_raw.tif")

        # Try WCS download
        ok, msg = download_wcs_coverage(
            layer_info["wcs_url"], layer_info["coverage_id"],
            bbox, raw_path
        )

        if not ok:
            # Try WMS fallback
            wms_url = layer_info["wcs_url"].replace("WCSServer", "WMSServer")
            ok, msg = download_wms_as_geotiff(wms_url, "0", bbox, raw_path)

        if ok and os.path.exists(raw_path):
            try:
                with rasterio.open(raw_path) as src:
                    raw_data = src.read()
                    print(f"    Raw: {src.width}x{src.height}, {src.count} bands, CRS={src.crs}")

                if has_ref:
                    aligned_path = os.path.join(tmp_dir, f"{layer_key}_aligned.tif")
                    align_to_reference(raw_path, args.ref_stack, aligned_path)
                    with rasterio.open(aligned_path) as al:
                        aligned_data = al.read()
                        aligned_bands.append(aligned_data)
                        all_band_names.extend(layer_info["band_names"])
                        print(f"    Aligned: {al.width}x{al.height}")

                results[layer_key] = {
                    "status": "OK",
                    "name": layer_info["name"],
                    "resolution_m": layer_info["resolution_m"],
                    "license": layer_info["license"],
                    "source": layer_info["source"],
                    "band_names": layer_info["band_names"],
                    "message": msg,
                }
            except Exception as e:
                results[layer_key] = {
                    "status": "PARSE_ERROR",
                    "name": layer_info["name"],
                    "error": str(e),
                }
                print(f"    ! Parse error: {e}")
        else:
            results[layer_key] = {
                "status": "DOWNLOAD_FAILED",
                "name": layer_info["name"],
                "error": msg,
            }
            print(f"    ! Failed: {msg}")

    # Stack aligned bands
    ok_count = sum(1 for r in results.values() if r["status"] == "OK")
    print(f"\n  Successfully downloaded: {ok_count}/{len(GA_WCS)} layers")

    if aligned_bands and has_ref:
        stack = np.concatenate(aligned_bands, axis=0)

        # Add availability band
        avail = np.ones((1, stack.shape[1], stack.shape[2]), dtype=np.float32)
        avail[0, np.all(stack == 0, axis=0)] = 0
        stack = np.concatenate([stack, avail], axis=0)
        all_band_names.append("mapped_geophysics_available")

        out_path = os.path.join(args.output, "pilbara_geophysics_stack.tif")
        with rasterio.open(args.ref_stack) as ref:
            profile = ref.profile.copy()
        profile.update(count=stack.shape[0], dtype='float32', compress='lzw')
        with rasterio.open(out_path, 'w', **profile) as dst:
            dst.write(stack)
        print(f"  Saved stack: {out_path} ({stack.shape[0]} bands)")
    elif not aligned_bands:
        print(f"  ! No layers aligned — creating empty placeholder")
        # Create minimal placeholder so pipeline doesn't break
        if has_ref:
            with rasterio.open(args.ref_stack) as ref:
                profile = ref.profile.copy()
                h, w = ref.height, ref.width
            placeholder = np.zeros((1, h, w), dtype=np.float32)
            out_path = os.path.join(args.output, "pilbara_geophysics_stack.tif")
            profile.update(count=1, dtype='float32', compress='lzw')
            with rasterio.open(out_path, 'w', **profile) as dst:
                dst.write(placeholder)
            all_band_names = ["geophysics_placeholder"]

    # Metadata
    meta = {
        "pilot": "pilbara",
        "bands": all_band_names,
        "n_bands": len(all_band_names),
        "layers_attempted": len(GA_WCS),
        "layers_success": ok_count,
        "results": results,
    }
    with open(os.path.join(args.output, "pilbara_geophysics_metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # Report
    md = "# Pilbara Open Geophysics Report\n\n"
    md += f"## Summary\n- Layers attempted: {len(GA_WCS)}\n- Successful: {ok_count}\n\n"
    md += "## Per-Layer Status\n\n"
    md += "| Layer | Status | Resolution | Source |\n|-------|--------|------------|--------|\n"
    for key, res in results.items():
        md += f"| {res['name']} | **{res['status']}** | "
        md += f"{res.get('resolution_m', '?')}m | {res.get('source', '?')} |\n"
    md += "\n## Notes\n"
    md += "- All successful layers are CC-BY 4.0 (Geoscience Australia)\n"
    md += "- Layers are reprojected and resampled to match the 30m satellite grid\n"
    for key, res in results.items():
        if res["status"] != "OK":
            md += f"- **{res['name']}**: {res.get('error', 'unknown error')}\n"
    md += "\n## Fallback Strategy\n"
    md += "If WCS/WMS downloads fail, datasets can be manually downloaded from:\n"
    md += "- https://ecat.ga.gov.au (search for TMI, radiometrics, gravity)\n"
    md += "- https://portal.ga.gov.au (interactive map + download)\n"

    with open(os.path.join(args.reports, "pilbara_geophysics_report.md"), "w") as f:
        f.write(md)
    print(f"  Report: pilbara_geophysics_report.md")


if __name__ == "__main__":
    main()
