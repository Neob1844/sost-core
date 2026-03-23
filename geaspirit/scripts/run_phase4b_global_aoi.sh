#!/bin/bash
# ============================================================
# GeaSpirit Phase 4B — Global AOI Engine + Kalgoorlie Benchmark
# ============================================================
set -e

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
DATA="$HOME/SOST/geaspirit/data"
OUT="$HOME/SOST/geaspirit/outputs"
MODELS="$HOME/SOST/geaspirit/models"
PY="${PYTHON:-python3}"

echo "============================================================"
echo "  GeaSpirit Phase 4B — Global AOI Engine"
echo "  $(date)"
echo "============================================================"

mkdir -p "$DATA/aois" "$DATA/labels" "$DATA/stack" "$DATA/emit" "$DATA/geophysics"
mkdir -p "$OUT" "$MODELS"

# === STEP 1: Define Kalgoorlie AOI ===
echo "=== STEP 1: Define Kalgoorlie AOI ==="
$PY "$SCRIPTS/define_aoi.py" --name kalgoorlie_50km \
    --center-lat -31.4 --center-lon 121.7 --width-km 50 \
    --notes "Kalgoorlie goldfields — Au/Cu/Ni benchmark"

# Also register legacy zones as AOIs
$PY "$SCRIPTS/define_aoi.py" --name chuquicamata \
    --center-lat -22.3 --center-lon -68.9 --width-km 50 \
    --notes "Legacy pilot — Cu/Au/Ag"
$PY "$SCRIPTS/define_aoi.py" --name pilbara \
    --center-lat -23.1 --center-lon 119.2 --width-km 100 --height-km 100 \
    --notes "Legacy pilot — Fe/Au (sparse MRDS)"
echo ""

# === STEP 2: Ingest Australian labels ===
echo "=== STEP 2: Ingest Australian Labels ==="
$PY "$SCRIPTS/ingest_australia_labels.py"
echo ""

# === STEP 3: Build Kalgoorlie satellite stack ===
echo "=== STEP 3: Build Kalgoorlie Stack ==="
KALG_STACK="$DATA/stack/kalgoorlie_50km_global_stack.tif"
if [ ! -f "$KALG_STACK" ]; then
    $PY "$SCRIPTS/build_global_aoi_stack.py" --aoi kalgoorlie_50km --scale 30
else
    echo "  Stack exists: $KALG_STACK"
fi
echo ""

# === STEP 4: Build geology (Macrostrat) ===
echo "=== STEP 4: Kalgoorlie Geology ==="
if [ -f "$KALG_STACK" ]; then
    $PY "$SCRIPTS/build_geology_features.py" --pilot kalgoorlie_50km \
        --stack "$KALG_STACK" --sample-step 100 \
        --output "$DATA/geology_maps" --reports "$OUT" 2>&1 || echo "  Geology failed — continuing"
fi
echo ""

# === STEP 5: EMIT inventory ===
echo "=== STEP 5: EMIT Inventory ==="
$PY "$SCRIPTS/inventory_emit_coverage.py"
echo ""

# === STEP 6: Build heuristic model ===
echo "=== STEP 6: Heuristic Proxy Model ==="
$PY "$SCRIPTS/build_proxy_heuristic_model.py"
echo ""

# === STEP 7: Kalgoorlie spatial CV ===
echo "=== STEP 7: Kalgoorlie Spatial CV ==="
KALG_LABELS="$DATA/labels/kalgoorlie_50km_labels_curated.csv"
if [ -f "$KALG_STACK" ] && [ -f "$KALG_LABELS" ]; then
    $PY "$SCRIPTS/train_kalgoorlie_spatial_cv.py" --aoi kalgoorlie_50km \
        --stack "$KALG_STACK" --labels "$KALG_LABELS"
else
    echo "  Missing stack or labels — skipping"
fi
echo ""

# === STEP 8: Scan Kalgoorlie (trained if model exists, else heuristic) ===
echo "=== STEP 8: Scan Kalgoorlie ==="
KALG_MODEL="$MODELS/kalgoorlie_50km_best_model.joblib"
if [ -f "$KALG_STACK" ]; then
    if [ -f "$KALG_MODEL" ]; then
        $PY "$SCRIPTS/scan_aoi_proxies.py" --aoi kalgoorlie_50km --model "$KALG_MODEL"
    else
        $PY "$SCRIPTS/scan_aoi_proxies.py" --aoi kalgoorlie_50km
    fi
fi
echo ""

# === STEP 9: Test AOI — scan a NEW zone by coordinates ===
echo "=== STEP 9: Test AOI — Tintic District, Utah ==="
# Classic mining district with known Au/Cu/Ag — good test
$PY "$SCRIPTS/define_aoi.py" --name tintic_utah_30km \
    --center-lat 39.9 --center-lon -112.1 --width-km 30 \
    --notes "Test AOI — Tintic Mining District, Utah (Au/Cu/Ag)"

TINTIC_STACK="$DATA/stack/tintic_utah_30km_global_stack.tif"
if [ ! -f "$TINTIC_STACK" ]; then
    $PY "$SCRIPTS/build_global_aoi_stack.py" --aoi tintic_utah_30km --scale 30
fi
if [ -f "$TINTIC_STACK" ]; then
    $PY "$SCRIPTS/scan_aoi_proxies.py" --aoi tintic_utah_30km
fi
echo ""

# === STEP 10: Inventory ===
echo "=== STEP 10: AOI Inventory ==="
$PY "$SCRIPTS/list_aoi_inventory.py"
echo ""

echo "============================================================"
echo "  Phase 4B COMPLETE — $(date)"
echo "============================================================"
echo "  Key results in: $OUT/"
echo "    - kalgoorlie_50km_spatial_cv.md"
echo "    - kalgoorlie_50km_proxy_summary.md"
echo "    - tintic_utah_30km_proxy_summary.md"
echo "    - australia_labels_ingestion_report.md"
echo "    - aoi_inventory.md"
echo ""
