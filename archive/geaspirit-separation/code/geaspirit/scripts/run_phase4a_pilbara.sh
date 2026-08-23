#!/bin/bash
# ============================================================
# GeaSpirit Phase 4A — Pilbara Pilot Orchestrator
# ============================================================
set -e

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$HOME/SOST/geaspirit/data"
OUTPUT_DIR="$HOME/SOST/geaspirit/outputs"
MODELS_DIR="$HOME/SOST/geaspirit/models"
PYTHON="${PYTHON:-python3}"

echo "============================================================"
echo "  GeaSpirit Phase 4A — Pilbara Open Geophysics Pilot"
echo "  $(date)"
echo "============================================================"
echo ""

mkdir -p "$DATA_DIR/mrds" "$DATA_DIR/geology_maps" "$DATA_DIR/targets"
mkdir -p "$DATA_DIR/geophysics" "$DATA_DIR/emit"
mkdir -p "$OUTPUT_DIR" "$MODELS_DIR"

# ============================================================
# STEP 1: Define commodity profiles
# ============================================================
echo "=== STEP 1: Commodity Profiles ==="
$PYTHON "$SCRIPTS_DIR/define_phase4_commodity_profile.py"
echo ""

# ============================================================
# STEP 2: Curate Pilbara labels
# ============================================================
echo "=== STEP 2: Curate Pilbara Labels ==="
$PYTHON "$SCRIPTS_DIR/curate_labels.py" --pilot pilbara \
    --output "$DATA_DIR/mrds" --reports "$OUTPUT_DIR"
# Rename output to pilbara-specific
if [ -f "$DATA_DIR/mrds/mrds_curated.csv" ]; then
    cp "$DATA_DIR/mrds/mrds_curated.csv" "$DATA_DIR/mrds/pilbara_mrds_curated.csv"
fi
echo ""

# ============================================================
# STEP 3: Build Pilbara satellite stack
# ============================================================
echo "=== STEP 3: Build Pilbara Satellite Stack ==="
PILBARA_STACK="$DATA_DIR/pilbara_stack.tif"

if [ ! -f "$PILBARA_STACK" ]; then
    echo "--- Downloading Sentinel-2 ---"
    $PYTHON "$SCRIPTS_DIR/download_sentinel2.py" --pilot pilbara || echo "  ! S2 download issue"

    echo "--- Computing mineral indices ---"
    S2_FILE=$(ls "$DATA_DIR/sentinel2/pilbara"*.tif 2>/dev/null | head -1)
    if [ -n "$S2_FILE" ]; then
        $PYTHON "$SCRIPTS_DIR/compute_mineral_indices.py" --pilot pilbara \
            --input "$S2_FILE" --output "$DATA_DIR/indices/" || echo "  ! Indices issue"
    fi

    echo "--- Building Sentinel-1 SAR features ---"
    $PYTHON "$SCRIPTS_DIR/build_sentinel1_features.py" --pilot pilbara || echo "  ! S1 issue"

    echo "--- Building DEM features ---"
    $PYTHON "$SCRIPTS_DIR/build_dem_features.py" --pilot pilbara || echo "  ! DEM issue"

    echo "--- Building Landsat thermal ---"
    $PYTHON "$SCRIPTS_DIR/build_landsat_thermal.py" --pilot pilbara || echo "  ! Thermal issue"

    echo "--- Stacking all features ---"
    $PYTHON "$SCRIPTS_DIR/stack_features.py" --pilot pilbara || echo "  ! Stack issue"
else
    echo "  Pilbara stack already exists: $PILBARA_STACK"
fi
echo ""

# ============================================================
# STEP 4: Integrate open geophysics
# ============================================================
echo "=== STEP 4: Pilbara Open Geophysics ==="
if [ -f "$PILBARA_STACK" ]; then
    $PYTHON "$SCRIPTS_DIR/build_pilbara_geophysics.py" --ref-stack "$PILBARA_STACK"
else
    echo "  ! No satellite stack — running geophysics without alignment"
    $PYTHON "$SCRIPTS_DIR/build_pilbara_geophysics.py"
fi
echo ""

# ============================================================
# STEP 5: EMIT coverage inventory
# ============================================================
echo "=== STEP 5: EMIT Coverage Inventory ==="
$PYTHON "$SCRIPTS_DIR/inventory_emit_coverage.py"
echo ""

# ============================================================
# STEP 6: Build geology features (Macrostrat + if available)
# ============================================================
echo "=== STEP 6: Pilbara Geology Features ==="
if [ -f "$PILBARA_STACK" ]; then
    $PYTHON "$SCRIPTS_DIR/build_geology_features.py" --pilot pilbara \
        --stack "$PILBARA_STACK" --sample-step 100
fi
echo ""

# ============================================================
# STEP 7: Build geology-aware negatives
# ============================================================
echo "=== STEP 7: Pilbara Negatives ==="
if [ -f "$PILBARA_STACK" ] && [ -f "$DATA_DIR/mrds/pilbara_mrds_curated.csv" ]; then
    $PYTHON "$SCRIPTS_DIR/build_geology_aware_negatives.py" --pilot pilbara \
        --stack "$PILBARA_STACK" \
        --mrds-curated "$DATA_DIR/mrds/pilbara_mrds_curated.csv"
else
    echo "  ! Missing stack or curated labels — skipping"
fi
echo ""

# ============================================================
# STEP 8: Pilbara ablation study
# ============================================================
echo "=== STEP 8: Pilbara Ablation Study ==="
if [ -f "$PILBARA_STACK" ]; then
    $PYTHON "$SCRIPTS_DIR/train_pilbara_ablation.py" \
        --mrds-curated "$DATA_DIR/mrds/pilbara_mrds_curated.csv"
else
    echo "  ! No satellite stack — cannot run ablation"
fi
echo ""

# ============================================================
# STEP 9: Two-zone transfer
# ============================================================
echo "=== STEP 9: Two-Zone Transfer ==="
$PYTHON "$SCRIPTS_DIR/train_two_zone_transfer.py"
echo ""

# ============================================================
# STEP 10: Conditional target ranking
# ============================================================
echo "=== STEP 10: Conditional Target Ranking ==="
ABLATION="$OUTPUT_DIR/pilbara_ablation.json"
if [ -f "$ABLATION" ]; then
    BEST_AUC=$($PYTHON -c "
import json
with open('$ABLATION') as f:
    data = json.load(f)
print(f'{data.get(\"best_auc\", 0):.4f}')
")
    echo "  Pilbara best AUC: $BEST_AUC"

    SHOULD_RANK=$($PYTHON -c "
import json
with open('$ABLATION') as f:
    data = json.load(f)
if data.get('best_auc', 0) >= 0.80:
    print('yes')
else:
    print('no')
")
    if [ "$SHOULD_RANK" = "yes" ]; then
        echo "  AUC >= 0.80 — generating Pilbara targets"
        # Use rank_targets with Pilbara model
        if [ -f "$SCRIPTS_DIR/rank_targets.py" ] && [ -f "$MODELS_DIR/pilbara_best_model.joblib" ]; then
            $PYTHON "$SCRIPTS_DIR/rank_targets.py" --pilot pilbara \
                --stack "$PILBARA_STACK" \
                --model "$MODELS_DIR/pilbara_best_model.joblib" \
                --output "$OUTPUT_DIR" 2>/dev/null || \
            echo "  ! Target ranking failed"
        fi
    else
        echo "  AUC < 0.80 — Pilbara model not strong enough for target ranking"
    fi
else
    echo "  ! No ablation results — skipping"
fi

echo ""
echo "============================================================"
echo "  Phase 4A COMPLETE — $(date)"
echo "============================================================"
echo ""
echo "  Key results:"
echo "    - $OUTPUT_DIR/pilbara_ablation.md"
echo "    - $OUTPUT_DIR/two_zone_transfer.md"
echo "    - $OUTPUT_DIR/pilbara_geophysics_report.md"
echo "    - $OUTPUT_DIR/emit_coverage_inventory.md"
echo "    - $OUTPUT_DIR/pilbara_commodity_profile.md"
echo ""
