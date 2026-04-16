#!/usr/bin/env bash
# Run the CASERT V6 pre-fork slew rate validation.
#
# Defaults: 5000 blocks, 50 seeds, 4 workers
# Override with environment variables or arguments:
#   BLOCKS=2000 SEEDS=20 WORKERS=8 ./scripts/run_slew_prefork_validation.sh
#
# Or pass arguments directly:
#   ./scripts/run_slew_prefork_validation.sh --blocks 2000 --seeds 20 --workers 8

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

BLOCKS="${BLOCKS:-5000}"
SEEDS="${SEEDS:-50}"
WORKERS="${WORKERS:-4}"
SEED_START="${SEED_START:-1000}"
REPORT_DIR="${REPORT_DIR:-reports}"

echo "============================================"
echo "CASERT V6 Pre-Fork Slew Rate Validation"
echo "============================================"
echo "  Blocks:     $BLOCKS"
echo "  Seeds:      $SEEDS"
echo "  Workers:    $WORKERS"
echo "  Seed start: $SEED_START"
echo "  Report dir: $REPORT_DIR"
echo ""

python3 scripts/slew_prefork_validation.py \
    --blocks "$BLOCKS" \
    --seeds "$SEEDS" \
    --seed-start "$SEED_START" \
    --workers "$WORKERS" \
    --report-dir "$REPORT_DIR" \
    "$@"

echo ""
echo "Done. Reports in $REPORT_DIR/slew_prefork_*"
