#!/bin/bash
# Custom AOI scanner: Salave, Volcán de Barqueros, Baños de Mula
set -e
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"

echo "=== Custom AOI Scanner ==="

# Define AOIs
$PY "$SCRIPTS/define_aoi.py" --name salave_asturias --center-lat 43.566667 --center-lon -6.899722 --width-km 20 --height-km 20 --notes "Salave gold, Asturias"
$PY "$SCRIPTS/define_aoi.py" --name volcan_barqueros_murcia --center-lat 37.955358 --center-lon -1.360842 --width-km 12 --height-km 12 --notes "Volcan de Barqueros, Murcia"
$PY "$SCRIPTS/define_aoi.py" --name banos_de_mula_murcia --center-lat 38.038208 --center-lon -1.425214 --width-km 12 --height-km 12 --notes "Los Banos de Mula, Murcia"

# Build stacks
for AOI in salave_asturias volcan_barqueros_murcia banos_de_mula_murcia; do
  echo "--- Building: $AOI ---"
  $PY "$SCRIPTS/build_global_aoi_stack.py" --aoi "$AOI" --scale 30 || echo "  ! Stack build issue for $AOI"
done

# Scan all
for AOI in salave_asturias volcan_barqueros_murcia banos_de_mula_murcia; do
  echo "--- Scanning: $AOI ---"
  $PY "$SCRIPTS/scan_aoi_proxies.py" --aoi "$AOI" || echo "  ! Scan issue for $AOI"
done

$PY "$SCRIPTS/list_aoi_inventory.py"
echo "=== Done ==="
