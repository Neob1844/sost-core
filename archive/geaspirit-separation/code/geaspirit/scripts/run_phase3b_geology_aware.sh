#!/bin/bash
# ============================================================
# GeaSpirit Phase 3B — Geology-Aware Learning Orchestrator
# ============================================================
# Runs all Phase 3B scripts in correct order:
# 1. Curate labels
# 2. Build geology features (per zone)
# 3. Build geology-aware negatives (per zone)
# 4. Train geology-aware + ablation study
# 5. Cross-zone LOZO validation
# 6. Open geophysics inventory
# 7. Conditional: rank targets (only if improvement)
# ============================================================

set -e

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$HOME/SOST/geaspirit/data"
OUTPUT_DIR="$HOME/SOST/geaspirit/outputs"
MODELS_DIR="$HOME/SOST/geaspirit/models"
PYTHON="${PYTHON:-python3}"
ZONES="chuquicamata pilbara zambia"

echo "============================================================"
echo "  GeaSpirit Phase 3B — Geology-Aware Learning"
echo "  $(date)"
echo "============================================================"
echo ""

# Ensure output directories exist
mkdir -p "$DATA_DIR/mrds" "$DATA_DIR/geology_maps" "$DATA_DIR/targets"
mkdir -p "$OUTPUT_DIR" "$MODELS_DIR"

# ============================================================
# STEP 1: Curate Labels
# ============================================================
echo "=== STEP 1: Curate MRDS Labels ==="
$PYTHON "$SCRIPTS_DIR/curate_labels.py" --pilot chuquicamata
echo ""

# ============================================================
# STEP 2: Build Geology Features (per zone with data)
# ============================================================
echo "=== STEP 2: Build Geology Features ==="
for ZONE in $ZONES; do
    STACK="$DATA_DIR/${ZONE}_stack.tif"
    if [ -f "$STACK" ]; then
        echo "--- $ZONE: stack found, building geology features ---"
        $PYTHON "$SCRIPTS_DIR/build_geology_features.py" \
            --pilot "$ZONE" \
            --stack "$STACK" \
            --sample-step 20
    else
        echo "--- $ZONE: NO STACK — skipping geology features ---"
        echo "  To build stack, run satellite download scripts first:"
        echo "    python3 $SCRIPTS_DIR/download_sentinel2.py --pilot $ZONE"
        echo "    python3 $SCRIPTS_DIR/build_sentinel1_features.py --pilot $ZONE"
        echo "    python3 $SCRIPTS_DIR/build_dem_features.py --pilot $ZONE"
        echo "    python3 $SCRIPTS_DIR/build_landsat_thermal.py --pilot $ZONE"
        echo "    python3 $SCRIPTS_DIR/stack_features.py --pilot $ZONE"
    fi
    echo ""
done

# ============================================================
# STEP 3: Build Geology-Aware Negatives (per zone with data)
# ============================================================
echo "=== STEP 3: Build Geology-Aware Negatives ==="
for ZONE in $ZONES; do
    STACK="$DATA_DIR/${ZONE}_stack.tif"
    if [ -f "$STACK" ]; then
        echo "--- $ZONE: building geology-aware negatives ---"
        $PYTHON "$SCRIPTS_DIR/build_geology_aware_negatives.py" \
            --pilot "$ZONE" \
            --stack "$STACK"
    else
        echo "--- $ZONE: NO STACK — skipping negatives ---"
    fi
    echo ""
done

# ============================================================
# STEP 4: Ablation Study (Chuquicamata first)
# ============================================================
echo "=== STEP 4: Ablation Study ==="
CHUQ_STACK="$DATA_DIR/chuquicamata_stack.tif"
if [ -f "$CHUQ_STACK" ]; then
    $PYTHON "$SCRIPTS_DIR/train_geology_aware.py" --pilot chuquicamata
else
    echo "! Chuquicamata stack not found — cannot run ablation"
fi
echo ""

# ============================================================
# STEP 5: Cross-Zone LOZO Validation
# ============================================================
echo "=== STEP 5: Cross-Zone LOZO Validation ==="
$PYTHON "$SCRIPTS_DIR/train_cross_zone.py"
echo ""

# ============================================================
# STEP 6: Open Geophysics Inventory
# ============================================================
echo "=== STEP 6: Open Geophysics Inventory ==="
$PYTHON "$SCRIPTS_DIR/inventory_open_geophysics.py"
echo ""

# ============================================================
# STEP 7: Conditional Target Ranking
# ============================================================
echo "=== STEP 7: Conditional Target Ranking ==="

# Check if ablation results exist and if improvement threshold is met
ABLATION="$OUTPUT_DIR/ablation_spatial_cv.json"
if [ -f "$ABLATION" ]; then
    # Extract improvement from JSON
    IMPROVEMENT=$($PYTHON -c "
import json
with open('$ABLATION') as f:
    data = json.load(f)
delta = data.get('improvement_over_baseline', 0)
print(f'{delta:.4f}')
")
    echo "  Improvement over Phase 3 baseline: $IMPROVEMENT"

    # Check threshold: AUC improvement >= 0.03
    SHOULD_RANK=$($PYTHON -c "
import json
with open('$ABLATION') as f:
    data = json.load(f)
delta_auc = data.get('improvement_over_baseline', 0)
best = data.get('experiments', {}).get(data.get('best_experiment', ''), {}).get('average', {})
delta_pr = best.get('pr_auc', 0) - 0.5007
delta_rec = best.get('recall', 0) - 0.2836
# At least one condition met
if delta_auc >= 0.03 or delta_pr >= 0.05 or delta_rec >= 0.10:
    print('yes')
else:
    print('no')
")

    if [ "$SHOULD_RANK" = "yes" ]; then
        echo "  Improvement threshold MET — regenerating targets"
        if [ -f "$SCRIPTS_DIR/rank_targets.py" ]; then
            $PYTHON "$SCRIPTS_DIR/rank_targets.py" --pilot chuquicamata \
                --model "$MODELS_DIR/geology_aware_model.joblib" 2>/dev/null || \
            echo "  ! rank_targets.py failed (may need model path adjustment)"
        fi
    else
        echo "  Improvement threshold NOT met — keeping Phase 3 targets"
        echo "  No new targets generated. Phase 3 model remains the reference."
    fi
else
    echo "  ! No ablation results found — skipping"
fi

echo ""
echo "============================================================"
echo "  Phase 3B COMPLETE — $(date)"
echo "============================================================"
echo ""
echo "  Check results in: $OUTPUT_DIR/"
echo "  Key files:"
echo "    - mrds_curation_report.md"
echo "    - ablation_spatial_cv.md"
echo "    - feature_family_comparison.csv"
echo "    - lozo_geology_aware.md"
echo "    - open_geophysics_inventory.md"
echo "    - *_geology_sources.md (per zone)"
echo "    - *_negatives_summary.md (per zone)"
echo ""
