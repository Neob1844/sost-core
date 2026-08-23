#!/usr/bin/env python3
"""List all defined AOIs and their data availability status."""
import argparse, os, json, glob


def check_file(path):
    return os.path.exists(path) and os.path.getsize(path) > 1000


def main():
    p = argparse.ArgumentParser(description="List GeaSpirit AOI inventory")
    p.add_argument("--aoi-dir", default=os.path.expanduser("~/SOST/geaspirit/data/aois"))
    p.add_argument("--data-dir", default=os.path.expanduser("~/SOST/geaspirit/data"))
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    aoi_files = sorted(glob.glob(os.path.join(args.aoi_dir, "*.json")))
    inventory = []

    for af in aoi_files:
        with open(af) as f:
            aoi = json.load(f)
        name = aoi["name"]

        # Check data availability
        status = {
            "name": name,
            "center": aoi["center"],
            "size_km": f"{aoi['width_km']}x{aoi['height_km']}",
            "area_km2": aoi["area_km2"],
            "has_stack": check_file(os.path.join(args.data_dir, "stack", f"{name}_global_stack.tif"))
                         or check_file(os.path.join(args.data_dir, f"{name}_stack.tif")),
            "has_labels": check_file(os.path.join(args.data_dir, "labels", f"{name}_labels_curated.csv"))
                          or check_file(os.path.join(args.data_dir, "mrds", f"{name}_mrds_curated.csv")),
            "has_geology": check_file(os.path.join(args.data_dir, "geology_maps", f"{name}_geology_stack.tif")),
            "has_geophysics": check_file(os.path.join(args.data_dir, "geophysics", f"{name}_geophysics_stack.tif"))
                              or check_file(os.path.join(args.data_dir, "geophysics", f"{name}_manual_geophysics_stack.tif")),
            "has_emit": check_file(os.path.join(args.data_dir, "emit", f"{name}_emit_stack.tif")),
            "notes": aoi.get("notes", ""),
        }
        inventory.append(status)

    # Also check legacy pilot zones
    for legacy in ["chuquicamata", "pilbara"]:
        if not any(s["name"] == legacy for s in inventory):
            has_stack = check_file(os.path.join(args.data_dir, f"{legacy}_stack.tif"))
            if has_stack:
                inventory.append({
                    "name": legacy,
                    "center": {"chuquicamata": [-22.3, -68.9], "pilbara": [-23.1, 119.2]}.get(legacy, [0, 0]),
                    "size_km": "50x50" if legacy == "chuquicamata" else "100x100",
                    "area_km2": 2500 if legacy == "chuquicamata" else 10000,
                    "has_stack": True,
                    "has_labels": check_file(os.path.join(args.data_dir, "mrds", f"{legacy}_mrds_curated.csv"))
                                  or check_file(os.path.join(args.data_dir, "mrds", "mrds_curated.csv")),
                    "has_geology": check_file(os.path.join(args.data_dir, "geology_maps", f"{legacy}_geology_stack.tif")),
                    "has_geophysics": False,
                    "has_emit": False,
                    "notes": "Legacy pilot zone",
                })

    # Print
    print(f"=== GeaSpirit AOI Inventory ({len(inventory)} zones) ===\n")
    for s in inventory:
        flags = ""
        flags += "S" if s["has_stack"] else "."
        flags += "L" if s["has_labels"] else "."
        flags += "G" if s["has_geology"] else "."
        flags += "P" if s["has_geophysics"] else "."
        flags += "E" if s["has_emit"] else "."
        print(f"  [{flags}] {s['name']:25s} {str(s['center']):30s} {s['size_km']:>10s} {s['area_km2']:>8.0f} km²")

    print(f"\n  Legend: S=stack L=labels G=geology P=geophysics E=EMIT")

    # Save
    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "aoi_inventory.json"), "w") as f:
        json.dump(inventory, f, indent=2)

    md = f"# GeaSpirit AOI Inventory\n\n"
    md += "| AOI | Center | Size | Stack | Labels | Geology | Geophys | EMIT |\n"
    md += "|-----|--------|------|-------|--------|---------|---------|------|\n"
    for s in inventory:
        yn = lambda v: "YES" if v else "-"
        md += f"| {s['name']} | {s['center']} | {s['size_km']} | {yn(s['has_stack'])} | "
        md += f"{yn(s['has_labels'])} | {yn(s['has_geology'])} | {yn(s['has_geophysics'])} | {yn(s['has_emit'])} |\n"

    with open(os.path.join(args.output, "aoi_inventory.md"), "w") as f:
        f.write(md)
    print(f"\n  Saved: aoi_inventory.json + .md")


if __name__ == "__main__":
    main()
