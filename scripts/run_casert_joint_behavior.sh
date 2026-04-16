#!/usr/bin/env bash
# Run the CASERT Joint Behavior Test.
#
# Tests the interaction between the bitsQ and equalizer subsystems
# across multiple configurations (slew rates, bitsQ caps, bitsQ on/off).
#
# Usage:
#   ./scripts/run_casert_joint_behavior.sh
#   WORKERS=8 SEEDS=20 ./scripts/run_casert_joint_behavior.sh
#
# Defaults: 4 workers, 10 seeds, 2000 blocks, 1.3 kH/s, medium variance.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

WORKERS="${WORKERS:-4}"
SEEDS="${SEEDS:-10}"
BLOCKS="${BLOCKS:-2000}"
HASHRATE="${HASHRATE:-1.3}"
VARIANCE="${VARIANCE:-medium}"

echo "CASERT Joint Behavior Test"
echo "  Workers:  $WORKERS"
echo "  Seeds:    $SEEDS"
echo "  Blocks:   $BLOCKS"
echo "  Hashrate: $HASHRATE kH/s"
echo "  Variance: $VARIANCE"
echo ""

cd "$PROJECT_DIR"

python3 scripts/casert_joint_behavior.py \
    --workers "$WORKERS" \
    --seeds "$SEEDS" \
    --blocks "$BLOCKS" \
    --hashrate "$HASHRATE" \
    --variance "$VARIANCE"

echo ""
echo "Output files:"
ls -la reports/casert_joint_* reports/casert_dual_* 2>/dev/null || echo "  (no output files found)"
