#!/usr/bin/env python3
"""Priority 6 — Inventory of open geophysics data for all pilot zones.

Documents available open/free geophysical datasets:
- Magnetics (aeromagnetic surveys)
- Gravity (Bouguer anomaly, free-air)
- Radiometrics (K, Th, U)
- Airborne surveys

For each AOI: source, format, resolution, license, coverage, integrability.
"""
import argparse, os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geaspirit.ee_download import ZONES

# Known open geophysics sources (curated from research)
INVENTORY = {
    "chuquicamata": {
        "zone": "Chuquicamata, Chile (-22.3S, -68.9W)",
        "geology_survey": "SERNAGEOMIN (Servicio Nacional de Geologia y Mineria)",
        "datasets": [
            {
                "type": "Geological Map (WMS)",
                "source": "SERNAGEOMIN",
                "url": "http://ogc.sernageomin.cl/cgi-bin/SNGM_Bedrock_Geology/wms",
                "format": "WMS (OGC)",
                "resolution": "1:1,000,000",
                "license": "Free via OneGeology (personal/non-commercial)",
                "coverage": "All continental Chile",
                "integrable": True,
                "notes": "Lithostratigraphy + structural layers available",
            },
            {
                "type": "Geological Map (detailed)",
                "source": "SERNAGEOMIN",
                "url": "https://tiendadigital.sernageomin.cl",
                "format": "Shapefile + PDF",
                "resolution": "1:100,000 (Carta Calama 2018)",
                "license": "PAID — must purchase from SERNAGEOMIN digital store",
                "coverage": "22°00'-22°30'S, 69°00'-68°30'W (covers Chuquicamata directly)",
                "integrable": False,
                "notes": "Best available but requires purchase. SSL cert sometimes expired.",
            },
            {
                "type": "Aeromagnetics",
                "source": "SERNAGEOMIN",
                "url": "https://portalgeomin.sernageomin.cl",
                "format": "Grid/raster (proprietary format)",
                "resolution": "Varies by survey (~200m line spacing)",
                "license": "Restricted — may require institutional access or purchase",
                "coverage": "Partial coverage of northern Chile",
                "integrable": False,
                "notes": "Chile has extensive aeromagnetic surveys but access is limited. "
                         "Some academic datasets may be available through collaboration.",
            },
            {
                "type": "Gravity",
                "source": "BGI (Bureau Gravimetrique International) / SERNAGEOMIN",
                "url": "http://bgi.obs-mip.fr",
                "format": "Point data / Grid",
                "resolution": "Station-based (~5-10km)",
                "license": "Academic access via BGI; Chilean data may be restricted",
                "coverage": "Sparse in Atacama region",
                "integrable": False,
                "notes": "Bouguer anomaly grids from satellite (GOCE/GRACE) available globally "
                         "at ~10km resolution but too coarse for prospect-scale work.",
            },
        ],
        "recommendation": "WMS geological map is usable now. Aeromagnetics and gravity "
                          "require institutional access. Satellite gravity (GOCE) too coarse.",
    },

    "pilbara": {
        "zone": "Pilbara, Western Australia (-22.0S, 118.0E)",
        "geology_survey": "Geological Survey of Western Australia (GSWA) / Geoscience Australia (GA)",
        "datasets": [
            {
                "type": "Geological Map (national)",
                "source": "Geoscience Australia",
                "url": "https://d28rz98at9flks.cloudfront.net/74619/74619_1M_shapefiles.zip",
                "format": "Shapefile (direct download)",
                "resolution": "1:1,000,000",
                "license": "CC-BY 4.0 (fully open)",
                "coverage": "All Australia",
                "integrable": True,
                "notes": "Excellent: lithology polygons, stratigraphic nomenclature, age. "
                         "Directly downloadable. Also available as WMS.",
            },
            {
                "type": "Geological Map (state, detailed)",
                "source": "GSWA / DMIRS",
                "url": "https://dasc.dmirs.wa.gov.au/",
                "format": "Shapefile / Geodatabase",
                "resolution": "1:100,000",
                "license": "CC-BY 4.0",
                "coverage": "Pilbara well-mapped at 1:100K",
                "integrable": True,
                "notes": "BEST SOURCE. World-class open geology data. "
                         "Lithology, structures, faults, mineral occurrences. "
                         "Download via DASC portal or GeoVIEW.WA.",
            },
            {
                "type": "Aeromagnetics (TMI)",
                "source": "Geoscience Australia",
                "url": "https://ecat.ga.gov.au/geonetwork/srv/eng/catalog.search#/metadata/89762",
                "format": "GeoTIFF / ERS Grid",
                "resolution": "~80m (compiled grid from multiple surveys)",
                "license": "CC-BY 4.0",
                "coverage": "All Australia (6th edition magnetic anomaly map)",
                "integrable": True,
                "notes": "EXCELLENT. Total Magnetic Intensity (TMI) anomaly grid. "
                         "80m resolution suitable for prospect-scale work. "
                         "Directly integrable as raster feature.",
            },
            {
                "type": "Gravity (Bouguer)",
                "source": "Geoscience Australia",
                "url": "https://ecat.ga.gov.au/geonetwork/srv/eng/catalog.search#/metadata/101104",
                "format": "GeoTIFF / ERS Grid",
                "resolution": "~800m (onshore Bouguer anomaly grid)",
                "license": "CC-BY 4.0",
                "coverage": "All onshore Australia",
                "integrable": True,
                "notes": "Bouguer anomaly grid. 800m resolution is coarser than magnetics "
                         "but still valuable for regional structural mapping.",
            },
            {
                "type": "Radiometrics (K, Th, U)",
                "source": "Geoscience Australia",
                "url": "https://ecat.ga.gov.au/geonetwork/srv/eng/catalog.search#/metadata/83855",
                "format": "GeoTIFF / ERS Grid",
                "resolution": "~100m",
                "license": "CC-BY 4.0",
                "coverage": "All Australia",
                "integrable": True,
                "notes": "Potassium, Thorium, Uranium dose rate grids. "
                         "Excellent for alteration mapping and lithology discrimination.",
            },
        ],
        "recommendation": "Pilbara has WORLD-CLASS open geophysics. All datasets are CC-BY 4.0. "
                          "Priority integration: (1) aeromagnetics TMI, (2) radiometrics K/Th/U, "
                          "(3) gravity Bouguer, (4) GSWA 1:100K geology.",
    },

    "zambia": {
        "zone": "Zambia Copperbelt (-12.8S, 28.2E)",
        "geology_survey": "Geological Survey Department (Ministry of Mines)",
        "datasets": [
            {
                "type": "Geological Map (continental)",
                "source": "CGMW-BRGM",
                "url": "https://www.ccgm.org/en/product/geological-map-of-africa-sig/",
                "format": "Geodatabase",
                "resolution": "1:10,000,000",
                "license": "Requires signed license agreement — NOT truly open",
                "coverage": "All Africa",
                "integrable": False,
                "notes": "Very coarse (1:10M). Limited value for prospect-scale work. "
                         "License process is slow.",
            },
            {
                "type": "Geological Map (hydrogeology)",
                "source": "BGS Africa Groundwater Atlas",
                "url": "https://africangroundwateratlas.org/downloadGIS.html",
                "format": "Shapefile",
                "resolution": "1:5,000,000",
                "license": "Free download",
                "coverage": "Zambia national",
                "integrable": True,
                "notes": "Very coarse (1:5M). Hydrogeology-focused but includes basic "
                         "lithology/geology polygons. Better than nothing.",
            },
            {
                "type": "Mineral Occurrences",
                "source": "USGS Africa Mineral Industries GIS",
                "url": "https://doi.org/10.5066/P97EQWXP",
                "format": "Geodatabase + Shapefiles",
                "resolution": "Point data",
                "license": "Public domain (US Government)",
                "coverage": "54 African countries including Zambia",
                "integrable": True,
                "notes": "500+ sediment-hosted Cu deposit locations in Copperbelt. "
                         "Mineral production, exploration sites, resource tracts.",
            },
            {
                "type": "Aeromagnetics",
                "source": "Zambia Geological Survey",
                "url": "Not available online",
                "format": "Unknown",
                "resolution": "Unknown",
                "license": "Not publicly available",
                "coverage": "Partial",
                "integrable": False,
                "notes": "Historical airborne surveys exist but are not digitally available. "
                         "Would require institutional collaboration.",
            },
            {
                "type": "Gravity",
                "source": "Satellite only (GOCE/GRACE)",
                "url": "http://bgi.obs-mip.fr",
                "format": "Grid",
                "resolution": "~10km (satellite-derived)",
                "license": "Free (satellite data)",
                "coverage": "Global",
                "integrable": False,
                "notes": "Too coarse for prospect-scale work. No ground-based open gravity "
                         "data available for Zambia Copperbelt.",
            },
        ],
        "recommendation": "Zambia has the WORST open geophysics coverage. Only the BGS 1:5M "
                          "shapefile and USGS mineral occurrence points are usable. "
                          "Aeromagnetics/gravity not publicly available. "
                          "Consider using Macrostrat as supplementary geology source.",
    },
}


def main():
    p = argparse.ArgumentParser(description="Inventory open geophysics data")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("=== Open Geophysics Inventory ===\n")

    # JSON output
    with open(os.path.join(args.output, "open_geophysics_inventory.json"), "w") as f:
        json.dump(INVENTORY, f, indent=2)

    # Markdown report
    md = "# Open Geophysics Data Inventory\n\n"
    md += "Comprehensive inventory of freely available geophysical data for GeaSpirit pilot zones.\n\n"

    # Summary table
    md += "## Summary\n\n"
    md += "| Zone | Geology | Magnetics | Gravity | Radiometrics | Overall |\n"
    md += "|------|---------|-----------|---------|--------------|--------|\n"

    for zone_name, info in INVENTORY.items():
        has = {"geology": False, "magnetics": False, "gravity": False, "radiometrics": False}
        for ds in info["datasets"]:
            if ds["integrable"]:
                t = ds["type"].lower()
                if "geolog" in t:
                    has["geology"] = True
                elif "magnet" in t:
                    has["magnetics"] = True
                elif "gravity" in t or "bouguer" in t:
                    has["gravity"] = True
                elif "radiom" in t:
                    has["radiometrics"] = True

        icons = {True: "YES", False: "no"}
        total = sum(has.values())
        grade = "EXCELLENT" if total >= 3 else "MODERATE" if total >= 1 else "POOR"
        md += f"| {zone_name} | {icons[has['geology']]} | {icons[has['magnetics']]} | "
        md += f"{icons[has['gravity']]} | {icons[has['radiometrics']]} | **{grade}** |\n"

    for zone_name, info in INVENTORY.items():
        md += f"\n---\n\n## {info['zone']}\n\n"
        md += f"**Survey**: {info['geology_survey']}\n\n"

        for ds in info["datasets"]:
            status = "INTEGRABLE" if ds["integrable"] else "NOT INTEGRABLE"
            md += f"### {ds['type']} — {status}\n\n"
            md += f"- **Source**: {ds['source']}\n"
            md += f"- **URL**: {ds['url']}\n"
            md += f"- **Format**: {ds['format']}\n"
            md += f"- **Resolution**: {ds['resolution']}\n"
            md += f"- **License**: {ds['license']}\n"
            md += f"- **Coverage**: {ds['coverage']}\n"
            md += f"- **Notes**: {ds['notes']}\n\n"

        md += f"**Recommendation**: {info['recommendation']}\n"

    md += "\n---\n\n## Strategic Recommendation\n\n"
    md += "1. **Pilbara first**: Integrate GA aeromagnetics (80m TMI) + radiometrics (100m K/Th/U) + "
    md += "gravity (800m Bouguer). All CC-BY 4.0, high quality.\n"
    md += "2. **Chile second**: Use SERNAGEOMIN WMS geological map. Explore institutional access "
    md += "for aeromagnetics.\n"
    md += "3. **Zambia third**: BGS 1:5M shapefile as baseline. USGS mineral points for enriched labels. "
    md += "Geophysics requires institutional partnerships.\n\n"
    md += "## Priority Integration Order\n\n"
    md += "| Priority | Dataset | Zone | Expected Impact |\n"
    md += "|----------|---------|------|------------------|\n"
    md += "| 1 | GA Aeromagnetics TMI (80m) | Pilbara | HIGH — structural mapping |\n"
    md += "| 2 | GA Radiometrics K/Th/U (100m) | Pilbara | HIGH — alteration detection |\n"
    md += "| 3 | GSWA 1:100K Geology | Pilbara | HIGH — detailed lithology |\n"
    md += "| 4 | SERNAGEOMIN WMS Geology | Chile | MODERATE — 1:1M resolution |\n"
    md += "| 5 | GA Gravity Bouguer (800m) | Pilbara | MODERATE — regional structure |\n"
    md += "| 6 | BGS Zambia Geology (1:5M) | Zambia | LOW — too coarse |\n"
    md += "| 7 | USGS Africa Mineral Points | Zambia | MODERATE — enriches labels |\n"

    with open(os.path.join(args.output, "open_geophysics_inventory.md"), "w") as f:
        f.write(md)

    print("  Inventory compiled for 3 zones:")
    for zn, info in INVENTORY.items():
        integrable = sum(1 for d in info["datasets"] if d["integrable"])
        total = len(info["datasets"])
        print(f"    {zn}: {integrable}/{total} datasets integrable")
    print(f"\n  Saved: open_geophysics_inventory.json + .md")


if __name__ == "__main__":
    main()
